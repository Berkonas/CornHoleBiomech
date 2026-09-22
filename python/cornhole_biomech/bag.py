"""Transparent semi-automatic bag tracking and projected release kinematics.

The automatic tracker output, manual corrections, and derived/interpolated points
remain separate. Tracker quality values are appearance-consistency heuristics, not
calibrated probabilities or physical position-error bounds.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import json
import math

import cv2
import numpy as np

from .corrections import interpolate_short_gaps
from .filtering import _finite_runs
from .models import EventValue, utc_now
from .serialization import json_ready, write_json
from .video import file_sha256, read_video_metadata


BAG_COORDINATE_SYSTEM = "raw_video_pixels_x_right_y_down"
ANALYSIS_COORDINATE_SYSTEM = "target_forward_x_up_y"


@dataclass(frozen=True)
class BagSeed:
    """User-selected tracker rectangle on one source-video frame."""

    frame_index: int
    bbox_xywh: tuple[float, float, float, float]
    source: str = "manual_bbox"

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "BagSeed":
        bbox = value.get("bbox_xywh", value.get("bbox"))
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            raise ValueError("Bag seed requires bbox_xywh = [x, y, width, height]")
        seed = cls(
            frame_index=int(value["frame_index"]),
            bbox_xywh=tuple(float(item) for item in bbox),
            source=str(value.get("source", "manual_bbox")),
        )
        if not all(math.isfinite(item) for item in seed.bbox_xywh):
            raise ValueError("Bag seed rectangle must contain finite values")
        if seed.bbox_xywh[2] <= 1 or seed.bbox_xywh[3] <= 1:
            raise ValueError("Bag seed rectangle must be larger than one pixel")
        return seed

    @classmethod
    def load(cls, path: str | Path) -> "BagSeed":
        return cls.from_dict(json.loads(Path(path).read_text()))


@dataclass(frozen=True)
class BagAutomaticPoint:
    frame_index: int
    x: float | None
    y: float | None
    confidence: float
    bbox_xywh: tuple[float, float, float, float] | None = None
    status: str = "tracked"

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "BagAutomaticPoint":
        bbox = value.get("bbox_xywh")
        point = cls(
            frame_index=int(value["frame_index"]),
            x=None if value.get("x") is None else float(value["x"]),
            y=None if value.get("y") is None else float(value["y"]),
            confidence=float(value.get("confidence", 0.0)),
            bbox_xywh=None if bbox is None else tuple(float(item) for item in bbox),
            status=str(value.get("status", "tracked")),
        )
        if not 0.0 <= point.confidence <= 1.0:
            raise ValueError("Bag tracker confidence/quality must be between 0 and 1")
        return point


@dataclass(frozen=True)
class BagCorrection:
    frame_index: int
    x: float
    y: float
    kind: str = "manual"
    created_at: str = field(default_factory=utc_now)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "BagCorrection":
        kind = str(value.get("kind", "manual"))
        if kind not in {"manual", "interpolated"}:
            raise ValueError("Bag correction kind must be manual or interpolated")
        return cls(
            frame_index=int(value["frame_index"]),
            x=float(value["x"]),
            y=float(value["y"]),
            kind=kind,
            created_at=str(value.get("created_at", utc_now())),
        )


@dataclass
class BagCorrectionSet:
    schema_version: int = 1
    corrections: list[BagCorrection] = field(default_factory=list)
    reviewed_through_frame: int | None = None
    reviewed_at: str | None = None
    review_note: str | None = None

    @classmethod
    def load(cls, path: str | Path | None) -> "BagCorrectionSet":
        if path is None or not Path(path).exists():
            return cls()
        value = json.loads(Path(path).read_text())
        version = int(value.get("schema_version", 1))
        if version != 1:
            raise ValueError(f"Unsupported bag-correction schema version: {version}")
        reviewed_through_frame = value.get("reviewed_through_frame")
        if reviewed_through_frame is not None:
            reviewed_through_frame = int(reviewed_through_frame)
            if reviewed_through_frame < 0:
                raise ValueError("Bag reviewed-through frame cannot be negative")
        return cls(
            schema_version=version,
            corrections=[BagCorrection.from_dict(item) for item in value.get("corrections", [])],
            reviewed_through_frame=reviewed_through_frame,
            reviewed_at=value.get("reviewed_at"),
            review_note=value.get("review_note"),
        )

    def covers(self, frame_index: int | None) -> bool:
        return (
            frame_index is not None
            and self.reviewed_through_frame is not None
            and self.reviewed_through_frame >= frame_index
        )

    def save(self, path: str | Path) -> None:
        write_json(path, self)


@dataclass
class BagTrack:
    """Immutable automatic tracking output produced from a manual seed."""

    schema_version: int
    frame_count: int
    width: int
    height: int
    source_video_sha256: str
    seed: BagSeed
    requested_method: str
    effective_method: str
    automatic_points: list[BagAutomaticPoint]
    status: str
    failure_frames: list[int] = field(default_factory=list)
    fallback_reason: str | None = None
    coordinate_system: str = BAG_COORDINATE_SYSTEM
    units: str = "pixels"
    quality_note: str = (
        "Tracker confidence is an uncalibrated appearance-consistency score; "
        "manual review determines whether the bag identity is correct."
    )
    created_at: str = field(default_factory=utc_now)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "BagTrack":
        version = int(value.get("schema_version", 1))
        if version != 1:
            raise ValueError(f"Unsupported bag-track schema version: {version}")
        raw_seed = value.get("seed")
        if not isinstance(raw_seed, dict):
            raise ValueError("Bag track is missing its manual seed provenance")
        points = value.get("automatic_points", value.get("points", []))
        return cls(
            schema_version=version,
            frame_count=int(value["frame_count"]),
            width=int(value["width"]),
            height=int(value["height"]),
            source_video_sha256=str(value.get("source_video_sha256", "")),
            seed=BagSeed.from_dict(raw_seed),
            requested_method=str(value.get("requested_method", "unknown")),
            effective_method=str(value.get("effective_method", "unknown")),
            automatic_points=[BagAutomaticPoint.from_dict(item) for item in points],
            status=str(value.get("status", "unknown")),
            failure_frames=[int(item) for item in value.get("failure_frames", [])],
            fallback_reason=value.get("fallback_reason"),
            coordinate_system=str(value.get("coordinate_system", BAG_COORDINATE_SYSTEM)),
            units=str(value.get("units", "pixels")),
            quality_note=str(value.get("quality_note", cls.__dataclass_fields__["quality_note"].default)),
            created_at=str(value.get("created_at", utc_now())),
        )

    @classmethod
    def load(cls, path: str | Path) -> "BagTrack":
        return cls.from_dict(json.loads(Path(path).read_text()))

    def save(self, path: str | Path) -> None:
        write_json(path, self)


@dataclass(frozen=True)
class SpatialCalibration:
    """Explicit image scale valid in the athlete/release motion plane only."""

    pixels_per_meter: float
    plane: str
    valid: bool
    source: str
    schema_version: int = 1

    known_length_m: float | None = None
    observed_length_px: float | None = None
    frame_index: int | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SpatialCalibration":
        version = int(value.get("schema_version", 1))
        if version != 1:
            raise ValueError(f"Unsupported calibration schema version: {version}")
        return cls(
            pixels_per_meter=float(value["pixels_per_meter"]),
            plane=str(value.get("plane", "")),
            valid=bool(value.get("valid", False)),
            source=str(value.get("source", "unspecified")),
            schema_version=version,
            known_length_m=value.get("known_length_m"),
            observed_length_px=value.get("observed_length_px"),
            frame_index=value.get("frame_index"),
        )

    @classmethod
    def load(cls, path: str | Path | None) -> "SpatialCalibration | None":
        if path is None:
            return None
        return cls.from_dict(json.loads(Path(path).read_text()))

    @property
    def permits_physical_units(self) -> bool:
        return (
            self.valid
            and self.plane == "athlete_release_motion_plane"
            and math.isfinite(self.pixels_per_meter)
            and self.pixels_per_meter > 0
        )


def _bounded_bbox(bbox: tuple[float, float, float, float], width: int, height: int) -> tuple[float, float, float, float]:
    x, y, w, h = bbox
    if not all(math.isfinite(v) for v in bbox) or w <= 1 or h <= 1:
        raise ValueError("Bag rectangle is invalid")
    # Intersect with the frame; never relocate an offscreen box to the edge.
    x1, y1 = min(float(width), x+w), min(float(height), y+h)
    x, y = max(0.0, x), max(0.0, y)
    w, h = x1-x, y1-y
    if w <= 1 or h <= 1:
        raise ValueError("Bag rectangle lies outside the video image")
    return x, y, w, h


def _crop(image: np.ndarray, bbox: tuple[float, float, float, float]) -> np.ndarray | None:
    x, y, w, h = bbox
    x0, y0 = max(0, int(round(x))), max(0, int(round(y)))
    x1, y1 = min(image.shape[1], int(round(x + w))), min(image.shape[0], int(round(y + h)))
    if x1 <= x0 or y1 <= y0:
        return None
    return image[y0:y1, x0:x1]


def _appearance_score(template: np.ndarray, image: np.ndarray, bbox: tuple[float, float, float, float]) -> float:
    patch = _crop(image, bbox)
    if patch is None or patch.size == 0 or template.size == 0:
        return 0.0
    patch = cv2.resize(patch, (template.shape[1], template.shape[0]), interpolation=cv2.INTER_AREA)
    a = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY).astype(float)
    b = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY).astype(float)
    if np.std(a) > 1e-6 and np.std(b) > 1e-6:
        correlation = float(np.corrcoef(a.ravel(), b.ravel())[0, 1])
        if math.isfinite(correlation):
            return float(np.clip((correlation + 1.0) / 2.0, 0.0, 1.0))
    return float(np.clip(1.0 - np.mean(np.abs(a - b)) / 255.0, 0.0, 1.0))


def _csrt_factory():
    factory = getattr(cv2, "TrackerCSRT_create", None)
    if factory is not None:
        return factory
    legacy = getattr(cv2, "legacy", None)
    return getattr(legacy, "TrackerCSRT_create", None) if legacy is not None else None


def _template_update(
    template: np.ndarray,
    image: np.ndarray,
    previous: tuple[float, float, float, float],
    search_scale: float,
) -> tuple[tuple[float, float, float, float], float] | None:
    x, y, w, h = previous
    margin_x, margin_y = search_scale * w, search_scale * h
    sx0 = max(0, int(math.floor(x - margin_x)))
    sy0 = max(0, int(math.floor(y - margin_y)))
    sx1 = min(image.shape[1], int(math.ceil(x + w + margin_x)))
    sy1 = min(image.shape[0], int(math.ceil(y + h + margin_y)))
    search = image[sy0:sy1, sx0:sx1]
    if search.shape[0] < template.shape[0] or search.shape[1] < template.shape[1]:
        return None
    search_gray = cv2.cvtColor(search, cv2.COLOR_BGR2GRAY)
    template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    if float(np.std(template_gray)) < 1e-6:
        response = cv2.matchTemplate(search_gray, template_gray, cv2.TM_SQDIFF_NORMED)
        minimum, _, minimum_location, _ = cv2.minMaxLoc(response)
        location, quality = minimum_location, 1.0 - float(minimum)
    else:
        response = cv2.matchTemplate(search_gray, template_gray, cv2.TM_CCOEFF_NORMED)
        _, maximum, _, maximum_location = cv2.minMaxLoc(response)
        location, quality = maximum_location, float(maximum)
    return (float(sx0 + location[0]), float(sy0 + location[1]), float(w), float(h)), float(np.clip(quality, 0.0, 1.0))


BAG_TRACKER_REVISION = "color_motion_v1"


def _seed_color_model(template):
    """Circular HSV hue from saturated seed pixels; no hard-coded bag color."""
    hsv = cv2.cvtColor(template, cv2.COLOR_BGR2HSV)
    usable = (hsv[...,1] >= 65) & (hsv[...,2] >= 35)
    if usable.sum() < max(8, template.shape[0]*template.shape[1]*0.03):
        return None
    yy,xx = np.indices(usable.shape)
    spatial = np.exp(-0.5*(((xx-(template.shape[1]-1)/2)/max(1,template.shape[1]*0.22))**2
                           +((yy-(template.shape[0]-1)/2)/max(1,template.shape[0]*0.22))**2))
    histogram = np.bincount(hsv[...,0][usable], weights=(hsv[...,1].astype(float)**2*spatial)[usable], minlength=180)
    smooth = sum(np.roll(histogram, offset) for offset in range(-6,7))
    hue = int(np.argmax(smooth))
    delta = np.abs(hsv[...,0].astype(float)-hue)
    selected = usable & (np.minimum(delta,180-delta) <= 12)
    central = (((xx-(template.shape[1]-1)/2)/max(1,template.shape[1]*0.25))**2
               +((yy-(template.shape[0]-1)/2)/max(1,template.shape[0]*0.25))**2) <= 1
    if selected.sum() < 8 or np.count_nonzero(selected & central) < max(3,0.2*np.count_nonzero(central)):
        return None
    return hue, max(45.,float(np.median(hsv[...,1][selected]))*0.45), float(selected.sum())


def _color_motion_candidate(image, center, radius, model, previous_mask=None):
    hue, saturation, seed_area = model
    x0,y0 = max(0,int(center[0]-radius)),max(0,int(center[1]-radius))
    x1,y1 = min(image.shape[1],int(center[0]+radius)+1),min(image.shape[0],int(center[1]+radius)+1)
    if x1 <= x0 or y1 <= y0: return None
    hsv=cv2.cvtColor(image[y0:y1,x0:x1],cv2.COLOR_BGR2HSV)
    delta=np.abs(hsv[...,0].astype(float)-hue)
    mask=((np.minimum(delta,180-delta)<=12)&(hsv[...,1]>=saturation)&(hsv[...,2]>=30)).astype(np.uint8)
    count, labels, stats, centroids=cv2.connectedComponentsWithStats(mask,8)
    best=None
    for i in range(1,count):
        area=float(stats[i,cv2.CC_STAT_AREA])
        if not max(3,seed_area*0.08)<=area<=seed_area*5: continue
        x,y=centroids[i]+np.array([x0,y0])
        distance=math.hypot(x-center[0],y-center[1])
        if distance>radius: continue
        if previous_mask is not None:
            component = labels == i
            occupied_before = np.count_nonzero(previous_mask[y0:y1,x0:x1][component])
            if 1-occupied_before/area < 0.15:
                continue  # Static same-colored fixtures are not a moving bag.
        size_score=min(area,seed_area)/max(area,seed_area)
        quality=math.exp(-0.5*(distance/max(8,radius*0.45))**2)*size_score**0.25
        if best is None or quality>best[1]:
            # Position is the component centroid; bounding box is retained for QA.
            box=(float(x0+stats[i,0]),float(y0+stats[i,1]),float(max(2,stats[i,2])),float(max(2,stats[i,3])))
            best=(box,float(quality),(float(x),float(y)))
    return best


def track_bag_from_seed(
    video_path: str | Path,
    seed: BagSeed,
    requested_method: str = "auto",
    template_quality_threshold: float = 0.25,
    search_scale: float = 2.5,
    progress=None,
) -> BagTrack:
    """Track forward from a manual rectangle without changing the source video.

    ``auto`` uses seed-color segmentation with constant-velocity search when the
    selected bag has distinct color; otherwise it uses OpenCV CSRT when available. If it is unavailable, a local
    template-matching fallback is selected and the reason is saved explicitly.
    A specifically requested unavailable method fails instead of substituting.
    """
    if requested_method not in {"auto", "csrt", "template_matching", "color_motion"}:
        raise ValueError("Bag tracker method must be auto, color_motion, csrt, or template_matching")
    if not 0.0 <= template_quality_threshold <= 1.0:
        raise ValueError("Template tracker quality threshold must be between 0 and 1")
    if search_scale <= 0:
        raise ValueError("Template tracker search scale must be positive")
    metadata = read_video_metadata(video_path)
    if not 0 <= seed.frame_index < metadata.frame_count:
        raise ValueError(f"Bag seed frame must be between 0 and {metadata.frame_count - 1}")
    bbox = _bounded_bbox(seed.bbox_xywh, metadata.width, metadata.height)
    capture = cv2.VideoCapture(metadata.path)
    if not capture.isOpened():
        raise ValueError("OpenCV could not open the source video for bag tracking")
    capture.set(cv2.CAP_PROP_POS_FRAMES, seed.frame_index)
    ok, seed_image = capture.read()
    if not ok:
        capture.release()
        raise ValueError("Could not decode the selected bag seed frame")
    template = _crop(seed_image, bbox)
    if template is None:
        capture.release()
        raise ValueError("Bag seed rectangle did not contain readable pixels")

    factory = _csrt_factory()
    fallback_reason: str | None = None
    color_model = _seed_color_model(template)
    if requested_method == "color_motion" and color_model is None:
        capture.release()
        raise ValueError("The selected bag has insufficient distinct color. Select a tighter box or use CSRT/template tracking.")
    if requested_method == "color_motion" or (requested_method == "auto" and color_model is not None):
        effective_method = "color_motion"
    elif requested_method == "template_matching":
        effective_method = "template_matching"
    elif factory is None:
        if requested_method == "csrt":
            capture.release()
            raise RuntimeError("OpenCV CSRT is unavailable; choose template_matching explicitly or install opencv-contrib-python")
        effective_method = "template_matching"
        fallback_reason = "OpenCV CSRT was unavailable; explicit local template-matching fallback used."
    else:
        effective_method = "csrt"

    tracker = None
    if effective_method == "csrt":
        tracker = factory()
        # OpenCV 5's Python binding requires integer seed rectangle values even
        # though update results and our stored centroid coordinates are floats.
        tracker_bbox = tuple(int(round(item)) for item in bbox)
        initialized = tracker.init(seed_image, tracker_bbox)
        if initialized is False:
            capture.release()
            raise RuntimeError("OpenCV CSRT could not initialize from the selected bag rectangle")

    points = [
        BagAutomaticPoint(i, None, None, 0.0, None, "before_seed")
        for i in range(seed.frame_index)
    ]
    center = (bbox[0] + 0.5 * bbox[2], bbox[1] + 0.5 * bbox[3])
    if effective_method == "color_motion":
        initial = _color_motion_candidate(seed_image, center, max(bbox[2:])/2+1, color_model)
        if initial is not None: center = initial[2]
    points.append(BagAutomaticPoint(seed.frame_index, center[0], center[1], 1.0, bbox, "manual_seed"))
    failures: list[int] = []
    previous = bbox
    last_center = np.asarray(center,float)
    last_valid_frame = seed.frame_index
    velocity = np.zeros(2)
    previous_image = seed_image
    frame_index = seed.frame_index + 1
    try:
        while frame_index < metadata.frame_count:
            if progress is not None and (frame_index-seed.frame_index) % 30 == 1:
                fraction = (frame_index-seed.frame_index)/max(1, metadata.frame_count-seed.frame_index)
                progress(fraction, f"Tracking bag: frame {frame_index} of {metadata.frame_count-1}")
            ok, image = capture.read()
            if not ok:
                for missing in range(frame_index, metadata.frame_count):
                    failures.append(missing)
                    points.append(BagAutomaticPoint(missing, None, None, 0.0, None, "decode_failed"))
                break
            component_center = None
            if effective_method == "color_motion":
                gap = frame_index-last_valid_frame
                predicted = last_center+velocity*gap
                radius = max(3*max(bbox[2:]), 2*np.linalg.norm(velocity)+max(bbox[2:]))*min(2,1+0.15*(gap-1))
                previous_mask = None
                if np.linalg.norm(velocity) > 3:
                    hue,saturation,_ = color_model
                    old_hsv=cv2.cvtColor(previous_image,cv2.COLOR_BGR2HSV)
                    delta=np.abs(old_hsv[...,0].astype(float)-hue)
                    old_mask=((np.minimum(delta,180-delta)<=12)&(old_hsv[...,1]>=saturation)&(old_hsv[...,2]>=30)).astype(np.uint8)
                    # Translation-only camera compensation for the rejection mask,
                    # never a world-coordinate calibration or a change to centroids.
                    factor=320/image.shape[1]
                    old_gray=cv2.resize(cv2.cvtColor(previous_image,cv2.COLOR_BGR2GRAY),None,fx=factor,fy=factor).astype(np.float32)
                    new_gray=cv2.resize(cv2.cvtColor(image,cv2.COLOR_BGR2GRAY),None,fx=factor,fy=factor).astype(np.float32)
                    shift,response=cv2.phaseCorrelate(old_gray,new_gray)
                    dx,dy=shift[0]/factor,shift[1]/factor
                    if response < 0.1 or abs(dx)>image.shape[1]*0.03 or abs(dy)>image.shape[0]*0.03: dx=dy=0
                    previous_mask=cv2.warpAffine(old_mask,np.float32([[1,0,dx],[0,1,dy]]),(image.shape[1],image.shape[0]),flags=cv2.INTER_NEAREST)
                candidate = _color_motion_candidate(image,predicted,radius,color_model,previous_mask)
                result = None if candidate is None else candidate[:2]
                if candidate is not None: component_center = candidate[2]
            elif effective_method == "csrt":
                tracked, candidate = tracker.update(image)
                result = None if not tracked else (tuple(float(item) for item in candidate), None)
            else:
                result = _template_update(template, image, previous, search_scale)
            if result is None:
                failures.append(frame_index)
                points.append(BagAutomaticPoint(frame_index, None, None, 0.0, None, "tracker_update_failed"))
            else:
                candidate, template_quality = result
                try:
                    candidate = _bounded_bbox(candidate, metadata.width, metadata.height)
                except ValueError:
                    failures.append(frame_index)
                    points.append(BagAutomaticPoint(frame_index, None, None, 0.0, None, "outside_frame"))
                    frame_index += 1
                    continue
                quality = _appearance_score(template, image, candidate) if template_quality is None else template_quality
                if quality < template_quality_threshold:
                    failures.append(frame_index)
                    points.append(BagAutomaticPoint(frame_index, None, None, quality, candidate, "appearance_quality_failed"))
                else:
                    previous = candidate
                    cx = candidate[0] + 0.5 * candidate[2]
                    cy = candidate[1] + 0.5 * candidate[3]
                    if component_center is not None: cx,cy = component_center
                    observed = np.array([cx,cy])
                    velocity = 0.65*(observed-last_center)/max(1,frame_index-last_valid_frame)+0.35*velocity
                    last_center, last_valid_frame = observed, frame_index
                    points.append(BagAutomaticPoint(frame_index, cx, cy, quality, candidate, "tracked"))
            previous_image = image
            frame_index += 1
    finally:
        capture.release()

    tracked_after_seed = sum(point.x is not None and point.y is not None for point in points[seed.frame_index:])
    possible = max(1, metadata.frame_count - seed.frame_index)
    coverage = tracked_after_seed / possible
    status = (
        "automatic_complete_unreviewed"
        if not failures
        else "partial_failure_unreviewed" if tracked_after_seed > 1
        else "automatic_failed"
    )
    quality_note = (
        "Tracker confidence is an uncalibrated appearance-consistency score; manual review determines "
        f"whether the bag identity is correct. Forward-from-seed coverage was {coverage:.1%}."
    )
    return BagTrack(
        schema_version=1,
        frame_count=metadata.frame_count,
        width=metadata.width,
        height=metadata.height,
        source_video_sha256=metadata.sha256,
        seed=seed,
        requested_method=requested_method,
        effective_method=effective_method,
        automatic_points=points,
        status=status,
        failure_frames=failures,
        fallback_reason=fallback_reason,
        quality_note=quality_note,
    )


def validate_bag_track_for_video(track: BagTrack, video_path: str | Path) -> None:
    metadata = read_video_metadata(video_path)
    if track.source_video_sha256 and track.source_video_sha256 != metadata.sha256:
        raise ValueError("Bag track belongs to a different source-video hash")
    if (track.frame_count, track.width, track.height) != (metadata.frame_count, metadata.width, metadata.height):
        raise ValueError("Bag track frame count or dimensions do not match the source video")
    indices = [point.frame_index for point in track.automatic_points]
    if len(indices) != len(set(indices)) or any(index < 0 or index >= track.frame_count for index in indices):
        raise ValueError("Bag track contains duplicate or out-of-range frame indices")


def effective_bag_track(
    track: BagTrack,
    corrections: BagCorrectionSet,
    confidence_threshold: float,
    max_interpolation_gap_frames: int,
) -> dict[str, Any]:
    """Apply review edits and short-gap interpolation without mutating raw points."""
    n = track.frame_count
    raw = np.full((n, 2), np.nan, dtype=float)
    confidence = np.zeros(n, dtype=float)
    for point in track.automatic_points:
        if not 0 <= point.frame_index < n:
            continue
        confidence[point.frame_index] = point.confidence
        if point.x is not None and point.y is not None:
            raw[point.frame_index] = (point.x, point.y)
    effective = raw.copy()
    provenance = np.full(n, "missing", dtype=object)
    automatic = np.isfinite(raw).all(axis=-1) & (confidence >= confidence_threshold)
    effective[~automatic] = np.nan
    provenance[automatic] = "automatic"
    manual_mask = np.zeros(n, dtype=bool)
    user_interpolated_mask = np.zeros(n, dtype=bool)
    for correction in corrections.corrections:
        if not 0 <= correction.frame_index < n:
            continue
        effective[correction.frame_index] = (correction.x, correction.y)
        if correction.kind == "manual":
            manual_mask[correction.frame_index] = True
            provenance[correction.frame_index] = "manual"
        else:
            user_interpolated_mask[correction.frame_index] = True
            provenance[correction.frame_index] = "reviewed_interpolation"
    interpolated, automatic_interpolation = interpolate_short_gaps(
        effective[:, None, :], max_interpolation_gap_frames
    )
    effective = interpolated[:, 0, :]
    automatic_interpolation = automatic_interpolation[:, 0]
    provenance[automatic_interpolation & ~user_interpolated_mask] = "automatic_short_gap_interpolation"
    interpolated_mask = automatic_interpolation | user_interpolated_mask
    samples = []
    for frame in range(n):
        samples.append({
            "frame_index": frame,
            "automatic_centroid": None if not np.isfinite(raw[frame]).all() else {
                "x": raw[frame, 0], "y": raw[frame, 1], "confidence": confidence[frame]
            },
            "effective_centroid": None if not np.isfinite(effective[frame]).all() else {
                "x": effective[frame, 0], "y": effective[frame, 1]
            },
            "provenance": str(provenance[frame]),
        })
    return {
        "raw": raw,
        "confidence": confidence,
        "effective": effective,
        "manual_mask": manual_mask,
        "interpolated_mask": interpolated_mask,
        "provenance": provenance,
        "payload": {
            "schema_version": 1,
            "coordinate_system": BAG_COORDINATE_SYSTEM,
            "units": "pixels",
            "tracker": {
                "requested_method": track.requested_method,
                "effective_method": track.effective_method,
                "status": track.status,
                "fallback_reason": track.fallback_reason,
                "failure_frames": track.failure_frames,
                "quality_note": track.quality_note,
            },
            "seed": asdict(track.seed),
            "corrections": asdict(corrections),
            "interpolation": {
                "maximum_automatic_gap_frames": max_interpolation_gap_frames,
                "automatic_interpolated_frames": np.flatnonzero(automatic_interpolation).tolist(),
                "reviewed_interpolated_frames": np.flatnonzero(user_interpolated_mask).tolist(),
                "longer_gaps_remain_missing": True,
            },
            "samples": samples,
        },
    }


def detect_bag_wrist_release(
    wrist_pixels: np.ndarray,
    bag_pixels: np.ndarray,
    arm_length_pixels: float,
    fps: float,
    minimum_divergence_arm_lengths: float = 0.08,
    persistence_seconds: float = 0.05,
) -> EventValue:
    """Find the first persistent bag/wrist divergence within one finite run."""
    wrist = np.asarray(wrist_pixels, float)
    bag = np.asarray(bag_pixels, float)
    empty = EventValue(name="release")
    if wrist.shape != bag.shape or wrist.ndim != 2 or wrist.shape[1] != 2:
        raise ValueError("Bag and wrist trajectories must have matching [frame, 2] shape")
    if not math.isfinite(arm_length_pixels) or arm_length_pixels <= 0 or fps <= 0:
        return empty
    separation = np.linalg.norm(bag - wrist, axis=-1) / arm_length_pixels
    valid = np.isfinite(separation)
    persistence = max(2, int(math.ceil(persistence_seconds * fps)))
    for first, last in _finite_runs(valid):
        if last - first < persistence + 3:
            continue
        for frame in range(first + 3, last - persistence + 1):
            prior = separation[first:frame]
            baseline = float(np.percentile(prior, 20))
            window = separation[frame:frame + persistence]
            if np.all(window >= baseline + minimum_divergence_arm_lengths):
                growth = float(np.median(window) - baseline)
                confidence = float(np.clip(growth / max(2 * minimum_divergence_arm_lengths, 1e-9), 0, 1))
                return EventValue(
                    name="release",
                    automatic_frame=frame,
                    automatic_confidence=confidence,
                    automatic_method=(
                        "bag_wrist_persistent_divergence_v1:"
                        f"{minimum_divergence_arm_lengths:g}_arm_lengths,"
                        f"{persistence}_frames"
                    ),
                )
    return empty


def _robust_polynomial(time: np.ndarray, values: np.ndarray, degree: int) -> tuple[np.ndarray, np.ndarray]:
    design = np.column_stack([time ** power for power in range(degree + 1)])
    weights = np.ones(len(time), dtype=float)
    coefficients = np.zeros(degree + 1)
    for _ in range(12):
        root = np.sqrt(weights)
        coefficients = np.linalg.lstsq(design * root[:, None], values * root, rcond=None)[0]
        residual = values - design @ coefficients
        scale = 1.4826 * float(np.median(np.abs(residual - np.median(residual))))
        if scale <= 1e-12:
            break
        normalized = np.abs(residual) / (1.345 * scale)
        updated = np.ones_like(normalized)
        large = normalized > 1
        updated[large] = 1.0 / normalized[large]
        if np.allclose(updated, weights, atol=1e-4):
            weights = updated
            break
        weights = updated
    return coefficients, values - design @ coefficients


def estimate_projectile_release_kinematics(
    bag_pixels: np.ndarray,
    release_frame: int | None,
    fps: float,
    arm_length_pixels: float,
    target_direction: str,
    calibration: SpatialCalibration | None = None,
    window_seconds: float = 0.12,
    minimum_points: int = 4,
    acceleration_minimum_fps: float = 60.0,
    acceleration_minimum_points: int = 6,
    acceleration_maximum_fit_rmse_arm_lengths: float = 0.03,
) -> dict[str, Any]:
    """Estimate launch derivatives from a robust short-window polynomial fit."""
    base: dict[str, Any] = {
        "status": "insufficient_data",
        "coordinate_system": ANALYSIS_COORDINATE_SYSTEM,
        "frame_interval_seconds": None if fps <= 0 else 1.0 / fps,
        "release_frame": release_frame,
        "velocity": None,
        "acceleration": {
            "status": "suppressed",
            "reason": "Acceleration requires adequate frame rate, samples, and local-fit quality.",
            "interpretation": "exploratory_noise_sensitive_projected_measurement",
        },
        "physical_units": {
            "status": "not_available_without_valid_athlete_plane_calibration",
            "calibration": None if calibration is None else asdict(calibration),
        },
    }
    points = np.asarray(bag_pixels, float)
    if points.ndim != 2 or points.shape[1] != 2:
        raise ValueError("Bag trajectory must have shape [frame, 2]")
    if release_frame is None or not 0 <= release_frame < len(points) or fps <= 0:
        return base
    end_limit = min(len(points), release_frame + max(minimum_points, int(math.ceil(window_seconds * fps)) + 1))
    valid = np.isfinite(points[:, 0]) & np.isfinite(points[:, 1])
    candidate_runs = [(a, b) for a, b in _finite_runs(valid[release_frame:end_limit])]
    if not candidate_runs:
        base["acceleration"]["reason"] = "No reliable contiguous bag samples follow release."
        return base
    first, last = candidate_runs[0]
    first += release_frame
    last += release_frame
    if first - release_frame > 1:
        base["acceleration"]["reason"] = "The first reliable bag sample is too far after release."
        return base
    sample_indices = np.arange(first, last)
    if len(sample_indices) < minimum_points:
        base["acceleration"]["reason"] = f"Only {len(sample_indices)} contiguous samples follow release; {minimum_points} are required for velocity."
        return base
    # Anchor the fit at the reviewed/candidate release frame. If the first
    # centroid occurs one frame later, the polynomial is extrapolated back by
    # at most one frame rather than mislabeled as velocity at release.
    time = (sample_indices - release_frame) / fps
    degree = 2  # Four or more samples identify curvature; linear fits bias launch velocity toward mid-window.
    coeff_x, residual_x = _robust_polynomial(time, points[sample_indices, 0], degree)
    coeff_y, residual_y = _robust_polynomial(time, points[sample_indices, 1], degree)
    x_sign = 1.0 if target_direction == "left_to_right" else -1.0
    velocity_pixels = np.array([x_sign * coeff_x[1], -coeff_y[1]], dtype=float)
    fit_rmse_pixels = float(np.sqrt(np.mean(residual_x**2 + residual_y**2)))
    fit_rmse_arm_lengths = (
        fit_rmse_pixels / arm_length_pixels
        if math.isfinite(arm_length_pixels) and arm_length_pixels > 0 else None
    )
    # Residual is a descriptive gate, not a probability of physical accuracy.
    if fit_rmse_arm_lengths is None or fit_rmse_arm_lengths > acceleration_maximum_fit_rmse_arm_lengths:
        base.update(status="suppressed_poor_fit", fit_rmse_pixels=fit_rmse_pixels,
                    fit_rmse_arm_lengths=fit_rmse_arm_lengths,
                    reason="Release fit lacks scale support or exceeds the documented pilot residual gate.")
        return base
    speed_pixels = float(np.linalg.norm(velocity_pixels))
    if speed_pixels <= 1e-8:
        base.update(status="suppressed_no_motion", reason="A stationary centroid has no defined launch direction.")
        return base
    angle = float(np.degrees(np.arctan2(velocity_pixels[1], velocity_pixels[0])))
    velocity: dict[str, Any] = {
        "forward_px_s": float(velocity_pixels[0]),
        "vertical_px_s": float(velocity_pixels[1]),
        "speed_px_s": speed_pixels,
        "angle_deg": angle,
        "forward_arm_lengths_s": None,
        "vertical_arm_lengths_s": None,
        "speed_arm_lengths_s": None,
    }
    if math.isfinite(arm_length_pixels) and arm_length_pixels > 0:
        velocity.update({
            "forward_arm_lengths_s": float(velocity_pixels[0] / arm_length_pixels),
            "vertical_arm_lengths_s": float(velocity_pixels[1] / arm_length_pixels),
            "speed_arm_lengths_s": float(speed_pixels / arm_length_pixels),
        })
    base.update({
        "status": "estimated",
        "sample_frames": sample_indices.tolist(),
        "sample_count": int(len(sample_indices)),
        "fit_degree": degree,
        "fit_method": "iteratively_reweighted_local_polynomial_huber",
        "fit_window_seconds": float(time[-1] - time[0]),
        "fit_time_origin": "release_frame",
        "fit_rmse_pixels": fit_rmse_pixels,
        "fit_rmse_arm_lengths": fit_rmse_arm_lengths,
        "velocity": velocity,
        "uncertainty_note": "Release time and derivative window are frame-limited; fit residual is descriptive, not a calibrated confidence interval.",
    })
    if calibration is not None and calibration.permits_physical_units:
        base["physical_units"] = {
            "status": "available_from_explicit_athlete_plane_scale",
            "calibration": asdict(calibration),
            "velocity": {
                "forward_m_s": float(velocity_pixels[0] / calibration.pixels_per_meter),
                "vertical_m_s": float(velocity_pixels[1] / calibration.pixels_per_meter),
                "speed_m_s": float(speed_pixels / calibration.pixels_per_meter),
            },
        }
    elif calibration is not None:
        base["physical_units"]["status"] = "rejected_invalid_or_wrong_plane_calibration"

    acceleration_reason = None
    if fps < acceleration_minimum_fps:
        acceleration_reason = f"Frame rate {fps:g} fps is below the {acceleration_minimum_fps:g} fps exploratory acceleration gate."
    elif degree < 2 or len(sample_indices) < acceleration_minimum_points:
        acceleration_reason = f"At least {acceleration_minimum_points} contiguous samples are required for exploratory acceleration."
    elif fit_rmse_arm_lengths is None:
        acceleration_reason = "Arm-length normalization is unavailable."
    elif fit_rmse_arm_lengths > acceleration_maximum_fit_rmse_arm_lengths:
        acceleration_reason = (
            f"Local-fit RMSE {fit_rmse_arm_lengths:.4g} arm lengths exceeds the "
            f"{acceleration_maximum_fit_rmse_arm_lengths:g} pilot quality gate."
        )
    if acceleration_reason is None:
        acceleration_pixels = np.array([x_sign * 2.0 * coeff_x[2], -2.0 * coeff_y[2]])
        acceleration: dict[str, Any] = {
            "status": "estimated_exploratory",
            "forward_px_s2": float(acceleration_pixels[0]),
            "vertical_px_s2": float(acceleration_pixels[1]),
            "magnitude_px_s2": float(np.linalg.norm(acceleration_pixels)),
            "forward_arm_lengths_s2": float(acceleration_pixels[0] / arm_length_pixels),
            "vertical_arm_lengths_s2": float(acceleration_pixels[1] / arm_length_pixels),
            "magnitude_arm_lengths_s2": float(np.linalg.norm(acceleration_pixels) / arm_length_pixels),
            "interpretation": "exploratory_noise_sensitive_projected_measurement",
            "warning": "Do not interpret this as gravity, force, or a validated aerodynamic estimate.",
        }
        if calibration is not None and calibration.permits_physical_units:
            acceleration["forward_m_s2"] = float(acceleration_pixels[0] / calibration.pixels_per_meter)
            acceleration["vertical_m_s2"] = float(acceleration_pixels[1] / calibration.pixels_per_meter)
            acceleration["magnitude_m_s2"] = float(np.linalg.norm(acceleration_pixels) / calibration.pixels_per_meter)
        base["acceleration"] = acceleration
    else:
        base["acceleration"]["reason"] = acceleration_reason
    return json_ready(base)


def bag_tracking_qa(
    track: BagTrack,
    manual_labels: list[dict[str, Any]],
    arm_length_pixels: float | None = None,
    automatic_release_frame: int | None = None,
    manual_release_frame: int | None = None,
    fps: float | None = None,
) -> dict[str, Any]:
    """Compare automatic centroids with reviewed labels without editing either."""
    automatic = {point.frame_index: point for point in track.automatic_points}
    errors: list[float] = []
    normalized: list[float] = []
    missing: list[int] = []
    identity_failures: list[int] = []
    observations = []
    for label in manual_labels:
        frame = int(label["frame_index"])
        if bool(label.get("automatic_identity_failure", False)):
            identity_failures.append(frame)
        point = automatic.get(frame)
        if point is None or point.x is None or point.y is None:
            missing.append(frame)
            observations.append({"frame_index": frame, "pixel_error": None, "normalized_error_arm_lengths": None})
            continue
        error = float(math.hypot(point.x - float(label["x"]), point.y - float(label["y"])))
        errors.append(error)
        norm = error / arm_length_pixels if arm_length_pixels is not None and arm_length_pixels > 0 else None
        if norm is not None:
            normalized.append(norm)
        observations.append({"frame_index": frame, "pixel_error": error, "normalized_error_arm_lengths": norm})
    release_difference = None
    if automatic_release_frame is not None and manual_release_frame is not None:
        frames = int(automatic_release_frame - manual_release_frame)
        release_difference = {
            "signed_frames": frames,
            "absolute_frames": abs(frames),
            "signed_milliseconds": None if not fps or fps <= 0 else 1000.0 * frames / fps,
            "absolute_milliseconds": None if not fps or fps <= 0 else 1000.0 * abs(frames) / fps,
        }
    return json_ready({
        "schema_version": 1,
        "track_status": track.status,
        "tracker_method": track.effective_method,
        "coordinate_system": BAG_COORDINATE_SYSTEM,
        "manual_label_count": len(manual_labels),
        "matched_label_count": len(errors),
        "missing_track_rate": len(missing) / len(manual_labels) if manual_labels else None,
        "failure_frames": missing,
        "reviewed_identity_failure_frames": identity_failures,
        "pixel_error": {
            "mean": float(np.mean(errors)) if errors else None,
            "median": float(np.median(errors)) if errors else None,
            "rmse": float(np.sqrt(np.mean(np.square(errors)))) if errors else None,
            "maximum": float(np.max(errors)) if errors else None,
        },
        "normalized_error_arm_lengths": {
            "mean": float(np.mean(normalized)) if normalized else None,
            "median": float(np.median(normalized)) if normalized else None,
        },
        "release_frame_error": release_difference,
        "observations": observations,
        "claim_scope": "software_and_tracking_qa_not_task_specific_validation",
    })


def write_bag_csv(path: str | Path, derived: dict[str, Any], fps: float) -> None:
    """Write frame-wise automatic/effective bag data with explicit provenance."""
    import csv
    payload = derived["payload"]
    with Path(path).open("w", newline="") as stream:
        fields = (
            "frame", "time_seconds", "automatic_x_px", "automatic_y_px",
            "automatic_quality", "effective_x_px", "effective_y_px", "provenance",
        )
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for item in payload["samples"]:
            automatic = item["automatic_centroid"] or {}
            effective = item["effective_centroid"] or {}
            writer.writerow({
                "frame": item["frame_index"],
                "time_seconds": f"{item['frame_index'] / fps:.9g}",
                "automatic_x_px": automatic.get("x", ""),
                "automatic_y_px": automatic.get("y", ""),
                "automatic_quality": automatic.get("confidence", ""),
                "effective_x_px": effective.get("x", ""),
                "effective_y_px": effective.get("y", ""),
                "provenance": item["provenance"],
            })
