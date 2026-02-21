"""Gmail API client for email operations."""

import base64
import re
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials


@dataclass
class Email:
    """Represents an email message."""

    id: str
    thread_id: str
    subject: str
    sender: str
    recipient: str
    body: str
    snippet: str
    labels: list[str]


class GmailClient:
    """Client for Gmail API operations."""

    def __init__(self, credentials: Credentials):
        """
        Initialize Gmail client.

        Args:
            credentials: Authenticated Google OAuth credentials
        """
        self.service = build("gmail", "v1", credentials=credentials)
        self._label_cache: dict[str, str] = {}

    def search_emails(
        self,
        query: str,
        max_results: int = 10,
    ) -> list[Email]:
        """
        Search for emails matching a query.

        Args:
            query: Gmail search query (same syntax as Gmail search box)
            max_results: Maximum number of results to return

        Returns:
            List of matching emails
        """
        results = (
            self.service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )

        messages = results.get("messages", [])
        emails = []

        for msg in messages:
            email = self.get_email(msg["id"])
            if email:
                emails.append(email)

        return emails

    def get_email(self, message_id: str) -> Optional[Email]:
        """
        Get full email by ID.

        Args:
            message_id: Gmail message ID

        Returns:
            Email object or None if not found
        """
        msg = (
            self.service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )

        headers = {h["name"].lower(): h["value"] for h in msg["payload"]["headers"]}

        # Extract body
        body = self._extract_body(msg["payload"])

        return Email(
            id=msg["id"],
            thread_id=msg["threadId"],
            subject=headers.get("subject", ""),
            sender=headers.get("from", ""),
            recipient=headers.get("to", ""),
            body=body,
            snippet=msg.get("snippet", ""),
            labels=msg.get("labelIds", []),
        )

    def _extract_body(self, payload: dict) -> str:
        """Extract plain text body from email payload."""
        if "body" in payload and payload["body"].get("data"):
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8")

        if "parts" in payload:
            for part in payload["parts"]:
                if part["mimeType"] == "text/plain":
                    if part["body"].get("data"):
                        return base64.urlsafe_b64decode(part["body"]["data"]).decode(
                            "utf-8"
                        )
                elif part["mimeType"].startswith("multipart/"):
                    body = self._extract_body(part)
                    if body:
                        return body

        return ""

    def find_thread_with_contact(self, email_address: str) -> Optional[str]:
        """
        Find an existing email thread with a specific contact.

        Searches inbox and sent mail for conversations with the contact.

        Args:
            email_address: Email address to search for

        Returns:
            Thread ID if found, None otherwise
        """
        # Search for emails to/from this contact
        query = f"from:{email_address} OR to:{email_address}"
        results = (
            self.service.users()
            .messages()
            .list(userId="me", q=query, maxResults=1)
            .execute()
        )

        messages = results.get("messages", [])
        if messages:
            return messages[0]["threadId"]

        return None

    def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        thread_id: Optional[str] = None,
        content_type: str = "plain",
        text_body: Optional[str] = None,
    ) -> dict:
        """
        Create a draft email.

        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body (HTML when content_type="html")
            thread_id: Optional thread ID to reply in existing conversation
            content_type: MIME subtype — "plain" or "html"
            text_body: Plain-text fallback when content_type="html"; triggers
                       multipart/alternative so Gmail opens the draft in rich
                       text mode instead of plain-text mode

        Returns:
            Created draft resource
        """
        if content_type == "html" and text_body is not None:
            message = MIMEMultipart("alternative")
            message.attach(MIMEText(text_body, "plain", "utf-8"))
            message.attach(MIMEText(body, "html", "utf-8"))
        else:
            message = MIMEText(body, content_type, "utf-8")
        message["to"] = to
        message["subject"] = subject

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

        draft_body = {"message": {"raw": raw}}
        if thread_id:
            draft_body["message"]["threadId"] = thread_id

        draft = (
            self.service.users()
            .drafts()
            .create(userId="me", body=draft_body)
            .execute()
        )

        return draft

    def get_or_create_label(self, label_name: str) -> str:
        """
        Get label ID by name, creating if it doesn't exist.

        Args:
            label_name: Label name (can include / for nested labels)

        Returns:
            Label ID
        """
        if label_name in self._label_cache:
            return self._label_cache[label_name]

        # List existing labels
        results = self.service.users().labels().list(userId="me").execute()
        labels = results.get("labels", [])

        for label in labels:
            if label["name"] == label_name:
                self._label_cache[label_name] = label["id"]
                return label["id"]

        # Create new label
        label_body = {
            "name": label_name,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
        }
        created = (
            self.service.users()
            .labels()
            .create(userId="me", body=label_body)
            .execute()
        )
        self._label_cache[label_name] = created["id"]
        return created["id"]

    def add_label(self, message_id: str, label_name: str) -> None:
        """
        Add a label to a message.

        Args:
            message_id: Gmail message ID
            label_name: Label name to add
        """
        label_id = self.get_or_create_label(label_name)
        self.service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"addLabelIds": [label_id]},
        ).execute()

    def has_label(self, message_id: str, label_name: str) -> bool:
        """
        Check if a message has a specific label.

        Args:
            message_id: Gmail message ID
            label_name: Label name to check

        Returns:
            True if message has the label
        """
        label_id = self.get_or_create_label(label_name)
        msg = (
            self.service.users()
            .messages()
            .get(userId="me", id=message_id, format="minimal")
            .execute()
        )
        return label_id in msg.get("labelIds", [])
