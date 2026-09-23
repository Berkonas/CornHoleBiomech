"""Level-2 flight model: drag-free ballistic fit and a measurement of how well it holds.

Model, in one fixed image frame (camera motion removed), image y down:

    x(t) = x0 + vx0·t
    y(t) = y0 − vy0·t + ½·a·t²          a = g · (pixels per metre) in the flight plane

Reported for every reviewed flight:

- in-sample RMSE: sqrt( (1/N) Σ [(x_i − x̂_i)² + (y_i − ŷ_i)²] ) over all flight samples;
- out-of-sample RMSE: fit the first half of the flight, predict the second half.
  This is the honest test of whether the model can be used to predict landing.
- horizontal-to-vertical acceleration ratio from a free quadratic in x. A
  drag-free projectile viewed square-on has 0. A negative value means the bag
  slows horizontally in the image, which drag OR perspective (the bag moving
  away from the camera) both produce; one camera cannot separate them.

No drag coefficient is fitted. On the 20 accepted pilot flights (docs/SECOND_PASS_AUDIT.md)
a fitted quadratic-drag model did not reduce out-of-sample error consistently
(median 24.5 px vs 24.9 px for a quadratic-x fit and 31 px for pure ballistic),
and its horizontal deceleration is confounded with perspective. The model is
therefore for description (apex, residuals) and short-range prediction only.
"""
from __future__ import annotations

from typing import Any

import numpy as np


def _fit_ballistic(t: np.ndarray, x: np.ndarray, y: np.ndarray):
    cx = np.polyfit(t, x, 1)
    cy = np.polyfit(t, y, 2)
    return cx, cy


def _rmse(t, x, y, cx, cy) -> float:
    return float(np.sqrt(np.mean((x - np.polyval(cx, t)) ** 2 + (y - np.polyval(cy, t)) ** 2)))


def ballistic_model_check(points: np.ndarray, release_frame: int | None, contact_frame: int | None,
                          fps: float, pixels_per_meter: float | None = None,
                          arm_length_px: float | None = None, minimum_points: int = 12) -> dict[str, Any]:
    """Fit and test the drag-free model on samples strictly between release and first contact."""
    result: dict[str, Any] = {
        "status": "insufficient_data", "model": "ballistic_drag_free_image_plane",
        "sample_count": 0, "in_sample_rmse_px": None, "out_of_sample_rmse_px": None,
        "in_sample_rmse_arm_lengths": None, "out_of_sample_rmse_arm_lengths": None,
        "in_sample_rmse_m": None, "out_of_sample_rmse_m": None,
        "horizontal_to_vertical_acceleration": None, "vertical_acceleration_px_s2": None,
        "apex_frame": None, "apex_rise_px": None, "apex_rise_m": None, "curve": [],
        "interpretation": None,
    }
    if release_frame is None or fps <= 0:
        return result
    p = np.asarray(points, float)
    end = contact_frame if contact_frame is not None else len(p)
    frames = np.arange(release_frame + 1, min(end, len(p)))
    ok = np.isfinite(p[frames]).all(axis=1) if len(frames) else np.zeros(0, bool)
    frames = frames[ok]
    result["sample_count"] = int(len(frames))
    if len(frames) < minimum_points:
        return result
    t = (frames - release_frame) / fps
    x, y = p[frames, 0], p[frames, 1]
    cx, cy = _fit_ballistic(t, x, y)
    in_rmse = _rmse(t, x, y, cx, cy)
    half = len(frames) // 2
    cx_h, cy_h = _fit_ballistic(t[:half], x[:half], y[:half])
    out_rmse = _rmse(t[half:], x[half:], y[half:], cx_h, cy_h)
    a_y = 2.0 * float(cy[0])
    a_x = 2.0 * float(np.polyfit(t, x, 2)[0])
    result.update(status="fitted", in_sample_rmse_px=in_rmse, out_of_sample_rmse_px=out_rmse,
                  vertical_acceleration_px_s2=a_y,
                  horizontal_to_vertical_acceleration=(a_x / a_y) if a_y > 0 else None)
    if arm_length_px and arm_length_px > 0:
        result["in_sample_rmse_arm_lengths"] = in_rmse / arm_length_px
        result["out_of_sample_rmse_arm_lengths"] = out_rmse / arm_length_px
    if pixels_per_meter and pixels_per_meter > 0:
        result["in_sample_rmse_m"] = in_rmse / pixels_per_meter
        result["out_of_sample_rmse_m"] = out_rmse / pixels_per_meter
    # Apex of the fitted vertical motion, only if it lies inside the observed flight.
    if a_y > 0:
        t_apex = -float(cy[1]) / (2.0 * float(cy[0]))
        if t[0] < t_apex < t[-1]:
            y_release = float(np.polyval(cy, 0.0))
            rise = y_release - float(np.polyval(cy, t_apex))
            result["apex_frame"] = int(round(release_frame + t_apex * fps))
            result["apex_rise_px"] = rise
            if pixels_per_meter:
                result["apex_rise_m"] = rise / pixels_per_meter
    step = max(1, len(frames) // 60)
    result["curve"] = [{"frame": int(f), "x": float(np.polyval(cx, tt)), "y": float(np.polyval(cy, tt))}
                       for f, tt in zip(range(release_frame, int(frames[-1]) + 1, step),
                                        (np.arange(release_frame, int(frames[-1]) + 1, step) - release_frame) / fps)]
    ratio = result["horizontal_to_vertical_acceleration"]
    notes = [f"Drag-free fit misses the measured path by {in_rmse:.1f} px RMS; predicting the second half "
             f"from the first half misses by {out_rmse:.1f} px RMS."]
    if ratio is not None and ratio < -0.03:
        notes.append(f"The bag slows horizontally in the image ({abs(ratio):.0%} of its vertical acceleration). "
                     "Drag and the bag moving away from the camera both cause this; one camera cannot separate them.")
    result["interpretation"] = " ".join(notes)
    return result

