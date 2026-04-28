#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Episode extraction from ``/session/episode`` markers in a ROS bag.

The interactive_capture_node publishes ``std_msgs/String`` markers:

- ``warmup_start``
- ``warmup_end``
- ``episode_start:<id>``
- ``episode_end:<id>``
- ``episode_discard:<id>``

This module parses those markers into time intervals, and provides a
filter to restrict any timestamp-indexed DataFrame to a single episode.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .bag_reader import BagReader
from .timebase import ros_ns_to_iso


@dataclass
class EpisodeInterval:
    """A single episode's time span and status."""

    episode_id: int
    start_ns: int
    end_ns: Optional[int] = None
    status: str = "recording"  # kept | discarded | recording (incomplete)

    @property
    def duration_s(self) -> Optional[float]:
        if self.end_ns is not None:
            return (self.end_ns - self.start_ns) / 1e9
        return None


def extract_episodes(reader: BagReader) -> list[EpisodeInterval]:
    """Read ``/session/episode`` from *reader* and return episode intervals.

    Episodes with ``episode_discard`` are marked as discarded; episodes
    that were cleanly ended are marked as ``kept``; episodes that were
    never ended are left as ``recording`` (incomplete).
    """
    available = reader.available_topics()
    if "/session/episode" not in available:
        return []

    episodes: dict[int, EpisodeInterval] = {}

    for sm in reader.read_topic("/session/episode"):
        text: str = sm.msg.data
        if text.startswith("episode_start:"):
            eid = int(text.split(":", 1)[1])
            episodes[eid] = EpisodeInterval(
                episode_id=eid, start_ns=sm.t_ros_ns, status="recording"
            )
        elif text.startswith("episode_end:"):
            eid = int(text.split(":", 1)[1])
            if eid in episodes:
                episodes[eid].end_ns = sm.t_ros_ns
                episodes[eid].status = "kept"
        elif text.startswith("episode_discard:"):
            eid = int(text.split(":", 1)[1])
            if eid in episodes:
                episodes[eid].end_ns = sm.t_ros_ns
                episodes[eid].status = "discarded"

    return sorted(episodes.values(), key=lambda e: e.episode_id)


def kept_episodes(episodes: list[EpisodeInterval]) -> list[EpisodeInterval]:
    """Return only episodes with status ``kept``."""
    return [e for e in episodes if e.status == "kept"]


def write_episodes_csv(episodes: list[EpisodeInterval], out_dir: Path) -> Path:
    """Write ``episodes.csv`` summarising all episodes."""
    csv_path = out_dir / "episodes.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "episode_id", "status",
            "start_ns", "end_ns",
            "start_iso", "end_iso",
            "duration_s",
        ])
        for ep in episodes:
            w.writerow([
                ep.episode_id,
                ep.status,
                ep.start_ns,
                ep.end_ns if ep.end_ns is not None else "",
                ros_ns_to_iso(ep.start_ns),
                ros_ns_to_iso(ep.end_ns) if ep.end_ns is not None else "",
                f"{ep.duration_s:.3f}" if ep.duration_s is not None else "",
            ])
    return csv_path


def filter_rows_by_episode(
    timestamps_ns: list[int],
    episode: EpisodeInterval,
) -> list[int]:
    """Return indices into *timestamps_ns* that fall within *episode*.

    If the episode has no ``end_ns``, all timestamps after ``start_ns``
    are included.
    """
    indices: list[int] = []
    for i, t in enumerate(timestamps_ns):
        if t < episode.start_ns:
            continue
        if episode.end_ns is not None and t > episode.end_ns:
            continue
        indices.append(i)
    return indices


def episode_id_for_timestamp(
    t_ns: int,
    episodes: list[EpisodeInterval],
) -> int:
    """Return the episode_id that contains *t_ns*, or -1 if none match.

    Only considers ``kept`` episodes.
    """
    for ep in episodes:
        if ep.status != "kept":
            continue
        if t_ns < ep.start_ns:
            continue
        if ep.end_ns is not None and t_ns > ep.end_ns:
            continue
        return ep.episode_id
    return -1
