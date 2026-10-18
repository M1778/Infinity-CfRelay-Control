#!/usr/bin/env python3
"""
NordVPN Dynamic Bridge — Full implementation with container control.

API on 127.0.0.1:1442:
  GET  /status                    - current location, IP, available locations
  POST /change_location            - switch to random location (70s cooldown)
  POST /change_location {"location": "se"} - switch to specific country

Proxy on 127.0.0.1:1443 - routes through active NordVPN container
"""
import http.server
import socketserver
import json
import time
import subprocess
import threading
import random
import urllib.request
import os

API_PORT = 1442
PROXY_PORT = 1443
BASE_DIR = os.path.expanduser("~/gluetun-dynamic")
SWITCH_COOLDOWN = 75  # seconds (fraud detection safety)

# Country -> Gluetun SERVER_COUNTRIES value
LOCATIONS = {
    "us": "United States", "nl": "Netherlands", "de": "Germany",
    "uk": "United Kingdom", "ch": "Switzerland", "se": "Sweden",
    "no": "Norway", "dk": "Denmark", "fi": "Finland", "fr": "France",
    "es": "Spain", "it": "Italy", "pl": "Poland", "ca": "Canada",
    "au": "Australia", "jp": "Japan", "sg": "Singapore",
}

current = {"location": "us", "ip": None, "last_switch": 0}
lock = threading.Lock()

def run(cmd, timeout=60):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, r.stdout.strip()
    except Exception as e:
        return False, str(e)

def get_ip_via_proxy(port, timeout=15):
    try:
        req = urllib.request.Request("https://api.ipify.org")
        req.set_proxy(f"http://127.0.0.1:{port}", "http")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode().strip()
    except:
        return None

def create_gluetun_compose(location):
    """Create docker-compose for a NordVPN location."""
    os.makedirs(BASE_DIR, exist_ok=True)
    # Copy credentials from existing setup
    compose = f"""services:
  gluetun:
    image: qmcgaw/gluetun:latest
    container_name: gluetun-dynamic
    cap_add:
      - NET_ADMIN
    devices:
      - /dev/net/tun:/dev/net/tun
    ports:
      - "127.0.0.1:1444:8888"
    volumes:
      - ./nordvpn.env:/gluetun/auth/config.toml:ro
    environment:
      - VPN_SERVICE_PROVIDER=nordvpn
      - VPN_TYPE=openvpn
      - SERVER_COUNTRIES={LOCATIONS[location]}
      - HTTPPROXY=on
      - HTTPPROXY_LOG=off
    restart: unless-stopped
"""
    with open(f"{BASE_DIR}/docker-compose.yml", "w") as f:
        f.write(compose)
    # Copy credentials (Eleanor's NordVPN creds are in ~/gluetun/nordvpn.env)
    run(f"cp ~/gluetun/nordvpn.env {BASE_DIR}/nordvpn.env && chmod 600 {BASE_DIR}/nordvpn.env")

def switch_location(new_location=None):
    global current
    with lock:
        now = time.time()
        elapsed = now - current["last_switch"]
        if elapsed < SWITCH_COOLDOWN and current["last_switch"] > 0:
            return {"error": f"Cooldown: wait {int(SWITCH_COOLDOWN - elapsed)}s", "current": current["location"]}
        
        if not new_location:
            choices = [l for l in LOCATIONS if l != current["location"]]
            new_location = random.choice(choices)
        elif new_location not in LOCATIONS:
            return {"error": f"Unknown location: {new_location}", "available": list(LOCATIONS.keys())}
        
        print(f"[Bridge] Switching {current['location']} -> {new_location}", flush=True)
        
        # Stop existing dynamic container
        run(f"cd {BASE_DIR} && docker compose down 2>/dev/null", timeout=30)
        time.sleep(3)
        
        # Create and start new
        create_gluetun_compose(new_location)
        ok, out = run(f"cd {BASE_DIR} && docker compose up -d", timeout=60)
        if not ok:
            return {"error": f"Failed to start: {out[:200]}"}
        
        # Wait for healthy (up to 60s)
        for i in range(12):
            time.sleep(5)
            ip = get_ip_via_proxy(1444, timeout=10)
            if ip:
                current = {"location": new_location, "ip": ip, "last_switch": time.time()}
                print(f"[Bridge] {new_location} ready: {ip}", flush=True)
                return {"switched_to": new_location, "ip": ip, "status": "ok"}
        
        return {"error": "Container started but no IP yet", "location": new_location}

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def _json(self, d):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(d).encode())
    
    def do_GET(self):
        if self.path == "/status":
            # Refresh IP
            ip = get_ip_via_proxy(1444, timeout=8)
            if ip:
                current["ip"] = ip
            self._json({
                "location": current["location"],
                "ip": current["ip"],
                "available": list(LOCATIONS.keys()),
                "cooldown_remaining": max(0, int(SWITCH_COOLDOWN - (time.time() - current["last_switch"])))
            })
        else:
            self.send_error(404)
    
    def do_POST(self):
        if self.path == "/change_location":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b"{}"
            try:
                loc = json.loads(body).get("location")
            except:
                loc = None
            self._json(switch_location(loc))
        else:
            self.send_error(404)

if __name__ == "__main__":
    print(f"[Bridge] API on 127.0.0.1:{API_PORT}", flush=True)
    with socketserver.TCPServer(("127.0.0.1", API_PORT), Handler) as h:
        h.serve_forever()
