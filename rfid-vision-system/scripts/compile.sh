#!/bin/bash

echo "Compiling RFID reader IPC client..."

# Check if we're in the right directory
if [ ! -f "src/rfid_reader_ipc.c" ]; then
    echo "Error: Run this script from the rfid-vision-system root directory"
    exit 1
fi

# Check for required headers
if [ ! -f "src/CAENRFIDLib_Light.h" ] || [ ! -f "src/host.h" ]; then
    echo "Error: CAEN library headers not found in src/"
    echo "Please copy CAENRFIDLib_Light.h and host.h to src/ directory"
    echo "Run: ./install_caen.sh for help"
    exit 1
fi

# Check for CAEN library
if ! ldconfig -p | grep -q "libCAENRFIDLib_Light"; then
    echo "Warning: CAEN library not found in system"
    echo "Install with: sudo cp /path/to/libCAENRFIDLib_Light.so /usr/local/lib/ && sudo ldconfig"
fi

# Compile the C program
echo "Compiling..."
gcc -Wall -O2 -pthread -o rfid_reader_ipc src/rfid_reader_ipc.c -lCAENRFIDLib_Light -lpthread -lm

if [ $? -eq 0 ]; then
    echo "Compilation successful!"
    echo "Binary created: rfid_reader_ipc"
else
    echo "Compilation failed!"
    echo "Make sure CAEN library is installed: sudo ldconfig"
    exit 1
fi

# Create required directories
mkdir -p output/matched output/unmatched logs

echo "Setup complete!"