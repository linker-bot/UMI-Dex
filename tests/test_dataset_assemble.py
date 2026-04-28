"""Tests for umi_dex.dataset.assemble."""

import csv
from pathlib import Path

import pandas as pd

from umi_dex.dataset.assemble import _nearest_index, assemble
from umi_dex.episodes import EpisodeInterval


def test_nearest_index():
    ts = [100, 200, 300, 400, 500]
    assert _nearest_index(ts, 100) == 0
    assert _nearest_index(ts, 250) == 1  # 200 is nearer than 300
    assert _nearest_index(ts, 260) == 2  # 300 is nearer than 200
    assert _nearest_index(ts, 500) == 4
    assert _nearest_index(ts, 50) == 0
    assert _nearest_index(ts, 600) == 4


def _write_trajectory_csv(path: Path, rows: list[dict]):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["idx", "t_ros_ns", "t_iso", "tx", "ty", "tz", "qw", "qx", "qy", "qz"])
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _write_controller_csv(path: Path, rows: list[dict]):
    fieldnames = ["idx", "t_ros_ns", "t_iso"] + [f"raw_{i}" for i in range(6)] + [
        "thumb_roll", "thumb_pitch", "index_pitch", "middle_pitch", "ring_pitch", "pinky_pitch"
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def test_assemble_basic(tmp_path: Path):
    _write_trajectory_csv(tmp_path / "trajectory.csv", [
        {"idx": 0, "t_ros_ns": 1000, "t_iso": "", "tx": 1.0, "ty": 2.0, "tz": 3.0, "qw": 1.0, "qx": 0, "qy": 0, "qz": 0},
        {"idx": 1, "t_ros_ns": 2000, "t_iso": "", "tx": 2.0, "ty": 3.0, "tz": 4.0, "qw": 1.0, "qx": 0, "qy": 0, "qz": 0},
    ])

    ctrl_row = {"idx": 0, "t_ros_ns": 1500, "t_iso": ""}
    for i in range(6):
        ctrl_row[f"raw_{i}"] = "0.0"
    for name in ["thumb_roll", "thumb_pitch", "index_pitch", "middle_pitch", "ring_pitch", "pinky_pitch"]:
        ctrl_row[name] = "50.0"
    _write_controller_csv(tmp_path / "controller.csv", [ctrl_row])

    pq_path, kept, dropped = assemble(tmp_path, write_csv_mirror=True)
    assert pq_path is not None
    assert pq_path.exists()
    assert kept == 2
    assert (tmp_path / "aligned_dataset.csv").exists()

    df = pd.read_csv(tmp_path / "aligned_dataset.csv")
    assert "episode_id" in df.columns
    assert (df["episode_id"] == -1).all()


def test_assemble_with_episodes(tmp_path: Path):
    _write_trajectory_csv(tmp_path / "trajectory.csv", [
        {"idx": 0, "t_ros_ns": 100, "t_iso": "", "tx": 0, "ty": 0, "tz": 0, "qw": 1, "qx": 0, "qy": 0, "qz": 0},
        {"idx": 1, "t_ros_ns": 200, "t_iso": "", "tx": 1, "ty": 0, "tz": 0, "qw": 1, "qx": 0, "qy": 0, "qz": 0},
        {"idx": 2, "t_ros_ns": 400, "t_iso": "", "tx": 2, "ty": 0, "tz": 0, "qw": 1, "qx": 0, "qy": 0, "qz": 0},
    ])

    episodes = [
        EpisodeInterval(1, start_ns=50, end_ns=250, status="kept"),
        EpisodeInterval(2, start_ns=350, end_ns=450, status="discarded"),
    ]

    pq_path, kept, dropped = assemble(
        tmp_path, episodes=episodes, split_episodes=True, write_csv_mirror=True,
    )
    assert pq_path is not None
    assert kept == 3

    df = pd.read_csv(tmp_path / "aligned_dataset.csv")
    assert list(df["episode_id"]) == [1, 1, -1]

    ep_dir = tmp_path / "episodes"
    assert (ep_dir / "episode_001.parquet").exists()
    assert (ep_dir / "episode_001.csv").exists()
    ep_df = pd.read_csv(ep_dir / "episode_001.csv")
    assert len(ep_df) == 2
    assert (ep_df["episode_id"] == 1).all()


def test_assemble_no_trajectory(tmp_path: Path):
    pq_path, kept, dropped = assemble(tmp_path)
    assert pq_path is None
    assert kept == 0
