#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Join trajectory, controller, and D405 frame data into one aligned dataset.

The trajectory (from SLAM) is the anchor: for each trajectory row we
find the nearest controller sample and the nearest D405 color frame,
producing one aligned row per trajectory pose.

When episode information is available, each row is tagged with its
``episode_id`` (-1 for rows outside any kept episode).  The optional
``--split-episodes`` mode writes one Parquet file per kept episode.
"""

from __future__ import annotations

import bisect
import csv
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .schema import ALIGNED_SCHEMA
from ..controllers.can_decode import JOINT_NAMES
from ..episodes import EpisodeInterval, episode_id_for_timestamp, kept_episodes


def _nearest_index(sorted_ts: list[int], target: int) -> int:
    """Return the index in *sorted_ts* closest to *target*."""
    pos = bisect.bisect_left(sorted_ts, target)
    if pos <= 0:
        return 0
    if pos >= len(sorted_ts):
        return len(sorted_ts) - 1
    if abs(sorted_ts[pos] - target) < abs(sorted_ts[pos - 1] - target):
        return pos
    return pos - 1


def _load_csv_timestamps(csv_path: Path, col: str = "t_ros_ns") -> tuple[list[int], list[dict]]:
    """Load a CSV and return (timestamp list, list of row dicts)."""
    timestamps: list[int] = []
    rows: list[dict] = []
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = int(row[col])
            timestamps.append(ts)
            rows.append(row)
    return timestamps, rows


def _build_aligned_rows(
    traj_ts: list[int],
    traj_rows: list[dict],
    ctrl_ts: list[int],
    ctrl_rows: list[dict],
    d405_ts: list[int],
    d405_rows: list[dict],
    episodes: list[EpisodeInterval],
    max_ctrl_dt_ns: int,
    max_d405_dt_ns: int,
) -> list[dict]:
    """Produce aligned rows from trajectory + nearest controller/D405."""
    has_ctrl = bool(ctrl_ts)
    has_d405 = bool(d405_ts)
    kept = kept_episodes(episodes) if episodes else []

    aligned: list[dict] = []

    for i, trow in enumerate(traj_rows):
        t_ns = int(trow["t_ros_ns"])
        out_row: dict = {
            "idx": i,
            "t_ros_ns": t_ns,
            "t_iso": trow.get("t_iso", ""),
            "episode_id": episode_id_for_timestamp(t_ns, kept) if kept else -1,
            "tx": float(trow["tx"]),
            "ty": float(trow["ty"]),
            "tz": float(trow["tz"]),
            "qw": float(trow["qw"]),
            "qx": float(trow["qx"]),
            "qy": float(trow["qy"]),
            "qz": float(trow["qz"]),
        }

        # --- Controller nearest match ---
        if has_ctrl:
            cj = _nearest_index(ctrl_ts, t_ns)
            c_dt = abs(ctrl_ts[cj] - t_ns)
            if c_dt <= max_ctrl_dt_ns:
                crow = ctrl_rows[cj]
                out_row["ctrl_t_ros_ns"] = ctrl_ts[cj]
                out_row["ctrl_dt_ns"] = c_dt
                for k in range(6):
                    val = crow.get(f"raw_{k}", "")
                    out_row[f"raw_{k}"] = float(val) if val else np.nan
                for name in JOINT_NAMES:
                    val = crow.get(name, "")
                    out_row[name] = float(val) if val else np.nan
            else:
                out_row["ctrl_t_ros_ns"] = 0
                out_row["ctrl_dt_ns"] = c_dt
                for k in range(6):
                    out_row[f"raw_{k}"] = np.nan
                for name in JOINT_NAMES:
                    out_row[name] = np.nan
        else:
            out_row["ctrl_t_ros_ns"] = 0
            out_row["ctrl_dt_ns"] = 0
            for k in range(6):
                out_row[f"raw_{k}"] = np.nan
            for name in JOINT_NAMES:
                out_row[name] = np.nan

        # --- D405 nearest match ---
        if has_d405:
            dj = _nearest_index(d405_ts, t_ns)
            d_dt = abs(d405_ts[dj] - t_ns)
            if d_dt <= max_d405_dt_ns:
                drow = d405_rows[dj]
                out_row["d405_frame_idx"] = int(drow["idx"])
                out_row["d405_t_ros_ns"] = d405_ts[dj]
                out_row["d405_dt_ns"] = d_dt
            else:
                out_row["d405_frame_idx"] = -1
                out_row["d405_t_ros_ns"] = 0
                out_row["d405_dt_ns"] = d_dt
        else:
            out_row["d405_frame_idx"] = -1
            out_row["d405_t_ros_ns"] = 0
            out_row["d405_dt_ns"] = 0

        aligned.append(out_row)

    return aligned


def assemble(
    out_dir: Path,
    *,
    episodes: Optional[list[EpisodeInterval]] = None,
    split_episodes: bool = False,
    max_ctrl_dt_ns: int = 50_000_000,    # 50 ms
    max_d405_dt_ns: int = 50_000_000,    # 50 ms
    write_csv_mirror: bool = True,
) -> tuple[Optional[Path], int, int]:
    """Build the aligned dataset from per-stream CSVs in *out_dir*.

    If *split_episodes* is True and episode data is available, one
    Parquet + CSV per kept episode is written under ``out_dir/episodes/``.

    Returns (parquet_path, kept_count, dropped_count).
    """
    traj_csv = out_dir / "trajectory.csv"
    ctrl_csv = out_dir / "controller.csv"
    d405_csv = out_dir / "d405_color_frames.csv"

    if not traj_csv.exists():
        print("[assemble] trajectory.csv not found; cannot assemble.")
        return None, 0, 0

    traj_ts, traj_rows = _load_csv_timestamps(traj_csv)

    ctrl_ts: list[int] = []
    ctrl_rows: list[dict] = []
    if ctrl_csv.exists():
        ctrl_ts, ctrl_rows = _load_csv_timestamps(ctrl_csv)

    d405_ts: list[int] = []
    d405_rows: list[dict] = []
    if d405_csv.exists():
        d405_ts, d405_rows = _load_csv_timestamps(d405_csv)

    ep_list = episodes or []

    aligned_rows = _build_aligned_rows(
        traj_ts, traj_rows,
        ctrl_ts, ctrl_rows,
        d405_ts, d405_rows,
        ep_list,
        max_ctrl_dt_ns, max_d405_dt_ns,
    )

    kept_count = len(aligned_rows)
    dropped = 0

    if not aligned_rows:
        print("[assemble] No aligned rows produced.")
        return None, 0, dropped

    df = pd.DataFrame(aligned_rows)
    table = pa.Table.from_pandas(df, schema=ALIGNED_SCHEMA, preserve_index=False)

    parquet_path = out_dir / "aligned_dataset.parquet"
    pq.write_table(table, parquet_path)

    if write_csv_mirror:
        csv_mirror = out_dir / "aligned_dataset.csv"
        df.to_csv(csv_mirror, index=False)

    print(f"[assemble] {kept_count} aligned rows written, {dropped} dropped")

    # --- Per-episode split ---
    if split_episodes and ep_list:
        kept_ep = kept_episodes(ep_list)
        if kept_ep:
            ep_dir = out_dir / "episodes"
            ep_dir.mkdir(exist_ok=True)
            for ep in kept_ep:
                ep_df = df[df["episode_id"] == ep.episode_id].copy()
                if ep_df.empty:
                    continue
                ep_df = ep_df.reset_index(drop=True)
                ep_df["idx"] = range(len(ep_df))

                ep_table = pa.Table.from_pandas(
                    ep_df, schema=ALIGNED_SCHEMA, preserve_index=False,
                )
                ep_pq = ep_dir / f"episode_{ep.episode_id:03d}.parquet"
                pq.write_table(ep_table, ep_pq)
                if write_csv_mirror:
                    ep_df.to_csv(
                        ep_dir / f"episode_{ep.episode_id:03d}.csv", index=False,
                    )
                print(f"[assemble]   episode {ep.episode_id}: {len(ep_df)} rows -> {ep_pq.name}")

    return parquet_path, kept_count, dropped
