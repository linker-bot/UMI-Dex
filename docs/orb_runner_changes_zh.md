# ORB 实时运行（`orb_runner`）本分支改动说明

面向 **D455 双目 + IMU** 的 `orb-run` 调试版：在 RealSense 时间对齐、IMU 送入方式、IR 点阵与可视化等方面做了调整，并更新了 ORB 配置里的 IMU 外参与噪声参数。

> 项目级环境与词典下载见根目录 [README_zhCN.md](../README_zhCN.md)。

---

## 一、改动摘要

### 1. `src/umi_dex/orb_runner.py`

| 项 | 说明 |
|----|------|
| **IMU 与图像同步** | 启动前对设备做 **Global Time**（`_enable_global_time_rs_devices`），并在主循环中按 **(上一相机时刻, 当前相机时刻]** 从队列取出 IMU，只喂本区间样本（与 ORB-SLAM3 预积分一致），带约 **5ms** 边界容忍。 |
| **IMU 预热** | 非 `--stereo_only` 时，启动后先等待缓冲区内 IMU 至少约 **80** 个样本再进主循环，减少初期丢步。 |
| **回调与队列** | 仅在为双目+IMU 模式时把陀螺/加速度写入 `imu_buf`；运动帧不进入 `frame_queue`，IR 帧正常入队。 |
| **纯双目模式** | 新增 `--stereo_only`：用 `Sensor.STEREO` + `process_stereo_enhanced`，不启 IMU 流。IMU 初始化失败或想避免惯导重初始化时可开。 |
| **IR 点阵** | 新增 `--ir_emitter` 启动时打开红外投射器；运行中在 **左/右 IR 的 OpenCV 窗口** 按 **`i`** 可开关。 |
| **本地预览与截图** | 左/右 IR 用 OpenCV 实时显示；每 **30** 帧存一对 `left_{frame_idx}.png` / `right_{frame_idx}.png` 到输出目录。 |
| **空 IMU 防御** | 某帧无 IMU 时打印警告，并用上一帧或重力占位，避免 `process_stereo_inertial_enhanced` 崩溃。 |
| **控制器** | 由 **SocketCAN** 改为 **串口**：`--controller_port`（默认 `/dev/l6encoder_usb`）、`--controller_baudrate`（默认 `115200`），与 `ControllerReader` 一致。 |
| **直接跑脚本** | 支持 `python path/to/orb_runner.py`：在包导入失败时把 `src` 加入 `sys.path`。 |
| **导出** | `export_summary.json` 中增加 `slam_mode`（`stereo_only` / `stereo_inertial`）与 `ir_emitter` 状态。 |
| **许可证头** | 文件头 SPDX 改为 `MIT`（与仓库总体许可证策略若有冲突，请与维护者统一）。 |

### 2. `config/intel_d455.yaml`

- **`IMU.T_b_c1`**：由单位阵近似改为带 **小幅旋转/平移** 的标定外参（适配 BMI088/当前安装）。  
- **`IMU.Noise*`**：由占位值改为与 **Kalibr 标定 + BMI088 数据手册** 一致的噪声与随机游走参数。

若你更换相机固定方式或重跑标定，应同步更新本文件中的 `T_b_c1` 与 IMU 噪声项。

---

## 二、环境

- 与主项目一致：Python 3.12+、`uv sync`、已安装 `pyrealsense2`、`orbslam3`（`uv run` 可调用）。  
- 需要 **D455**、词典 `config/ORBvoc.txt` 与 `config/intel_d455.yaml`（或自配 settings）。  
- 可选：调试日志路径环境变量 `LINKER_UD_DEBUG_LOG`（写 JSONL）。

---

## 三、使用方式

在项目根目录执行（见 [README_zhCN.md](../README_zhCN.md) 中 `uv` 与词典准备）。

### 1. 默认：双目 + IMU（惯导模式）

```bash
uv run orb-run \
  --vocab ./config/ORBvoc.txt \
  --settings ./config/intel_d455.yaml \
  --out_dir ./outputs/realtime_map
```

- 无手套/无串口设备时，控制器连接会失败但可继续；若**必须**连接控制器再加 `--controller_required`。  
- 完全不要控制器 CSV：加 `--disable_controller_capture`。

常用参数：

| 参数 | 说明 |
|------|------|
| `--controller_port` | 串口设备路径，默认 `/dev/l6encoder_usb` |
| `--controller_baudrate` | 默认 `115200` |
| `--ir_emitter` | 启动时打开 IR 投射器；运行中在预览窗口按 `i` 切换 |
| `--max_seconds N` | 运行 N 秒后自动结束；`0` 为一直跑到 Ctrl+C |

### 2. 仅双目（无 IMU 融合）

IMU 异常或想先用纯视觉稳定轨迹时：

```bash
uv run orb-run \
  --vocab ./config/ORBvoc.txt \
  --settings ./config/intel_d455.yaml \
  --stereo_only \
  --out_dir ./outputs/realtime_map
```

### 3. 输出目录内主要文件

| 文件 | 内容 |
|------|------|
| `trajectory.txt` | SLAM 轨迹（时间 + 位姿等） |
| `tracked_points.xyz` | 当前跟踪地图点 |
| `map_info.json` | 关键帧/地图点/跟踪状态等 |
| `orb_frame_times.csv` | 帧序号、ORB 时间、单调时间、墙钟、本帧 IMU 样本数 |
| `run_clock_info.csv` | 会话起始墙钟/UTC/单调时间 |
| `export_summary.json` | 本次运行模式、IR 状态、同步文件路径等汇总 |
| `controller_angles.csv` | 未 `--disable_controller_capture` 且串口连上时 |
| `left_*.png` / `right_*.png` | 每 30 帧各一张 IR 存盘 |

### 4. 轨迹可视化

与主文档一致，例如：

```bash
MPLCONFIGDIR="$(pwd)/.mplcache" uv run visualize-trajectory \
  --traj ./outputs/realtime_map/trajectory.txt \
  --points ./outputs/realtime_map/tracked_points.xyz \
  --out_dir ./outputs/realtime_map/plots \
  --traj_only
```

---

## 四、与主 README 的差异提示

主仓库 [README_zhCN.md](../README_zhCN.md) 里 `orb-run` 示例仍使用 **SocketCAN**（`--controller_channel` / `controller_bustype`）。**本分支已改为串口参数**；请以上文「三、使用方式」为准。若合并回主线，应同步更新主 README 中的该示例。

---

## 五、排障简表

| 现象 | 可尝试 |
|------|--------|
| 终端大量 `Empty IMU buffer` | 检查 D455 固件、USB 带宽；确认非 `stereo_only` 时 IMU 流已开；看 Global Time 是否生效。 |
| 跟踪发飘 / 频繁重定位 | 核对 `intel_d455.yaml` 中 `T_b_c1` 与 IMU 噪声；光照差时可试 `--ir_emitter`。 |
| 纯视觉试跑 | 加 `--stereo_only` 对比。 |
| `orbslam3` 导入失败 | 在项目根 `uv sync`，必要时查主文档。 |

---

**文档版本**：对应分支 `feature/dev` 上相对 `main` 的 `orb_runner` + `intel_d455` 差异；若后续提交有变，请更新本页。
