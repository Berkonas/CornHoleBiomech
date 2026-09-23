"""Run the automatic bag tracker on every analysed clip in a library and summarise it.

Without manual ground truth this reports internal-consistency measures only:
acceptance, detected frames, re-acquired frames, measurement noise σ from third
differences (jitter), mask-vs-detection centroid shift, and runtime. Accuracy
against hand-marked centroids comes from `cornhole-biomech bag-benchmark`.

    PYTHONPATH=python .venv/bin/python scripts/benchmark_auto_bag.py \
        --library "~/Documents/Cornhole Pilot Library" --output bag_benchmark.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from cornhole_biomech.auto_bag import auto_track_bag
from cornhole_biomech.bag_filter import smooth_flight, third_difference_sigma
from cornhole_biomech.geometry import robust_segment_length


def _landmark(table: pd.DataFrame, name: str, frames: int) -> np.ndarray:
    rows = table[table["landmark"] == name].set_index("frame")
    out = np.full((frames, 2), np.nan)
    idx = rows.index.to_numpy()
    out[idx] = rows[["filtered_x_px", "filtered_y_px"]].to_numpy(float)
    return out


def run(analysis: Path) -> dict:
    manifest = json.loads((analysis / "manifest.json").read_text())
    context = manifest["trial_context"]
    table = pd.read_csv(analysis / "keypoints.csv")
    frames = int(table["frame"].max()) + 1
    side = context["throwing_side"]
    shoulder, elbow, wrist = (_landmark(table, f"{side}_{j}", frames) for j in ("shoulder", "elbow", "wrist"))
    arm = robust_segment_length(shoulder, elbow) + robust_segment_length(elbow, wrist)
    result = auto_track_bag(context["source_video"], wrist, arm if np.isfinite(arm) else None,
                            context["target_direction"])
    row = {"clip": Path(context["source_video"]).name, "status": result["status"],
           "release_frame": result.get("release_frame"), "first_contact_frame": result.get("first_contact_frame"),
           "runtime_seconds": result.get("runtime_seconds"), "reasons": result.get("reasons")}
    points = result.get("points") or []
    if points:
        f = np.array([p["frame"] for p in points])
        refined = np.array([[p["x"], p["y"]] for p in points])
        detected = [p for p in points if p.get("detection_x") is not None]
        fd = np.array([p["frame"] for p in detected])
        det = np.array([[p["detection_x"], p["detection_y"]] for p in detected])
        shifts = [np.hypot(p["x"] - p["detection_x"], p["y"] - p["detection_y"]) for p in detected
                  if p["source"] == "mask"]
        stab = result.get("stabilized_points") or []
        filt = smooth_flight(stab, result["fps"]) if len(stab) >= 8 else {}
        row.update(tracked_frames=len(points), flight_span_frames=int(f[-1] - f[0] + 1),
                   sources=result.get("centroid_sources"),
                   sigma_detection_px=third_difference_sigma(fd, det) if len(fd) > 6 else None,
                   sigma_refined_px=third_difference_sigma(f, refined) if len(f) > 6 else None,
                   mask_shift_median_px=float(np.median(shifts)) if shifts else None,
                   mask_shift_p90_px=float(np.percentile(shifts, 90)) if shifts else None,
                   filter_outliers=len(filt.get("rejected_outlier_frames", [])),
                   filter_longest_gap=filt.get("longest_gap_frames"),
                   camera_motion_px=result.get("camera_motion_during_flight_px"))
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    analyses = sorted(Path(args.library).expanduser().glob("Athletes/*/analyses/*/manifest.json"))
    rows = []
    for manifest in analyses:
        row = run(manifest.parent)
        rows.append(row)
        print(json.dumps({k: v for k, v in row.items() if k != "reasons"}, default=str))
    Path(args.output).write_text(json.dumps(rows, indent=2, default=str))


if __name__ == "__main__":
    main()
