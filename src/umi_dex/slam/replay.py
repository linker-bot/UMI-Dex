#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline ORB-SLAM3 replayer driven by bag data.

Reads D455 stereo IR + IMU from a bag file and feeds them to ORB-SLAM3
in time order, paced at real time by default to let the internal local
mapping and IMU-init threads converge properly.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import orbslam3

from ..bag_reader import BagReader


@dataclass
class ReplayResult:
    """Aggregated results after SLAM replay completes."""

    trajectory: list[tuple[float, np.ndarray]]  # (t_orb_s, 4x4 matrix)
    tracked_points: list[np.ndarray]  # list of (x,y,z)
    map_info: Optional[dict]
    frame_records: list[dict]  # per-frame metadata
    slam_log: list[str]  # VIBA / tracking events
    total_frames: int
    slam_mode: str


def replay_bag(
    bag_path: Path,
    vocab_path: Path,
    settings_path: Path,
    *,
    stereo_only: bool = False,
    realtime_factor: float = 1.0,
    max_frames: int = 0,
) -> ReplayResult:
    """Run ORB-SLAM3 offline on bag data.

    Parameters
    ----------
    bag_path:
        Path to the ROS1 bag containing D455 topics.
    vocab_path:
        Path to ORBvoc.txt.
    settings_path:
        Path to the ORB-SLAM3 YAML settings file.
    stereo_only:
        If True, use Sensor.STEREO (no IMU fusion).
    realtime_factor:
        Pacing factor: 1.0 = realtime, 0.0 = no pacing (fast as possible).
    max_frames:
        Stop after this many stereo frames (0 = no limit).
    """
    slam_log: list[str] = []
    frame_records: list[dict] = []

    mode_str = "stereo_only" if stereo_only else "stereo_inertial"
    sensor = orbslam3.Sensor.STEREO if stereo_only else orbslam3.Sensor.IMU_STEREO
    slam = orbslam3.System(str(vocab_path), str(settings_path), sensor)
    slam.initialize()
    slam_log.append(f"[slam] initialized mode={mode_str}")

    ir1_topic = "/camera/infra1/image_rect_raw"
    ir2_topic = "/camera/infra2/image_rect_raw"
    imu_topic = "/camera/imu"

    topics = [ir1_topic, ir2_topic]
    if not stereo_only:
        topics.append(imu_topic)

    # Collect all messages into memory-efficient buffers keyed by timestamp.
    # For large bags this could be done streaming, but for typical sessions
    # (< 10 min @ 30 Hz + 200 Hz IMU) the memory footprint is manageable.
    ir1_frames: dict[int, np.ndarray] = {}
    ir2_frames: dict[int, np.ndarray] = {}
    imu_samples: list[tuple[int, float, float, float, float, float, float]] = []

    with BagReader(bag_path) as reader:
        bag_start_ns = reader.start_ns

        for sm in reader.read_messages(topics=topics):
            if sm.topic == ir1_topic:
                img = np.frombuffer(bytes(sm.msg.data), dtype=np.uint8).reshape(
                    int(sm.msg.height), int(sm.msg.width)
                )
                ir1_frames[sm.t_ros_ns] = img
            elif sm.topic == ir2_topic:
                img = np.frombuffer(bytes(sm.msg.data), dtype=np.uint8).reshape(
                    int(sm.msg.height), int(sm.msg.width)
                )
                ir2_frames[sm.t_ros_ns] = img
            elif sm.topic == imu_topic:
                av = sm.msg.linear_acceleration
                gv = sm.msg.angular_velocity
                imu_samples.append((
                    sm.t_ros_ns,
                    float(gv.x), float(gv.y), float(gv.z),
                    float(av.x), float(av.y), float(av.z),
                ))

    # Sort IMU by timestamp
    imu_samples.sort(key=lambda x: x[0])
    imu_deque = deque(imu_samples)

    # Match stereo pairs by finding nearest IR2 for each IR1 timestamp
    ir1_times = sorted(ir1_frames.keys())
    ir2_times_sorted = sorted(ir2_frames.keys())

    if not ir1_times:
        slam.shutdown()
        return ReplayResult(
            trajectory=[], tracked_points=[], map_info=None,
            frame_records=[], slam_log=slam_log,
            total_frames=0, slam_mode=mode_str,
        )

    # Build a quick lookup for IR2 nearest-match
    import bisect

    def _nearest_ir2(t_ns: int) -> Optional[int]:
        pos = bisect.bisect_left(ir2_times_sorted, t_ns)
        candidates = []
        if pos > 0:
            candidates.append(ir2_times_sorted[pos - 1])
        if pos < len(ir2_times_sorted):
            candidates.append(ir2_times_sorted[pos])
        if not candidates:
            return None
        return min(candidates, key=lambda c: abs(c - t_ns))

    t_base_ns = ir1_times[0]
    t_base_s = t_base_ns / 1e9
    prev_tl_ns: Optional[int] = None
    last_imu_row: Optional[tuple] = None
    last_traj_snapshot: list = []
    last_pts_snapshot: list = []

    wall_start = time.perf_counter()
    bag_time_start_s = ir1_times[0] / 1e9

    frame_idx = 0
    for tl_ns in ir1_times:
        if max_frames > 0 and frame_idx >= max_frames:
            break

        tr_ns = _nearest_ir2(tl_ns)
        if tr_ns is None or abs(tr_ns - tl_ns) > 50_000_000:  # 50ms max stereo pair gap
            continue

        iml = ir1_frames[tl_ns]
        imr = ir2_frames[tr_ns]

        tl_s = (tl_ns / 1e9) - t_base_s

        if stereo_only:
            slam.process_stereo_enhanced(iml, imr, tl_s)
            imu_n = 0
        else:
            frame_imu = []
            while imu_deque and imu_deque[0][0] <= tl_ns + 5_000_000:
                row = imu_deque.popleft()
                if prev_tl_ns is not None and row[0] < prev_tl_ns:
                    continue
                ts_rel = (row[0] / 1e9) - t_base_s
                # ORB-SLAM3 expects: (ax, ay, az, gx, gy, gz, ts)
                frame_imu.append((row[4], row[5], row[6], row[1], row[2], row[3], ts_rel))

            if not frame_imu:
                if last_imu_row is not None:
                    ax, ay, az, gx, gy, gz, _ = last_imu_row
                    frame_imu.append((ax, ay, az, gx, gy, gz, tl_s))
                else:
                    frame_imu.append((0.0, 9.81, 0.0, 0.0, 0.0, 0.0, tl_s))
                slam_log.append(f"[slam] frame {frame_idx}: empty IMU buffer, using fallback")

            slam.process_stereo_inertial_enhanced(iml, imr, tl_s, frame_imu)
            last_imu_row = frame_imu[-1]
            imu_n = len(frame_imu)

        prev_tl_ns = tl_ns

        frame_records.append({
            "frame_idx": frame_idx,
            "t_ros_ns": tl_ns,
            "t_orb_s": tl_s,
            "imu_count": imu_n,
        })

        # Periodically snapshot trajectory for fallback
        if frame_idx % 30 == 0:
            try:
                traj_now = list(slam.get_trajectory_points())
                pts_now = list(slam.get_tracked_mappoints())
                if traj_now:
                    last_traj_snapshot = traj_now
                if pts_now:
                    last_pts_snapshot = pts_now
            except Exception:
                pass

        # Realtime pacing
        if realtime_factor > 0:
            bag_elapsed_s = (tl_ns / 1e9) - bag_time_start_s
            wall_elapsed = time.perf_counter() - wall_start
            target = bag_elapsed_s / realtime_factor
            sleep_s = target - wall_elapsed
            if sleep_s > 0.001:
                time.sleep(sleep_s)

        frame_idx += 1

    # Finalize
    trajectory: list[tuple[float, np.ndarray]] = []
    try:
        traj_iter = list(slam.get_trajectory_points())
        if not traj_iter and last_traj_snapshot:
            traj_iter = last_traj_snapshot
        for item in traj_iter:
            ts = float(item[0])
            mat = np.array(item[1], dtype=np.float64).reshape(4, 4)
            trajectory.append((ts, mat))
    except Exception:
        slam_log.append("[slam] WARNING: failed to retrieve final trajectory")

    tracked_points: list[np.ndarray] = []
    try:
        pts_iter = list(slam.get_tracked_mappoints())
        if not pts_iter and last_pts_snapshot:
            pts_iter = last_pts_snapshot
        for p in pts_iter:
            if len(p) >= 3:
                tracked_points.append(np.array([float(p[0]), float(p[1]), float(p[2])]))
    except Exception:
        slam_log.append("[slam] WARNING: failed to retrieve tracked map points")

    map_info: Optional[dict] = None
    try:
        mi = slam.get_map_info()
        map_info = {
            "num_keyframes": int(mi.num_keyframes),
            "active_map_points": int(mi.active_map_points),
            "total_map_points": int(mi.total_map_points),
            "tracking_state": int(mi.tracking_state),
        }
    except Exception:
        slam_log.append("[slam] WARNING: get_map_info unavailable")

    slam.shutdown()

    return ReplayResult(
        trajectory=trajectory,
        tracked_points=tracked_points,
        map_info=map_info,
        frame_records=frame_records,
        slam_log=slam_log,
        total_frames=frame_idx,
        slam_mode=mode_str,
    )
