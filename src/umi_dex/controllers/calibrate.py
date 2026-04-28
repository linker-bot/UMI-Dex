#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Map raw encoder counts to calibrated joint angles.

Ported from ``controller_capture.py`` — the same math, but decoupled
from the live CAN reader.  Calibration data comes from
``config/calibration.csv``.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .can_decode import COUNT_SCALE, JOINT_NAMES, NUM_JOINTS

_DEFAULT_CALIBRATION_CSV = Path(__file__).resolve().parents[3] / "config" / "calibration.csv"


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


def load_calibrations(
    csv_path: Optional[str | Path] = None,
) -> list[JointCalibration]:
    """Load per-joint calibration from CSV.

    Falls back to ``config/calibration.csv`` relative to the repo root.
    """
    path = str(csv_path or _DEFAULT_CALIBRATION_CSV)
    rows: dict[str, dict[str, str]] = {}
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, skipinitialspace=True)
        for row in reader:
            joint = (row.get("joints") or "").strip()
            if not joint:
                continue
            rows[joint] = row

    missing = [name for name in JOINT_NAMES if name not in rows]
    if missing:
        raise RuntimeError(
            f"Calibration CSV missing joints: {missing}. File: {path}"
        )

    calibrations: list[JointCalibration] = []
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


class Calibrator:
    """Maps 6-channel raw encoder counts to calibrated joint angles."""

    def __init__(
        self,
        calibrations: Optional[list[JointCalibration]] = None,
        csv_path: Optional[str | Path] = None,
    ) -> None:
        self.calibrations = calibrations or load_calibrations(csv_path)

    def _map_single(self, raw_count: float, channel_idx: int) -> float:
        calib = self.calibrations[channel_idx]
        value = raw_count % COUNT_SCALE
        lo = min(calib.actual_angle_min, calib.actual_angle_max)
        hi = max(calib.actual_angle_min, calib.actual_angle_max)

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

    def map_counts(self, raw_counts: list[float]) -> list[float]:
        """Map a 6-element raw-count vector to calibrated angles."""
        if len(raw_counts) != len(self.calibrations):
            raise ValueError(
                f"Expected {len(self.calibrations)} channels, got {len(raw_counts)}"
            )
        return [self._map_single(raw_counts[i], i) for i in range(len(raw_counts))]

    @property
    def wrapped_channels(self) -> set[int]:
        return {
            i for i, c in enumerate(self.calibrations)
            if c.raw_count_min > c.raw_count_max
        }
