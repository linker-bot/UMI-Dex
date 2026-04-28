# Documentation / 文档

Policy and contributor guides live under **`docs/<locale>/`**, where `<locale>` is a BCP 47–style tag (for example `en`, `zh-CN`).  

项目策略与贡献者类文档按 **语言/区域** 分目录放在 **`docs/<locale>/`** 下（`<locale>` 建议采用 BCP 47 风格标签，例如 `en`、`zh-CN`）。

**Adding a locale / 新增语种：** open a PR that adds `docs/<your-locale>/` (mirroring the file set in `docs/en/`) and a row in the table below.  

**欢迎补充翻译：** 提交 PR 增加 `docs/<你的语种标签>/`（建议与 `docs/en/` 下文件结构一致），并在下表中登记。

## Available locales / 当前索引

| Locale | Index |
|--------|-------|
| `en` | [English](en/README.md) |
| `zh-CN` | [简体中文](zh-CN/README.md) |

**Repository usage docs / 使用说明：** the main setup and run instructions are in the root [README.md](../README.md) and [README_zhCN.md](../README_zhCN.md); additional root `README_<locale>.md` files may appear over time.  

**使用与构建说明：** 见仓库根目录 [README.md](../README.md)、[README_zhCN.md](../README_zhCN.md)；日后也可增加其它 `README_<locale>.md`。

## Pipeline guides / 流水线指南

| Doc | Description |
|-----|-------------|
| [recording_sop.md](recording_sop.md) | Operator procedure for ROS capture sessions (IMU warm-up, data collection) |
| [processing.md](processing.md) | Offline Python pipeline: `umi-inspect`, `umi-extract`, `umi-slam`, `umi-process` |
