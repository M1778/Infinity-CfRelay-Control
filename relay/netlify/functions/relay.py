"""
Netlify serverless relay function.

Deploy: copy this directory to a Netlify project, set RELAY_SECRET env var.
File must be at: netlify/functions/relay.py
"""

import base64
import json
import os
import urllib.request
import urllib.error


RELAY_SECRET = os.environ.get("RELAY_SECRET", "")


def _forward(method, url, headers, body):
    req = urllib.request.Request(url, data=body, method=method)
    for k, v in (headers or {}).items():
        if k.lower() not in ("host", "content-length", "connection"):
            try:
                req.add_header(k, v)
            except Exception:
                pass

    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()
    except Exception as e:
        return 502, {}, f"Relay error: {e}".encode()


def handler(event, context):
    # Auth
    headers = event.get("headers", {}) or {}
    # Netlify lowercases headers
    secret = headers.get("x-relay-secret", "")
    if not RELAY_SECRET or secret != RELAY_SECRET:
        return {"statusCode": 401, "body": "Unauthorized"}

    if event.get("httpMethod") == "GET":
        return {"statusCode": 200,
                "body": json.dumps({"status": "ok", "relay": "netlify"})}

    try:
        payload = json.loads(event.get("body") or "{}")
    except Exception:
        return {"statusCode": 400, "body": "Invalid JSON"}

    method = payload.get("method", "GET")
    url = payload.get("url", "")
    fwd_headers = payload.get("headers", {})
    body_b64 = payload.get("body")
    body = base64.b64decode(body_b64) if body_b64 else None

    if not url:
        return {"statusCode": 400, "body": "Missing url"}

    status, resp_headers, resp_body = _forward(method, url, fwd_headers, body)

    result = {
        "status": status,
        "headers": {k: v for k, v in resp_headers.items()
                    if k.lower() not in ("transfer-encoding", "connection")},
        "body": base64.b64encode(resp_body).decode() if resp_body else None,
    }

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(result),
    }
