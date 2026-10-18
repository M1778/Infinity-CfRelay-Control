"""
Vercel serverless relay function.

Deploy: copy this directory to a Vercel project, set RELAY_SECRET env var.

Each invocation gets a fresh Vercel egress IP (rotation built-in).
"""

import base64
import os
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler


RELAY_SECRET = os.environ.get("RELAY_SECRET", "")


def _forward(method, url, headers, body):
    """Forward HTTP request and return (status, headers, body)."""
    req = urllib.request.Request(url, data=body, method=method)
    for k, v in (headers or {}).items():
        # Skip headers that break forwarding
        if k.lower() not in ("host", "content-length", "connection"):
            try:
                req.add_header(k, v)
            except Exception:
                pass

    try:
        with urllib.request.urlopen(req, timeout=55) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()
    except Exception as e:
        return 502, {}, f"Relay error: {e}".encode()


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        # Auth check
        secret = self.headers.get("X-Relay-Secret", "")
        if not RELAY_SECRET or secret != RELAY_SECRET:
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"Unauthorized")
            return

        # Parse payload
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)

        import json
        try:
            payload = json.loads(raw)
        except Exception:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Invalid JSON")
            return

        method = payload.get("method", "GET")
        url = payload.get("url", "")
        headers = payload.get("headers", {})
        body_b64 = payload.get("body")
        body = base64.b64decode(body_b64) if body_b64 else None

        if not url:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Missing url")
            return

        status, resp_headers, resp_body = _forward(method, url, headers, body)

        # Return packaged response
        result = {
            "status": status,
            "headers": {k: v for k, v in resp_headers.items()
                        if k.lower() not in ("transfer-encoding", "connection")},
            "body": base64.b64encode(resp_body).decode() if resp_body else None,
        }
        result_json = json.dumps(result).encode()

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(result_json)))
        self.end_headers()
        self.wfile.write(result_json)

    def do_GET(self):
        # Simple health check
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok","relay":"vercel"}')
