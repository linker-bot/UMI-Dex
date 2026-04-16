#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Standalone controller capture utilities."""

import csv
import os
import threading
import time
import argparse
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import can

COUNT_SCALE = 4096.0
CAN_ID_ENC = 0x112
CAN_PART_COUNT = 3
ASSEMBLY_TTL_S = 2.0
JOINT_NAMES = [
    "thumb_roll",
    "thumb_pitch",
    "index_pitch",
    "middle_pitch",
    "ring_pitch",
    "pinky_pitch",
]
CALIBRATION_CSV_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "config", "calibration.csv")
)


@dataclass(frozen=True)
class JointCalibration:
    joint: str
    raw_count_min: float
    raw_count_max: float
    actual_angle_min: float
    actual_angle_max: float
    reverse_ratio: bool = False


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _circular_distance(value: float, ref: float, period: float = COUNT_SCALE) -> float:
    d = abs(value - ref) % period
    return min(d, period - d)


def _in_ascending_interval(value: float, start: float, end: float) -> bool:
    if start <= end:
        return start <= value <= end
    return value >= start or value <= end


def _ascending_ratio_with_wrap(value: float, start: float, end: float) -> float:
    if start <= end:
        span = end - start
        if span <= 1e-9:
            return 0.0
        return _clip((value - start) / span, 0.0, 1.0)

    span = (COUNT_SCALE - start) + end
    if span <= 1e-9:
        return 0.0
    pos = value - start
    if pos < 0.0:
        pos += COUNT_SCALE
    return _clip(pos / span, 0.0, 1.0)


def _load_calibrations(csv_path: str = CALIBRATION_CSV_PATH) -> List[JointCalibration]:
    rows: Dict[str, Dict[str, str]] = {}
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, skipinitialspace=True)
        for row in reader:
            joint = (row.get("joints") or "").strip()
            if not joint:
                continue
            rows[joint] = row

    missing = [name for name in JOINT_NAMES if name not in rows]
    if missing:
        raise RuntimeError(
            f"Calibration CSV missing joints: {missing}. File: {csv_path}"
        )

    calibrations: List[JointCalibration] = []
    for joint in JOINT_NAMES:
        row = rows[joint]
        raw_deg_min = float(row["raw_angle_min"])
        raw_deg_max = float(row["raw_angle_max"])
        raw_count_min = raw_deg_min * COUNT_SCALE / 360.0
        raw_count_max = raw_deg_max * COUNT_SCALE / 360.0
        calibrations.append(
            JointCalibration(
                joint=joint,
                raw_count_min=raw_count_min,
                raw_count_max=raw_count_max,
                actual_angle_min=float(row["actual_angle_min"]),
                actual_angle_max=float(row["actual_angle_max"]),
                reverse_ratio=(joint == "thumb_roll"),
            )
        )
    return calibrations


class ControllerCalibrator:
    def __init__(self, calibrations: Optional[List[JointCalibration]] = None) -> None:
        self.calibrations = calibrations or _load_calibrations()

    def _map_single(self, raw_count: float, channel_idx: int) -> float:
        calib = self.calibrations[channel_idx]
        value = raw_count % COUNT_SCALE
        lo = min(calib.actual_angle_min, calib.actual_angle_max)
        hi = max(calib.actual_angle_min, calib.actual_angle_max)

        # thumb_roll has a wrapped calibration interval and opposite direction.
        if calib.joint == "thumb_roll" and not _in_ascending_interval(
            value, calib.raw_count_min, calib.raw_count_max
        ):
            d_min = _circular_distance(value, calib.raw_count_min)
            d_max = _circular_distance(value, calib.raw_count_max)
            value = calib.raw_count_min if d_min <= d_max else calib.raw_count_max

        ratio = _ascending_ratio_with_wrap(value, calib.raw_count_min, calib.raw_count_max)
        if calib.reverse_ratio:
            ratio = 1.0 - ratio

        actual = calib.actual_angle_min + ratio * (calib.actual_angle_max - calib.actual_angle_min)
        return round(_clip(actual, lo, hi), 1)

    def map_counts_to_actual(self, raw_counts: List[float]) -> List[float]:
        if len(raw_counts) != len(self.calibrations):
            raise ValueError(f"Expected {len(self.calibrations)} channels, got {len(raw_counts)}")
        return [self._map_single(raw_counts[i], i) for i in range(len(raw_counts))]


@dataclass
class FrameAssembly:
    parts: Dict[int, bytes]
    first_seen_s: float


class ControllerReader:
    def __init__(
        self,
        channel: str = "can0",
        interface: str = "socketcan",
        timeout: float = 0.1,
        enable_filter: bool = True,
        filter_alpha: float = 0.3,
    ) -> None:
        self.channel = channel
        self.interface = interface
        self.timeout = timeout
        self.enable_filter = enable_filter
        self.filter_alpha = filter_alpha

        self.bus: Optional[can.BusABC] = None
        self.assemblies: Dict[int, FrameAssembly] = {}
        self.filtered_angles = [0.0] * 6
        self.is_first_read = True
        self.calibrator = ControllerCalibrator()
        self._wrapped_channels = {
            idx
            for idx, c in enumerate(self.calibrator.calibrations)
            if c.raw_count_min > c.raw_count_max
        }

        self.packet_count = 0
        self.error_count = 0
        self.last_valid_mask = 0
        self.last_angles = [0.0] * 6
        self.last_raw_angles = [0.0] * 6

    @staticmethod
    def _blend_circular_count(prev_value: float, new_value: float, alpha: float) -> float:
        # Blend on a ring [0, COUNT_SCALE) along the shortest angular path.
        delta = (new_value - prev_value) % COUNT_SCALE
        if delta > (COUNT_SCALE / 2.0):
            delta -= COUNT_SCALE
        return (prev_value + alpha * delta) % COUNT_SCALE

    def connect(self) -> bool:
        try:
            self.bus = can.interface.Bus(channel=self.channel, interface=self.interface)
            return True
        except Exception:
            return False

    def disconnect(self) -> None:
        if self.bus is not None:
            self.bus.shutdown()
            self.bus = None

    def _prune_stale(self, now_s: float) -> None:
        stale = [k for k, v in self.assemblies.items() if (now_s - v.first_seen_s) > ASSEMBLY_TTL_S]
        for k in stale:
            self.assemblies.pop(k, None)

    def _assemble_counts(self, asm: FrameAssembly) -> Tuple[List[float], int]:
        # Hardware order in part0 is [thumb_pitch, thumb_roll], we expose [thumb_roll, thumb_pitch].
        counts = [0.0] * 6
        valid_mask = int(asm.parts[0][1]) if 0 in asm.parts else 0
        for p in range(CAN_PART_COUNT):
            pb = asm.parts[p]
            i0 = p * 2
            i1 = i0 + 1
            raw0 = float(pb[4] | (pb[5] << 8))
            raw1 = float(pb[6] | (pb[7] << 8))
            if p == 0:
                counts[1] = raw0  # thumb_pitch -> ch2
                counts[0] = raw1  # thumb_roll  -> ch1
            else:
                counts[i0] = raw0
                counts[i1] = raw1
        return counts, valid_mask

    def _parse_0112(self, msg: can.Message) -> Optional[Tuple[List[float], int]]:
        if msg.arbitration_id != CAN_ID_ENC or msg.dlc != 8:
            return None
        b = msg.data
        part = int(b[0])
        if part not in (0, 1, 2):
            return None
        seq = int(b[2] | (b[3] << 8))
        now_s = time.time()
        asm = self.assemblies.get(seq)
        if asm is None:
            asm = FrameAssembly(parts={}, first_seen_s=now_s)
            self.assemblies[seq] = asm
        asm.parts[part] = bytes(b)
        self._prune_stale(now_s)
        if len(asm.parts) != CAN_PART_COUNT:
            return None
        counts, valid_mask = self._assemble_counts(asm)
        self.assemblies.pop(seq, None)
        return counts, valid_mask

    def read_packet(self) -> Optional[Tuple[List[float], List[float]]]:
        if self.bus is None:
            return None
        try:
            msg = self.bus.recv(timeout=self.timeout)
            if msg is None:
                return None
            parsed = self._parse_0112(msg)
            if parsed is None:
                return None
            latest_raw, valid_mask = parsed
            self.last_raw_angles = latest_raw.copy()
            self.last_valid_mask = valid_mask

            if self.enable_filter:
                if self.is_first_read:
                    self.filtered_angles = latest_raw.copy()
                    self.is_first_read = False
                else:
                    for i in range(6):
                        if bool(valid_mask & (1 << i)):
                            if i in self._wrapped_channels:
                                self.filtered_angles[i] = self._blend_circular_count(
                                    self.filtered_angles[i], latest_raw[i], self.filter_alpha
                                )
                            else:
                                self.filtered_angles[i] = (
                                    self.filter_alpha * latest_raw[i]
                                    + (1.0 - self.filter_alpha) * self.filtered_angles[i]
                                )
                filtered = self.filtered_angles.copy()
            else:
                filtered = latest_raw.copy()

            self.packet_count += 1
            self.last_angles = filtered
            return latest_raw, filtered
        except Exception:
            self.error_count += 1
            return None

    def get_statistics(self) -> Dict[str, object]:
        return {
            "packet_count": self.packet_count,
            "error_count": self.error_count,
            "assembly_buffer_size": len(self.assemblies),
            "last_valid_mask": self.last_valid_mask,
            "last_angles": self.last_angles,
            "last_raw_angles": self.last_raw_angles,
        }


class ControllerCaptureLogger:
    def __init__(
        self,
        csv_path: str,
        mono_base_s: float,
        reader: ControllerReader,
        poll_interval_s: float = 0.001,
    ) -> None:
        self.csv_path = csv_path
        self.mono_base_s = mono_base_s
        self.reader = reader
        self.poll_interval_s = poll_interval_s

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._sample_idx = 0
        self._write_lock = threading.Lock()

    def start(self) -> None:
        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "sample_idx",
                    "t_mono_s",
                    "t_wall_ns",
                    "raw_0",
                    "raw_1",
                    "raw_2",
                    "raw_3",
                    "raw_4",
                    "raw_5",
                    "thumb_roll",
                    "thumb_pitch",
                    "index_pitch",
                    "middle_pitch",
                    "ring_pitch",
                    "pinky_pitch",
                ]
            )
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        while self._running:
            result = self.reader.read_packet()
            if result is not None:
                raw_angles, filtered_angles = result
                mapped = self.reader.calibrator.map_counts_to_actual(filtered_angles)
                t_mono = time.perf_counter() - self.mono_base_s
                t_wall_ns = time.time_ns()
                row = [self._sample_idx, f"{t_mono:.9f}", t_wall_ns] + raw_angles + mapped
                with self._write_lock:
                    with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
                        csv.writer(f).writerow(row)
                self._sample_idx += 1
            time.sleep(self.poll_interval_s)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Capture calibrated controller joint angles from CAN to CSV (no camera required)."
    )
    ap.add_argument("--channel", default="can0", help="CAN channel name, e.g. can0.")
    ap.add_argument("--bustype", default="socketcan", help="python-can interface type.")
    ap.add_argument("--timeout", type=float, default=0.1, help="CAN receive timeout in seconds.")
    ap.add_argument("--out", default="./outputs/realtime_map/controller_angles.csv", help="Output CSV path.")
    ap.add_argument("--poll_interval_s", type=float, default=0.001, help="Logger poll interval in seconds.")
    ap.add_argument("--filter_alpha", type=float, default=0.3, help="Low-pass filter alpha.")
    ap.add_argument("--disable_filter", action="store_true", help="Disable low-pass filter.")
    ap.add_argument(
        "--max_seconds",
        type=float,
        default=0.0,
        help="Optional capture duration; 0 means run until Ctrl+C.",
    )
    args = ap.parse_args()

    out_path = os.path.normpath(args.out)
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    reader = ControllerReader(
        channel=args.channel,
        interface=args.bustype,
        timeout=args.timeout,
        enable_filter=not args.disable_filter,
        filter_alpha=args.filter_alpha,
    )
    if not reader.connect():
        print(f"[controller] failed to connect on {args.channel} ({args.bustype})")
        return 1

    logger = ControllerCaptureLogger(
        csv_path=out_path,
        mono_base_s=time.perf_counter(),
        reader=reader,
        poll_interval_s=args.poll_interval_s,
    )
    logger.start()
    print(f"[controller] capturing to: {out_path}")
    print("[controller] press Ctrl+C to stop")

    t0 = time.time()
    try:
        while True:
            if args.max_seconds > 0 and (time.time() - t0) >= args.max_seconds:
                break
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        logger.stop()
        reader.disconnect()
        stats = reader.get_statistics()
        print(
            f"[controller] stopped. packets={stats['packet_count']} errors={stats['error_count']}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
