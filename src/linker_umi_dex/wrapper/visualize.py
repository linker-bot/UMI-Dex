#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compatibility entrypoint for trajectory visualization.

The implementation lives in ./script/visualize_trajectory.py.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_script_main():
    root = Path(__file__).resolve().parents[3]
    script_path = root / "script" / "visualize_trajectory.py"
    if not script_path.exists():
        raise FileNotFoundError(f"visualization script not found: {script_path}")
    spec = importlib.util.spec_from_file_location("visualize_trajectory_script", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module spec from: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "main"):
        raise RuntimeError(f"script entrypoint missing main(): {script_path}")
    return module.main


def main() -> int:
    script_main = _load_script_main()
    return int(script_main())


if __name__ == "__main__":
    raise SystemExit(main())
