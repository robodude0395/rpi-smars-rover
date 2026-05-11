#!/usr/bin/env python3
"""SMARS Rover - WiFi Provisioning Captive Portal.

Serves a simple web page on the hotspot that lets users select a WiFi network
and enter credentials. Once connected, the hotspot is torn down and this
script exits.
"""

import http.server
import json
import subprocess
import threading
import time
import urllib.parse

HOST = "10.42.0.1"
PORT = 80
HOTSPOT_CON = "smars-rover-hotspot"


def scan_networks():
    """Scan for available WiFi networks using nmcli."""
    try:
        # Rescan
        subprocess.run(["nmcli", "device", "wifi", "rescan"], capture_output=True, timeout=10)
        time.sleep(2)
        # List networks
        result = subprocess.run(
            ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list"],
            capture_output=True, text=True, timeout=10
        )
        networks = []
        seen = set()
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split(":")
            if len(parts) >= 3:
                ssid = parts[0].strip()
                signal = parts[1].strip()
                security = parts[2].strip()
                if ssid and ssid not in seen and ssid != "SMARS-Rover":
                    seen.add(ssid)
                    networks.append({
                        "ssid": ssid,
                        "signal": signal,
                        "security": security
                    })
        # Sort by signal strength descending
        networks.sort(key=lambda n: int(n["signal"]) if n["signal"].isdigit() else 0, reverse=True)
        return networks
    except Exception as e:
        print(f"[provision] Scan error: {e}")
        return []


def connect_to_network(ssid, password):
    """Attempt to connect to a WiFi network."""
    try:
        # Bring down the hotspot and release wlan0
        subprocess.run(["nmcli", "connection", "down", HOTSPOT_CON],
                       capture_output=True, timeout=10)
        time.sleep(3)

        # Try to connect
        cmd = ["nmcli", "device", "wifi", "connect", ssid]
        if password:
            cmd += ["password", password]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            # Verify the connection is actually up
            time.sleep(3)
            verify = subprocess.run(
                ["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show", "--active"],
                capture_output=True, text=True, timeout=10
            )
            if ssid in verify.stdout:
                print(f"[provision] Connected to '{ssid}' successfully!")
                return True, "Connected successfully!"
            else:
                print(f"[provision] Connection to '{ssid}' did not persist.")
                subprocess.run(["nmcli", "connection", "up", HOTSPOT_CON],
                               capture_output=True, timeout=10)
                return False, "Connection dropped immediately after connecting"
        else:
            error_msg = result.stderr.strip() or result.stdout.strip() or "Connection failed"
            print(f"[provision] Failed to connect to '{ssid}': {error_msg}")
            # Re-enable hotspot since connection failed
            subprocess.run(["nmcli", "connection", "up", HOTSPOT_CON],
                           capture_output=True, timeout=10)
            return False, error_msg
    except Exception as e:
        print(f"[provision] Connection error: {e}")
        subprocess.run(["nmcli", "connection", "up", HOTSPOT_CON],
                       capture_output=True, timeout=10)
        return False, str(e)


HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SMARS Rover - WiFi Setup</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #1a1a2e;
            color: #eee;
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 400px; margin: 0 auto; }
        h1 {
            text-align: center;
            margin-bottom: 8px;
            font-size: 1.4em;
        }
        .subtitle {
            text-align: center;
            color: #888;
            margin-bottom: 24px;
            font-size: 0.9em;
        }
        .network-list { list-style: none; }
        .network-item {
            background: #16213e;
            border: 1px solid #0f3460;
            border-radius: 8px;
            padding: 12px 16px;
            margin-bottom: 8px;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: background 0.2s;
        }
        .network-item:hover { background: #1a2a4a; }
        .network-item.selected { border-color: #4CAF50; background: #1a3a2a; }
        .ssid-name { font-weight: 500; }
        .signal-info { color: #888; font-size: 0.85em; }
        .password-section {
            margin-top: 16px;
            display: none;
        }
        .password-section.visible { display: block; }
        label { display: block; margin-bottom: 6px; font-size: 0.9em; color: #aaa; }
        input[type="password"], input[type="text"] {
            width: 100%;
            padding: 12px;
            border: 1px solid #0f3460;
            border-radius: 6px;
            background: #16213e;
            color: #eee;
            font-size: 1em;
            margin-bottom: 12px;
        }
        .btn {
            width: 100%;
            padding: 14px;
            border: none;
            border-radius: 6px;
            background: #4CAF50;
            color: white;
            font-size: 1em;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
        }
        .btn:hover { background: #45a049; }
        .btn:disabled { background: #555; cursor: not-allowed; }
        .btn-scan {
            background: #0f3460;
            margin-bottom: 16px;
        }
        .btn-scan:hover { background: #1a4a7a; }
        .status {
            text-align: center;
            margin-top: 16px;
            padding: 12px;
            border-radius: 6px;
            display: none;
        }
        .status.success { display: block; background: #1a3a2a; color: #4CAF50; }
        .status.error { display: block; background: #3a1a1a; color: #f44336; }
        .status.loading { display: block; background: #1a2a3a; color: #2196F3; }
        .refresh-note { text-align: center; color: #666; font-size: 0.8em; margin-top: 12px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>SMARS Rover</h1>
        <p class="subtitle">WiFi Setup</p>

        <button class="btn btn-scan" onclick="scanNetworks()">Scan for Networks</button>

        <ul class="network-list" id="networkList">
            <li class="network-item" style="justify-content: center; color: #888;">
                Scanning for networks...
            </li>
        </ul>

        <div class="password-section" id="passwordSection">
            <label for="ssid">Network</label>
            <input type="text" id="ssid" readonly>
            <label for="password">Password</label>
            <input type="password" id="password" placeholder="Enter WiFi password">
            <button class="btn" id="connectBtn" onclick="connectToNetwork()">Connect</button>
        </div>

        <div class="status" id="status"></div>
        <p class="refresh-note">If the page doesn't load, browse to http://10.42.0.1</p>
    </div>

    <script>
        let selectedSSID = '';

        function scanNetworks() {
            document.getElementById('networkList').innerHTML =
                '<li class="network-item" style="justify-content:center;color:#888;">Scanning...</li>';
            fetch('/api/scan')
                .then(r => r.json())
                .then(data => {
                    const list = document.getElementById('networkList');
                    if (data.networks.length === 0) {
                        list.innerHTML = '<li class="network-item" style="justify-content:center;color:#888;">No networks found</li>';
                        return;
                    }
                    list.innerHTML = data.networks.map(n =>
                        `<li class="network-item" onclick="selectNetwork('${n.ssid.replace(/'/g, "\\'")}', '${n.security}')">
                            <span class="ssid-name">${n.ssid}</span>
                            <span class="signal-info">${n.signal}% ${n.security ? '&#128274;' : ''}</span>
                        </li>`
                    ).join('');
                })
                .catch(() => {
                    document.getElementById('networkList').innerHTML =
                        '<li class="network-item" style="justify-content:center;color:#f44336;">Scan failed</li>';
                });
        }

        function selectNetwork(ssid, security) {
            selectedSSID = ssid;
            document.getElementById('ssid').value = ssid;
            document.getElementById('passwordSection').classList.add('visible');
            document.getElementById('password').value = '';
            document.getElementById('password').focus();
            // Highlight selected
            document.querySelectorAll('.network-item').forEach(el => el.classList.remove('selected'));
            event.currentTarget.classList.add('selected');
        }

        function connectToNetwork() {
            const password = document.getElementById('password').value;
            const status = document.getElementById('status');
            const btn = document.getElementById('connectBtn');

            btn.disabled = true;
            btn.textContent = 'Connecting...';
            status.className = 'status loading';
            status.textContent = 'Connecting to ' + selectedSSID + '...';

            fetch('/api/connect', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ssid: selectedSSID, password: password})
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    status.className = 'status success';
                    status.textContent = 'Connected! The rover is now on ' + selectedSSID + '. This hotspot will shut down.';
                } else {
                    status.className = 'status error';
                    status.textContent = 'Failed: ' + data.message;
                    btn.disabled = false;
                    btn.textContent = 'Connect';
                }
            })
            .catch(() => {
                status.className = 'status success';
                status.textContent = 'Connection initiated. If this page stops loading, the rover connected successfully!';
            });
        }

        // Auto-scan on load
        scanNetworks();
    </script>
</body>
</html>
"""


class ProvisionHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for the WiFi provisioning portal."""

    def log_message(self, format, *args):
        print(f"[provision] {args[0]}")

    def do_GET(self):
        if self.path == "/api/scan":
            networks = scan_networks()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"networks": networks}).encode())
        else:
            # Serve the main page (also handles captive portal detection)
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode())

    def do_POST(self):
        if self.path == "/api/connect":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)

            ssid = data.get("ssid", "")
            password = data.get("password", "")

            success, message = connect_to_network(ssid, password)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": success, "message": message}).encode())

            if success:
                # Give time for response to be sent, then exit
                threading.Timer(2.0, shutdown_server).start()
        else:
            self.send_response(404)
            self.end_headers()


server = None


def shutdown_server():
    """Shut down the HTTP server after successful connection."""
    global server
    print("[provision] Shutting down provisioning portal...")
    if server:
        server.shutdown()


def main():
    global server
    print(f"[provision] Starting captive portal on {HOST}:{PORT}")
    server = http.server.HTTPServer((HOST, PORT), ProvisionHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    print("[provision] Portal stopped.")


if __name__ == "__main__":
    main()
