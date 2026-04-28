# UMI-Dex

![](.github/assets/connected.png)

**Documentation:** English (this file) · [简体中文](README_zhCN.md) · [Docs index / 文档索引](docs/README.md)

UMI-Dex is an open-source dexterous-hand teleoperation data pipeline for synchronized multi-sensor recording and trajectory analysis.

## Architecture

UMI-Dex uses a **hybrid pipeline**: ROS records synchronized bags, Python processes them offline into client-ready datasets.

- **ROS1 recording pipeline (canonical recorder):** `ros/`
  - Captures D455 stereo IR + IMU, D405 color, and raw CAN hand frames
  - Records synchronized streams into rosbag with a shared ROS clock
  - Provides interactive recording controls (`s/c/r/l/q`)
  - Writes a session provenance sidecar (`<bag>.session.json`)
- **Python 3.12+ offline pipeline:** `src/umi_dex/`
  - `umi-inspect` — bag health check and topic summary
  - `umi-extract` — CAN decode + calibrate to `controller.csv`, D405 to H.264 MP4
  - `umi-slam` — offline ORB-SLAM3 replay producing trajectory + map
  - `umi-process` — full pipeline: extract + SLAM + aligned dataset assembly

## Quick Start

### 1) ROS1 capture setup (recording)

See [ros/README.md](ros/README.md) for Noetic dependencies, catkin workspace setup, launch files, and recording operations.

Operator procedure (IMU warm-up, data collection): [docs/recording_sop.md](docs/recording_sop.md)

### 2) Python offline pipeline (processing)

Prerequisites: Python 3.12+, `uv`, Linux, system FFmpeg.

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

### 3) Process a recorded bag

```bash
# Inspect the bag first
uv run umi-inspect /path/to/capture.bag --check-topics

# Full pipeline: extract + SLAM + aligned dataset
uv run umi-process /path/to/capture.bag \
  --vocab ./config/ORBvoc.txt \
  --settings ./config/intel_d455.yaml \
  --out sessions/my_session/
```

Or run steps individually:

```bash
# Extract only (controller CSV + D405 MP4, no SLAM)
uv run umi-extract /path/to/capture.bag --out sessions/my_session/

# SLAM only
uv run umi-slam /path/to/capture.bag \
  --vocab ./config/ORBvoc.txt \
  --settings ./config/intel_d455.yaml \
  --out sessions/my_session/
```

See [docs/processing.md](docs/processing.md) for full details and output layout.

## Project Layout

- Recorder package: `ros/`
- Python package: `src/umi_dex/`
- Camera/ORB configuration: `config/`
- Session outputs: `sessions/`
- Documentation: `docs/`

## License

- Project code is licensed under [Apache License 2.0](LICENSE).
- Third-party dependencies (including ORB-SLAM3 and `orbslam3-python`) follow their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
- ORB-SLAM3 is GPL-3.0 licensed. If you redistribute binaries or integrated products including ORB-SLAM3 or its bindings, ensure GPL-3.0 compliance.
