#!/bin/bash
# SMARS Telepresence Rover - Server Installation Script
# Run this on the Raspberry Pi to install all dependencies.

set -e

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
python3 -m venv .venv --system-site-packages
source .venv/bin/activate

echo ""
echo "Installing Python packages..."
pip install -r requirements.txt

echo ""
echo "=== Installation Complete ==="
echo ""
echo "To run the server:"
echo "  source .venv/bin/activate"
echo "  python main.py"
echo ""
echo "Make sure SPI is enabled via raspi-config before starting."
