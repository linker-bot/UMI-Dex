# UMI-Dex

![](.github/assets/connected.png)

**Documentation:** English (this file) · [简体中文](README_zhCN.md) · [Docs index / 文档索引](docs/README.md)

UMI-Dex is an open-source dexterous-hand teleoperation data pipeline for synchronized multi-sensor recording and trajectory analysis.

## Architecture

UMI-Dex is split into two clear layers:

- **ROS1 recording pipeline (canonical recorder):** `ros/`
  - Captures D455 stereo IR + IMU, D405 color, and CAN hand joint states
  - Records synchronized streams into rosbag with a shared ROS clock
  - Provides interactive recording controls (`s/c/r/l/q`)
- **Python ORB-SLAM3 utilities (analysis and tooling):** `src/umi_dex/`
  - ORB runtime/debug command: `orb-run`
  - Trajectory visualization: `visualize-trajectory`
  - Trajectory/controller alignment: `align-trajectory`

## Quick Start

### 1) ROS1 capture setup (recommended for recording)

Use the ROS-specific guide:

- [ros/README.md](ros/README.md)

It includes Noetic dependencies, catkin workspace setup, launch files, and recording operations.

### 2) Python utilities setup (ORB + visualization + alignment)

Prerequisites:

- Python 3.12+
- `uv`
- Linux is recommended for `orbslam3-python` wheel compatibility

Install:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
source .venv/bin/activate
```

If `config/ORBvoc.txt` is missing, download it once:

```bash
curl -L "https://github.com/UZ-SLAMLab/ORB_SLAM3/raw/master/Vocabulary/ORBvoc.txt.tar.gz" -o ./config/ORBvoc.txt.tar.gz
tar -xzf ./config/ORBvoc.txt.tar.gz -C ./config
rm ./config/ORBvoc.txt.tar.gz
```

## Python Utility Commands

Trajectory visualization:

```bash
MPLCONFIGDIR="$(pwd)/.mplcache" uv run visualize-trajectory \
  --traj ./outputs/realtime_map/trajectory.txt \
  --points ./outputs/realtime_map/tracked_points.xyz \
  --out_dir ./outputs/realtime_map/plots \
  --traj_only
```

Trajectory/controller alignment:

```bash
uv run align-trajectory \
  --traj ./outputs/realtime_map/trajectory.txt \
  --controller ./outputs/realtime_map/controller_angles.csv \
  --out ./outputs/realtime_map/trajectory_controller_aligned.csv
```

ORB runtime/debug:

```bash
uv run orb-run \
  --vocab ./config/ORBvoc.txt \
  --settings ./config/intel_d455.yaml \
  --out_dir ./outputs/realtime_map \
  --controller_channel can0 \
  --controller_bustype socketcan
```

## Notes

- Recording is ROS1-first; Python commands are utilities and debug tooling.
- Controller capture uses SocketCAN (`can0` by default).
- If `orbslam3` import fails, run `uv sync` again in the project root.
- In restricted environments, set `MPLCONFIGDIR="$(pwd)/.mplcache"` for plotting.

## Project Layout

- Recorder package: `ros/`
- Python package: `src/umi_dex/`
- Visualization CLI script (repo convenience entry): `script/visualize_trajectory.py`
- Camera/ORB configuration: `config/`
- Runtime outputs: `outputs/`, `recordings/`

## Sample Data

Public sample data will be released after data quality validation milestones are met.

## License

- Project code is licensed under [Apache License 2.0](LICENSE).
- Third-party dependencies (including ORB-SLAM3 and `orbslam3-python`) follow their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
- ORB-SLAM3 is GPL-3.0 licensed. If you redistribute binaries or integrated products including ORB-SLAM3 or its bindings, ensure GPL-3.0 compliance.
