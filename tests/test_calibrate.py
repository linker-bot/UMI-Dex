"""Tests for umi_dex.controllers.calibrate."""

import pytest
from umi_dex.controllers.calibrate import (
    Calibrator,
    JointCalibration,
    _ascending_ratio_with_wrap,
    _clip,
    _in_ascending_interval,
    load_calibrations,
)


def test_clip():
    assert _clip(5, 0, 10) == 5
    assert _clip(-1, 0, 10) == 0
    assert _clip(15, 0, 10) == 10


def test_ascending_interval_normal():
    assert _in_ascending_interval(5, 0, 10)
    assert not _in_ascending_interval(15, 0, 10)


def test_ascending_interval_wrapped():
    # Interval wraps: [350, 30] means 350..360/0..30
    assert _in_ascending_interval(355, 350, 30)
    assert _in_ascending_interval(10, 350, 30)
    assert not _in_ascending_interval(100, 350, 30)


def test_ascending_ratio_normal():
    assert _ascending_ratio_with_wrap(5, 0, 10) == pytest.approx(0.5)
    assert _ascending_ratio_with_wrap(0, 0, 10) == pytest.approx(0.0)
    assert _ascending_ratio_with_wrap(10, 0, 10) == pytest.approx(1.0)


def test_load_calibrations_from_default():
    cals = load_calibrations()
    assert len(cals) == 6
    assert cals[0].joint == "thumb_roll"
    assert cals[1].joint == "thumb_pitch"


def test_calibrator_map_counts():
    calibrator = Calibrator()
    # All zeros — should map to some value without error
    result = calibrator.map_counts([0.0] * 6)
    assert len(result) == 6
    for v in result:
        assert isinstance(v, float)


def test_calibrator_wrong_length():
    calibrator = Calibrator()
    with pytest.raises(ValueError):
        calibrator.map_counts([0.0] * 5)
