#!/bin/bash
# SMARS Rover - WiFi connectivity check and hotspot fallback
# Called by the systemd service on boot.

HOTSPOT_CON="smars-rover-hotspot"
WAIT_SECONDS=15
CHECK_INTERVAL=3

echo "[wifi_check] Waiting ${WAIT_SECONDS}s for WiFi to connect..."
sleep "$WAIT_SECONDS"

# Check if we have an active WiFi connection (that isn't our hotspot)
ACTIVE_WIFI=$(nmcli -t -f NAME,TYPE,DEVICE connection show --active | grep wifi | grep -v "$HOTSPOT_CON" | head -1)

if [ -n "$ACTIVE_WIFI" ]; then
    echo "[wifi_check] Already connected to WiFi: $ACTIVE_WIFI"
    echo "[wifi_check] No hotspot needed."
    exit 0
fi

echo "[wifi_check] No WiFi connection found. Starting hotspot..."
nmcli connection up "$HOTSPOT_CON"

if [ $? -eq 0 ]; then
    echo "[wifi_check] Hotspot active. Starting provisioning portal..."
    python3 /opt/wifi_provision.py
else
    echo "[wifi_check] ERROR: Failed to start hotspot."
    exit 1
fi
