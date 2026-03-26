# 硬件资料（Hardware）

**文档与语言：** [English](README.md) · 简体中文（本页）· [文档索引](../docs/README.md)

本目录存放 UMI-Dex 相关的机械结构（STEP）与电路板设计资料，便于复现与加工。整机软件栈与系统说明见仓库根目录 [README](../README.md)。

## 目录内容

| 位置 | 说明 |
|------|------|
| [`L6-TG-STEP/`](./L6-TG-STEP/) | L6 六自由度串口编码器手套：STEP 零件与主装配 |
| 仓库 `hardware/` 根目录（本层） | 编码器板 STEP、双 IMU / 编码器读数板 STEP、EasyEDA 工程与预览图 |

---

## L6 手套结构件（`L6-TG-STEP/`）

6 自由度串口编码器手套（L6）的 STEP 零件与装配模型，可在 CAD 中打开、出图或送 CNC / 3D 打印。

![L6 手套结构预览](./L6-TG-STEP/L6-TG-Preview.png)

**主要内容概览：**

| 类型 | 说明 / 示例 |
|------|-------------|
| 整装配体 | `1-l6-_v100001.stp` — 主装配文件（体积较大） |
| 拇指 / 手指 | `thumb-*.stp`、`finger-*.stp`、`finger-strap.stp`、`finger-root.stp` 等 |
| 外壳与护盖 | `l6-top-cover.stp`、`l6-botto-cover.stp`、`screen-cover.stp` 等 |
| 相机相关 | `camera-mount-l.stp`、`camera-mount-r.stp`、`camera-zhijia-1.stp`、`carema-cover.stp` |
| 板卡区域护盖（文件名含 3588） | `3588-pcb-top-cover.stp`、`3588-pcb-bottom-cover.stp` |
| 连杆与腕带 | `link-*.stp`、`arm-strap-1.stp` |
| 紧固件示意 | `m1-6.stp`、`m2-5.stp`、`m2-8.stp`、`m2-12.stp`、`m2-16.stp` |
| 其它 | `magnet.stp` 等 |

其余 `.stp` 多为子零件；具体以文件名为准。

---

## 电路板与原理图（本目录内文件）

编码器读数与双 IMU 等相关 PCB 与 3D 预览；EasyEDA 工程为 `UMI-Dex-PCB.epro2`。

### 编码器板

![编码器板预览](./UMI-Dex%20Encoder%20Board.png)

| 文件 | 说明 |
|------|------|
| `UMI-Dex Encoder Board.step` | 编码器板 3D 模型（STEP） |

### 双 IMU 与编码器读数板

![双 IMU 与编码器读数板预览](./UMI-Dex_Dual%20IMU%20and%20encoder%20reading.step.jpg)

| 文件 | 说明 |
|------|------|
| `UMI-Dex_Dual IMU and encoder reading.step` | 双 IMU + 编码器读数相关 PCB 的 3D 模型 |

### PCB 总览图

![PCB 预览 1](./UMI-Dex-PCB-1.png) ![PCB 预览 2](./UMI-Dex-PCB-2.png)

| 文件 | 说明 |
|------|------|
| `UMI-Dex-PCB.epro2` | EasyEDA 工程，可在 EasyEDA 中打开编辑并导出 Gerber / 制板资料 |

---

## 使用提示

- **STEP**：推荐使用 FreeCAD、Fusion 360、SolidWorks 等打开；大装配体加载可能较慢。
- **PCB**：`.epro2` 需使用 [EasyEDA](https://easyeda.com/)（或兼容工具）打开；下单前请与板厂核对 BOM、叠层与工艺要求。
