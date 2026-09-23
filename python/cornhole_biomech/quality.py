"""Measurement-quality summaries that prevent polished output hiding poor data."""

from __future__ import annotations

from typing import Any
import numpy as np


def quality_summary(
    raw_coords: np.ndarray,
    confidence: np.ndarray,
    effective_coords: np.ndarray,
    manual_mask: np.ndarray,
    interpolated_mask: np.ndarray,
    landmarks: tuple[str, ...],
    fps: float,
    width: int,
    height: int,
    camera_view: str,
    confidence_threshold: float,
    throwing_side: str,
) -> dict[str, Any]:
    finite_conf = confidence[np.isfinite(confidence)]
    raw_present = np.isfinite(raw_coords).all(axis=-1)
    usable = np.isfinite(effective_coords).all(axis=-1)
    low_counts = {
        name: int(np.count_nonzero((confidence[:, j] < confidence_threshold) | ~raw_present[:, j]))
        for j, name in enumerate(landmarks)
    }
    required_names = (
        "left_shoulder",
        "right_shoulder",
        f"{throwing_side}_elbow",
        f"{throwing_side}_wrist",
        "left_hip",
        "right_hip",
    )
    lookup = {name: index for index, name in enumerate(landmarks)}
    required_indices = [lookup[name] for name in required_names if name in lookup]
    required_usable = usable[:, required_indices] if required_indices else np.zeros((len(usable), 1), bool)
    usable_frames = np.all(required_usable, axis=1)
    warnings: list[str] = []
    throwing_arm_missing = 1.0 - float(np.mean(usable_frames))
    if throwing_arm_missing > 0.20:
        warnings.append(f"Throwing-arm/trunk landmarks are unusable in {throwing_arm_missing:.0%} of frames.")
    average_confidence = float(np.mean(finite_conf)) if finite_conf.size else None
    if average_confidence is None or average_confidence < confidence_threshold:
        warnings.append("Average markerless pose confidence is below the configured threshold.")
    if required_indices:
        required_raw = raw_coords[:, required_indices, :]
        finite_required = np.isfinite(required_raw).all(axis=-1)
        boundary = (
            (required_raw[..., 0] < 0.02 * width)
            | (required_raw[..., 0] > 0.98 * width)
            | (required_raw[..., 1] < 0.02 * height)
            | (required_raw[..., 1] > 0.98 * height)
        ) & finite_required
        if float(np.mean(np.any(boundary, axis=1))) > 0.10:
            warnings.append("Required landmarks frequently touch the image boundary; the person or throwing arm may be cropped.")
    if fps < 30:
        warnings.append("Frame rate is below 30 fps; event timing and peak velocity are not reliable.")
    elif fps < 60:
        warnings.append("Frame rate is below the recommended 60 fps; release timing is coarsely sampled.")
    if camera_view != "side":
        warnings.append("This is not a Side view; primary Stage 1 reference scoring is not recommended.")
    interpolation_fraction = float(np.mean(interpolated_mask))
    if interpolation_fraction > 0.10:
        warnings.append(f"{interpolation_fraction:.0%} of landmark samples were interpolated.")
    return {
        "average_pose_confidence": average_confidence,
        "usable_frame_percentage": 100.0 * float(np.mean(usable_frames)),
        "missing_data_percentage": 100.0 * (1.0 - float(np.mean(usable))),
        "low_confidence_landmark_counts": low_counts,
        "manual_correction_count": int(np.count_nonzero(manual_mask)),
        "interpolated_sample_count": int(np.count_nonzero(interpolated_mask)),
        "frame_rate_fps": fps,
        "resolution_pixels": {"width": width, "height": height},
        "camera_view": camera_view,
        "warnings": warnings,
        "confidence_note": "Model confidence is not a calibrated physical position or angle error.",
    }


# ---------------------------------------------------------------- per-trial grades
# Provisional thresholds, stated so they can be defended or changed; replace with
# values from the annotation study (docs/BAG_TRACKING_VALIDATION.md) when available.
GRADE_RULES = {
    "pose": "GOOD: required landmarks usable in ≥90% of frames and ≥90% of frames within ±50 ms of release. "
            "WARNING: ≥70% and ≥60%. Otherwise POOR.",
    "bag": "GOOD: bag found in ≥90% of flight frames, no gap longer than 3 frames, ≤10% of samples rejected as "
           "outliers, measurement noise σ ≤ 2 px. WARNING: ≥70% coverage and no gap longer than 6 frames. "
           "Otherwise POOR. No tracked flight is POOR.",
    "calibration": "GOOD: an independent in-plane scale agrees with the flight's gravity scale within 10%. "
                   "WARNING: a single scale source (gravity-only or measured-only). POOR: no physical scale "
                   "(results stay in pixels / arm lengths).",
    "release": "GOOD: release confirmed by a person, or found automatically with the first flight point within "
               "0.5 arm lengths of the wrist, ≥6 launch-fit samples and launch-angle SE ≤ 3°. WARNING: automatic "
               "release failing one of those. POOR: no confirmed release.",
}


def _grade(good: bool, warning: bool) -> str:
    return "GOOD" if good else "WARNING" if warning else "POOR"


def quality_grades(quality: dict[str, Any], flight_filter: dict[str, Any] | None,
                   gravity_scale: dict[str, Any] | None, measured_scale: bool,
                   release_confirmed_by: str | None, release_wrist_distance_arm_lengths: float | None,
                   launch_sample_count: int | None, launch_angle_se_deg: float | None) -> dict[str, Any]:
    """GOOD / WARNING / POOR per measurement stage, each with the numbers that decided it."""
    grades: dict[str, Any] = {"rules": GRADE_RULES}

    usable = quality.get("usable_frame_percentage") or 0.0
    release_vis = quality.get("release_visibility")
    rv = 0.0 if release_vis is None else 100.0 * release_vis
    grades["pose"] = {"grade": _grade(usable >= 90 and rv >= 90, usable >= 70 and rv >= 60),
                      "usable_frame_percentage": usable, "release_window_visible_percentage": rv if release_vis is not None else None}

    if not flight_filter or flight_filter.get("status") != "filtered":
        grades["bag"] = {"grade": "POOR", "reason": "No tracked flight: insufficient tracking quality."}
    else:
        frames = flight_filter["last_frame"] - flight_filter["first_frame"] + 1
        measured = len(flight_filter.get("measured_frames") or []) or (
            flight_filter["measurement_count"] - len(flight_filter["rejected_outlier_frames"]))
        coverage = measured / frames if frames else 0.0
        outliers = len(flight_filter["rejected_outlier_frames"]) / max(1, flight_filter["measurement_count"])
        gap, sigma = flight_filter["longest_gap_frames"], flight_filter["measurement_sigma_px"]
        grades["bag"] = {"grade": _grade(coverage >= 0.9 and gap <= 3 and outliers <= 0.1 and sigma <= 2.0,
                                         coverage >= 0.7 and gap <= 6),
                         "flight_coverage": coverage, "longest_gap_frames": gap,
                         "outlier_share": outliers, "measurement_sigma_px": sigma}

    gravity_ok = bool(gravity_scale and gravity_scale.get("status") == "estimated")
    ratio = (gravity_scale or {}).get("scale_ratio_to_reference")
    grades["calibration"] = {
        "grade": _grade(measured_scale and gravity_ok and ratio is not None and abs(ratio - 1) <= 0.10,
                        measured_scale or gravity_ok),
        "measured_scale": measured_scale, "gravity_scale": gravity_ok, "gravity_to_measured_ratio": ratio,
        "note": "A gravity scale assumes the flight plane is square to the camera; it is not a 3D calibration."}

    if release_confirmed_by == "manual":
        release_grade = "GOOD"
    elif release_confirmed_by == "automatic_physics":
        checks = [release_wrist_distance_arm_lengths is not None and release_wrist_distance_arm_lengths <= 0.5,
                  (launch_sample_count or 0) >= 6,
                  launch_angle_se_deg is not None and launch_angle_se_deg <= 3.0]
        release_grade = "GOOD" if all(checks) else "WARNING"
    else:
        release_grade = "POOR"
    grades["release"] = {"grade": release_grade, "confirmed_by": release_confirmed_by,
                         "wrist_distance_arm_lengths": release_wrist_distance_arm_lengths,
                         "launch_fit_samples": launch_sample_count, "launch_angle_se_deg": launch_angle_se_deg}
    return grades
