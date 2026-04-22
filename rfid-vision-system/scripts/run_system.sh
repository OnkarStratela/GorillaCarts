#!/bin/bash

# Cleanup function
cleanup() {
    echo ""
    echo "Shutting down..."
    if [ ! -z "$PYTHON_PID" ]; then
        kill $PYTHON_PID 2>/dev/null
        echo "Vision processor stopped"
    fi
    sleep 1
    if [ ! -z "$C_PID" ]; then
        kill $C_PID 2>/dev/null
        echo "RFID reader stopped"
    fi
    rm -f /tmp/rfid_vision.sock
    echo "Cleanup complete"
    exit 0
}

trap cleanup SIGINT SIGTERM

echo "RFID-Vision System Startup"
echo "=========================="

# Check if we're in the right directory
if [ ! -f "src/vision_processor.py" ]; then
    echo "Error: Run this script from the rfid-vision-system root directory"
    exit 1
fi

# Check if Python script exists
if [ ! -f "src/vision_processor.py" ]; then
    echo "Error: vision_processor.py not found"
    exit 1
fi

# Check if compiled binary exists
if [ ! -f "rfid_reader_ipc" ]; then
    echo "RFID reader not compiled. Compiling now..."
    make
    if [ $? -ne 0 ]; then
        echo "Compilation failed! Try running: ./scripts/compile.sh"
        exit 1
    fi
fi

# Check config
if [ ! -f "config/config.json" ]; then
    echo "Error: config/config.json not found"
    exit 1
fi

# Create required directories
mkdir -p logs output/matched output/unmatched

# Start Python vision processor (must start first - it's the server)
echo "Starting vision processor..."
python3 src/vision_processor.py > logs/vision_$(date +%Y%m%d_%H%M%S).log 2>&1 &
PYTHON_PID=$!

# Wait for socket to be created
echo "Waiting for IPC socket..."
for i in {1..15}; do
    if [ -S "/tmp/rfid_vision.sock" ]; then
        echo "✓ Socket ready!"
        break
    fi
    echo -n "."
    sleep 1
done
echo ""

if [ ! -S "/tmp/rfid_vision.sock" ]; then
    echo "Error: Socket not created. Check vision processor logs:"
    echo "  tail logs/vision_*.log"
    kill $PYTHON_PID 2>/dev/null
    exit 1
fi

# Start RFID reader
echo "Starting RFID reader..."
./rfid_reader_ipc > logs/rfid_$(date +%Y%m%d_%H%M%S).log 2>&1 &
C_PID=$!

echo ""
echo "✓ System running successfully!"
echo "  Vision processor PID: $PYTHON_PID"
echo "  RFID reader PID: $C_PID"
echo ""
echo "Output will be saved in: output/"
echo "Logs are in: logs/"
echo ""
echo "Press Ctrl+C to stop the system"

# Wait for processes
wait $PYTHON_PID $C_PID