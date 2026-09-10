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


def _analysis_points(points: np.ndarray, target_direction: str) -> np.ndarray:
    """Convert image pixels to target-forward x and upward y without scaling."""
    source = np.asarray(points, float)
    x_sign = 1.0 if target_direction == "left_to_right" else -1.0
    return np.stack((x_sign * source[..., 0], -source[..., 1]), axis=-1)


def _center_on_first_finite(points: np.ndarray) -> np.ndarray:
    result = np.asarray(points, float).copy()
    valid = np.isfinite(result).all(axis=-1)
    if not valid.any():
        return np.full_like(result, np.nan)
    return result - result[np.flatnonzero(valid)[0]]


def path_shape_metrics(points: np.ndarray) -> dict[str, float | int | None]:
    """Describe one 2D path using its longest contiguous finite run.

    This avoids silently joining an occlusion. Straightness is net displacement
    divided by traveled path length. Line deviation uses an orthogonal PCA line;
    curvature is accumulated absolute turning angle per path-length unit.
    """
    source = np.asarray(points, float)
    if source.ndim != 2 or source.shape[1] != 2:
        raise ValueError("Path must have shape [sample, 2]")
    runs = _finite_runs(np.isfinite(source).all(axis=-1))
    if not runs:
        return {
            "sample_count": 0, "coverage": 0.0, "path_length": None,
            "net_displacement": None, "straightness": None,
            "rms_line_deviation": None, "mean_abs_turn_deg": None,
            "total_abs_turn_deg": None, "curvature_rad_per_unit": None,
        }
    first, last = max(runs, key=lambda run: run[1] - run[0])
    path = source[first:last]
    base: dict[str, float | int | None] = {
        "sample_count": int(len(path)),
        "coverage": float(len(path) / len(source)) if len(source) else 0.0,
        "path_length": None,
        "net_displacement": None,
        "straightness": None,
        "rms_line_deviation": None,
        "mean_abs_turn_deg": None,
        "total_abs_turn_deg": None,
        "curvature_rad_per_unit": None,
    }
    if len(path) < 2:
        return base
    steps = np.diff(path, axis=0)
    lengths = np.linalg.norm(steps, axis=-1)
    nonzero = lengths > 1e-12
    path_length = float(np.sum(lengths[nonzero]))
    net = float(np.linalg.norm(path[-1] - path[0]))
    base["path_length"] = path_length
    base["net_displacement"] = net
    base["straightness"] = float(np.clip(net / path_length, 0.0, 1.0)) if path_length > 0 else None
    centered = path - np.mean(path, axis=0)
    if len(path) >= 2 and np.linalg.norm(centered) > 1e-12:
        _, _, vectors = np.linalg.svd(centered, full_matrices=False)
        direction = vectors[0]
        perpendicular = centered - np.outer(centered @ direction, direction)
        base["rms_line_deviation"] = float(np.sqrt(np.mean(np.sum(perpendicular**2, axis=-1))))
    if np.count_nonzero(nonzero) >= 2:
        units = steps[nonzero] / lengths[nonzero, None]
        turns = np.arccos(np.clip(np.sum(units[:-1] * units[1:], axis=-1), -1.0, 1.0))
        total = float(np.sum(np.abs(turns)))
        base["mean_abs_turn_deg"] = float(np.degrees(np.mean(np.abs(turns)))) if turns.size else None
        base["total_abs_turn_deg"] = float(np.degrees(total)) if turns.size else None
        base["curvature_rad_per_unit"] = total / path_length if path_length > 0 else None
    return base


def movement_phase_summaries(
    values: dict[str, np.ndarray],
    start_frame: int,
    end_frame: int,
    forward_swing_frame: int | None,
    release_frame: int | None,
) -> dict[str, float | int | None]:
    """Return transparent movement- and forward-swing descriptors."""
    if not 0 <= start_frame <= end_frame:
        raise ValueError("Movement interval is invalid")
    stop = end_frame + 1
    summaries: dict[str, float | int | None] = {}
    elbow = np.asarray(values["elbow_angle_deg"], float)[start_frame:stop]
    finite_elbow = elbow[np.isfinite(elbow)]
    summaries["elbow_angle_deg_min"] = float(np.min(finite_elbow)) if finite_elbow.size else None
    summaries["elbow_angle_deg_max"] = float(np.max(finite_elbow)) if finite_elbow.size else None
    summaries["elbow_angle_deg_rom"] = (
        float(np.max(finite_elbow) - np.min(finite_elbow)) if finite_elbow.size else None
    )
    deficit = 180.0 - elbow
    finite_deficit = deficit[np.isfinite(deficit)]
    summaries["elbow_extension_deficit_deg_mean"] = (
        float(np.mean(finite_deficit)) if finite_deficit.size else None
    )
    if release_frame is not None and 0 <= release_frame < len(values["elbow_angle_deg"]):
        release_elbow = values["elbow_angle_deg"][release_frame]
        summaries["elbow_angle_deg_at_release"] = float(release_elbow) if np.isfinite(release_elbow) else None
        summaries["elbow_extension_deficit_deg_at_release"] = (
            float(180.0 - release_elbow) if np.isfinite(release_elbow) else None
        )
        radius = values.get("shoulder_wrist_radius_arm_lengths")
        summaries["shoulder_wrist_radius_at_release_arm_lengths"] = (
            float(radius[release_frame]) if radius is not None and np.isfinite(radius[release_frame]) else None
        )
        bag_radius = values.get("shoulder_bag_radius_arm_lengths")
        summaries["shoulder_bag_radius_at_release_arm_lengths"] = (
            float(bag_radius[release_frame]) if bag_radius is not None and np.isfinite(bag_radius[release_frame]) else None
        )

    wrist_metrics = path_shape_metrics(np.asarray(values["wrist_path_arm_lengths"])[start_frame:stop])
    path_names = {
        "sample_count": "sample_count",
        "coverage": "coverage",
        "path_length": "length_arm_lengths",
        "net_displacement": "net_displacement_arm_lengths",
        "straightness": "straightness_ratio",
        "rms_line_deviation": "rms_fitted_line_deviation_arm_lengths",
        "mean_abs_turn_deg": "mean_abs_turn_deg",
        "total_abs_turn_deg": "total_abs_turn_deg",
        "curvature_rad_per_unit": "curvature_rad_per_arm_length",
    }
    for key, value in wrist_metrics.items():
        summaries[f"wrist_path_{path_names[key]}"] = value
    shoulder_metrics = path_shape_metrics(np.asarray(values["shoulder_translation_arm_lengths"])[start_frame:stop])
    summaries["shoulder_translation_path_length_arm_lengths"] = shoulder_metrics["path_length"]
    summaries["shoulder_translation_net_arm_lengths"] = shoulder_metrics["net_displacement"]
    summaries["shoulder_translation_straightness"] = shoulder_metrics["straightness"]

    for source, stem in (
        ("shoulder_speed_arm_lengths_s", "shoulder_peak_speed_arm_lengths_s"),
        ("wrist_global_speed_arm_lengths_s", "wrist_global_peak_speed_arm_lengths_s"),
        ("wrist_relative_speed_arm_lengths_s", "wrist_relative_peak_speed_arm_lengths_s"),
    ):
        data = np.asarray(values[source], float)[start_frame:stop]
        finite = data[np.isfinite(data)]
        summaries[stem] = float(np.max(finite)) if finite.size else None

    if (
        forward_swing_frame is not None and release_frame is not None
        and 0 <= forward_swing_frame < release_frame < len(values["elbow_angle_deg"])
    ):
        phase = slice(forward_swing_frame, release_frame + 1)
        radius = np.asarray(values["shoulder_wrist_radius_arm_lengths"], float)[phase]
        finite_radius = radius[np.isfinite(radius)]
        summaries["shoulder_wrist_radius_forward_swing_mean_arm_lengths"] = (
            float(np.mean(finite_radius)) if finite_radius.size else None
        )
        summaries["shoulder_wrist_radius_forward_swing_sd_arm_lengths"] = (
            float(np.std(finite_radius, ddof=1)) if finite_radius.size > 1 else None
        )
        summaries["shoulder_wrist_radius_forward_swing_range_arm_lengths"] = (
            float(np.ptp(finite_radius)) if finite_radius.size else None
        )
        orientation = np.asarray(values["shoulder_wrist_orientation_deg"], float)[phase]
        finite_orientation = orientation[np.isfinite(orientation)]
        summaries["shoulder_wrist_angular_sweep_forward_swing_deg"] = (
            float(np.ptp(finite_orientation)) if finite_orientation.size else None
        )
        summaries["shoulder_wrist_angular_net_change_forward_swing_deg"] = (
            float(finite_orientation[-1] - finite_orientation[0]) if finite_orientation.size > 1 else None
        )
        angular_velocity = np.asarray(values["shoulder_wrist_angular_velocity_deg_s"], float)[phase]
        finite_angular_velocity = angular_velocity[np.isfinite(angular_velocity)]
        summaries["shoulder_wrist_peak_angular_velocity_forward_swing_deg_s"] = (
            float(np.max(np.abs(finite_angular_velocity))) if finite_angular_velocity.size else None
        )
        forward_path = path_shape_metrics(np.asarray(values["wrist_path_arm_lengths"])[phase])
        for key, value in forward_path.items():
            summaries[f"wrist_forward_swing_path_{path_names[key]}"] = value
        start_elbow = values["elbow_angle_deg"][forward_swing_frame]
        release_elbow = values["elbow_angle_deg"][release_frame]
        summaries["elbow_extension_change_forward_swing_deg"] = (
            float(release_elbow - start_elbow)
            if np.isfinite(start_elbow) and np.isfinite(release_elbow) else None
        )
    return summaries


def calculate_kinematics(
    filtered_coords: np.ndarray,
    landmarks: tuple[str, ...],
    fps: float,
    throwing_side: str,
    target_direction: str,
    minimum_velocity_coverage: float = 0.80,
    bag_coords: np.ndarray | None = None,
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
    shoulder_global = _analysis_points(shoulder, target_direction)
    wrist_global = _analysis_points(wrist, target_direction)
    shoulder_translation = _center_on_first_finite(shoulder_global)
    wrist_relative_pixels = _analysis_points(wrist - shoulder, target_direction)
    shoulder_wrist_radius = np.linalg.norm(normalized_wrist, axis=-1)
    shoulder_wrist_orientation = signed_orientation_degrees(normalized_wrist)

    values: dict[str, np.ndarray] = {
        "elbow_angle_deg": elbow_angle,
        "upper_arm_orientation_deg": upper_orientation,
        "forearm_orientation_deg": forearm_orientation,
        "arm_to_trunk_deg": arm_to_trunk,
        "trunk_inclination_deg": trunk_inclination,
        "wrist_path_arm_lengths": normalized_wrist,
        "elbow_path_arm_lengths": normalized_elbow,
        "elbow_extension_deficit_deg": 180.0 - elbow_angle,
        "shoulder_global_position_px": shoulder_global,
        "wrist_global_position_px": wrist_global,
        "shoulder_translation_px": shoulder_translation,
        "shoulder_translation_arm_lengths": shoulder_translation / arm_length,
        "wrist_relative_position_px": wrist_relative_pixels,
        "shoulder_wrist_radius_arm_lengths": shoulder_wrist_radius,
        "shoulder_wrist_orientation_deg": shoulder_wrist_orientation,
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
    # Translational decomposition is kinematic only; it is not a force contribution.
    velocity_sources = {
        "shoulder_velocity_px_s": shoulder_global,
        "wrist_global_velocity_px_s": wrist_global,
        "wrist_relative_velocity_px_s": wrist_relative_pixels,
    }
    for name, source in velocity_sources.items():
        coverage = float(np.mean(np.isfinite(source).all(axis=-1)))
        values[name] = derivative(source, fps) if coverage >= minimum_velocity_coverage else np.full_like(source, np.nan)
        if coverage < minimum_velocity_coverage:
            warnings.append(f"{name}: {coverage:.0%} finite coverage is below the velocity reporting threshold.")
    values["shoulder_velocity_arm_lengths_s"] = values["shoulder_velocity_px_s"] / arm_length
    values["wrist_global_velocity_arm_lengths_s"] = values["wrist_global_velocity_px_s"] / arm_length
    values["wrist_relative_velocity_arm_lengths_s"] = values["wrist_relative_velocity_px_s"] / arm_length
    for stem in ("shoulder", "wrist_global", "wrist_relative"):
        values[f"{stem}_speed_px_s"] = np.linalg.norm(values[f"{stem}_velocity_px_s"], axis=-1)
        values[f"{stem}_speed_arm_lengths_s"] = np.linalg.norm(values[f"{stem}_velocity_arm_lengths_s"], axis=-1)
    for first, last in _finite_runs(np.isfinite(values["shoulder_wrist_orientation_deg"])):
        values["shoulder_wrist_orientation_deg"][first:last] = np.degrees(
            np.unwrap(np.radians(values["shoulder_wrist_orientation_deg"][first:last]))
        )
    values["shoulder_wrist_angular_velocity_deg_s"] = derivative(
        values["shoulder_wrist_orientation_deg"], fps
    )
    if bag_coords is not None:
        bag = np.asarray(bag_coords, float)
        if bag.shape != shoulder.shape:
            raise ValueError("bag_coords must match the pose frame count and have shape [frame, 2]")
        values["bag_global_position_px"] = _analysis_points(bag, target_direction)
        values["bag_path_arm_lengths"] = throw_centered_points(bag, shoulder, arm_length, target_direction)
        values["shoulder_bag_radius_arm_lengths"] = np.linalg.norm(values["bag_path_arm_lengths"], axis=-1)
    summaries: dict[str, float | None] = {}
    for field in ANGLE_FIELDS:
        summaries[f"{field}_mean"] = _nan_summary(values[field], "mean")
        summaries[f"{field}_rom"] = _nan_summary(values[field], "rom")
        velocity_field = field.replace("_deg", "_velocity_deg_s")
        summaries[f"{velocity_field}_mean"] = _nan_summary(values[velocity_field], "mean")
        summaries[f"{velocity_field}_peak_abs"] = _nan_summary(values[velocity_field], "peak_abs")
    summaries.update(movement_phase_summaries(values, 0, len(filtered_coords) - 1, None, None))
    return KinematicResult(
        time_seconds=np.arange(len(filtered_coords), dtype=float) / fps,
        values=values,
        summaries=summaries,
        arm_length_pixels=float(arm_length),
        warnings=warnings,
    )
