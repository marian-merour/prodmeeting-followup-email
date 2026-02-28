"""Main orchestration for the email assistant."""

import re
from pathlib import Path
from typing import Optional

from .config import Settings
from .gmail.auth import GmailAuth
from .gmail.client import GmailClient, Email
from .drive.client import DriveClient
from .sheets.client import SheetsClient
from .parser.notes_parser import NotesParser, MeetingData
from .drafts.generator import DraftGenerator, DraftResult
from .notifications.slack import SlackNotifier


class EmailAssistant:
    """Main email assistant orchestrator."""

    def __init__(self, settings: Settings):
        """
        Initialize the email assistant.

        Args:
            settings: Application settings
        """
        self.settings = settings
        self._gmail_client: Optional[GmailClient] = None
        self._drive_client: Optional[DriveClient] = None
        self._sheets_client: Optional[SheetsClient] = None
        self._notes_parser: Optional[NotesParser] = None
        self._draft_generator: Optional[DraftGenerator] = None
        self._slack: Optional[SlackNotifier] = None

    def _parse_email_from_address_header(
        self, header_value: str, name_hint: str = ""
    ) -> Optional[str]:
        """
        Extract a valid (non-system) email address from an address header value.

        Handles "Name <email>" format and plain email addresses.
        If name_hint is provided, prefers entries whose display name contains it.

        Args:
            header_value: Raw header value (e.g. To: or From: contents),
                          may be comma-separated for multiple recipients.
            name_hint: Artist name fragment to prefer when multiple recipients exist.

        Returns:
            Email address string, or None if not found / only system emails.
        """
        entries = [e.strip() for e in header_value.split(",")]

        # Two passes: first try entries whose display name matches the hint,
        # then fall back to any valid entry.
        for pass_entries in (
            [e for e in entries if name_hint.lower() in e.lower()] if name_hint else [],
            entries,
        ):
            for entry in pass_entries:
                if "<" in entry and ">" in entry:
                    m = re.search(r"<([^>]+)>", entry)
                    if m:
                        addr = m.group(1)
                        if "google.com" not in addr and "noreply" not in addr:
                            return addr
                elif "@" in entry:
                    if "google.com" not in entry and "noreply" not in entry:
                        return entry

        return None

    def _find_artist_email_in_gmail(self, artist_name: str) -> Optional[str]:
        """
        Search Gmail for the artist's email address.

        First looks for emails FROM the artist (inbox search), then falls back
        to emails sent TO the artist (sent folder search).

        Args:
            artist_name: Artist name to search for

        Returns:
            Email address if found, None otherwise
        """
        # A: Search for emails from the artist
        for email in self._gmail_client.search_emails(f"from:{artist_name}", max_results=5):
            addr = self._parse_email_from_address_header(email.sender)
            if addr:
                return addr

        # B: Search sent folder for emails to the artist
        for email in self._gmail_client.search_emails(
            f"in:sent to:{artist_name}", max_results=5
        ):
            addr = self._parse_email_from_address_header(email.recipient, name_hint=artist_name)
            if addr:
                return addr

        return None

    def _extract_email_from_invited_line(self, notes_text: str) -> Optional[str]:
        """
        Extract artist email from the 'Invited:' line in Gemini meeting notes.

        The Invited line lists all participants including Marian Merour.
        We return the first email that does NOT belong to Marian Merour.

        Args:
            notes_text: Raw meeting notes text (email body)

        Returns:
            Artist email address if found, None otherwise
        """
        for line in notes_text.splitlines():
            if re.match(r"^\s*invited\s*:", line, re.IGNORECASE):
                # Remove "Invited:" prefix
                participants_str = re.sub(r"^\s*invited\s*:\s*", "", line, flags=re.IGNORECASE)
                # Split by comma — each entry is one participant
                for entry in participants_str.split(","):
                    entry = entry.strip()
                    # Skip Marian's entry
                    if "marian merour" in entry.lower():
                        continue
                    # Extract email from angle brackets: Name <email@example.com>
                    bracket_match = re.search(r"<([^>]+@[^>]+)>", entry)
                    if bracket_match:
                        return bracket_match.group(1).strip()
                    # Extract raw email address if no angle brackets
                    raw_match = re.search(r"[\w.+-]+@[\w.-]+\.\w+", entry)
                    if raw_match:
                        return raw_match.group(0).strip()
        return None

    def setup_auth(self) -> None:
        """Run interactive OAuth setup."""
        auth = GmailAuth(
            credentials_path=self.settings.gmail_credentials_path,
            token_path=self.settings.gmail_token_path,
        )
        auth.setup_auth()

    def _initialize_clients(self) -> None:
        """Initialize API clients (lazy initialization)."""
        if self._gmail_client is not None:
            return

        auth = GmailAuth(
            credentials_path=self.settings.gmail_credentials_path,
            token_path=self.settings.gmail_token_path,
        )
        credentials = auth.get_credentials()

        self._gmail_client = GmailClient(credentials)
        self._drive_client = DriveClient(credentials)
        self._sheets_client = SheetsClient(credentials)
        self._notes_parser = NotesParser(self.settings.anthropic_api_key)

        templates_dir = Path(__file__).parent.parent.parent / "config" / "templates"
        self._draft_generator = DraftGenerator(
            gmail_client=self._gmail_client,
            drive_client=self._drive_client,
            sheets_client=self._sheets_client,
            spreadsheet_id=self.settings.sheets_spreadsheet_id,
            sheets_gid=self.settings.sheets_gid,
            templates_dir=templates_dir,
            drive_base_path=self.settings.drive_base_folder,
        )

        self._slack = SlackNotifier(self.settings.slack_webhook_url)

    def check_and_process(self, dry_run: bool = False, broad_search: bool = False) -> list[DraftResult]:
        """
        Check for new Gemini notes emails and process them.

        Args:
            dry_run: If True, don't create drafts or mark as processed
            broad_search: If True, use subject:Marian instead of subject:"21 Draw Course Production"

        Returns:
            List of draft results
        """
        self._initialize_clients()

        results = []

        # Search for Gemini notes emails
        if broad_search:
            query = f'from:{self.settings.gemini_sender} subject:Marian'
        else:
            query = f'from:{self.settings.gemini_sender} subject:"21 Draw Course Production"'
        emails = self._gmail_client.search_emails(query, max_results=10)

        for email in emails:
            # Skip if already processed
            if not dry_run and self._gmail_client.has_label(
                email.id, self.settings.processed_label
            ):
                continue

            # Check if subject matches our pattern
            match = re.search(self.settings.subject_pattern, email.subject)
            if not match:
                continue

            artist_name_from_subject = match.group(1).strip()
            print(f"Found matching email: {email.subject}")
            print(f"  Artist from subject: {artist_name_from_subject}")

            # Parse meeting notes
            try:
                meeting_data = self._notes_parser.parse(
                    email.body,
                    artist_name_hint=artist_name_from_subject,
                )
                print(f"  Parsed artist: {meeting_data.artist_first_name}")
                print(f"  Artist email: {meeting_data.artist_email}")
                print(f"  Course subject: {meeting_data.course_subject}")

                # If Claude didn't extract the email, try the Invited line first
                if not meeting_data.artist_email:
                    print(f"  Email not in notes, scanning Invited line...")
                    found_email = self._extract_email_from_invited_line(email.body)
                    if found_email:
                        meeting_data.artist_email = found_email
                        print(f"  Found email in Invited line: {found_email}")
                    else:
                        # Final fallback: search Gmail
                        print(f"  Invited line not found, searching Gmail inbox and sent folder...")
                        found_email = self._find_artist_email_in_gmail(artist_name_from_subject)
                        if found_email:
                            meeting_data.artist_email = found_email
                            print(f"  Found email in Gmail: {found_email}")
                        else:
                            print(f"  Could not find artist email")
            except Exception as e:
                print(f"  Error parsing notes: {e}")
                if self._slack and self._slack.is_configured():
                    self._slack.send_error(
                        f"Failed to parse meeting notes: {e}",
                        context=f"Subject: {email.subject}",
                    )
                continue

            # Generate draft
            try:
                result = self._draft_generator.generate_draft(
                    meeting_data,
                    dry_run=dry_run,
                )
                results.append(result)

                if result.success:
                    print(f"  Draft created: {result.draft_link}")

                    # Mark as processed
                    if not dry_run:
                        self._gmail_client.add_label(
                            email.id,
                            self.settings.processed_label,
                        )

                    # Send Slack notification
                    if (
                        not dry_run
                        and self._slack
                        and self._slack.is_configured()
                        and result.draft_link
                    ):
                        self._slack.send_draft_ready(
                            artist_name=result.artist_name or "Unknown",
                            artist_email=result.artist_email or "",
                            draft_link=result.draft_link,
                            in_thread=result.in_thread,
                        )
                else:
                    print(f"  Draft generation failed: {result.error}")
            except Exception as e:
                print(f"  Error generating draft: {e}")
                if self._slack and self._slack.is_configured():
                    self._slack.send_error(
                        f"Failed to generate draft: {e}",
                        context=f"Artist: {meeting_data.artist_first_name}",
                    )

        if not results:
            print("No new matching emails found")

        return results
