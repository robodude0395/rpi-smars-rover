#!/bin/bash
# SMARS Telepresence Rover - Server Installation Script
# Run this on the Raspberry Pi to install all dependencies,
# set up WiFi provisioning, and configure the rover to start on boot.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== SMARS Rover Server Installation ==="
echo ""

# Check we're running on a Raspberry Pi (optional, just a warning)
if [ ! -f /proc/device-tree/model ]; then
    echo "WARNING: This doesn't appear to be a Raspberry Pi."
    echo "Some hardware-specific packages may not work correctly."
    echo ""
fi

# Install system dependencies
echo "Installing system packages..."
sudo apt-get update
sudo apt-get install -y \
    python3-opencv \
    python3-pyaudio \
    libasound2-dev \
    v4l-utils \
    alsa-utils \
    python3-pip \
    python3-venv

echo ""
echo "Creating Python virtual environment..."
python3 -m venv "$SCRIPT_DIR/.venv" --system-site-packages
source "$SCRIPT_DIR/.venv/bin/activate"

echo ""
echo "Installing Python packages..."
pip install -r "$SCRIPT_DIR/requirements.txt"

# --- WiFi Provisioning Setup ---
echo ""
echo "Setting up WiFi provisioning..."

# Ensure NetworkManager is active
if ! systemctl is-active --quiet NetworkManager; then
    echo "WARNING: NetworkManager is not running. WiFi provisioning requires it."
    echo "Skipping WiFi provisioning setup."
else
    # Create hotspot connection profile
    sudo nmcli connection delete smars-rover-hotspot 2>/dev/null || true
    sudo nmcli connection add \
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

    # Install provisioning files
    sudo cp "$SCRIPT_DIR/wifi_provision/wifi_check.sh" /opt/wifi_check.sh
    sudo cp "$SCRIPT_DIR/wifi_provision/wifi_provision.py" /opt/wifi_provision.py
    sudo chmod +x /opt/wifi_check.sh
    sudo chmod +x /opt/wifi_provision.py
    sudo cp "$SCRIPT_DIR/wifi_provision/wifi_provision.service" /etc/systemd/system/

    sudo systemctl daemon-reload
    sudo systemctl enable wifi_provision.service

    echo "WiFi provisioning installed (SSID: SMARS-Rover on fallback)."
fi

# --- Rover Server Startup Service ---
echo ""
echo "Setting up rover server startup service..."

cat <<EOF | sudo tee /etc/systemd/system/smars-rover.service > /dev/null
[Unit]
Description=SMARS Telepresence Rover Server
After=network-online.target wifi_provision.service
Wants=network-online.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$SCRIPT_DIR
ExecStart=$SCRIPT_DIR/.venv/bin/python $SCRIPT_DIR/main.py
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable smars-rover.service

echo "Rover server service installed (starts on boot after WiFi connects)."

# --- Done ---
echo ""
echo "=== Installation Complete ==="
echo ""
echo "Services installed:"
echo "  - wifi_provision.service : Hotspot fallback when no WiFi available"
echo "  - smars-rover.service   : Rover server (main.py) starts on boot"
echo ""
echo "Useful commands:"
echo "  sudo systemctl status smars-rover        # Check rover server status"
echo "  sudo journalctl -u smars-rover -f        # View rover logs"
echo "  sudo systemctl restart smars-rover       # Restart rover server"
echo ""
echo "Make sure SPI is enabled via raspi-config before rebooting."
