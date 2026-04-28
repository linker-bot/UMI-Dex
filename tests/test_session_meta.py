"""Tests for umi_dex.session_meta."""

import json
from pathlib import Path

from umi_dex.session_meta import SessionMeta, StreamStats, generate_session_id


def test_session_meta_roundtrip(tmp_path: Path):
    meta = SessionMeta(
        session_id="test_session",
        bag_path="/tmp/test.bag",
        bag_sha256="abc123",
        bag_start_ns=1000,
        bag_end_ns=2000,
        bag_duration_s=1.0,
        streams=[
            StreamStats(name="ctrl", message_count=100, output_file="controller.csv"),
        ],
    )
    written = meta.write(tmp_path)
    assert written.exists()

    loaded = SessionMeta.from_json(written)
    assert loaded.session_id == "test_session"
    assert loaded.bag_sha256 == "abc123"
    assert len(loaded.streams) == 1
    assert loaded.streams[0].name == "ctrl"
    assert loaded.streams[0].message_count == 100


def test_generate_session_id_with_date():
    p = Path("/data/capture_2025-04-10-14-30-00.bag")
    sid = generate_session_id(p)
    assert "20250410_143000" in sid


def test_generate_session_id_no_date():
    p = Path("/data/my_bag.bag")
    sid = generate_session_id(p)
    assert "my_bag" in sid
