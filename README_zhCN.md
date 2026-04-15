# UMI-Dex

![](.github/assets/connected.png)

**文档与语言：** [English](README.md) · 简体中文（本页）· [文档索引](docs/README.md)

UMI-Dex 是一套开源的灵巧手遥操作数据采集与轨迹分析项目，用于统一记录多传感器数据并支持后续模仿学习和数据处理。

## 架构说明

当前项目分为两层：

- **ROS1 录制流水线（标准录制入口）：** `ros/`
  - 采集 D455 双目 IR + IMU、D405 彩色图像、CAN 手部关节角
  - 所有数据写入同一 rosbag，共享 ROS 时间基准
  - 提供交互式录制控制（`s/c/r/l/q`）
- **Python ORB-SLAM3 工具（分析与调试）：** `src/umi_dex/`
  - ORB 运行/调试：`orb-run`
  - 轨迹可视化：`visualize-trajectory`
  - 轨迹与控制器对齐：`align-trajectory`

## 快速开始

### 1) ROS1 录制环境（推荐用于正式采集）

请直接参考 ROS 指南：

- [ros/README.md](ros/README.md)

该文档包含 Noetic 依赖、catkin 工作空间、launch 方式和录制流程。

### 2) Python 工具环境（ORB + 可视化 + 对齐）

前置要求：

- Python 3.12+
- 已安装 `uv`
- 建议在 Linux 环境使用 `orbslam3-python`（预编译 wheel 兼容性更好）

安装：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
source .venv/bin/activate
```

如果 `config/ORBvoc.txt` 不存在，首次执行一次：

```bash
curl -L "https://github.com/UZ-SLAMLab/ORB_SLAM3/raw/master/Vocabulary/ORBvoc.txt.tar.gz" -o ./config/ORBvoc.txt.tar.gz
tar -xzf ./config/ORBvoc.txt.tar.gz -C ./config
rm ./config/ORBvoc.txt.tar.gz
```

## Python 工具命令

轨迹可视化：

```bash
MPLCONFIGDIR="$(pwd)/.mplcache" uv run visualize-trajectory \
  --traj ./outputs/realtime_map/trajectory.txt \
  --points ./outputs/realtime_map/tracked_points.xyz \
  --out_dir ./outputs/realtime_map/plots \
  --traj_only
```

轨迹与控制器数据对齐：

```bash
uv run align-trajectory \
  --traj ./outputs/realtime_map/trajectory.txt \
  --controller ./outputs/realtime_map/controller_angles.csv \
  --out ./outputs/realtime_map/trajectory_controller_aligned.csv
```

ORB 运行/调试：

```bash
uv run orb-run \
  --vocab ./config/ORBvoc.txt \
  --settings ./config/intel_d455.yaml \
  --out_dir ./outputs/realtime_map \
  --controller_channel can0 \
  --controller_bustype socketcan
```

## 说明与排障

- 正式录制建议使用 ROS1 流程；Python 命令主要用于分析和调试。
- 控制器默认使用 SocketCAN（`can0`），不使用旧的串口录制入口。
- 若 `orbslam3` 导入失败，请在项目根目录重新执行 `uv sync`。
- 在受限环境中绘图建议设置 `MPLCONFIGDIR="$(pwd)/.mplcache"`。

## 项目结构

- 录制包：`ros/`
- Python 包：`src/umi_dex/`
- 可视化脚本（仓库便捷入口）：`script/visualize_trajectory.py`
- 相机与 ORB 配置：`config/`
- 运行输出：`outputs/`、`recordings/`

## 示例数据

公开示例数据将在数据质量达到发布标准后提供。

## 许可证说明

- 本项目基于 [Apache License 2.0](LICENSE) 开源。
- 第三方依赖（含 ORB-SLAM3 与 `orbslam3-python`）遵循各自许可证要求，详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
- ORB-SLAM3 采用 GPL-3.0 许可证。如果你分发包含 ORB-SLAM3 或其编译绑定的二进制文件、容器镜像或集成产品，须遵守 GPL-3.0 义务（提供源码、附带许可证文本等）。
