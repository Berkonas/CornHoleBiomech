"""Quality-gated descriptors of elbow motion, not a technique or dynamics score."""
from __future__ import annotations

import numpy as np


ARM_METRICS = {
    "arm_motion_mean_flexion_deg": "Mean projected elbow flexion (°)",
    "arm_motion_flexion_rom_deg": "Forward-swing elbow excursion (°)",
    "arm_motion_flexion_sd_deg": "Within-swing elbow flexion SD (°)",
    "arm_motion_radius_cv_ratio": "Forward-swing radius CV (ratio)",
}


def analyze_arm_motion(values, start_frame, end_frame, forward_frame, release_frame, camera_view):
    """Use native-rate filtered samples, inclusive forward swing to release.

    Five samples and 80% finite coverage are pragmatic availability gates, not
    validated accuracy thresholds. Radius has its own gate. No gaps are filled
    here. SD is sample SD (ddof=1), CV = sample SD / mean positive radius.
    """
    metrics = dict.fromkeys(ARM_METRICS)
    result = {
        "schema_version": 1, "status": "unavailable_phase", "summaries": metrics,
        "start_frame": forward_frame, "release_frame": release_frame,
        "sample_count": 0, "valid_sample_count": 0, "coverage": None,
        "radius_coverage": None, "minimum_samples": 5, "minimum_coverage": 0.8,
        "message": "Review forward-swing and release events inside the movement interval, then reanalyze.",
    }
    elbow = np.asarray(values["elbow_angle_deg"], float)
    if (forward_frame is None or release_frame is None
            or not 0 <= start_frame <= forward_frame < release_frame <= end_frame < len(elbow)):
        return result
    phase = slice(forward_frame, release_frame + 1)
    angle = elbow[phase]
    valid = np.isfinite(angle) & (angle >= 0) & (angle <= 180)
    count = int(np.count_nonzero(valid))
    result.update(sample_count=len(angle), valid_sample_count=count, coverage=count / len(angle))
    if camera_view != "side":
        result.update(status="unavailable_view", message="Arm-model descriptors require a side view. Other projections cannot establish elbow flexion.")
        return result
    if count < 5 or result["coverage"] < 0.8:
        result.update(status="insufficient_tracking", message="Too few usable elbow samples: at least 5 and 80% coverage of forward swing to release are required.")
        return result
    flexion = 180.0 - angle[valid]
    metrics.update(arm_motion_mean_flexion_deg=float(np.mean(flexion)),
                   arm_motion_flexion_rom_deg=float(np.ptp(flexion)),
                   arm_motion_flexion_sd_deg=float(np.std(flexion, ddof=1)))
    radius = np.asarray(values["shoulder_wrist_radius_arm_lengths"], float)[phase]
    usable = np.isfinite(radius) & (radius > 1e-12) & valid
    result["radius_coverage"] = float(np.count_nonzero(usable) / len(angle))
    if np.count_nonzero(usable) >= 5 and result["radius_coverage"] >= 0.8:
        metrics["arm_motion_radius_cv_ratio"] = float(np.std(radius[usable], ddof=1) / np.mean(radius[usable]))
    result.update(status="available", message="Lower elbow excursion describes a more fixed elbow during this swing. Mean flexion describes how bent it is. Neither establishes accuracy or better technique; a fixed bent elbow can also act as one rigid link.")
    return result
