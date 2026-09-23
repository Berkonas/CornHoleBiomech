"""Re-analyse every throw of a library in scratch copies and compare release metrics with the stored results.

The library itself is never modified. Pose is reused from the cached raw pose, so
only tracking/analysis changes show up. Manual bag corrections, events and
flight review are copied so reviewed decisions are respected.

    PYTHONPATH=python .venv/bin/python scripts/regression_check.py \
        --library "~/Documents/Cornhole Pilot Library" --scratch /tmp/regression --output regression.json
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from cornhole_biomech.cli import main as cli_main

KEYS = ("bag_release_angle_deg", "bag_release_speed_m_s", "bag_release_speed_arm_lengths_s", "bag_release_height_m",
        "bag_time_of_flight_seconds", "swing_release_arm_angle_deg", "elbow_angle_deg_at_release",
        "trunk_inclination_deg_at_release")
COPY = ("pose_raw.json", "pose_cache.json", "corrections.json", "events.json", "bag_raw.json", "bag_cache.json",
        "bag_corrections.json", "flight_review.json", "auto_flight.json")


def rerun(analysis: Path, scratch: Path) -> dict:
    manifest = json.loads((analysis / "manifest.json").read_text())
    context = manifest["trial_context"]
    target = scratch / analysis.name
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for name in COPY:
        if (analysis / name).exists():
            shutil.copy2(analysis / name, target / name)
    if (analysis / "sports2d").exists():
        shutil.copytree(analysis / "sports2d", target / "sports2d")
    code = cli_main(["analyze", context["source_video"], "--output", str(target), "--trial-id", context["trial_id"],
                     "--athlete-id", context["athlete_id"], "--view", context["camera_view"],
                     "--throwing-side", context["throwing_side"], "--target-direction", context["target_direction"],
                     "--no-annotated-video"])
    old = json.loads((analysis / "results.json").read_text())
    row = {"throw": analysis.name, "clip": Path(context["source_video"]).name, "exit": code}
    if code == 0:
        new = json.loads((target / "results.json").read_text())
        for key in KEYS:
            row[key] = {"old": old["summaries"].get(key), "new": new["summaries"].get(key)}
        row["release_old"] = old["events"]["release"]["effective_frame"]
        row["release_new"] = new["events"]["release"]["effective_frame"]
        row["grades"] = {k: v["grade"] for k, v in new["quality"]["grades"].items() if k != "rules"}
    shutil.rmtree(target / "sports2d", ignore_errors=True)
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", required=True)
    parser.add_argument("--scratch", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    scratch = Path(args.scratch).expanduser()
    rows = [rerun(m.parent, scratch)
            for m in sorted(Path(args.library).expanduser().glob("Athletes/*/analyses/*/manifest.json"))]
    Path(args.output).write_text(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
