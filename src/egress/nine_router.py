"""9router Cloudflare relay egress.

Routes requests through 9router's serverless Cloudflare relay,
which gives clean Cloudflare egress IPs that OpenCode doesn't flag.

Requires 9router running with a Cloudflare relay proxy pool configured.
"""

import requests
from typing import Dict, Optional
from .base import EgressProvider, EgressResult


class NineRouterEgress(EgressProvider):
    """Forward via 9router's Cloudflare serverless relay."""

    def __init__(self, relay_url: str, api_key: str, model_prefix: str = "oc/"):
        self.relay_url = relay_url.rstrip("/")
        self.api_key = api_key
        self.model_prefix = model_prefix

    def name(self) -> str:
        return "9router-cloudflare"

    def forward(self, method: str, url: str, headers: Dict[str, str],
                body: Optional[bytes], timeout: int = 30) -> EgressResult:
        """
        Forward through 9router.

        For OpenCode API calls, we route through 9router's /v1 endpoints
        which use the configured Cloudflare relay pool.

        For generic URLs, we use 9router as an HTTP proxy if supported,
        otherwise fall back to direct with a warning.
        """
        # If this is an OpenCode API call, route through 9router's API
        # which uses the Cloudflare relay pool
        if "opencode.ai" in url:
            return self._via_9router_api(method, url, headers, body, timeout)
        else:
            # Generic URL - 9router doesn't proxy arbitrary URLs,
            # so we note this and let the caller handle it
            raise ValueError(
                f"9router egress only supports opencode.ai URLs, got: {url}"
            )

    def _via_9router_api(self, method: str, url: str, headers: Dict[str, str],
                         body: Optional[bytes], timeout: int = 30) -> EgressResult:
        """Route OpenCode API calls through 9router's relay pool."""
        # Map opencode.ai URLs to 9router endpoints
        # 9router exposes OpenAI-compatible and Anthropic-compatible endpoints
        nine_url = url.replace("https://opencode.ai", self.relay_url)
        nine_url = nine_url.replace("http://opencode.ai", self.relay_url)

        clean = {k: v for k, v in headers.items()
                 if k.lower() not in ("proxy-authorization", "proxy-connection",
                                      "host", "content-length")}
        clean["Authorization"] = f"Bearer {self.api_key}"

        resp = requests.request(method, nine_url, headers=clean, data=body,
                                timeout=timeout, allow_redirects=False)
        return EgressResult(resp.status_code, dict(resp.headers), resp.content)

    def health_check(self) -> bool:
        try:
            r = requests.get(f"{self.relay_url}/v1/models",
                             headers={"Authorization": f"Bearer {self.api_key}"},
                             timeout=10)
            return r.status_code == 200
        except Exception:
            return False
