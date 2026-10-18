#!/usr/bin/env python3
"""
cf-proxy-retry: Cloudflare-routed HTTP proxy with automatic 429 retry.

Usage:
    python -m src.proxy_server [--config config.yaml]
    python src/proxy_server.py [--config config.yaml]
"""

import argparse
import json
import logging
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import urlparse

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.egress.base import EgressProvider
from src.egress.direct import DirectEgress
from src.egress.nine_router import NineRouterEgress
from src.egress.serverless import ServerlessEgress
from src.retry_handler import RetryHandler
from src.queue_manager import QueueManager

log = logging.getLogger("cf-proxy-retry")

# Stats
_stats = {"requests": 0, "retries": 0, "rate_limited": 0, "errors": 0}
_stats_lock = threading.Lock()


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def create_egress(config: dict) -> EgressProvider:
    """Create egress provider from config."""
    egress_cfg = config.get("egress", {})
    provider = egress_cfg.get("provider", "direct")

    if provider == "direct":
        return DirectEgress()
    elif provider == "cloudflare":
        cf = egress_cfg.get("cloudflare", {})
        return NineRouterEgress(
            relay_url=cf.get("relay_url", "http://127.0.0.1:20128"),
            api_key=cf.get("api_key", ""),
            model_prefix=cf.get("model_prefix", "oc/"),
        )
    elif provider == "vercel":
        v = egress_cfg.get("vercel", {})
        return ServerlessEgress(v.get("relay_url", ""), v.get("secret", ""),
                                platform="vercel")
    elif provider == "netlify":
        n = egress_cfg.get("netlify", {})
        return ServerlessEgress(n.get("relay_url", ""), n.get("secret", ""),
                                platform="netlify")
    else:
        raise ValueError(f"Unknown egress provider: {provider}")


class ProxyHandler(BaseHTTPRequestHandler):
    """HTTP proxy request handler."""

    # Set by server
    egress: EgressProvider = None
    retry_handler: RetryHandler = None
    queue: QueueManager = None

    def log_message(self, fmt, *args):
        log.debug(f"{self.address_string()} {fmt % args}")

    def _send_proxy_response(self, status: int, headers: dict, body: bytes):
        self.send_response(status)
        # Filter hop-by-hop headers
        skip = {"transfer-encoding", "connection", "keep-alive",
                "proxy-authenticate", "proxy-authorization", "te",
                "trailer", "upgrade"}
        for k, v in headers.items():
            if k.lower() not in skip:
                try:
                    self.send_header(k, v)
                except Exception:
                    pass
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _handle_health(self):
        """Health check endpoint."""
        healthy = True
        try:
            healthy = self.egress.health_check()
        except Exception as e:
            log.warning(f"Health check failed: {e}")
            healthy = False

        with _stats_lock:
            stats = dict(_stats)

        body = json.dumps({
            "status": "healthy" if healthy else "degraded",
            "egress": self.egress.name(),
            "stats": stats,
        }).encode()

        self.send_response(200 if healthy else 503)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _proxy_request(self):
        # Health check
        if self.path == "/health" or self.path == "/healthz":
            self._handle_health()
            return

        # Parse target URL
        if self.path.startswith("http://") or self.path.startswith("https://"):
            target_url = self.path
        else:
            # Relative path - use Host header
            host = self.headers.get("Host", "")
            if not host:
                self.send_error(400, "Missing Host header")
                return
            target_url = f"http://{host}{self.path}"

        # CONNECT method (HTTPS tunneling) - not supported through relay
        # Client should use HTTP proxy mode, not CONNECT
        if self.command == "CONNECT":
            self.send_error(501, "CONNECT not supported, use plain HTTP proxy mode")
            return

        # Read body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else None

        # Collect headers
        headers = dict(self.headers)

        description = f"{self.command} {urlparse(target_url).netloc}{urlparse(target_url).path[:50]}"

        with _stats_lock:
            _stats["requests"] += 1

        def do_forward():
            self.queue.wait_turn()
            return self.egress.forward(
                self.command, target_url, headers, body, timeout=60
            )

        try:
            result = self.retry_handler.execute(do_forward, description)

            with _stats_lock:
                if result.status_code == 429:
                    _stats["rate_limited"] += 1

            self._send_proxy_response(result.status_code, result.headers,
                                      result.body)
        except Exception as e:
            log.error(f"{description}: failed: {e}")
            with _stats_lock:
                _stats["errors"] += 1
            self.send_error(502, f"Proxy error: {e}")

    # HTTP methods
    do_GET = _proxy_request
    do_POST = _proxy_request
    do_PUT = _proxy_request
    do_DELETE = _proxy_request
    do_PATCH = _proxy_request
    do_HEAD = _proxy_request
    do_OPTIONS = _proxy_request


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    parser = argparse.ArgumentParser(description="cf-proxy-retry")
    parser.add_argument("--config", default="config.yaml",
                        help="Path to config file")
    args = parser.parse_args()

    # Find config
    config_path = args.config
    if not os.path.exists(config_path):
        # Try relative to script
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(script_dir, "config.yaml")
    if not os.path.exists(config_path):
        config_path = os.path.join(script_dir, "config.example.yaml")
        print(f"Warning: using example config at {config_path}")

    config = load_config(config_path)

    # Logging
    log_cfg = config.get("logging", {})
    logging.basicConfig(
        level=getattr(logging, log_cfg.get("level", "INFO")),
        format=log_cfg.get("format", "%(asctime)s [%(levelname)s] %(message)s"),
    )

    # Build components
    egress = create_egress(config)
    log.info(f"Egress provider: {egress.name()}")

    retry_cfg = config.get("retry", {})
    retry_handler = RetryHandler(
        max_retries=retry_cfg.get("max_retries", 10),
        initial_delay=retry_cfg.get("initial_delay", 5.0),
        max_delay=retry_cfg.get("max_delay", 60.0),
        backoff_multiplier=retry_cfg.get("backoff_multiplier", 2.0),
        retry_on=retry_cfg.get("retry_on", [429]),
        retry_on_body_contains=retry_cfg.get("retry_on_body_contains", []),
    )

    queue_cfg = config.get("queue", {})
    queue = QueueManager(
        min_interval=queue_cfg.get("min_interval", 2.0),
        enabled=queue_cfg.get("enabled", True),
    )

    # Wire up handler
    ProxyHandler.egress = egress
    ProxyHandler.retry_handler = retry_handler
    ProxyHandler.queue = queue

    # Start server
    server_cfg = config.get("server", {})
    host = server_cfg.get("host", "127.0.0.1")
    port = server_cfg.get("port", 8895)

    server = ThreadedHTTPServer((host, port), ProxyHandler)
    log.info(f"cf-proxy-retry listening on {host}:{port}")
    log.info(f"Health check: http://{host}:{port}/health")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
