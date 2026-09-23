"""Bag-tracking accuracy against hand-marked centroids, stratified by flight phase.

Workflow (docs/BAG_TRACKING_VALIDATION.md):
1. `cornhole-biomech bag-annotation-frames` picks frames in each phase of every
   clip's automatic flight and exports them blinded (no overlays). Phases:
   in_hand, release, early_flight (high velocity), apex, descent, near_board,
   landing. The phase plan is written to a separate file that raters don't open.
2. Raters mark the bag centre in tools/annotator.html (bag-only mode), or
   "not visible" when occluded, and enter release / first-contact frames.
3. `cornhole-biomech bag-benchmark` compares every available tracker output
   ("detection" blob, "mask" silhouette, "filtered" Kalman/RTS) with the marks.

Metrics per tracker (e_i = √((x_auto − x_manual)² + (y_auto − y_manual)²)):
- MAE = (1/N) Σ e_i, RMSE = √((1/N) Σ e_i²), median, 95th percentile, bias;
- success rate: share of visible reference frames with an estimate within
  `success_radius_px` (default: the bag's own radius, half a bag length), over
  all marked frames and over marked frames inside the tracker's flight span;
- per-phase MAE/RMSE;
- over the whole flight (not only annotated frames): tracked-frame share,
  lost-track events (runs of ≥1 frame without an estimate) and the longest run;
- release-frame and first-contact-frame error (frames and ms);
- landing position error: estimate vs. mark at the marked frame nearest (±2) the rater's first contact;
- runtime and processing speed (frames/s).
Errors in cm are reported only with an explicit flight-plane scale, labelled as
valid for the plane of flight only (a single camera has no depth).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from .validation import _stats, annotation_points, event_errors

PHASES = ("in_hand", "release", "early_flight", "apex", "descent", "near_board", "landing")


def bag_phase_frames(release: int, contact: int | None, last_tracked: int, apex: int | None,
                     fps: float, frame_count: int) -> dict[str, list[int]]:
    """Candidate frames per flight phase from an automatic flight (all clipped to the clip)."""
    end = contact if contact is not None else last_tracked
    step = max(1, int(round(0.05 * fps)))
    if apex is None or not release < apex < end:
        apex = (release + end) // 2
    ranges = {
        "in_hand": range(release - 6 * step, release - 1),
        "release": range(release - 1, release + 2),
        "early_flight": range(release + 2, release + 4 * step),
        "apex": range(apex - step, apex + step + 1),
        "descent": range(apex + 2 * step, max(apex + 2 * step + 1, end - 3 * step)),
        "near_board": range(end - 3 * step, end - 1),
        "landing": range(end, end + 4) if contact is not None else range(0),
    }
    return {name: [f for f in r if 0 <= f < frame_count] for name, r in ranges.items()}


def select_bag_frames(phases: dict[str, list[int]], per_phase: int = 2, seed: int = 20260923,
                      always: dict[int, str] | None = None) -> list[dict[str, Any]]:
    """Deterministic, evenly spread pick of `per_phase` frames from each phase.

    `always` frames (e.g. the automatic release and first-contact frames) are
    included in addition, so release timing and landing position can be scored.
    """
    rng = np.random.default_rng(seed)
    chosen: dict[int, str] = dict(always or {})
    for name in PHASES:
        pool = [f for f in phases.get(name, []) if f not in chosen]
        if not pool:
            continue
        if len(pool) <= per_phase:
            picks = pool
        else:
            edges = np.linspace(0, len(pool), per_phase + 1).astype(int)
            picks = [pool[int(rng.integers(a, max(a + 1, b)))] for a, b in zip(edges[:-1], edges[1:])]
        for f in picks:
            chosen[int(f)] = name
    return [{"frame": f, "phase": chosen[f]} for f in sorted(chosen)]


def _runs_without_estimate(track: dict[int, tuple[float, float] | None], first: int, last: int) -> list[int]:
    runs, current = [], 0
    for f in range(first, last + 1):
        if track.get(f) is None:
            current += 1
        elif current:
            runs.append(current); current = 0
    if current:
        runs.append(current)
    return runs


def tracker_report(reference: dict[int, tuple[float, float]], hidden: set[int], phase_of: dict[int, str],
                   track: dict[int, tuple[float, float] | None], flight_span: tuple[int, int] | None,
                   success_radius_px: float, pixels_per_meter: float | None = None) -> dict[str, Any]:
    """Accuracy of one tracker's per-frame bag centres against one rater's marks."""
    errors, dx, dy, by_phase = [], [], [], {}
    missing = 0
    for f, (rx, ry) in sorted(reference.items()):
        est = track.get(f)
        if est is None:
            missing += 1
            continue
        ex, ey = est[0] - rx, est[1] - ry
        e = float(np.hypot(ex, ey))
        errors.append(e); dx.append(ex); dy.append(ey)
        by_phase.setdefault(phase_of.get(f, "unassigned"), []).append(e)
    stats = _stats(errors)
    n_ref = len(reference)
    within = sum(1 for e in errors if e <= success_radius_px)
    in_flight = {f for f in reference if flight_span and flight_span[0] <= f <= flight_span[1]}
    in_flight_ok = sum(1 for f in in_flight if track.get(f) is not None
                       and np.hypot(track[f][0] - reference[f][0], track[f][1] - reference[f][1]) <= success_radius_px)
    out: dict[str, Any] = {
        "n_reference_visible": n_ref, "n_reference_not_visible": len(hidden), "n_compared": len(errors),
        "n_no_estimate": missing,
        "mae_px": stats["mean"], "rmse_px": stats["rmse"], "median_px": stats["median"],
        "p95_px": stats["p95"], "max_px": stats["max"],
        "bias_x_px": float(np.mean(dx)) if dx else None, "bias_y_px": float(np.mean(dy)) if dy else None,
        "success_radius_px": success_radius_px,
        "success_rate": within / n_ref if n_ref else None,
        # Only frames inside the tracker's own flight span (the flight tracker does not claim the in-hand phase).
        "success_rate_in_flight": in_flight_ok / len(in_flight) if in_flight else None,
        "by_phase": {name: {"n": len(v), "mae_px": float(np.mean(v)), "rmse_px": float(np.sqrt(np.mean(np.square(v))))}
                     for name, v in by_phase.items()},
        # Estimates on frames the rater marked "not visible" (e.g. occluded by the hand).
        "estimates_on_not_visible_frames": sum(1 for f in hidden if track.get(f) is not None),
    }
    if flight_span:
        first, last = flight_span
        runs = _runs_without_estimate(track, first, last)
        span = last - first + 1
        out.update(flight_frames=span, tracked_share=1 - sum(runs) / span, lost_track_events=len(runs),
                   longest_missing_frames=max(runs, default=0))
    if pixels_per_meter:
        out["mae_cm_flight_plane"] = None if stats["mean"] is None else 100 * stats["mean"] / pixels_per_meter
        out["rmse_cm_flight_plane"] = None if stats["rmse"] is None else 100 * stats["rmse"] / pixels_per_meter
        out["cm_note"] = "Scale valid in the bag's flight plane only; not a 3D error."
    return out


def tracks_from_analysis(analysis: str | Path) -> tuple[dict[str, dict[int, tuple[float, float] | None]], dict[str, Any]]:
    """Per-tracker raw-pixel bag centres from an analysis folder, plus flight metadata."""
    folder = Path(analysis)
    auto = json.loads((folder / "auto_flight.json").read_text()) if (folder / "auto_flight.json").exists() else {}
    tracks: dict[str, dict[int, tuple[float, float] | None]] = {}
    points = auto.get("points") or []
    if points and "detection_x" in points[0]:
        tracks["detection"] = {p["frame"]: (p["detection_x"], p["detection_y"]) for p in points
                               if p.get("detection_x") is not None}
        tracks["mask"] = {p["frame"]: (p["x"], p["y"]) for p in points}
    elif points:
        tracks["detection"] = {p["frame"]: (p["x"], p["y"]) for p in points}
    bag_track = folder / "bag_track.json"
    if bag_track.exists():
        samples = json.loads(bag_track.read_text()).get("samples", [])
        tracks["filtered"] = {s["frame_index"]: (s["filtered_centroid"]["x"], s["filtered_centroid"]["y"])
                              for s in samples if s.get("filtered_centroid")}
        tracks["effective"] = {s["frame_index"]: (s["effective_centroid"]["x"], s["effective_centroid"]["y"])
                               for s in samples if s.get("effective_centroid")}
    meta = {"release_frame": auto.get("release_frame"), "first_contact_frame": auto.get("first_contact_frame"),
            "last_tracked_frame": auto.get("last_tracked_frame"), "fps": auto.get("fps"),
            "runtime_seconds": auto.get("runtime_seconds"), "frames_processed": auto.get("frames_processed"),
            "median_area_px": float(np.median([p["area_px"] for p in points if p.get("area_px")]))
            if any(p.get("area_px") for p in points) else None}
    return tracks, meta


def bag_benchmark(annotation_path: str | Path, analysis: str | Path, plan_path: str | Path | None = None,
                  success_radius_px: float | None = None, pixels_per_meter: float | None = None) -> dict[str, Any]:
    """Compare every tracker output in `analysis` with one rater's bag marks."""
    annotation = json.loads(Path(annotation_path).read_text())
    points, hidden_keys = annotation_points(annotation)
    reference = {f: p for (f, name), p in points.items() if name == "bag"}
    hidden = {f for (f, name) in hidden_keys if name == "bag"}
    plan = json.loads(Path(plan_path).read_text()) if plan_path else {"frames": []}
    phase_of = {int(r["frame"]): r["phase"] for r in plan.get("frames", [])}
    tracks, meta = tracks_from_analysis(analysis)
    fps = float(meta.get("fps") or annotation.get("fps") or 0) or None
    if success_radius_px is None:
        # Half a bag length (the bag's own radius): an estimate inside the bag counts as tracked.
        area = meta.get("median_area_px")
        success_radius_px = float(np.sqrt(area / np.pi)) if area else 10.0
    release, contact = meta.get("release_frame"), meta.get("first_contact_frame") or meta.get("last_tracked_frame")
    span = (release, contact) if release is not None and contact is not None else None
    report: dict[str, Any] = {
        "schema_version": 1, "rater": annotation.get("rater"),
        "criterion": "blinded_manual_annotation_not_ground_truth",
        "success_radius_px": success_radius_px, "trackers": {},
        "runtime_seconds": meta.get("runtime_seconds"),
        "processing_fps": (meta["frames_processed"] / meta["runtime_seconds"])
        if meta.get("runtime_seconds") and meta.get("frames_processed") else None,
    }
    for name, track in tracks.items():
        report["trackers"][name] = tracker_report(reference, hidden, phase_of, track, span,
                                                  success_radius_px, pixels_per_meter)
    ref_events = annotation.get("events") or {}
    if fps and ref_events:
        report["events"] = event_errors(ref_events, {"release": meta.get("release_frame"),
                                                     "first_contact": meta.get("first_contact_frame")}, fps)
        contact_ref = ref_events.get("first_contact")
        near = [f for f in reference if contact_ref is not None and abs(f - contact_ref) <= 2]
        if near:
            # Bag position at first contact: the marked frame closest to the rater's contact frame.
            f = min(near, key=lambda g: (abs(g - contact_ref), g))
            report["landing_position_frame"] = f
            report["landing_position_error_px"] = {
                name: None if track.get(f) is None else float(np.hypot(track[f][0] - reference[f][0],
                                                                       track[f][1] - reference[f][1]))
                for name, track in tracks.items()}
    return report


def _weighted(pairs) -> float | None:
    usable = [(v, r["n_reference_visible"]) for v, r in pairs if v is not None]
    total = sum(n for _, n in usable)
    return sum(v * n for v, n in usable) / total if total else None


def pooled(reports: list[dict[str, Any]]) -> dict[str, Any]:
    """Pool several clips' reports: frame-weighted MAE/RMSE and summed counts per tracker."""
    out: dict[str, Any] = {}
    for name in sorted({t for r in reports for t in r["trackers"]}):
        rows = [r["trackers"][name] for r in reports if name in r["trackers"] and r["trackers"][name]["n_compared"]]
        n = sum(r["n_compared"] for r in rows)
        if not n:
            continue
        out[name] = {
            "clips": len(rows), "n_compared": n,
            "mae_px": sum(r["mae_px"] * r["n_compared"] for r in rows) / n,
            "rmse_px": float(np.sqrt(sum(r["rmse_px"] ** 2 * r["n_compared"] for r in rows) / n)),
            "success_rate": sum(r["success_rate"] * r["n_reference_visible"] for r in rows)
            / max(1, sum(r["n_reference_visible"] for r in rows)),
            "success_rate_in_flight": _weighted([(r.get("success_rate_in_flight"), r) for r in rows]),
            "lost_track_events": sum(r.get("lost_track_events", 0) for r in rows),
            "longest_missing_frames": max((r.get("longest_missing_frames", 0) for r in rows), default=0),
        }
    return out
