"""Structured command-line boundary shared by the Swift app and researchers."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any
import argparse
import importlib.util
import json
import sys

import numpy as np

from . import __version__
from .bag import BagSeed, BagTrack, bag_tracking_qa, track_bag_from_seed
from .models import BoardPoint, TrialContext, TrialOutcome
from .outcomes import outcome_summary
from .pipeline import analyze_relationships, analyze_trial, compare_trial
from .serialization import json_ready, write_json
from .video import read_video_metadata


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(json_ready(payload), separators=(",", ":")), flush=True)


def progress(stage: str, fraction: float, message: str) -> None:
    emit({"type": "progress", "stage": stage, "fraction": fraction, "message": message})


def load_json(path: str | None, default: Any = None) -> Any:
    return default if not path else json.loads(Path(path).read_text())


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="cornhole-biomech",
        description="Local, transparent projected 2D cornhole biomechanics analysis.",
    )
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="command", required=True)

    probe = commands.add_parser("probe", help="Report runtime/backend availability as JSON")
    probe.set_defaults(handler=handle_probe)

    metadata = commands.add_parser("video-info", help="Read video metadata without modification")
    metadata.add_argument("video")
    metadata.set_defaults(handler=handle_video_info)

    prepare = commands.add_parser('prepare-video', help='Create a trim/crop/rotation copy; preserve original')
    prepare.add_argument('video')
    prepare.add_argument('--output', required=True)
    prepare.add_argument('--start-frame', type=int, default=0)
    prepare.add_argument('--end-frame', type=int)
    prepare.add_argument('--crop', nargs=4, type=int)
    prepare.add_argument('--rotation', type=int, choices=(0, 90, 180, 270), default=0)
    prepare.set_defaults(handler=handle_prepare_video)

    analyze = commands.add_parser("analyze", help="Analyze one local video trial")
    analyze.add_argument("video")
    analyze.add_argument("--output", required=True)
    analyze.add_argument("--trial-id", required=True)
    analyze.add_argument("--athlete-id", required=True)
    analyze.add_argument("--view", choices=("side", "front", "other"), required=True)
    analyze.add_argument("--throwing-side", choices=("left", "right"), required=True)
    analyze.add_argument("--target-direction", choices=("left_to_right", "right_to_left"), required=True)
    analyze.add_argument("--source-url")
    analyze.add_argument("--source-attribution")
    analyze.add_argument("--backend", choices=("sports2d", "rtmpose", "mediapipe"), default="sports2d")
    analyze.add_argument("--device", choices=("cpu", "mps"), default="cpu")
    analyze.add_argument("--pose-input", help="Import a canonical pose_raw.json instead of inference")
    analyze.add_argument("--corrections")
    analyze.add_argument("--events")
    analyze.add_argument("--bag-track-input", help="Import immutable canonical bag_raw.json")
    analyze.add_argument("--bag-seed", help="Track from a reviewed bag seed rectangle JSON")
    analyze.add_argument("--bag-corrections", help="Apply separate reviewed bag centroid corrections JSON")
    analyze.add_argument("--calibration", help="Optional validated athlete-plane spatial calibration JSON")
    analyze.add_argument("--config")
    analyze.add_argument("--app-version", default=__version__)
    analyze.add_argument("--force-pose", action="store_true")
    analyze.add_argument("--no-annotated-video", action="store_true")
    analyze.set_defaults(handler=handle_analyze)

    bag_track = commands.add_parser("bag-track", help="Track a bag forward from a reviewed seed rectangle")
    bag_track.add_argument("video")
    bag_track.add_argument("--seed", required=True)
    bag_track.add_argument("--output", required=True)
    bag_track.add_argument("--method", choices=("auto", "csrt", "template_matching", "color_motion"), default="auto")
    bag_track.add_argument("--quality-threshold", type=float, default=0.25)
    bag_track.add_argument("--search-scale", type=float, default=2.5)
    bag_track.set_defaults(handler=handle_bag_track)

    bag_qa = commands.add_parser("bag-qa", help="Compare an automatic bag track with reviewed frame labels")
    bag_qa.add_argument("--track", required=True)
    bag_qa.add_argument("--labels", required=True)
    bag_qa.add_argument("--output")
    bag_qa.add_argument("--arm-length-pixels", type=float)
    bag_qa.add_argument("--automatic-release-frame", type=int)
    bag_qa.add_argument("--manual-release-frame", type=int)
    bag_qa.add_argument("--fps", type=float)
    bag_qa.set_defaults(handler=handle_bag_qa)

    compare = commands.add_parser("compare", help="Compare one analyzed trial to a reference set")
    compare.add_argument("--test", required=True)
    compare.add_argument("--reference", action="append", required=True)
    compare.add_argument("--output", required=True)
    compare.add_argument("--config")
    compare.set_defaults(handler=handle_compare)

    batch = commands.add_parser("batch", help="Analyze trials from a JSON specification")
    batch.add_argument("spec")
    batch.set_defaults(handler=handle_batch)

    relationships = commands.add_parser(
        "relationships", help="Estimate within-athlete movement/outcome relationships"
    )
    relationships.add_argument("--analysis", action="append", required=True)
    relationships.add_argument("--comparison", action="append", default=[])
    relationships.add_argument("--outcomes", required=True)
    relationships.add_argument("--output", required=True)
    relationships.add_argument("--minimum-trials", type=int, default=8)
    relationships.set_defaults(handler=handle_relationships)

    outcome = commands.add_parser("outcome", help="Validate and summarize one outcome JSON file")
    outcome.add_argument("input")
    outcome.set_defaults(handler=handle_outcome)
    insights = commands.add_parser("insights", help="Refresh trial insights and a self-contained local report")
    insights.add_argument("--project", required=True)
    insights.add_argument("--trial-id", required=True)
    insights.set_defaults(handler=handle_insights)
    dashboard = commands.add_parser("athlete-dashboard", help="Refresh one athlete's coaching dashboard")
    dashboard.add_argument("--project", required=True)
    dashboard.add_argument("--athlete-id", required=True)
    dashboard.set_defaults(handler=handle_athlete_dashboard)

    frames = commands.add_parser("annotation-frames", help="Export blinded frames for manual tracking validation")
    frames.add_argument("video")
    frames.add_argument("--output", required=True)
    frames.add_argument("--analysis", help="Analysis folder; its automatic events seed the frame choice")
    frames.add_argument("--count", type=int, default=10)
    frames.add_argument("--seed", type=int, default=20260922)
    frames.set_defaults(handler=handle_annotation_frames)

    validate = commands.add_parser("validate-tracking", help="Compare automatic tracking with manual annotation")
    validate.add_argument("--annotation", required=True)
    validate.add_argument("--analysis", required=True)
    validate.add_argument("--throwing-side", choices=("left", "right"), required=True)
    validate.add_argument("--second-annotation", help="Second rater's file for inter-rater agreement")
    validate.add_argument("--output")
    validate.set_defaults(handler=handle_validate_tracking)

    bag_frames = commands.add_parser("bag-annotation-frames",
                                     help="Export blinded, phase-stratified frames for bag-tracking validation")
    bag_frames.add_argument("--library", required=True, help="Athlete library with analysed throws")
    bag_frames.add_argument("--output", required=True)
    bag_frames.add_argument("--per-phase", type=int, default=2)
    bag_frames.add_argument("--seed", type=int, default=20260923)
    bag_frames.set_defaults(handler=handle_bag_annotation_frames)

    bag_bench = commands.add_parser("bag-benchmark", help="Score every bag tracker output against manual bag marks")
    bag_bench.add_argument("--frames", required=True, help="Folder written by bag-annotation-frames, with raters' "
                           "annotation_*.json saved into each clip folder")
    bag_bench.add_argument("--rater", help="Only use annotation files from this rater")
    bag_bench.add_argument("--output")
    bag_bench.set_defaults(handler=handle_bag_benchmark)

    pair = commands.add_parser("compare-throws", help="Explain how throw B differs from throw A for one athlete")
    pair.add_argument("--project", required=True)
    pair.add_argument("--a", required=True, help="Trial ID of the first throw")
    pair.add_argument("--b", required=True, help="Trial ID of the second throw")
    pair.set_defaults(handler=handle_compare_throws)

    corners = commands.add_parser("set-board-corners",
        help="Store four clicked deck corners for a trial's analysis output folder (and others)")
    corners.add_argument("--trial-dir", required=True,
        help="The trial's analysis output folder (has manifest.json and plate.jpg)")
    corners.add_argument("--corners", required=True,
        help="Four deck corners, in any order, as x1,y1,x2,y2,x3,y3,x4,y4 pixels of the trial's plate.jpg")
    corners.add_argument("--apply-to", nargs="*", default=[],
        help="Other trials' analysis output folders shot from the same camera position")
    corners.set_defaults(handler=handle_set_board_corners)

    session = commands.add_parser("calibrate-session",
        help="Pool a recording session's per-throw board field-of-view calibrations into one "
             "camera.json, written into every listed throw's analysis folder")
    session.add_argument("--analyses", nargs="+", required=True,
        help="Every throw's analysis output folder shot from the same camera setup (has manifest.json "
             "and results.json)")
    session.add_argument("--session-key", help="Label for this session; defaults to a hash of the folder paths")
    session.set_defaults(handler=handle_calibrate_session)
    return root


def handle_compare_throws(args: argparse.Namespace) -> dict[str, Any]:
    from .performance import compare_throws
    root = Path(args.project).resolve()
    project = load_json(str(root / "project.json"))
    trials = {t["id"]: t for t in project["trials"]}
    if args.a not in trials or args.b not in trials:
        raise ValueError("Both throws must belong to this library.")
    if trials[args.a]["athleteID"] != trials[args.b]["athleteID"]:
        raise ValueError("Throw comparison is within one athlete. Choose two throws from the same athlete.")
    relationships = root / (trials[args.b].get("analysisRelativePath") or "") / "relationships.json"
    if not relationships.exists():
        raise ValueError("Open Results for the second throw first so its comparable throws are summarized.")
    rows = load_json(str(relationships))["data_rows"]
    by_id = {r["trial_id"]: r for r in rows}
    if args.a not in by_id or args.b not in by_id:
        raise ValueError("One of these throws is not comparable (different session setup, or tracking below 80 %).")
    labels = {t["id"]: t.get("name") or t.get("originalFilename") or t["id"] for t in project["trials"]}
    return compare_throws(by_id[args.a], by_id[args.b], rows, labels)


def _automatic_events(analysis: Path) -> dict[str, int | None]:
    """Automatic (not manually overridden) event candidates of an analysis folder."""
    events = load_json(str(analysis / "results.json"), {}).get("events", {})
    return {name: value.get("automatic_frame") for name, value in events.items()}


def handle_annotation_frames(args: argparse.Namespace) -> dict[str, Any]:
    from .validation import export_annotation_frames, select_validation_frames
    events = _automatic_events(Path(args.analysis)) if args.analysis else None
    frame_count = read_video_metadata(args.video).frame_count
    chosen = select_validation_frames(frame_count, events, args.count, args.seed)
    return export_annotation_frames(args.video, chosen, args.output)


def handle_bag_annotation_frames(args: argparse.Namespace) -> dict[str, Any]:
    from .bag_validation import bag_phase_frames, select_bag_frames
    from .serialization import write_json
    from .validation import export_annotation_frames
    output = Path(args.output).expanduser()
    exported = []
    for auto_path in sorted(Path(args.library).expanduser().glob("Athletes/*/analyses/*/auto_flight.json")):
        auto = load_json(str(auto_path), {})
        manifest = load_json(str(auto_path.parent / "manifest.json"), {})
        video = manifest.get("trial_context", {}).get("source_video")
        if auto.get("release_frame") is None or not video:
            continue
        results = load_json(str(auto_path.parent / "results.json"), {})
        apex = ((results.get("flight") or {}).get("model_check") or {}).get("apex_frame")
        filtered_path = auto_path.parent / "bag_flight_filtered.json"
        filtered = load_json(str(filtered_path), {}) if filtered_path.exists() else {}
        weak = [p["frame"] for p in auto.get("points", []) if p.get("source", "mask") != "mask"]
        weak += filtered.get("rejected_outlier_frames", [])
        phases = bag_phase_frames(int(auto["release_frame"]), auto.get("first_contact_frame"),
                                  int(auto.get("last_tracked_frame") or auto["release_frame"]), apex,
                                  float(auto["fps"]), read_video_metadata(video).frame_count, weak)
        always = {int(auto["release_frame"]): "release"}
        if auto.get("first_contact_frame") is not None:
            always[int(auto["first_contact_frame"])] = "landing"
        plan = select_bag_frames(phases, args.per_phase, args.seed, always)
        folder = output / auto_path.parent.name
        frame_manifest = export_annotation_frames(video, [r["frame"] for r in plan], folder)
        frame_manifest["landmarks"] = ["bag"]   # annotator bag-only mode
        write_json(folder / "annotation_manifest.json", frame_manifest)
        # Kept apart from the annotation manifest so raters are not shown the automatic phases.
        write_json(folder / "bag_validation_plan.json", {"schema_version": 1, "analysis": str(auto_path.parent),
                                                         "frames": plan, "seed": args.seed})
        exported.append({"clip": auto_path.parent.name, "frames": len(plan)})
    return {"output": str(output), "clips": exported, "total_frames": sum(c["frames"] for c in exported)}


def handle_bag_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    """Tracker error vs the reference rater, next to rater-vs-rater disagreement on the same frames."""
    import numpy as np
    from .bag_validation import bag_benchmark, inter_rater, pooled
    from .serialization import write_json
    reports, floors = [], []
    for plan_path in sorted(Path(args.frames).expanduser().glob("*/bag_validation_plan.json")):
        plan = load_json(str(plan_path), {})
        files = {load_json(str(f), {}).get("rater"): f for f in sorted(plan_path.parent.glob("annotation_*.json"))}
        if not files:
            continue
        reference_rater = args.rater if args.rater in files else sorted(files)[0]
        report = bag_benchmark(files[reference_rater], plan["analysis"], plan_path)
        report["clip"] = plan_path.parent.name
        reports.append(report)
        for rater, path in files.items():
            if rater != reference_rater:
                floor = inter_rater(files[reference_rater], path, plan_path, report["success_radius_px"])
                floor["clip"] = plan_path.parent.name
                floors.append(floor)
    if not reports:
        raise ValueError("No annotation_*.json files found next to a bag_validation_plan.json. "
                         "Save each rater's download into its clip folder first.")
    release = [r["events"]["release"] for r in reports if r.get("events", {}).get("release", {}).get("status") == "compared"]
    contact = [r["events"]["first_contact"] for r in reports
               if r.get("events", {}).get("first_contact", {}).get("status") == "compared"]

    def timing(rows: list[dict[str, Any]]) -> dict[str, Any]:
        signed = np.array([r["signed_frames"] for r in rows], float)
        if not signed.size:
            return {"n": 0}
        return {"n": int(signed.size), "mean_signed_frames": float(signed.mean()),
                "median_abs_frames": float(np.median(np.abs(signed))), "max_abs_frames": float(np.abs(signed).max()),
                "within_1_frame": int(np.sum(np.abs(signed) <= 1)),
                "within_rater_window": sum(1 for r in rows if r.get("within_rater_window")),
                "with_rater_window": sum(1 for r in rows if "within_rater_window" in r)}
    result = {
        "schema_version": 1, "clips": len(reports),
        "trackers": pooled(reports),
        "human_floor": pooled(floors, key="raters_block") if floors else None,
        "human_floor_clips": len(floors),
        "human_event_differences_frames": [f["event_differences_frames"] for f in floors],
        "release_timing": timing(release), "first_contact_timing": timing(contact),
        "landing_position_error_px": {name: [r["landing_position_error_px"].get(name) for r in reports
                                             if r.get("landing_position_error_px")]
                                      for name in ("detection", "mask", "filtered", "effective")},
        "reading_note": ("Tracker error is only demonstrable down to the human floor: where tracker error is at or "
                         "below rater-vs-rater disagreement, the data cannot say which is closer to the true centre."),
        "per_clip": reports, "inter_rater_per_clip": floors,
    }
    if args.output:
        write_json(args.output, result)
    return {k: v for k, v in result.items() if k not in ("per_clip", "inter_rater_per_clip")}


def handle_validate_tracking(args: argparse.Namespace) -> dict[str, Any]:
    from .serialization import write_json
    from .validation import inter_rater_report, validation_report
    analysis = Path(args.analysis)
    arm_length = load_json(str(analysis / "normalized.json"), {}).get("arm_length_pixels")
    bag_csv = analysis / "bag_keypoints.csv"
    result = validation_report(args.annotation, analysis / "keypoints.csv", args.throwing_side, arm_length,
                               bag_csv if bag_csv.exists() else None, _automatic_events(analysis))
    if args.second_annotation:
        result["inter_rater"] = inter_rater_report(args.annotation, args.second_annotation,
                                                   args.throwing_side, arm_length)
    if args.output:
        write_json(args.output, result)
    return result


def handle_insights(args):
    from .insights import generate_insights
    generate_insights(args.project, args.trial_id)
    return {"trial_id": args.trial_id, "status": "ready"}


def dashboard_base_trial(root: Path, trials: list[dict[str, Any]]) -> dict[str, Any]:
    """The throw whose comparable group is largest (ties: the newest), so the summary pools as many throws as
    possible instead of whichever was imported last (a newer app version must not hide older throws, and one
    re-analyzed throw must not shrink the summary to itself)."""
    from .insights import compatible_key, read
    keys = {}
    for t in trials:
        d = root / t["analysisRelativePath"]
        if (d / "needs_reanalysis.json").exists():
            continue
        keys[t["id"]] = compatible_key(t, read(d / "manifest.json", {}))
    counts: dict[Any, int] = {}
    for key in keys.values():
        counts[key] = counts.get(key, 0) + 1
    candidates = [t for t in trials if t["id"] in keys] or trials
    return max(candidates, key=lambda t: (counts.get(keys.get(t["id"]), 0), t.get("createdAt") or ""))


def handle_athlete_dashboard(args: argparse.Namespace) -> dict[str, Any]:
    """The dashboard is athlete-level; any analysed throw of the athlete regenerates it."""
    from .insights import generate_insights
    root = Path(args.project).expanduser().resolve()
    project = load_json(str(root / "project.json"), {})
    trials = [t for t in project.get("trials", []) if t["athleteID"] == args.athlete_id and t.get("analysisRelativePath")]
    if not trials:
        raise ValueError("Analyze at least one throw for this athlete first.")
    generate_insights(root, dashboard_base_trial(root, trials)["id"], export_report=False)
    return {"athlete_id": args.athlete_id, "dashboard": str(root / "dashboards" / f"{args.athlete_id}.json")}


def handle_probe(args: argparse.Namespace) -> dict[str, Any]:
    del args
    packages = ("numpy", "scipy", "pandas", "matplotlib", "cv2", "rtmlib", "onnxruntime", "mediapipe")
    from .sports2d_adapter import availability
    return {
        "sports2d": availability(),
        "package_version": __version__,
        "python": sys.version.split()[0],
        "backends": {
            "sports2d": availability()["available"] and availability()["supported"],
            "rtmpose": importlib.util.find_spec("rtmlib") is not None,
            "mediapipe": importlib.util.find_spec("mediapipe") is not None,
            "canonical_pose_import": True,
        },
        "modules": {name: importlib.util.find_spec(name) is not None for name in packages},
        "offline_after_model_cache": True,
        "openai_api_calls": False,
    }


def handle_prepare_video(args: argparse.Namespace) -> dict[str, Any]:
    from .preparation import prepare_video
    return prepare_video(args.video, args.output, args.start_frame, args.end_frame, args.crop, args.rotation)


def handle_video_info(args: argparse.Namespace) -> dict[str, Any]:
    return read_video_metadata(args.video).to_dict()


def handle_bag_track(args: argparse.Namespace) -> dict[str, Any]:
    track = track_bag_from_seed(
        args.video,
        BagSeed.load(args.seed),
        requested_method=args.method,
        template_quality_threshold=args.quality_threshold,
        search_scale=args.search_scale,
    )
    track.save(args.output)
    return {
        "output": str(Path(args.output).expanduser().resolve()),
        "status": track.status,
        "effective_method": track.effective_method,
        "failure_frame_count": len(track.failure_frames),
    }


def handle_bag_qa(args: argparse.Namespace) -> dict[str, Any]:
    result = bag_tracking_qa(
        BagTrack.load(args.track),
        load_json(args.labels, []),
        arm_length_pixels=args.arm_length_pixels,
        automatic_release_frame=args.automatic_release_frame,
        manual_release_frame=args.manual_release_frame,
        fps=args.fps,
    )
    if args.output:
        from .serialization import write_json
        write_json(args.output, result)
    return result


ANALYSIS_LOCK_NAME = "cornhole-biomech-analysis.lock"


class analysis_slot:
    """Only one video analysis runs at a time on this computer, across app windows and copies of the app.

    Each analysis decodes a whole clip into memory (about 2 GB for a 1080p throw), so two or more at
    once can exhaust memory and freeze the Mac. A second analysis waits here, reporting that it is
    queued, until the first finishes (an OS file lock: released automatically if a process dies).
    Set CORNHOLE_ANALYSIS_LOCK to a path to override the lock file (tests).
    """

    def __init__(self, report=None):
        import os
        import tempfile
        self.path = Path(os.environ.get("CORNHOLE_ANALYSIS_LOCK") or Path(tempfile.gettempdir()) / ANALYSIS_LOCK_NAME)
        self.report = report
        self.handle = None

    def __enter__(self):
        import time
        try:
            import fcntl
        except ImportError:          # not POSIX: no cross-process lock
            return self
        self.handle = open(self.path, "a+")
        waited = False
        while True:
            try:
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except BlockingIOError:
                if not waited and self.report:
                    self.report("queued", 0.0, "Waiting for another analysis on this Mac to finish (one at a time).")
                waited = True
                time.sleep(1.0)

    def __exit__(self, *exc):
        if self.handle is not None:
            try:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            finally:
                self.handle.close()
        return False


def handle_analyze(args: argparse.Namespace) -> dict[str, Any]:
    with analysis_slot(progress):
        return _handle_analyze(args)


def _handle_analyze(args: argparse.Namespace) -> dict[str, Any]:
    context = TrialContext(
        trial_id=args.trial_id,
        athlete_id=args.athlete_id,
        camera_view=args.view,
        throwing_side=args.throwing_side,
        target_direction=args.target_direction,
        source_video=str(Path(args.video).expanduser().resolve()),
        source_url=args.source_url,
        source_attribution=args.source_attribution,
    )
    result = analyze_trial(
        context,
        args.output,
        config_overrides=load_json(args.config),
        backend=args.backend,
        pose_input=args.pose_input,
        corrections_path=args.corrections,
        events_path=args.events,
        device=args.device,
        force_pose=args.force_pose,
        make_annotated_video=not args.no_annotated_video,
        app_version=args.app_version,
        progress=progress,
        bag_track_input=args.bag_track_input,
        bag_seed_path=args.bag_seed,
        bag_corrections_path=args.bag_corrections,
        calibration_path=args.calibration,
    )
    return {"output_dir": result["output_dir"], "results": result["results"]}


def handle_compare(args: argparse.Namespace) -> dict[str, Any]:
    return compare_trial(args.test, args.reference, args.output, load_json(args.config))


def handle_batch(args: argparse.Namespace) -> dict[str, Any]:
    specification = load_json(args.spec)
    completed: list[dict[str, Any]] = []
    for index, trial in enumerate(specification.get("trials", [])):
        progress("batch", index / max(1, len(specification["trials"])), f"Analyzing {trial['trial_id']}")
        context = TrialContext.from_dict(trial)
        result = analyze_trial(
            context,
            trial["output_dir"],
            config_overrides=specification.get("config"),
            backend=trial.get("backend", specification.get("backend", "rtmpose")),
            pose_input=trial.get("pose_input"),
            corrections_path=trial.get("corrections"),
            events_path=trial.get("events"),
            bag_track_input=trial.get("bag_track_input"),
            bag_seed_path=trial.get("bag_seed"),
            bag_corrections_path=trial.get("bag_corrections"),
            calibration_path=trial.get("calibration"),
            device=trial.get("device", "cpu"),
            make_annotated_video=trial.get("annotated_video", True),
            progress=progress,
        )
        completed.append({"trial_id": trial["trial_id"], "output_dir": result["output_dir"]})
    return {"completed": completed}


def handle_relationships(args: argparse.Namespace) -> dict[str, Any]:
    outcomes = load_json(args.outcomes, {})
    return analyze_relationships(
        args.analysis, outcomes, args.output,
        comparison_dirs=args.comparison,
        minimum_trials=args.minimum_trials,
    )


def _point(value: dict[str, Any] | None) -> BoardPoint | None:
    return None if value is None else BoardPoint(**value)


def handle_outcome(args: argparse.Namespace) -> dict[str, Any]:
    value = load_json(args.input)
    outcome = TrialOutcome(
        intended_target=value["intended_target"],
        score_category=value.get("score_category"),
        throw_type=value["throw_type"],
        notes=value.get("notes", ""),
        intended_point=_point(value.get("intended_point")),
        first_contact_point=_point(value.get("first_contact_point")),
        final_resting_point=_point(value.get("final_resting_point")),
    )
    return outcome_summary(outcome)


def handle_set_board_corners(args: argparse.Namespace) -> dict[str, Any]:
    """Store clicked deck corners for a trial's analysis output folder, ordered consistently
    (front-far, front-near, back-near, back-far) regardless of click order, and transfer them
    to other trials' analysis output folders shot from the same camera position.
    """
    import cv2
    from .board import order_corners, transfer_corners
    values = [float(v) for v in args.corners.split(",")]
    if len(values) != 8:
        raise ValueError("Give exactly four corners: x1,y1,x2,y2,x3,y3,x4,y4.")
    source = Path(args.trial_dir)
    manifest_path = source / "manifest.json"
    if not manifest_path.exists():
        raise ValueError(f"{manifest_path} does not exist. --trial-dir is the trial's analysis output folder "
                         "(analyze it first).")
    target_direction = (load_json(str(manifest_path), {}).get("trial_context") or {}).get("target_direction")
    if target_direction not in ("left_to_right", "right_to_left"):
        raise ValueError(f"{manifest_path} has no target_direction; analyze this trial first.")
    ordered = order_corners(np.asarray(values, float).reshape(4, 2), target_direction)
    source_frame = _plate_reference_frame(source)
    if source_frame is None:
        raise ValueError(f"{source / 'auto_flight.json'} does not say which frame plate.jpg was built in; "
                         "analyze this trial first.")
    write_json(source / "board_corners.json",
               {"corners_px": ordered.tolist(), "source": "clicked", "reference_frame": source_frame})
    applied, failed = [], []
    src_plate = cv2.imread(str(source / "plate.jpg"))
    for other in args.apply_to:
        # plate-to-plate transfer lands in the target's own plate pixels, i.e. its reference frame
        dst_plate = cv2.imread(str(Path(other) / "plate.jpg"))
        target_frame = _plate_reference_frame(Path(other))
        moved = (None if src_plate is None or dst_plate is None or target_frame is None
                 else transfer_corners(src_plate, dst_plate, ordered))
        if moved is None:
            failed.append(other)
            continue
        write_json(Path(other) / "board_corners.json",
                  {"corners_px": moved.tolist(), "source": f"transferred:{source.name}",
                   "reference_frame": target_frame})
        applied.append(other)
    return {"written": str(source / "board_corners.json"), "applied": applied, "failed": failed}


def _plate_reference_frame(trial_dir: Path) -> int | None:
    """The frame `plate.jpg` in this analysis folder was built in (the plate the user clicked on):
    auto_flight.json's board `reference_frame`, else its release frame (pre-8c caches)."""
    path = trial_dir / "auto_flight.json"
    auto = (load_json(str(path), {}) if path.exists() else {}) or {}
    frame = (auto.get("board") or {}).get("reference_frame", auto.get("release_frame"))
    return None if frame is None else int(frame)


def handle_calibrate_session(args: argparse.Namespace) -> dict[str, Any]:
    """Pool every listed throw's own gravity-calibrated board HFOV (`results.json["scale"]`'s
    `per_throw_hfov_deg`/`per_throw_hfov_status`, written by `analyze`) into one session estimate
    (`board.pool_session_hfov`), and write it as `camera.json` into every listed folder. Analyzing
    (or reanalyzing) those throws afterward prefers this pooled field of view over each throw's own
    noisy single-flight one (`pipeline._board_scale`). It pools only the listed folders: it has no
    library-wide fallback for a session with too few measured throws (the two-pass scripts do).
    """
    from .board import pool_session_hfov
    dirs = [Path(d) for d in args.analyses]
    calibrations = []
    for directory in dirs:
        manifest = load_json(str(directory / "manifest.json"), {})
        results = load_json(str(directory / "results.json"), {})
        scale = results.get("scale") or {}
        trial_id = (manifest.get("trial_context") or {}).get("trial_id") or directory.name
        calibrations.append({"trial_id": trial_id, "hfov_deg": scale.get("per_throw_hfov_deg"),
                             "status": scale.get("per_throw_hfov_status")})
    pooled = pool_session_hfov(calibrations)
    from .serialization import canonical_hash
    session_key = args.session_key or canonical_hash(sorted(str(d.resolve()) for d in dirs))
    camera = {**pooled, "session_key": session_key}
    for directory in dirs:
        write_json(directory / "camera.json", camera)
    return camera


def main(argv: list[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        result = args.handler(args)
        emit({"type": "result", "success": True, "data": result})
        return 0
    except Exception as error:
        emit({
            "type": "error",
            "success": False,
            "error_type": type(error).__name__,
            "message": str(error),
        })
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
