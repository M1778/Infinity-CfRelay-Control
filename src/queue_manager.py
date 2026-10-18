"""Request queue manager - spaces requests to avoid hammering."""

import time
import threading
import logging

log = logging.getLogger("cf-proxy-retry")


class QueueManager:
    """Ensures minimum interval between requests."""

    def __init__(self, min_interval: float = 2.0, enabled: bool = True):
        self.min_interval = min_interval
        self.enabled = enabled
        self._lock = threading.Lock()
        self._last_request = 0.0

    def wait_turn(self):
        """Block until enough time has passed since last request."""
        if not self.enabled:
            return

        with self._lock:
            now = time.time()
            elapsed = now - self._last_request
            if elapsed < self.min_interval:
                wait = self.min_interval - elapsed
                log.debug(f"Queue: waiting {wait:.1f}s before next request")
                time.sleep(wait)
            self._last_request = time.time()
