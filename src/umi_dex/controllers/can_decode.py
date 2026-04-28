#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Decode raw CAN 0x112 frames into 6-channel encoder count vectors.

Operates on deserialized bag messages (CanFrame or HandJointState),
not on a live CAN bus.  Mirrors the assembly logic that was in
``controller_capture.py`` and ``ros/umi_dex/can_protocol.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

COUNT_SCALE = 4096.0
CAN_ID_ENC = 0x112
CAN_PART_COUNT = 3
NUM_JOINTS = 6
ASSEMBLY_TTL_NS = 2_000_000_000  # 2 seconds in nanoseconds

JOINT_NAMES: list[str] = [
    "thumb_roll",
    "thumb_pitch",
    "index_pitch",
    "middle_pitch",
    "ring_pitch",
    "pinky_pitch",
]


@dataclass
class _FrameAssembly:
    parts: dict[int, bytes] = field(default_factory=dict)
    first_seen_ns: int = 0


@dataclass
class DecodedSample:
    """A fully assembled and decoded 6-channel sample."""

    t_ros_ns: int
    raw_counts: list[float]
    valid_mask: int


class CanDecoder:
    """Stateful assembler that collects 3-part CAN 0x112 groups from bag messages.

    Feed individual ``CanFrame`` messages via :meth:`feed_can_frame`.
    Each call returns ``None`` until all three parts of a group arrive,
    then returns a :class:`DecodedSample`.
    """

    def __init__(self) -> None:
        self._assemblies: dict[int, _FrameAssembly] = {}

    def _prune_stale(self, now_ns: int) -> None:
        stale = [
            k for k, v in self._assemblies.items()
            if (now_ns - v.first_seen_ns) > ASSEMBLY_TTL_NS
        ]
        for k in stale:
            del self._assemblies[k]

    @staticmethod
    def _assemble_counts(asm: _FrameAssembly) -> tuple[list[float], int]:
        counts = [0.0] * NUM_JOINTS
        valid_mask = int(asm.parts[0][1]) if 0 in asm.parts else 0

        for p in range(CAN_PART_COUNT):
            pb = asm.parts[p]
            raw0 = float(pb[4] | (pb[5] << 8))
            raw1 = float(pb[6] | (pb[7] << 8))
            if p == 0:
                counts[1] = raw0  # thumb_pitch
                counts[0] = raw1  # thumb_roll (swapped)
            else:
                counts[p * 2] = raw0
                counts[p * 2 + 1] = raw1

        return counts, valid_mask

    def feed_can_frame(
        self,
        t_ros_ns: int,
        arb_id: int,
        dlc: int,
        data: bytes | list[int],
    ) -> Optional[DecodedSample]:
        """Feed one raw CAN frame.

        Returns a :class:`DecodedSample` when a complete 3-part group
        has been assembled, otherwise ``None``.
        """
        if arb_id != CAN_ID_ENC or dlc != 8:
            return None

        if isinstance(data, list):
            data = bytes(data)
        if len(data) < 8:
            return None

        part = int(data[0])
        if part not in (0, 1, 2):
            return None
        seq = int(data[2] | (data[3] << 8))

        asm = self._assemblies.get(seq)
        if asm is None:
            asm = _FrameAssembly(first_seen_ns=t_ros_ns)
            self._assemblies[seq] = asm
        asm.parts[part] = bytes(data)

        self._prune_stale(t_ros_ns)

        if len(asm.parts) != CAN_PART_COUNT:
            return None

        counts, valid_mask = self._assemble_counts(asm)
        del self._assemblies[seq]
        return DecodedSample(
            t_ros_ns=t_ros_ns,
            raw_counts=counts,
            valid_mask=valid_mask,
        )
