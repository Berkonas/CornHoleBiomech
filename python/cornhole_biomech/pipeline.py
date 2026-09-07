"""End-to-end reproducible analysis, comparison, and repeated-trial workflows."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable
import json

import numpy as np

from . import REQUIRED_LANDMARKS, __version__
from .comparison import (
    assert_compatible_views,
    build_reference_set,
    compare_normalized,
    similarity_score,
)
from .config import merged_config, validate_config
from .corrections import apply_corrections, interpolate_short_gaps, pose_arrays
from .events import apply_manual_event_overrides, detect_events
from .export import (
    annotate_video,
    export_keypoints_csv,
    export_kinematics_csv,
    markdown_summary,
    plot_angles_angles,
    plot_comparison,
    plot_wrist_trajectory,
)
from .filtering import lowpass_zero_phase
from .kinematics import calculate_kinematics
from .models import CorrectionSet, PoseSequence, TrialContext, utc_now
from .normalization import normalized_event_timing, resample_curve
from .pose import analyze_pose
from .quality import quality_summary
from .serialization import canonical_hash, json_ready, write_json
from .statistics import grouped_summary, relationship
from .video import file_sha256, read_video_metadata

Progress = Callable[[str, float, str], None]


def _no_progress(stage: str, fraction: float, message: str) -> None:
    del stage, fraction, message


def _load_json(path: str | Path | None, default: Any) -> Any:
    if path is None or not Path(path).exists():
        return default
    return json.loads(Path(path).read_text())


def _manual_event_overrides(path: Path) -> dict[str, int | None]:
    value = _load_json(path, {})
    if "manual_overrides" in value:
        return value["manual_overrides"]
    if "events" in value:
        return {name: item.get("manual_frame") for name, item in value["events"].items()}
    return {}


def analyze_trial(
    context: TrialContext,
    output_dir: str | Path,
    config_overrides: dict[str, Any] | None = None,
    backend: str = "rtmpose",
    pose_input: str | Path | None = None,
    corrections_path: str | Path | None = None,
    events_path: str | Path | None = None,
    device: str = "cpu",
    force_pose: bool = False,
    make_annotated_video: bool = True,
    app_version: str = "0.1.0",
    progress: Progress = _no_progress,
) -> dict[str, Any]:
    """Analyze one trial and write a deterministic, inspectable result package."""
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    progress("loading_video", 0.02, "Reading video metadata without modifying the source")
    video = read_video_metadata(context.source_video)
    config = merged_config(config_overrides)
    validate_config(config, video.fps)

    pose_path = output / "pose_raw.json"
    cache_path = output / "pose_cache.json"
    pose_key = canonical_hash({
        "video_sha256": video.sha256,
        "backend": "import" if pose_input else backend,
        "pose_input": str(Path(pose_input).resolve()) if pose_input else None,
        "pose_input_sha256": file_sha256(pose_input) if pose_input else None,
        "device": device,
    })
    cache = _load_json(cache_path, {})
    if pose_path.exists() and cache.get("pose_key") == pose_key and not force_pose:
        progress("detecting_pose", 0.40, "Using cached raw pose predictions")
        sequence = PoseSequence.load(pose_path)
    else:
        sequence = analyze_pose(video, backend, progress, pose_input=pose_input, device=device)
        sequence.save(pose_path)
        write_json(cache_path, {"pose_key": pose_key, "created_at": utc_now()})
    if sequence.frame_count != len(sequence.frames):
        raise ValueError("pose frame_count does not match stored frames")

    progress("applying_corrections", 0.46, "Applying non-destructive corrections and confidence mask")
    landmarks = tuple(sequence.frames[0].landmarks.keys()) if sequence.frames else REQUIRED_LANDMARKS
    for required in REQUIRED_LANDMARKS:
        if required not in landmarks:
            raise ValueError(f"Pose backend did not provide required landmark: {required}")
    raw, confidence = pose_arrays(sequence, landmarks)
    corrections = CorrectionSet.load(corrections_path or (output / "corrections.json"))
    corrections.save(output / "corrections.json")
    effective, manual_mask, low_confidence = apply_corrections(
        raw, confidence, landmarks, corrections, float(config["confidence_threshold"])
    )
    gap_handled, interpolated_mask = interpolate_short_gaps(
        effective, int(config["max_interpolation_gap_frames"])
    )

    progress("filtering", 0.53, "Filtering coordinates before calculating angles and velocities")
    filter_config = config["filter"]
    filter_warnings: list[str] = []
    effective_cutoff: float | None = None
    if filter_config["enabled"] and filter_config["type"] != "none":
        filtered, effective_cutoff, filter_warnings = lowpass_zero_phase(
            gap_handled,
            video.fps,
            float(filter_config["cutoff_hz"]),
            int(filter_config["order"]),
        )
    else:
        filtered = np.array(gap_handled, copy=True)

    progress("calculating_kinematics", 0.62, "Calculating projected 2D upper-body measures")
    kinematics = calculate_kinematics(
        filtered,
        landmarks,
        video.fps,
        context.throwing_side,
        context.target_direction,
        float(config["minimum_velocity_coverage"]),
    )
    event_file = Path(events_path) if events_path else output / "events.json"
    progress("detecting_events", 0.68, "Detecting frame-limited movement event candidates")
    events = detect_events(kinematics.values["wrist_path_arm_lengths"], video.fps)
    events = apply_manual_event_overrides(events, _manual_event_overrides(event_file))
    start = events["motion_start"].effective_frame
    end = events["motion_end"].effective_frame
    if start is None or end is None or end <= start:
        start, end = 0, sequence.frame_count - 1
        filter_warnings.append("Motion bounds could not be detected; full-video bounds were used.")
    event_payload = {
        "schema_version": 1,
        "frame_interval_seconds": 1.0 / video.fps,
        "release_precision_note": "Visible release is frame-limited and is not a sub-frame measurement of bag-hand separation.",
        "events": {name: {**asdict(value), "effective_frame": value.effective_frame} for name, value in events.items()},
        "manual_overrides": {name: value.manual_frame for name, value in events.items() if value.manual_frame is not None},
    }
    write_json(output / "events.json", event_payload)

    progress("normalizing", 0.74, "Normalizing body scale and movement time")
    normalized_values: dict[str, np.ndarray] = {}
    tau: np.ndarray | None = None
    for name, values in kinematics.values.items():
        tau, normalized = resample_curve(values, start, end, int(config["normalization_samples"]))
        normalized_values[name] = normalized
    assert tau is not None
    event_timing = {
        name: normalized_event_timing(value.effective_frame, start, end) for name, value in events.items()
    }
    release_frame = events["release"].effective_frame
    summaries = dict(kinematics.summaries)
    summaries["movement_duration_seconds"] = (end - start) / video.fps
    summaries["release_timing_cycle"] = event_timing["release"]
    if release_frame is not None and 0 <= release_frame < sequence.frame_count:
        for field in ("elbow_angle_deg", "trunk_inclination_deg", "arm_to_trunk_deg"):
            value = kinematics.values[field][release_frame]
            summaries[f"{field}_at_release"] = float(value) if np.isfinite(value) else None

    quality = quality_summary(
        raw, confidence, effective, manual_mask, interpolated_mask, landmarks,
        video.fps, video.width, video.height, context.camera_view,
        float(config["confidence_threshold"]), context.throwing_side,
    )
    warnings = sorted(set(filter_warnings + kinematics.warnings))
    results = {
        "schema_version": 1,
        "trial_id": context.trial_id,
        "athlete_id": context.athlete_id,
        "camera_view": context.camera_view,
        "throwing_side": context.throwing_side,
        "target_direction": context.target_direction,
        "summaries": summaries,
        "quality": quality,
        "events": event_payload["events"],
        "warnings": warnings,
        "claim_scope": "projected_2d_kinematics_not_true_3d_joint_orientation",
    }
    normalized_payload = {
        "schema_version": 1,
        "trial_id": context.trial_id,
        "athlete_id": context.athlete_id,
        "camera_view": context.camera_view,
        "throwing_side": context.throwing_side,
        "target_direction": context.target_direction,
        "tau": tau,
        "values": normalized_values,
        "event_timing": event_timing,
        "arm_length_pixels": kinematics.arm_length_pixels,
    }

    progress("saving_results", 0.82, "Writing transparent CSV, JSON, plots, and manifest")
    times = np.arange(sequence.frame_count, dtype=float) / video.fps
    export_keypoints_csv(
        output / "keypoints.csv", times, landmarks, raw, confidence, effective, filtered,
        manual_mask, interpolated_mask,
    )
    export_kinematics_csv(output / "kinematics.csv", times, kinematics.values)
    write_json(output / "normalized.json", normalized_payload)
    write_json(output / "results.json", results)
    plot_angles_angles(output / "angle_trajectories.png", tau, normalized_values,
                       f"Projected 2D angles - Trial {context.trial_id}")
    plot_wrist_trajectory(output / "wrist_trajectory.png", normalized_values["wrist_path_arm_lengths"],
                          f"Shoulder-relative wrist path - Trial {context.trial_id}")
    (output / "summary.md").write_text(markdown_summary(json_ready(results)))
    if make_annotated_video:
        progress("annotating_video", 0.88, "Rendering skeleton overlay video")
        annotate_video(
            video.path, output / "annotated.mp4", filtered, confidence, landmarks,
            float(config["confidence_threshold"]), manual_mask,
        )
    manifest = {
        "schema_version": 1,
        "analysis_id": canonical_hash({
            "trial": context.trial_id,
            "video": video.sha256,
            "pose": pose_key,
            "corrections": canonical_hash(asdict(corrections)),
            "events": canonical_hash(event_payload["manual_overrides"]),
            "config": config,
        }),
        "created_at": utc_now(),
        "app_version": app_version,
        "python_package": "cornhole-biomech",
        "python_package_version": __version__,
        "pose_backend": sequence.backend,
        "pose_model": sequence.model_name,
        "pose_model_version": sequence.model_version,
        "pose_model_sha256": sequence.model_sha256,
        "pose_backend_metadata": sequence.backend_metadata,
        "source_video": video.to_dict(),
        "trial_context": asdict(context),
        "analysis_configuration": config,
        "effective_filter_cutoff_hz": effective_cutoff,
        "confidence_threshold": config["confidence_threshold"],
        "manual_correction_hash": canonical_hash(asdict(corrections)),
        "reference_trial_ids": [],
        "outputs": sorted(p.name for p in output.iterdir() if p.is_file()),
    }
    write_json(output / "manifest.json", manifest)
    progress("complete", 1.0, "Analysis complete")
    return {"output_dir": str(output), "results": results, "manifest": manifest}


def compare_trial(
    test_dir: str | Path,
    reference_dirs: list[str | Path],
    output_dir: str | Path,
    config_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare a trial with one or more compatible-view references."""
    if not reference_dirs:
        raise ValueError("at least one reference directory is required")
    test_payload = _load_json(Path(test_dir) / "normalized.json", None)
    if test_payload is None:
        raise FileNotFoundError(f"Missing normalized.json in {test_dir}")
    references = [_load_json(Path(path) / "normalized.json", None) for path in reference_dirs]
    if any(value is None for value in references):
        raise FileNotFoundError("Every reference directory must contain normalized.json")
    assert_compatible_views(test_payload["camera_view"], [item["camera_view"] for item in references])
    test_values = {name: np.asarray(value, float) for name, value in test_payload["values"].items()}
    reference_values = [
        {name: np.asarray(value, float) for name, value in item["values"].items()} for item in references
    ]
    reference_set = build_reference_set(reference_values)
    reference_event_timing: dict[str, float | None] = {}
    event_names = set().union(*(item["event_timing"].keys() for item in references))
    for name in event_names:
        values = [item["event_timing"].get(name) for item in references]
        finite = [float(value) for value in values if value is not None and np.isfinite(value)]
        reference_event_timing[name] = float(np.mean(finite)) if finite else None
    metrics = compare_normalized(
        test_values, reference_set, test_payload["event_timing"], reference_event_timing
    )
    config = merged_config(config_overrides)
    score = similarity_score(metrics, config["similarity"])
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    label = (
        "Prototype reference similarity - single reference trial"
        if len(references) == 1 else f"Prototype reference similarity - reference set of {len(references)} trials"
    )
    result = {
        "schema_version": 1,
        "test_trial_id": test_payload["trial_id"],
        "reference_trial_ids": [item["trial_id"] for item in references],
        "camera_view": test_payload["camera_view"],
        "label": label,
        "raw_metrics": metrics,
        "similarity": score,
        "claim_scope": "reference_similarity_not_performance_quality",
        "timing_method": "time_preserving_no_dynamic_time_warping",
    }
    write_json(output / "comparison.json", result)
    tau = np.asarray(test_payload["tau"], float)
    field = "elbow_angle_deg"
    if field in test_values and field in reference_set:
        plot_comparison(
            output / "comparison_elbow_angle.png", tau, test_values[field],
            reference_set[field]["mean"], reference_set[field]["sd"],
            "2D projected elbow angle", len(references),
        )
    return result


def analyze_relationships(
    analysis_dirs: list[str | Path],
    outcome_records: dict[str, dict[str, Any]],
    output_path: str | Path,
    minimum_trials: int = 8,
) -> dict[str, Any]:
    """Analyze selected movement features against outcome within one athlete."""
    rows: list[dict[str, Any]] = []
    athlete_ids: set[str] = set()
    for directory in analysis_dirs:
        result = _load_json(Path(directory) / "results.json", None)
        if result is None:
            continue
        athlete_ids.add(result["athlete_id"])
        outcome = outcome_records.get(result["trial_id"], {})
        row = {"trial_id": result["trial_id"], "score_category": outcome.get("score_category")}
        row.update(result.get("summaries", {}))
        spatial = outcome.get("spatial_error") or {}
        row["radial_error_inches"] = spatial.get("radial_error_inches")
        rows.append(row)
    if len(athlete_ids) > 1:
        raise ValueError("Initial relationship analysis is within-person; provide one athlete at a time")
    outcomes = [row.get("radial_error_inches") for row in rows]
    if not any(value is not None for value in outcomes):
        outcomes = [row.get("score_category") for row in rows]
        outcome_name = "score_category"
    else:
        outcome_name = "radial_error_inches"
    feature_names = (
        "elbow_angle_deg_at_release",
        "elbow_angle_deg_rom",
        "trunk_inclination_deg_at_release",
        "movement_duration_seconds",
        "release_timing_cycle",
    )
    relationships = {
        name: relationship([row.get(name) for row in rows], outcomes, minimum_trials)
        for name in feature_names
    }
    groups = {
        name: grouped_summary([row.get(name) for row in rows], [row.get("score_category") for row in rows])
        for name in feature_names
    }
    result = {
        "schema_version": 1,
        "athlete_id": next(iter(athlete_ids), None),
        "trial_count": len(rows),
        "outcome_variable": outcome_name,
        "relationships": relationships,
        "grouped_by_score": groups,
        "claim_scope": "within_athlete_observational_association_not_causation",
    }
    write_json(output_path, result)
    return result
