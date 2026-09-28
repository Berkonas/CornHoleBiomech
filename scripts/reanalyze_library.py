#!/usr/bin/env python3
"""Re-run the analysis of every analysed throw in a library with the current engine.

Pose, manual corrections, reviewed events and bag reviews are reused from each
analysis folder (the pipeline never discards manual work); automatic bag tracks
from an older tracker revision are recomputed. Insights are regenerated so the
app's Results open immediately. Outcomes in project.json are untouched.

Two passes (Task 8b): a throw's own board field-of-view calibration from its ~0.4 s bag flight
is noisy (per-throw HFOV can vary ten-plus degrees between throws shot from the same phone in
one sitting). Pass 1 analyses every throw and reports each one's own per-throw calibration; each
recording session (same athlete, same source-clip folder) is then pooled into one camera.json
(`pipeline.pool_session_camera_files`); pass 2 re-analyses every throw so `_board_scale` picks up
the pooled, less noisy field of view.

    PYTHONPATH=python .venv/bin/python scripts/reanalyze_library.py --library ~/Documents/"Cornhole Pilot Library"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from cornhole_biomech.insights import generate_insights  # noqa: E402
from cornhole_biomech.models import TrialContext  # noqa: E402
from cornhole_biomech.pipeline import analyze_trial, pool_session_camera_files  # noqa: E402


def _analyzed_folders(project: dict) -> list[tuple[dict, Path]]:
    return [(trial, trial["analysisRelativePath"]) for trial in project["trials"]
            if trial.get("analysisRelativePath")]


def _analyze_pass(root: Path, project: dict, statuses: dict[str, str] | None = None) -> list[str]:
    """Analyse every throw with an analysis folder once; return failure messages.

    With `statuses`, each throw's outcome ("Analyzed" or "Analysis failed: ...") is recorded by id.
    """
    failures = []
    for trial, relative_path in _analyzed_folders(project):
        folder = root / relative_path
        context = json.loads((folder / "manifest.json").read_text())["trial_context"]
        print(f"Analyzing {trial.get('name')} · {trial.get('originalFilename')}", flush=True)
        try:
            analyze_trial(TrialContext(**context), folder, make_annotated_video=False, app_version="cli")
            if statuses is not None:
                statuses[trial["id"]] = "Analyzed"
        except Exception as error:  # keep going: one bad clip must not stop the library
            failures.append(f"{trial.get('originalFilename')}: {error}")
            print(f"   failed: {error}", flush=True)
            if statuses is not None:
                statuses[trial["id"]] = f"Analysis failed: {error}"
    return failures


def _save_statuses(root: Path, statuses: dict[str, str]) -> None:
    """Write each throw's final analysis status into project.json (atomically)."""
    path = root / "project.json"
    project = json.loads(path.read_text())
    for trial in project["trials"]:
        if trial["id"] in statuses:
            trial["analysisStatus"] = statuses[trial["id"]]
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(project, indent=2))
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", required=True)
    args = parser.parse_args()
    root = Path(args.library).expanduser().resolve()
    project = json.loads((root / "project.json").read_text())

    print("Pass 1/2: per-throw analysis", flush=True)
    failures = _analyze_pass(root, project)

    folders = [root / relative_path for _, relative_path in _analyzed_folders(project)]
    print(f"Pooling {len(folders)} throw(s) into recording sessions", flush=True)
    pooled = pool_session_camera_files(folders)
    for key, camera in pooled.items():
        iqr = "—" if camera["iqr_deg"] is None else f"{camera['iqr_deg']:.2f}"
        print(f"  {key}: {camera['status']} field of view from {camera['source']}, {camera['n']} measured "
              f"throw(s), hfov={camera['hfov_deg']}, IQR={iqr}", flush=True)

    print("Pass 2/2: re-analysis with the pooled session field of view", flush=True)
    statuses: dict[str, str] = {}
    failures += _analyze_pass(root, project, statuses)
    _save_statuses(root, statuses)

    for trial, _ in _analyzed_folders(project):
        try:
            generate_insights(root, trial["id"], export_report=True)
        except Exception as error:
            failures.append(f"{trial.get('originalFilename')} (insights): {error}")

    print(f"Done: {len(failures)} failure(s)")
    for message in failures:
        print(f"  {message}")


if __name__ == "__main__":
    main()
