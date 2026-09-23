"""Everything the app needs to replay one measured throw over its video (replay.json).

Paths are stored once, in the release frame's pixels (camera motion removed), and
`release_to_frame[f]` maps them onto frame f of the raw video, so the whole throw
can be drawn in place on a hand-held clip at any moment. For a fixed camera (or a
manually tracked bag) the transforms are omitted and paths are raw pixels.

Layers, in visual priority:
- measured: bag centres actually detected (solid);
- filtered: the Kalman/RTS estimate (for the smooth line; gaps stay gaps);
- model: the drag-free ballistic fit (dashed, secondary; never presented as observed);
- after_contact: the measured slide from first contact to rest.
Events carry a frame, a position when the bag defines them, and the values a coach
reads at that moment. Nothing is extrapolated beyond what was measured.
"""
from __future__ import annotations

from typing import Any

import numpy as np

REPLAY_REVISION = "replay_v1"


def _inverse_transforms(camera_to_release: dict[str, Any] | None) -> dict[str, list[list[float]]] | None:
    if not camera_to_release:
        return None
    out = {}
    for key, matrix in camera_to_release.items():
        M = np.vstack([np.asarray(matrix, float), [0, 0, 1]])
        out[key] = np.round(np.linalg.inv(M)[:2], 6).tolist()
    return out


def _point(frame: int | None, series: dict[int, tuple[float, float]]) -> dict[str, Any] | None:
    if frame is None or frame not in series:
        return None
    x, y = series[frame]
    return {"x": float(x), "y": float(y)}


def build_replay(*, fps: float, frame_count: int, width: int, height: int, camera_to_release: dict[str, Any] | None,
                 measured: np.ndarray, filtered: dict[str, Any] | None, model_check: dict[str, Any] | None,
                 after_contact: dict[str, Any] | None, events: dict[str, int | None], summaries: dict[str, Any],
                 coach_metrics: dict[str, Any], grades: dict[str, Any], release_window: tuple[int, int] | None) -> dict[str, Any]:
    """Assemble replay.json from the analysis products (all bag positions in release-frame pixels)."""
    measured_rows = [{"frame": int(f), "x": float(measured[f, 0]), "y": float(measured[f, 1])}
                     for f in range(len(measured)) if np.isfinite(measured[f]).all()]
    filtered_rows = [{"frame": r["frame"], "x": r["x"], "y": r["y"], "status": r["status"]}
                     for r in (filtered or {}).get("frames", []) if r.get("x") is not None]
    model_rows = list((model_check or {}).get("curve") or [])
    slide = [{"frame": p["frame"], "x": p.get("x_release_frame", p["x"]), "y": p.get("y_release_frame", p["y"])}
             for p in (after_contact or {}).get("path", [])]
    positions = {r["frame"]: (r["x"], r["y"]) for r in measured_rows}
    positions.update({r["frame"]: (r["x"], r["y"]) for r in filtered_rows if r["frame"] not in positions})
    release, contact = events.get("release"), events.get("first_contact")
    apex = (model_check or {}).get("apex_frame")
    rest = (after_contact or {}).get("rest")

    def values(*keys: str) -> list[dict[str, Any]]:
        rows = []
        for key in keys:
            metric = coach_metrics.get(key) or {}
            raw = summaries.get(key)
            rows.append({"key": key, "label": metric.get("label", key), "unit": metric.get("unit", ""),
                         "value": metric.get("value") if metric else raw, "status": metric.get("status", "reported")})
        return rows

    event_rows = {
        "motion_start": {"frame": events.get("motion_start"), "label": "Movement starts"},
        "peak_backswing": {"frame": events.get("peak_backswing"), "label": "Top of backswing",
                           "values": values("swing_backswing_angle_deg")},
        "peak_wrist_speed": {"frame": events.get("peak_wrist_speed"), "label": "Peak wrist speed",
                             "values": values("wrist_peak_speed_arm_lengths_s", "wrist_peak_speed_time_rel_release_ms")},
        "peak_elbow_extension": {"frame": events.get("peak_elbow_extension"), "label": "Fastest elbow extension",
                                 "values": values("elbow_peak_extension_velocity_deg_s")},
        "release": {"frame": release, "label": "Release", "position": _point(release, positions),
                    "window": list(release_window) if release_window else None,
                    "values": values("bag_release_speed_m_s", "bag_release_angle_deg", "bag_release_height_m",
                                     "wrist_speed_at_release_arm_lengths_s", "elbow_angle_deg_at_release",
                                     "swing_release_arm_angle_deg", "trunk_inclination_deg_at_release")},
        "apex": {"frame": apex, "label": "Apex", "position": _point(apex, positions),
                 "values": [{"key": "bag_trajectory_apex_rise_m", "label": "Rise above release", "unit": "m",
                             "value": summaries.get("bag_trajectory_apex_rise_m"), "status": "reported"}]},
        "first_contact": {"frame": contact, "label": "First contact", "position": _point(contact, positions),
                          "values": [{"key": "bag_time_of_flight_seconds", "label": "Flight time", "unit": "s",
                                      "value": summaries.get("bag_time_of_flight_seconds"), "status": "reported"}]},
        "final_rest": {"frame": rest["frame"] if rest else None, "label": "Final rest",
                       "position": {"x": rest["x_release_frame"], "y": rest["y_release_frame"]} if rest else None,
                       "status": (after_contact or {}).get("status"), "note": (after_contact or {}).get("note")},
    }
    return {
        "schema_version": 1, "revision": REPLAY_REVISION, "fps": fps, "frame_count": frame_count,
        "width": width, "height": height,
        "coordinates": "release_frame_pixels" if camera_to_release else "raw_video_pixels",
        "reference_frame": release,
        "release_to_frame": _inverse_transforms(camera_to_release),
        "measured": measured_rows, "filtered": filtered_rows, "model": model_rows, "after_contact": slide,
        "model_note": (model_check or {}).get("interpretation"),
        "model_rmse_px": (model_check or {}).get("in_sample_rmse_px"),
        "events": {k: v for k, v in event_rows.items() if v.get("frame") is not None},
        "grades": {k: v.get("grade") for k, v in grades.items() if isinstance(v, dict) and "grade" in v},
    }
