#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Realtime ORB-SLAM3 runner."""

import argparse
import csv
import json
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone

import numpy as np
import orbslam3
import pyrealsense2 as rs

from .controller_capture import ControllerCaptureLogger, ControllerReader

_DEBUG_LOG_PATH = os.environ.get("LINKER_UD_DEBUG_LOG", "").strip()
_RUN_ID = f"realtime-{int(time.time() * 1000)}"

def _debug_log(hypothesis_id: str, location: str, message: str, data: dict) -> None:
    if not _DEBUG_LOG_PATH:
        return
    payload = {
        "sessionId": "829bce",
        "runId": _RUN_ID,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    try:
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass


def frame_ts_s(frame: rs.frame) -> float:
    return float(frame.get_timestamp()) * 1e-3


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Realtime ORB-SLAM3 stereo-inertial runner with optional controller capture."
    )
    ap.add_argument("--vocab", required=True)
    ap.add_argument("--settings", required=True)
    ap.add_argument("--width", type=int, default=848)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--gyro_fps", type=int, default=200)
    ap.add_argument("--accel_fps", type=int, default=200)
    ap.add_argument("--max_seconds", type=float, default=0.0, help="0 means run until Ctrl+C")
    ap.add_argument("--out_dir", default="./outputs/realtime_map")
    ap.add_argument("--controller_channel", default="can0")
    ap.add_argument("--controller_bustype", default="socketcan")
    ap.add_argument("--controller_timeout", type=float, default=0.1)
    ap.add_argument("--controller_filter_alpha", type=float, default=0.3)
    ap.add_argument("--controller_disable_filter", action="store_true")
    ap.add_argument("--controller_required", action="store_true")
    ap.add_argument("--disable_controller_capture", action="store_true")
    args = ap.parse_args()
    out_dir = os.path.normpath(args.out_dir.strip())
    os.makedirs(out_dir, exist_ok=True)

    session_start_wall_ns = time.time_ns()
    session_start_mono_s = time.perf_counter()
    run_clock_info_path = os.path.join(out_dir, "run_clock_info.csv")
    with open(run_clock_info_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["session_start_wall_ns", "session_start_utc_iso8601", "session_start_mono_s"]
        )
        writer.writerow(
            [
                session_start_wall_ns,
                datetime.fromtimestamp(
                    session_start_wall_ns / 1_000_000_000.0, tz=timezone.utc
                ).isoformat(),
                f"{session_start_mono_s:.9f}",
            ]
        )

    frame_times_path = os.path.join(out_dir, "orb_frame_times.csv")
    frame_times_f = open(frame_times_path, "w", newline="", encoding="utf-8")
    frame_times_w = csv.writer(frame_times_f)
    frame_times_w.writerow(["frame_idx", "t_orb_s", "t_mono_s", "t_wall_ns", "imu_count"])

    controller_reader = None
    controller_logger = None
    controller_csv_path = os.path.join(out_dir, "controller_angles.csv")
    controller_enabled = not args.disable_controller_capture
    if controller_enabled:
        controller_reader = ControllerReader(
            channel=args.controller_channel,
            interface=args.controller_bustype,
            timeout=args.controller_timeout,
            enable_filter=not args.controller_disable_filter,
            filter_alpha=args.controller_filter_alpha,
        )
        if controller_reader.connect():
            controller_logger = ControllerCaptureLogger(
                csv_path=controller_csv_path,
                mono_base_s=session_start_mono_s,
                reader=controller_reader,
            )
            controller_logger.start()
            print(f"[controller] logging enabled: {controller_csv_path}")
        else:
            msg = (
                f"[controller] failed to connect on "
                f"{args.controller_channel} ({args.controller_bustype})"
            )
            if args.controller_required:
                raise RuntimeError(msg)
            print(msg + " (continuing without controller logging)")
            controller_enabled = False

    slam = orbslam3.System(args.vocab, args.settings, orbslam3.Sensor.IMU_STEREO)
    slam.initialize()

    pipeline = rs.pipeline()
    cfg = rs.config()
    cfg.enable_stream(rs.stream.infrared, 1, args.width, args.height, rs.format.y8, args.fps)
    cfg.enable_stream(rs.stream.infrared, 2, args.width, args.height, rs.format.y8, args.fps)
    cfg.enable_stream(rs.stream.gyro, rs.format.motion_xyz32f, args.gyro_fps)
    cfg.enable_stream(rs.stream.accel, rs.format.motion_xyz32f, args.accel_fps)

    imu_lock = threading.Lock()
    imu_buf = deque(maxlen=20000)
    last_acc = None
    q = rs.frame_queue(4096)

    def cb(frame: rs.frame) -> None:
        nonlocal last_acc
        if frame.is_motion_frame():
            m = frame.as_motion_frame()
            md = m.get_motion_data()
            t_s = frame_ts_s(m)
            st = m.get_profile().stream_type()
            with imu_lock:
                if st == rs.stream.accel:
                    last_acc = (md.x, md.y, md.z)
                elif st == rs.stream.gyro:
                    ax, ay, az = last_acc if last_acc is not None else (0.0, 0.0, 9.81)
                    imu_buf.append((t_s, md.x, md.y, md.z, ax, ay, az))
        else:
            try:
                q.enqueue(frame)
            except Exception:
                pass

    profile = pipeline.start(cfg, cb)
    try:
        stream_summaries = []
        for s in profile.get_streams():
            if s.stream_type() == rs.stream.infrared:
                vsp = s.as_video_stream_profile()
                intr = vsp.get_intrinsics()
                stream_summaries.append(
                    {
                        "stream_name": s.stream_name(),
                        "stream_index": int(s.stream_index()),
                        "fps": int(s.fps()),
                        "format": str(s.format()),
                        "width": int(intr.width),
                        "height": int(intr.height),
                    }
                )
        _debug_log(
            "H15",
            "orb_runner.py",
            "active infrared stream intrinsics",
            {"streams": stream_summaries},
        )
    except Exception:
        pass
    try:
        dev = profile.get_device()
        for sensor in dev.query_sensors():
            if sensor.supports(rs.option.global_time_enabled):
                sensor.set_option(rs.option.global_time_enabled, 1.0)
    except Exception:
        pass

    t0 = time.time()
    prev_cam_t = None
    frame_idx = 0
    t_base = None
    last_stats_print = time.time()
    last_traj_snapshot = []
    last_pts_snapshot = []

    try:
        while True:
            if args.max_seconds > 0 and (time.time() - t0) > args.max_seconds:
                break

            f = q.wait_for_frame(1000)
            if not f or not f.is_frameset():
                continue
            fs = f.as_frameset()
            l = fs.get_infrared_frame(1)
            r = fs.get_infrared_frame(2)
            if not l or not r:
                continue

            tl_abs = frame_ts_s(l)
            if t_base is None:
                t_base = tl_abs
            tl = tl_abs - t_base
            iml = np.asanyarray(l.get_data())
            imr = np.asanyarray(r.get_data())

            frame_imu = []
            with imu_lock:
                for t_s, gx, gy, gz, ax, ay, az in list(imu_buf):
                    ts_rel = t_s - t_base if t_base is not None else t_s
                    if prev_cam_t is None:
                        if ts_rel <= tl:
                            frame_imu.append((ax, ay, az, gx, gy, gz, ts_rel))
                    else:
                        if prev_cam_t < ts_rel <= tl:
                            frame_imu.append((ax, ay, az, gx, gy, gz, ts_rel))
                while imu_buf and imu_buf[0][0] <= tl_abs - 0.2:
                    imu_buf.popleft()

            slam.process_stereo_inertial_enhanced(iml, imr, tl, frame_imu)
            t_mono = time.perf_counter() - session_start_mono_s
            frame_times_w.writerow([frame_idx, f"{tl:.9f}", f"{t_mono:.9f}", time.time_ns(), len(frame_imu)])

            if time.time() - last_stats_print > 1.0:
                last_stats_print = time.time()
                try:
                    mi = slam.get_map_info()
                    print(
                        f"[map] keyframes={int(mi.num_keyframes)} "
                        f"active_points={int(mi.active_map_points)} "
                        f"total_points={int(mi.total_map_points)}"
                    )
                except Exception:
                    try:
                        traj_now = list(slam.get_trajectory_points())
                        pts_now = list(slam.get_tracked_mappoints())
                        if len(traj_now) > 0:
                            last_traj_snapshot = traj_now
                        if len(pts_now) > 0:
                            last_pts_snapshot = pts_now
                    except Exception:
                        pass
            prev_cam_t = tl
            frame_idx += 1
    except KeyboardInterrupt:
        pass
    finally:
        try:
            frame_times_f.close()
        except Exception:
            pass
        export_summary = {"out_dir": out_dir}
        export_summary["controller_capture"] = {
            "enabled": bool(controller_enabled),
            "csv_path": controller_csv_path if controller_enabled else None,
        }
        export_summary["sync_files"] = {
            "run_clock_info": run_clock_info_path,
            "orb_frame_times": frame_times_path,
        }
        if controller_reader is not None:
            export_summary["controller_stats"] = controller_reader.get_statistics()
        try:
            mi = slam.get_map_info()
            info = {
                "num_keyframes": int(mi.num_keyframes),
                "active_map_points": int(mi.active_map_points),
                "total_map_points": int(mi.total_map_points),
                "tracking_state": int(mi.tracking_state),
            }
            with open(os.path.join(out_dir, "map_info.json"), "w", encoding="utf-8") as f:
                json.dump(info, f, indent=2)
            export_summary["map_info"] = info
        except Exception:
            export_summary["map_info_error"] = "get_map_info unavailable"
        try:
            traj_iter = list(slam.get_trajectory_points())
            if len(traj_iter) == 0 and len(last_traj_snapshot) > 0:
                traj_iter = last_traj_snapshot
            with open(os.path.join(out_dir, "trajectory.txt"), "w", encoding="utf-8") as f:
                for item in traj_iter:
                    ts = float(item[0])
                    vals = [float(x) for x in item[1].reshape(-1).tolist()]
                    f.write(" ".join([f"{ts:.9f}"] + [f"{v:.9f}" for v in vals]) + "\n")
            export_summary["trajectory_count"] = len(traj_iter)
        except Exception:
            export_summary["trajectory_count"] = -1
        try:
            pts_iter = list(slam.get_tracked_mappoints())
            if len(pts_iter) == 0 and len(last_pts_snapshot) > 0:
                pts_iter = last_pts_snapshot
            with open(os.path.join(out_dir, "tracked_points.xyz"), "w", encoding="utf-8") as f:
                for p in pts_iter:
                    if len(p) >= 3:
                        f.write(f"{float(p[0]):.6f} {float(p[1]):.6f} {float(p[2]):.6f}\n")
            export_summary["tracked_points_count"] = len(pts_iter)
        except Exception:
            export_summary["tracked_points_count"] = -1
        try:
            with open(os.path.join(out_dir, "export_summary.json"), "w", encoding="utf-8") as f:
                json.dump(export_summary, f, indent=2)
        except Exception:
            pass
        if controller_logger is not None:
            controller_logger.stop()
        if controller_reader is not None:
            controller_reader.disconnect()
        pipeline.stop()
        slam.shutdown()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
