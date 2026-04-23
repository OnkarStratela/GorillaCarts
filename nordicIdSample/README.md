# Nordic ID Stix — tag scan sample (Windows)

This sample runs a small Python utility that connects to a Nordic ID Stix reader over USB (WinUSB or virtual COM), performs RFID inventory, and prints detected tag EPCs in the terminal.

**Author:** Stratela

## Requirements

- Windows
- Python 3 (64-bit recommended; use 64-bit Python with `native\windows\x64\NURAPI.dll`)
- Nordic ID USB drivers installed from `drivers\WinDriverInstall\` (run `NUR USB Setup.exe` or install manually as needed)

## How to run

1. Install the drivers from `drivers\WinDriverInstall\`.
2. Plug in the Stix.
3. Open a command prompt in this folder (`sample`).
4. Run:
  ```bat
   python stix_notepad_tags.py
  ```
   Or double-click `start_tags_notepad.bat`.
5. Stop with `Ctrl+C` in the terminal.

## Contents


| Item                            | Description                                         |
| ------------------------------- | --------------------------------------------------- |
| `stix_notepad_tags.py`          | Main script (uses `NURAPI.dll` via Python `ctypes`) |
| `start_tags_notepad.bat`        | Launches the script with unbuffered output          |
| `native\windows\x64\NURAPI.dll` | NurApi library for 64-bit Python                    |
| `native\windows\x86\NURAPI.dll` | NurApi library for 32-bit Python                    |
| `drivers\WinDriverInstall\`     | Windows driver package                              |


## Notes

- Python architecture must match the DLL folder (`x64` vs `x86`).
- If the reader does not connect, check Device Manager for a COM port or Nordic ID USB entries, and confirm drivers are installed.

