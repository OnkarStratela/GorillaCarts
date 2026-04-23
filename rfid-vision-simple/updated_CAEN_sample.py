#!/usr/bin/env python3
"""
Sequential CAEN RFID scanner output for Raspberry Pi.

Prints one line per scan cycle in this format:
[]
[TAGCODE]
[TAGCODE1,TAGCODE2]
"""

import argparse
import ctypes
import os
import subprocess
import sys
import time
from ctypes import POINTER, byref
from typing import Optional


CAENRFID_STATUS_OK = 0
CAENRFID_RS232 = 0
INVENTORY_FLAG_RSSI = 0x0001
MAX_ID_LENGTH = 64
DEFAULT_PORT_CANDIDATES = ("/dev/ttyACM0", "/dev/ttyUSB0")


class RS232Params(ctypes.Structure):
    _fields_ = [
        ("com", ctypes.c_char_p),
        ("baudrate", ctypes.c_uint32),
        ("dataBits", ctypes.c_uint8),
        ("stopBits", ctypes.c_uint8),
        ("parity", ctypes.c_uint8),
        ("flowControl", ctypes.c_uint8),
    ]


class CAENRFIDInventoryParams(ctypes.Structure):
    _fields_ = [
        ("has_RSSI", ctypes.c_bool),
        ("has_framed", ctypes.c_bool),
        ("has_continuous", ctypes.c_bool),
        ("has_compact", ctypes.c_bool),
        ("has_TID", ctypes.c_bool),
        ("has_event_trigger", ctypes.c_bool),
        ("has_XPC", ctypes.c_bool),
        ("has_PC", ctypes.c_bool),
    ]


class CAENRFIDReader(ctypes.Structure):
    _fields_ = [
        ("_port_handle", ctypes.c_void_p),
        # Keep raw function pointers (as in C struct) to avoid callback wrapper issues.
        ("connect", ctypes.c_void_p),
        ("disconnect", ctypes.c_void_p),
        ("tx", ctypes.c_void_p),
        ("rx", ctypes.c_void_p),
        ("clear_rx_data", ctypes.c_void_p),
        ("enable_irqs", ctypes.c_void_p),
        ("disable_irqs", ctypes.c_void_p),
        ("_inventory_params", CAENRFIDInventoryParams),
    ]


class CAENRFIDTag(ctypes.Structure):
    _fields_ = [
        ("ID", ctypes.c_uint8 * MAX_ID_LENGTH),
        ("Length", ctypes.c_uint16),
        ("LogicalSource", ctypes.c_char * 30),
        ("ReadPoint", ctypes.c_char * 5),
        ("TimeStamp", ctypes.c_uint32 * 2),
        ("Type", ctypes.c_int),
        ("RSSI", ctypes.c_int16),
        ("TID", ctypes.c_uint8 * 64),
        ("TIDLen", ctypes.c_uint16),
        ("XPC", ctypes.c_uint8 * 4),
        ("PC", ctypes.c_uint8 * 2),
    ]


class CAENRFIDTagList(ctypes.Structure):
    pass


CAENRFIDTagList._fields_ = [
    ("Tag", CAENRFIDTag),
    ("Next", POINTER(CAENRFIDTagList)),
]


def build_shared_library(base_dir: str, lib_path: str) -> None:
    src_dir = os.path.join(base_dir, "SRC")
    required = [
        os.path.join(src_dir, "host.c"),
        os.path.join(src_dir, "CAENRFIDLib_Light.c"),
        os.path.join(src_dir, "IO_Light.c"),
    ]
    missing = [path for path in required if not os.path.exists(path)]
    if missing:
        raise RuntimeError(f"Missing required CAEN sources: {', '.join(missing)}")

    cmd = [
        "gcc",
        "-shared",
        "-fPIC",
        "-O2",
        "-Wall",
        "-Wextra",
        "-I",
        src_dir,
        required[0],
        required[1],
        required[2],
        "-o",
        lib_path,
        "-lpthread",
        "-lm",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        details = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"Failed to build shared library with gcc: {details}")


def load_caen_library(base_dir: str):
    lib_path = os.path.join(base_dir, "libcaenrfid_light.so")
    if not os.path.exists(lib_path):
        print(f"[INFO] Building {lib_path} from SRC files...", flush=True)
        build_shared_library(base_dir, lib_path)

    lib = ctypes.CDLL(lib_path)
    libc = ctypes.CDLL("libc.so.6")
    libc.free.argtypes = [ctypes.c_void_p]
    libc.free.restype = None

    lib.CAENRFID_Connect.argtypes = [POINTER(CAENRFIDReader), ctypes.c_int, ctypes.c_void_p]
    lib.CAENRFID_Connect.restype = ctypes.c_int
    lib.CAENRFID_Disconnect.argtypes = [POINTER(CAENRFIDReader)]
    lib.CAENRFID_Disconnect.restype = ctypes.c_int
    lib.CAENRFID_GetReaderInfo.argtypes = [POINTER(CAENRFIDReader), ctypes.c_char_p, ctypes.c_char_p]
    lib.CAENRFID_GetReaderInfo.restype = ctypes.c_int
    lib.CAENRFID_SetPower.argtypes = [POINTER(CAENRFIDReader), ctypes.c_uint32]
    lib.CAENRFID_SetPower.restype = ctypes.c_int
    lib.CAENRFID_InventoryTag.argtypes = [
        POINTER(CAENRFIDReader),
        ctypes.c_char_p,
        ctypes.c_uint16,
        ctypes.c_uint16,
        ctypes.c_uint16,
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.c_uint16,
        ctypes.c_uint16,
        POINTER(POINTER(CAENRFIDTagList)),
        POINTER(ctypes.c_uint16),
    ]
    lib.CAENRFID_InventoryTag.restype = ctypes.c_int

    return lib, libc


def make_reader(lib) -> CAENRFIDReader:
    connect_ptr = ctypes.cast(lib._connect, ctypes.c_void_p).value
    disconnect_ptr = ctypes.cast(lib._disconnect, ctypes.c_void_p).value
    tx_ptr = ctypes.cast(lib._tx, ctypes.c_void_p).value
    rx_ptr = ctypes.cast(lib._rx, ctypes.c_void_p).value
    clear_rx_ptr = ctypes.cast(lib._clear_rx_data, ctypes.c_void_p).value
    enable_irqs_ptr = ctypes.cast(lib._enable_irqs, ctypes.c_void_p).value
    disable_irqs_ptr = ctypes.cast(lib._disable_irqs, ctypes.c_void_p).value

    return CAENRFIDReader(
        None,
        connect_ptr,
        disconnect_ptr,
        tx_ptr,
        rx_ptr,
        clear_rx_ptr,
        enable_irqs_ptr,
        disable_irqs_ptr,
        CAENRFIDInventoryParams(),
    )


def format_tags(tags: list[str]) -> str:
    if not tags:
        return "[]"
    return "[" + ",".join(tags) + "]"


def free_tag_list(head: POINTER(CAENRFIDTagList), libc) -> None:
    node = head
    while node:
        current = node
        node = node.contents.Next
        libc.free(ctypes.cast(current, ctypes.c_void_p))


def collect_tags_for_source(lib, libc, reader: CAENRFIDReader, source_name: str) -> list[str]:
    tags_head = POINTER(CAENRFIDTagList)()
    count = ctypes.c_uint16(0)
    err = lib.CAENRFID_InventoryTag(
        byref(reader),
        source_name.encode("ascii"),
        0,
        0,
        0,
        None,
        0,
        INVENTORY_FLAG_RSSI,
        byref(tags_head),
        byref(count),
    )
    if err != CAENRFID_STATUS_OK or count.value == 0 or not tags_head:
        return []

    tags: list[str] = []
    try:
        node = tags_head
        while node:
            tag = node.contents.Tag
            epc = bytes(tag.ID[: tag.Length]).hex().upper()
            if epc:
                tags.append(epc)
            node = node.contents.Next
    finally:
        free_tag_list(tags_head, libc)
    return tags


def connect_with_port(lib, reader: CAENRFIDReader, port: str, baud: int) -> int:
    params = RS232Params(
        port.encode("ascii"),
        baud,
        8,
        1,
        0,
        0,
    )
    return lib.CAENRFID_Connect(byref(reader), CAENRFID_RS232, byref(params))


def connect_reader(lib, reader: CAENRFIDReader, port_arg: Optional[str], baud: int) -> str:
    if port_arg:
        ports_to_try = [port_arg]
    else:
        ports_to_try = [p for p in DEFAULT_PORT_CANDIDATES if os.path.exists(p)]
        if not ports_to_try:
            ports_to_try = list(DEFAULT_PORT_CANDIDATES)

    last_error = None
    for port in ports_to_try:
        err = connect_with_port(lib, reader, port, baud)
        if err == CAENRFID_STATUS_OK:
            return port
        last_error = err
        lib.CAENRFID_Disconnect(byref(reader))

    raise RuntimeError(
        f"Failed to connect on ports {ports_to_try}. Last CAEN error code: {last_error}. "
        "Check USB cable, device path, and serial permissions."
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sequential CAEN RFID scanner output.")
    parser.add_argument("--port", default=None, help="Serial port (e.g. /dev/ttyACM0).")
    parser.add_argument("--baud", type=int, default=921600, help="Reader baudrate.")
    parser.add_argument("--power", type=int, default=316, help="RF power in mW.")
    parser.add_argument("--interval", type=float, default=0.3, help="Scan interval seconds.")
    parser.add_argument(
        "--sources",
        nargs="+",
        default=["Source_0", "Source_1"],
        help="Logical source names to scan each cycle.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_dir = os.path.dirname(os.path.abspath(__file__))

    try:
        lib, libc = load_caen_library(base_dir)
        reader = make_reader(lib)
        connected_port = connect_reader(lib, reader, args.port, args.baud)

        model = ctypes.create_string_buffer(64)
        serial = ctypes.create_string_buffer(64)
        if lib.CAENRFID_GetReaderInfo(byref(reader), model, serial) == CAENRFID_STATUS_OK:
            print(f"[INFO] Reader: {model.value.decode(errors='ignore')} SN:{serial.value.decode(errors='ignore')}")

        set_power_err = lib.CAENRFID_SetPower(byref(reader), ctypes.c_uint32(args.power))
        if set_power_err != CAENRFID_STATUS_OK:
            print(f"[WARN] Could not set power to {args.power} mW (error {set_power_err}).")

        print(
            f"[INFO] Connected on {connected_port}, baud={args.baud}, interval={args.interval}s, "
            f"sources={args.sources}"
        )
        print("[INFO] Press Ctrl+C to stop.")

        while True:
            cycle_tags: list[str] = []
            for source in args.sources:
                source_tags = collect_tags_for_source(lib, libc, reader, source)
                for tag in source_tags:
                    if tag not in cycle_tags:
                        cycle_tags.append(tag)

            print(format_tags(cycle_tags), flush=True)
            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\n[INFO] Stopped.")
        return 0
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    finally:
        try:
            if "lib" in locals() and "reader" in locals():
                lib.CAENRFID_Disconnect(byref(reader))
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
