"""Winter residual analysis to choose a low-pass cutoff from real landmark data.

For each cutoff fc, residual R(fc) = RMS(raw − zero-phase Butterworth(raw)).
Above the signal band R falls linearly with fc (it is mostly noise). A line fitted to
that high-frequency tail, extrapolated to fc = 0, gives the noise level; the chosen
cutoff is where R(fc) first drops to that level (Winter, Biomechanics and Motor
Control of Human Movement, 4th ed., §3.4.4.3).

Usage:
    python scripts/residual_analysis.py ANALYSIS_DIR [ANALYSIS_DIR ...] \
        --landmarks right_wrist right_elbow right_shoulder [--tail 12 20]
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfiltfilt


def longest_run(values: np.ndarray) -> np.ndarray:
    finite = np.isfinite(values)
    best, start = (0, 0), None
    for i, ok in enumerate(np.append(finite, False)):
        if ok and start is None:
            start = i
        elif not ok and start is not None:
            best = max(best, (start, i), key=lambda r: r[1] - r[0])
            start = None
    return values[best[0]:best[1]]


def residuals(signal: np.ndarray, fps: float, cutoffs: np.ndarray) -> np.ndarray:
    out = []
    for fc in cutoffs:
        sos = butter(4, fc, fs=fps, output="sos")
        out.append(float(np.sqrt(np.mean((signal - sosfiltfilt(sos, signal)) ** 2))))
    return np.asarray(out)


def optimal_cutoff(cutoffs: np.ndarray, r: np.ndarray, tail: tuple[float, float]) -> float | None:
    mask = (cutoffs >= tail[0]) & (cutoffs <= tail[1])
    slope, intercept = np.polyfit(cutoffs[mask], r[mask], 1)
    below = np.flatnonzero(r <= intercept)
    return float(cutoffs[below[0]]) if below.size and intercept > 0 else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("analysis", nargs="+", type=Path)
    parser.add_argument("--landmarks", nargs="+", default=["right_wrist", "right_elbow", "right_shoulder"])
    parser.add_argument("--tail", nargs=2, type=float, default=(12.0, 20.0), help="Hz range treated as noise")
    args = parser.parse_args()
    report = []
    for directory in args.analysis:
        fps = json.loads((directory / "manifest.json").read_text())["source_video"]["fps"]
        cutoffs = np.arange(1.0, min(25.0, 0.45 * fps), 0.5)
        series: dict[tuple[str, str], list[float]] = {}
        with (directory / "keypoints.csv").open(newline="") as stream:
            for row in csv.DictReader(stream):
                if row["landmark"] in args.landmarks:
                    for axis in ("x", "y"):
                        cell = row[f"effective_{axis}_px"]   # confidence-masked, unfiltered
                        series.setdefault((row["landmark"], axis), []).append(float(cell) if cell else np.nan)
        for (landmark, axis), values in sorted(series.items()):
            signal = longest_run(np.asarray(values, float))
            if len(signal) < 30:
                continue
            r = residuals(signal, fps, cutoffs)
            fc = optimal_cutoff(cutoffs, r, tuple(args.tail))
            report.append({"analysis": directory.name, "landmark": landmark, "axis": axis,
                           "samples": len(signal), "fps": fps, "optimal_cutoff_hz": fc})
            print(f"{directory.name:>14} {landmark:>15} {axis}  n={len(signal):4d}  optimal cutoff ≈ {fc} Hz")
    cut = [r["optimal_cutoff_hz"] for r in report if r["optimal_cutoff_hz"] is not None]
    if cut:
        print(f"median {np.median(cut):.1f} Hz, range {min(cut):.1f}–{max(cut):.1f} Hz over {len(cut)} signals")


if __name__ == "__main__":
    main()
