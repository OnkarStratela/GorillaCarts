import ctypes
import os
import struct
import subprocess
import sys
import time
from ctypes import byref
from ctypes import wintypes


NUR_NO_ERROR = 0
NUR_ERROR_NO_TAG = 0x20
NUR_MAX_EPC_LENGTH = 62
NUR_DEFAULT_BAUDRATE = 115200
SCAN_INTERVAL_SECONDS = 0.3

USB_ENUM_CB = ctypes.WINFUNCTYPE(
    ctypes.c_int,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    ctypes.c_void_p,
)


class NUR_INVENTORY_RESPONSE(ctypes.Structure):
    _fields_ = [
        ("numTagsFound", ctypes.c_int),
        ("numTagsMem", ctypes.c_int),
        ("roundsDone", ctypes.c_int),
        ("collisions", ctypes.c_int),
        ("Q", ctypes.c_int),
    ]


class NUR_TAG_DATA(ctypes.Structure):
    _fields_ = [
        ("timestamp", ctypes.c_ushort),
        ("rssi", ctypes.c_byte),
        ("scaledRssi", ctypes.c_byte),
        ("freq", ctypes.c_uint32),
        ("pc", ctypes.c_ushort),
        ("channel", ctypes.c_ubyte),
        ("antennaId", ctypes.c_ubyte),
        ("epcLen", ctypes.c_ubyte),
        ("epc", ctypes.c_ubyte * NUR_MAX_EPC_LENGTH),
    ]


def get_arch_folder() -> str:
    return "x64" if struct.calcsize("P") == 8 else "x86"


def list_com_ports() -> list[str]:
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "[System.IO.Ports.SerialPort]::GetPortNames()",
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if result.returncode != 0:
            return []
        return [port.strip() for port in result.stdout.splitlines() if port.strip()]
    except OSError:
        return []


def try_ping(nur, h_api: int) -> bool:
    return nur.NurApiIsConnected(h_api) == NUR_NO_ERROR and nur.NurApiPing(h_api, None) == NUR_NO_ERROR


def connect_reader(nur, h_api: int) -> bool:
    """Stix may use WinUSB (auto) or a CDC virtual COM port; try both."""
    print("Connecting to reader...", flush=True)

    nur.NurApiSetUsbAutoConnect(h_api, 1)
    time.sleep(0.8)
    err = nur.NurApiConnect(h_api)
    if err == NUR_NO_ERROR and try_ping(nur, h_api):
        print("Connected: USB auto-connect.", flush=True)
        return True
    for _ in range(40):
        if try_ping(nur, h_api):
            print("Connected: USB auto-connect (after wait).", flush=True)
            return True
        time.sleep(0.25)

    usb_paths: list[tuple[str, str]] = []

    def _usb_cb(path, friendly, _arg):
        if path:
            usb_paths.append((path, friendly or ""))
        return 0

    usb_cb = USB_ENUM_CB(_usb_cb)
    nur.NurApiDisconnect(h_api)
    time.sleep(0.15)
    nur.NurUSBEnumerateDevices(usb_cb, None)
    for path, friendly in usb_paths:
        nur.NurApiDisconnect(h_api)
        time.sleep(0.05)
        err = nur.NurApiConnectUsb(h_api, path)
        if err == NUR_NO_ERROR and try_ping(nur, h_api):
            hint = f" ({friendly})" if friendly else ""
            print(f"Connected: USB path{hint}.", flush=True)
            return True

    nur.NurApiSetUsbAutoConnect(h_api, 0)
    nur.NurApiDisconnect(h_api)
    time.sleep(0.2)
    ports = list_com_ports()
    if ports:
        print(f"Trying serial ports: {', '.join(ports)}", flush=True)
    for port in ports:
        nur.NurApiDisconnect(h_api)
        time.sleep(0.05)
        dev = port if port.startswith("\\\\") else f"\\\\.\\{port}"
        err = nur.NurApiConnectSerialPortEx(h_api, dev, NUR_DEFAULT_BAUDRATE)
        if err == NUR_NO_ERROR and try_ping(nur, h_api):
            print(f"Connected: {port} @ {NUR_DEFAULT_BAUDRATE} baud (CDC serial).", flush=True)
            return True
        nur.NurApiDisconnect(h_api)

    print(
        "Could not open the reader. Install drivers from drivers\\WinDriverInstall, "
        "unplug/replug USB, and confirm a COM port appears in Device Manager.",
        flush=True,
    )
    return False


def get_dll_path() -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    arch = get_arch_folder()

    candidates = [
        os.path.join(base_dir, "native", "windows", arch, "NURAPI.dll"),
        os.path.join(base_dir, "..", "nordicIdSample", "native", "windows", arch, "NURAPI.dll"),
    ]

    for path in candidates:
        abs_path = os.path.abspath(path)
        if os.path.exists(abs_path):
            return abs_path
    return os.path.abspath(candidates[0])


def configure_api_functions(nur) -> None:
    nur.NurApiCreate.restype = ctypes.c_void_p
    nur.NurApiFree.argtypes = [ctypes.c_void_p]
    nur.NurApiFree.restype = ctypes.c_int
    nur.NurApiSetUsbAutoConnect.argtypes = [ctypes.c_void_p, ctypes.c_int]
    nur.NurApiSetUsbAutoConnect.restype = ctypes.c_int
    nur.NurApiClearTags.argtypes = [ctypes.c_void_p]
    nur.NurApiClearTags.restype = ctypes.c_int
    nur.NurApiSimpleInventory.argtypes = [ctypes.c_void_p, ctypes.POINTER(NUR_INVENTORY_RESPONSE)]
    nur.NurApiSimpleInventory.restype = ctypes.c_int
    nur.NurApiFetchTags.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    nur.NurApiFetchTags.restype = ctypes.c_int
    nur.NurApiGetTagCount.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
    nur.NurApiGetTagCount.restype = ctypes.c_int
    nur.NurApiGetTagData.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(NUR_TAG_DATA)]
    nur.NurApiGetTagData.restype = ctypes.c_int
    nur.NurApiIsConnected.argtypes = [ctypes.c_void_p]
    nur.NurApiIsConnected.restype = ctypes.c_int
    nur.NurApiPing.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    nur.NurApiPing.restype = ctypes.c_int
    nur.NurApiConnect.argtypes = [ctypes.c_void_p]
    nur.NurApiConnect.restype = ctypes.c_int
    nur.NurApiDisconnect.argtypes = [ctypes.c_void_p]
    nur.NurApiDisconnect.restype = ctypes.c_int
    nur.NurApiConnectUsb.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    nur.NurApiConnectUsb.restype = ctypes.c_int
    nur.NurApiConnectSerialPortEx.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, ctypes.c_int]
    nur.NurApiConnectSerialPortEx.restype = ctypes.c_int
    nur.NurUSBEnumerateDevices.argtypes = [USB_ENUM_CB, ctypes.c_void_p]
    nur.NurUSBEnumerateDevices.restype = ctypes.c_uint32


def scan_once(nur, h_api: int) -> list[str]:
    nur.NurApiClearTags(h_api)

    inv = NUR_INVENTORY_RESPONSE()
    err = nur.NurApiSimpleInventory(h_api, byref(inv))
    if err not in (NUR_NO_ERROR, NUR_ERROR_NO_TAG):
        return []

    if inv.numTagsMem > 0:
        nur.NurApiFetchTags(h_api, 1, None)

    count = ctypes.c_int(0)
    err = nur.NurApiGetTagCount(h_api, byref(count))
    if err != NUR_NO_ERROR or count.value <= 0:
        return []

    tags: list[str] = []
    for i in range(count.value):
        tag = NUR_TAG_DATA()
        if nur.NurApiGetTagData(h_api, i, byref(tag)) == NUR_NO_ERROR:
            epc = bytes(tag.epc[: tag.epcLen]).hex().upper()
            if epc and epc not in tags:
                tags.append(epc)
    return tags


def format_tag_list(tags: list[str]) -> str:
    if not tags:
        return "[]"
    return "[" + ",".join(tags) + "]"


def main() -> int:
    dll_path = get_dll_path()
    if not os.path.exists(dll_path):
        print(f"NURAPI.dll not found: {dll_path}")
        return 1

    os.environ["PATH"] = os.path.dirname(dll_path) + os.pathsep + os.environ.get("PATH", "")
    nur = ctypes.WinDLL(dll_path)
    configure_api_functions(nur)

    h_api = nur.NurApiCreate()
    if not h_api:
        print("NurApiCreate failed")
        return 1

    try:
        if not connect_reader(nur, h_api):
            return 1

        print("Start sequential scan output. Press Ctrl+C to stop.", flush=True)
        while True:
            tags = scan_once(nur, h_api)
            print(format_tag_list(tags), flush=True)
            time.sleep(SCAN_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("Stopped.")
        return 0
    finally:
        nur.NurApiFree(h_api)


if __name__ == "__main__":
    sys.exit(main())

