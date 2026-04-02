# UMI-Dex

![](.github/assets/connected.png)

**文档与语言：** [English](README.md) · 简体中文（本页）· [文档索引](docs/README.md)

UMI-Dex 是一套面向灵巧手遥操作的数据采集流水线：通过同构手套（USB 串口编码器）与视觉惯性里程计（VIO）同步记录操作者的手部关节角度与末端位姿，输出统一时间轴对齐的数据文件，用于后续模仿学习、动作回放与数据处理。

当前项目实现采用 **Intel RealSense D455 + ORB-SLAM3（stereo-inertial）** 的 PC 侧本地采集方案（`uv` 管理 Python 工作流），直接在采集进程内完成轨迹估计与时间同步导出，不依赖 `kimera_vio_ros` 或 `/poseimu` 话题桥接。

## 当前功能（PC）

- RealSense D455 双目 IR + IMU 采集
- ORB-SLAM3 双目惯性轨迹估计
- USB 控制器角度采集（原始值 + 映射值）
- 轨迹与控制器数据离线对齐与可视化

## 环境要求

- Python 3.12+
- 已安装 `uv`（推荐）
- Intel RealSense D455（运行采集时需要）
- 可选控制器串口设备（默认 `/dev/l6encoder_usb`）

## 环境准备

1) 如果未安装 `uv`，先安装：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

2) 创建并同步项目环境：

```bash
uv sync
```

3) 激活虚拟环境：

```bash
source .venv/bin/activate
```

4) 下载 ORB-SLAM3 词典到 `config/`（首次执行一次即可）：

```bash
curl -L "https://github.com/UZ-SLAMLab/ORB_SLAM3/raw/master/Vocabulary/ORBvoc.txt.tar.gz" -o ./config/ORBvoc.txt.tar.gz
tar -xzf ./config/ORBvoc.txt.tar.gz -C ./config
rm ./config/ORBvoc.txt.tar.gz
```

## 主流程（推荐）

1) 启动交互式录制（脚本入口）：

```bash
uv run python script/interactive_record.py \
  --vocab ./config/ORBvoc.txt \
  --settings ./config/intel_d455.yaml \
  --out_dir ./outputs/realtime_map
```

2) 轨迹可视化（脚本入口）：

```bash
MPLCONFIGDIR="$(pwd)/.mplcache" uv run python script/visualize_trajectory.py \
  --traj ./outputs/realtime_map/trajectory.txt \
  --points ./outputs/realtime_map/tracked_points.xyz \
  --out_dir ./outputs/realtime_map/plots \
  --traj_only
```

3) 可选：轨迹与控制器数据对齐：

```bash
uv run align-trajectory \
  --traj ./outputs/realtime_map/trajectory.txt \
  --controller ./outputs/realtime_map/controller_angles.csv \
  --out ./outputs/realtime_map/trajectory_controller_aligned.csv
```

## 交互式录制控制（终端）

启动命令：

```bash
uv run record-interactive \
  --vocab ./config/ORBvoc.txt \
  --settings ./config/intel_d455.yaml \
  --out_dir ./outputs/realtime_map
```

按键说明：

- `s`：开始录制
- `c`：停止当前录制并保存输出
- `r`：删除/重置上一次输出目录内容（危险操作）
- `q`：退出控制器

说明：

- 录制进行中不允许执行 `r`，请先按 `c` 停止。
- 交互式控制器会以子进程方式启动 `orb_runner`，并在停止时执行安全退出流程。
- 交互模式下会屏蔽 `orb_runner` 的常规日志，仅保留 warning/error/traceback 等异常输出。
- 启动器实现源码位于 `script/interactive_record.py`。

## 调试/开发命令（进阶）

用于直接测试 `orb_runner` 与底层排障：

```bash
uv run orb-run \
  --vocab ./config/ORBvoc.txt \
  --settings ./config/intel_d455.yaml \
  --out_dir ./outputs/realtime_map \
  --disable_controller_capture
```

```bash
uv run orb-run \
  --vocab ./config/ORBvoc.txt \
  --settings ./config/intel_d455.yaml \
  --out_dir ./outputs/realtime_map \
  --controller_port /dev/l6encoder_usb
```

其他保留的开发封装命令：

```bash
uv run record-interactive --help
uv run visualize-trajectory --help
uv run record-realsense --out ./recordings/session_001
```

## 示例数据（即将发布）

公开高质量示例数据将在当前设备与数据链路达到目标质量标准后发布。

## 输出文件（`--out_dir`）

- `trajectory.txt`
- `tracked_points.xyz`
- `map_info.json`
- `export_summary.json`
- `orb_frame_times.csv`
- `run_clock_info.csv`
- `controller_angles.csv`（启用控制器采集时生成）

## 使用说明与排障建议

- Linux 串口权限：若控制器连接失败，请检查串口权限（`dialout` 用户组或 udev 规则）。
- 若 `orbslam3` 导入失败，请重新执行 `uv sync` 并检查 `uv` 环境是否正常。
- 仅轨迹测试可使用 `--disable_controller_capture`。
- 在受限环境中可视化建议使用 `MPLCONFIGDIR="$(pwd)/.mplcache"`。

## 项目结构

- 流水线代码：`src/linker_umi_dex/`
- 交互式录制启动器：`script/interactive_record.py`
- 轨迹可视化脚本：`script/visualize_trajectory.py`
- ORB 资源/配置：`config/intel_d455.yaml`、`config/ORBvoc.txt`
- 运行输出：`outputs/`、`recordings/`

## 许可证说明

- 本项目基于 [Apache License 2.0](LICENSE) 开源，希望整个行业和生态越来越好 ❤️
- 第三方依赖（含 ORB-SLAM3 与 `orbslam3-python`）遵循各自许可证要求。
