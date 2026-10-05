#!/usr/bin/env python3
"""Add an athlete's two-camera takes (Take_<n>_Front / Take_<n>_Side videos) to an athlete library.

For every take in the folder (file names matched in any capitalisation; a take whose Front and Side
files were swapped is detected from the cameras and used the right way round), the take is prepared
(``takes.prepare_take``: the two soundtracks synchronised, each throw found in the side video, one side
and one front clip cut per throw, the board found in the front camera) into
``<athlete>/takes/Take-<n>-<id>/``. Each throw becomes one trial in project.json, linked to its take
(``take_link.json`` in its analysis folder). The front camera's field of view is then pooled over the
athlete's takes.

Nothing is analysed here: run ``analyze_library.py`` afterwards (one throw at a time). Takes already in
the library (same take number for this athlete) are skipped. The library and athlete are created when
they do not exist yet.

  PYTHONPATH=python .venv/bin/python scripts/add_takes_to_library.py \\
      --library ~/Documents/"Cornhole Biomechanics Lab Data" --athlete "Player 1" \\
      --folder "data/videos/Final Data Collection/Player 1"
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from cornhole_biomech.cli import analysis_slot  # noqa: E402
from cornhole_biomech.takes import (assign_camera_roles, camera_signature, discover_takes,  # noqa: E402
                                    front_setups, pool_front_hfov, prepare_take, recording_date,
                                    share_front_lag)
from cornhole_biomech.two_view import TAKE_LINK_FILENAME  # noqa: E402

SCHEMA_VERSION = 4


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slug(value: str) -> str:
    parts = [p for p in re.split(r"[^A-Za-z0-9]+", value) if p]
    return "-".join(parts)[:60] or "Athlete"


def new_library(root: Path) -> dict:
    stamp = now()
    root.mkdir(parents=True, exist_ok=True)
    for sub in ("Athletes", "comparisons", "exports", "relationships", "References"):
        (root / sub).mkdir(exist_ok=True)
    return {"schemaVersion": SCHEMA_VERSION, "appVersion": "cli", "id": str(uuid.uuid4()).upper(), "name": root.name,
            "createdAt": stamp, "updatedAt": stamp, "athletes": [], "trials": [], "sessions": [], "referenceSets": [],
            "analysisSettings": {"confidenceThreshold": 0.35, "maxInterpolationGapFrames": 3, "filterEnabled": True,
                                 "filterOrder": 4, "filterCutoffHz": 6.0, "normalizationSamples": 101,
                                 "minimumRelationshipTrials": 8, "poseBackend": "sports2d",
                                 "poseModel": "body_with_feet", "poseMode": "balanced"}}


def save(root: Path, project: dict) -> None:
    project["updatedAt"] = now()
    path = root / "project.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(project, indent=2))
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--library", required=True, type=Path)
    parser.add_argument("--athlete", required=True, help="Participant code, e.g. 'Player 1'")
    parser.add_argument("--folder", required=True, type=Path, help="Folder with Take_<n>_Front/Side videos")
    parser.add_argument("--throwing-side", choices=("left", "right"), default="right")
    parser.add_argument("--target-direction", choices=("left_to_right", "right_to_left"), default="left_to_right")
    parser.add_argument("--expected-throws", type=int, default=4)
    parser.add_argument("--takes", help="Only these take numbers, e.g. 1,3")
    args = parser.parse_args()

    root = args.library.expanduser().resolve()
    project = json.loads((root / "project.json").read_text()) if (root / "project.json").exists() else new_library(root)
    for key in ("athletes", "trials", "sessions"):
        project.setdefault(key, [])
        if project[key] is None:
            project[key] = []
    athlete = next((a for a in project["athletes"] if a.get("participantCode") == args.athlete), None)
    if athlete is None:
        athlete = {"id": str(uuid.uuid4()).upper(), "participantCode": args.athlete,
                   "dominantHand": args.throwing_side, "notes": ""}
        project["athletes"].append(athlete)
        save(root, project)
        print(f"Created athlete {args.athlete}", flush=True)
    athlete_id = athlete["id"]
    base = f"Athletes/{slug(args.athlete)}-{athlete_id[:8]}"
    (root / base / "analyses").mkdir(parents=True, exist_ok=True)

    takes = discover_takes(args.folder.expanduser())
    signatures = {p: camera_signature(p) for t in takes for p in (t.front, t.side) if p}
    roles = assign_camera_roles(takes, signatures)
    if roles.get("swapped_takes"):
        print(f"Takes with swapped Front/Side labels (used the right way round): {roles['swapped_takes']}", flush=True)
    wanted = {int(x) for x in args.takes.split(",")} if args.takes else None
    known = {t.get("takeNumber") for t in project["trials"] if t["athleteID"] == athlete_id}
    records = []
    for take in takes:
        if wanted and take.take not in wanted:
            continue
        for note in take.notes:
            print(f"  note: {note}", flush=True)
        if take.take in known:
            print(f"Take {take.take}: already in the library, skipped", flush=True)
            continue
        if not take.side:
            print(f"Take {take.take}: no side video, skipped", flush=True)
            continue
        take_id = str(uuid.uuid4()).upper()
        take_rel = f"{base}/takes/Take-{take.take:02d}-{take_id[:8]}"
        print(f"Take {take.take}: preparing (sync, throws, clips)", flush=True)

        def progress(stage: str, fraction: float, message: str) -> None:
            if stage in ("synchronising", "done") or fraction in (0.68, 0.84):
                print(f"   {message}", flush=True)

        with analysis_slot(lambda s, f, m: print(f"   {m}", flush=True)):
            record = prepare_take(take.front, take.side, root / take_rel, take_number=take.take,
                                  target_direction=args.target_direction, expected_throws=args.expected_throws,
                                  progress=progress)
        sync = record.get("sync") or {}
        print(f"   sync: {sync.get('status')} offset={sync.get('offset_s')} r={sync.get('correlation')}; "
              f"throws: {len(record['throws'])}; front board: {(record.get('front_board') or {}).get('status')}",
              flush=True)
        for note in record.get("notes", []):
            print(f"   note: {note}", flush=True)
        records.append(root / take_rel / "take.json")
        recorded = recording_date(signatures.get(take.side))
        # One recording session per athlete and day (one camera set-up): the athlete's takes from that day are
        # compared together on the summary. The take stays on each throw (takeNumber).
        session_name = f"Two-camera session · {recorded or 'unknown date'}"
        session = next((s for s in project["sessions"] if s.get("athleteID") == athlete_id
                        and s.get("name") == session_name), None)
        if session is None:
            session = {"id": str(uuid.uuid4()).upper(), "athleteID": athlete_id, "name": session_name, "date": now(),
                       "cameraSetup": "Side + front (two cameras)", "cameraView": "side",
                       "throwingSide": args.throwing_side, "targetDirection": args.target_direction,
                       "notes": f"Recorded {recorded or 'on an unknown date'}; takes are kept on each throw.",
                       "referenceTrialIDs": []}
            project["sessions"].append(session)
        session_id = session["id"]
        for throw in record["throws"]:
            if not throw.get("side_clip"):
                continue
            trial_id = str(uuid.uuid4()).upper()
            analysis_rel = f"{base}/analyses/Throw-{trial_id[:8]}"
            folder = root / analysis_rel
            folder.mkdir(parents=True, exist_ok=False)
            side_rel = f"{take_rel}/{Path(throw['side_clip']['path']).name}"
            front_rel = f"{take_rel}/{Path(throw['front_clip']['path']).name}" if throw.get("front_clip") else None
            context = {"trial_id": trial_id, "athlete_id": athlete_id, "camera_view": "side",
                       "throwing_side": args.throwing_side, "target_direction": args.target_direction,
                       "source_video": str(root / side_rel), "source_url": None, "source_attribution": None,
                       "recording_date": recorded}
            (folder / "manifest.json").write_text(json.dumps({"trial_context": context}, indent=2))
            (folder / TAKE_LINK_FILENAME).write_text(json.dumps({
                "schema_version": 1, "take_record": f"../../takes/{Path(take_rel).name}/take.json",
                "throw_number": throw["number"]}, indent=2))
            project["trials"].append({
                "id": trial_id, "athleteID": athlete_id, "createdAt": now(), "sourceVideoRelativePath": side_rel,
                "originalFilename": f"{Path(record['side']['path']).name} · throw {throw['number']}",
                "cameraView": "side", "throwingSide": args.throwing_side, "targetDirection": args.target_direction,
                "isReference": False, "sessionID": session_id, "name": f"Take {take.take} · Throw {throw['number']}",
                "analysisRelativePath": analysis_rel, "analysisStatus": "Needs analysis",
                "takeNumber": take.take, "throwInTake": throw["number"], "frontVideoRelativePath": front_rel,
                "takeRecordRelativePath": f"{take_rel}/take.json", "recordingDate": recorded})
        save(root, project)
    # Pool the front camera's field of view over every take the same phone recorded that day (all athletes):
    # the field of view is a property of the lens, not of where the tripod stood.
    for key, records in front_setups(sorted(root.glob("Athletes/*/takes/Take-*/take.json"))).items():
        pooled = pool_front_hfov(records)
        share_front_lag(records)        # a re-prepared take gets its set-up's measured picture lag back
        print(f"Front camera field of view ({key}): {pooled.get('status')} {pooled.get('median_deg')}° from "
              f"{pooled.get('takes')} take(s)", flush=True)
    print(f"Done. {sum(1 for t in project['trials'] if t['athleteID'] == athlete_id)} throws for {args.athlete}.")


if __name__ == "__main__":
    main()
