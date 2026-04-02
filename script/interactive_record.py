#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Interactive terminal controller for trajectory recording.

Keys:
- s: start recording
- c: stop recording and save
- r: reset/delete previous output directory
- q: quit
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import List, Optional

_ERROR_LINE_PATTERNS = (
    "warn",
    "error",
    "exception",
    "traceback",
    "failed",
    "runtimeerror",
    "fatal",
    "keyboardinterrupt",
)

_TRACE_LINE_RE = re.compile(r"^\s*File\s+\".*\", line \d+, in .+")


def _validate_required_files(vocab: Path, settings: Path) -> None:
    if not vocab.exists():
        raise FileNotFoundError(f"vocab file not found: {vocab}")
    if not settings.exists():
        raise FileNotFoundError(f"settings file not found: {settings}")


def _build_child_cmd(args: argparse.Namespace) -> List[str]:
    cmd = [
        sys.executable,
        "-m",
        "linker_umi_dex.orb_runner",
        "--vocab",
        str(args.vocab),
        "--settings",
        str(args.settings),
        "--out_dir",
        str(args.out_dir),
        "--width",
        str(args.width),
        "--height",
        str(args.height),
        "--fps",
        str(args.fps),
        "--gyro_fps",
        str(args.gyro_fps),
        "--accel_fps",
        str(args.accel_fps),
    ]
    if args.disable_controller_capture:
        cmd.append("--disable_controller_capture")
    else:
        cmd.extend(
            [
                "--controller_port",
                args.controller_port,
                "--controller_baudrate",
                str(args.controller_baudrate),
                "--controller_timeout",
                str(args.controller_timeout),
                "--controller_filter_alpha",
                str(args.controller_filter_alpha),
            ]
        )
        if args.controller_disable_filter:
            cmd.append("--controller_disable_filter")
        if args.controller_required:
            cmd.append("--controller_required")
    return cmd


def _is_error_line(line: str) -> bool:
    ll = line.lower()
    return any(pat in ll for pat in _ERROR_LINE_PATTERNS)


def _relay_stream(stream: Optional[object]) -> None:
    if stream is None:
        return
    in_traceback = False
    traceback_lines_left = 0
    for raw in iter(stream.readline, ""):
        line = raw.rstrip("\n")
        if in_traceback:
            print(line)
            if _TRACE_LINE_RE.match(line) or line.strip() == "":
                traceback_lines_left = max(traceback_lines_left, 6)
            traceback_lines_left -= 1
            if traceback_lines_left <= 0:
                in_traceback = False
            continue
        if _is_error_line(line):
            print(line)
            if "traceback" in line.lower():
                in_traceback = True
                traceback_lines_left = 12
    try:
        stream.close()
    except Exception:
        pass


def _spawn_child_with_filtered_output(
    cmd: List[str], cwd: str
) -> tuple[subprocess.Popen, List[threading.Thread]]:
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    threads = [
        threading.Thread(target=_relay_stream, args=(proc.stdout,), daemon=True),
        threading.Thread(target=_relay_stream, args=(proc.stderr,), daemon=True),
    ]
    for th in threads:
        th.start()
    return proc, threads


def _join_relays(threads: List[threading.Thread], timeout: float = 1.0) -> None:
    for th in threads:
        th.join(timeout=timeout)


def _stop_child(proc: subprocess.Popen, wait_seconds: float = 6.0) -> None:
    if proc.poll() is not None:
        return
    def _try_send(sig: int) -> bool:
        try:
            proc.send_signal(sig)
            return True
        except (PermissionError, ProcessLookupError):
            return False

    try:
        if not _try_send(signal.SIGINT):
            return
    except Exception:
        return
    t0 = time.time()
    while (time.time() - t0) < wait_seconds:
        if proc.poll() is not None:
            return
        time.sleep(0.1)
    if not _try_send(signal.SIGTERM):
        return
    try:
        proc.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        if _try_send(signal.SIGKILL):
            proc.wait(timeout=2.0)


def _reset_output_dir(out_dir: Path) -> None:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)


def _print_help() -> None:
    print("")
    print("[interactive] Controls:")
    print("  s -> start recording")
    print("  c -> stop recording and save")
    print("  r -> delete previous output directory (destructive)")
    print("  q -> quit")
    print("")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Interactive trajectory recorder: s=start, c=stop/save, r=reset outputs, q=quit."
    )
    ap.add_argument("--vocab", default="./config/ORBvoc.txt")
    ap.add_argument("--settings", default="./config/intel_d455.yaml")
    ap.add_argument("--out_dir", default="./outputs/realtime_map")
    ap.add_argument("--width", type=int, default=848)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--gyro_fps", type=int, default=200)
    ap.add_argument("--accel_fps", type=int, default=200)
    ap.add_argument("--disable_controller_capture", action="store_true")
    ap.add_argument("--controller_port", default="/dev/l6encoder_usb")
    ap.add_argument("--controller_baudrate", type=int, default=115200)
    ap.add_argument("--controller_timeout", type=float, default=0.1)
    ap.add_argument("--controller_filter_alpha", type=float, default=0.3)
    ap.add_argument("--controller_disable_filter", action="store_true")
    ap.add_argument("--controller_required", action="store_true")
    args = ap.parse_args()

    args.vocab = str(Path(args.vocab).expanduser().resolve())
    args.settings = str(Path(args.settings).expanduser().resolve())
    args.out_dir = str(Path(args.out_dir).expanduser().resolve())
    out_dir = Path(args.out_dir)

    _validate_required_files(Path(args.vocab), Path(args.settings))
    out_dir.mkdir(parents=True, exist_ok=True)

    child: Optional[subprocess.Popen] = None
    child_relays: List[threading.Thread] = []
    _print_help()
    print(f"[interactive] output directory: {out_dir}")
    print("[interactive] waiting for command...")

    while True:
        try:
            key = input("> ").strip().lower()
        except EOFError:
            key = "q"
        except KeyboardInterrupt:
            print("")
            key = "q"

        if key == "s":
            if child is not None and child.poll() is None:
                print("[interactive] already recording; press 'c' to stop first.")
                continue
            cmd = _build_child_cmd(args)
            print("[interactive] starting orb runner...")
            print("[interactive] cmd:", " ".join(cmd))
            child, child_relays = _spawn_child_with_filtered_output(cmd, cwd=os.getcwd())
            print("[interactive] recording started.")
        elif key == "c":
            if child is None or child.poll() is not None:
                print("[interactive] no active recording.")
                continue
            print("[interactive] stopping and saving...")
            _stop_child(child)
            _join_relays(child_relays)
            print("[interactive] stopped.")
        elif key == "r":
            if child is not None and child.poll() is None:
                print("[interactive] cannot reset while recording. Press 'c' first.")
                continue
            print(f"[interactive] deleting output directory: {out_dir}")
            _reset_output_dir(out_dir)
            print("[interactive] output directory reset complete.")
        elif key == "q":
            if child is not None and child.poll() is None:
                print("[interactive] stopping active recording before exit...")
                _stop_child(child)
                _join_relays(child_relays)
            print("[interactive] bye.")
            return 0
        elif key == "":
            continue
        else:
            print(f"[interactive] unknown key: {key!r}")
            _print_help()


if __name__ == "__main__":
    raise SystemExit(main())
