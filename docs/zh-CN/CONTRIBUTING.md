# 贡献指南

**其它语言版本：**见 [文档索引](../README.md)。

感谢你考虑为 UMI-Dex 做贡献！无论是 Bug 反馈、功能建议、文档改进还是代码贡献，我们都非常欢迎。

## 目录

- [行为准则](#行为准则)
- [如何贡献](#如何贡献)
- [开发环境搭建](#开发环境搭建)
- [Pull Request 流程](#pull-request-流程)
- [代码规范](#代码规范)
- [提交信息规范](#提交信息规范)

## 行为准则

本项目遵守 [行为准则](CODE_OF_CONDUCT.md)。参与本项目即表示你同意遵守这些规范。如发现不当行为，请联系 **helloworld@linkerbot.cn**。

## 如何贡献

### 报告 Bug

请使用 [Bug 报告](../../.github/ISSUE_TEMPLATE/bug_report.md) Issue 模板，并提供：

- ROS 发行版与操作系统版本（录制相关问题建议写明 Noetic + Ubuntu 20.04）
- 硬件配置（相机型号、编码器版本）
- 问题复现步骤
- 相关日志或 CSV 片段

### 功能建议

请使用 [功能请求](../../.github/ISSUE_TEMPLATE/feature_request.md) Issue 模板，描述你要解决的问题和建议方案。

### 提问

请使用 [提问](../../.github/ISSUE_TEMPLATE/question.md) Issue 模板来提出使用问题、集成帮助或一般讨论。

### 改进文档

欢迎修正错别字、提升可读性、补充示例或翻译；任何大小的文档改进都很有价值。

## 开发环境搭建

```bash
# 克隆仓库
git clone <your-fork-url>
cd <repo-root>

# 安装 ROS1 依赖
source /opt/ros/noetic/setup.bash

# 编译 ROS 包
mkdir -p ~/catkin_ws/src
ln -s "$(pwd)/ros" ~/catkin_ws/src/umi_dex
cd ~/catkin_ws && catkin_make
source devel/setup.bash
cd <repo-root>

# 安装 Python 开发依赖
uv sync
```

### 运行测试

```bash
cd ~/catkin_ws && catkin_make
source devel/setup.bash
roslaunch umi_dex capture.launch

# Python 工具检查
cd <repo-root>
uv run align-trajectory --help
uv run visualize-trajectory --help
```

## Pull Request 流程

1. **Fork** 本仓库，从 `main` 分支创建功能分支。
2. **实现变更** —— 每个 PR 只关注一个主题。
3. **本地测试**（ROS 部分用 `catkin_make` / `roslaunch`，Python 工具用 `uv run ...`）。
4. 如果变更影响用户体验，请**同步更新文档**。
5. 使用 [PR 模板](../../.github/PULL_REQUEST_TEMPLATE.md) **提交 Pull Request**。
6. 确保所有 CI 检查通过后，再请求 Review。
7. 维护者会审查你的 PR，可能会要求修改。

### 我们关注什么

- 与现有代码风格与约定一致
- 新功能附带测试
- 避免无关变更打包进同一 PR
- 提交信息与 PR 描述清晰

## 代码规范

- **Python**：遵循 PEP 8，保证命令行工具可脚本化且文档清晰。
- **ROS 1**：遵循 ROS Noetic/catkin 的命名与参数约定。
- **Launch 文件**：使用 `ros/launch/` 下的 ROS1 XML `.launch` 文件。
- **配置文件**：参数文件使用 YAML 格式，放置在 `config/` 下。

## 提交信息规范

使用清晰的提交信息：

```
<类型>: <简短描述>

<可选的正文，解释原因>
```

类型：`feat`、`fix`、`docs`、`style`、`refactor`、`test`、`chore`。

示例：

```
feat: add configurable CAN filter smoothing parameter

Expose filter alpha in controller launch defaults to
improve joint angle stability across different hands.
```
