"""End-to-end reproducible analysis, comparison, and repeated-trial workflows."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable
import json
import math

import numpy as np

from . import REQUIRED_LANDMARKS, __version__
from .bag import (
    ANALYSIS_COORDINATE_SYSTEM,
    BAG_COORDINATE_SYSTEM,
    BagCorrectionSet,
    BagSeed,
    BagTrack,
    SpatialCalibration,
    detect_bag_wrist_release,
    effective_bag_track,
    estimate_projectile_release_kinematics,
    track_bag_from_seed,
    validate_bag_track_for_video,
    write_bag_csv,
)
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
from .kinematics import calculate_kinematics, movement_phase_summaries
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


def _summary_units(name: str) -> str:
    if name.endswith("_px_s2"):
        return "pixels/s^2"
    if name.endswith("_m_s2"):
        return "m/s^2"
    if name.endswith("_arm_lengths_s2"):
        return "arm lengths/s^2"
    if name.endswith("_px_s"):
        return "pixels/s"
    if name.endswith("_m_s"):
        return "m/s"
    if name.endswith("_arm_lengths_s"):
        return "arm lengths/s"
    if name.endswith("_deg_s"):
        return "degrees/s"
    if name.endswith("_deg") or "_deg_" in name:
        return "degrees"
    if name.endswith("_arm_lengths"):
        return "arm lengths"
    if name.endswith("_seconds"):
        return "seconds"
    if name.endswith("_cycle"):
        return "movement cycle fraction"
    if name.endswith("_coverage") or name.endswith("_ratio"):
        return "dimensionless"
    if name.endswith("_sample_count"):
        return "samples"
    if "curvature_rad_per_arm_length" in name:
        return "radians/arm length"
    return "dimensionless"


def _metrics_metadata(summaries: dict[str, Any], camera_view: str) -> dict[str, Any]:
    applicability = "primary_stage1_side_view" if camera_view == "side" else "exploratory_non_side_projection"
    result = {}
    for name in summaries:
        claim = "descriptive_projected_2d_kinematics"
        if "shoulder_bag_radius" in name:
            claim = "projected_radial_distance_proxy_not_moment_arm_or_torque"
        elif "acceleration" in name:
            claim = "exploratory_noise_sensitive_projected_measurement"
        elif "similarity" in name:
            claim = "reference_similarity_not_performance_quality"
        result[name] = {
            "units": _summary_units(name),
            "view_applicability": applicability,
            "claim_scope": claim,
        }
    return result


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
    app_version: str = "0.3.0",
    progress: Progress = _no_progress,
    bag_track_input: str | Path | None = None,
    bag_seed_path: str | Path | None = None,
    bag_corrections_path: str | Path | None = None,
    calibration_path: str | Path | None = None,
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

    if bag_track_input is not None and bag_seed_path is not None:
        raise ValueError("Provide either an existing bag track or a manual bag seed, not both")
    bag_track: BagTrack | None = None
    bag_derived: dict[str, Any] | None = None
    bag_filtered: np.ndarray | None = None
    bag_corrections: BagCorrectionSet | None = None
    bag_release_candidate = None
    bag_warnings: list[str] = []
    bag_raw_path = output / "bag_raw.json"
    bag_cache_path = output / "bag_cache.json"
    bag_key: str | None = None
    if bag_track_input is not None:
        bag_track = BagTrack.load(bag_track_input)
        bag_key = canonical_hash({
            "source_video_sha256": video.sha256,
            "import_sha256": file_sha256(bag_track_input),
            "method": "canonical_bag_track_import",
        })
        validate_bag_track_for_video(bag_track, video.path)
        bag_track.save(bag_raw_path)
        write_json(bag_cache_path, {"bag_key": bag_key, "created_at": utc_now()})
    elif bag_seed_path is not None:
        seed = BagSeed.load(bag_seed_path)
        tracking_config = config["bag_tracking"]
        bag_key = canonical_hash({
            "source_video_sha256": video.sha256,
            "seed": asdict(seed),
            "tracker_configuration": tracking_config,
            "opencv_version": _version("opencv-contrib-python"),
        })
        bag_cache = _load_json(bag_cache_path, {})
        if bag_raw_path.exists() and bag_cache.get("bag_key") == bag_key:
            bag_track = BagTrack.load(bag_raw_path)
            validate_bag_track_for_video(bag_track, video.path)
        else:
            progress("tracking_bag", 0.48, "Tracking the bag forward from the reviewed seed rectangle")
            bag_track = track_bag_from_seed(
                video.path,
                seed,
                requested_method=str(tracking_config["method"]),
                template_quality_threshold=float(tracking_config["template_quality_threshold"]),
                search_scale=float(tracking_config["template_search_scale"]),
            )
            bag_track.save(bag_raw_path)
            write_json(bag_cache_path, {"bag_key": bag_key, "created_at": utc_now()})
    elif bag_raw_path.exists():
        # Reanalysis retains an already reviewed raw bag track even if the caller
        # does not repeat its seed/import arguments.
        bag_track = BagTrack.load(bag_raw_path)
        validate_bag_track_for_video(bag_track, video.path)
        bag_key = _load_json(bag_cache_path, {}).get("bag_key")

    if bag_track is not None:
        bag_corrections = BagCorrectionSet.load(bag_corrections_path or (output / "bag_corrections.json"))
        bag_corrections.save(output / "bag_corrections.json")
        bag_derived = effective_bag_track(
            bag_track,
            bag_corrections,
            float(config["bag_tracking"]["confidence_threshold"]),
            int(config["max_interpolation_gap_frames"]),
        )
        bag_gap_handled = bag_derived["effective"]
        if filter_config["enabled"] and filter_config["type"] != "none":
            bag_filtered, _, current_warnings = lowpass_zero_phase(
                bag_gap_handled,
                video.fps,
                float(filter_config["cutoff_hz"]),
                int(filter_config["order"]),
            )
            bag_warnings.extend(f"Bag track: {item}" for item in current_warnings)
        else:
            bag_filtered = np.array(bag_gap_handled, copy=True)
        if bag_track.fallback_reason:
            bag_warnings.append(bag_track.fallback_reason)
        if bag_track.failure_frames:
            bag_warnings.append(
                f"Bag tracker did not return a reviewed automatic centroid in {len(bag_track.failure_frames)} frame(s); inspect and correct the track."
            )

    progress("calculating_kinematics", 0.62, "Calculating projected 2D upper-body measures")
    kinematics = calculate_kinematics(
        filtered,
        landmarks,
        video.fps,
        context.throwing_side,
        context.target_direction,
        float(config["minimum_velocity_coverage"]),
        bag_coords=bag_filtered,
    )
    if bag_filtered is not None:
        lookup = {name: index for index, name in enumerate(landmarks)}
        wrist_pixels = filtered[:, lookup[f"{context.throwing_side}_wrist"], :]
        release_config = config["bag_release"]
        bag_release_candidate = detect_bag_wrist_release(
            wrist_pixels,
            bag_filtered,
            kinematics.arm_length_pixels,
            video.fps,
            float(release_config["minimum_divergence_arm_lengths"]),
            float(release_config["persistence_seconds"]),
        )
    event_file = Path(events_path) if events_path else output / "events.json"
    progress("detecting_events", 0.68, "Detecting frame-limited movement event candidates")
    events = detect_events(
        kinematics.values["wrist_path_arm_lengths"], video.fps, bag_release_candidate
    )
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
        "release_precision_note": "Visible release is frame-limited; neither bag/wrist divergence nor manual review establishes sub-frame timing.",
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
    summaries.update(movement_phase_summaries(
        kinematics.values,
        start,
        end,
        events["forward_swing"].effective_frame,
        release_frame,
    ))

    calibration = SpatialCalibration.load(calibration_path)
    projectile: dict[str, Any] | None = None
    bag_result: dict[str, Any] | None = None
    if bag_track is not None and bag_derived is not None and bag_filtered is not None:
        projectile_config = config["projectile"]
        fit_frame_count = max(
            int(projectile_config["minimum_velocity_points"]),
            int(math.ceil(float(projectile_config["release_fit_window_seconds"]) * video.fps)) + 1,
        )
        required_review_through = (
            None if release_frame is None
            else min(sequence.frame_count - 1, release_frame + fit_frame_count - 1)
        )
        bag_review_covers_fit = bag_corrections.covers(required_review_through)
        if bag_review_covers_fit:
            projectile = estimate_projectile_release_kinematics(
                bag_filtered,
                release_frame,
                video.fps,
                kinematics.arm_length_pixels,
                context.target_direction,
                calibration=calibration,
                window_seconds=float(projectile_config["release_fit_window_seconds"]),
                minimum_points=int(projectile_config["minimum_velocity_points"]),
                acceleration_minimum_fps=float(projectile_config["acceleration_minimum_fps"]),
                acceleration_minimum_points=int(projectile_config["acceleration_minimum_points"]),
                acceleration_maximum_fit_rmse_arm_lengths=float(
                    projectile_config["acceleration_maximum_fit_rmse_arm_lengths"]
                ),
            )
        else:
            projectile = {
                "status": "suppressed_unreviewed_track",
                "coordinate_system": ANALYSIS_COORDINATE_SYSTEM,
                "frame_interval_seconds": 1.0 / video.fps,
                "release_frame": release_frame,
                "required_review_through_frame": required_review_through,
                "reviewed_through_frame": bag_corrections.reviewed_through_frame,
                "velocity": None,
                "acceleration": {
                    "status": "suppressed",
                    "reason": "The complete release-fit interval has not been marked as reviewed.",
                    "interpretation": "exploratory_noise_sensitive_projected_measurement",
                },
                "physical_units": {
                    "status": "not_available_while_track_is_unreviewed",
                    "calibration": None if calibration is None else asdict(calibration),
                },
                "uncertainty_note": (
                    "Automatic bag coverage is not evidence of correct object identity. "
                    "Review every frame used by the release fit before interpreting launch quantities."
                ),
            }
            bag_warnings.append(
                "Projected bag launch is suppressed because the automatic track has not been reviewed through "
                f"frame {required_review_through}."
            )
        projectile["release_event_method"] = events["release"].automatic_method
        projectile["release_event_was_manually_reviewed"] = events["release"].manual_frame is not None
        velocity = projectile.get("velocity") or {}
        velocity_names = {
            "forward_px_s": "bag_release_forward_velocity_px_s",
            "vertical_px_s": "bag_release_vertical_velocity_px_s",
            "speed_px_s": "bag_release_speed_px_s",
            "angle_deg": "bag_release_angle_deg",
            "forward_arm_lengths_s": "bag_release_forward_velocity_arm_lengths_s",
            "vertical_arm_lengths_s": "bag_release_vertical_velocity_arm_lengths_s",
            "speed_arm_lengths_s": "bag_release_speed_arm_lengths_s",
        }
        for source, destination in velocity_names.items():
            summaries[destination] = velocity.get(source)
        physical_velocity = projectile.get("physical_units", {}).get("velocity", {})
        for source, destination in (
            ("forward_m_s", "bag_release_forward_velocity_m_s"),
            ("vertical_m_s", "bag_release_vertical_velocity_m_s"),
            ("speed_m_s", "bag_release_speed_m_s"),
        ):
            summaries[destination] = physical_velocity.get(source)
        acceleration = projectile.get("acceleration", {})
        for source, destination in (
            ("forward_px_s2", "bag_release_forward_acceleration_px_s2"),
            ("vertical_px_s2", "bag_release_vertical_acceleration_px_s2"),
            ("magnitude_px_s2", "bag_release_acceleration_magnitude_px_s2"),
            ("forward_arm_lengths_s2", "bag_release_forward_acceleration_arm_lengths_s2"),
            ("vertical_arm_lengths_s2", "bag_release_vertical_acceleration_arm_lengths_s2"),
            ("magnitude_arm_lengths_s2", "bag_release_acceleration_magnitude_arm_lengths_s2"),
            ("forward_m_s2", "bag_release_forward_acceleration_m_s2"),
            ("vertical_m_s2", "bag_release_vertical_acceleration_m_s2"),
            ("magnitude_m_s2", "bag_release_acceleration_magnitude_m_s2"),
        ):
            summaries[destination] = acceleration.get(source)
        if bag_review_covers_fit and release_frame is not None and 0 <= release_frame < sequence.frame_count:
            bag_position = kinematics.values["bag_path_arm_lengths"][release_frame]
            summaries["bag_release_position_forward_arm_lengths"] = (
                float(bag_position[0]) if np.isfinite(bag_position[0]) else None
            )
            summaries["bag_release_position_vertical_arm_lengths"] = (
                float(bag_position[1]) if np.isfinite(bag_position[1]) else None
            )
        automatic_present = np.isfinite(bag_derived["raw"]).all(axis=-1)
        effective_present = np.isfinite(bag_derived["effective"]).all(axis=-1)
        after_seed = slice(bag_track.seed.frame_index, None)
        automatic_quality = bag_derived["confidence"][automatic_present]
        candidate_payload = None
        if bag_release_candidate is not None and bag_release_candidate.automatic_frame is not None:
            candidate_payload = asdict(bag_release_candidate)
        else:
            bag_warnings.append(
                "Bag/wrist persistent divergence did not produce a release candidate; the wrist-speed candidate remains active until manual review."
            )
        for frame, sample in enumerate(bag_derived["payload"]["samples"]):
            sample["filtered_centroid"] = (
                None if not np.isfinite(bag_filtered[frame]).all()
                else {"x": bag_filtered[frame, 0], "y": bag_filtered[frame, 1]}
            )
        bag_result = {
            "coordinate_system": BAG_COORDINATE_SYSTEM,
            "analysis_coordinate_system": ANALYSIS_COORDINATE_SYSTEM,
            "units": "pixels_and_arm_lengths; physical_units_only_with_explicit_athlete_plane_calibration",
            "view_applicability": (
                "primary_stage1_side_view" if context.camera_view == "side"
                else "exploratory_non_side_projection"
            ),
            "automatic_tracking_coverage_percent": 100.0 * float(np.mean(automatic_present[after_seed])),
            "effective_tracking_coverage_percent": 100.0 * float(np.mean(effective_present[after_seed])),
            "median_automatic_quality": (
                float(np.median(automatic_quality)) if automatic_quality.size else None
            ),
            "manual_correction_count": int(np.count_nonzero(bag_derived["manual_mask"])),
            "interpolated_sample_count": int(np.count_nonzero(bag_derived["interpolated_mask"])),
            "review": {
                "reviewed_through_frame": bag_corrections.reviewed_through_frame,
                "required_through_frame_for_launch": required_review_through,
                "covers_launch_fit": bag_review_covers_fit,
                "reviewed_at": bag_corrections.reviewed_at,
                "note": bag_corrections.review_note,
            },
            "tracker": bag_derived["payload"]["tracker"],
            "release_candidate": candidate_payload,
            "launch": projectile,
            "quality_note": bag_track.quality_note,
        }

    quality = quality_summary(
        raw, confidence, effective, manual_mask, interpolated_mask, landmarks,
        video.fps, video.width, video.height, context.camera_view,
        float(config["confidence_threshold"]), context.throwing_side,
    )
    from .insights import quality_index
    quality.update(quality_index(quality, raw, confidence, landmarks, release_frame, context.throwing_side, config))
    warnings = sorted(set(filter_warnings + kinematics.warnings + bag_warnings))
    results = {
        "schema_version": 1,
        "trial_id": context.trial_id,
        "athlete_id": context.athlete_id,
        "camera_view": context.camera_view,
        "throwing_side": context.throwing_side,
        "target_direction": context.target_direction,
        "summaries": summaries,
        "metrics_metadata": _metrics_metadata(summaries, context.camera_view),
        "quality": quality,
        "bag": bag_result,
        "events": event_payload["events"],
        "warnings": warnings,
        "coordinate_system": {
            "raw_video": "x right, y down, pixels",
            "analysis": "x toward target after reflection, y up",
            "body_normalization": "throwing-shoulder-relative, divided by median projected upper-arm plus forearm length",
        },
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
        "coordinate_system": ANALYSIS_COORDINATE_SYSTEM,
        "spatial_units": "arm_lengths_unless_field_suffix_states_pixels",
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
    if bag_derived is not None:
        write_json(output / "bag_track.json", bag_derived["payload"])
        write_bag_csv(output / "bag_keypoints.csv", bag_derived, video.fps)
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
            bag_points=bag_filtered,
            bag_provenance=None if bag_derived is None else bag_derived["provenance"],
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
            "bag_track": bag_key,
            "bag_corrections": None if bag_corrections is None else canonical_hash(asdict(bag_corrections)),
            "calibration": None if calibration is None else canonical_hash(asdict(calibration)),
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
        "bag_tracking": None if bag_track is None else {
            "raw_track_sha256": file_sha256(bag_raw_path),
            "cache_key": bag_key,
            "requested_method": bag_track.requested_method,
            "effective_method": bag_track.effective_method,
            "status": bag_track.status,
            "manual_correction_hash": canonical_hash(asdict(bag_corrections)) if bag_corrections is not None else None,
            "coordinate_system": BAG_COORDINATE_SYSTEM,
        },
        "spatial_calibration": None if calibration is None else {
            **asdict(calibration),
            "physical_units_permitted": calibration.permits_physical_units,
        },
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
    finite_radial = [value for value in outcomes if value is not None and np.isfinite(value)]
    if len(finite_radial) < minimum_trials:
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
        "elbow_extension_deficit_deg_at_release",
        "elbow_angle_deg_rom",
        "trunk_inclination_deg_at_release",
        "movement_duration_seconds",
        "release_timing_cycle",
        "shoulder_translation_net_arm_lengths",
        "shoulder_peak_speed_arm_lengths_s",
        "wrist_relative_peak_speed_arm_lengths_s",
        "shoulder_wrist_radius_at_release_arm_lengths",
        "shoulder_wrist_radius_forward_swing_sd_arm_lengths",
        "wrist_forward_swing_path_straightness_ratio",
        "wrist_forward_swing_path_rms_fitted_line_deviation_arm_lengths",
        "bag_release_speed_arm_lengths_s",
        "bag_release_angle_deg",
        "bag_release_position_forward_arm_lengths",
        "bag_release_position_vertical_arm_lengths",
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
        "elbow_extension_deficit_deg_at_release": "degrees",
        "elbow_angle_deg_rom": "degrees",
        "trunk_inclination_deg_at_release": "degrees",
        "movement_duration_seconds": "seconds",
        "release_timing_cycle": "movement cycle fraction",
        "shoulder_translation_net_arm_lengths": "arm lengths",
        "shoulder_peak_speed_arm_lengths_s": "arm lengths/second",
        "wrist_relative_peak_speed_arm_lengths_s": "arm lengths/second",
        "shoulder_wrist_radius_at_release_arm_lengths": "arm lengths",
        "shoulder_wrist_radius_forward_swing_sd_arm_lengths": "arm lengths",
        "wrist_forward_swing_path_straightness_ratio": "dimensionless",
        "wrist_forward_swing_path_rms_fitted_line_deviation_arm_lengths": "arm lengths",
        "bag_release_speed_arm_lengths_s": "arm lengths/second",
        "bag_release_angle_deg": "degrees",
        "bag_release_position_forward_arm_lengths": "arm lengths",
        "bag_release_position_vertical_arm_lengths": "arm lengths",
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
