"""Tests for umi_dex.controllers.can_decode."""

from umi_dex.controllers.can_decode import (
    CAN_ID_ENC,
    CanDecoder,
    DecodedSample,
)


def _make_part(part_idx: int, seq: int, val0: int, val1: int, valid_mask: int = 0x3F) -> bytes:
    """Build an 8-byte CAN data payload for one of the 3 parts."""
    b = bytearray(8)
    b[0] = part_idx
    b[1] = valid_mask if part_idx == 0 else 0
    b[2] = seq & 0xFF
    b[3] = (seq >> 8) & 0xFF
    b[4] = val0 & 0xFF
    b[5] = (val0 >> 8) & 0xFF
    b[6] = val1 & 0xFF
    b[7] = (val1 >> 8) & 0xFF
    return bytes(b)


def test_decoder_assembles_three_parts():
    decoder = CanDecoder()
    seq = 42
    t = 1_000_000_000

    r0 = decoder.feed_can_frame(t, CAN_ID_ENC, 8, _make_part(0, seq, 100, 200))
    assert r0 is None

    r1 = decoder.feed_can_frame(t + 1000, CAN_ID_ENC, 8, _make_part(1, seq, 300, 400))
    assert r1 is None

    r2 = decoder.feed_can_frame(t + 2000, CAN_ID_ENC, 8, _make_part(2, seq, 500, 600))
    assert isinstance(r2, DecodedSample)
    assert len(r2.raw_counts) == 6
    # part0: raw0=100 -> thumb_pitch (idx 1), raw1=200 -> thumb_roll (idx 0)
    assert r2.raw_counts[0] == 200.0  # thumb_roll
    assert r2.raw_counts[1] == 100.0  # thumb_pitch
    assert r2.raw_counts[2] == 300.0
    assert r2.raw_counts[3] == 400.0
    assert r2.raw_counts[4] == 500.0
    assert r2.raw_counts[5] == 600.0


def test_decoder_ignores_wrong_id():
    decoder = CanDecoder()
    result = decoder.feed_can_frame(0, 0x999, 8, bytes(8))
    assert result is None


def test_decoder_ignores_short_data():
    decoder = CanDecoder()
    result = decoder.feed_can_frame(0, CAN_ID_ENC, 4, bytes(4))
    assert result is None


def test_decoder_prunes_stale_assemblies():
    decoder = CanDecoder()
    t0 = 1_000_000_000
    t_stale = t0 + 3_000_000_000  # 3 seconds later

    decoder.feed_can_frame(t0, CAN_ID_ENC, 8, _make_part(0, 1, 10, 20))
    assert len(decoder._assemblies) == 1

    # Feed a different seq at a time that triggers pruning
    decoder.feed_can_frame(t_stale, CAN_ID_ENC, 8, _make_part(0, 2, 30, 40))
    assert 1 not in decoder._assemblies  # seq 1 was pruned
