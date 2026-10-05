#!/usr/bin/env python3
"""Analyse an athlete's throws one at a time: side camera, then front camera and the combined result.

Never runs two analyses at once (the engine's analysis lock is held for each throw), so the Mac is not
overloaded. Two passes, as in ``reanalyze_library.py``: pass 1 analyses every selected throw (pose, bag,
release); the side camera's field of view is then pooled per recording session; pass 2 re-runs the
fast part with the pooled value (pose is cached), adds the front camera (``two_view``) and refreshes
the athlete's insights and dashboard. After the front camera, the front picture lag is pooled per front set-up
(``two_view.pool_front_lag``) and throws analysed with a different lag get the front camera once more.

  PYTHONPATH=python .venv/bin/python scripts/analyze_library.py \\
      --library ~/Documents/"Cornhole Biomechanics Lab Data" --athlete "Player 1"

``--takes 1,4`` limits the run to some takes (spot checks); ``--only-new`` skips throws whose analysis
already finished with the current engine. ``--athlete all`` runs every athlete in turn (still one throw at a
time); run it once after the last athlete so every throw uses the side-camera field of view pooled over the
whole camera set-up.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from cornhole_biomech.cli import analysis_slot  # noqa: E402
from cornhole_biomech.insights import generate_insights  # noqa: E402
from cornhole_biomech.models import TrialContext  # noqa: E402
from cornhole_biomech.pipeline import analyze_trial, pool_session_camera_files  # noqa: E402
from cornhole_biomech.two_view import (TAKE_LINK_FILENAME, TWO_VIEW_VERSION, analyze_two_view, ensure_side_board_corners,  # noqa: E402
                                       load_take_link, outcome_from_two_view, pool_front_lag, share_side_board,
                                       side_camera_setups)


def log(message: str) -> None:
    print(time.strftime("%H:%M:%S ") + message, flush=True)


def save_statuses(root: Path, statuses: dict[str, str], outcomes: dict[str, dict] | None = None,
                  refreshed: set[str] | None = None) -> None:
    """Write analysis statuses, and front-camera outcomes for throws that have no result recorded yet
    (a result someone entered is never replaced). A throw whose front camera ran again (``refreshed``) and is
    no longer confident loses its earlier automatic result, so it shows as needing a result."""
    path = root / "project.json"
    project = json.loads(path.read_text())
    for trial in project["trials"]:
        if trial["id"] in statuses:
            trial["analysisStatus"] = statuses[trial["id"]]
        automatic = (outcomes or {}).get(trial["id"])
        previous = trial.get("outcome") or {}
        was_automatic = (previous.get("notes") or "").startswith("Recorded automatically")
        if automatic and (not previous or was_automatic):
            trial["outcome"] = automatic
        elif not automatic and was_automatic and trial["id"] in (refreshed or set()):
            trial.pop("outcome", None)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(project, indent=2))
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--library", required=True, type=Path)
    parser.add_argument("--athlete", required=True)
    parser.add_argument("--takes", help="Only these take numbers, e.g. 1,4")
    parser.add_argument("--only-new", action="store_true")
    parser.add_argument("--single-pass", action="store_true", help="Skip the pooled second pass (quick checks)")
    parser.add_argument("--front-only", action="store_true",
                        help="Only re-run the front camera and the combined result (side analyses kept)")
    args = parser.parse_args()
    root = args.library.expanduser().resolve()
    project = json.loads((root / "project.json").read_text())
    if args.athlete == "all":
        athlete_ids = [a["id"] for a in project["athletes"]]
    else:
        athlete = next((a for a in project["athletes"] if a.get("participantCode") == args.athlete), None)
        if athlete is None:
            raise SystemExit(f"No athlete {args.athlete!r} in {root}")
        athlete_ids = [athlete["id"]]
    order = {a: i for i, a in enumerate(athlete_ids)}
    wanted = {int(x) for x in args.takes.split(",")} if args.takes else None
    trials = [t for t in project["trials"] if t["athleteID"] in order and t.get("analysisRelativePath")
              and (wanted is None or t.get("takeNumber") in wanted)]
    trials.sort(key=lambda t: (order[t["athleteID"]], t.get("takeNumber") or 0, t.get("throwInTake") or 0,
                               t.get("createdAt") or ""))
    if args.only_new:
        def current(t: dict) -> bool:
            try:
                return json.loads((root / t["analysisRelativePath"] / "two_view.json").read_text()).get(
                    "method_version") == TWO_VIEW_VERSION
            except (OSError, ValueError):
                return False
        trials = [t for t in trials if not current(t)]
    log(f"{args.athlete}: {len(trials)} throw(s) to analyse, one at a time")
    statuses: dict[str, str] = {}
    outcomes: dict[str, dict] = {}
    failures: list[str] = []

    def board_missing(folder: Path) -> bool:
        try:
            board = json.loads((folder / "auto_flight.json").read_text()).get("board") or {}
        except (OSError, ValueError):
            return True
        return board.get("status") != "found"

    def side_pass(label: str, subset: list[dict] | None = None) -> None:
        batch = trials if subset is None else subset
        for n, trial in enumerate(batch, 1):
            folder = root / trial["analysisRelativePath"]
            context = json.loads((folder / "manifest.json").read_text())["trial_context"]
            ensure_side_board_corners(folder)
            log(f"[{label} {n}/{len(batch)}] {trial.get('name')}")
            started = time.time()
            try:
                with analysis_slot(lambda s, f, m: log(f"   {m}")):
                    analyze_trial(TrialContext.from_dict(context), folder, make_annotated_video=False, app_version="cli",
                                  progress=lambda s, f, m: None)
                statuses[trial["id"]] = "Analyzed"
                log(f"   side camera done in {time.time() - started:.0f} s")
            except Exception as error:  # one bad clip must not stop the athlete
                statuses[trial["id"]] = f"Analysis failed: {error}"
                failures.append(f"{trial.get('name')}: {error}")
                log(f"   FAILED: {error}")
                traceback.print_exc()

    if args.front_only:
        for trial in trials:
            if (root / trial["analysisRelativePath"] / "results.json").exists():
                statuses[trial["id"]] = trial.get("analysisStatus") or "Analyzed"
    else:
        side_pass("pass 1")
    # Throws analysed before any sibling had found the side deck: share it now and analyse them again.
    repair = []
    for trial in ([] if args.front_only else trials):
        folder = root / trial["analysisRelativePath"]
        if statuses.get(trial["id"]) == "Analyzed" and board_missing(folder) \
                and not (folder / "board_corners.json").exists():
            shared = share_side_board(folder)
            if shared:
                log(f"   {trial.get('name')}: side deck from {shared['from_throw']} "
                    f"(alignment {shared['alignment_correlation']:.2f})")
                repair.append(trial)
    if repair and args.single_pass:
        log(f"{len(repair)} throw(s) get the side deck from another throw; analysing them again")
        side_pass("deck repair", repair)
    folders = [root / t["analysisRelativePath"] for t in trials if statuses.get(t["id"]) == "Analyzed"]
    if folders and not args.single_pass and not args.front_only:
        # Two-camera throws: pool by physical side-camera set-up over the whole library (every athlete analysed
        # so far), since the lens field of view does not depend on who threw. Other throws: by session.
        everyone = [root / t["analysisRelativePath"] for t in project["trials"] if t.get("analysisRelativePath")
                    and (root / t["analysisRelativePath"] / TAKE_LINK_FILENAME).exists()
                    and (root / t["analysisRelativePath"] / "results.json").exists()]
        two_camera = [f for f in folders if (f / TAKE_LINK_FILENAME).exists()]
        pooled = {}
        if two_camera:
            pooled.update(pool_session_camera_files(everyone, groups=side_camera_setups(everyone)))
        single = [f for f in folders if f not in two_camera]
        if single:
            pooled.update(pool_session_camera_files(single))
        for key, camera in pooled.items():
            log(f"Side camera session {key}: {camera['status']} field of view {camera['hfov_deg']} from "
                f"{camera['n']} throw(s)")
        side_pass("pass 2")
    refreshed: set[str] = set()
    for n, trial in enumerate(trials, 1):
        folder = root / trial["analysisRelativePath"]
        if statuses.get(trial["id"]) != "Analyzed" or not (folder / TAKE_LINK_FILENAME).exists():
            continue
        log(f"[front {n}/{len(trials)}] {trial.get('name')}")
        try:
            with analysis_slot(lambda s, f, m: log(f"   {m}")):
                record = analyze_two_view(folder, throwing_side=trial.get("throwingSide", "right"))
            refreshed.add(trial["id"])
            log(f"   {record.get('status')}: {(record.get('explanation') or {}).get('sentence') or record.get('reason')}")
            automatic = outcome_from_two_view(record)
            if automatic:
                outcomes[trial["id"]] = automatic
                log(f"   result from the front camera: {automatic['score_category']} point(s)")
        except Exception as error:
            failures.append(f"{trial.get('name')} (front): {error}")
            log(f"   front camera FAILED: {error}")
            traceback.print_exc()
    # Front picture lag per front set-up from every throw both cameras saw land (two_view.pool_front_lag).
    # Every throw of the library analysed with a different lag gets the front camera once more (front only;
    # the front pose is cached), including other athletes' throws of the same set-up.
    rerun: list[dict] = []
    try:
        save_statuses(root, statuses, outcomes, refreshed)       # keep the work so far if anything below fails
        by_id = {t["id"]: t for t in project["trials"]}
        two_camera_all = [t for t in project["trials"] if t.get("analysisRelativePath")
                          and (root / t["analysisRelativePath"] / TAKE_LINK_FILENAME).exists()]
        lag_pools = pool_front_lag([root / t["analysisRelativePath"] for t in two_camera_all]) if two_camera_all else {}
        for key, pool in lag_pools.items():
            log(f"Front set-up {key}: picture lag {pool}")
        for trial in two_camera_all:
            folder = root / trial["analysisRelativePath"]
            if trial["id"] in statuses and statuses[trial["id"]] != "Analyzed":
                continue
            try:
                previous = json.loads((folder / "two_view.json").read_text())
                if previous.get("status") != "measured":
                    continue
                frames = previous.get("frames") or {}
                applied = float(frames.get("front_lag_s") or 0.0)
                wanted_lag = float((load_take_link(folder) or {}).get("front_lag_s") or 0.0)
                fps = float(frames.get("front_fps") or 30.0)
            except (OSError, ValueError, KeyError, TypeError):
                continue
            if abs(wanted_lag - applied) >= 0.5 / fps:
                rerun.append(by_id[trial["id"]])
        for n, trial in enumerate(rerun, 1):
            folder = root / trial["analysisRelativePath"]
            log(f"[front with lag {n}/{len(rerun)}] {trial.get('name')}")
            try:
                with analysis_slot(lambda s, f, m: log(f"   {m}")):
                    record = analyze_two_view(folder, throwing_side=trial.get("throwingSide", "right"))
                refreshed.add(trial["id"])
                statuses.setdefault(trial["id"], trial.get("analysisStatus") or "Analyzed")
                automatic = outcome_from_two_view(record)
                if automatic:
                    outcomes[trial["id"]] = automatic
                else:
                    outcomes.pop(trial["id"], None)
            except Exception as error:
                failures.append(f"{trial.get('name')} (front, lag): {error}")
                log(f"   front camera FAILED: {error}")
                traceback.print_exc()
    except Exception as error:  # the lag is a refinement; never lose the run over it
        failures.append(f"front picture lag: {error}")
        log(f"   front picture lag FAILED: {error}")
        traceback.print_exc()
    save_statuses(root, statuses, outcomes, refreshed)
    for trial in trials + [t for t in rerun if t not in trials]:
        if statuses.get(trial["id"]) == "Analyzed":
            try:
                generate_insights(root, trial["id"], export_report=False)
            except Exception as error:
                failures.append(f"{trial.get('name')} (insights): {error}")
    log(f"Done: {len(trials) - len(failures)} ok, {len(failures)} problem(s)")
    for message in failures:
        log(f"  {message}")


if __name__ == "__main__":
    main()
