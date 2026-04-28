#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Unified time-base for the offline pipeline.

Master time is ROS bag header stamp in nanoseconds (`t_ros_ns`).
Every output row carries (idx, t_ros_ns, t_iso, ...payload...).

The provenance anchor from session_meta.json lets us translate
between ROS time, host monotonic, and wall-clock domains when needed
(e.g. for detecting NTP steps or joining with external systems).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from dataclasses import dataclass


@dataclass(frozen=True)
class SessionAnchor:
    """Provenance anchor captured at recording start."""

    ros_time_ns: int
    wall_clock_ns: int
    perf_counter_ns: int
    hostname: str
    kernel: str

    def ros_to_wall_ns(self, t_ros_ns: int) -> int:
        return self.wall_clock_ns + (t_ros_ns - self.ros_time_ns)

    def ros_to_mono_ns(self, t_ros_ns: int) -> int:
        return self.perf_counter_ns + (t_ros_ns - self.ros_time_ns)


def ros_ns_to_iso(t_ros_ns: int) -> str:
    """Convert a ROS nanosecond timestamp to an ISO-8601 UTC string."""
    secs = t_ros_ns / 1_000_000_000.0
    dt = datetime.fromtimestamp(secs, tz=timezone.utc)
    return dt.isoformat()


def stamp_to_ns(stamp_sec: int, stamp_nsec: int) -> int:
    """Convert a ROS Header stamp (sec, nsec) pair to a single nanosecond value."""
    return stamp_sec * 1_000_000_000 + stamp_nsec


def validate_monotonic(timestamps_ns: list[int], label: str = "stream") -> list[int]:
    """Check that a timestamp sequence is non-decreasing.

    Returns indices of any violations (empty list if clean).
    """
    violations = []
    for i in range(1, len(timestamps_ns)):
        if timestamps_ns[i] < timestamps_ns[i - 1]:
            violations.append(i)
    if violations:
        n = len(violations)
        print(f"[timebase] WARNING: {n} monotonicity violation(s) in {label}")
    return violations


def estimate_rate_hz(timestamps_ns: list[int]) -> Optional[float]:
    """Estimate the average sample rate from a list of nanosecond timestamps."""
    if len(timestamps_ns) < 2:
        return None
    duration_s = (timestamps_ns[-1] - timestamps_ns[0]) / 1e9
    if duration_s <= 0:
        return None
    return (len(timestamps_ns) - 1) / duration_s
