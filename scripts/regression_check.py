"""Re-analyse every throw of a library in scratch copies and compare release metrics with the stored results.

The library itself is never modified. Pose is reused from the cached raw pose, so
only tracking/analysis changes show up. Manual bag corrections, events and
flight review are copied so reviewed decisions are respected.

Two passes (Task 8b), entirely inside the scratch copies: pass 1 analyses every throw so each
scratch copy's own results.json["scale"] holds its own per-throw board field-of-view calibration;
each recording session (same athlete, same source-clip folder, from
`pipeline.pool_session_camera_files`) is then pooled into a camera.json written into its scratch
copies; pass 2 re-analyses every scratch copy in place (nothing is re-copied from the library) so
`_board_scale` picks up the pooled field of view. The comparison against the library's stored
results.json uses pass 2's output. A session with fewer than 3 measured throws uses the
median of every measured throw in the run instead (source "library_median_gravity_fov", Task 8c).

    PYTHONPATH=python .venv/bin/python scripts/regression_check.py \
        --library "~/Documents/Cornhole Pilot Library" --scratch /tmp/regression --output regression.json
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from cornhole_biomech.cli import main as cli_main
from cornhole_biomech.pipeline import pool_session_camera_files

KEYS = ("bag_release_angle_deg", "bag_release_speed_m_s", "bag_release_speed_arm_lengths_s", "bag_release_height_m",
        "bag_time_of_flight_seconds", "swing_release_arm_angle_deg", "elbow_angle_deg_at_release",
        "trunk_inclination_deg_at_release")
COPY = ("pose_raw.json", "pose_cache.json", "corrections.json", "events.json", "bag_raw.json", "bag_cache.json",
        "bag_corrections.json", "flight_review.json", "auto_flight.json")


def _copy_from_library(analysis: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for name in COPY:
        if (analysis / name).exists():
            shutil.copy2(analysis / name, target / name)
    if (analysis / "sports2d").exists():
        shutil.copytree(analysis / "sports2d", target / "sports2d")


def analyze_scratch(analysis: Path, scratch: Path) -> int:
    """Analyse `scratch/<analysis.name>` (already populated) in place; return the CLI exit code."""
    context = json.loads((analysis / "manifest.json").read_text())["trial_context"]
    target = scratch / analysis.name
    code = cli_main(["analyze", context["source_video"], "--output", str(target), "--trial-id", context["trial_id"],
                     "--athlete-id", context["athlete_id"], "--view", context["camera_view"],
                     "--throwing-side", context["throwing_side"], "--target-direction", context["target_direction"],
                     "--no-annotated-video"])
    shutil.rmtree(target / "sports2d", ignore_errors=True)
    return code


def compare(analysis: Path, scratch: Path, code: int) -> dict:
    target = scratch / analysis.name
    context = json.loads((analysis / "manifest.json").read_text())["trial_context"]
    old = json.loads((analysis / "results.json").read_text())
    row = {"throw": analysis.name, "clip": Path(context["source_video"]).name, "exit": code}
    if code == 0:
        new = json.loads((target / "results.json").read_text())
        for key in KEYS:
            row[key] = {"old": old["summaries"].get(key), "new": new["summaries"].get(key)}
        row["release_old"] = old["events"]["release"]["effective_frame"]
        row["release_new"] = new["events"]["release"]["effective_frame"]
        row["grades"] = {k: v["grade"] for k, v in new["quality"]["grades"].items() if k != "rules"}
        row["scale"] = new.get("scale")
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", required=True)
    parser.add_argument("--scratch", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    scratch = Path(args.scratch).expanduser()
    analyses = [m.parent for m in
               sorted(Path(args.library).expanduser().glob("Athletes/*/analyses/*/manifest.json"))]

    print(f"Pass 1/2: {len(analyses)} throw(s) into scratch copies", flush=True)
    for analysis in analyses:
        _copy_from_library(analysis, scratch / analysis.name)
        analyze_scratch(analysis, scratch)

    targets = [scratch / analysis.name for analysis in analyses]
    print(f"Pooling {len(targets)} scratch throw(s) into recording sessions", flush=True)
    pooled = pool_session_camera_files(targets)
    for key, camera in pooled.items():
        iqr = "—" if camera["iqr_deg"] is None else f"{camera['iqr_deg']:.2f}"
        print(f"  {key}: {camera['status']} field of view from {camera['source']}, {camera['n']} measured "
              f"throw(s), hfov={camera['hfov_deg']}, IQR={iqr}", flush=True)

    print("Pass 2/2: re-analysing the same scratch copies with the pooled session field of view", flush=True)
    rows = [compare(analysis, scratch, analyze_scratch(analysis, scratch)) for analysis in analyses]
    Path(args.output).write_text(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
