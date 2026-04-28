#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Export SLAM replay results to the session output layout.

Writes: trajectory.txt, trajectory.csv, tracked_points.xyz,
map_info.json, d455_frames.csv, slam_log.txt.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np

from ..timebase import ros_ns_to_iso
from .replay import ReplayResult


def _rotation_matrix_to_quaternion(R: np.ndarray) -> tuple[float, float, float, float]:
    """Convert a 3x3 rotation matrix to (qw, qx, qy, qz)."""
    tr = R[0, 0] + R[1, 1] + R[2, 2]
    if tr > 0:
        s = 2.0 * math.sqrt(tr + 1.0)
        qw = 0.25 * s
        qx = (R[2, 1] - R[1, 2]) / s
        qy = (R[0, 2] - R[2, 0]) / s
        qz = (R[1, 0] - R[0, 1]) / s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = 2.0 * math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2])
        qw = (R[2, 1] - R[1, 2]) / s
        qx = 0.25 * s
        qy = (R[0, 1] + R[1, 0]) / s
        qz = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = 2.0 * math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2])
        qw = (R[0, 2] - R[2, 0]) / s
        qx = (R[0, 1] + R[1, 0]) / s
        qy = 0.25 * s
        qz = (R[1, 2] + R[2, 1]) / s
    else:
        s = 2.0 * math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1])
        qw = (R[1, 0] - R[0, 1]) / s
        qx = (R[0, 2] + R[2, 0]) / s
        qy = (R[1, 2] + R[2, 1]) / s
        qz = 0.25 * s
    return qw, qx, qy, qz


def _build_orb_to_ros_map(frame_records: list[dict]) -> dict[float, int]:
    """Map ORB relative time (t_orb_s) to bag timestamp (t_ros_ns)."""
    return {rec["t_orb_s"]: rec["t_ros_ns"] for rec in frame_records}


def export(result: ReplayResult, out_dir: Path) -> dict:
    """Write all SLAM output files and return summary stats."""
    out_dir.mkdir(parents=True, exist_ok=True)
    summary: dict = {"slam_mode": result.slam_mode, "total_frames": result.total_frames}
    orb_to_ros = _build_orb_to_ros_map(result.frame_records)

    # --- trajectory.txt (raw ORB dump, for SLAM debugging) ---
    traj_txt = out_dir / "trajectory.txt"
    with traj_txt.open("w", encoding="utf-8") as f:
        for ts, mat in result.trajectory:
            vals = mat.reshape(-1).tolist()
            f.write(" ".join([f"{ts:.9f}"] + [f"{v:.9f}" for v in vals]) + "\n")
    summary["trajectory_txt_count"] = len(result.trajectory)

    # --- trajectory.csv (with t_ros_ns / t_iso / pose as tx,ty,tz,qw,qx,qy,qz) ---
    traj_csv = out_dir / "trajectory.csv"
    with traj_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["idx", "t_ros_ns", "t_iso", "tx", "ty", "tz", "qw", "qx", "qy", "qz"])
        for i, (ts, mat) in enumerate(result.trajectory):
            tx, ty, tz = float(mat[0, 3]), float(mat[1, 3]), float(mat[2, 3])
            qw, qx, qy, qz = _rotation_matrix_to_quaternion(mat[:3, :3])

            # Resolve t_ros_ns: find the closest ORB time in our frame records
            t_ros_ns = orb_to_ros.get(ts)
            if t_ros_ns is None:
                # Nearest match fallback
                closest_orb = min(orb_to_ros.keys(), key=lambda k: abs(k - ts), default=None)
                t_ros_ns = orb_to_ros.get(closest_orb, 0) if closest_orb is not None else 0

            t_iso = ros_ns_to_iso(t_ros_ns) if t_ros_ns else ""
            w.writerow([
                i, t_ros_ns, t_iso,
                f"{tx:.9f}", f"{ty:.9f}", f"{tz:.9f}",
                f"{qw:.9f}", f"{qx:.9f}", f"{qy:.9f}", f"{qz:.9f}",
            ])
    summary["trajectory_csv_count"] = len(result.trajectory)

    # --- tracked_points.xyz ---
    pts_path = out_dir / "tracked_points.xyz"
    with pts_path.open("w", encoding="utf-8") as f:
        for p in result.tracked_points:
            f.write(f"{float(p[0]):.6f} {float(p[1]):.6f} {float(p[2]):.6f}\n")
    summary["tracked_points_count"] = len(result.tracked_points)

    # --- map_info.json ---
    if result.map_info:
        mi_path = out_dir / "map_info.json"
        mi_path.write_text(json.dumps(result.map_info, indent=2), encoding="utf-8")
    summary["map_info"] = result.map_info

    # --- d455_frames.csv ---
    frames_csv = out_dir / "d455_frames.csv"
    with frames_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["idx", "t_ros_ns", "t_iso", "t_orb_s", "imu_count"])
        for rec in result.frame_records:
            w.writerow([
                rec["frame_idx"],
                rec["t_ros_ns"],
                ros_ns_to_iso(rec["t_ros_ns"]),
                f"{rec['t_orb_s']:.9f}",
                rec["imu_count"],
            ])

    # --- slam_log.txt ---
    log_path = out_dir / "slam_log.txt"
    log_path.write_text("\n".join(result.slam_log) + "\n", encoding="utf-8")

    return summary
