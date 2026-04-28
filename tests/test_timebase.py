"""Tests for umi_dex.timebase."""

from umi_dex.timebase import (
    SessionAnchor,
    estimate_rate_hz,
    ros_ns_to_iso,
    stamp_to_ns,
    validate_monotonic,
)


def test_ros_ns_to_iso_epoch():
    assert ros_ns_to_iso(0) == "1970-01-01T00:00:00+00:00"


def test_ros_ns_to_iso_known():
    # 2025-01-01T00:00:00Z = 1735689600 seconds
    ns = 1735689600 * 1_000_000_000
    iso = ros_ns_to_iso(ns)
    assert iso.startswith("2025-01-01T00:00:00")


def test_stamp_to_ns():
    assert stamp_to_ns(1, 500_000_000) == 1_500_000_000
    assert stamp_to_ns(0, 0) == 0


def test_validate_monotonic_clean():
    ts = [100, 200, 300, 400]
    violations = validate_monotonic(ts, label="test")
    assert violations == []


def test_validate_monotonic_violation():
    ts = [100, 200, 150, 400]
    violations = validate_monotonic(ts, label="test")
    assert violations == [2]


def test_estimate_rate_hz():
    # 10 samples over 1 second = 9 intervals -> 9 Hz
    ts = [i * 111_111_111 for i in range(10)]
    rate = estimate_rate_hz(ts)
    assert rate is not None
    assert abs(rate - 9.0) < 0.1


def test_estimate_rate_hz_insufficient():
    assert estimate_rate_hz([]) is None
    assert estimate_rate_hz([100]) is None


def test_session_anchor_translation():
    anchor = SessionAnchor(
        ros_time_ns=1000,
        wall_clock_ns=2000,
        perf_counter_ns=500,
        hostname="test",
        kernel="6.0",
    )
    assert anchor.ros_to_wall_ns(1500) == 2500
    assert anchor.ros_to_mono_ns(1500) == 1000
