"""Cornhole-specific projected 2D upper-body kinematics."""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from .filtering import derivative, _finite_runs
from .geometry import (
    robust_segment_length,
    signed_orientation_degrees,
    throw_centered_points,
    unsigned_vector_angle_degrees,
    vector_angle_degrees,
)


ANGLE_FIELDS = (
    "elbow_angle_deg",
    "upper_arm_orientation_deg",
    "forearm_orientation_deg",
    "arm_to_trunk_deg",
    "trunk_inclination_deg",
)


@dataclass
class KinematicResult:
    time_seconds: np.ndarray
    values: dict[str, np.ndarray]
    summaries: dict[str, float | None]
    arm_length_pixels: float
    warnings: list[str]


def _point(coords: np.ndarray, lookup: dict[str, int], name: str) -> np.ndarray:
    return coords[:, lookup[name], :]


def _nan_summary(values: np.ndarray, operation: str) -> float | None:
    finite = values[np.isfinite(values)]
    if not finite.size:
        return None
    if operation == "mean":
        return float(np.mean(finite))
    if operation == "peak_abs":
        return float(np.max(np.abs(finite)))
    if operation == "rom":
        return float(np.max(finite) - np.min(finite))
    raise ValueError(operation)


def calculate_kinematics(
    filtered_coords: np.ndarray,
    landmarks: tuple[str, ...],
    fps: float,
    throwing_side: str,
    target_direction: str,
    minimum_velocity_coverage: float = 0.80,
) -> KinematicResult:
    """Calculate interpretable projected 2D metrics from filtered image points.

    Definitions and units:
    - elbow_angle_deg: unsigned shoulder-elbow-wrist planar angle, degrees.
    - upper_arm_orientation_deg: shoulder-to-elbow direction from +x, degrees.
    - forearm_orientation_deg: elbow-to-wrist direction from +x, degrees.
    - arm_to_trunk_deg: unsigned upper-arm versus hip-to-shoulder angle, degrees.
    - trunk_inclination_deg: signed trunk displacement from image vertical,
      degrees; positive is toward the target after direction reflection.
    - wrist/elbow_path_arm_lengths: throwing-shoulder-relative position divided
      by median upper-arm plus forearm length, dimensionless arm lengths.
    - *_velocity_deg_s: derivative of the already-filtered angle, degrees/second.
    - *_rom: finite maximum minus minimum projected angle, degrees.

    Image y is flipped upward and x is reflected into a common target-forward
    direction for orientations and normalized paths. Joint points are markerless
    image estimates rather than anatomical ground truth. Perspective and
    out-of-plane motion remain. No quantity here estimates axial
    shoulder/forearm/wrist rotation or a true 3D joint orientation.
    """
    lookup = {name: index for index, name in enumerate(landmarks)}
    required = {
        f"{throwing_side}_shoulder",
        f"{throwing_side}_elbow",
        f"{throwing_side}_wrist",
        "left_shoulder",
        "right_shoulder",
        "left_hip",
        "right_hip",
    }
    missing = sorted(required - set(lookup))
    if missing:
        raise ValueError(f"required landmarks unavailable: {', '.join(missing)}")
    shoulder = _point(filtered_coords, lookup, f"{throwing_side}_shoulder")
    elbow = _point(filtered_coords, lookup, f"{throwing_side}_elbow")
    wrist = _point(filtered_coords, lookup, f"{throwing_side}_wrist")
    opposite_shoulder = _point(
        filtered_coords, lookup, f"{'left' if throwing_side == 'right' else 'right'}_shoulder"
    )
    left_hip = _point(filtered_coords, lookup, "left_hip")
    right_hip = _point(filtered_coords, lookup, "right_hip")
    mid_hip = 0.5 * (left_hip + right_hip)
    mid_shoulder = 0.5 * (shoulder + opposite_shoulder)

    # Math-frame vectors: x toward image right, y upward.
    x_sign = 1.0 if target_direction == "left_to_right" else -1.0
    arm_vec = np.stack((x_sign * (elbow[:, 0] - shoulder[:, 0]), shoulder[:, 1] - elbow[:, 1]), axis=-1)
    forearm_vec = np.stack((x_sign * (wrist[:, 0] - elbow[:, 0]), elbow[:, 1] - wrist[:, 1]), axis=-1)
    trunk_vec = np.stack((x_sign * (mid_shoulder[:, 0] - mid_hip[:, 0]), mid_hip[:, 1] - mid_shoulder[:, 1]), axis=-1)

    elbow_angle = vector_angle_degrees(shoulder, elbow, wrist)
    upper_orientation = signed_orientation_degrees(arm_vec)
    forearm_orientation = signed_orientation_degrees(forearm_vec)
    arm_to_trunk = unsigned_vector_angle_degrees(arm_vec, trunk_vec)
    # Positive means the trunk top is displaced toward the target from the hips.
    trunk_inclination = np.degrees(np.arctan2(trunk_vec[:, 0], trunk_vec[:, 1]))
    trunk_inclination[~np.isfinite(trunk_vec).all(axis=-1)] = np.nan

    upper_length = robust_segment_length(shoulder, elbow)
    forearm_length = robust_segment_length(elbow, wrist)
    arm_length = upper_length + forearm_length
    normalized_wrist = throw_centered_points(wrist, shoulder, arm_length, target_direction)
    normalized_elbow = throw_centered_points(elbow, shoulder, arm_length, target_direction)

    values: dict[str, np.ndarray] = {
        "elbow_angle_deg": elbow_angle,
        "upper_arm_orientation_deg": upper_orientation,
        "forearm_orientation_deg": forearm_orientation,
        "arm_to_trunk_deg": arm_to_trunk,
        "trunk_inclination_deg": trunk_inclination,
        "wrist_path_arm_lengths": normalized_wrist,
        "elbow_path_arm_lengths": normalized_elbow,
    }
    # Keep orientation continuous within each finite run before derivatives.
    for field in ("upper_arm_orientation_deg", "forearm_orientation_deg", "trunk_inclination_deg"):
        for first, last in _finite_runs(np.isfinite(values[field])):
            values[field][first:last] = np.degrees(np.unwrap(np.radians(values[field][first:last])))
    for name in ("left_shoulder", "right_shoulder", "left_hip", "right_hip"):
        values[f"{name}_path_arm_lengths"] = throw_centered_points(
            _point(filtered_coords, lookup, name), shoulder, arm_length, target_direction)
    warnings: list[str] = []
    for field in ANGLE_FIELDS:
        coverage = float(np.mean(np.isfinite(values[field])))
        if coverage >= minimum_velocity_coverage:
            values[field.replace("_deg", "_velocity_deg_s")] = derivative(values[field], fps)
        else:
            values[field.replace("_deg", "_velocity_deg_s")] = np.full_like(values[field], np.nan)
            warnings.append(
                f"{field}: {coverage:.0%} finite coverage is below the velocity reporting threshold."
            )
    summaries: dict[str, float | None] = {}
    for field in ANGLE_FIELDS:
        summaries[f"{field}_mean"] = _nan_summary(values[field], "mean")
        summaries[f"{field}_rom"] = _nan_summary(values[field], "rom")
        velocity_field = field.replace("_deg", "_velocity_deg_s")
        summaries[f"{velocity_field}_mean"] = _nan_summary(values[velocity_field], "mean")
        summaries[f"{velocity_field}_peak_abs"] = _nan_summary(values[velocity_field], "peak_abs")
    return KinematicResult(
        time_seconds=np.arange(len(filtered_coords), dtype=float) / fps,
        values=values,
        summaries=summaries,
        arm_length_pixels=float(arm_length),
        warnings=warnings,
    )
