#!/usr/bin/env python3
"""Re-run the analysis of every analysed throw in a library with the current engine.

Pose, manual corrections, reviewed events and bag reviews are reused from each
analysis folder (the pipeline never discards manual work); automatic bag tracks
from an older tracker revision are recomputed. Insights are regenerated so the
app's Results open immediately. Outcomes in project.json are untouched.

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
from cornhole_biomech.pipeline import analyze_trial  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", required=True)
    args = parser.parse_args()
    root = Path(args.library).expanduser().resolve()
    project = json.loads((root / "project.json").read_text())
    failures = []
    for trial in project["trials"]:
        if not trial.get("analysisRelativePath"):
            continue
        folder = root / trial["analysisRelativePath"]
        context = json.loads((folder / "manifest.json").read_text())["trial_context"]
        print(f"Analyzing {trial.get('name')} · {trial.get('originalFilename')}", flush=True)
        try:
            analyze_trial(TrialContext(**context), folder, make_annotated_video=False, app_version="cli")
            generate_insights(root, trial["id"], export_report=True)
        except Exception as error:  # keep going: one bad clip must not stop the library
            failures.append((trial.get("originalFilename"), str(error)))
            print(f"   failed: {error}", flush=True)
    print(f"Done: {len(failures)} failure(s)")
    for name, error in failures:
        print(f"  {name}: {error}")


if __name__ == "__main__":
    main()
