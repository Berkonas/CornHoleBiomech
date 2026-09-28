#!/usr/bin/env python3
"""Add a folder of throw videos to an existing athlete library as one new recording session.

Videos are copied into the athlete's `throws/` folder and registered in project.json the way
`build_library.py` does it (same trial, session and analysis-folder layout). Analysis is left to
`reanalyze_library.py`, which analyses every throw, pools each recording session's field of view
and re-analyses, so a throw whose own flight is too short to calibrate the camera borrows the
session's calibration. Existing throws, outcomes and manual work are never touched; a video whose
file name is already in the athlete's library is skipped.

Example (Player 1's 4K clips):
  PYTHONPATH=python .venv/bin/python scripts/add_session_to_library.py \\
      --library ~/Documents/"Cornhole Pilot Library" --athlete "Player 1" \\
      --videos ~/Desktop/"Videos For Biomech/Player 1" --pattern "playe1*" --session "4K session"
  PYTHONPATH=python .venv/bin/python scripts/reanalyze_library.py --library ~/Documents/"Cornhole Pilot Library"

`--reuse DIR` copies earlier analysis folders named after each clip (DIR/<clip stem>) as a head
start; pose and bag caches are keyed by the video's hash, so they stay valid after the copy.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

VIDEO_SUFFIXES = {".mov", ".mp4", ".m4v"}


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def natural(path: Path) -> list:
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", path.name)]


def add_session(library: Path, athlete_name: str, videos: list[Path], session_name: str,
                side: str, direction: str, reuse: Path | None = None) -> list[str]:
    project_path = library / "project.json"
    project = json.loads(project_path.read_text())
    athlete = next((a for a in project["athletes"] if athlete_name in (a.get("participantCode"), a.get("name"))), None)
    if athlete is None:
        raise SystemExit(f"No athlete named {athlete_name!r} in {project_path}.")
    athlete_id = athlete["id"]
    existing = [t for t in project["trials"] if t["athleteID"] == athlete_id]
    if not existing:
        raise SystemExit(f"{athlete_name} has no throws yet; cannot tell where the athlete's folder is.")
    base = existing[0]["sourceVideoRelativePath"].split("/throws/")[0]
    known = {t.get("originalFilename") for t in existing}
    stamp = now()
    session_id = str(uuid.uuid4()).upper()
    project.setdefault("sessions", []).append({
        "id": session_id, "athleteID": athlete_id, "name": session_name, "date": stamp,
        "cameraSetup": "Side view", "cameraView": "side", "throwingSide": side, "targetDirection": direction,
        "notes": "", "referenceTrialIDs": []})
    added = []
    number = len(existing)
    for video in videos:
        if video.name in known:
            print(f"skip {video.name}: already in the library")
            continue
        number += 1
        trial_id = str(uuid.uuid4()).upper()
        video_rel = f"{base}/throws/{trial_id[:8]}-{video.name}"
        analysis_rel = f"{base}/analyses/Throw-{trial_id[:8]}"
        (library / video_rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(video, library / video_rel)   # keeps the file date: sessions pool by recording date
        (library / analysis_rel).mkdir(parents=True, exist_ok=False)
        if reuse is not None and (reuse / video.stem).is_dir():
            for name in ("pose_raw.json", "pose_cache.json", "sports2d", "scene_vision"):
                source = reuse / video.stem / name
                if source.is_dir():
                    shutil.copytree(source, library / analysis_rel / name)
                elif source.exists():
                    shutil.copy2(source, library / analysis_rel / name)
        manifest = {"trial_context": {"trial_id": trial_id, "athlete_id": athlete_id, "camera_view": "side",
                                      "throwing_side": side, "target_direction": direction,
                                      "source_video": str(library / video_rel)}}
        (library / analysis_rel / "manifest.json").write_text(json.dumps(manifest, indent=2))
        project["trials"].append({"id": trial_id, "athleteID": athlete_id, "createdAt": stamp,
                                  "sourceVideoRelativePath": video_rel, "originalFilename": video.name,
                                  "cameraView": "side", "throwingSide": side, "targetDirection": direction,
                                  "isReference": False, "sessionID": session_id, "name": f"Throw {number}",
                                  "analysisRelativePath": analysis_rel, "analysisStatus": "Needs analysis"})
        added.append(video.name)
    project["updatedAt"] = stamp
    temporary = project_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(project, indent=2))
    temporary.replace(project_path)
    return added


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--library", required=True, type=Path)
    parser.add_argument("--athlete", required=True, help="Participant code shown in the app, e.g. 'Player 1'")
    parser.add_argument("--videos", required=True, type=Path, help="Folder of throw videos")
    parser.add_argument("--pattern", default="*", help="Glob inside the folder, e.g. 'playe1*'")
    parser.add_argument("--session", required=True, help="Session name shown in the app")
    parser.add_argument("--throwing-side", choices=("left", "right"), default="right")
    parser.add_argument("--target-direction", choices=("left_to_right", "right_to_left"), default="left_to_right")
    parser.add_argument("--reuse", type=Path)
    args = parser.parse_args()
    folder = args.videos.expanduser()
    videos = sorted((p for p in folder.glob(args.pattern) if p.suffix.lower() in VIDEO_SUFFIXES), key=natural)
    added = add_session(args.library.expanduser(), args.athlete, videos, args.session, args.throwing_side,
                        args.target_direction, args.reuse.expanduser() if args.reuse else None)
    print(f"Added {len(added)} throw(s): {', '.join(added)}")


if __name__ == "__main__":
    main()
