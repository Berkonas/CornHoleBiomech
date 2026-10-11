#!/usr/bin/env python3
"""Print one line per two-camera throw of a library: side-camera scale and contact, front-camera result,
miss, heading, sync check and the coach sentence. A quick QA view after analyze_library.py.

  PYTHONPATH=python .venv/bin/python scripts/summarize_two_view.py --library <library> [--athlete "Player 1"]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def _fmt(value, digits: int = 1) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--library", required=True, type=Path)
    parser.add_argument("--athlete")
    args = parser.parse_args()
    root = args.library.expanduser().resolve()
    project = _load(root / "project.json")
    athletes = {a["id"]: a.get("participantCode") for a in project.get("athletes", [])}
    trials = [t for t in project.get("trials", []) if t.get("takeNumber") is not None
              and (args.athlete is None or athletes.get(t["athleteID"]) == args.athlete)]
    trials.sort(key=lambda t: (athletes.get(t["athleteID"]) or "", t.get("takeNumber") or 0, t.get("throwInTake") or 0))
    counts: dict[str, int] = {}
    for trial in trials:
        folder = root / (trial.get("analysisRelativePath") or "")
        results = _load(folder / "results.json")
        two = _load(folder / "two_view.json")
        scale = results.get("scale") or {}
        summaries = results.get("summaries") or {}
        phase = results.get("board_phase") or {}
        touchdown = phase.get("touchdown") or {}
        result = two.get("result") or {}
        miss = two.get("miss") or {}
        heading = two.get("heading") or {}
        check = two.get("sync_check") or {}
        outcome = (trial.get("outcome") or {}).get("score_category")
        counts[result.get("category") or "unknown"] = counts.get(result.get("category") or "unknown", 0) + 1
        print(f"{athletes.get(trial['athleteID'])} T{trial.get('takeNumber')}.{trial.get('throwInTake')} | "
              f"{trial.get('analysisStatus')} | side fov {_fmt(scale.get('hfov_deg'))}° {scale.get('hfov_status')} | "
              f"v {_fmt(summaries.get('bag_release_speed_m_s'), 2)} m/s, D {_fmt(summaries.get('release_to_board_front_m'), 2)} m | "
              f"side contact {'yes' if touchdown else 'no'} | front {two.get('status')} {result.get('category')} "
              f"(agree {result.get('views_agree')}) | miss R{_fmt(miss.get('left_right_in'))} L{_fmt(miss.get('short_long_in'))} in | "
              f"heading {_fmt(heading.get('deg'))}° {heading.get('status')} | sync Δ{check.get('front_frames_difference')} | "
              f"saved outcome {outcome}")
        sentence = (two.get("explanation") or {}).get("sentence") or two.get("reason")
        print(f"    {sentence}")
    print("Results:", counts)


if __name__ == "__main__":
    main()
