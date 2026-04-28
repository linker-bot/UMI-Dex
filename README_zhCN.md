# UMI-Dex

![](.github/assets/connected.png)

**文档与语言：** [English](README.md) · 简体中文（本页）· [文档索引](docs/README.md)

UMI-Dex 是一套开源的灵巧手遥操作数据采集与轨迹分析项目，用于统一记录多传感器数据并支持后续模仿学习和数据处理。

## 架构说明

UMI-Dex 采用**混合流水线**：ROS 负责同步录制 bag，Python 负责离线后处理生成客户交付数据集。

- **ROS1 录制流水线（标准录制入口）：** `ros/`
  - 采集 D455 双目 IR + IMU、D405 彩色图像、CAN 手部原始帧
  - 所有数据写入同一 rosbag，共享 ROS 时间基准
  - 提供交互式录制控制（`s/c/r/l/q`）
  - 录制时写入会话溯源文件（`<bag>.session.json`）
- **Python 3.12+ 离线流水线：** `src/umi_dex/`
  - `umi-inspect` — bag 健康检查与话题摘要
  - `umi-extract` — CAN 解码校准 → `controller.csv`，D405 → H.264 MP4
  - `umi-slam` — 离线 ORB-SLAM3 回放，生成轨迹 + 地图
  - `umi-process` — 完整流水线：提取 + SLAM + 对齐数据集组装

## 快速开始

### 1) ROS1 录制环境（采集）

请参考 [ros/README.md](ros/README.md) 了解 Noetic 依赖、catkin 工作空间、launch 文件与录制操作。

操作规程（IMU 激活、数据采集）：[docs/recording_sop.md](docs/recording_sop.md)

### 2) Python 离线流水线（处理）

前置要求：Python 3.12+、`uv`、Linux、系统 FFmpeg。

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

### 3) 处理已录制的 bag

```bash
# 先检查 bag 健康状态
uv run umi-inspect /path/to/capture.bag --check-topics

# 完整流水线：提取 + SLAM + 对齐数据集
uv run umi-process /path/to/capture.bag \
  --vocab ./config/ORBvoc.txt \
  --settings ./config/intel_d455.yaml \
  --out sessions/my_session/
```

也可分步执行：

```bash
# 仅提取（controller CSV + D405 MP4，无 SLAM）
uv run umi-extract /path/to/capture.bag --out sessions/my_session/

# 仅 SLAM
uv run umi-slam /path/to/capture.bag \
  --vocab ./config/ORBvoc.txt \
  --settings ./config/intel_d455.yaml \
  --out sessions/my_session/
```

详见 [docs/processing.md](docs/processing.md)。

## 项目结构

- 录制包：`ros/`
- Python 包：`src/umi_dex/`
- 相机与 ORB 配置：`config/`
- 会话输出：`sessions/`
- 文档：`docs/`

## 许可证说明

- 本项目基于 [Apache License 2.0](LICENSE) 开源。
- 第三方依赖（含 ORB-SLAM3 与 `orbslam3-python`）遵循各自许可证要求，详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
- ORB-SLAM3 采用 GPL-3.0 许可证。如果你分发包含 ORB-SLAM3 或其编译绑定的二进制文件、容器镜像或集成产品，须遵守 GPL-3.0 义务。
