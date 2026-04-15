"""Joint angle calibration: raw encoder counts -> actual angles (0-100).

Ported from src/umi_dex/controller_capture.py.  No ROS dependency.
"""

import csv
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

from .can_protocol import COUNT_SCALE, JOINT_NAMES, NUM_JOINTS

DEFAULT_CALIBRATION_CSV = os.path.normpath(
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


def load_calibrations(csv_path: str = DEFAULT_CALIBRATION_CSV) -> List[JointCalibration]:
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
        calibrations.append(
            JointCalibration(
                joint=joint,
                raw_count_min=raw_deg_min * COUNT_SCALE / 360.0,
                raw_count_max=raw_deg_max * COUNT_SCALE / 360.0,
                actual_angle_min=float(row["actual_angle_min"]),
                actual_angle_max=float(row["actual_angle_max"]),
                reverse_ratio=(joint == "thumb_roll"),
            )
        )
    return calibrations


class Calibrator:
    def __init__(self, calibrations: Optional[List[JointCalibration]] = None,
                 csv_path: str = DEFAULT_CALIBRATION_CSV) -> None:
        self.calibrations = calibrations or load_calibrations(csv_path)

    def wrapped_channels(self) -> set:
        """Return indices of channels whose raw range wraps around 0/4096."""
        return {
            i for i, c in enumerate(self.calibrations)
            if c.raw_count_min > c.raw_count_max
        }

    def _map_single(self, raw_count: float, idx: int) -> float:
        calib = self.calibrations[idx]
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

    def map_counts(self, raw_counts: List[float]) -> List[float]:
        return [self._map_single(raw_counts[i], i) for i in range(NUM_JOINTS)]
