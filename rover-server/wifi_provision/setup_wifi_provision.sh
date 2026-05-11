#!/bin/bash
# SMARS Rover - WiFi Provisioning Setup
# Run once to install the WiFi provisioning service.
# After this, the rover will automatically create a hotspot when no known WiFi is available.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== SMARS Rover WiFi Provisioning Setup ==="
echo ""

# Ensure NetworkManager is active (Trixie uses it by default)
if ! systemctl is-active --quiet NetworkManager; then
    echo "ERROR: NetworkManager is not running. This script requires NetworkManager."
    exit 1
fi

# Create the hotspot connection profile (won't autoconnect — managed by our service)
echo "Creating hotspot connection profile..."
nmcli connection delete smars-rover-hotspot 2>/dev/null || true
nmcli connection add \
    type wifi \
    ifname wlan0 \
    con-name smars-rover-hotspot \
    ssid "SMARS-Rover" \
    mode ap \
    wifi.band bg \
    wifi.channel 6 \
    ipv4.method shared \
    ipv4.addresses 10.42.0.1/24 \
    connection.autoconnect no

echo "Hotspot profile created (SSID: SMARS-Rover)"

# Install the provisioning service files
echo "Installing provisioning service..."
sudo cp "$SCRIPT_DIR/wifi_provision.service" /etc/systemd/system/
sudo cp "$SCRIPT_DIR/wifi_provision.py" /opt/wifi_provision.py
sudo cp "$SCRIPT_DIR/wifi_check.sh" /opt/wifi_check.sh
sudo chmod +x /opt/wifi_check.sh
sudo chmod +x /opt/wifi_provision.py

# Enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable wifi_provision.service
sudo systemctl start wifi_provision.service

echo ""
echo "=== Setup Complete ==="
echo ""
echo "How it works:"
echo "  1. On boot, the service waits 15s for WiFi to auto-connect"
echo "  2. If no connection is found, it starts a hotspot (SSID: SMARS-Rover)"
echo "  3. Connect to the hotspot from your phone/laptop"
echo "  4. Browse to http://10.42.0.1 to pick a WiFi network"
echo "  5. The rover connects and drops the hotspot"
echo ""
echo "The rover remembers networks — next time it's in range, it auto-connects."
