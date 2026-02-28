"""Gmail OAuth2 authentication handling."""

import json
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Scopes for Gmail API - deliberately excludes gmail.send
# We only create drafts, never send automatically
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",  # Create drafts
    "https://www.googleapis.com/auth/gmail.modify",   # Add labels
    "https://www.googleapis.com/auth/drive.readonly", # Read Drive for folder lookups
    "https://www.googleapis.com/auth/spreadsheets.readonly",  # Read Sheets for contract data
]


class GmailAuth:
    """Handle Gmail OAuth2 authentication."""

    def __init__(self, credentials_path: Path, token_path: Path):
        """
        Initialize Gmail auth handler.

        Args:
            credentials_path: Path to OAuth credentials JSON from Google Cloud Console
            token_path: Path to store/load the authenticated token
        """
        self.credentials_path = credentials_path
        self.token_path = token_path
        self._credentials: Credentials | None = None

    def get_credentials(self) -> Credentials:
        """
        Get valid credentials, refreshing or re-authenticating as needed.

        Returns:
            Valid Google OAuth credentials
        """
        if self._credentials and self._credentials.valid:
            return self._credentials

        # Try to load existing token
        if self.token_path.exists():
            self._credentials = Credentials.from_authorized_user_file(
                str(self.token_path), SCOPES
            )

        # Refresh if expired
        if self._credentials and self._credentials.expired and self._credentials.refresh_token:
            self._credentials.refresh(Request())
            self._save_token()
            return self._credentials

        # If no valid credentials, need to authenticate
        if not self._credentials or not self._credentials.valid:
            raise RuntimeError(
                "No valid credentials. Run with --setup-auth to authenticate."
            )

        return self._credentials

    def setup_auth(self) -> Credentials:
        """
        Run interactive OAuth flow to authenticate.

        Opens browser for user to authorize the application.

        Returns:
            Newly authenticated credentials
        """
        if not self.credentials_path.exists():
            raise FileNotFoundError(
                f"OAuth credentials file not found: {self.credentials_path}\n"
                "Download from Google Cloud Console and save to this location."
            )

        flow = InstalledAppFlow.from_client_secrets_file(
            str(self.credentials_path), SCOPES
        )
        self._credentials = flow.run_local_server(port=0)
        self._save_token()
        print(f"Authentication successful! Token saved to {self.token_path}")
        return self._credentials

    def _save_token(self) -> None:
        """Save credentials to token file."""
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.token_path, "w") as f:
            f.write(self._credentials.to_json())
