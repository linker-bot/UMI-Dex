#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""``umi-inspect`` — quick bag stats and health check."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..bag_reader import BagReader
from ..timebase import ros_ns_to_iso


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="umi-inspect",
        description="Print summary statistics for a ROS1 bag file.",
    )
    ap.add_argument("bag", type=Path, help="Path to the .bag file.")
    ap.add_argument(
        "--check-topics",
        action="store_true",
        help="Warn if expected capture topics are missing.",
    )
    args = ap.parse_args()

    bag_path: Path = args.bag.expanduser().resolve()
    if not bag_path.exists():
        print(f"Error: bag file not found: {bag_path}", file=sys.stderr)
        return 1

    print(f"Bag: {bag_path}")
    print()

    with BagReader(bag_path) as reader:
        summary = reader.summarize()

    print(f"Duration : {summary.duration_s:.2f} s")
    print(f"Start    : {ros_ns_to_iso(summary.start_ns)}")
    print(f"End      : {ros_ns_to_iso(summary.end_ns)}")
    print(f"Messages : {summary.message_count}")
    print()

    name_w = max((len(t.name) for t in summary.topics), default=10)
    type_w = max((len(t.msgtype) for t in summary.topics), default=10)
    hdr = f"  {'Topic':<{name_w}}  {'Type':<{type_w}}  {'Count':>8}  {'Rate':>8}  First / Last"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for t in summary.topics:
        rate_str = f"{t.rate_hz:.1f} Hz" if t.rate_hz else "—"
        first_str = ros_ns_to_iso(t.first_ns) if t.first_ns else "—"
        last_str = ros_ns_to_iso(t.last_ns) if t.last_ns else "—"
        print(
            f"  {t.name:<{name_w}}  {t.msgtype:<{type_w}}  "
            f"{t.count:>8}  {rate_str:>8}  {first_str} / {last_str}"
        )

    if args.check_topics:
        print()
        available = {t.name for t in summary.topics}
        expected = {
            "/camera/infra1/image_rect_raw",
            "/camera/infra2/image_rect_raw",
            "/camera/imu",
            "/camera_d405/color/image_raw",
        }
        can_topics = {"/hand/can_raw", "/hand/joint_states"}
        has_hand = bool(available & can_topics)

        missing = expected - available
        if missing:
            for m in sorted(missing):
                print(f"  WARNING: expected topic missing: {m}")
        if not has_hand:
            print("  WARNING: no hand topic found (/hand/can_raw or /hand/joint_states)")
        if not missing and has_hand:
            print("  All expected capture topics present.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
