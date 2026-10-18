"""Direct egress - requests go out via local machine IP (no relay)."""

import requests
from typing import Dict, Optional
from .base import EgressProvider, EgressResult


class DirectEgress(EgressProvider):
    """Forward requests directly (local egress IP)."""

    def name(self) -> str:
        return "direct"

    def forward(self, method: str, url: str, headers: Dict[str, str],
                body: Optional[bytes], timeout: int = 30) -> EgressResult:
        # Strip proxy-specific headers
        clean = {k: v for k, v in headers.items()
                 if k.lower() not in ("proxy-authorization", "proxy-connection")}

        resp = requests.request(method, url, headers=clean, data=body,
                                timeout=timeout, allow_redirects=False)
        return EgressResult(resp.status_code, dict(resp.headers), resp.content)
