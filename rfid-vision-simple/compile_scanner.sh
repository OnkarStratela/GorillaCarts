#!/bin/bash

echo "[Build] Compiling RFID Tag Scanner..."

# Check if SRC directory exists
if [ ! -d "SRC" ]; then
    echo "[Build] ERROR: SRC directory not found!"
    exit 1
fi

# Check for critical files
if [ ! -f "SRC/CAENRFIDLib_Light.c" ] || [ ! -f "SRC/host.c" ] || [ ! -f "SRC/IO_Light.c" ]; then
    echo "[Build] ERROR: Missing CAEN library files in SRC folder!"
    exit 1
fi

if [ ! -f "rfid_tag_scanner.c" ]; then
    echo "[Build] ERROR: rfid_tag_scanner.c not found!"
    exit 1
fi

gcc \
  rfid_tag_scanner.c \
  SRC/host.c SRC/CAENRFIDLib_Light.c SRC/IO_Light.c \
  -ISRC \
  -o rfid_tag_scanner \
  -lpthread -lm \
  -Wall

if [ $? -eq 0 ]; then
    echo "[Build] Success! Created rfid_tag_scanner"
    chmod +x rfid_tag_scanner
    echo ""
    echo "To run: ./rfid_tag_scanner"
else
    echo "[Build] Compilation failed!"
    exit 1
fi