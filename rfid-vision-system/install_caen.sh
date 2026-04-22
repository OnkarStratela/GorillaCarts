#!/bin/bash

echo "CAEN RFID Library Installation Helper"
echo "====================================="

# Check if we're in the right directory
if [ ! -f "src/rfid_reader_ipc.c" ]; then
    echo "Error: Run this script from the rfid-vision-system root directory"
    exit 1
fi

echo "This script helps you install the CAEN RFID library."
echo ""
echo "You need to provide the following files:"
echo "1. libCAENRFIDLib_Light.so (shared library)"
echo "2. CAENRFIDLib_Light.h (header file)"
echo "3. host.h (header file)"
echo ""

# Check for existing files
if [ -f "src/CAENRFIDLib_Light.h" ] && [ -f "src/host.h" ]; then
    echo "Header files already found in src/ directory"
else
    echo "Header files not found. Please copy them to src/ directory:"
    echo "  cp /path/to/CAENRFIDLib_Light.h src/"
    echo "  cp /path/to/host.h src/"
fi

# Check for library in system
if ldconfig -p | grep -q "libCAENRFIDLib_Light"; then
    echo "CAEN library already installed in system"
else
    echo "CAEN library not found in system. To install:"
    echo "  sudo cp /path/to/libCAENRFIDLib_Light.so /usr/local/lib/"
    echo "  sudo ldconfig"
fi

echo ""
echo "After copying the files, run:"
echo "  make"
echo "  ./scripts/run_system.sh"
