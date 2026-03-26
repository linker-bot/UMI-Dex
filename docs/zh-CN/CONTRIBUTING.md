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

请使用 [Bug 报告](https://github.com/linkerbot/dex-umi/issues/new?template=bug_report.md) Issue 模板，并提供：

- ROS 2 发行版与操作系统版本
- 硬件配置（相机型号、编码器版本）
- 问题复现步骤
- 相关日志或 CSV 片段

### 功能建议

请使用 [功能请求](https://github.com/linkerbot/dex-umi/issues/new?template=feature_request.md) Issue 模板，描述你要解决的问题和建议方案。

### 提问

请使用 [提问](https://github.com/linkerbot/dex-umi/issues/new?template=question.md) Issue 模板来提出使用问题、集成帮助或一般讨论。

### 改进文档

欢迎修正错别字、提升可读性、补充示例或翻译；任何大小的文档改进都很有价值。

## 开发环境搭建

```bash
# 克隆仓库
git clone <your-fork-url>
cd <repo-root>

# 安装 ROS 2 依赖
source /opt/ros/jazzy/setup.bash

# 编译
colcon build --packages-select controller_reader kimera_vio_bringup
source install/setup.bash

# 安装 Python 开发依赖
pip install -r requirements.txt
```

### 运行测试

```bash
colcon test --packages-select controller_reader kimera_vio_bringup
colcon test-result --verbose
```

## Pull Request 流程

1. **Fork** 本仓库，从 `main` 分支创建功能分支。
2. **实现变更** —— 每个 PR 只关注一个主题。
3. **本地测试**（`colcon build && colcon test`）。
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

- **Python**：遵循 PEP 8，项目使用 `ament_flake8` 和 `ament_pep257` 进行检查。
- **ROS 2**：遵循 [ROS 2 开发者指南](https://docs.ros.org/en/rolling/The-ROS2-Project/Contributing/Developer-Guide.html)。
- **Launch 文件**：使用 Python 格式的 `.launch.py` 文件。
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
feat: add configurable baud rate for encoder serial port

Allow users to override the default 115200 baud rate via
controller_reader_params.yaml for compatibility with
third-party encoder hardware.
```
