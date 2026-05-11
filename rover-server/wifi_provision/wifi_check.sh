#!/bin/bash
# SMARS Rover - WiFi connectivity check and hotspot fallback
# Called by the systemd service on boot.

HOTSPOT_CON="smars-rover-hotspot"
MAX_WAIT=45
POLL_INTERVAL=5

echo "[wifi_check] Waiting up to ${MAX_WAIT}s for WiFi to connect..."

# Wait for NetworkManager to be fully up
sleep 5
nmcli general status > /dev/null 2>&1

# Poll for an active WiFi connection (not our hotspot)
ELAPSED=0
while [ $ELAPSED -lt $MAX_WAIT ]; do
    ACTIVE_WIFI=$(nmcli -t -f NAME,TYPE connection show --active | grep "wifi" | grep -v "$HOTSPOT_CON")
    if [ -n "$ACTIVE_WIFI" ]; then
        echo "[wifi_check] Connected to WiFi: $ACTIVE_WIFI"
        echo "[wifi_check] No hotspot needed. Exiting."
        exit 0
    fi
    sleep $POLL_INTERVAL
    ELAPSED=$((ELAPSED + POLL_INTERVAL))
    echo "[wifi_check] Still waiting... (${ELAPSED}s/${MAX_WAIT}s)"
done

echo "[wifi_check] No WiFi connection after ${MAX_WAIT}s. Starting hotspot..."

# Make sure nothing else is using wlan0 before we take it
nmcli device disconnect wlan0 2>/dev/null
sleep 1

nmcli connection up "$HOTSPOT_CON"

if [ $? -eq 0 ]; then
    echo "[wifi_check] Hotspot active (SSID: SMARS-Rover). Starting provisioning portal..."
    python3 /opt/wifi_provision.py
    # Portal exited — means user connected to a network. Stay down.
    echo "[wifi_check] Provisioning complete. Exiting."
    exit 0
else
    echo "[wifi_check] ERROR: Failed to start hotspot."
    exit 1
fi
