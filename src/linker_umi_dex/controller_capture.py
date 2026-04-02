#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Standalone controller capture utilities."""

import csv
import struct
import threading
import time
from typing import Dict, List, Optional, Tuple

import serial

PACKET_SIZE = 28
FRAME_TAIL = b"\x00\x00\x80\x7f"

JOINT_ANGLE_RANGES = [
    (150.0, 205.0),
    (264.0, 308.0),
    (81.0, 145.0),
    (350.0, 406.0),
    (70.0, 130.0),
    (307.0, 367.0),
]
JOINT_REVERSED = [False, True, True, True, True, True]
JOINT_POS_MIN = 0
JOINT_POS_MAX = 1023


def normalize_angle(angle: float) -> float:
    if angle < -360.0:
        return -360.0
    if angle > 720.0:
        return 720.0
    return angle


def map_angle_to_position(
    angle: float,
    angle_min: float,
    angle_max: float,
    reversed_flag: bool = False,
) -> int:
    angle = normalize_angle(angle)
    angle_min = normalize_angle(angle_min)
    angle_max = normalize_angle(angle_max)

    if abs(angle_max - angle_min) < 1e-6:
        ratio = 0.0
    elif angle <= angle_min:
        ratio = 0.0
    elif angle >= angle_max:
        ratio = 1.0
    else:
        ratio = (angle - angle_min) / (angle_max - angle_min)

    if reversed_flag:
        ratio = 1.0 - ratio

    position = int(ratio * (JOINT_POS_MAX - JOINT_POS_MIN) + JOINT_POS_MIN)
    return max(JOINT_POS_MIN, min(JOINT_POS_MAX, position))


def map_angles_to_positions(angles: List[float]) -> List[float]:
    if len(angles) != 6:
        raise ValueError(f"Expected 6 angles, got {len(angles)}")
    positions: List[float] = []
    for i in range(6):
        angle_min, angle_max = JOINT_ANGLE_RANGES[i]
        position = map_angle_to_position(
            angles[i], angle_min, angle_max, JOINT_REVERSED[i]
        )
        positions.append(float(position))
    return positions


class ControllerReader:
    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        timeout: float = 0.1,
        enable_filter: bool = True,
        filter_alpha: float = 0.3,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.enable_filter = enable_filter
        self.filter_alpha = filter_alpha

        self.serial: Optional[serial.Serial] = None
        self.buffer = bytearray()
        self.filtered_angles = [0.0] * 6
        self.is_first_read = True

        self.packet_count = 0
        self.error_count = 0
        self.last_angles = [0.0] * 6
        self.last_raw_angles = [0.0] * 6

    def connect(self) -> bool:
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
            )
            return True
        except Exception:
            return False

    def disconnect(self) -> None:
        if self.serial and self.serial.is_open:
            self.serial.close()

    def read_packet(self) -> Optional[Tuple[List[float], List[float]]]:
        if not self.serial or not self.serial.is_open:
            return None
        try:
            if self.serial.in_waiting > 0:
                data = self.serial.read(self.serial.in_waiting)
                self.buffer.extend(data)

            data_len = PACKET_SIZE - len(FRAME_TAIL)
            latest_raw = None

            while True:
                frame_end = self.buffer.find(FRAME_TAIL)
                if frame_end == -1:
                    break

                if frame_end >= data_len:
                    packet_start = frame_end - data_len
                    packet = self.buffer[packet_start:frame_end]
                    if len(packet) == data_len:
                        try:
                            latest_raw = list(struct.unpack("<6f", packet))
                        except struct.error:
                            self.error_count += 1

                self.buffer = self.buffer[frame_end + len(FRAME_TAIL) :]

            if len(self.buffer) > PACKET_SIZE * 4:
                self.buffer.clear()

            if latest_raw is None:
                return None

            self.last_raw_angles = latest_raw.copy()

            if self.enable_filter:
                if self.is_first_read:
                    self.filtered_angles = latest_raw.copy()
                    self.is_first_read = False
                else:
                    for i in range(6):
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
            "buffer_size": len(self.buffer),
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
                    "mapped_0",
                    "mapped_1",
                    "mapped_2",
                    "mapped_3",
                    "mapped_4",
                    "mapped_5",
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
                mapped = map_angles_to_positions(filtered_angles)
                t_mono = time.perf_counter() - self.mono_base_s
                t_wall_ns = time.time_ns()
                row = [self._sample_idx, f"{t_mono:.9f}", t_wall_ns] + raw_angles + mapped
                with self._write_lock:
                    with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
                        csv.writer(f).writerow(row)
                self._sample_idx += 1
            time.sleep(self.poll_interval_s)
