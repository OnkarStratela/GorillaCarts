# Simplified RFID Reader System

This is a simplified version that only reads RFID tags and displays them in GREEN color on the command line.

## Files Included:

1. **compile.sh** - Compiles the RFID reader against CAEN libraries
2. **rfid_reader.c** - Simple RFID reader that displays detected tags in green
3. **run_system.sh** - Checks setup and runs the RFID reader
4. **SRC/** - Folder containing CAEN library files (keep this unchanged)

## What Was Removed:

- All Python vision processing code
- File writing/reading functionality  
- Configuration files
- Image capture and processing
- Multi-container detection
- Web interface components

## How to Use:

1. Make sure the SRC folder with CAEN libraries is present
2. Connect your CAEN RFID reader to USB
3. Run the system:
   ```bash
   chmod +x run_system.sh
   ./run_system.sh
   ```

## What It Does:

- Connects to CAEN RFID reader on /dev/ttyACM0 (or /dev/ttyUSB0)
- Continuously scans for RFID tags
- When a new tag is detected, displays it in GREEN color
- Shows timestamp for each detection
- Remembers seen tags (won't repeat the same tag)
- Press Ctrl+C to stop

## Output Example:

```
[RFID] TAG DETECTED: E20000172211010418905449 [2024-01-15 14:32:45]
```

The tag ID will appear in GREEN color on the terminal.

## Troubleshooting:

If the reader doesn't connect:
- Check USB connection
- Try: `sudo chmod 666 /dev/ttyACM0`
- Or add user to dialout group: `sudo usermod -a -G dialout $USER`
- Then logout and login again