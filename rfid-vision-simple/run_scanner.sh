#!/bin/bash

# Check USB permissions
if [ -e /dev/ttyACM0 ]; then
    if [ ! -r /dev/ttyACM0 ]; then
        echo "Setting USB permissions..."
        sudo chmod 666 /dev/ttyACM0
    fi
fi

# Compile and run
chmod +x compile_scanner.sh
./compile_scanner.sh

if [ $? -eq 0 ]; then
    ./rfid_tag_scanner
fi