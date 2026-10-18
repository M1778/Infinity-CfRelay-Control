#!/usr/bin/env python3
"""
NordVPN Auto-Switch Watcher

Monitors 9router logs for 403/FreeTierError on the nordvpn-bridge pool.
When detected, automatically triggers a location switch via the bridge API.

Run: nohup python3 auto_switch_watcher.py > /tmp/auto-switch.log 2>&1 &
"""
import subprocess
import time
import urllib.request
import json
import re

BRIDGE_API = "http://127.0.0.1:1442"
CHECK_INTERVAL = 30  # Check logs every 30s
COOLDOWN_AFTER_SWITCH = 120  # Wait 2 min after auto-switch before watching again

# Patterns indicating the NordVPN IP is blocked
BLOCK_PATTERNS = [
    r"FreeTierError",
    r"abusive traffic",
    r"403.*nordvpn-bridge",
    r"nordvpn-bridge.*403",
]

last_switch_time = 0
last_log_position = None

def get_9router_logs(since_seconds=60):
    """Get recent 9router logs."""
    try:
        r = subprocess.run(
            ["docker", "logs", "--since", f"{since_seconds}s", "9router"],
            capture_output=True, text=True, timeout=15
        )
        return r.stdout + r.stderr
    except Exception as e:
        print(f"[Watcher] Log fetch failed: {e}", flush=True)
        return ""

def is_nordvpn_blocked(logs):
    """Check if logs show nordvpn-bridge pool getting blocked."""
    # Look for 403 errors mentioning the nordvpn pool or FreeTierError
    # after a nordvpn-bridge proxy attempt
    lines = logs.split("\n")
    for i, line in enumerate(lines):
        # Check if this is a nordvpn-bridge proxy attempt
        if "nordvpn-bridge" in line.lower() or "1444" in line:
            # Look at next few lines for 403
            context = "\n".join(lines[i:i+5])
            for pattern in BLOCK_PATTERNS:
                if re.search(pattern, context, re.IGNORECASE):
                    return True, line[:100]
    return False, None

def trigger_switch():
    """Trigger a location switch via bridge API."""
    global last_switch_time
    try:
        req = urllib.request.Request(
            f"{BRIDGE_API}/change_location",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=150) as r:
            result = json.load(r)
            last_switch_time = time.time()
            print(f"[Watcher] Switch triggered: {result}", flush=True)
            return result
    except Exception as e:
        print(f"[Watcher] Switch failed: {e}", flush=True)
        return {"error": str(e)}

def main():
    print("[Watcher] NordVPN auto-switch watcher started", flush=True)
    print(f"[Watcher] Checking every {CHECK_INTERVAL}s for blocks", flush=True)
    
    while True:
        try:
            # Skip if we recently switched
            if time.time() - last_switch_time < COOLDOWN_AFTER_SWITCH:
                time.sleep(CHECK_INTERVAL)
                continue
            
            logs = get_9router_logs(CHECK_INTERVAL + 10)
            blocked, evidence = is_nordvpn_blocked(logs)
            
            if blocked:
                print(f"[Watcher] Block detected! Evidence: {evidence}", flush=True)
                print("[Watcher] Triggering auto-switch...", flush=True)
                trigger_switch()
            # else: print(f"[Watcher] OK - no blocks", flush=True)
            
        except Exception as e:
            print(f"[Watcher] Error: {e}", flush=True)
        
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
