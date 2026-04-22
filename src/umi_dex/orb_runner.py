#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
#主程序：SLAM + 相机 + 手套采集+imu 稳定版本
"""Realtime ORB-SLAM3 runner."""

import argparse
import csv
import json
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone
import cv2
import numpy as np
import orbslam3
import pyrealsense2 as rs

try:
    from .controller_capture import ControllerCaptureLogger, ControllerReader
except ImportError:
    # Running as `python path/to/orb_runner.py`: add `src` so the package resolves.
    import sys
    from pathlib import Path

    _src = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(_src))
    from umi_dex.controller_capture import ControllerCaptureLogger, ControllerReader

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


def _enable_global_time_rs_devices() -> None:
    """Align camera + IMU timestamps (best effort) before streaming."""
    try:
        ctx = rs.context()
        for dev in ctx.query_devices():
            for sensor in dev.query_sensors():
                if sensor.supports(rs.option.global_time_enabled):
                    sensor.set_option(rs.option.global_time_enabled, 1.0)
    except Exception:
        pass


def _apply_ir_emitter(profile: rs.pipeline_profile, enabled: bool) -> None:
    """Enable or disable the RealSense IR dot projector (structured light)."""
    try:
        dev = profile.get_device()
        val = 1.0 if enabled else 0.0
        for sensor in dev.query_sensors():
            if sensor.supports(rs.option.emitter_enabled):
                sensor.set_option(rs.option.emitter_enabled, val)
        print("[RealSense] IR projector", "ON" if enabled else "OFF")
    except Exception as e:
        print("[RealSense] failed to set IR emitter:", e)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Realtime ORB-SLAM3 stereo-inertial runner with optional controller capture."
    )
    ap.add_argument("--vocab", required=True)#ORB-SLAM3 词典
    ap.add_argument("--settings", required=True)#ORB-SLAM3 设置
    ap.add_argument("--width", type=int, default=848)
    ap.add_argument("--height", type=int, default=480)#RealSense D455 高度
    ap.add_argument("--fps", type=int, default=30)#RealSense D455 帧率
    ap.add_argument("--gyro_fps", type=int, default=200)
    ap.add_argument("--accel_fps", type=int, default=200)#RealSense D455 加速度计帧率
    ap.add_argument("--max_seconds", type=float, default=0.0, help="0 means run until Ctrl+C")#最大运行时间  
    ap.add_argument("--out_dir", default="./outputs/realtime_map")
    ap.add_argument("--controller_port", default="/dev/l6encoder_usb")#控制器端口
    ap.add_argument("--controller_baudrate", type=int, default=115200)#控制器波特率
    ap.add_argument("--controller_timeout", type=float, default=0.1)
    ap.add_argument("--controller_filter_alpha", type=float, default=0.3)#控制器滤波器alpha
    ap.add_argument("--controller_disable_filter", action="store_true")#控制器滤波器禁用
    ap.add_argument("--controller_required", action="store_true")#控制器必选
    ap.add_argument("--disable_controller_capture", action="store_true")#控制器捕获禁用
    ap.add_argument(
        "--stereo_only",
        action="store_true",
        help="Use stereo SLAM without IMU (Sensor.STEREO + process_stereo_enhanced). "
        "Use when IMU init fails or you want to avoid Stereo-Inertial resets.",
    )
    ap.add_argument(
        "--ir_emitter",
        action="store_true",
        help="Start with IR projector on. Press 'i' in an OpenCV preview window to toggle while running.",
    )
    args = ap.parse_args()
    out_dir = os.path.normpath(args.out_dir.strip())
    os.makedirs(out_dir, exist_ok=True)

    session_start_wall_ns = time.time_ns()#会话开始时间 真实世界时间
    session_start_mono_s = time.perf_counter()#会话开始时间 单调时间（不考虑时间偏移）
   
    run_clock_info_path = os.path.join(out_dir, "run_clock_info.csv")#运行时钟信息 
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
            port=args.controller_port,
            baudrate=args.controller_baudrate,
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
            msg = f"[controller] failed to connect on {args.controller_port}"
            if args.controller_required:
                raise RuntimeError(msg)
            print(msg + " (continuing without controller logging)")
            controller_enabled = False

    if args.stereo_only:
        slam = orbslam3.System(args.vocab, args.settings, orbslam3.Sensor.STEREO)
        print("[orb_runner] mode: stereo-only (no IMU fusion)")
    else:
        slam = orbslam3.System(args.vocab, args.settings, orbslam3.Sensor.IMU_STEREO)
        print("[orb_runner] mode: stereo-inertial")
    slam.initialize()#初始化 SLAM

    pipeline = rs.pipeline()
    cfg = rs.config()
    cfg.enable_stream(rs.stream.infrared, 1, args.width, args.height, rs.format.y8, args.fps)
    cfg.enable_stream(rs.stream.infrared, 2, args.width, args.height, rs.format.y8, args.fps)
    if not args.stereo_only:
        cfg.enable_stream(rs.stream.gyro, rs.format.motion_xyz32f, args.gyro_fps)#开启陀螺仪
        cfg.enable_stream(rs.stream.accel, rs.format.motion_xyz32f, args.accel_fps)#开启加速度计

    imu_lock = threading.Lock()
    imu_buf = deque(maxlen=20000)
    last_acc = None
    q = rs.frame_queue(4096)
#回调函数cb会在RealSense相机每产生一帧数据时被自动调用
    def cb(frame: rs.frame) -> None:
        nonlocal last_acc
        if frame.is_motion_frame():
            if not args.stereo_only:
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
            return
        try:
            q.enqueue(frame)
        except Exception:
            pass
    # Align timestamps before start so IMU and IR share one clock domain.
    _enable_global_time_rs_devices()
    #启动 RealSense 并检查当前启用的相机流参数
    profile = pipeline.start(cfg, cb)
    ir_emitter_enabled = bool(args.ir_emitter)
    _apply_ir_emitter(profile, ir_emitter_enabled)
    print("[orb_runner] Press 'i' in the left/right OpenCV window to toggle IR projector.")
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
    #开启“全局时间同步”（核心）
    try:
        dev = profile.get_device()
        for sensor in dev.query_sensors():
            if sensor.supports(rs.option.global_time_enabled):
                sensor.set_option(rs.option.global_time_enabled, 1.0)#开启全局时间
    except Exception:
        pass
    #“实时 SLAM 运行（双目 或 双目+IMU）+ 数据记录”
    t0 = time.time() #开始时间
    prev_tl_abs: float | None = None  # previous left-IR timestamp (s), for IMU interval
    last_orb_imu_row: tuple[float, float, float, float, float, float, float] | None = None
    frame_idx = 0 #帧索引
    t_base = None #时间基线
    last_stats_print = time.time() #最后统计时间
    last_traj_snapshot = [] #最后轨迹快照
    last_pts_snapshot = [] #最后地图点快照

    if not args.stereo_only:
        print("[orb_runner] Filling IMU ring buffer (discard a few camera frames)...")
        _warm_deadline = time.perf_counter() + 3.0
        while time.perf_counter() < _warm_deadline:
            with imu_lock:
                if len(imu_buf) >= 80:
                    break
            try:
                q.wait_for_frame(200)
            except RuntimeError:
                continue
            # Drain framesets only; IMU still arrives via callback.

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
            cv2.imshow("left", iml)
            cv2.imshow("right", imr)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("i"), ord("I")):
                ir_emitter_enabled = not ir_emitter_enabled
                _apply_ir_emitter(profile, ir_emitter_enabled)
            if frame_idx % 30 == 0:  # 每30帧保存一张
                cv2.imwrite(f"{out_dir}/left_{frame_idx}.png", iml)
                cv2.imwrite(f"{out_dir}/right_{frame_idx}.png", imr)
            if args.stereo_only:
                slam.process_stereo_enhanced(iml, imr, tl)
                imu_n = 0
            else:
                # ORB-SLAM3 expects IMU samples in (prev image time, current image time],
                # not the entire deque every frame (that duplicates integration and can NaN).
                frame_imu = []
                with imu_lock:
                    # 调试信息：看看队列里到底有没有数据，时间差多少
                    # if len(imu_buf) > 0:
                    #     # print(f"Cam Time: {tl_abs:.3f}, IMU Time: {imu_buf[0][0]:.3f}, Diff: {imu_buf[0][0] - tl_abs:.3f}")
                    # else:
                        # print("IMU buffer is totally empty!")
                    
                    # 1. 丢弃比上一帧相机时间还要早的陈旧 IMU 数据
                    if prev_tl_abs is not None:
                        while imu_buf and imu_buf[0][0] < prev_tl_abs:
                            imu_buf.popleft()
                    
                    # 2. 收集从 prev_cam_t 到 current_cam_t 之间的 IMU 数据
                    # 增加 5ms (0.005s) 的宽容度，防止 RealSense 硬件时间轻微错位
                    while imu_buf and imu_buf[0][0] <= (tl_abs + 0.005):
                        t_s, gx, gy, gz, ax, ay, az = imu_buf.popleft()
                        
                        # 确保传给 SLAM 的相对时间戳也是 秒
                        ts_rel = t_s - t_base if t_base is not None else t_s
                        
                        # 直接传入原始轴向数据
                        frame_imu.append((ax, ay, az, gx, gy, gz, ts_rel))
                
                # 防御性编程：如果真的没有提取到数据，强制塞入上一帧数据避免崩溃
                if not frame_imu:
                    print("WARNING: Empty IMU buffer for this frame! Generating dummy data.")
                    ts_rel = tl_abs - t_base if t_base is not None else tl_abs
                    if last_orb_imu_row is not None:
                        ax, ay, az, gx, gy, gz, _ = last_orb_imu_row
                        frame_imu.append((ax, ay, az, gx, gy, gz, ts_rel))
                    else:
                        frame_imu.append((0.0, 9.81, 0.0, 0.0, 0.0, 0.0, ts_rel))

                slam.process_stereo_inertial_enhanced(iml, imr, tl, frame_imu)
                
                prev_tl_abs = tl_abs
                last_orb_imu_row = frame_imu[-1]
                imu_n = len(frame_imu)
            t_mono = time.perf_counter() - session_start_mono_s
            frame_times_w.writerow([frame_idx, f"{tl:.9f}", f"{t_mono:.9f}", time.time_ns(), imu_n])

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
            frame_idx += 1
    except KeyboardInterrupt:
        pass
    finally:
        try:
            frame_times_f.close()
        except Exception:
            pass
        export_summary = {
            "out_dir": out_dir,
            "slam_mode": "stereo_only" if args.stereo_only else "stereo_inertial",
            "ir_emitter": ir_emitter_enabled,
        }
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
            mi = slam.get_map_info()#获取地图信息
            info = {
                "num_keyframes": int(mi.num_keyframes), #关键帧数量
                "active_map_points": int(mi.active_map_points),#当前参与优化的点
                "total_map_points": int(mi.total_map_points),#总地图点
                "tracking_state": int(mi.tracking_state),#跟踪状态
            }
            with open(os.path.join(out_dir, "map_info.json"), "w", encoding="utf-8") as f:
                json.dump(info, f, indent=2)
            export_summary["map_info"] = info
        except Exception:
            export_summary["map_info_error"] = "get_map_info unavailable"
        try:
            traj_iter = list(slam.get_trajectory_points())#获取轨迹
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
