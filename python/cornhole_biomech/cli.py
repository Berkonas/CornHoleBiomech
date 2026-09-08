"""Structured command-line boundary shared by the Swift app and researchers."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any
import argparse
import importlib.util
import json
import sys

from . import __version__
from .models import BoardPoint, TrialContext, TrialOutcome
from .outcomes import outcome_summary
from .pipeline import analyze_relationships, analyze_trial, compare_trial
from .serialization import json_ready
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
    analyze.add_argument("--config")
    analyze.add_argument("--app-version", default="0.1.0")
    analyze.add_argument("--force-pose", action="store_true")
    analyze.add_argument("--no-annotated-video", action="store_true")
    analyze.set_defaults(handler=handle_analyze)

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
    return root


def handle_insights(args):
    from .insights import generate_insights
    generate_insights(args.project, args.trial_id)
    return {"trial_id": args.trial_id, "status": "ready"}


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


def handle_video_info(args: argparse.Namespace) -> dict[str, Any]:
    return read_video_metadata(args.video).to_dict()


def handle_analyze(args: argparse.Namespace) -> dict[str, Any]:
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
        score_category=int(value["score_category"]),
        throw_type=value["throw_type"],
        notes=value.get("notes", ""),
        intended_point=_point(value.get("intended_point")),
        first_contact_point=_point(value.get("first_contact_point")),
        final_resting_point=_point(value.get("final_resting_point")),
    )
    return outcome_summary(outcome)


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
