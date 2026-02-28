"""Configuration management using Pydantic settings."""

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Gmail API
    gmail_credentials_path: Path = Field(
        default=Path("credentials/gmail_credentials.json"),
        description="Path to Gmail OAuth credentials JSON file",
    )
    gmail_token_path: Path = Field(
        default=Path("credentials/token.json"),
        description="Path to store OAuth token after authentication",
    )

    # Anthropic Claude API
    anthropic_api_key: str = Field(
        ...,
        description="Anthropic API key for Claude",
    )

    # Polling
    polling_interval_seconds: int = Field(
        default=300,
        description="Interval between email checks in seconds",
    )

    # Slack (optional - Phase 2)
    slack_webhook_url: Optional[str] = Field(
        default=None,
        description="Slack incoming webhook URL for notifications",
    )

    # Email matching patterns
    gemini_sender: str = Field(
        default="gemini-notes@google.com",
        description="Email address of Gemini meeting notes sender",
    )
    subject_pattern: str = Field(
        default=r'Notes: [\u201c""](?=[^\u201d""]*Marian)(?![^\u201d""]*(?:Darko|Course prod|Beers and Brags|Noras|\bJP\b|Renco|David|Stefan|Maisie))([^\u201d""]+)[\u201d""]',
        description="Regex pattern to match Gemini notes subject lines",
    )

    # Google Drive paths
    drive_base_folder: str = Field(
        default="Ext - 21 Draw/_online_courses",
        description="Base path in Google Drive for artist folders",
    )

    # Gmail label for processed emails
    processed_label: str = Field(
        default="AutoDraft/Processed",
        description="Gmail label to mark processed emails",
    )


def get_settings() -> Settings:
    """Get application settings singleton."""
    return Settings()
