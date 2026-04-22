# RFID-Vision Integration System

A real-time system for associating RFID tags with container images using temporal correlation. This system captures containers moving through a field of view and matches them with RFID tag detections based on timing proximity.

## Overview

The system consists of two main components:
- **Vision Processor** (Python): Detects containers using motion detection and captures high-quality images
- **RFID Reader** (C): Continuously scans for RFID tags and communicates detections via IPC

## Hardware Requirements

- **Raspberry Pi CM4**
- **CAEN R3100C RFID Reader** (USB serial connection)
- **Raspberry Pi Camera Module v3** (CSI port)

## Software Requirements

- Raspberry Pi OS
- Python 3.7+
- OpenCV (`pip3 install opencv-python`)
- Picamera2 (`sudo apt install python3-picamera2`)
- CAEN RFID Library (`libCAENRFIDLib_Light.so`)
- GCC compiler

## Installation

### 1. System Dependencies

```bash
# Update package lists
sudo apt update

# Install system packages
sudo apt install build-essential python3-pip python3-opencv python3-picamera2

# Install Python packages
pip3 install numpy
```

### 2. CAEN RFID Library Setup

```bash
# Copy the CAEN library to system directory
sudo cp /path/to/libCAENRFIDLib_Light.so /usr/local/lib/
sudo ldconfig

# Copy header files to project
cp /path/to/CAENRFIDLib_Light.h src/
cp /path/to/host.h src/
```

### 3. Compile the System

```bash
# Option 1: Using Makefile
make

# Option 2: Using compile script
chmod +x scripts/compile.sh
./scripts/compile.sh
```

## Configuration

Edit `config/config.json` to adjust system parameters:

- **Camera settings**: Resolution, FPS
- **Detection parameters**: Motion threshold, container size filters
- **Association buffers**: Timing windows for RFID-container matching
- **Confidence thresholds**: Minimum confidence for high-quality matches

## Usage

### Quick Start

```bash
# Start the complete system
./scripts/run_system.sh
```

### Manual Operation

```bash
# Start components individually
python3 src/vision_processor.py  # Must start first (creates IPC socket)
./rfid_reader_ipc                # Connects to vision processor
python3 scripts/test_ipc.py      # Test IPC communication
```

## Output Structure

```
output/
├── matched/          # High confidence matches (≥60%)
│   └── {TAG_ID}/
│       ├── frame_01_id{N}_score{S}.jpg
│       ├── frame_02_id{N}_score{S}.jpg
│       └── metadata.json
└── unmatched/        # Low confidence or no match
    ├── {TAG_ID}_low_conf/
    └── no_tag_{TIMESTAMP}/
```

### Metadata Format

Each folder contains `metadata.json`:

```json
{
  "tag_id": "E20000172211010118905449",
  "confidence": 0.85,
  "entry_time": 1234567890.123,
  "exit_time": 1234567892.456,
  "transit_duration": 2.333,
  "entry_offset": 0.5,
  "exit_offset": 0.3,
  "frame_count": 45,
  "best_frames": [
    {
      "filename": "frame_01_id123_score450.jpg",
      "frame_id": 123,
      "focus_score": 450.2
    }
  ]
}
```

## How It Works

### Association Algorithm

The system uses temporal correlation with buffered windows:

1. **RFID events** are buffered for 30 seconds
2. **Container detection** uses motion analysis with Kalman filtering
3. **Matching** occurs within ±2 second windows around container entry/exit
4. **Confidence scoring** is based on timing proximity
5. **Results** are saved to appropriate folders based on confidence level

### Process Management

The system handles:
- Graceful shutdown (Ctrl+C)
- Automatic reconnection on socket failure
- Old event cleanup (30s buffer)
- Multiple simultaneous containers

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Socket connection failed | Ensure Python vision processor starts before C RFID reader |
| RFID not detected | Check `/dev/ttyACM0` permissions and USB connection |
| Camera not found | Verify CSI connection and enable camera in `raspi-config` |
| Low confidence matches | Adjust buffer windows in `config.json` |

## Logs

System logs are stored in the `logs/` directory:
- `vision_YYYYMMDD_HHMMSS.log` - Vision processor logs
- `rfid_YYYYMMDD_HHMMSS.log` - RFID reader logs

## Testing

Test the IPC communication between components:

```bash
python3 scripts/test_ipc.py
```

This will verify that the vision processor and RFID reader can communicate properly.
