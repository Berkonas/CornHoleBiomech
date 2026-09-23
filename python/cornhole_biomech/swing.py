"""Throwing-arm swing (pendulum) metrics in the camera's side view.

Arm angle φ is the direction of the shoulder→wrist line measured from straight
down, positive toward the target: 0° hangs straight down, +90° points horizontally
at the target, −90° points straight back, 180° is overhead. It is a projected 2D
angle of the whole arm (not the shoulder joint angle relative to the trunk).

Pendulum drive ratio: a uniform rigid arm of length L swinging freely about the
shoulder from amplitude A reaches ω_passive = √(3g(1 − cos A)/L) at the bottom
(energy: ½·(mL²/3)·ω² = m·g·(L/2)·(1 − cos A)). The ratio of measured to passive
bottom speed shows how much the athlete drives the swing beyond gravity (≈1:
pendulum-like; >1: active). It needs L in metres, so it requires a scale.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from .bag import GRAVITY_M_S2
from .filtering import derivative

SWING_METRICS = {
    "swing_backswing_angle_deg": "Backswing arm angle (°)",
    "swing_release_arm_angle_deg": "Arm angle at release (°)",
    "swing_peak_angular_velocity_deg_s": "Peak arm angular speed (°/s)",
    "swing_angular_velocity_at_release_deg_s": "Arm angular speed at release (°/s)",
    "swing_hand_speed_at_release_arm_lengths_s": "Hand speed at release (arm lengths/s)",
    "swing_hand_speed_at_release_m_s": "Hand speed at release (m/s)",
    "swing_total_hand_speed_at_release_m_s": "Hand speed incl. body movement (m/s)",
    "swing_backswing_duration_s": "Backswing duration (s)",
    "swing_forward_duration_s": "Forward-swing duration (s)",
    "swing_tempo_ratio": "Tempo (backswing ÷ forward swing)",
    "swing_pendulum_drive_ratio": "Pendulum drive ratio (measured ÷ passive)",
}


def arm_angle_deg(shoulder: np.ndarray, wrist: np.ndarray, target_direction: str) -> np.ndarray:
    """φ per frame in degrees, unwrapped within finite runs (see module docstring)."""
    sign = 1.0 if target_direction == "left_to_right" else -1.0
    d = np.asarray(wrist, float) - np.asarray(shoulder, float)
    forward, down = sign * d[:, 0], d[:, 1]            # image y points down
    phi = np.degrees(np.arctan2(forward, down))
    finite = np.isfinite(phi)
    if finite.sum() > 1:
        idx = np.flatnonzero(finite)
        phi[idx] = np.degrees(np.unwrap(np.radians(phi[idx])))
    return phi


def _backswing_start(omega: np.ndarray, back: int, fps: float, window_s: float = 2.0) -> int | None:
    """Last frame before the backswing peak where the arm was nearly at rest.

    Uses the arm's own angular speed (< 15 % of the backswing's peak), so setup
    fidgeting or walking earlier in the clip does not inflate the backswing time.
    """
    lo = max(0, back - int(window_s * fps))
    segment = np.abs(omega[lo:back])
    if not np.isfinite(segment).any():
        return None
    peak = np.nanmax(segment)
    quiet = np.flatnonzero(np.nan_to_num(segment, nan=np.inf) < 0.15 * peak)
    return int(lo + quiet[-1]) if quiet.size else None


def _at(values: np.ndarray, frame: int | None) -> float | None:
    if frame is None or not 0 <= frame < len(values) or not np.isfinite(values[frame]):
        return None
    return float(values[frame])


def swing_metrics(shoulder: np.ndarray, wrist: np.ndarray, fps: float, target_direction: str,
                  events: dict[str, int | None], arm_length_px: float | None,
                  pixels_per_meter: float | None = None) -> dict[str, Any]:
    """Swing descriptors; any metric whose inputs are missing stays None."""
    phi = arm_angle_deg(shoulder, wrist, target_direction)
    omega = derivative(phi, fps)                        # deg/s, finite runs only
    start, back, release, follow = (events.get(k) for k in ("motion_start", "peak_backswing", "release", "peak_follow_through"))
    out: dict[str, Any] = dict.fromkeys(SWING_METRICS)
    out["swing_arm_angle_curve_deg"] = phi
    out["swing_arm_angular_velocity_curve_deg_s"] = omega
    if back is not None and release is not None and back < release:
        begin = _backswing_start(omega, back, fps)
        window = phi[begin if begin is not None else back: release + 1]
        out["swing_backswing_angle_deg"] = float(np.nanmin(window)) if np.isfinite(window).any() else None
        forward_omega = omega[back:release + 1]
        if np.isfinite(forward_omega).any():
            out["swing_peak_angular_velocity_deg_s"] = float(np.nanmax(forward_omega))
        out["swing_forward_duration_s"] = (release - back) / fps
        if begin is not None:
            out["swing_backswing_duration_s"] = (back - begin) / fps
            out["swing_tempo_ratio"] = (back - begin) / (release - back)
            out["swing_backswing_start_frame"] = begin
    out["swing_release_arm_angle_deg"] = _at(phi, release) if release is not None and back is not None else None
    w = _at(omega, release)
    out["swing_angular_velocity_at_release_deg_s"] = w
    if release is not None and arm_length_px and arm_length_px > 0:
        v = derivative(np.asarray(wrist, float) - np.asarray(shoulder, float), fps)   # shoulder-relative hand velocity
        if 0 <= release < len(v) and np.isfinite(v[release]).all():
            speed_px = float(np.hypot(*v[release]))
            out["swing_hand_speed_at_release_arm_lengths_s"] = speed_px / arm_length_px
            if pixels_per_meter and pixels_per_meter > 0:
                out["swing_hand_speed_at_release_m_s"] = speed_px / pixels_per_meter
                total = derivative(np.asarray(wrist, float), fps)       # includes trunk/step translation
                if np.isfinite(total[release]).all():
                    out["swing_total_hand_speed_at_release_m_s"] = float(np.hypot(*total[release])) / pixels_per_meter
    if (pixels_per_meter and arm_length_px and out["swing_backswing_angle_deg"] is not None
            and back is not None and release is not None):
        # Bottom of the swing: first frame after the backswing where the arm passes vertical.
        crossing = [f for f in range(back, release + 1) if np.isfinite(phi[f]) and phi[f] >= 0]
        amplitude = np.radians(abs(out["swing_backswing_angle_deg"]))
        length_m = arm_length_px / pixels_per_meter
        if crossing and amplitude > 0 and np.isfinite(omega[crossing[0]]):
            passive = np.sqrt(3 * GRAVITY_M_S2 * (1 - np.cos(amplitude)) / length_m)
            out["swing_pendulum_drive_ratio"] = float(np.radians(omega[crossing[0]]) / passive)
    return out
