"""Versioned analysis configuration with explicit, reproducible defaults."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "schema_version": 1,
    "sports2d": {"pose_model": "body_with_feet", "mode": "balanced", "person_ordering_method": "highest_likelihood", "export_filter": "butterworth"},
    "confidence_threshold": 0.35,
    "max_interpolation_gap_frames": 3,
    "filter": {
        "enabled": True,
        "type": "butterworth_zero_phase",
        "order": 4,
        "cutoff_hz": 6.0,
    },
    "normalization_samples": 101,
    "minimum_velocity_coverage": 0.80,
    "minimum_relationship_trials": 8,
    "bag_tracking": {
        "method": "auto",
        "confidence_threshold": 0.20,
        "template_quality_threshold": 0.25,
        "template_search_scale": 2.5,
    },
    "bag_release": {
        "minimum_divergence_arm_lengths": 0.08,
        "persistence_seconds": 0.05,
    },
    "projectile": {
        "release_fit_window_seconds": 0.12,
        "minimum_velocity_points": 4,
        "acceleration_minimum_fps": 60.0,
        "acceleration_minimum_points": 6,
        "acceleration_maximum_fit_rmse_arm_lengths": 0.03,
    },
}


def merged_config(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return defaults recursively updated by user overrides without mutating either."""
    result = deepcopy(DEFAULT_CONFIG)

    def merge(target: dict[str, Any], source: dict[str, Any]) -> None:
        for key, value in source.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                merge(target[key], value)
            else:
                target[key] = deepcopy(value)

    if overrides:
        merge(result, overrides)
    validate_config(result)
    return result


def validate_config(config: dict[str, Any], fps: float | None = None) -> None:
    """Reject settings that would create misleading or numerically invalid results."""
    threshold = float(config["confidence_threshold"])
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("confidence_threshold must be between 0 and 1")
    if int(config["max_interpolation_gap_frames"]) < 0:
        raise ValueError("max_interpolation_gap_frames must be non-negative")
    if int(config["normalization_samples"]) < 3:
        raise ValueError("normalization_samples must be at least 3")
    if not 0.0 <= float(config["minimum_velocity_coverage"]) <= 1.0:
        raise ValueError("minimum_velocity_coverage must be between 0 and 1")
    if int(config["minimum_relationship_trials"]) < 3:
        raise ValueError("minimum_relationship_trials must be at least 3")
    filt = config["filter"]
    if filt["type"] not in {"butterworth_zero_phase", "none"}:
        raise ValueError("filter.type must be butterworth_zero_phase or none")
    if int(filt["order"]) < 1:
        raise ValueError("filter.order must be positive")
    if float(filt["cutoff_hz"]) <= 0:
        raise ValueError("filter.cutoff_hz must be positive")
    if filt["enabled"] and fps is not None and float(filt["cutoff_hz"]) >= 0.5 * fps:
        raise ValueError("filter.cutoff_hz must be below the Nyquist frequency")
    tracking = config["bag_tracking"]
    if tracking["method"] not in {"auto", "csrt", "template_matching", "color_motion"}:
        raise ValueError("bag_tracking.method must be auto, color_motion, csrt, or template_matching")
    for name in ("confidence_threshold", "template_quality_threshold"):
        if not 0.0 <= float(tracking[name]) <= 1.0:
            raise ValueError(f"bag_tracking.{name} must be between 0 and 1")
    if float(tracking["template_search_scale"]) <= 0:
        raise ValueError("bag_tracking.template_search_scale must be positive")
    release = config["bag_release"]
    if float(release["minimum_divergence_arm_lengths"]) <= 0:
        raise ValueError("bag_release.minimum_divergence_arm_lengths must be positive")
    if float(release["persistence_seconds"]) <= 0:
        raise ValueError("bag_release.persistence_seconds must be positive")
    projectile = config["projectile"]
    if float(projectile["release_fit_window_seconds"]) <= 0:
        raise ValueError("projectile.release_fit_window_seconds must be positive")
    if int(projectile["minimum_velocity_points"]) < 3:
        raise ValueError("projectile.minimum_velocity_points must be at least 3")
    if int(projectile["acceleration_minimum_points"]) < 4:
        raise ValueError("projectile.acceleration_minimum_points must be at least 4")
    if float(projectile["acceleration_minimum_fps"]) <= 0:
        raise ValueError("projectile.acceleration_minimum_fps must be positive")
    if float(projectile["acceleration_maximum_fit_rmse_arm_lengths"]) <= 0:
        raise ValueError("projectile.acceleration_maximum_fit_rmse_arm_lengths must be positive")
