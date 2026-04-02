#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Visualization utilities for ORB outputs."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def load_trajectory(path: Path) -> np.ndarray:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            vals = [float(x) for x in s.split()]
            if len(vals) < 17:
                continue
            m = np.asarray(vals[1:17], dtype=np.float64).reshape(4, 4)
            rows.append(m[:3, 3])
    if not rows:
        raise RuntimeError(f"No trajectory poses found in {path}")
    return np.asarray(rows, dtype=np.float64)


def load_points(path: Path) -> np.ndarray:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            vals = [float(x) for x in s.split()]
            if len(vals) >= 3:
                rows.append(vals[:3])
    if not rows:
        return np.zeros((0, 3), dtype=np.float64)
    return np.asarray(rows, dtype=np.float64)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--traj", required=True, help="Path to trajectory.txt")
    ap.add_argument("--points", default="", help="Optional path to tracked_points.xyz")
    ap.add_argument("--out_dir", required=True, help="Output directory for PNGs")
    ap.add_argument("--point_stride", type=int, default=1, help="Subsample stride for map points")
    ap.add_argument("--traj_only", action="store_true", help="Plot trajectory only (no map points)")
    args = ap.parse_args()

    traj_path = Path(args.traj).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    traj = load_trajectory(traj_path)

    pts = np.zeros((0, 3), dtype=np.float64)
    if args.points.strip():
        pts_path = Path(args.points).expanduser().resolve()
        pts = load_points(pts_path)
        if args.point_stride > 1 and pts.shape[0] > 0:
            pts = pts[:: args.point_stride]

    fig2d, ax2d = plt.subplots(figsize=(8, 6))
    if (not args.traj_only) and pts.shape[0] > 0:
        ax2d.scatter(pts[:, 0], pts[:, 2], s=2, alpha=0.35, label="map points")
    ax2d.plot(traj[:, 0], traj[:, 2], "r-", linewidth=2.0, label="trajectory")
    ax2d.scatter(traj[0, 0], traj[0, 2], c="g", s=40, label="start")
    ax2d.scatter(traj[-1, 0], traj[-1, 2], c="b", s=40, label="end")
    ax2d.set_xlabel("X (m)")
    ax2d.set_ylabel("Z (m)")
    ax2d.set_title("ORB-SLAM3 Top View (X-Z)")
    ax2d.grid(True, alpha=0.3)
    ax2d.legend(loc="best")
    fig2d.tight_layout()
    fig2d.savefig(out_dir / "traj_top_xz.png", dpi=180)
    plt.close(fig2d)

    fig3d = plt.figure(figsize=(9, 7))
    ax3d = fig3d.add_subplot(111, projection="3d")
    if (not args.traj_only) and pts.shape[0] > 0:
        ax3d.scatter(pts[:, 0], pts[:, 1], pts[:, 2], s=1, alpha=0.2, label="map points")
    ax3d.plot(traj[:, 0], traj[:, 1], traj[:, 2], "r-", linewidth=2.0, label="trajectory")
    ax3d.scatter(traj[0, 0], traj[0, 1], traj[0, 2], c="g", s=40, label="start")
    ax3d.scatter(traj[-1, 0], traj[-1, 1], traj[-1, 2], c="b", s=40, label="end")
    ax3d.set_xlabel("X (m)")
    ax3d.set_ylabel("Y (m)")
    ax3d.set_zlabel("Z (m)")
    ax3d.set_title("ORB-SLAM3 3D Trajectory and Map Points")
    ax3d.legend(loc="best")
    fig3d.tight_layout()
    fig3d.savefig(out_dir / "traj_3d.png", dpi=180)
    plt.close(fig3d)

    print(f"Wrote: {out_dir / 'traj_top_xz.png'}")
    print(f"Wrote: {out_dir / 'traj_3d.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
