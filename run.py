#!/usr/bin/env python3
"""Entry point for the 21 Draw Email Assistant."""

import argparse
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from email_assistant.config import get_settings
from email_assistant.main import EmailAssistant
from email_assistant.scheduler.runner import SchedulerRunner


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="21 Draw Email Assistant - Automated follow-up draft generator"
    )
    parser.add_argument(
        "--setup-auth",
        action="store_true",
        help="Run OAuth setup flow (opens browser)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check emails but don't create drafts or mark as processed",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run continuously, checking at configured interval",
    )

    args = parser.parse_args()

    # Load settings
    try:
        settings = get_settings()
    except Exception as e:
        print(f"Error loading settings: {e}")
        print("Make sure you have a .env file with required settings.")
        print("Copy .env.example to .env and fill in your values.")
        sys.exit(1)

    # Initialize assistant
    assistant = EmailAssistant(settings)

    # Handle setup-auth mode
    if args.setup_auth:
        print("Starting OAuth setup...")
        assistant.setup_auth()
        print("\nSetup complete! You can now run the assistant.")
        return

    # Run once or as daemon
    if args.daemon:
        scheduler = SchedulerRunner(
            check_function=lambda: assistant.check_and_process(dry_run=args.dry_run),
            interval_seconds=settings.polling_interval_seconds,
        )
        scheduler.start()
    else:
        results = assistant.check_and_process(dry_run=args.dry_run)

        if args.dry_run:
            print(f"\nDry run complete. Found {len(results)} matching email(s).")
        else:
            success_count = sum(1 for r in results if r.success)
            print(f"\nProcessed {len(results)} email(s), {success_count} draft(s) created.")


if __name__ == "__main__":
    main()
