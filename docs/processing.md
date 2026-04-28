# Offline Processing Guide

This document describes how to process recorded ROS bags into client-ready datasets using the Python offline pipeline.

## Prerequisites

- Python 3.12+
- `uv` package manager
- System FFmpeg (for H.264 encoding via PyAV)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
source .venv/bin/activate
```

Download ORB vocabulary if not already present:

```bash
curl -L "https://github.com/UZ-SLAMLab/ORB_SLAM3/raw/master/Vocabulary/ORBvoc.txt.tar.gz" \
  -o ./config/ORBvoc.txt.tar.gz
tar -xzf ./config/ORBvoc.txt.tar.gz -C ./config
rm ./config/ORBvoc.txt.tar.gz
```

## CLI Tools

### `umi-inspect` — bag health check

```bash
uv run umi-inspect /path/to/capture.bag --check-topics
```

Reports topic list, message counts, rates, and warns if expected topics are missing.

### `umi-extract` — extract controller + D405 video + episodes (no SLAM)

```bash
uv run umi-extract /path/to/capture.bag --out sessions/my_session/
```

Produces:
- `controller.csv` — calibrated joint angles with bag timestamps
- `d405_color.mp4` — H.264 encoded color video
- `d405_color_frames.csv` — per-frame timestamp index
- `episodes.csv` — episode intervals with status (kept/discarded)
- `session_meta.json` — provenance and statistics

### `umi-slam` — offline ORB-SLAM3 replay

```bash
uv run umi-slam /path/to/capture.bag \
  --vocab ./config/ORBvoc.txt \
  --settings ./config/intel_d455.yaml \
  --out sessions/my_session/
```

Produces:
- `trajectory.txt` — raw ORB-SLAM3 pose dump
- `trajectory.csv` — poses with `t_ros_ns`, `t_iso`, quaternion representation
- `tracked_points.xyz` — 3D map points
- `map_info.json` — keyframe/point counts
- `d455_frames.csv` — per-frame timestamp + IMU count
- `slam_log.txt` — VIBA milestones and tracking events

Options:
- `--stereo-only` — disable IMU fusion
- `--realtime-factor 1.0` — pacing (1.0 = realtime, 0 = unbounded)
- `--max-frames N` — process only first N frames

### `umi-process` — full pipeline (one shot)

```bash
uv run umi-process /path/to/capture.bag \
  --vocab ./config/ORBvoc.txt \
  --settings ./config/intel_d455.yaml \
  --split-episodes \
  --out sessions/my_session/
```

Runs extract + SLAM + assembly in sequence. Produces all of the above plus:
- `aligned_dataset.parquet` — the client deliverable (all episodes, tagged with `episode_id`)
- `aligned_dataset.csv` — CSV mirror of the parquet
- `episodes/episode_001.parquet` — per-episode split (with `--split-episodes`)
- `episodes/episode_001.csv` — per-episode CSV mirror

Options:
- `--split-episodes` — write individual episode files under `episodes/`

The aligned dataset joins trajectory poses with nearest-matched controller angles and D405 frame indices at each trajectory keyframe. Each row includes an `episode_id` column (-1 for samples outside any kept episode).

## Episode-Based Recording

Sessions recorded with the interactive capture node contain episode markers on the `/session/episode` topic. The offline pipeline:

1. **Extracts** episode intervals from `std_msgs/String` markers in the bag.
2. **Tags** each aligned row with the `episode_id` it belongs to.
3. **Optionally splits** into per-episode Parquet/CSV files.

Discarded episodes (marked during recording with `c` during an active episode) are filtered out — their rows receive `episode_id = -1`.

For bags recorded before the episode system was added, all rows receive `episode_id = -1` and no episode files are produced.

## Output Layout

```
sessions/<session_id>/
├── session_meta.json
├── source.bag.sha256
├── trajectory.txt
├── trajectory.csv
├── tracked_points.xyz
├── map_info.json
├── controller.csv
├── d405_color.mp4
├── d405_color_frames.csv
├── d455_frames.csv
├── slam_log.txt
├── episodes.csv
├── aligned_dataset.parquet
├── aligned_dataset.csv
└── episodes/                  (with --split-episodes)
    ├── episode_001.parquet
    ├── episode_001.csv
    ├── episode_002.parquet
    └── episode_002.csv
```

## Master Clock

All output rows share the column prefix `(idx, t_ros_ns, t_iso, episode_id, ...)`:

- `t_ros_ns` — nanosecond timestamp from the ROS bag header (master time)
- `t_iso` — human-readable UTC ISO-8601 derived from `t_ros_ns`
- `episode_id` — which kept episode this row belongs to (-1 if none)

The `session_meta.json` contains provenance anchors that relate bag time to host monotonic and wall clock, enabling post-hoc clock forensics.
