"""Transparent file models for raw pose, corrections, outcomes, and events."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
import json

CameraView = Literal["side", "front", "other"]
ThrowingSide = Literal["left", "right"]
TargetDirection = Literal["left_to_right", "right_to_left"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class PointEstimate:
    """A model-estimated image point; confidence is not a physical error bound."""

    x: float | None
    y: float | None
    confidence: float

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PointEstimate":
        return cls(value.get("x"), value.get("y"), float(value.get("confidence", 0.0)))


@dataclass(frozen=True)
class PoseFrame:
    frame_index: int
    time_seconds: float
    landmarks: dict[str, PointEstimate]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PoseFrame":
        return cls(
            frame_index=int(value["frame_index"]),
            time_seconds=float(value["time_seconds"]),
            landmarks={k: PointEstimate.from_dict(v) for k, v in value["landmarks"].items()},
        )


@dataclass
class PoseSequence:
    schema_version: int
    fps: float
    width: int
    height: int
    frame_count: int
    backend: str
    model_name: str
    model_version: str
    frames: list[PoseFrame]
    model_sha256: str | None = None
    backend_metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PoseSequence":
        return cls(
            schema_version=int(value.get("schema_version", 1)),
            fps=float(value["fps"]),
            width=int(value["width"]),
            height=int(value["height"]),
            frame_count=int(value["frame_count"]),
            backend=str(value["backend"]),
            model_name=str(value["model_name"]),
            model_version=str(value.get("model_version", "unknown")),
            model_sha256=value.get("model_sha256"),
            frames=[PoseFrame.from_dict(v) for v in value["frames"]],
            backend_metadata=value.get("backend_metadata", {}),
        )

    @classmethod
    def load(cls, path: str | Path) -> "PoseSequence":
        return cls.from_dict(json.loads(Path(path).read_text()))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=2, allow_nan=False) + "\n")


@dataclass(frozen=True)
class PointCorrection:
    frame_index: int
    landmark: str
    x: float
    y: float
    kind: Literal["manual", "interpolated"] = "manual"
    created_at: str = field(default_factory=utc_now)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PointCorrection":
        return cls(
            frame_index=int(value["frame_index"]),
            landmark=str(value["landmark"]),
            x=float(value["x"]),
            y=float(value["y"]),
            kind=value.get("kind", "manual"),
            created_at=value.get("created_at", utc_now()),
        )


@dataclass
class CorrectionSet:
    schema_version: int = 1
    corrections: list[PointCorrection] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path | None) -> "CorrectionSet":
        if path is None or not Path(path).exists():
            return cls()
        value = json.loads(Path(path).read_text())
        return cls(
            schema_version=int(value.get("schema_version", 1)),
            corrections=[PointCorrection.from_dict(v) for v in value.get("corrections", [])],
        )

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=2) + "\n")


@dataclass
class EventValue:
    name: str
    automatic_frame: int | None = None
    automatic_confidence: float | None = None
    automatic_method: str | None = None
    manual_frame: int | None = None
    suppressed_reason: str | None = None

    @property
    def effective_frame(self) -> int | None:
        return self.manual_frame if self.manual_frame is not None else (None if self.suppressed_reason else self.automatic_frame)


@dataclass
class TrialContext:
    trial_id: str
    athlete_id: str
    camera_view: CameraView
    throwing_side: ThrowingSide
    target_direction: TargetDirection
    source_video: str
    source_url: str | None = None
    source_attribution: str | None = None
    # yyyy-mm-dd the camera recorded the clip (QuickTime creation date of the original take); used to
    # group throws into recording sessions instead of the clip file's modification date.
    recording_date: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "TrialContext":
        return cls(**{k: value.get(k) for k in cls.__dataclass_fields__})


@dataclass
class BoardPoint:
    x_inches: float
    y_inches: float
    precision: str = "approximate_manual_click"


@dataclass
class TrialOutcome:
    intended_target: str
    score_category: Literal[0, 1, 3] | None
    throw_type: str
    notes: str = ""
    intended_point: BoardPoint | None = None
    first_contact_point: BoardPoint | None = None
    final_resting_point: BoardPoint | None = None
