#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""``umi-slam`` — offline ORB-SLAM3 replay on a ROS1 bag.

Produces trajectory.txt, trajectory.csv, tracked_points.xyz,
map_info.json, d455_frames.csv, and slam_log.txt.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..session_meta import (
    SessionMeta,
    StreamStats,
    compute_bag_sha256,
    generate_session_id,
    write_bag_sha256,
)
from ..slam.replay import replay_bag
from ..slam.exporter import export


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="umi-slam",
        description="Run offline ORB-SLAM3 on a ROS1 bag (D455 stereo IR + IMU).",
    )
    ap.add_argument("bag", type=Path, help="Path to the .bag file.")
    ap.add_argument("--out", type=Path, default=None, help="Output session directory.")
    ap.add_argument("--vocab", type=Path, required=True, help="Path to ORBvoc.txt.")
    ap.add_argument("--settings", type=Path, required=True, help="Path to ORB-SLAM3 settings YAML.")
    ap.add_argument(
        "--stereo-only",
        action="store_true",
        help="Use stereo SLAM without IMU fusion.",
    )
    ap.add_argument(
        "--realtime-factor",
        type=float,
        default=1.0,
        help="Pacing factor: 1.0 = realtime, 0 = no pacing. Default 1.0.",
    )
    ap.add_argument(
        "--max-frames",
        type=int,
        default=0,
        help="Process at most N stereo frames (0 = all).",
    )
    ap.add_argument(
        "--skip-sha256",
        action="store_true",
        help="Skip computing bag SHA-256.",
    )
    args = ap.parse_args()

    bag_path: Path = args.bag.expanduser().resolve()
    if not bag_path.exists():
        print(f"Error: bag file not found: {bag_path}", file=sys.stderr)
        return 1

    vocab_path: Path = args.vocab.expanduser().resolve()
    if not vocab_path.exists():
        print(f"Error: vocab file not found: {vocab_path}", file=sys.stderr)
        return 1

    settings_path: Path = args.settings.expanduser().resolve()
    if not settings_path.exists():
        print(f"Error: settings file not found: {settings_path}", file=sys.stderr)
        return 1

    session_id = generate_session_id(bag_path)
    out_dir: Path = (args.out or Path("sessions") / session_id).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[umi-slam] bag:      {bag_path}")
    print(f"[umi-slam] session:  {session_id}")
    print(f"[umi-slam] out:      {out_dir}")
    print(f"[umi-slam] mode:     {'stereo_only' if args.stereo_only else 'stereo_inertial'}")
    print(f"[umi-slam] pacing:   {args.realtime_factor}x")
    print()

    print("[umi-slam] Loading bag and running SLAM replay ...")
    result = replay_bag(
        bag_path=bag_path,
        vocab_path=vocab_path,
        settings_path=settings_path,
        stereo_only=args.stereo_only,
        realtime_factor=args.realtime_factor,
        max_frames=args.max_frames,
    )

    print(f"[umi-slam] SLAM complete: {result.total_frames} frames processed")
    print(f"[umi-slam] Trajectory poses: {len(result.trajectory)}")
    print(f"[umi-slam] Tracked points:   {len(result.tracked_points)}")
    print()

    print("[umi-slam] Exporting results ...")
    summary = export(result, out_dir)

    # Write/update session_meta.json
    meta = SessionMeta(session_id=session_id, bag_path=str(bag_path))
    if not args.skip_sha256:
        sha = compute_bag_sha256(bag_path)
        meta.bag_sha256 = sha
        write_bag_sha256(sha, out_dir)

    meta.parameters = {
        "slam_mode": result.slam_mode,
        "realtime_factor": args.realtime_factor,
        "vocab": str(vocab_path),
        "settings": str(settings_path),
    }
    meta.streams.append(StreamStats(
        name="d455_slam",
        message_count=result.total_frames,
        output_file="trajectory.csv",
    ))
    meta.write(out_dir)

    print()
    print(f"[umi-slam] Done. Output: {out_dir}")
    for entry in result.slam_log:
        print(f"  {entry}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
