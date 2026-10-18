"""429 retry handler with exponential backoff.

Eleanor's insight: when OpenCode rate-limits you, don't give up —
wait and retry automatically until it succeeds.
"""

import time
import logging
from typing import Callable, List, Optional

from .egress.base import EgressResult

log = logging.getLogger("cf-proxy-retry")


class RetryHandler:
    """Handles automatic retry on 429 rate limits."""

    def __init__(self, max_retries: int = 10, initial_delay: float = 5.0,
                 max_delay: float = 60.0, backoff_multiplier: float = 2.0,
                 retry_on: Optional[List[int]] = None,
                 retry_on_body_contains: Optional[List[str]] = None):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_multiplier = backoff_multiplier
        self.retry_on = retry_on or [429]
        self.retry_on_body_contains = retry_on_body_contains or []

    def should_retry(self, result: EgressResult) -> bool:
        """Check if this result warrants a retry."""
        if result.status_code in self.retry_on:
            return True
        # Also check body for rate limit indicators
        # (some APIs return 200 with error JSON, or wrap the 429)
        try:
            body_str = result.body.decode("utf-8", errors="ignore")
            for pattern in self.retry_on_body_contains:
                if pattern in body_str:
                    return True
        except Exception:
            pass
        return False

    def _backoff_delay(self, attempt: int) -> float:
        """Calculate delay for attempt N (0-indexed)."""
        delay = self.initial_delay * (self.backoff_multiplier ** attempt)
        return min(delay, self.max_delay)

    def execute(self, fn: Callable[[], EgressResult],
                description: str = "request") -> EgressResult:
        """
        Execute fn with automatic retry on 429.

        Args:
            fn: Zero-arg callable returning EgressResult
            description: Human-readable description for logging

        Returns:
            Final EgressResult (success or exhausted retries)
        """
        last_result = None

        for attempt in range(self.max_retries + 1):
            try:
                result = fn()
            except Exception as e:
                log.warning(f"{description}: egress error: {e}")
                if attempt >= self.max_retries:
                    raise
                delay = self._backoff_delay(attempt)
                log.info(f"{description}: error, retry {attempt + 1}/"
                         f"{self.max_retries} in {delay:.0f}s...")
                time.sleep(delay)
                continue

            last_result = result

            if not self.should_retry(result):
                if attempt > 0:
                    log.info(f"{description}: succeeded after "
                             f"{attempt} retries")
                return result

            # Got a 429 - retry with backoff
            if attempt >= self.max_retries:
                log.warning(f"{description}: max retries ({self.max_retries}) "
                            f"exhausted, giving up")
                return result

            delay = self._backoff_delay(attempt)
            log.info(f"{description}: 429 rate limited, "
                     f"retry {attempt + 1}/{self.max_retries} in "
                     f"{delay:.0f}s...")

            # Log rate limit details if available
            try:
                body_preview = result.body[:200].decode("utf-8",
                                                       errors="ignore")
                log.debug(f"429 body preview: {body_preview}")
            except Exception:
                pass

            time.sleep(delay)

        return last_result
