#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""``umi-process`` — one-shot: extract + SLAM + assemble.

Runs the full offline pipeline on a single bag file and produces
a complete session directory ready for client delivery.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from ..bag_reader import BagReader
from ..controllers.calibrate import Calibrator
from ..controllers.can_decode import CanDecoder, JOINT_NAMES
from ..dataset.assemble import assemble
from ..episodes import extract_episodes, kept_episodes, write_episodes_csv
from ..session_meta import (
    SessionMeta,
    StreamStats,
    compute_bag_sha256,
    generate_session_id,
    write_bag_sha256,
)
from ..slam.exporter import export as export_slam
from ..slam.replay import replay_bag
from ..timebase import estimate_rate_hz, ros_ns_to_iso
from ..video.encode import encode_d405_from_messages


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="umi-process",
        description="Full offline pipeline: bag -> extract + SLAM + aligned dataset.",
    )
    ap.add_argument("bag", type=Path, help="Path to the .bag file.")
    ap.add_argument("--out", type=Path, default=None, help="Output session directory.")
    ap.add_argument("--vocab", type=Path, required=True, help="Path to ORBvoc.txt.")
    ap.add_argument("--settings", type=Path, required=True, help="Path to ORB-SLAM3 settings YAML.")
    ap.add_argument(
        "--calibration",
        type=Path,
        default=None,
        help="Path to calibration.csv (default: config/calibration.csv).",
    )
    ap.add_argument("--stereo-only", action="store_true", help="Stereo SLAM without IMU.")
    ap.add_argument(
        "--realtime-factor",
        type=float,
        default=1.0,
        help="SLAM pacing factor (1.0 = realtime, 0 = unbounded). Default 1.0.",
    )
    ap.add_argument("--max-frames", type=int, default=0, help="Limit stereo frames for SLAM (0 = all).")
    ap.add_argument("--skip-sha256", action="store_true", help="Skip bag SHA-256 computation.")
    ap.add_argument(
        "--split-episodes",
        action="store_true",
        help="Write per-episode Parquet/CSV files under episodes/ subdirectory.",
    )
    args = ap.parse_args()

    bag_path: Path = args.bag.expanduser().resolve()
    if not bag_path.exists():
        print(f"Error: bag file not found: {bag_path}", file=sys.stderr)
        return 1

    session_id = generate_session_id(bag_path)
    out_dir: Path = (args.out or Path("sessions") / session_id).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[umi-process] bag:     {bag_path}")
    print(f"[umi-process] session: {session_id}")
    print(f"[umi-process] out:     {out_dir}")
    print()

    meta = SessionMeta(session_id=session_id, bag_path=str(bag_path))

    if not args.skip_sha256:
        print("[umi-process] Computing bag SHA-256 ...")
        sha = compute_bag_sha256(bag_path)
        meta.bag_sha256 = sha
        write_bag_sha256(sha, out_dir)

    # ====== Step 1: Extract controller + D405 + episodes ======
    print("[umi-process] === Step 1: Extract ===")
    episodes = []

    with BagReader(bag_path) as reader:
        meta.bag_start_ns = reader.start_ns
        meta.bag_end_ns = reader.end_ns
        meta.bag_duration_s = reader.duration_s
        available = reader.available_topics()

        # Controller
        if "/hand/can_raw" in available:
            print("[umi-process] Extracting controller from /hand/can_raw ...")
            calibrator = Calibrator(csv_path=args.calibration)
            decoder = CanDecoder()
            ctrl_timestamps: list[int] = []
            ctrl_csv_path = out_dir / "controller.csv"
            with ctrl_csv_path.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(
                    ["idx", "t_ros_ns", "t_iso"]
                    + [f"raw_{i}" for i in range(6)]
                    + list(JOINT_NAMES)
                )
                cidx = 0
                for sm in reader.read_topic("/hand/can_raw"):
                    sample = decoder.feed_can_frame(
                        t_ros_ns=sm.t_ros_ns,
                        arb_id=int(sm.msg.arb_id),
                        dlc=int(sm.msg.dlc),
                        data=sm.msg.data,
                    )
                    if sample is None:
                        continue
                    calibrated = calibrator.map_counts(sample.raw_counts)
                    w.writerow(
                        [cidx, sample.t_ros_ns, ros_ns_to_iso(sample.t_ros_ns)]
                        + [f"{v:.1f}" for v in sample.raw_counts]
                        + [f"{v:.1f}" for v in calibrated]
                    )
                    ctrl_timestamps.append(sample.t_ros_ns)
                    cidx += 1
            meta.streams.append(StreamStats(
                name="controller", message_count=len(ctrl_timestamps),
                first_t_ros_ns=ctrl_timestamps[0] if ctrl_timestamps else None,
                last_t_ros_ns=ctrl_timestamps[-1] if ctrl_timestamps else None,
                rate_hz=estimate_rate_hz(ctrl_timestamps),
                output_file="controller.csv",
            ))
            print(f"[umi-process]   {len(ctrl_timestamps)} samples")
        elif "/hand/joint_states" in available:
            print("[umi-process] Extracting controller from /hand/joint_states (legacy) ...")
            ctrl_timestamps = []
            ctrl_csv_path = out_dir / "controller.csv"
            with ctrl_csv_path.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(
                    ["idx", "t_ros_ns", "t_iso"]
                    + [f"raw_{i}" for i in range(6)]
                    + list(JOINT_NAMES)
                )
                cidx = 0
                for sm in reader.read_topic("/hand/joint_states"):
                    positions = list(sm.msg.positions)
                    w.writerow(
                        [cidx, sm.t_ros_ns, ros_ns_to_iso(sm.t_ros_ns)]
                        + [""] * 6
                        + [f"{v:.1f}" for v in positions]
                    )
                    ctrl_timestamps.append(sm.t_ros_ns)
                    cidx += 1
            meta.streams.append(StreamStats(
                name="controller", message_count=len(ctrl_timestamps),
                first_t_ros_ns=ctrl_timestamps[0] if ctrl_timestamps else None,
                last_t_ros_ns=ctrl_timestamps[-1] if ctrl_timestamps else None,
                rate_hz=estimate_rate_hz(ctrl_timestamps),
                output_file="controller.csv",
            ))
            print(f"[umi-process]   {len(ctrl_timestamps)} samples")
        else:
            print("[umi-process] WARNING: no hand topic found; skipping controller.")

        # D405 Color
        if "/camera_d405/color/image_raw" in available:
            print("[umi-process] Encoding D405 color to H.264 ...")

            def _d405_iter():
                for sm in reader.read_topic("/camera_d405/color/image_raw"):
                    yield sm.t_ros_ns, sm.msg

            _, _, d405_count = encode_d405_from_messages(_d405_iter(), out_dir)
            meta.streams.append(StreamStats(
                name="d405_color", message_count=d405_count, output_file="d405_color.mp4",
            ))
            print(f"[umi-process]   {d405_count} frames")
        else:
            print("[umi-process] WARNING: D405 color topic not found; skipping.")

        # Episodes
        episodes = extract_episodes(reader)
        if episodes:
            write_episodes_csv(episodes, out_dir)
            kept = kept_episodes(episodes)
            discarded = sum(1 for e in episodes if e.status == "discarded")
            print(f"[umi-process] Episodes: {len(kept)} kept, {discarded} discarded")
        else:
            print("[umi-process] No episode markers found (pre-episode bag or warmup-only).")

    # ====== Step 2: SLAM replay ======
    print()
    print("[umi-process] === Step 2: SLAM Replay ===")
    vocab_path = args.vocab.expanduser().resolve()
    settings_path = args.settings.expanduser().resolve()

    result = replay_bag(
        bag_path=bag_path,
        vocab_path=vocab_path,
        settings_path=settings_path,
        stereo_only=args.stereo_only,
        realtime_factor=args.realtime_factor,
        max_frames=args.max_frames,
    )
    print(f"[umi-process] SLAM: {result.total_frames} frames, {len(result.trajectory)} poses")
    slam_summary = export_slam(result, out_dir)
    meta.streams.append(StreamStats(
        name="d455_slam", message_count=result.total_frames, output_file="trajectory.csv",
    ))
    meta.parameters = {
        "slam_mode": result.slam_mode,
        "realtime_factor": args.realtime_factor,
        "vocab": str(vocab_path),
        "settings": str(settings_path),
    }

    # ====== Step 3: Assemble ======
    print()
    print("[umi-process] === Step 3: Assemble ===")
    pq_path, kept_count, dropped = assemble(
        out_dir,
        episodes=episodes,
        split_episodes=args.split_episodes,
    )
    if pq_path:
        print(f"[umi-process] aligned_dataset.parquet: {kept_count} rows")

    meta.write(out_dir)
    print()
    print(f"[umi-process] Done. Session output: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
