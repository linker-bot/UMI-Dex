# Contributing to UMI-Dex

**Locales:** English (this file) — [other locales](../README.md)

Thank you for considering contributing to UMI-Dex! Whether it's a bug report, feature request, documentation improvement, or code contribution, we appreciate your help.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How to Contribute](#how-to-contribute)
- [Development Setup](#development-setup)
- [Pull Request Process](#pull-request-process)
- [Coding Standards](#coding-standards)
- [Commit Messages](#commit-messages)

## Code of Conduct

This project follows our [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold these standards. Please report unacceptable behavior to **helloworld@linkerbot.cn**.

## How to Contribute

### Reporting Bugs

Use the [Bug Report](../../.github/ISSUE_TEMPLATE/bug_report.md) issue template. Include:

- ROS distro and OS version (for recorder issues, e.g. Noetic + Ubuntu 20.04)
- Hardware setup (camera model, encoder version)
- Steps to reproduce the issue
- Relevant log output or CSV snippets

### Suggesting Features

Use the [Feature Request](../../.github/ISSUE_TEMPLATE/feature_request.md) issue template. Describe the problem you're trying to solve and your proposed approach.

### Asking Questions

Use the [Question](../../.github/ISSUE_TEMPLATE/question.md) issue template for usage questions, integration help, or general discussion.

### Improving Documentation

Documentation fixes are always welcome — typos, clarity improvements, additional examples, or translations. No issue is too small.

## Development Setup

```bash
# Clone the repository
git clone <your-fork-url>
cd <repo-root>

# Install ROS1 dependencies
source /opt/ros/noetic/setup.bash

# Build ROS package
mkdir -p ~/catkin_ws/src
ln -s "$(pwd)/ros" ~/catkin_ws/src/umi_dex
cd ~/catkin_ws && catkin_make
source devel/setup.bash
cd <repo-root>

# Install Python dev dependencies
uv sync
```

### Running Tests

```bash
cd ~/catkin_ws && catkin_make
source devel/setup.bash
roslaunch umi_dex capture.launch

# Python utility checks
cd <repo-root>
uv run align-trajectory --help
uv run visualize-trajectory --help
```

## Pull Request Process

1. **Fork** the repository and create a feature branch from `main`.
2. **Make your changes** — keep each PR focused on a single concern.
3. **Test** your changes locally (`catkin_make` / `roslaunch` for ROS parts, `uv run ...` for Python tools).
4. **Update documentation** if your change affects user-facing behavior.
5. **Open a Pull Request** using the [PR template](../../.github/PULL_REQUEST_TEMPLATE.md).
6. Ensure all CI checks pass before requesting review.
7. A maintainer will review your PR and may request changes.

### What We Look For

- Adherence to existing code style and conventions
- Tests for new functionality
- No unrelated changes bundled together
- Clear commit messages and PR description

## Coding Standards

- **Python**: Follow PEP 8 and keep CLIs scriptable and documented.
- **ROS 1**: Follow ROS Noetic/catkin conventions for node names, topics, and parameters.
- **Launch files**: Use ROS1 XML launch files under `ros/launch/`.
- **Config files**: Use YAML for parameter files under `config/`.

## Commit Messages

Use clear, descriptive commit messages:

```
<type>: <short summary>

<optional body explaining why>
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`.

Example:
```
feat: add configurable CAN filter smoothing parameter

Expose filter alpha in controller launch defaults to
improve joint angle stability across different hands.
```
