"""Slack webhook notifications."""

from typing import Optional

import requests


class SlackNotifier:
    """Send notifications via Slack incoming webhooks."""

    def __init__(self, webhook_url: Optional[str] = None):
        """
        Initialize Slack notifier.

        Args:
            webhook_url: Slack incoming webhook URL (if None, notifications are no-ops)
        """
        self.webhook_url = webhook_url

    def is_configured(self) -> bool:
        """Check if Slack notifications are configured."""
        return bool(self.webhook_url)

    def send_draft_ready(
        self,
        artist_name: str,
        artist_email: str,
        draft_link: str,
        in_thread: bool = False,
    ) -> bool:
        """
        Send notification that a draft is ready for review.

        Args:
            artist_name: Name of the artist
            artist_email: Artist's email address
            draft_link: Link to the Gmail draft
            in_thread: Whether draft is a reply in existing thread

        Returns:
            True if sent successfully (or notifications disabled)
        """
        if not self.is_configured():
            return True

        thread_note = " (reply in existing thread)" if in_thread else " (new email)"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "📧 New Email Draft Ready for Review",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Artist:*\n{artist_name}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Email:*\n{artist_email}",
                    },
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Type:* Follow-up email{thread_note}",
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Open Draft in Gmail",
                            "emoji": True,
                        },
                        "url": draft_link,
                        "style": "primary",
                    },
                ],
            },
        ]

        return self._send_message(blocks=blocks)

    def send_error(self, error_message: str, context: Optional[str] = None) -> bool:
        """
        Send error notification.

        Args:
            error_message: Error description
            context: Optional additional context

        Returns:
            True if sent successfully
        """
        if not self.is_configured():
            return True

        text = f"⚠️ *Email Assistant Error*\n\n{error_message}"
        if context:
            text += f"\n\n_Context: {context}_"

        return self._send_message(text=text)

    def _send_message(
        self,
        text: Optional[str] = None,
        blocks: Optional[list] = None,
    ) -> bool:
        """
        Send a message to Slack.

        Args:
            text: Simple text message (fallback)
            blocks: Rich block kit message

        Returns:
            True if successful
        """
        if not self.webhook_url:
            return False

        payload = {}
        if text:
            payload["text"] = text
        if blocks:
            payload["blocks"] = blocks

        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10,
            )
            return response.status_code == 200
        except requests.RequestException:
            return False
