#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Record RealSense stereo IR images + raw IMU streams."""

from __future__ import annotations

import argparse
import csv
import signal
import time
from pathlib import Path

import cv2
import numpy as np
import pyrealsense2 as rs


def _mkdir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _timestamp_ns_from_frame(frame: rs.frame) -> int:
    t_ms = float(frame.get_timestamp())
    return int(round(t_ms * 1e6))


def _write_streams_meta(meta_dir: Path, profile: rs.pipeline_profile) -> None:
    lines = []
    for s in profile.get_streams():
        try:
            vsp = s.as_video_stream_profile()
            intr = vsp.get_intrinsics()
            lines.append(
                f"{s.stream_name()} {s.stream_type()} idx={s.stream_index()} "
                f"{intr.width}x{intr.height} fps={s.fps()} format={s.format()}"
            )
        except Exception:
            lines.append(
                f"{s.stream_name()} {s.stream_type()} idx={s.stream_index()} fps={s.fps()} format={s.format()}"
            )
    (meta_dir / "streams.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="Output directory (will be created).")
    ap.add_argument("--width", type=int, default=848)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--ir_format", choices=["UYVY", "Y8"], default="Y8")
    ap.add_argument("--gyro_fps", type=int, default=200)
    ap.add_argument("--accel_fps", type=int, default=200)
    ap.add_argument("--max_seconds", type=float, default=0.0, help="0 = until Ctrl+C.")
    ap.add_argument("--disable_emitter", action="store_true", default=True)
    ap.add_argument("--enable_motion_correction", action="store_true", default=False)
    ap.add_argument("--verbose", action="store_true", default=False)
    args = ap.parse_args()

    out_dir = Path(args.out).expanduser().resolve()
    cam0_dir = out_dir / "cam0"
    cam1_dir = out_dir / "cam1"
    imu_dir = out_dir / "imu"
    meta_dir = out_dir / "meta"
    _mkdir(cam0_dir)
    _mkdir(cam1_dir)
    _mkdir(imu_dir)
    _mkdir(meta_dir)

    accel_path = imu_dir / "accel.csv"
    gyro_path = imu_dir / "gyro.csv"
    stop = False

    def _sigint(_signum, _frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _sigint)

    pipeline = rs.pipeline()
    ir_fmt = rs.format.uyvy if args.ir_format.upper() == "UYVY" else rs.format.y8
    request_variants = [
        {"gyro_fps": args.gyro_fps, "accel_fps": args.accel_fps},
        {"gyro_fps": 400, "accel_fps": 200},
        {"gyro_fps": 200, "accel_fps": 100},
    ]
    profile = None
    last_err = None
    for variant in request_variants:
        cfg = rs.config()
        cfg.enable_stream(rs.stream.infrared, 1, args.width, args.height, ir_fmt, args.fps)
        cfg.enable_stream(rs.stream.infrared, 2, args.width, args.height, ir_fmt, args.fps)
        cfg.enable_stream(rs.stream.gyro, rs.format.motion_xyz32f, int(variant["gyro_fps"]))
        cfg.enable_stream(rs.stream.accel, rs.format.motion_xyz32f, int(variant["accel_fps"]))
        try:
            pw = rs.pipeline_wrapper(pipeline)
            cfg.resolve(pw)
            q = rs.frame_queue(1024)

            def cb(frame):
                try:
                    q.enqueue(frame)
                except Exception:
                    pass

            profile = pipeline.start(cfg, cb)
            break
        except Exception as e:
            last_err = e
            try:
                pipeline.stop()
            except Exception:
                pass
            continue

    if profile is None:
        raise RuntimeError(f"Couldn't resolve requests (all variants). Last error: {last_err!r}")
    _write_streams_meta(meta_dir, profile)

    try:
        dev = profile.get_device()
        for sensor in dev.query_sensors():
            if sensor.supports(rs.option.emitter_enabled) and args.disable_emitter:
                sensor.set_option(rs.option.emitter_enabled, 0.0)
            if sensor.supports(rs.option.enable_motion_correction):
                sensor.set_option(
                    rs.option.enable_motion_correction,
                    1.0 if args.enable_motion_correction else 0.0,
                )
    except Exception:
        pass

    accel_f = open(accel_path, "w", newline="", encoding="utf-8")
    gyro_f = open(gyro_path, "w", newline="", encoding="utf-8")
    accel_w = csv.writer(accel_f)
    gyro_w = csv.writer(gyro_f)
    accel_w.writerow(["t_ns", "ax", "ay", "az"])
    gyro_w.writerow(["t_ns", "gx", "gy", "gz"])

    img_count = 0
    accel_count = 0
    gyro_count = 0
    last_print = time.time()
    t0 = time.time()

    try:
        while not stop:
            if args.max_seconds > 0 and (time.time() - t0) >= args.max_seconds:
                break
            try:
                frame = q.wait_for_frame(500)
            except Exception:
                continue

            if frame.is_frameset():
                fs = frame.as_frameset()
                f0 = fs.get_infrared_frame(1)
                f1 = fs.get_infrared_frame(2)
                if not f0 or not f1:
                    continue
                t_ns = _timestamp_ns_from_frame(f0)
                im0 = np.asanyarray(f0.get_data())
                im1 = np.asanyarray(f1.get_data())
                if args.ir_format.upper() == "UYVY":
                    im0 = cv2.cvtColor(im0, cv2.COLOR_YUV2GRAY_UYVY)
                    im1 = cv2.cvtColor(im1, cv2.COLOR_YUV2GRAY_UYVY)
                cv2.imwrite(str(cam0_dir / f"{t_ns}.png"), im0)
                cv2.imwrite(str(cam1_dir / f"{t_ns}.png"), im1)
                img_count += 1
            elif frame.is_motion_frame():
                m = frame.as_motion_frame()
                md = m.get_motion_data()
                mt_ns = _timestamp_ns_from_frame(m)
                if m.get_profile().stream_type() == rs.stream.gyro:
                    gyro_w.writerow([mt_ns, md.x, md.y, md.z])
                    gyro_count += 1
                elif m.get_profile().stream_type() == rs.stream.accel:
                    accel_w.writerow([mt_ns, md.x, md.y, md.z])
                    accel_count += 1

            if args.verbose and (time.time() - last_print) > 1.0:
                last_print = time.time()
                print(f"imgs={img_count} gyro={gyro_count} accel={accel_count}")
    finally:
        pipeline.stop()
        accel_f.close()
        gyro_f.close()

    print(f"Saved: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
