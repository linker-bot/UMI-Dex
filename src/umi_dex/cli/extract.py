#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""``umi-extract`` — extract controller CSV + D405 color MP4 from a bag.

No SLAM involved; this is pure data extraction and transcoding.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from ..bag_reader import BagReader
from ..controllers.can_decode import CanDecoder, JOINT_NAMES
from ..controllers.calibrate import Calibrator
from ..episodes import extract_episodes, kept_episodes, write_episodes_csv
from ..session_meta import (
    SessionMeta,
    StreamStats,
    compute_bag_sha256,
    generate_session_id,
    write_bag_sha256,
)
from ..timebase import ros_ns_to_iso, estimate_rate_hz
from ..video.encode import encode_d405_from_messages


def _extract_controller_from_can_raw(
    reader: BagReader,
    calibrator: Calibrator,
    out_dir: Path,
) -> tuple[Path, StreamStats]:
    """Decode /hand/can_raw → controller.csv."""
    csv_path = out_dir / "controller.csv"
    decoder = CanDecoder()
    timestamps: list[int] = []

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            ["idx", "t_ros_ns", "t_iso"]
            + [f"raw_{i}" for i in range(6)]
            + list(JOINT_NAMES)
        )

        idx = 0
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
                [idx, sample.t_ros_ns, ros_ns_to_iso(sample.t_ros_ns)]
                + [f"{v:.1f}" for v in sample.raw_counts]
                + [f"{v:.1f}" for v in calibrated]
            )
            timestamps.append(sample.t_ros_ns)
            idx += 1

    stats = StreamStats(
        name="controller",
        message_count=len(timestamps),
        first_t_ros_ns=timestamps[0] if timestamps else None,
        last_t_ros_ns=timestamps[-1] if timestamps else None,
        rate_hz=estimate_rate_hz(timestamps),
        output_file="controller.csv",
    )
    return csv_path, stats


def _extract_controller_from_joint_states(
    reader: BagReader,
    out_dir: Path,
) -> tuple[Path, StreamStats]:
    """Extract /hand/joint_states (legacy HandJointState) → controller.csv.

    For bags recorded before the raw-CAN switch in Phase 5.
    """
    csv_path = out_dir / "controller.csv"
    timestamps: list[int] = []

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            ["idx", "t_ros_ns", "t_iso"]
            + [f"raw_{i}" for i in range(6)]
            + list(JOINT_NAMES)
        )

        idx = 0
        for sm in reader.read_topic("/hand/joint_states"):
            msg = sm.msg
            positions = list(msg.positions)
            w.writerow(
                [idx, sm.t_ros_ns, ros_ns_to_iso(sm.t_ros_ns)]
                + [""] * 6  # no raw counts in legacy format
                + [f"{v:.1f}" for v in positions]
            )
            timestamps.append(sm.t_ros_ns)
            idx += 1

    stats = StreamStats(
        name="controller",
        message_count=len(timestamps),
        first_t_ros_ns=timestamps[0] if timestamps else None,
        last_t_ros_ns=timestamps[-1] if timestamps else None,
        rate_hz=estimate_rate_hz(timestamps),
        output_file="controller.csv",
    )
    return csv_path, stats


def _extract_d405_color(
    reader: BagReader,
    out_dir: Path,
) -> tuple[Path, Path, StreamStats]:
    """Encode /camera_d405/color/image_raw → d405_color.mp4 + frames CSV."""

    def _msg_iter():
        for sm in reader.read_topic("/camera_d405/color/image_raw"):
            yield sm.t_ros_ns, sm.msg

    mp4_path, csv_path, count = encode_d405_from_messages(_msg_iter(), out_dir)

    timestamps: list[int] = []
    if csv_path.exists():
        with csv_path.open("r", encoding="utf-8") as f:
            rd = csv.DictReader(f)
            for row in rd:
                timestamps.append(int(row["t_ros_ns"]))

    stats = StreamStats(
        name="d405_color",
        message_count=count,
        first_t_ros_ns=timestamps[0] if timestamps else None,
        last_t_ros_ns=timestamps[-1] if timestamps else None,
        rate_hz=estimate_rate_hz(timestamps),
        output_file="d405_color.mp4",
    )
    return mp4_path, csv_path, stats


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="umi-extract",
        description="Extract controller CSV and D405 color MP4 from a ROS1 bag.",
    )
    ap.add_argument("bag", type=Path, help="Path to the .bag file.")
    ap.add_argument("--out", type=Path, default=None, help="Output session directory.")
    ap.add_argument(
        "--calibration",
        type=Path,
        default=None,
        help="Path to calibration.csv (default: config/calibration.csv).",
    )
    ap.add_argument(
        "--skip-sha256",
        action="store_true",
        help="Skip computing bag SHA-256 (faster for large bags).",
    )
    args = ap.parse_args()

    bag_path: Path = args.bag.expanduser().resolve()
    if not bag_path.exists():
        print(f"Error: bag file not found: {bag_path}", file=sys.stderr)
        return 1

    session_id = generate_session_id(bag_path)
    out_dir: Path = (args.out or Path("sessions") / session_id).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[umi-extract] bag:     {bag_path}")
    print(f"[umi-extract] session: {session_id}")
    print(f"[umi-extract] out:     {out_dir}")
    print()

    # Session metadata
    meta = SessionMeta(session_id=session_id, bag_path=str(bag_path))

    if not args.skip_sha256:
        print("[umi-extract] Computing bag SHA-256 ...")
        sha = compute_bag_sha256(bag_path)
        meta.bag_sha256 = sha
        write_bag_sha256(sha, out_dir)
        print(f"[umi-extract] SHA-256: {sha[:16]}...")

    with BagReader(bag_path) as reader:
        meta.bag_start_ns = reader.start_ns
        meta.bag_end_ns = reader.end_ns
        meta.bag_duration_s = reader.duration_s

        available = reader.available_topics()

        # --- Controller ---
        if "/hand/can_raw" in available:
            print("[umi-extract] Extracting controller from /hand/can_raw ...")
            calibrator = Calibrator(csv_path=args.calibration)
            _, ctrl_stats = _extract_controller_from_can_raw(reader, calibrator, out_dir)
            meta.streams.append(ctrl_stats)
            print(f"[umi-extract]   {ctrl_stats.message_count} samples -> controller.csv")
        elif "/hand/joint_states" in available:
            print("[umi-extract] Extracting controller from /hand/joint_states (legacy) ...")
            _, ctrl_stats = _extract_controller_from_joint_states(reader, out_dir)
            meta.streams.append(ctrl_stats)
            print(f"[umi-extract]   {ctrl_stats.message_count} samples -> controller.csv")
        else:
            print("[umi-extract] WARNING: no hand topic found; skipping controller extraction.")

        # --- D405 Color ---
        if "/camera_d405/color/image_raw" in available:
            print("[umi-extract] Encoding D405 color to H.264 ...")
            _, _, d405_stats = _extract_d405_color(reader, out_dir)
            meta.streams.append(d405_stats)
            print(f"[umi-extract]   {d405_stats.message_count} frames -> d405_color.mp4")
        else:
            print("[umi-extract] WARNING: /camera_d405/color/image_raw not found; skipping.")

        # --- Episodes ---
        episodes = extract_episodes(reader)
        if episodes:
            ep_csv = write_episodes_csv(episodes, out_dir)
            kept = kept_episodes(episodes)
            discarded = sum(1 for e in episodes if e.status == "discarded")
            print(f"[umi-extract] Episodes: {len(kept)} kept, {discarded} discarded -> episodes.csv")
        else:
            print("[umi-extract] No episode markers found (pre-episode bag or warmup-only).")

    meta.write(out_dir)
    print()
    print(f"[umi-extract] Done. Output: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
