# Quick Start Guide

## For Raspberry Pi Deployment

### 1. Copy to Pi
```bash
scp -r rfid-vision-system pi@your-pi-ip:/home/pi/
ssh pi@your-pi-ip
cd rfid-vision-system
```

### 2. Setup System
```bash
chmod +x setup.sh
./setup.sh
```

### 3. Install CAEN Library
```bash
./install_caen.sh
# Copy the required CAEN files as instructed
```

### 4. Run System
```bash
make check    # Check requirements
make          # Compile
make run      # Start system
```

## Required CAEN Files

You need these files from CAEN:
- `libCAENRFIDLib_Light.so` → Copy to `/usr/local/lib/`
- `CAENRFIDLib_Light.h` → Copy to `src/`
- `host.h` → Copy to `src/`

## Hardware Connections

- **Camera**: Connect Pi Camera Module v3 to CSI port
- **RFID Reader**: Connect CAEN R3100C to USB port
- **Enable camera**: `sudo raspi-config` → Interface Options → Camera → Enable

## Output

- **Matched containers**: `output/matched/{TAG_ID}/`
- **Unmatched containers**: `output/unmatched/`
- **System logs**: `logs/`

## Commands

- `make help` - Show all available commands
- `make check` - Check system requirements
- `make test` - Test IPC communication
- `make clean` - Clean compiled files and output

## Troubleshooting

- Check logs: `tail logs/vision_*.log` and `tail logs/rfid_*.log`
- Verify hardware: `ls /dev/ttyACM*` and `libcamera-hello --list-cameras`
- Test components: `python3 scripts/test_ipc.py`
