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

Use the [Bug Report](https://github.com/linkerbot/dex-umi/issues/new?template=bug_report.md) issue template. Include:

- ROS 2 distro and OS version
- Hardware setup (camera model, encoder version)
- Steps to reproduce the issue
- Relevant log output or CSV snippets

### Suggesting Features

Use the [Feature Request](https://github.com/linkerbot/dex-umi/issues/new?template=feature_request.md) issue template. Describe the problem you're trying to solve and your proposed approach.

### Asking Questions

Use the [Question](https://github.com/linkerbot/dex-umi/issues/new?template=question.md) issue template for usage questions, integration help, or general discussion.

### Improving Documentation

Documentation fixes are always welcome — typos, clarity improvements, additional examples, or translations. No issue is too small.

## Development Setup

```bash
# Clone the repository
git clone <your-fork-url>
cd <repo-root>

# Install ROS 2 dependencies
source /opt/ros/jazzy/setup.bash

# Build
colcon build --packages-select controller_reader kimera_vio_bringup
source install/setup.bash

# Install Python dev dependencies
pip install -r requirements.txt
```

### Running Tests

```bash
colcon test --packages-select controller_reader kimera_vio_bringup
colcon test-result --verbose
```

## Pull Request Process

1. **Fork** the repository and create a feature branch from `main`.
2. **Make your changes** — keep each PR focused on a single concern.
3. **Test** your changes locally (`colcon build && colcon test`).
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

- **Python**: Follow PEP 8. The project uses `ament_flake8` and `ament_pep257` for linting.
- **ROS 2**: Follow [ROS 2 developer guide](https://docs.ros.org/en/rolling/The-ROS2-Project/Contributing/Developer-Guide.html) conventions.
- **Launch files**: Use Python-based launch files (`.launch.py`).
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
feat: add configurable baud rate for encoder serial port

Allow users to override the default 115200 baud rate via
controller_reader_params.yaml for compatibility with
third-party encoder hardware.
```
