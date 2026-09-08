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
    path_rmse,
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
from .models import BoardPoint, CorrectionSet, PoseSequence, TrialContext, TrialOutcome, utc_now
from .normalization import normalized_event_timing, resample_curve
from .outcomes import outcome_summary
from .pose import analyze_pose, _version
from .sports2d_adapter import Sports2DAdapter
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
    backend: str = "sports2d",
    pose_input: str | Path | None = None,
    corrections_path: str | Path | None = None,
    events_path: str | Path | None = None,
    device: str = "cpu",
    force_pose: bool = False,
    make_annotated_video: bool = True,
    app_version: str = "0.2.0",
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
        "backend_version": _version("sports2d" if backend == "sports2d" else "rtmlib" if backend == "rtmpose" else "mediapipe"),
        "model_configuration": config.get("sports2d") if backend == "sports2d" else None,
    })
    cache = _load_json(cache_path, {})
    if pose_path.exists() and cache.get("pose_key") == pose_key and not force_pose:
        progress("detecting_pose", 0.40, "Using cached raw pose predictions")
        sequence = PoseSequence.load(pose_path)
    else:
        if backend == "sports2d" and pose_input is None:
            sequence = Sports2DAdapter().analyze(video, output / "sports2d", config, progress, device)
        else:
            sequence = analyze_pose(video, backend, progress, pose_input=pose_input, device=device)
        sequence.save(pose_path)
        write_json(cache_path, {"pose_key": pose_key, "created_at": utc_now()})
    if sequence.frame_count < 3:
        raise ValueError("The recording needs at least three readable frames to measure movement")
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

    for correction in corrections.corrections:
        if correction.kind == "interpolated" and correction.landmark in landmarks and 0 <= correction.frame_index < len(effective):
            interpolated_mask[correction.frame_index, landmarks.index(correction.landmark)] = True

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
    for event in events.values():
        if event.effective_frame is not None and not 0 <= event.effective_frame < sequence.frame_count:
            raise ValueError(f"{event.name} frame lies outside the video. Choose a frame from 0 to {sequence.frame_count - 1}.")
    start = events["motion_start"].effective_frame
    end = events["motion_end"].effective_frame
    if start is None or end is None or end <= start:
        start, end = 0, sequence.frame_count - 1
        filter_warnings.append("Motion bounds could not be detected; full-video bounds were used.")
    ordered = [events[n].effective_frame for n in ("motion_start", "peak_backswing", "forward_swing", "release", "peak_follow_through", "motion_end")]
    present = [f for f in ordered if f is not None]
    if any(a > b for a, b in zip(present, present[1:])):
        raise ValueError("Movement events are out of order. Review start, backswing, forward swing, release, follow-through and end before reanalysis.")
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
    # Summaries describe the reviewed movement interval, not setup before/after it.
    from .kinematics import ANGLE_FIELDS, _nan_summary
    summaries = {}
    for field in ANGLE_FIELDS:
        summaries[f"{field}_mean"] = _nan_summary(kinematics.values[field][start:end+1], "mean")
        summaries[f"{field}_rom"] = _nan_summary(kinematics.values[field][start:end+1], "rom")
        velocity_field = field.replace("_deg", "_velocity_deg_s")
        summaries[f"{velocity_field}_mean"] = _nan_summary(kinematics.values[velocity_field][start:end+1], "mean")
        summaries[f"{velocity_field}_peak_abs"] = _nan_summary(kinematics.values[velocity_field][start:end+1], "peak_abs")
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
    from .insights import quality_index
    quality.update(quality_index(quality, raw, confidence, landmarks, release_frame, context.throwing_side, config))
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
                       "Projected upper-body angles")
    plot_wrist_trajectory(output / "wrist_trajectory.png", normalized_values["wrist_path_arm_lengths"],
                          "Shoulder-relative wrist path")
    (output / "summary.md").write_text(markdown_summary(json_ready(results)))
    if make_annotated_video:
        progress("annotating_video", 0.88, "Rendering skeleton overlay video")
        annotate_video(
            video.path, output / "annotated.mp4", filtered, confidence, landmarks,
            float(config["confidence_threshold"]), manual_mask,
        )
    engine_source_hash = canonical_hash({p.name: file_sha256(p) for p in Path(__file__).parent.glob("*.py")})
    manifest = {
        "engine_source_sha256": engine_source_hash,
        "schema_version": 1,
        "analysis_id": canonical_hash({
            "engine_source_sha256": engine_source_hash,
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
        "pose_cache_key": pose_key,
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
    for directory in [test_dir, *reference_dirs]:
        if (Path(directory) / "needs_reanalysis.json").exists():
            raise ValueError("Tracking or event corrections changed. Reanalyze every selected throw before comparison.")
    manifests = [_load_json(Path(d) / "manifest.json", {}) for d in [test_dir, *reference_dirs]]
    signatures = [(m.get("pose_backend"), m.get("pose_model"), m.get("pose_model_version"), m.get("pose_model_sha256"), m.get("engine_source_sha256"), canonical_hash(m.get("analysis_configuration", {}))) for m in manifests]
    if any(signature != signatures[0] for signature in signatures[1:]):
        raise ValueError("These throws use different pose models or analysis settings. Reanalyze them with matching settings before comparison.")
    test_payload = _load_json(Path(test_dir) / "normalized.json", None)
    if test_payload is None:
        raise FileNotFoundError(f"Missing normalized.json in {test_dir}")
    references = [_load_json(Path(path) / "normalized.json", None) for path in reference_dirs]
    if any(value is None for value in references):
        raise FileNotFoundError("Every reference directory must contain normalized.json")
    if test_payload["trial_id"] in [item["trial_id"] for item in references]:
        raise ValueError("Choose a different throw for comparison; a trial cannot be its own reference.")
    for item in references:
        if len(item["tau"]) != len(test_payload["tau"]) or not np.allclose(item["tau"], test_payload["tau"]):
            raise ValueError("These analyses use different normalized time grids. Reanalyze with matching settings.")
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
    tau = np.asarray(test_payload["tau"], float)
    result = {
        "schema_version": 1,
        "test_trial_id": test_payload["trial_id"],
        "reference_trial_ids": [item["trial_id"] for item in references],
        "camera_view": test_payload["camera_view"],
        "label": label,
        "source_hashes": {str(Path(path).resolve()): file_sha256(Path(path)/"normalized.json") for path in [test_dir, *reference_dirs]},
        "test_event_timing": test_payload["event_timing"],
        "reference_event_timing": reference_event_timing,
        "raw_metrics": metrics,
        "similarity": score,
        "curves": {
            "tau": tau,
            "test": test_values,
            "reference_mean": {name: values["mean"] for name, values in reference_set.items()},
            "reference_sd": {name: values["sd"] for name, values in reference_set.items()},
        },
        "claim_scope": "reference_similarity_not_performance_quality",
        "timing_method": "time_preserving_no_dynamic_time_warping",
    }
    write_json(output / "comparison.json", result)
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
    comparison_dirs: list[str | Path] | None = None,
    minimum_trials: int = 8,
) -> dict[str, Any]:
    """Analyze selected movement features against outcome within one athlete."""
    comparison_by_trial: dict[str, dict[str, Any]] = {}
    for directory in comparison_dirs or []:
        comparison = _load_json(Path(directory) / "comparison.json", None)
        if comparison is not None:
            comparison_by_trial[comparison["test_trial_id"]] = comparison
    rows: list[dict[str, Any]] = []
    normalized_by_trial: dict[str, dict[str, Any]] = {}
    athlete_ids: set[str] = set()
    for directory in analysis_dirs:
        result = _load_json(Path(directory) / "results.json", None)
        if result is None:
            continue
        athlete_ids.add(result["athlete_id"])
        outcome = outcome_records.get(result["trial_id"], {})
        if outcome and "spatial_error" not in outcome:
            def point(value: dict[str, Any] | None) -> BoardPoint | None:
                return None if value is None else BoardPoint(**value)
            parsed = TrialOutcome(
                intended_target=outcome.get("intended_target", "Hole center"),
                score_category=int(outcome.get("score_category", 0)),
                throw_type=outcome.get("throw_type", "Standard"),
                notes=outcome.get("notes", ""),
                intended_point=point(outcome.get("intended_point")),
                first_contact_point=point(outcome.get("first_contact_point")),
                final_resting_point=point(outcome.get("final_resting_point")),
            )
            outcome = outcome_summary(parsed)
        row = {"trial_id": result["trial_id"], "score_category": outcome.get("score_category")}
        row.update(result.get("summaries", {}))
        comparison = comparison_by_trial.get(result["trial_id"], {})
        row["reference_similarity_score"] = comparison.get("similarity", {}).get("overall")
        row["wrist_reference_deviation_arm_lengths"] = comparison.get("raw_metrics", {}).get(
            "wrist_path_rmse_arm_lengths"
        )
        spatial = outcome.get("spatial_error") or {}
        row["radial_error_inches"] = spatial.get("radial_error_inches")
        rows.append(row)
        normalized = _load_json(Path(directory) / "normalized.json", None)
        if normalized is not None:
            normalized_by_trial[result["trial_id"]] = normalized
    views = {v.get("camera_view") for v in normalized_by_trial.values() if v.get("camera_view")}
    if len(views) > 1:
        raise ValueError("Repeated-trial analysis requires matching camera views. Select one view at a time.")
    if len(athlete_ids) > 1:
        raise ValueError("Initial relationship analysis is within-person; provide one athlete at a time")
    outcomes = [row.get("radial_error_inches") for row in rows]
    if not any(value is not None for value in outcomes):
        outcomes = [row.get("score_category") for row in rows]
        outcome_name = "score_category"
    else:
        outcome_name = "radial_error_inches"
    wrist_paths = {
        trial_id: np.asarray(value.get("values", {}).get("wrist_path_arm_lengths"), float)
        for trial_id, value in normalized_by_trial.items()
        if value.get("values", {}).get("wrist_path_arm_lengths") is not None
    }
    if wrist_paths:
        shapes = {path.shape for path in wrist_paths.values()}
        if len(shapes) == 1:
            with np.errstate(invalid="ignore"):
                athlete_mean_wrist = np.nanmean(np.stack(list(wrist_paths.values())), axis=0)
            for row in rows:
                path = wrist_paths.get(row["trial_id"])
                row["wrist_path_deviation_from_athlete_mean_arm_lengths"] = (
                    path_rmse(path, athlete_mean_wrist) if path is not None else None
                )
    feature_names = (
        "elbow_angle_deg_at_release",
        "elbow_angle_deg_rom",
        "trunk_inclination_deg_at_release",
        "movement_duration_seconds",
        "release_timing_cycle",
        "reference_similarity_score",
        "wrist_reference_deviation_arm_lengths",
        "wrist_path_deviation_from_athlete_mean_arm_lengths",
    )
    relationships = {
        name: relationship([row.get(name) for row in rows], outcomes, minimum_trials)
        for name in feature_names
    }
    groups = {
        name: grouped_summary([row.get(name) for row in rows], [row.get("score_category") for row in rows])
        for name in feature_names
    }
    consistency: dict[str, dict[str, Any]] = {}
    units = {
        "elbow_angle_deg_at_release": "degrees",
        "elbow_angle_deg_rom": "degrees",
        "trunk_inclination_deg_at_release": "degrees",
        "movement_duration_seconds": "seconds",
        "release_timing_cycle": "movement cycle fraction",
        "reference_similarity_score": "0-100 reference similarity index",
        "wrist_reference_deviation_arm_lengths": "arm lengths",
        "wrist_path_deviation_from_athlete_mean_arm_lengths": "arm lengths",
    }
    for name in feature_names:
        values = np.asarray([row.get(name) for row in rows if row.get(name) is not None], float)
        values = values[np.isfinite(values)]
        consistency[name] = {
            "n": int(values.size),
            "mean": float(np.mean(values)) if values.size else None,
            "standard_deviation": float(np.std(values, ddof=1)) if values.size > 1 else None,
            "median": float(np.median(values)) if values.size else None,
            "range": float(np.ptp(values)) if values.size else None,
            "units": units[name],
        }
    result = {
        "schema_version": 1,
        "athlete_id": next(iter(athlete_ids), None),
        "trial_count": len(rows),
        "outcome_variable": outcome_name,
        "relationships": relationships,
        "grouped_by_score": groups,
        "within_athlete_consistency": consistency,
        "data_rows": rows,
        "claim_scope": "within_athlete_observational_association_not_causation",
    }
    write_json(output_path, result)
    return result
