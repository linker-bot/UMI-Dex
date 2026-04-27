#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bag reader built on the ``rosbags`` library (no ROS install required).

Supports both ROS1 ``.bag`` files and ROS2 bag directories (mcap/sqlite3).
Auto-detects the format based on whether the path is a file or a directory
containing ``metadata.yaml``.

Provides per-topic stamped iterators and topic discovery / statistics
for the umi-inspect CLI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional, Union

from rosbags.rosbag1 import Reader as Rosbag1Reader
from rosbags.rosbag2 import Reader as Rosbag2Reader
from rosbags.serde import deserialize_cdr, ros1_to_cdr
from rosbags.typesys import Stores, get_typestore

from .timebase import stamp_to_ns

_CANFRAME_FIELDS = (
    [],
    [
        ("header", "std_msgs/msg/Header"),
        ("arb_id", "uint32"),
        ("dlc", "uint8"),
        ("data", "uint8[8]"),
    ],
)

_HANDJOINTSTATE_FIELDS = (
    [],
    [
        ("header", "std_msgs/msg/Header"),
        ("names", "string[6]"),
        ("positions", "float64[6]"),
        ("valid", "bool[6]"),
    ],
)


def _detect_bag_version(bag_path: Path) -> int:
    """Return 1 for ROS1 .bag, 2 for ROS2 bag directory."""
    if bag_path.is_file() and bag_path.suffix == ".bag":
        return 1
    if bag_path.is_dir() and (bag_path / "metadata.yaml").exists():
        return 2
    raise ValueError(
        f"Cannot detect bag format for {bag_path}. "
        "Expected a .bag file or a directory containing metadata.yaml."
    )


def _build_typestore(version: int) -> Any:
    """Build a type store for the given ROS version."""
    if version == 1:
        return get_typestore(Stores.ROS1_NOETIC)
    return get_typestore(Stores.ROS2_JAZZY)


def _register_custom_types(typestore: Any, version: int) -> None:
    """Register custom umi_dex / umi_dex_msgs message types."""
    try:
        if version == 1:
            typestore.register({
                "umi_dex/msg/CanFrame": _CANFRAME_FIELDS,
                "umi_dex/msg/HandJointState": _HANDJOINTSTATE_FIELDS,
            })
        else:
            typestore.register({
                "umi_dex_msgs/msg/CanFrame": _CANFRAME_FIELDS,
                "umi_dex_msgs/msg/HandJointState": _HANDJOINTSTATE_FIELDS,
            })
    except Exception:
        pass


@dataclass
class TopicStats:
    """Per-topic summary statistics."""

    name: str
    msgtype: str
    count: int = 0
    first_ns: Optional[int] = None
    last_ns: Optional[int] = None
    rate_hz: Optional[float] = None

    @property
    def duration_s(self) -> Optional[float]:
        if self.first_ns is not None and self.last_ns is not None:
            return (self.last_ns - self.first_ns) / 1e9
        return None


@dataclass
class BagSummary:
    """Aggregate summary of a bag file."""

    path: Path
    duration_s: float
    start_ns: int
    end_ns: int
    message_count: int
    topics: list[TopicStats] = field(default_factory=list)


@dataclass
class StampedMessage:
    """A single message with its ROS header timestamp in nanoseconds."""

    t_ros_ns: int
    topic: str
    msg: Any


class BagReader:
    """Read a ROS1 or ROS2 bag using the ``rosbags`` library.

    Auto-detects the bag version from the path:
    - File ending in ``.bag`` -> ROS1
    - Directory with ``metadata.yaml`` -> ROS2 (mcap / sqlite3)

    Usage::

        reader = BagReader(Path("capture.bag"))      # ROS1
        reader = BagReader(Path("capture_bag_dir"))   # ROS2
        for sm in reader.read_messages("/camera/infra1/image_rect_raw"):
            print(sm.t_ros_ns, sm.msg.width, sm.msg.height)
        reader.close()
    """

    KNOWN_TOPICS = {
        "d455_ir1": "/camera/infra1/image_rect_raw",
        "d455_ir1_info": "/camera/infra1/camera_info",
        "d455_ir2": "/camera/infra2/image_rect_raw",
        "d455_ir2_info": "/camera/infra2/camera_info",
        "d455_imu": "/camera/imu",
        "d405_color": "/camera_d405/color/image_raw",
        "d405_color_info": "/camera_d405/color/camera_info",
        "hand_can_raw": "/hand/can_raw",
        "hand_joint_states": "/hand/joint_states",
        "session_episode": "/session/episode",
    }

    def __init__(self, bag_path: Path) -> None:
        self.bag_path = bag_path.resolve()
        self._version = _detect_bag_version(self.bag_path)

        if self._version == 1:
            self._reader: Union[Rosbag1Reader, Rosbag2Reader] = (
                Rosbag1Reader(self.bag_path)
            )
        else:
            self._reader = Rosbag2Reader(self.bag_path)

        self._reader.open()
        self._typestore = _build_typestore(self._version)
        _register_custom_types(self._typestore, self._version)

    @property
    def version(self) -> int:
        """Return 1 for ROS1 bags, 2 for ROS2 bags."""
        return self._version

    def close(self) -> None:
        self._reader.close()

    def __enter__(self) -> "BagReader":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    @property
    def connections(self) -> list[Any]:
        return list(self._reader.connections)

    @property
    def start_ns(self) -> int:
        return self._reader.start_time

    @property
    def end_ns(self) -> int:
        return self._reader.end_time

    @property
    def duration_s(self) -> float:
        return (self.end_ns - self.start_ns) / 1e9

    @property
    def message_count(self) -> int:
        return self._reader.message_count

    def available_topics(self) -> dict[str, str]:
        """Return {topic_name: msg_type} for all topics in the bag."""
        return {c.topic: c.msgtype for c in self._reader.connections}

    def summarize(self) -> BagSummary:
        """Compute per-topic stats by iterating through the bag."""
        topic_map: dict[str, TopicStats] = {}
        for c in self._reader.connections:
            if c.topic not in topic_map:
                topic_map[c.topic] = TopicStats(name=c.topic, msgtype=c.msgtype)

        for conn, timestamp, _rawdata in self._reader.messages():
            ts = topic_map.get(conn.topic)
            if ts is None:
                continue
            ts.count += 1
            if ts.first_ns is None or timestamp < ts.first_ns:
                ts.first_ns = timestamp
            if ts.last_ns is None or timestamp > ts.last_ns:
                ts.last_ns = timestamp

        for ts in topic_map.values():
            dur = ts.duration_s
            if dur is not None and dur > 0 and ts.count > 1:
                ts.rate_hz = (ts.count - 1) / dur

        topics = sorted(topic_map.values(), key=lambda t: t.name)
        return BagSummary(
            path=self.bag_path,
            duration_s=self.duration_s,
            start_ns=self.start_ns,
            end_ns=self.end_ns,
            message_count=self.message_count,
            topics=topics,
        )

    def read_messages(
        self,
        topics: Optional[list[str]] = None,
    ) -> Iterator[StampedMessage]:
        """Yield StampedMessage for the given topics (or all if None).

        The timestamp is the bag-level connection timestamp (nanoseconds).
        """
        conns = [
            c for c in self._reader.connections
            if topics is None or c.topic in topics
        ]
        if not conns:
            return

        for conn, timestamp, rawdata in self._reader.messages(connections=conns):
            try:
                if self._version == 1:
                    cdr = ros1_to_cdr(rawdata, conn.msgtype)
                else:
                    cdr = rawdata
                msg = deserialize_cdr(cdr, conn.msgtype, self._typestore)
            except Exception:
                continue
            yield StampedMessage(
                t_ros_ns=timestamp,
                topic=conn.topic,
                msg=msg,
            )

    def read_topic(self, topic: str) -> Iterator[StampedMessage]:
        """Convenience: iterate a single topic."""
        yield from self.read_messages(topics=[topic])
