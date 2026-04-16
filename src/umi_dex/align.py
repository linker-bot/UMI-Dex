#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Align ORB trajectory outputs with controller samples in time."""

import argparse
import bisect
import csv
from typing import List, Tuple


def _read_trajectory(path: str) -> List[Tuple[float, float, float, float]]:
    rows: List[Tuple[float, float, float, float]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) < 17:
                continue
            t = float(parts[0])
            m = [float(v) for v in parts[1:17]]
            tx, ty, tz = m[3], m[7], m[11]
            rows.append((t, tx, ty, tz))
    return rows


def _read_controller(path: str) -> Tuple[List[float], List[List[str]]]:
    times: List[float] = []
    rows: List[List[str]] = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            t = float(r["t_mono_s"])
            times.append(t)
            rows.append(
                [
                    r["sample_idx"],
                    r["t_mono_s"],
                    r["t_wall_ns"],
                    r["raw_0"],
                    r["raw_1"],
                    r["raw_2"],
                    r["raw_3"],
                    r["raw_4"],
                    r["raw_5"],
                    r["thumb_roll"],
                    r["thumb_pitch"],
                    r["index_pitch"],
                    r["middle_pitch"],
                    r["ring_pitch"],
                    r["pinky_pitch"],
                ]
            )
    return times, rows


def _nearest_index(times: List[float], target: float) -> int:
    pos = bisect.bisect_left(times, target)
    if pos <= 0:
        return 0
    if pos >= len(times):
        return len(times) - 1
    prev_i = pos - 1
    if abs(times[pos] - target) < abs(times[prev_i] - target):
        return pos
    return prev_i


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--traj", required=True, help="Path to trajectory.txt")
    ap.add_argument("--controller", required=True, help="Path to controller_angles.csv")
    ap.add_argument("--out", required=True, help="Output aligned CSV")
    ap.add_argument(
        "--max_dt_s",
        type=float,
        default=0.05,
        help="Max allowed abs time difference for nearest match (seconds).",
    )
    args = ap.parse_args()

    traj = _read_trajectory(args.traj)
    ctrl_times, ctrl_rows = _read_controller(args.controller)
    if not traj:
        raise RuntimeError("No valid trajectory rows found.")
    if not ctrl_times:
        raise RuntimeError("No valid controller rows found.")

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "traj_idx",
                "traj_t_s",
                "traj_tx",
                "traj_ty",
                "traj_tz",
                "ctrl_sample_idx",
                "ctrl_t_mono_s",
                "ctrl_t_wall_ns",
                "ctrl_raw_0",
                "ctrl_raw_1",
                "ctrl_raw_2",
                "ctrl_raw_3",
                "ctrl_raw_4",
                "ctrl_raw_5",
                "ctrl_thumb_roll",
                "ctrl_thumb_pitch",
                "ctrl_index_pitch",
                "ctrl_middle_pitch",
                "ctrl_ring_pitch",
                "ctrl_pinky_pitch",
                "match_abs_dt_s",
            ]
        )

        kept = 0
        dropped = 0
        for i, (t, tx, ty, tz) in enumerate(traj):
            j = _nearest_index(ctrl_times, t)
            dt = abs(ctrl_times[j] - t)
            if dt > args.max_dt_s:
                dropped += 1
                continue
            w.writerow([i, f"{t:.9f}", tx, ty, tz] + ctrl_rows[j] + [f"{dt:.9f}"])
            kept += 1

    print(f"Aligned rows: {kept}, dropped: {dropped}")
    print(f"Saved: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
