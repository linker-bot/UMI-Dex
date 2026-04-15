"""CAN 0x112 three-part frame assembly and circular low-pass filter.

Ported from src/umi_dex/controller_capture.py for use in the
ROS1 capture pipeline.  This module has *no* ROS dependency so it can
be unit-tested standalone.
"""

import struct
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

COUNT_SCALE = 4096.0
CAN_ID_ENC = 0x112
CAN_PART_COUNT = 3
ASSEMBLY_TTL_S = 2.0
NUM_JOINTS = 6
JOINT_NAMES = [
    "thumb_roll",
    "thumb_pitch",
    "index_pitch",
    "middle_pitch",
    "ring_pitch",
    "pinky_pitch",
]


@dataclass
class FrameAssembly:
    parts: Dict[int, bytes] = field(default_factory=dict)
    first_seen_s: float = 0.0


class CanAssembler:
    """Collects CAN 0x112 frames and emits complete 6-channel count vectors."""

    def __init__(self) -> None:
        self._assemblies: Dict[int, FrameAssembly] = {}

    def _prune_stale(self, now_s: float) -> None:
        stale = [
            k for k, v in self._assemblies.items()
            if (now_s - v.first_seen_s) > ASSEMBLY_TTL_S
        ]
        for k in stale:
            del self._assemblies[k]

    @staticmethod
    def _assemble_counts(asm: FrameAssembly) -> Tuple[List[float], int]:
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

    def feed(self, arb_id: int, dlc: int, data: bytes) -> Optional[Tuple[List[float], int]]:
        """Feed a single CAN frame.  Returns (counts, valid_mask) when a
        complete 3-part group is assembled, else None."""
        if arb_id != CAN_ID_ENC or dlc != 8 or len(data) < 8:
            return None

        part = int(data[0])
        if part not in (0, 1, 2):
            return None
        seq = int(data[2] | (data[3] << 8))

        now_s = time.monotonic()
        asm = self._assemblies.get(seq)
        if asm is None:
            asm = FrameAssembly(first_seen_s=now_s)
            self._assemblies[seq] = asm
        asm.parts[part] = bytes(data)

        self._prune_stale(now_s)

        if len(asm.parts) != CAN_PART_COUNT:
            return None
        counts, valid_mask = self._assemble_counts(asm)
        del self._assemblies[seq]
        return counts, valid_mask


class CircularFilter:
    """Per-channel exponential low-pass filter that handles wrap-around."""

    def __init__(self, alpha: float = 0.3, wrapped_channels: Optional[set] = None):
        self.alpha = alpha
        self._wrapped = wrapped_channels or set()
        self._state: Optional[List[float]] = None

    @staticmethod
    def _blend_circular(prev: float, cur: float, alpha: float) -> float:
        delta = (cur - prev) % COUNT_SCALE
        if delta > COUNT_SCALE / 2.0:
            delta -= COUNT_SCALE
        return (prev + alpha * delta) % COUNT_SCALE

    def apply(self, raw: List[float], valid_mask: int) -> List[float]:
        if self._state is None:
            self._state = list(raw)
            return list(raw)

        for i in range(NUM_JOINTS):
            if not (valid_mask & (1 << i)):
                continue
            if i in self._wrapped:
                self._state[i] = self._blend_circular(self._state[i], raw[i], self.alpha)
            else:
                self._state[i] = self.alpha * raw[i] + (1.0 - self.alpha) * self._state[i]

        return list(self._state)
