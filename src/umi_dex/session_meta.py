#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Read/write session_meta.json for provenance and per-stream statistics."""

from __future__ import annotations

import hashlib
import json
import platform
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from .timebase import SessionAnchor


@dataclass
class StreamStats:
    """Per-stream output statistics."""

    name: str
    message_count: int = 0
    first_t_ros_ns: Optional[int] = None
    last_t_ros_ns: Optional[int] = None
    rate_hz: Optional[float] = None
    output_file: Optional[str] = None


@dataclass
class SessionMeta:
    """Top-level session metadata, written once per processed session."""

    session_id: str
    bag_path: str
    bag_sha256: Optional[str] = None
    anchor: Optional[SessionAnchor] = None
    hostname: str = field(default_factory=platform.node)
    kernel: str = field(default_factory=platform.release)
    python_version: str = field(default_factory=platform.python_version)
    bag_start_ns: Optional[int] = None
    bag_end_ns: Optional[int] = None
    bag_duration_s: Optional[float] = None
    streams: list[StreamStats] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        d = asdict(self)
        return json.dumps(d, indent=2, default=str)

    def write(self, out_dir: Path) -> Path:
        path = out_dir / "session_meta.json"
        path.write_text(self.to_json(), encoding="utf-8")
        return path

    @classmethod
    def from_json(cls, path: Path) -> "SessionMeta":
        raw = json.loads(path.read_text(encoding="utf-8"))
        anchor_data = raw.pop("anchor", None)
        streams_data = raw.pop("streams", [])
        anchor = SessionAnchor(**anchor_data) if anchor_data else None
        streams = [StreamStats(**s) for s in streams_data]
        return cls(anchor=anchor, streams=streams, **raw)


def compute_bag_sha256(bag_path: Path, chunk_size: int = 1 << 20) -> str:
    """SHA-256 hex digest of a bag file."""
    h = hashlib.sha256()
    with bag_path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def generate_session_id(bag_path: Path) -> str:
    """Generate a session ID from the bag filename and host.

    Format: <UTC_YYYYMMDD_HHMMSS>_<hostname>
    Falls back to the bag stem if the filename doesn't encode a date.
    """
    import re
    stem = bag_path.stem
    match = re.search(r"(\d{4}[-_]?\d{2}[-_]?\d{2}[-_T]?\d{2}[-_:]?\d{2}[-_:]?\d{2})", stem)
    if match:
        digits = re.sub(r"[-_:T]", "", match.group(1))
        date_part = digits[:8] + "_" + digits[8:14]
    else:
        date_part = stem

    host = platform.node() or "unknown"
    return f"{date_part}_{host}"


def write_bag_sha256(sha256: str, out_dir: Path) -> Path:
    """Write the source.bag.sha256 provenance file."""
    path = out_dir / "source.bag.sha256"
    path.write_text(sha256 + "\n", encoding="utf-8")
    return path
