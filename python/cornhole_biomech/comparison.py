"""Time-preserving reference comparison and transparent similarity scoring."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np


ANGLE_COMPARISON_FIELDS = (
    "elbow_angle_deg",
    "upper_arm_orientation_deg",
    "forearm_orientation_deg",
    "arm_to_trunk_deg",
    "trunk_inclination_deg",
)


def _paired(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    aa, bb = np.asarray(a, float), np.asarray(b, float)
    valid = np.isfinite(aa) & np.isfinite(bb)
    return aa[valid], bb[valid]


def curve_errors(test: np.ndarray, reference: np.ndarray) -> dict[str, float | None]:
    """Return time-preserving errors without warping away timing differences."""
    a, b = _paired(test, reference)
    if not a.size:
        return {"mae": None, "rmse": None, "correlation": None, "paired_samples": 0}
    error = a - b
    if a.size >= 3 and np.std(a) > 1e-12 and np.std(b) > 1e-12:
        correlation: float | None = float(np.corrcoef(a, b)[0, 1])
    else:
        correlation = None
    return {
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "correlation": correlation,
        "paired_samples": int(a.size),
    }


def path_rmse(test: np.ndarray, reference: np.ndarray) -> float | None:
    """Euclidean RMSE for paired dimensionless 2D path samples."""
    a, b = np.asarray(test, float), np.asarray(reference, float)
    valid = np.isfinite(a).all(axis=-1) & np.isfinite(b).all(axis=-1)
    if not np.any(valid):
        return None
    squared_distance = np.sum((a[valid] - b[valid]) ** 2, axis=-1)
    return float(np.sqrt(np.mean(squared_distance)))


def _peak_and_rom_difference(test: np.ndarray, reference: np.ndarray) -> tuple[float | None, float | None]:
    a, b = _paired(test, reference)
    if not a.size:
        return None, None
    peak = float(abs(np.max(a) - np.max(b)))
    rom = float(abs((np.max(a) - np.min(a)) - (np.max(b) - np.min(b))))
    return peak, rom


def build_reference_set(trials: list[dict[str, np.ndarray]]) -> dict[str, dict[str, np.ndarray]]:
    """Build pointwise reference mean/SD/count while retaining natural variability."""
    if not trials:
        raise ValueError("at least one reference trial is required")
    common = set(trials[0])
    for trial in trials[1:]:
        common &= set(trial)
    result: dict[str, dict[str, np.ndarray]] = {}
    for field in sorted(common):
        stack = np.stack([np.asarray(trial[field], float) for trial in trials])
        with np.errstate(invalid="ignore", divide="ignore"):
            result[field] = {
                "mean": np.nanmean(stack, axis=0),
                "sd": np.nanstd(stack, axis=0, ddof=1) if len(trials) > 1 else np.zeros_like(stack[0]),
                "count": np.sum(np.isfinite(stack), axis=0),
            }
    return result


def compare_normalized(
    test: dict[str, np.ndarray],
    reference_set: dict[str, dict[str, np.ndarray]],
    test_event_timing: dict[str, float | None],
    reference_event_timing: dict[str, float | None],
) -> dict[str, Any]:
    """Compare normalized motion using raw biomechanical errors first."""
    metrics: dict[str, Any] = {}
    for field in ANGLE_COMPARISON_FIELDS:
        if field not in test or field not in reference_set:
            continue
        errors = curve_errors(test[field], reference_set[field]["mean"])
        peak, rom = _peak_and_rom_difference(test[field], reference_set[field]["mean"])
        stem = field.removesuffix("_deg")
        metrics[f"{stem}_mae_deg"] = errors["mae"]
        metrics[f"{stem}_rmse_deg"] = errors["rmse"]
        metrics[f"{stem}_waveform_correlation"] = errors["correlation"]
        metrics[f"{stem}_peak_difference_deg"] = peak
        metrics[f"{stem}_rom_difference_deg"] = rom
        metrics[f"{stem}_paired_samples"] = errors["paired_samples"]
    for joint in ("wrist", "elbow"):
        field = f"{joint}_path_arm_lengths"
        if field in test and field in reference_set:
            metrics[f"{joint}_path_rmse_arm_lengths"] = path_rmse(
                test[field], reference_set[field]["mean"]
            )
    for event in sorted(set(test_event_timing) & set(reference_event_timing)):
        a, b = test_event_timing[event], reference_event_timing[event]
        metrics[f"{event}_timing_abs_difference_cycle"] = (
            None if a is None or b is None else abs(float(a) - float(b))
        )
    return metrics


def similarity_score(metrics: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Transform configured errors into visible component scores and weighted mean.

    score = 100 * max(0, 1 - error/tolerance). Tolerances are configuration,
    not norms. Missing components are omitted and explicitly listed.
    """
    components: dict[str, Any] = {}
    weighted_sum = 0.0
    weight_sum = 0.0
    omitted: list[str] = []
    for metric, settings in config["components"].items():
        value = metrics.get(metric)
        if value is None or not math.isfinite(float(value)):
            omitted.append(metric)
            continue
        tolerance = float(settings["tolerance"])
        weight = float(settings["weight"])
        score = 100.0 * max(0.0, 1.0 - float(value) / tolerance)
        components[metric] = {
            "raw_error": float(value),
            "tolerance": tolerance,
            "weight": weight,
            "score": score,
            "formula": "100 * max(0, 1 - raw_error / tolerance)",
        }
        weighted_sum += score * weight
        weight_sum += weight
    return {
        "overall": weighted_sum / weight_sum if weight_sum > 0 else None,
        "components": components,
        "omitted_components": omitted,
        "tolerance_status": "provisional_pilot_tolerances_not_population_norms",
        "interpretation": "reference_similarity_not_performance_quality",
    }


def assert_compatible_views(test_view: str, reference_views: list[str]) -> None:
    incompatible = sorted({view for view in reference_views if view != test_view})
    if incompatible:
        raise ValueError(
            f"Cannot compare camera view '{test_view}' with incompatible reference view(s): {', '.join(incompatible)}"
        )

