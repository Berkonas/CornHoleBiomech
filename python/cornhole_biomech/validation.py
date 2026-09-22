"""Agreement between automatic tracking and blinded manual annotation.

Manual annotation is the criterion here, not ground truth: reviewer error is
estimated separately by comparing two raters with the same functions. All image
coordinates are raw video pixels (x right, y down); biases are estimate minus
reference in that frame. Frames where the reference marks a point as not visible
are excluded from error statistics and counted separately.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .geometry import vector_angle_degrees
from .serialization import write_json
from .video import read_video_metadata

Key = tuple[int, str]
Point = tuple[float, float]

# Event frames most informative for coaching metrics; release gets ±2 neighbors
# because release-referenced values are the most sensitive to local error.
_EVENT_NEIGHBORS = {"release": (-2, -1, 0, 1, 2)}


def select_validation_frames(
    frame_count: int,
    events: dict[str, int | None] | None,
    count: int = 10,
    seed: int = 20260922,
) -> list[int]:
    """Choose frames to annotate: event frames first, then evenly spread fill.

    Deterministic for a given seed so a second rater annotates the same frames.
    Fill frames come from equal-width strata with one random frame each, which
    avoids clustering while keeping the choice free of analyst judgment.
    """
    if frame_count <= 0 or count <= 0:
        return []
    chosen: set[int] = set()
    for name, frame in (events or {}).items():
        if frame is None:
            continue
        for offset in _EVENT_NEIGHBORS.get(name, (0,)):
            if 0 <= frame + offset < frame_count:
                chosen.add(int(frame + offset))
    rng = np.random.default_rng(seed)
    remaining = max(0, min(count, frame_count) - len(chosen))
    if remaining:
        edges = np.linspace(0, frame_count, remaining + 1)
        for low, high in zip(edges[:-1], edges[1:]):
            candidates = [f for f in range(int(np.ceil(low)), max(int(np.ceil(low)) + 1, int(np.ceil(high))))
                          if f < frame_count and f not in chosen]
            if candidates:
                chosen.add(int(rng.choice(candidates)))
    return sorted(chosen)


def annotation_points(annotation: dict[str, Any]) -> tuple[dict[Key, Point], set[Key]]:
    """Return visible manual points and the set of points marked not visible."""
    points: dict[Key, Point] = {}
    hidden: set[Key] = set()
    for item in annotation.get("annotations", []):
        key = (int(item["frame_index"]), str(item["landmark"]))
        if item.get("visible", True) is False or item.get("x") is None or item.get("y") is None:
            hidden.add(key)
        else:
            points[key] = (float(item["x"]), float(item["y"]))
    return points, hidden


def _stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "median": None, "rmse": None, "p95": None, "max": None}
    a = np.asarray(values, float)
    return {
        "mean": float(np.mean(a)),
        "median": float(np.median(a)),
        "rmse": float(np.sqrt(np.mean(a**2))),
        "p95": float(np.percentile(a, 95)),
        "max": float(np.max(a)),
    }


def landmark_errors(
    reference: dict[Key, Point],
    estimate: dict[Key, Point | None],
    normalizer_px: float | None,
) -> dict[str, dict[str, Any]]:
    """Per-landmark Euclidean error of estimate versus reference.

    A reference point with no estimate is a detection failure: it raises the
    failure rate and is never scored as zero error. `normalizer_px` (arm length
    in pixels) converts errors to body-scaled units when provided.
    """
    by_landmark: dict[str, list[Key]] = {}
    for key in reference:
        by_landmark.setdefault(key[1], []).append(key)
    result: dict[str, dict[str, Any]] = {}
    for landmark, keys in sorted(by_landmark.items()):
        errors: list[float] = []
        dx: list[float] = []
        dy: list[float] = []
        for key in keys:
            point = estimate.get(key)
            if point is None or not np.all(np.isfinite(point)):
                continue
            ex, ey = point[0] - reference[key][0], point[1] - reference[key][1]
            dx.append(ex)
            dy.append(ey)
            errors.append(float(np.hypot(ex, ey)))
        stats = _stats(errors)
        scale = normalizer_px if normalizer_px and normalizer_px > 0 else None
        result[landmark] = {
            "n_reference": len(keys),
            "n_compared": len(errors),
            "detection_failure_rate": 1.0 - len(errors) / len(keys),
            **{f"{name}_px": value for name, value in stats.items()},
            "bias_x_px": float(np.mean(dx)) if dx else None,
            "bias_y_px": float(np.mean(dy)) if dy else None,
            "mean_arm_lengths": None if scale is None or stats["mean"] is None else stats["mean"] / scale,
            "rmse_arm_lengths": None if scale is None or stats["rmse"] is None else stats["rmse"] / scale,
        }
    return result


def elbow_angle_errors(reference: dict[Key, Point], estimate: dict[Key, Point | None], side: str) -> dict[str, Any]:
    """Projected elbow included-angle error on frames with complete triplets in both sets."""
    names = (f"{side}_shoulder", f"{side}_elbow", f"{side}_wrist")
    frames = sorted({frame for frame, _ in reference})
    observations = []
    for frame in frames:
        ref = [reference.get((frame, n)) for n in names]
        est = [estimate.get((frame, n)) for n in names]
        if any(p is None for p in ref + est):
            continue
        ref_angle = float(vector_angle_degrees(*map(np.asarray, ref)))
        est_angle = float(vector_angle_degrees(*map(np.asarray, est)))
        if np.isfinite(ref_angle) and np.isfinite(est_angle):
            observations.append({"frame_index": frame, "reference_deg": ref_angle,
                                 "estimate_deg": est_angle, "error_deg": est_angle - ref_angle})
    signed = [o["error_deg"] for o in observations]
    stats = _stats([abs(v) for v in signed])
    return {
        "n_compared": len(observations),
        "mean_abs_deg": stats["mean"],
        "median_abs_deg": stats["median"],
        "rmse_deg": stats["rmse"],
        "p95_abs_deg": stats["p95"],
        "max_abs_deg": stats["max"],
        "bias_deg": float(np.mean(signed)) if signed else None,
        "observations": observations,
    }


def event_errors(reference: dict[str, int | None], estimate: dict[str, int | None], fps: float) -> dict[str, Any]:
    """Signed event-frame differences (estimate minus reference) in frames and ms."""
    result: dict[str, Any] = {}
    for name, ref in reference.items():
        if ref is None:
            continue
        est = estimate.get(name)
        if est is None:
            result[name] = {"status": "no_automatic_estimate", "reference_frame": ref}
            continue
        frames = int(est) - int(ref)
        result[name] = {"status": "compared", "reference_frame": ref, "estimate_frame": est,
                        "signed_frames": frames, "signed_ms": 1000.0 * frames / fps}
    return result


def points_from_keypoints_csv(path: str | Path, column: str = "raw") -> dict[Key, Point | None]:
    """Read automatic landmark points from an analysis `keypoints.csv`.

    `column` is "raw" (model output, before confidence masking) or "filtered"
    (what the kinematics use). Blank cells become None.
    """
    if column not in {"raw", "effective", "filtered"}:
        raise ValueError("column must be raw, effective, or filtered")
    points: dict[Key, Point | None] = {}
    with Path(path).open(newline="") as stream:
        for row in csv.DictReader(stream):
            x, y = row[f"{column}_x_px"], row[f"{column}_y_px"]
            points[(int(row["frame"]), row["landmark"])] = (float(x), float(y)) if x and y else None
    return points


def points_from_bag_csv(path: str | Path) -> dict[Key, Point | None]:
    """Read automatic bag centroids from `bag_keypoints.csv` under landmark name 'bag'."""
    points: dict[Key, Point | None] = {}
    with Path(path).open(newline="") as stream:
        for row in csv.DictReader(stream):
            x, y = row["automatic_x_px"], row["automatic_y_px"]
            points[(int(row["frame"]), "bag")] = (float(x), float(y)) if x and y else None
    return points


def export_annotation_frames(video_path: str | Path, frames: list[int], output_dir: str | Path) -> dict[str, Any]:
    """Write full-resolution PNGs with no automatic overlays (keeps raters blinded)."""
    metadata = read_video_metadata(video_path)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(metadata.path)
    written = []
    try:
        for frame in frames:
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame)
            ok, image = capture.read()
            if not ok:
                continue
            name = f"frame_{frame:05d}.png"
            cv2.imwrite(str(out / name), image)
            written.append({"frame_index": frame, "file": name})
    finally:
        capture.release()
    manifest = {"schema_version": 1, "video": metadata.to_dict(), "frames": written,
                "instructions": "Annotate with tools/annotator.html. Do not look at automatic overlays first."}
    write_json(out / "annotation_manifest.json", manifest)
    return manifest


def validation_report(
    annotation_path: str | Path,
    keypoints_csv: str | Path,
    throwing_side: str,
    arm_length_px: float | None = None,
    bag_csv: str | Path | None = None,
    automatic_events: dict[str, int | None] | None = None,
) -> dict[str, Any]:
    """Compare one rater's annotation with an analysis folder's automatic output."""
    annotation = json.loads(Path(annotation_path).read_text())
    reference, hidden = annotation_points(annotation)
    fps = float(annotation.get("fps") or 0) or None
    report: dict[str, Any] = {"schema_version": 1, "rater": annotation.get("rater"),
                              "reference_points": len(reference), "reference_not_visible": len(hidden),
                              "criterion": "blinded_manual_annotation_not_ground_truth"}
    for column in ("raw", "filtered"):
        estimate = points_from_keypoints_csv(keypoints_csv, column)
        body_ref = {k: v for k, v in reference.items() if k[1] != "bag"}
        report[f"landmarks_{column}"] = landmark_errors(body_ref, estimate, arm_length_px)
        report[f"elbow_angle_{column}"] = elbow_angle_errors(body_ref, estimate, throwing_side)
    if bag_csv is not None:
        bag_ref = {k: v for k, v in reference.items() if k[1] == "bag"}
        report["bag"] = landmark_errors(bag_ref, points_from_bag_csv(bag_csv), arm_length_px).get("bag")
    if automatic_events and annotation.get("events") and fps:
        report["events"] = event_errors(annotation["events"], automatic_events, fps)
    return report


def inter_rater_report(first_path: str | Path, second_path: str | Path, throwing_side: str,
                       arm_length_px: float | None = None) -> dict[str, Any]:
    """Annotation repeatability: rater B treated as the estimate of rater A."""
    a, _ = annotation_points(json.loads(Path(first_path).read_text()))
    b, _ = annotation_points(json.loads(Path(second_path).read_text()))
    shared = {k: v for k, v in a.items() if k in b}
    return {"schema_version": 1, "shared_points": len(shared),
            "landmarks": landmark_errors(shared, b, arm_length_px),
            "elbow_angle": elbow_angle_errors(shared, b, throwing_side)}
