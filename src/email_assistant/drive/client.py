"""Google Drive API client for folder and document lookups."""

from dataclasses import dataclass
from typing import Optional

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials


@dataclass
class DriveItem:
    """Represents a file or folder in Google Drive."""

    id: str
    name: str
    mime_type: str
    web_view_link: Optional[str] = None

    @property
    def is_folder(self) -> bool:
        return self.mime_type == "application/vnd.google-apps.folder"

    def get_shareable_link(self) -> str:
        """Get a shareable link for this item."""
        if self.web_view_link:
            return self.web_view_link
        return f"https://drive.google.com/open?id={self.id}"


class DriveClient:
    """Client for Google Drive API operations."""

    def __init__(self, credentials: Credentials):
        """
        Initialize Drive client.

        Args:
            credentials: Authenticated Google OAuth credentials
        """
        self.service = build("drive", "v3", credentials=credentials)
        self._shared_drive_cache: dict[str, str] = {}

    def _get_shared_drive_id(self, name: str) -> Optional[str]:
        """
        Get a shared drive ID by name.

        Args:
            name: Shared drive name

        Returns:
            Drive ID or None
        """
        if name in self._shared_drive_cache:
            return self._shared_drive_cache[name]

        results = self.service.drives().list(pageSize=50).execute()
        drives = results.get("drives", [])

        for drive in drives:
            self._shared_drive_cache[drive["name"]] = drive["id"]
            if drive["name"].lower() == name.lower():
                return drive["id"]

        return None

    def search_by_name(
        self,
        name: str,
        parent_id: Optional[str] = None,
        mime_type: Optional[str] = None,
        shared_drive_id: Optional[str] = None,
    ) -> list[DriveItem]:
        """
        Search for files/folders by name.

        Args:
            name: Name to search for (partial match)
            parent_id: Optional parent folder ID to search within
            mime_type: Optional MIME type filter
            shared_drive_id: Optional shared drive ID to search within

        Returns:
            List of matching items
        """
        query_parts = [f"name contains '{name}'", "trashed = false"]

        if parent_id:
            query_parts.append(f"'{parent_id}' in parents")
        if mime_type:
            query_parts.append(f"mimeType = '{mime_type}'")

        query = " and ".join(query_parts)

        params = {
            "q": query,
            "fields": "files(id, name, mimeType, webViewLink)",
            "pageSize": 20,
        }

        # Add shared drive parameters if specified
        if shared_drive_id:
            params["corpora"] = "drive"
            params["driveId"] = shared_drive_id
            params["includeItemsFromAllDrives"] = True
            params["supportsAllDrives"] = True
        else:
            params["spaces"] = "drive"

        results = self.service.files().list(**params).execute()

        return [
            DriveItem(
                id=f["id"],
                name=f["name"],
                mime_type=f["mimeType"],
                web_view_link=f.get("webViewLink"),
            )
            for f in results.get("files", [])
        ]

    def find_folder_in_shared_drive(
        self,
        shared_drive_name: str,
        folder_path: str,
    ) -> Optional[DriveItem]:
        """
        Find a folder within a shared drive by path.

        Args:
            shared_drive_name: Name of the shared drive
            folder_path: Forward-slash separated path within the drive

        Returns:
            DriveItem for the folder or None if not found
        """
        drive_id = self._get_shared_drive_id(shared_drive_name)
        if not drive_id:
            return None

        parts = [p.strip() for p in folder_path.split("/") if p.strip()]
        if not parts:
            # Return the drive root
            return DriveItem(id=drive_id, name=shared_drive_name, mime_type="application/vnd.google-apps.folder")

        current_parent_id = drive_id
        current_item = None

        for part in parts:
            items = self.search_by_name(
                name=part,
                parent_id=current_parent_id,
                mime_type="application/vnd.google-apps.folder",
                shared_drive_id=drive_id,
            )

            # Find exact match
            exact_match = None
            for item in items:
                if item.name.lower() == part.lower():
                    exact_match = item
                    break

            if not exact_match:
                # Try fuzzy match (contains)
                if items:
                    exact_match = items[0]
                else:
                    return None

            current_parent_id = exact_match.id
            current_item = exact_match

        return current_item

    def find_artist_folder(self, artist_name: str, base_path: str) -> Optional[DriveItem]:
        """
        Find an artist's folder in the courses directory.

        Args:
            artist_name: Artist name to search for
            base_path: Base path (e.g., "Ext - 21 Draw/_online_courses")

        Returns:
            DriveItem for the artist folder or None if not found
        """
        # Parse base_path - first part is shared drive name, rest is folder path
        parts = [p.strip() for p in base_path.split("/") if p.strip()]
        if not parts:
            return None

        shared_drive_name = parts[0]
        folder_path = "/".join(parts[1:]) if len(parts) > 1 else ""

        # Find the base folder in shared drive
        base_folder = self.find_folder_in_shared_drive(shared_drive_name, folder_path)
        if not base_folder:
            return None

        drive_id = self._get_shared_drive_id(shared_drive_name)

        # Search for artist folder within base
        items = self.search_by_name(
            name=artist_name,
            parent_id=base_folder.id,
            mime_type="application/vnd.google-apps.folder",
            shared_drive_id=drive_id,
        )

        if items:
            # Prefer exact match
            for item in items:
                if artist_name.lower() in item.name.lower():
                    return item
            return items[0]

        return None

    def _list_subfolders(
        self,
        parent_id: str,
        shared_drive_id: Optional[str] = None,
    ) -> list["DriveItem"]:
        """List all immediate subfolder children of a folder."""
        params = {
            "q": f"'{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
            "fields": "files(id, name, mimeType, webViewLink)",
            "pageSize": 20,
        }
        if shared_drive_id:
            params["corpora"] = "drive"
            params["driveId"] = shared_drive_id
            params["includeItemsFromAllDrives"] = True
            params["supportsAllDrives"] = True
        else:
            params["spaces"] = "drive"

        results = self.service.files().list(**params).execute()
        return [
            DriveItem(
                id=f["id"],
                name=f["name"],
                mime_type=f["mimeType"],
                web_view_link=f.get("webViewLink"),
            )
            for f in results.get("files", [])
        ]

    def find_artist_edit_folder(self, artist_name: str, base_path: str) -> Optional[DriveItem]:
        """
        Find the _artist_edit folder for an artist.

        Searches directly inside the artist folder first, then one level
        deeper (inside course subfolders) to handle structures like:
          _artist_name/Course Title/_artist_edit/

        Args:
            artist_name: Artist name
            base_path: Base path for courses

        Returns:
            DriveItem for _artist_edit folder or None
        """
        artist_folder = self.find_artist_folder(artist_name, base_path)
        if not artist_folder:
            return None

        # Get shared drive ID from base_path
        parts = [p.strip() for p in base_path.split("/") if p.strip()]
        shared_drive_name = parts[0] if parts else None
        drive_id = self._get_shared_drive_id(shared_drive_name) if shared_drive_name else None

        # Search for _artist_edit directly within artist folder
        items = self.search_by_name(
            name="_artist_edit",
            parent_id=artist_folder.id,
            mime_type="application/vnd.google-apps.folder",
            shared_drive_id=drive_id,
        )
        if items:
            return items[0]

        # Not found directly — check one level deeper (course subfolders)
        for subfolder in self._list_subfolders(artist_folder.id, drive_id):
            items = self.search_by_name(
                name="_artist_edit",
                parent_id=subfolder.id,
                mime_type="application/vnd.google-apps.folder",
                shared_drive_id=drive_id,
            )
            if items:
                return items[0]

        return None

    def find_course_outline_doc(self, artist_name: str, base_path: str) -> Optional[DriveItem]:
        """
        Find the Course Outline document for an artist.

        Searches in the artist folder and its subfolders (_artist_edit, etc.)

        Args:
            artist_name: Artist name
            base_path: Base path for courses

        Returns:
            DriveItem for the Course Outline doc or None
        """
        artist_folder = self.find_artist_folder(artist_name, base_path)
        if not artist_folder:
            return None

        # Get shared drive ID from base_path
        parts = [p.strip() for p in base_path.split("/") if p.strip()]
        shared_drive_name = parts[0] if parts else None
        drive_id = self._get_shared_drive_id(shared_drive_name) if shared_drive_name else None

        # Folders to search in (artist root + common subfolders)
        folders_to_search = [artist_folder.id]

        # Also search in _artist_edit and course subfolders (one level deep)
        for subfolder in self._list_subfolders(artist_folder.id, drive_id):
            folders_to_search.append(subfolder.id)
            # And _artist_edit inside each course subfolder
            artist_edit_items = self.search_by_name(
                name="_artist_edit",
                parent_id=subfolder.id,
                mime_type="application/vnd.google-apps.folder",
                shared_drive_id=drive_id,
            )
            if artist_edit_items:
                folders_to_search.append(artist_edit_items[0].id)

        # Search for Course Outline doc in each folder
        for folder_id in folders_to_search:
            items = self.search_by_name(
                name="Course Outline",
                parent_id=folder_id,
                shared_drive_id=drive_id,
            )

            if items:
                # Prefer Google Doc
                for item in items:
                    if "document" in item.mime_type:
                        return item
                return items[0]

        return None

    def get_item_by_id(self, file_id: str) -> Optional[DriveItem]:
        """
        Get a Drive item by its ID.

        Args:
            file_id: Google Drive file/folder ID

        Returns:
            DriveItem or None if not found
        """
        try:
            result = (
                self.service.files()
                .get(
                    fileId=file_id,
                    fields="id, name, mimeType, webViewLink",
                    supportsAllDrives=True,
                )
                .execute()
            )
            return DriveItem(
                id=result["id"],
                name=result["name"],
                mime_type=result["mimeType"],
                web_view_link=result.get("webViewLink"),
            )
        except Exception:
            return None
