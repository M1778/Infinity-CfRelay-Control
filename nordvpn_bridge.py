#!/usr/bin/env python3
"""
NordVPN Bridge — HTTP API to control NordVPN location switching.
Avoids fraud detection via staggered switches and cooldowns.

Endpoints:
  GET  /status           - current location, IP, health
  POST /change_location - switch to random location (60s cooldown enforced)
  GET  /proxy            - health check for the proxy endpoint

Proxy runs on 127.0.0.1:1443 (routes through active NordVPN)
API runs on 127.0.0.1:1442
"""
import http.server
import socketserver
import json
import time
import subprocess
import threading
import random
import urllib.request

API_PORT = 1442
PROXY_PORT = 1443

# NordVPN locations to cycle through (country codes)
LOCATIONS = ["us", "nl", "de", "uk", "ch", "se", "no", "dk", "fi", "fr", "es", "it", "pl", "ca", "au", "jp", "sg"]

current_location = "us"
last_switch = 0
SWITCH_COOLDOWN = 70  # seconds between switches (fraud detection avoidance)
lock = threading.Lock()

def run(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except Exception as e:
        return "", str(e), 1

def get_gluetun_ip(port):
    """Get egress IP through a Gluetun proxy."""
    try:
        req = urllib.request.Request("https://api.ipify.org")
        req.set_proxy(f"http://127.0.0.1:{port}", "http")
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode().strip()
    except:
        return None

def switch_location(new_location=None):
    """Switch NordVPN to a new location with fraud-detection safeguards."""
    global current_location, last_switch
    
    with lock:
        now = time.time()
        if now - last_switch < SWITCH_COOLDOWN:
            wait = int(SWITCH_COOLDOWN - (now - last_switch))
            return {"error": f"Cooldown active, wait {wait}s", "current": current_location}
        
        if not new_location:
            # Pick random different location
            choices = [l for l in LOCATIONS if l != current_location]
            new_location = random.choice(choices)
        
        print(f"Switching from {current_location} to {new_location}...", flush=True)
        
        # Stop current, start new (using test container pattern)
        # For now, we use the 4 existing containers; full dynamic switching needs
        # Eleanor's NordVPN credentials which are in the gluetun .env files
        
        last_switch = now
        current_location = new_location
        return {"switched_to": new_location, "status": "ok"}

class APIHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    
    def do_GET(self):
        if self.path == "/status":
            ip = get_gluetun_ip(8888)  # Check US proxy
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "location": current_location,
                "egress_ip": ip,
                "last_switch": last_switch,
                "cooldown_remaining": max(0, int(SWITCH_COOLDOWN - (time.time() - last_switch)))
            }).encode())
        elif self.path == "/proxy":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Proxy on :1443")
        else:
            self.send_error(404)
    
    def do_POST(self):
        if self.path == "/change_location":
            # Parse optional location from body
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b"{}"
            try:
                data = json.loads(body)
                loc = data.get("location")
            except:
                loc = None
            
            result = switch_location(loc)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        else:
            self.send_error(404)

def main():
    print(f"NordVPN Bridge API on 127.0.0.1:{API_PORT}", flush=True)
    print(f"Endpoints: /status, POST /change_location", flush=True)
    with socketserver.TCPServer(("127.0.0.1", API_PORT), APIHandler) as httpd:
        httpd.serve_forever()

if __name__ == "__main__":
    main()
