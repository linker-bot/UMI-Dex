# ORB 实时运行（`orb-run`）使用说明

本说明介绍如何用 **RealSense D455 双目 + IMU** 运行实时 `orb-run`：包括**启动时词典加载、惯导初始化与 VIBA 阶段含义**、时间对齐、IMU 与图像配合方式、IR 点阵、本地预览、可选手套控制器，以及结果目录中的文件与后续可视化。

> 项目级环境（Python、`uv`、词典与依赖安装）见根目录 [README.md](../README.md)（英文）· [README_zhCN.md](../README_zhCN.md)（简体中文）。

---

## 一、环境与前准备

- **运行环境**与主项目一致：Python 3.12+、在项目根执行 `uv sync`；需能导入 `pyrealsense2` 与 `orbslam3`（通过 `uv run` 调用）。
- **硬件与文件**：D455、ORB 词典 `config/ORBvoc.txt`、标定与 ORB 设置 `config/intel_d455.yaml`（或你自配的 settings）。
- **可选调试**：环境变量 `LINKER_UD_DEBUG_LOG` 可设为 JSONL 日志路径，便于联调。

`intel_d455.yaml` 中的 **`IMU.T_b_c1`** 以及以 **`IMU.Noise`** 为前缀的噪声项（`IMU.NoiseGyro` / `IMU.NoiseAcc` 等）应对应当前相机安装与标定。若你更换固定方式或重跑标定，请同步更新该文件，否则惯导解算易不稳定。

---

## 二、启动过程与惯导（IMU）初始化

本小节仅针对**「双目 + IMU」** 的默认模式。

运行代码为

```bash
uv run orb-run \
  --vocab ./config/ORBvoc.txt \
  --settings ./config/intel_d455.yaml \
  --out_dir ./outputs/realtime_map
```

**流程速览**（与终端里常见出现顺序，可对照操作；详细说明见下方编号条目）

- **（一）词典**  
  先出现如 **`Loading ORB Vocabulary. This could take a while...`**，随后可能类似 `Vocabulary loaded in ...`；表示词袋在加载。在**纹理较丰富**环境做**平滑前后/左右平移**（忌长期对白墙静止、忌只转不平移、忌猛甩糊片）。  

- **（二）`not IMU meas` / `not enough acceleration`**  
  **多见于 VIBA 之前**；处理见下 **第 6 点**。本质是**补纹理 + 平滑平移激励**。  

- **（三）`First KF:...; Map init KF:...` / `New Map created with N points`**（`N` 因场景/版本而变）  
  新地图与初值点已建立，多表示**视觉建图与跟踪已启动、状态正常向**。可继续在纹理好处平移。  

- **（四）VIBA 1**  
  见 **`end VIBA 1`** 表示第一轮 VIBA 走完一段，**请继续**平滑平移，**不要**在此就长时间静止。  

- **（五）VIBA 2 与跟丢**  
  再出现 **`end VIBA 2`**，多可视为**联合初始化**常用完成条件，可**开始正式采数据**。之后若**局部跟丢、终端刷 `Fail to track local map!`** 等，见下 **第 7 点**。

1. **加载 ORB 词袋（词典）**  
  若出现 **Loading ORB Vocabulary. This could take a while...**（及随后的 loaded 类提示），表示正从 `--vocab` 读入词袋；大文件时可能**数秒到数十秒**，属正常，等其结束即可。

2. **开始激励相机（激发 IMU 可观测性）**  
  在惯导系统真正收敛前，**不要把相机完全静止在白纸或强无纹理平面上**；建议让相机对准**纹理、边缘相对丰富** 的场景，并对相机做**缓慢、持续** 的运动，例如**左右/上下平移**或**小范围前后平移**（以激发陀螺与加速度的测量，便于视觉与 IMU 对齐）。运动幅度以平稳、不糊片为宜。若先反复出现第 **6** 点中的两条提示，**优先**回到纹理更好处并加强**线向平移**（见上「流程速览」）。

3. **第一阶段：VIBA 1**  
  终端出现 **`start VIBA 1`** 与 **`end VIBA 1`**，表示 ORB-SLAM3 中第一轮「视觉-惯性」联合优化/初始化子阶段（VIBA 可理解为 *Visual Inertial Bundle Adjustment* 的缩写）已跑完一段。仅到 **`end VIBA 1`** 一般仍不视为「可以随便停、随便采」：请**按流程速览继续平移运动**，以推进第二轮。

4. **第二阶段：VIBA 2 = 可开始正式采集的常用判据**  
  在 **`end VIBA 1` 之后** 继续上述激励，再出现 **`start VIBA 2` / `end VIBA 2`** 时，在多数情况下可认为 **IMU 与视觉侧联合初始化**已把主要步走完、**惯导/激励**侧可视为**成功**（**惯导初始化 + 整段 VIBA 流程的常用外显判据**），**可开始**按任务做**正式移动与数据采集**（轨迹、手套、输出目录等）。**之后**无纹理、动太快等仍可能出现 **`Fail to track local map!`**，见下 **第 7 点**，与此时是否已结束 VIBA 无矛盾。

5. **若长时间卡在 VIBA 1 之前、或没有 VIBA 2**  
  优先检查视场内纹理、光照、运动是否过慢/过激、IMU 时间戳与 `intel_d455.yaml` 中 IMU 外参/噪声是否合理；需要纯视觉时可用 **`--stereo_only`** 绕过 IMU 流程。

6. **终端里 `not IMU meas` / `not enough acceleration` 是什么？常在哪出现？**  
  这两条**多数出现在进入 VIBA 之前**（也可见于**刚送图/送 IMU 的衔接**或 VIBA 刚起时），来自 **ORB-SLAM3 与惯导（IMU）相关的初始化/对齐**逻辑，**不是**「跟丢 / Tracking LOST」的专用标志。  
  - **代表什么、怎么缓解**（与上文「流程速览」一致）  
  总体表示：**该步暂时缺可用 IMU 量测**、或**线加速度/激励对当前步不够**。处理上请优先回到 **纹理较多、对比清晰** 的环境，做**平滑的前后/左右平移**（**不要**只绕竖轴转、**不要**大静止对白墙）。多能在随后出现 **`New Map created...` → VIBA 1/2** 的推进。  
  - **`not IMU meas`**（「没有 IMU 量测」类含义）  
  在**当前时刻/当前一步** 内部要用的 IMU **暂时不可用**（时间窗缺样本、与像不同步、缓冲刚空等）。**偶发**可忽略；**持续刷屏** 时与 **`Empty IMU buffer`** 同查：IMU 流、Global Time、USB 与本仓库的 IMU 时间对齐。  
  - **`not enough acceleration`**（「加速度激励不够」）  
  需**足量平移** 带来的加速度变化以约束重力/尺度等；**动得太小、只转身不平移** 时易反复。加强 **仍平滑的** 前后/左右平移。  
  - **和「跟丢」**  
  **不画等号**；若**长期不消失** 且**走不完 VIBA**，再同时查纹理、标定与 IMU 数据路径。

7. **终端里 `Fail to track local map!` 表示什么？怎么算恢复？**  
  在 **`end VIBA 2` 已出现、惯导初始化可视为完成之后**，运行过程中若仍打印 **`Fail to track local map!`**，在 ORB-SLAM3 语境下多表示**当前帧在局部地图上的跟踪/关联失败**（常见原因：突然走进**无纹理/弱光照**区、运动过快、运动模糊、或视场和已有地图**几何/外观**对不上等）。它属于**跟丢/跟踪质量恶化**时常见的一类英文提示，**与** VIBA 是否结束**无矛盾**——初始化成功不等于永远不会丢跟踪。  
  - **出现时应怎么办**  
  尽快将相机**移回**或**对准** **纹理、边缘较丰富** 的环境（如室内有家具、标贴、书格等，避免大片单色墙或地面），保持**速度适中**；可配合**小范围平移+缓慢环视**，帮助系统重新在局部地图中锁定。  
  - **怎么判断已恢复正常**  
  在实践上，当终端里**不再继续刷屏** 或**不再新出现** **`Fail to track local map!`**，且**左/右 IR 预览**里建图/跟踪又趋于稳定、位姿与地图点续得起来，即可**大致认为** 局部跟踪已**恢复**（以你实际绑定中是否还伴随其它 LOST/重定位类信息为准，综合判断）。**不要**把「必须等某一条固定英文」当成唯一标准，但「该提示消失 + 画面稳」是很好用的**现场判据**。

---

## 三、启动命令

在项目根目录执行（`uv` 与词典准备见主 README）。

### 1. 默认：双目 + IMU（惯导模式）+关闭ir投射模式

```bash
uv run orb-run \
  --vocab ./config/ORBvoc.txt \
  --settings ./config/intel_d455.yaml \
  --out_dir ./outputs/realtime_map
```

- 无 CAN 设备或总线未就绪时，控制器会连接失败，但 **SLAM 可继续**；若必须连上手套才允许运行，请加 `--controller_required`。
- 完全不需要手套 CSV：加 `--disable_controller_capture`。

**常用参数：**


| 参数                       | 说明                                                      |
| ------------------------ | ------------------------------------------------------- |
| `--controller_channel`   | CAN 通道名，默认 `can0`                                       |
| `--controller_bustype` | `python-can` 的 *bustype*（与实现里 `interface` 形参一致），默认 `socketcan`（如 slcan 用 `slcan` 等） |
| `--ir_emitter`           | 启动时打开 IR 投射；运行中在 IR 预览窗口按 `i` 切换                        |
| `--max_seconds N`        | 运行 N 秒后自动结束；`0` 为一直运行直到 Ctrl+C                          |


### 2. 仅双目（不融合 IMU）

IMU 异常或想先用纯视觉稳定轨迹时：

```bash
uv run orb-run \
  --vocab ./config/ORBvoc.txt \
  --settings ./config/intel_d455.yaml \
  --stereo_only \
  --out_dir ./outputs/realtime_map
```

### 3. 开启 IR 红外投射（结构光点阵）

D455 的红外投射器能在**弱纹理、对比度差**的场景下补纹理，有利于特征点与跟踪稳定。可按需二选一或组合使用：

1. **启动时就打开**  
   在命令里加上 `--ir_emitter`。程序启动管道后会打开投射，终端一般会打印类似 `[RealSense] IR projector ON`。
2. **运行中再开/关**  
   不加 `--ir_emitter` 时，默认以**关闭投射**启动。程序会打开左/右 IR 的 **OpenCV 预览窗口**（标题一般为 `left` / `right`）。**用鼠标点选其一使窗口处于前台**，然后按键盘 **`i`**（大小写均可）即可在**开 ↔ 关**之间切换投射；每次切换同样会打印 `[RealSense] IR projector ON/OFF`。
3. **记录与汇总**  
   结束运行后，输出目录里的 **`export_summary.json`** 里会记录本次结束时的 `ir_emitter` 是否开启。

**说明**：切换键依赖 OpenCV 窗口能收到键盘事件；若在无图形界面或远程未做 X11/Wayland 转发，可能无法靠按键切换，此时请用 **`--ir_emitter`** 在启动时固定为开（或接受默认关）。

---

## 四、输出目录中的主要文件


| 文件                           | 内容                                                |
| ---------------------------- | ------------------------------------------------- |
| `trajectory.txt`             | SLAM 轨迹（时间、位姿等）                                   |
| `tracked_points.xyz`         | 当前跟踪到的地图点                                         |
| `map_info.json`              | 关键帧/地图点/跟踪状态等                                     |
| `orb_frame_times.csv`        | 帧序号、ORB 时间、单调时间、墙钟、本帧 IMU 样本数                     |
| `run_clock_info.csv`         | 会话起始墙钟/UTC/单调时间                                   |
| `export_summary.json`        | 运行模式、IR 状态、同步与导出路径等汇总（含 `slam_mode`、`ir_emitter`） |
| `controller_angles.csv`      | 未 `--disable_controller_capture` 且 CAN 已连上时       |
| `left_*.png` / `right_*.png` | 每 30 帧各存一张 IR 图                                   |


---

## 五、轨迹可视化

与主文档一致，例如：

```bash
MPLCONFIGDIR="$(pwd)/.mplcache" uv run visualize-trajectory \
  --traj ./outputs/realtime_map/trajectory.txt \
  --points ./outputs/realtime_map/tracked_points.xyz \
  --out_dir ./outputs/realtime_map/plots \
  --traj_only
```

---

## 六、常见问题与排障


| 现象                                               | 可尝试                                                                                                                   |
| ------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------- |
| 终端大量 `Empty IMU buffer`                          | 检查 D455 固件与 USB 带宽；确认非 `stereo_only` 时 IMU 已开启；确认 Global Time 已生效。                                                    |
| `First KF:...` / `New Map created with N points` | 新局部地图与初始地图点已建立，多表示**视觉侧已跑通、状态正常向**；点数 **N** 因场景而异；见 **二** 中「流程速览（三）」。                                                 |
| `not IMU meas` / `not enough acceleration`       | **多见于 VIBA 前**；属 **IMU 初始化/对齐** 提示，**不是**跟丢专用；回**丰富纹理**处做**平滑前后/左右平移**；见 **二、6**与「流程速览（二）」。                           |
| `Fail to track local map!`                       | **局部地图跟踪失败**，多见于**无纹理/光照差/动太快** 等；**不表示**要重做 VIBA。回到**纹理丰富**处、适度缓动、可开 IR；**该提示不再反复出现**且画面又稳，可作恢复好的**实用判据**；见 **二、7**。 |
| 跟踪发飘 / 频繁重定位                                     | 核对 `intel_d455.yaml` 中 `T_b_c1` 与 IMU 噪声；弱纹理或光照差时可试 `--ir_emitter`。                                                   |
| 中途跟丢、需重新稳住跟踪                                     | 见 **二、6**；若终端反复出现 **`Fail to track local map!`** 见 **二、7**。**不要**把「再出现 `start VIBA 2`」当作恢复成功的前提。                        |
| 想对比纯视觉                                           | 加 `--stereo_only` 与惯导结果对比。                                                                                            |
| `orbslam3` 导入失败                                  | 在项目根 `uv sync`，并查阅主文档中的安装说明。                                                                                          |


