#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""H.264 video encoder for D405 color frames extracted from a bag.

Uses PyAV (libav/FFmpeg) to produce an MP4 with per-frame PTS derived
from bag timestamps.  Writes a sidecar ``d405_color_frames.csv`` with
the mapping ``(idx, t_ros_ns, t_iso, pts_ns)``.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterator

import av
import numpy as np

from ..timebase import ros_ns_to_iso


def _image_msg_to_ndarray(msg: object) -> np.ndarray:
    """Convert a deserialized sensor_msgs/Image to a numpy BGR array.

    Supports ``rgb8``, ``bgr8``, ``mono8`` encodings.
    """
    encoding = str(msg.encoding).lower()
    h, w = int(msg.height), int(msg.width)
    raw = bytes(msg.data)

    if encoding in ("rgb8",):
        arr = np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 3)
        return arr[:, :, ::-1]  # RGB -> BGR for OpenCV/av convention
    elif encoding in ("bgr8",):
        return np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 3)
    elif encoding in ("mono8",):
        mono = np.frombuffer(raw, dtype=np.uint8).reshape(h, w)
        return np.stack([mono, mono, mono], axis=-1)
    else:
        arr = np.frombuffer(raw, dtype=np.uint8).reshape(h, w, -1)
        if arr.shape[2] >= 3:
            return arr[:, :, :3]
        return np.stack([arr[:, :, 0]] * 3, axis=-1)


def encode_d405_from_messages(
    messages: Iterator[tuple[int, object]],
    out_dir: Path,
    fps: int = 30,
    codec: str = "libx264",
    pix_fmt: str = "yuv420p",
    crf: int = 18,
) -> tuple[Path, Path, int]:
    """Encode D405 color frames from bag messages to H.264 MP4.

    Parameters
    ----------
    messages:
        Iterator of ``(t_ros_ns, image_msg)`` pairs.
    out_dir:
        Directory for output files.
    fps:
        Nominal frame rate (used for container timebase).
    codec:
        FFmpeg encoder name.
    pix_fmt:
        Pixel format for the encoder.
    crf:
        Constant rate factor (quality).

    Returns
    -------
    (mp4_path, csv_path, frame_count)
    """
    mp4_path = out_dir / "d405_color.mp4"
    csv_path = out_dir / "d405_color_frames.csv"

    container = None
    stream = None
    csv_f = csv_path.open("w", newline="", encoding="utf-8")
    csv_w = csv.writer(csv_f)
    csv_w.writerow(["idx", "t_ros_ns", "t_iso", "pts_ns"])

    session_start_ns: int | None = None
    frame_count = 0

    try:
        for t_ros_ns, img_msg in messages:
            bgr = _image_msg_to_ndarray(img_msg)

            if container is None:
                h, w = bgr.shape[:2]
                container = av.open(str(mp4_path), mode="w")
                stream = container.add_stream(codec, rate=fps)
                stream.width = w
                stream.height = h
                stream.pix_fmt = pix_fmt
                stream.options = {"crf": str(crf)}
                stream.time_base = av.Fraction(1, 1_000_000_000)
                session_start_ns = t_ros_ns

            pts_ns = t_ros_ns - session_start_ns
            frame = av.VideoFrame.from_ndarray(bgr, format="bgr24")
            frame.pts = pts_ns
            frame.time_base = av.Fraction(1, 1_000_000_000)

            for packet in stream.encode(frame):
                container.mux(packet)

            csv_w.writerow([frame_count, t_ros_ns, ros_ns_to_iso(t_ros_ns), pts_ns])
            frame_count += 1

        if stream is not None:
            for packet in stream.encode():
                container.mux(packet)
    finally:
        csv_f.close()
        if container is not None:
            container.close()

    return mp4_path, csv_path, frame_count
