#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Column definitions and dtypes for all output files.

Centralises the contract so validators, writers, and readers agree on
column names, ordering, and types.
"""

from __future__ import annotations

import pyarrow as pa

from ..controllers.can_decode import JOINT_NAMES

# ---------- trajectory.csv ----------
TRAJECTORY_COLUMNS = [
    "idx", "t_ros_ns", "t_iso",
    "tx", "ty", "tz",
    "qw", "qx", "qy", "qz",
]

# ---------- controller.csv ----------
CONTROLLER_COLUMNS = (
    ["idx", "t_ros_ns", "t_iso"]
    + [f"raw_{i}" for i in range(6)]
    + list(JOINT_NAMES)
)

# ---------- d405_color_frames.csv ----------
D405_FRAME_COLUMNS = ["idx", "t_ros_ns", "t_iso", "pts_ns"]

# ---------- d455_frames.csv ----------
D455_FRAME_COLUMNS = ["idx", "t_ros_ns", "t_iso", "t_orb_s", "imu_count"]

# ---------- aligned_dataset.parquet ----------
ALIGNED_SCHEMA = pa.schema([
    pa.field("idx", pa.int64()),
    pa.field("t_ros_ns", pa.int64()),
    pa.field("t_iso", pa.string()),
    pa.field("episode_id", pa.int64()),
    # trajectory
    pa.field("tx", pa.float64()),
    pa.field("ty", pa.float64()),
    pa.field("tz", pa.float64()),
    pa.field("qw", pa.float64()),
    pa.field("qx", pa.float64()),
    pa.field("qy", pa.float64()),
    pa.field("qz", pa.float64()),
    # controller (nearest-matched)
    pa.field("ctrl_t_ros_ns", pa.int64()),
    pa.field("ctrl_dt_ns", pa.int64()),
    *[pa.field(f"raw_{i}", pa.float64()) for i in range(6)],
    *[pa.field(name, pa.float64()) for name in JOINT_NAMES],
    # D405 color frame (nearest-matched)
    pa.field("d405_frame_idx", pa.int64()),
    pa.field("d405_t_ros_ns", pa.int64()),
    pa.field("d405_dt_ns", pa.int64()),
])
