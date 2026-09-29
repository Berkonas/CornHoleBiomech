#!/usr/bin/env python3
"""Build an athlete library the app can open, from folders of throw videos.

Each folder becomes one athlete with one session; every video is copied into the
library, analyzed with the full automatic pipeline (pose, bag flight, release,
swing), and summarized so Results open immediately. Outcomes (0/1/3) are left
unknown: enter them in the app. Existing folders are never overwritten.

Example:
  python scripts/build_library.py --output ~/Documents/"Cornhole Pilot Library" \
      --athlete "Player 1=data/videos/Player 1" \
      --athlete "Player 2=data/videos/Player 2"
Optionally reuse existing analysis folders named after each clip with --reuse DIR.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from cornhole_biomech.insights import generate_insights  # noqa: E402
from cornhole_biomech.models import TrialContext  # noqa: E402
from cornhole_biomech.pipeline import analyze_trial  # noqa: E402

VIDEO_SUFFIXES = {".mov", ".mp4", ".m4v"}


def slug(value: str) -> str:
    parts = [p for p in re.split(r"[^A-Za-z0-9]+", value) if p]
    return "-".join(parts)[:60] or "Athlete"


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build(output: Path, athletes: list[tuple[str, Path]], side: str, direction: str, reuse: Path | None) -> Path:
    if output.exists():
        raise SystemExit(f"{output} already exists; choose a new folder (existing data is never overwritten).")
    output.mkdir(parents=True)
    stamp = now()
    project = {"schemaVersion": 4, "appVersion": "cli", "id": str(uuid.uuid4()).upper(), "name": output.name,
               "createdAt": stamp, "updatedAt": stamp, "athletes": [], "trials": [], "sessions": [], "referenceSets": [],
               "analysisSettings": {"confidenceThreshold": 0.35, "maxInterpolationGapFrames": 3, "filterEnabled": True,
                                    "filterOrder": 4, "filterCutoffHz": 6.0, "normalizationSamples": 101,
                                    "minimumRelationshipTrials": 8, "poseBackend": "sports2d",
                                    "poseModel": "body_with_feet", "poseMode": "balanced"}}
    for name, folder in athletes:
        athlete_id = str(uuid.uuid4()).upper()
        session_id = str(uuid.uuid4()).upper()
        base = f"Athletes/{slug(name)}-{athlete_id[:8]}"
        project["athletes"].append({"id": athlete_id, "participantCode": name, "dominantHand": side, "notes": ""})
        project["sessions"].append({"id": session_id, "athleteID": athlete_id, "name": f"{folder.name} session",
                                    "date": stamp, "cameraSetup": "Side view", "cameraView": "side",
                                    "throwingSide": side, "targetDirection": direction, "notes": "",
                                    "referenceTrialIDs": []})
        videos = sorted((p for p in folder.iterdir() if p.suffix.lower() in VIDEO_SUFFIXES),
                        key=lambda p: [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", p.name)])
        for index, video in enumerate(videos, 1):
            trial_id = str(uuid.uuid4()).upper()
            video_rel = f"{base}/throws/{trial_id[:8]}-{video.name}"
            analysis_rel = f"{base}/analyses/Throw-{trial_id[:8]}"
            (output / video_rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(video, output / video_rel)
            if reuse is not None:
                cached = reuse / video.stem.replace(" ", "")
                if cached.exists():   # pose/bag caches are keyed by video hash, so they stay valid
                    shutil.copytree(cached, output / analysis_rel)
            print(f"Analyzing {name} · {video.name}", flush=True)
            status = "Analyzed"
            try:
                analyze_trial(TrialContext(trial_id, athlete_id, "side", side, direction, str(output / video_rel)),
                              output / analysis_rel, make_annotated_video=False, app_version="cli")
            except Exception as error:   # keep going: one bad clip must not stop a session
                status = f"Analysis failed: {error}"
                print(f"   failed: {error}", flush=True)
            project["trials"].append({"id": trial_id, "athleteID": athlete_id, "createdAt": stamp,
                                      "sourceVideoRelativePath": video_rel, "originalFilename": video.name,
                                      "cameraView": "side", "throwingSide": side, "targetDirection": direction,
                                      "isReference": False, "sessionID": session_id, "name": f"Throw {index}",
                                      "analysisRelativePath": analysis_rel if status == "Analyzed" else None,
                                      "analysisStatus": status})
    for sub in ("comparisons", "exports", "relationships", "References"):
        (output / sub).mkdir(exist_ok=True)
    (output / "project.json").write_text(json.dumps(project, indent=2))
    for trial in project["trials"]:
        if trial["analysisRelativePath"]:
            generate_insights(output, trial["id"], export_report=True)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--athlete", action="append", required=True, help='"Name=folder of videos"')
    parser.add_argument("--throwing-side", choices=("left", "right"), default="right")
    parser.add_argument("--target-direction", choices=("left_to_right", "right_to_left"), default="left_to_right")
    parser.add_argument("--reuse", type=Path, help="Folder of earlier analysis outputs named after each clip")
    args = parser.parse_args()
    athletes = []
    for item in args.athlete:
        name, _, folder = item.partition("=")
        athletes.append((name.strip(), Path(folder).expanduser()))
    print(build(args.output.expanduser(), athletes, args.throwing_side, args.target_direction,
                args.reuse.expanduser() if args.reuse else None))


if __name__ == "__main__":
    main()
