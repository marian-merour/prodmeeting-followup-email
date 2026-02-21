"""Draft email generator orchestrator."""

import re
from dataclasses import dataclass
import markdown as md_lib
from pathlib import Path
from typing import Optional

from ..gmail.client import GmailClient
from ..drive.client import DriveClient
from ..parser.notes_parser import MeetingData
from .templates import TemplateLoader


# Static links that don't change per artist
REFERENCES_LINK = "https://drive.google.com/open?id=1AWlDLh-6TPDGcFWE5uDoTQHB0fN0Cauu&usp=drive_fs"
TECH_GUIDELINES_LINK = "https://docs.google.com/document/d/1-mEJzqgESWEyxjRzKMbh4mP-pxX-AqPgmPyvI0HMqTU/edit?usp=sharing"


@dataclass
class DraftResult:
    """Result of draft generation."""

    success: bool
    draft_id: Optional[str] = None
    draft_link: Optional[str] = None
    error: Optional[str] = None
    artist_name: Optional[str] = None
    artist_email: Optional[str] = None
    in_thread: bool = False


class DraftGenerator:
    """Orchestrate draft email generation."""

    def __init__(
        self,
        gmail_client: GmailClient,
        drive_client: DriveClient,
        templates_dir: Path,
        drive_base_path: str,
    ):
        """
        Initialize draft generator.

        Args:
            gmail_client: Gmail API client
            drive_client: Google Drive API client
            templates_dir: Path to email templates directory
            drive_base_path: Base path in Drive for artist folders
        """
        self.gmail = gmail_client
        self.drive = drive_client
        self.templates = TemplateLoader(templates_dir)
        self.drive_base_path = drive_base_path

    def _extract_name_from_email(self, email_address: str) -> Optional[str]:
        """
        Try to extract a name from email address.

        E.g., "john.smith@gmail.com" -> "John Smith"
        """
        if not email_address or "@" not in email_address:
            return None

        local_part = email_address.split("@")[0]
        # Split by dots, underscores, or numbers and capitalize
        parts = re.split(r'[._0-9]+', local_part)
        parts = [p.capitalize() for p in parts if p and len(p) > 1]

        if parts:
            return " ".join(parts)
        return None

    def _find_legal_name_from_threads(self, artist_email: str) -> Optional[str]:
        """
        Search email threads with the artist to find their legal name.

        The legal name may differ from their pen name used in meeting titles.
        """
        if not artist_email:
            return None

        # Search for emails from this artist
        emails = self.gmail.search_emails(f"from:{artist_email}", max_results=5)

        for email in emails:
            sender = email.sender
            # Extract name from "John Smith <john@example.com>" format
            if "<" in sender:
                name_part = sender.split("<")[0].strip()
                # Remove quotes if present
                name_part = name_part.strip('"').strip("'")
                if name_part and len(name_part) > 2:
                    return name_part

        # Fallback: try to extract from email address
        return self._extract_name_from_email(artist_email)

    def _find_legal_name_from_internal_emails(self, artist_email: str) -> Optional[str]:
        """
        Search emails from Gerardo or Chris that mention this artist.

        These internal emails often contain the artist's legal name in formats like:
        - Subject: "Alejandra Oviedo artist info"
        - "Name <email>"
        - "Name (email)"
        - "Name - email"
        """
        if not artist_email:
            return None

        internal_senders = ["gerardo@21-draw.com", "chris@21-draw.com"]

        for sender in internal_senders:
            query = f"from:{sender} {artist_email}"
            emails = self.gmail.search_emails(query, max_results=3)

            for email in emails:
                body = email.body
                subject = email.subject

                # Check subject line for patterns like "Name artist info" or "Re: Name artist info"
                subject_patterns = [
                    r'(?:Re:\s*)?([A-Z][a-zà-ÿ]+ [A-Z][a-zà-ÿ]+)\s+artist\s+info',
                    r'(?:Re:\s*)?([A-Z][a-zà-ÿ]+ [A-Z][a-zà-ÿ]+)\s*[-–]\s*artist',
                ]
                for pattern in subject_patterns:
                    match = re.search(pattern, subject, re.IGNORECASE)
                    if match:
                        return match.group(1)

                # Search email body for name near the artist's email
                body_patterns = [
                    rf'([A-Z][a-zà-ÿ]+ [A-Z][a-zà-ÿ]+)\s*<{re.escape(artist_email)}>',
                    rf'([A-Z][a-zà-ÿ]+ [A-Z][a-zà-ÿ]+)\s*\({re.escape(artist_email)}\)',
                    rf'([A-Z][a-zà-ÿ]+ [A-Z][a-zà-ÿ]+)\s*[-–]\s*{re.escape(artist_email)}',
                ]
                for pattern in body_patterns:
                    match = re.search(pattern, body, re.IGNORECASE)
                    if match:
                        return match.group(1)

        return None

    def _find_artist_folders_with_fallback(
        self,
        artist_name: str,
        artist_email: Optional[str] = None,
    ) -> tuple[Optional[object], Optional[object], str]:
        """
        Find artist folders, trying pen name first, then legal name from emails.

        Returns:
            Tuple of (artist_edit_folder, course_outline_doc, name_used)
        """
        # Try with the given artist name (pen name from meeting title)
        artist_edit_folder = self.drive.find_artist_edit_folder(
            artist_name,
            self.drive_base_path,
        )

        if artist_edit_folder:
            course_outline_doc = self.drive.find_course_outline_doc(
                artist_name,
                self.drive_base_path,
            )
            return artist_edit_folder, course_outline_doc, artist_name

        # Try with legal name from email threads
        if artist_email:
            legal_name = self._find_legal_name_from_threads(artist_email)
            if legal_name and legal_name.lower() != artist_name.lower():
                print(f"  Folder not found for '{artist_name}', trying legal name: '{legal_name}'")

                artist_edit_folder = self.drive.find_artist_edit_folder(
                    legal_name,
                    self.drive_base_path,
                )

                if artist_edit_folder:
                    course_outline_doc = self.drive.find_course_outline_doc(
                        legal_name,
                        self.drive_base_path,
                    )
                    return artist_edit_folder, course_outline_doc, legal_name

                # Try just the first name
                first_name = legal_name.split()[0]
                if first_name.lower() != artist_name.lower():
                    print(f"  Trying first name only: '{first_name}'")
                    artist_edit_folder = self.drive.find_artist_edit_folder(
                        first_name,
                        self.drive_base_path,
                    )

                    if artist_edit_folder:
                        course_outline_doc = self.drive.find_course_outline_doc(
                            first_name,
                            self.drive_base_path,
                        )
                        return artist_edit_folder, course_outline_doc, first_name

            # Try finding legal name from internal team emails
            internal_name = self._find_legal_name_from_internal_emails(artist_email)
            if internal_name and internal_name.lower() != artist_name.lower():
                print(f"  Trying name from internal emails: '{internal_name}'")
                artist_edit_folder = self.drive.find_artist_edit_folder(
                    internal_name,
                    self.drive_base_path,
                )
                if artist_edit_folder:
                    course_outline_doc = self.drive.find_course_outline_doc(
                        internal_name,
                        self.drive_base_path,
                    )
                    return artist_edit_folder, course_outline_doc, internal_name

        # Nothing found
        return None, None, artist_name

    def generate_draft(
        self,
        meeting_data: MeetingData,
        dry_run: bool = False,
    ) -> DraftResult:
        """
        Generate a follow-up email draft.

        Args:
            meeting_data: Parsed meeting notes data
            dry_run: If True, don't actually create draft

        Returns:
            DraftResult with outcome
        """
        if not meeting_data.artist_email:
            return DraftResult(
                success=False,
                error="Could not extract artist email from meeting notes",
            )

        # Look up Drive folders (with pen name to legal name fallback)
        artist_edit_folder, course_outline_doc, name_used = self._find_artist_folders_with_fallback(
            meeting_data.artist_first_name,
            meeting_data.artist_email,
        )

        if name_used != meeting_data.artist_first_name:
            print(f"  Found folders using name: '{name_used}'")

        # Build template context
        context = {
            "artist_first_name": meeting_data.artist_first_name,
            "course_subject": meeting_data.course_subject or "[Course Subject]",
            "artist_edit_link": (
                artist_edit_folder.get_shareable_link()
                if artist_edit_folder
                else "[Link to _artist_edit folder - NOT FOUND]"
            ),
            "course_outline_link": (
                course_outline_doc.get_shareable_link()
                if course_outline_doc
                else "[Link to Course Outline doc - NOT FOUND]"
            ),
            "references_link": REFERENCES_LINK,
            "tech_guidelines_link": TECH_GUIDELINES_LINK,
            "outline_delivery_date": meeting_data.outline_delivery_date,
            "demo_video_date": meeting_data.demo_video_date,
            "contract_timeline": meeting_data.contract_timeline,
            "checkin_schedule": meeting_data.checkin_schedule,
            "action_items": meeting_data.action_items,
        }

        # Render email body
        body = self.templates.render("artist_followup.md", **context)

        if dry_run:
            print("\n=== DRY RUN - Draft would be created ===")
            print(f"To: {meeting_data.artist_email}")
            print(f"Subject: Re: 21 Draw Course Production")
            print(f"\n{body}")
            print("=== END DRY RUN ===\n")
            return DraftResult(
                success=True,
                artist_name=meeting_data.artist_first_name,
                artist_email=meeting_data.artist_email,
            )

        # Find existing thread with artist
        thread_id = self.gmail.find_thread_with_contact(meeting_data.artist_email)

        # Create draft
        subject = "Re: 21 Draw Course Production" if thread_id else "21 Draw Course Production - Follow Up"

        html_body = md_lib.markdown(body)

        draft = self.gmail.create_draft(
            to=meeting_data.artist_email,
            subject=subject,
            body=html_body,
            thread_id=thread_id,
            content_type="html",
        )

        draft_id = draft["id"]
        # Gmail draft link format
        draft_link = f"https://mail.google.com/mail/u/0/#drafts?compose={draft['message']['id']}"

        return DraftResult(
            success=True,
            draft_id=draft_id,
            draft_link=draft_link,
            artist_name=meeting_data.artist_first_name,
            artist_email=meeting_data.artist_email,
            in_thread=thread_id is not None,
        )
