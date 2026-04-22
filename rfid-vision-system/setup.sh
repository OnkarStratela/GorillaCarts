#!/bin/bash

echo "RFID-Vision System Setup Script"
echo "================================"

# Check if running on Raspberry Pi
if ! grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
    echo "Warning: This script is designed for Raspberry Pi OS"
fi

# Update package lists
echo "Updating package lists..."
sudo apt update

# Install system dependencies
echo "Installing system dependencies..."
sudo apt install -y build-essential python3-pip python3-opencv python3-picamera2

# Install Python dependencies
echo "Installing Python dependencies..."
pip3 install -r requirements.txt

# Create required directories
echo "Creating required directories..."
mkdir -p output/matched output/unmatched logs

# Set permissions
echo "Setting permissions..."
chmod +x scripts/*.sh
chmod +x setup.sh

# Check for CAEN library headers
echo "Checking for CAEN library headers..."
if [ ! -f "src/CAENRFIDLib_Light.h" ] || [ ! -f "src/host.h" ]; then
    echo ""
    echo "WARNING: CAEN library headers not found!"
    echo "Please copy the following files to src/ directory:"
    echo "  - CAENRFIDLib_Light.h"
    echo "  - host.h"
    echo ""
    echo "Also ensure libCAENRFIDLib_Light.so is installed:"
    echo "  sudo cp /path/to/libCAENRFIDLib_Light.so /usr/local/lib/"
    echo "  sudo ldconfig"
    echo ""
fi

# Enable camera interface
echo "Checking camera interface..."
if command -v raspi-config >/dev/null 2>&1; then
    echo "To enable camera interface, run: sudo raspi-config"
    echo "  Go to: Interface Options -> Camera -> Enable"
fi

echo ""
echo "Setup complete!"
echo ""
echo "Next steps:"
echo "1. Copy CAEN library headers to src/ directory"
echo "2. Install CAEN library (.so file)"
echo "3. Enable camera interface if needed"
echo "4. Run: make (to compile)"
echo "5. Run: ./scripts/run_system.sh (to start system)"
