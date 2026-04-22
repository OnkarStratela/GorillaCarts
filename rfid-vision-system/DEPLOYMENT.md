# Raspberry Pi Deployment Guide

This guide will help you deploy the RFID-Vision system on your Raspberry Pi.

## Quick Start

1. **Copy the project to your Pi:**
   ```bash
   scp -r rfid-vision-system pi@your-pi-ip:/home/pi/
   ```

2. **SSH into your Pi:**
   ```bash
   ssh pi@your-pi-ip
   cd rfid-vision-system
   ```

3. **Run the setup script:**
   ```bash
   chmod +x setup.sh
   ./setup.sh
   ```

4. **Install CAEN library:**
   ```bash
   ./install_caen.sh
   # Follow the instructions to copy the required files
   ```

5. **Compile and run:**
   ```bash
   make
   ./scripts/run_system.sh
   ```

## Step-by-Step Installation

### 1. System Setup
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y build-essential python3-pip python3-opencv python3-picamera2

# Install Python packages
pip3 install -r requirements.txt
```

### 2. CAEN RFID Library Setup

You need to obtain the CAEN RFID library files from CAEN:
- `libCAENRFIDLib_Light.so` (shared library)
- `CAENRFIDLib_Light.h` (header file)
- `host.h` (header file)

```bash
# Install the shared library
sudo cp /path/to/libCAENRFIDLib_Light.so /usr/local/lib/
sudo ldconfig

# Copy header files to project
cp /path/to/CAENRFIDLib_Light.h src/
cp /path/to/host.h src/
```

### 3. Hardware Setup

**Camera:**
```bash
# Enable camera interface
sudo raspi-config
# Go to: Interface Options -> Camera -> Enable
```

**RFID Reader:**
- Connect CAEN R3100C to USB port
- Check device appears: `ls /dev/ttyACM*`
- Set permissions: `sudo chmod 666 /dev/ttyACM0`

### 4. Compile and Test

```bash
# Check system requirements
make check

# Compile the system
make

# Test IPC communication
make test

# Start the system
make run
```

## Configuration

Edit `config/config.json` to adjust:
- Camera settings (resolution, FPS)
- Detection parameters
- RFID association timing
- Output preferences

## Troubleshooting

### Common Issues

1. **Camera not detected:**
   ```bash
   # Check camera is enabled
   sudo raspi-config
   # Test camera
   libcamera-hello --list-cameras
   ```

2. **RFID reader not found:**
   ```bash
   # Check USB device
   lsusb
   # Check serial device
   ls /dev/ttyACM*
   # Set permissions
   sudo chmod 666 /dev/ttyACM0
   ```

3. **Compilation fails:**
   ```bash
   # Check CAEN library is installed
   ldconfig -p | grep CAEN
   # Check headers are present
   ls src/CAENRFIDLib_Light.h src/host.h
   ```

4. **Socket connection fails:**
   - Ensure vision processor starts first
   - Check logs: `tail logs/vision_*.log`

### Log Files

Monitor system logs:
```bash
# Vision processor logs
tail -f logs/vision_*.log

# RFID reader logs
tail -f logs/rfid_*.log

# System output
tail -f logs/system.log
```

## System Service (Optional)

To run as a system service:

1. Create service file:
```bash
sudo nano /etc/systemd/system/rfid-vision.service
```

2. Add service configuration:
```ini
[Unit]
Description=RFID-Vision Integration System
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/rfid-vision-system
ExecStart=/home/pi/rfid-vision-system/scripts/run_system.sh
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

3. Enable and start service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable rfid-vision.service
sudo systemctl start rfid-vision.service
```

## Output

The system will create:
- `output/matched/` - High confidence RFID-container matches
- `output/unmatched/` - Low confidence or unmatched detections
- `logs/` - System and component logs

Each match includes:
- Best quality images of the container
- Metadata with timing and confidence information
- JSON files with detailed analysis results
