"""Read-only video metadata and hashing."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import hashlib

import cv2


@dataclass(frozen=True)
class VideoMetadata:
    path: str
    sha256: str
    fps: float
    width: int
    height: int
    frame_count: int
    duration_seconds: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def file_sha256(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_video_metadata(path: str | Path) -> VideoMetadata:
    """Inspect video without altering or transcoding the raw recording."""
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Video does not exist: {source}")
    capture = cv2.VideoCapture(str(source))
    try:
        if not capture.isOpened():
            raise ValueError(f"OpenCV could not open video: {source}")
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        width = int(round(capture.get(cv2.CAP_PROP_FRAME_WIDTH)))
        height = int(round(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        frame_count = int(round(capture.get(cv2.CAP_PROP_FRAME_COUNT)))
    finally:
        capture.release()
    if fps <= 0 or width <= 0 or height <= 0 or frame_count <= 0:
        raise ValueError(
            f"Invalid video metadata (fps={fps}, size={width}x{height}, frames={frame_count})"
        )
    return VideoMetadata(
        path=str(source),
        sha256=file_sha256(source),
        fps=fps,
        width=width,
        height=height,
        frame_count=frame_count,
        duration_seconds=frame_count / fps,
    )

