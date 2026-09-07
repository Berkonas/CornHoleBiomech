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
        f"{throwing_side}_shoulder",
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
        "average_pose_confidence": float(np.mean(finite_conf)) if finite_conf.size else None,
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

