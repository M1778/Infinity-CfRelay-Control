"""Serverless relay egress (Vercel / Netlify).

Routes requests through your own deployed serverless function,
giving you private egress IPs (not shared with other users).

Deploy the relay function from relay/vercel/ or relay/netlify/
then point this at your deployment URL.
"""

import base64
import requests
from typing import Dict, Optional
from .base import EgressProvider, EgressResult


class ServerlessEgress(EgressProvider):
    """Forward via a custom serverless relay function."""

    def __init__(self, relay_url: str, secret: str, platform: str = "vercel"):
        self.relay_url = relay_url
        self.secret = secret
        self.platform = platform

    def name(self) -> str:
        return f"{self.platform}-relay"

    def forward(self, method: str, url: str, headers: Dict[str, str],
                body: Optional[bytes], timeout: int = 30) -> EgressResult:
        # Package the request for the relay function
        payload = {
            "method": method,
            "url": url,
            "headers": {k: v for k, v in headers.items()
                        if k.lower() not in ("proxy-authorization",
                                             "proxy-connection", "host")},
            "body": base64.b64encode(body).decode() if body else None,
        }

        resp = requests.post(
            self.relay_url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "X-Relay-Secret": self.secret,
            },
            timeout=timeout + 10,  # relay adds overhead
        )

        if resp.status_code != 200:
            # Relay itself failed
            return EgressResult(resp.status_code, dict(resp.headers), resp.content)

        data = resp.json()
        result_body = base64.b64decode(data["body"]) if data.get("body") else b""
        return EgressResult(
            data["status"],
            data.get("headers", {}),
            result_body,
        )

    def health_check(self) -> bool:
        try:
            r = requests.post(
                self.relay_url,
                json={"method": "GET", "url": "https://httpbin.org/status/200",
                      "headers": {}, "body": None},
                headers={"X-Relay-Secret": self.secret},
                timeout=15,
            )
            return r.status_code == 200
        except Exception:
            return False
