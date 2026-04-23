#!/usr/bin/env python3
"""
Stable CAEN sequential output wrapper for Raspberry Pi.

This script runs the existing CAEN C scanner and prints one line each cycle:
[]
[TAGCODE]
[TAGCODE,TAGCODE2]
"""

import argparse
import os
import queue
import re
import subprocess
import sys
import threading
import time


TAG_HEX_RE = re.compile(r"\b[A-F0-9]{8,128}\b")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sequential CAEN RFID output wrapper.")
    parser.add_argument("--interval", type=float, default=0.3, help="Output interval seconds.")
    parser.add_argument(
        "--scanner-cmd",
        default="./rfid_tag_scanner",
        help="Scanner command to run (default: ./rfid_tag_scanner).",
    )
    parser.add_argument(
        "--build-cmd",
        default="./compile_scanner.sh",
        help="Build command if scanner binary is missing.",
    )
    return parser.parse_args()


def ensure_scanner_available(scanner_cmd: str, build_cmd: str) -> None:
    scanner_bin = scanner_cmd.split()[0]
    if os.path.exists(scanner_bin):
        return

    print(f"[INFO] {scanner_bin} not found. Building with: {build_cmd}", flush=True)
    build = subprocess.run(build_cmd, shell=True)
    if build.returncode != 0 or not os.path.exists(scanner_bin):
        raise RuntimeError(
            f"Could not build scanner binary '{scanner_bin}'. "
            "Check compile_scanner.sh and CAEN SRC files."
        )


def format_tags(tags: list[str]) -> str:
    if not tags:
        return "[]"
    return "[" + ",".join(tags) + "]"


def stdout_reader(pipe, out_queue: "queue.Queue[str]") -> None:
    try:
        for line in iter(pipe.readline, ""):
            if not line:
                break
            out_queue.put(line.strip())
    finally:
        try:
            pipe.close()
        except Exception:
            pass


def main() -> int:
    args = parse_args()
    try:
        ensure_scanner_available(args.scanner_cmd, args.build_cmd)
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    proc = subprocess.Popen(
        args.scanner_cmd,
        shell=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    line_queue: "queue.Queue[str]" = queue.Queue()
    reader_thread = threading.Thread(target=stdout_reader, args=(proc.stdout, line_queue), daemon=True)
    reader_thread.start()

    # Scanner waits for Enter before starting; trigger it automatically.
    if proc.stdin:
        try:
            proc.stdin.write("\n")
            proc.stdin.flush()
        except Exception:
            pass

    seen_tags: list[str] = []
    print("[INFO] Wrapper started. Press Ctrl+C to stop.", flush=True)

    try:
        while True:
            # Drain all available scanner lines for this cycle.
            while True:
                try:
                    line = line_queue.get_nowait()
                except queue.Empty:
                    break

                # Extract EPC-looking tokens from scanner lines.
                for token in TAG_HEX_RE.findall(line.upper()):
                    if token not in seen_tags:
                        seen_tags.append(token)

            print(format_tags(seen_tags), flush=True)
            time.sleep(args.interval)

            if proc.poll() is not None:
                # Scanner process died; surface whatever we have and stop.
                if proc.returncode != 0:
                    print(f"[ERROR] Scanner exited with code {proc.returncode}", file=sys.stderr)
                    return proc.returncode
                return 0

    except KeyboardInterrupt:
        print("\n[INFO] Stopped.")
        return 0
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    sys.exit(main())
