"""Scheduler for continuous email monitoring."""

import signal
import time
from typing import Callable


class SchedulerRunner:
    """Run email checking on a schedule."""

    def __init__(
        self,
        check_function: Callable[[], None],
        interval_seconds: int,
    ):
        """
        Initialize scheduler.

        Args:
            check_function: Function to call on each check
            interval_seconds: Seconds between checks
        """
        self.check_function = check_function
        self.interval_seconds = interval_seconds
        self._running = False

    def start(self) -> None:
        """Start the scheduler daemon."""
        self._running = True

        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        print(f"Starting email monitor (checking every {self.interval_seconds}s)")
        print("Press Ctrl+C to stop")

        while self._running:
            try:
                self.check_function()
            except Exception as e:
                print(f"Error during check: {e}")

            # Sleep in small increments to allow quick shutdown
            for _ in range(self.interval_seconds):
                if not self._running:
                    break
                time.sleep(1)

        print("Scheduler stopped")

    def _handle_shutdown(self, signum, frame) -> None:
        """Handle shutdown signal."""
        print("\nShutdown signal received...")
        self._running = False
