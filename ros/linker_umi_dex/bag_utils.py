"""Rosbag read/extract helpers for post-processing capture bags."""

import csv
import os
from typing import List, Optional

from .can_protocol import JOINT_NAMES


def extract_controller_csv(bag_path: str, output_csv: str,
                           topic: str = "/hand/joint_states") -> int:
    """Read HandJointState messages from a bag and write a CSV.

    Returns the number of rows written.

    This function imports rosbag lazily so it can be tested for import
    errors before the ROS environment is available.
    """
    import rosbag  # noqa: delayed import

    os.makedirs(os.path.dirname(output_csv) or ".", exist_ok=True)

    count = 0
    with rosbag.Bag(bag_path, "r") as bag, \
         open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["t_ros_s"] + JOINT_NAMES)
        for _, msg, t in bag.read_messages(topics=[topic]):
            t_s = t.to_sec()
            positions = list(msg.positions)
            writer.writerow([f"{t_s:.9f}"] + [f"{p:.1f}" for p in positions])
            count += 1

    return count


def extract_image_timestamps(bag_path: str, output_csv: str,
                              topic: str = "/camera/infra1/image_rect_raw") -> int:
    """Extract per-frame timestamps from an image topic into a CSV."""
    import rosbag  # noqa: delayed import

    os.makedirs(os.path.dirname(output_csv) or ".", exist_ok=True)

    count = 0
    with rosbag.Bag(bag_path, "r") as bag, \
         open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["frame_idx", "t_ros_s", "t_header_s"])
        for _, msg, t in bag.read_messages(topics=[topic]):
            t_ros = t.to_sec()
            t_hdr = msg.header.stamp.to_sec() if msg.header.stamp.to_sec() > 0 else t_ros
            writer.writerow([count, f"{t_ros:.9f}", f"{t_hdr:.9f}"])
            count += 1

    return count
