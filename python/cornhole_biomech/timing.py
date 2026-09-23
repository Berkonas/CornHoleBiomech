"""Wrist speed and movement timing around release.

Every quantity here is projected 2D, from the 6 Hz zero-phase-filtered pose
(`filtering.py`, cut-off from Winter residual analysis in scripts/residual_analysis.py).

Definitions (x toward the target after reflection, y up; t_release = release frame / fps):

- wrist velocity v_w(t) = d p_wrist / dt, from the filtered wrist in camera-steadied
  pixels (hand-held camera motion removed when the tracker measured it), divided by
  arm length (arm lengths/s) or by the flight-plane scale (m/s).
- wrist speed at release = |v_w(t_release)|.
- wrist direction at release = atan2(v_wy, v_wx), degrees above horizontal toward the target.
- peak wrist speed = max |v_w| between peak backswing and release + 0.1 s;
  its timing = (t_peak − t_release) in ms (negative = before release).
- peak elbow extension velocity = max dθ_elbow/dt (positive = straightening, °/s) in the
  same window; timing relative to release in ms. θ_elbow is the 2D projected
  shoulder–elbow–wrist included angle.
- hand-to-bag speed ratio = bag release speed / wrist speed at release (both in
  arm lengths/s). The bag sits beyond the wrist on the swinging arm, so > 1 is
  expected; a large change between throws means the hand did something different at release.
- launch-direction difference = bag release angle − wrist direction at release (°).

Timing resolution is one frame (16.7 ms at 60 fps); release itself carries the
uncertainty of the release window (reliability.py).
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from .bag_filter import stabilize_points
from .filtering import derivative


def _analysis_axes(v: np.ndarray, target_direction: str) -> np.ndarray:
    """Image velocity (x right, y down) → x toward target, y up."""
    sign = 1.0 if target_direction == "left_to_right" else -1.0
    return np.column_stack([sign * v[:, 0], -v[:, 1]])


def _peak(values: np.ndarray, start: int, stop: int) -> int | None:
    segment = values[max(0, start):min(len(values), stop + 1)]
    if not segment.size or not np.isfinite(segment).any():
        return None
    return int(max(0, start) + np.nanargmax(segment))


def release_timing_metrics(wrist_px: np.ndarray, elbow_angle_deg: np.ndarray, fps: float,
                           events: dict[str, int | None], arm_length_px: float, target_direction: str,
                           camera_to_release: dict[str, Any] | None = None,
                           pixels_per_meter: float | None = None,
                           bag_release_speed_arm_lengths_s: float | None = None,
                           bag_release_angle_deg: float | None = None) -> dict[str, Any]:
    """Wrist and elbow timing variables plus per-frame wrist speed for plotting."""
    empty_keys = ("wrist_speed_at_release_arm_lengths_s", "wrist_speed_at_release_m_s",
                  "wrist_direction_at_release_deg", "wrist_peak_speed_arm_lengths_s", "wrist_peak_speed_m_s",
                  "wrist_peak_speed_time_rel_release_ms", "elbow_peak_extension_velocity_deg_s",
                  "elbow_peak_extension_time_rel_release_ms", "hand_to_bag_speed_ratio",
                  "launch_direction_difference_deg")
    out: dict[str, Any] = {k: None for k in empty_keys}
    out.update(wrist_speed_series_arm_lengths_s=None, peak_wrist_speed_frame=None, peak_elbow_extension_frame=None)
    release, backswing = events.get("release"), events.get("peak_backswing")
    if release is None or fps <= 0 or not arm_length_px or arm_length_px <= 0:
        return out
    wrist = stabilize_points(wrist_px, camera_to_release) if camera_to_release else np.asarray(wrist_px, float)
    velocity = _analysis_axes(derivative(wrist, fps), target_direction)
    speed = np.linalg.norm(velocity, axis=1) / arm_length_px
    out["wrist_speed_series_arm_lengths_s"] = [None if not math.isfinite(v) else float(v) for v in speed]
    start = backswing if backswing is not None and backswing < release else release - int(round(0.6 * fps))
    stop = release + int(round(0.1 * fps))
    if 0 <= release < len(speed) and math.isfinite(speed[release]):
        out["wrist_speed_at_release_arm_lengths_s"] = float(speed[release])
        out["wrist_direction_at_release_deg"] = float(math.degrees(math.atan2(velocity[release, 1], velocity[release, 0])))
        if pixels_per_meter:
            out["wrist_speed_at_release_m_s"] = float(speed[release] * arm_length_px / pixels_per_meter)
        if bag_release_speed_arm_lengths_s and speed[release] > 1e-6:
            out["hand_to_bag_speed_ratio"] = float(bag_release_speed_arm_lengths_s / speed[release])
        if bag_release_angle_deg is not None:
            out["launch_direction_difference_deg"] = float(bag_release_angle_deg - out["wrist_direction_at_release_deg"])
    peak = _peak(speed, start, stop)
    if peak is not None:
        out.update(peak_wrist_speed_frame=peak, wrist_peak_speed_arm_lengths_s=float(speed[peak]),
                   wrist_peak_speed_time_rel_release_ms=1000.0 * (peak - release) / fps)
        if pixels_per_meter:
            out["wrist_peak_speed_m_s"] = float(speed[peak] * arm_length_px / pixels_per_meter)
    extension = derivative(np.asarray(elbow_angle_deg, float), fps)
    peak_elbow = _peak(extension, start, stop)
    if peak_elbow is not None and extension[peak_elbow] > 0:
        out.update(peak_elbow_extension_frame=peak_elbow,
                   elbow_peak_extension_velocity_deg_s=float(extension[peak_elbow]),
                   elbow_peak_extension_time_rel_release_ms=1000.0 * (peak_elbow - release) / fps)
    return out
