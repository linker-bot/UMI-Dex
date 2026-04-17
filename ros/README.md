# umi_dex — ROS1 Capture Package

ROS Noetic (Python) package for synchronized data capture from:

- **Intel D455** — stereo IR (848x480 @ 30 fps) + IMU (gyro/accel @ 200 Hz)
- **Intel D405** — color stream + camera info
- **CAN controller** — 6-DOF hand joint angles via SocketCAN (CAN ID 0x112)

All streams are recorded into a single **rosbag** with a shared ROS clock, eliminating the need for post-hoc timestamp alignment.

## Prerequisites

| Component | Install |
|-----------|---------|
| Ubuntu 20.04 | — |
| ROS Noetic | `sudo apt install ros-noetic-desktop-full` |
| RealSense ROS (D405 recommended) | Build `librealsense` + `realsense-ros` from source (see below) |
| SocketCAN | Kernel built-in; configure with `sudo ip link set can0 up type can bitrate 1000000` |

## Install librealsense + realsense-ros from source (recommended for D405)

`ros-noetic-realsense2-camera` from apt can lag behind and may not include the D405 support/behavior you need.  
For D405, install both `librealsense` and the ROS1 wrapper from source in this order:

```bash
# 0. Optional: remove apt ROS wrapper if already installed.
sudo apt remove -y ros-noetic-realsense2-camera

# 1. Build and install librealsense.
sudo apt update
sudo apt install -y \
  git cmake build-essential pkg-config \
  libssl-dev libusb-1.0-0-dev libgtk-3-dev \
  libglfw3-dev libgl1-mesa-dev libglu1-mesa-dev

cd ~
git clone https://github.com/IntelRealSense/librealsense.git
cd librealsense
# Use a tag that supports your D405 firmware (replace if needed).
git checkout v2.55.1

mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release -DFORCE_RSUSB_BACKEND=ON -DBUILD_EXAMPLES=false
make -j"$(nproc)"
sudo make install
sudo ldconfig

# 2. Build ROS1 wrapper inside your catkin workspace.
cd ~/catkin_ws/src
git clone https://github.com/IntelRealSense/realsense-ros.git
cd realsense-ros
# ROS1 branch for Noetic users.
git checkout ros1-legacy

cd ~/catkin_ws
rosdep install --from-paths src --ignore-src -r -y
catkin_make -DCMAKE_BUILD_TYPE=Release
source devel/setup.bash

# 3. Verify ROS can find the wrapper package.
rospack find realsense2_camera
```

If `rospack find realsense2_camera` succeeds, `roslaunch umi_dex capture.launch` can resolve RealSense dependencies.

## Setup

```bash
# 1. Create (or reuse) a catkin workspace.
mkdir -p ~/catkin_ws/src && cd ~/catkin_ws/src

# 2. Symlink this package into the workspace.
ln -s /path/to/UMI-Dex/ros umi_dex

# 3. Build.
cd ~/catkin_ws
catkin_make

# 4. Source.
source devel/setup.bash
```

## Output directories

`rosbag record` does **not** create missing parent directories. Default `bag_dir` is `$(find umi_dex)/../../outputs`, which is usually **two levels above the `ros/` package** — e.g. the **git repo root** if that is where `../../` lands, or **`~/catkin_ws`** if the package is `~/catkin_ws/src/umi_dex`. Create those directories before capture:

```bash
# Example: ros/ lives at /path/to/UMI-Dex/ros
cd /path/to/UMI-Dex && mkdir -p outputs recordings

# Example: package is symlinked as ~/catkin_ws/src/umi_dex → .../UMI-Dex/ros
mkdir -p ~/catkin_ws/outputs ~/catkin_ws/recordings
```

If you set `bag_dir:=/somewhere/else`, create that path yourself before launching.

## Usage

### Record a capture session (interactive)

```bash
# Bring up CAN interface first.
sudo ip link set can0 up type can bitrate 1000000

# Set camera serials once in:
#   ros/config/camera_serials.conf
#
# Launch all streams + interactive recorder.
roslaunch umi_dex capture.launch

# After launch, use interactive commands:
#   s : start new recording
#   c : stop current recording and keep bag
#   r : delete last finished recording
#   l : list recordings in bag_dir with per-topic count/rate
#   q : quit (if recording, stop and discard active bag)
```

### Launch individual components

```bash
# D455 camera only
roslaunch umi_dex d455.launch

# CAN controller only
roslaunch umi_dex controller.launch

# Override defaults (optional; config file is used by default)
roslaunch umi_dex capture.launch can_channel:=can1 filter_alpha:=0.5 d405_serial:=123456
```

### Play back a bag

```bash
roslaunch umi_dex playback.launch bag:=/path/to/capture_2025-04-10.bag
```

### Extract CSVs from a bag

```bash
rosrun umi_dex bag_extract_node \
    --bag /path/to/capture.bag \
    --out_dir /path/to/output
```

This produces:
- `controller_angles.csv` — timestamped calibrated joint angles
- `ir1_timestamps.csv` — per-frame timestamps for IR camera 1
- `ir2_timestamps.csv` — per-frame timestamps for IR camera 2

## ROS Topics

| Topic | Type | Rate | Source |
|-------|------|------|--------|
| `/camera/infra1/image_rect_raw` | `sensor_msgs/Image` | 30 Hz | realsense2_camera |
| `/camera/infra1/camera_info` | `sensor_msgs/CameraInfo` | 30 Hz | realsense2_camera |
| `/camera/infra2/image_rect_raw` | `sensor_msgs/Image` | 30 Hz | realsense2_camera |
| `/camera/infra2/camera_info` | `sensor_msgs/CameraInfo` | 30 Hz | realsense2_camera |
| `/camera/imu` | `sensor_msgs/Imu` | 200 Hz | realsense2_camera |
| `/camera_d405/color/image_raw` | `sensor_msgs/Image` | 30 Hz | realsense2_camera |
| `/camera_d405/color/camera_info` | `sensor_msgs/CameraInfo` | 30 Hz | realsense2_camera |
| `/hand/joint_states` | `umi_dex/HandJointState` | ~100 Hz | can_controller_node |

## Custom Message: HandJointState

```
std_msgs/Header header
string[6]  names       # [thumb_roll, thumb_pitch, index_pitch, ...]
float64[6] positions   # calibrated angles (0-100 scale)
bool[6]    valid       # per-channel validity from CAN assembly
```

## Package Structure

```
ros/
├── CMakeLists.txt
├── package.xml
├── setup.py
├── config/
│   ├── calibration.csv      # symlink → ../../config/calibration.csv
│   ├── camera_serials.conf  # default D455/D405 serials for capture.launch
│   └── d455_params.yaml
├── launch/
│   ├── capture.launch       # full pipeline + interactive recorder
│   ├── d405.launch          # D405 color + camera info
│   ├── d455.launch          # D455 stereo IR + IMU
│   ├── controller.launch    # CAN controller standalone
│   └── playback.launch      # bag playback
├── msg/
│   └── HandJointState.msg
├── nodes/
│   ├── can_controller_node  # CAN → ROS publisher
│   ├── interactive_capture_node  # CLI recorder controller
│   └── bag_extract_node     # bag → CSV extractor
└── umi_dex/
    ├── __init__.py
    ├── can_protocol.py      # CAN 0x112 frame assembly
    ├── calibration.py       # raw count → actual angle mapping
    └── bag_utils.py         # rosbag extraction helpers
```

## License

Apache License 2.0 — see [LICENSE](../LICENSE).
