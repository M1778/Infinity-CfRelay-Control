"""Tests for retry handler logic."""

import sys
import os
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.retry_handler import RetryHandler
from src.egress.base import EgressResult
from src.queue_manager import QueueManager


class TestRetryHandler(unittest.TestCase):

    def test_success_no_retry(self):
        """Successful request should not retry."""
        handler = RetryHandler(max_retries=3)
        calls = []

        def fn():
            calls.append(1)
            return EgressResult(200, {}, b"ok")

        result = handler.execute(fn, "test")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(len(calls), 1)

    def test_retry_on_429_then_success(self):
        """Should retry on 429 and succeed."""
        handler = RetryHandler(max_retries=3, initial_delay=0.01,
                               max_delay=0.05)
        calls = []

        def fn():
            calls.append(1)
            if len(calls) < 3:
                return EgressResult(429, {}, b"rate limited")
            return EgressResult(200, {}, b"ok")

        result = handler.execute(fn, "test")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(len(calls), 3)

    def test_max_retries_exhausted(self):
        """Should give up after max retries."""
        handler = RetryHandler(max_retries=2, initial_delay=0.01,
                               max_delay=0.05)
        calls = []

        def fn():
            calls.append(1)
            return EgressResult(429, {}, b"rate limited")

        result = handler.execute(fn, "test")
        self.assertEqual(result.status_code, 429)
        self.assertEqual(len(calls), 3)  # initial + 2 retries

    def test_backoff_timing(self):
        """Backoff should increase exponentially."""
        handler = RetryHandler(initial_delay=5.0, max_delay=60.0,
                               backoff_multiplier=2.0)
        self.assertEqual(handler._backoff_delay(0), 5.0)
        self.assertEqual(handler._backoff_delay(1), 10.0)
        self.assertEqual(handler._backoff_delay(2), 20.0)
        self.assertEqual(handler._backoff_delay(3), 40.0)
        self.assertEqual(handler._backoff_delay(4), 60.0)  # capped
        self.assertEqual(handler._backoff_delay(10), 60.0)  # capped

    def test_body_pattern_retry(self):
        """Should retry when body contains rate limit pattern."""
        handler = RetryHandler(
            max_retries=1, initial_delay=0.01, max_delay=0.05,
            retry_on_body_contains=["FreeUsageLimitError"])
        calls = []

        def fn():
            calls.append(1)
            if len(calls) == 1:
                return EgressResult(200, {},
                                    b'{"error":{"type":"FreeUsageLimitError"}}')
            return EgressResult(200, {}, b"ok")

        result = handler.execute(fn, "test")
        self.assertEqual(len(calls), 2)
        self.assertEqual(result.body, b"ok")


class TestQueueManager(unittest.TestCase):

    def test_min_interval(self):
        """Should enforce minimum interval between requests."""
        q = QueueManager(min_interval=0.2, enabled=True)
        start = time.time()
        q.wait_turn()
        q.wait_turn()
        q.wait_turn()
        elapsed = time.time() - start
        # 3 requests with 0.2s spacing = at least 0.4s
        self.assertGreaterEqual(elapsed, 0.35)

    def test_disabled(self):
        """Disabled queue should not wait."""
        q = QueueManager(min_interval=10.0, enabled=False)
        start = time.time()
        q.wait_turn()
        q.wait_turn()
        elapsed = time.time() - start
        self.assertLess(elapsed, 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
