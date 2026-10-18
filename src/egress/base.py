"""Egress provider interface - how requests leave to the internet."""

from abc import ABC, abstractmethod
from typing import Dict, Tuple, Optional


class EgressResult:
    """Result of an egress request."""
    def __init__(self, status_code: int, headers: Dict[str, str], body: bytes):
        self.status_code = status_code
        self.headers = headers
        self.body = body


class EgressProvider(ABC):
    """Base class for egress providers."""

    @abstractmethod
    def forward(self, method: str, url: str, headers: Dict[str, str],
                body: Optional[bytes], timeout: int = 30) -> EgressResult:
        """
        Forward an HTTP request through this egress provider.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Full target URL
            headers: Request headers
            body: Request body (None for GET/HEAD)
            timeout: Request timeout in seconds

        Returns:
            EgressResult with status, headers, body
        """
        pass

    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""
        pass

    def health_check(self) -> bool:
        """Optional health check. Default: always healthy."""
        return True
