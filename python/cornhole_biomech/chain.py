"""Per-throw chain: body → release → flight → outcome, each quantity with state, formula and uncertainty.

Coordinates: the board's 2D throw plane (board.py) — x horizontal toward the board with the
board's front edge at x = 0, y height above the floor, metres. Angles come from the 6 Hz
zero-lag filtered pose (kinematics.py); joint positions are the same filtered landmarks,
camera-steadied into the release frame and mapped through the board's plane homography.

Every quantity is `quantity(value, unit, state, formula, reason, interval, assumptions)`:
`state` is "measured", "estimated" (with a reason) or "unavailable" (with a reason);
`interval` is a Monte Carlo 95 % interval (2.5th–97.5th percentile of `MC_DRAWS` draws).

State rules
- Anything in metres (speeds, energies, forces, distances) is at most "estimated" when the
  metric scale is not "measured" (`scale_state`/`scale_reason` from the pipeline's board scale).
- Second-derivative quantities (acceleration, force, power) are "measured" only when their
  95 % interval half-width is below 25 % of the value (Winter: differentiation amplifies
  landmark noise); otherwise "estimated" with that reason. The force direction is "measured"
  only when the peak force is and its own interval half-width is below 15°.
- Power is also checked against dE/dt: when max |F·v − dE/dt| over the forward swing is
  ≥ 10 % of the peak F·v, it is "estimated" with the reason "power estimates disagree".
- Flight-model quantities (energy match, speed margin, predicted landing, timing
  sensitivity) are always "estimated": they assume drag-free flight in the board's plane.

Peak order (shoulder → elbow → wrist) is DESCRIBED, not graded: Putnam (1993) concerns fast
throws; cornhole is a slow accuracy swing. Resolution is one frame.

All mechanics are bag-only (mechanics.BAG_ONLY_NOTE): never a muscle, joint or hand-contact force.
"""
from __future__ import annotations

import math
import warnings
from typing import Any, Callable

import numpy as np

from .bag import GRAVITY_M_S2
from .filtering import derivative, lowpass_zero_phase
from .mechanics import (BAG_ONLY_NOTE, G_VECTOR, along_error_m, energy_rate, minimum_speed, net_force_on_bag,
                        power_on_bag, release_state, required_speed, timing_sensitivity)
from .regulation import BAG_MASS_KG, BAG_MASS_RANGE_KG, INCH_M, Board

HAND_OFFSET_ARM_LENGTHS = 0.34   # bag sits about one hand length beyond the wrist (auto_bag.py)
LANDMARK_NOISE_PX = 4.0          # per-frame pose noise on the pilot clips (~300 px tall athlete)
MC_DRAWS = 500
PEAK_WINDOW_AFTER_RELEASE_S = 0.1
FALLBACK_WINDOW_BEFORE_RELEASE_S = 0.6
MAX_FORWARD_SWING_S = 1.0        # a longer "forward swing" is an event error, not a swing
MAX_RELATIVE_HALF_WIDTH = 0.25   # second-derivative quantities: "measured" only below this
MAX_DIRECTION_HALF_WIDTH_DEG = 15.0   # force direction: "measured" only below this (and a measured peak force)
MAX_POWER_DISAGREEMENT = 0.10    # |F·v − dE/dt| relative to peak F·v
DEFAULT_SCALE_REL_SD = 0.05      # used only when the scale block reports no uncertainty at all
MIN_SCALE_REL_SD = 0.01
RELEASE_HEIGHT_SD_M = 0.02       # bag-centroid height in the plane: plane-offset + centroid noise, not fitted

QUANTITY_UNITS: dict[str, str] = {
    "shoulder_angle_at_release_deg": "°", "elbow_angle_at_release_deg": "°",
    "shoulder_peak_angular_velocity_deg_s": "°/s", "shoulder_peak_time_rel_release_ms": "ms",
    "elbow_peak_extension_velocity_deg_s": "°/s", "elbow_peak_time_rel_release_ms": "ms",
    "wrist_peak_speed_time_rel_release_ms": "ms", "peak_sequence": "",
    "hand_speed_at_release_m_s": "m/s", "hand_acceleration_at_release_m_s2": "m/s²",
    "peak_net_force_on_bag_n": "N", "mean_net_force_on_bag_n": "N", "force_direction_at_peak_deg": "°",
    "peak_power_on_bag_w": "W", "release_speed_m_s": "m/s", "release_angle_deg": "°", "release_height_m": "m",
    "momentum_kg_m_s": "kg·m/s", "kinetic_energy_j": "J", "potential_energy_j": "J", "mechanical_energy_j": "J",
    "energy_match_percent": "%", "speed_margin_over_minimum_percent": "%",
    "timing_sensitivity_in_per_10ms": "in / 10 ms", "predicted_along_error_in": "in",
    "measured_along_error_in": "in",
}


def quantity(value, unit: str, state: str, formula: str, *, reason: str | None = None,
             interval: list[float] | None = None, assumptions: tuple[str, ...] | list[str] = ()) -> dict[str, Any]:
    return {"value": value, "unit": unit, "state": state, "formula": formula, "reason": reason,
            "interval": interval, "assumptions": list(assumptions)}


def _missing(unit: str, formula: str, reason: str) -> dict[str, Any]:
    return quantity(None, unit, "unavailable", formula, reason=reason)


def _join(*reasons: str | None) -> str | None:
    parts = [r for r in reasons if r]
    return " ".join(parts) if parts else None


def _cap(state: str, reason: str | None, scale_state: str, scale_reason: str | None) -> tuple[str, str | None]:
    """A metre-based quantity is at most "estimated" when the scale is not measured."""
    if scale_state == "measured":
        return state, reason
    return "estimated", _join(reason, f"Metric scale not measured: {scale_reason or 'no reason given'}.")


def _interval(samples: np.ndarray) -> list[float] | None:
    s = np.asarray(samples, float)
    s = s[np.isfinite(s)]
    return None if s.size < 20 else [float(np.percentile(s, 2.5)), float(np.percentile(s, 97.5))]


def _noise_state(value: float, interval: list[float] | None, unit: str) -> tuple[str, str | None]:
    """Second-derivative rule: measured only when the 95 % interval half-width < 25 % of |value|."""
    if interval is None:
        return "estimated", "No Monte Carlo interval (landmark noise not propagated)."
    half = (interval[1] - interval[0]) / 2
    if half < MAX_RELATIVE_HALF_WIDTH * abs(value):
        return "measured", None
    return "estimated", (f"95 % interval half-width {half:.3g} {unit} is not below "
                         f"{100 * MAX_RELATIVE_HALF_WIDTH:.0f} % of the value (differentiation amplifies landmark noise).")


def _window(forward_swing: int | None, release: int, fps: float) -> tuple[int, str]:
    """Start of the forward-swing window and a note saying where it came from.

    A forward-swing event more than `MAX_FORWARD_SWING_S` before release is not a forward swing
    (pilot forward swings last 0.2–0.6 s; one clip's event sat 7 s early), so the window then
    falls back to release − `FALLBACK_WINDOW_BEFORE_RELEASE_S`, as it does without the event.
    """
    fallback = max(0, release - int(round(FALLBACK_WINDOW_BEFORE_RELEASE_S * fps)))
    if forward_swing is None or not 0 <= forward_swing < release:
        return fallback, (f"No forward-swing event before release; window starts "
                          f"{FALLBACK_WINDOW_BEFORE_RELEASE_S:.1f} s before release.")
    if (release - forward_swing) / fps > MAX_FORWARD_SWING_S:
        return fallback, (f"The forward-swing event is {(release - forward_swing) / fps:.1f} s before release "
                          f"(> {MAX_FORWARD_SWING_S:.0f} s); window starts {FALLBACK_WINDOW_BEFORE_RELEASE_S:.1f} s "
                          "before release instead.")
    return forward_swing, "Window starts at the forward-swing event."


def _peak(series: np.ndarray, start: int, stop: int) -> int | None:
    seg = np.asarray(series, float)[max(0, start):min(len(series), stop + 1)]
    if seg.size == 0 or not np.isfinite(seg).any():
        return None
    return max(0, start) + int(np.nanargmax(seg))


# ---------------------------------------------------------------------------------------------- body

def body_chain(angles: dict[str, np.ndarray], fps: float, forward_swing: int | None, release: int,
               wrist_speed: np.ndarray | None = None) -> dict[str, Any]:
    """Joint angles at release, peak angular velocities and their timing, and the peak order.

    Angles are the already-filtered 2D projected angles (no second filter). Peaks are searched in
    [forward swing, release + 0.1 s] (forward swing missing → release − 0.6 s). `wrist_speed`
    (any unit; only its timing is used) adds the wrist to the peak order.
    """
    out: dict[str, Any] = {}
    start, start_note = _window(forward_swing, release, fps)
    stop = release + int(round(PEAK_WINDOW_AFTER_RELEASE_S * fps))
    ms = lambda f: 1000.0 * (f - release) / fps
    window_note = f"Searched up to 0.1 s after release; resolution 1 frame. {start_note}"
    peaks: dict[str, int] = {}
    specs = (("shoulder", "arm_to_trunk_deg", "shoulder_angle_at_release_deg",
              "shoulder_peak_angular_velocity_deg_s", "shoulder_peak_time_rel_release_ms",
              "upper-arm vs trunk (hip→shoulder) angle"),
             ("elbow", "elbow_angle_deg", "elbow_angle_at_release_deg",
              "elbow_peak_extension_velocity_deg_s", "elbow_peak_time_rel_release_ms",
              "shoulder–elbow–wrist included angle"))
    for name, field, at_key, v_key, t_key, label in specs:
        series = np.asarray(angles[field], float)
        at = series[release] if 0 <= release < len(series) and math.isfinite(series[release]) else None
        out[at_key] = (quantity(float(at), "°", "measured", f"{label} (2D projected) at the release frame")
                       if at is not None else _missing("°", f"{label} at release", "Landmark missing at release."))
        velocity = derivative(series, fps)
        if name == "shoulder":
            p = _peak(np.abs(velocity), start, stop)
            formula = "max |dθ/dt| of the filtered shoulder angle"
        else:
            p = _peak(velocity, start, stop)
            formula = "max dθ/dt of the filtered elbow angle (positive = extending)"
            if p is not None and velocity[p] <= 0:
                p = None
        if p is None:
            out[v_key] = _missing("°/s", formula, f"No {name} angular-velocity peak in the swing window.")
            out[t_key] = _missing("ms", "t_peak − t_release", f"No {name} peak.")
            continue
        peaks[name] = p
        out[v_key] = quantity(float(abs(velocity[p])), "°/s", "measured", formula, assumptions=[window_note])
        out[t_key] = quantity(ms(p), "ms", "measured", "t_peak − t_release (negative = before release)",
                              assumptions=[window_note])
    p_wrist = None if wrist_speed is None else _peak(np.asarray(wrist_speed, float), start, stop)
    if p_wrist is None:
        out["wrist_peak_speed_time_rel_release_ms"] = _missing(
            "ms", "t(max |v_wrist|) − t_release", "Wrist speed not available in the swing window.")
    else:
        peaks["wrist"] = p_wrist
        out["wrist_peak_speed_time_rel_release_ms"] = quantity(
            ms(p_wrist), "ms", "measured", "t(max |v_wrist|) − t_release (negative = before release)",
            assumptions=[window_note, "Wrist speed from the camera-steadied filtered wrist (timing.py)."])
    if "shoulder" in peaks and "elbow" in peaks:
        rank = {"shoulder": 0, "elbow": 1, "wrist": 2, "release": 3}   # ties: proximal first, release last
        events = {**peaks, "release": release}
        chain = sorted(events, key=lambda k: (events[k], rank[k]))
        frames = [events[k] for k in chain]
        seq = quantity(" → ".join(chain), "", "measured",
                       "time order of the peak angular velocities, peak wrist speed and release (described, not graded)",
                       assumptions=["Putnam (1993) describes proximal-to-distal sequencing in fast throws; cornhole "
                                    "is a slow accuracy swing, so no order is 'correct'.",
                                    "Resolution 1 frame (16.7 ms at 60 fps); equal frames keep proximal first."])
        seq["lags_ms"] = {f"{a} → {b}": 1000.0 * (fb - fa) / fps
                          for a, b, fa, fb in zip(chain, chain[1:], frames, frames[1:])}
        out["peak_sequence"] = seq
    else:
        out["peak_sequence"] = _missing("", "peak order", "Shoulder and elbow peaks are both needed.")
    return out


# ---------------------------------------------------------------------------------------------- hand

def _hand_kinematics(shoulder: np.ndarray, elbow: np.ndarray, wrist: np.ndarray, fps: float):
    """Bag point one hand length beyond the wrist along the forearm; works on (N, ..., 2) arrays."""
    upper = np.linalg.norm(elbow - shoulder, axis=-1)
    fore = np.linalg.norm(wrist - elbow, axis=-1)
    total = upper + fore
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        arm = np.nanmedian(total, axis=0)
        unit = (wrist - elbow) / fore[..., None]
    point = wrist + HAND_OFFSET_ARM_LENGTHS * np.asarray(arm)[None, ..., None] * unit
    velocity = derivative(point, fps)
    acceleration = derivative(velocity, fps)
    return point, velocity, acceleration, arm


def _masked_stats(values: np.ndarray, axis: int = 0):
    """nanmax/nanargmax/nanmean without all-NaN warnings; columns without data give NaN / -1."""
    finite = np.isfinite(values)
    filled = np.where(finite, values, -np.inf)
    arg = np.argmax(filled, axis=axis)
    has = finite.any(axis=axis)
    peak = np.where(has, np.take_along_axis(filled, np.expand_dims(arg, axis), axis).squeeze(axis), np.nan)
    count = finite.sum(axis=axis)
    mean = np.where(count > 0, np.where(finite, values, 0.0).sum(axis=axis) / np.maximum(count, 1), np.nan)
    return peak, np.where(has, arg, -1), mean


def hand_chain(shoulder_m: np.ndarray, elbow_m: np.ndarray, wrist_m: np.ndarray, fps: float,
               forward_swing: int | None, release: int, mass_kg: float = BAG_MASS_KG, *,
               landmark_noise_m: float | None = None, rel_scale_sd: float = 0.0,
               mass_range: tuple[float, float] = BAG_MASS_RANGE_KG, scale_state: str = "measured",
               scale_reason: str | None = None, board: Board | None = None, draws: int = MC_DRAWS,
               seed: int = 0) -> dict[str, Any]:
    """Bag-point kinematics and bag-only net force F = m (a − g⃗) and power F·v over the forward swing.

    Joint positions are (N, 2) metres in a plane with y up. When `board` is given they are taken
    to be the board's throw-plane coordinates (front edge at x = 0, y above the floor) and the
    release-timing sensitivity is computed too. Monte Carlo: each draw adds 6 Hz-filtered white
    landmark noise (`landmark_noise_m` per axis per frame, i.e. the part of pose noise that
    survives the pose filter), multiplies positions by a scale factor N(1, `rel_scale_sd`) and
    draws the bag mass uniformly in `mass_range`.
    """
    shoulder_m, elbow_m, wrist_m = (np.asarray(a, float) for a in (shoulder_m, elbow_m, wrist_m))
    n = len(wrist_m)
    point, velocity, acceleration, arm = _hand_kinematics(shoulder_m, elbow_m, wrist_m, fps)
    force = net_force_on_bag(acceleration, mass_kg)
    power = power_on_bag(force, velocity)
    rate = energy_rate(velocity, point, mass_kg, fps)
    start, start_note = _window(forward_swing, release, fps)
    window = slice(start, min(n, release + 1))
    magnitude = np.linalg.norm(force[window], axis=1)
    has_release = 0 <= release < n and np.isfinite(velocity[release]).all() and np.isfinite(acceleration[release]).all()

    # ---- Monte Carlo
    mc: dict[str, np.ndarray] = {}
    noise = float(landmark_noise_m or 0.0)
    if (noise > 0 or rel_scale_sd > 0) and draws > 0 and np.isfinite(magnitude).any():
        rng = np.random.default_rng(seed)
        s = rng.normal(1.0, rel_scale_sd, draws) if rel_scale_sd > 0 else np.ones(draws)
        m = rng.uniform(*mass_range, draws)

        def perturbed(joint: np.ndarray) -> np.ndarray:
            out = joint[:, None, :] * s[None, :, None]
            if noise > 0:
                white = rng.normal(0.0, noise, (n, draws * 2))
                out = out + lowpass_zero_phase(white, fps)[0].reshape(n, draws, 2)
            return out

        sh, el, wr = perturbed(shoulder_m), perturbed(elbow_m), perturbed(wrist_m)
        p_mc, v_mc, a_mc, _ = _hand_kinematics(sh, el, wr, fps)
        f_mc = m[None, :, None] * (a_mc - G_VECTOR)
        mag_mc = np.linalg.norm(f_mc[window], axis=-1)                      # (W, draws)
        peak_mc, arg_mc, mean_mc = _masked_stats(mag_mc)
        f_win = f_mc[window]
        cols = np.arange(draws)
        f_at = f_win[np.clip(arg_mc, 0, None), cols]                        # (draws, 2)
        dir_mc = np.where(arg_mc >= 0, np.degrees(np.arctan2(f_at[:, 1], f_at[:, 0])), np.nan)
        pow_mc, _, _ = _masked_stats(np.sum(f_win * v_mc[window], axis=-1))
        mc = {"peak": peak_mc, "mean": mean_mc, "direction": dir_mc, "power": pow_mc}
        if has_release:
            mc["speed"] = np.linalg.norm(v_mc[release], axis=-1)
            mc["accel"] = np.linalg.norm(a_mc[release], axis=-1)
            if board is not None:
                mc["timing"] = np.array([
                    np.nan if (t := timing_sensitivity(p_mc[:, k], v_mc[:, k], release, fps,
                                                       -float(p_mc[release, k, 0]), board)) is None else t
                    for k in range(draws)]) / INCH_M
    iv = lambda key: _interval(mc[key]) if key in mc else None

    assume = [BAG_ONLY_NOTE, "Bag assumed rigidly held one hand length (0.34 arm length) beyond the wrist along "
              "the forearm.", "2D throw plane; second derivative of 6 Hz filtered landmarks (noise-sensitive).",
              f"Monte Carlo: {LANDMARK_NOISE_PX:.0f} px landmark noise (6 Hz filtered), scale and bag-mass range.",
              f"Forward swing = window up to release. {start_note}"]
    q: dict[str, Any] = {}

    def second(key: str, value: float, unit: str, formula: str, mc_key: str) -> dict[str, Any]:
        interval = iv(mc_key)
        state, reason = _noise_state(value, interval, unit)
        state, reason = _cap(state, reason, scale_state, scale_reason)
        return quantity(value, unit, state, formula, reason=reason, interval=interval, assumptions=assume)

    if np.isfinite(magnitude).any():
        i = int(np.nanargmax(magnitude))
        f_peak = force[window][i]
        q["peak_net_force_on_bag_n"] = second("peak", float(magnitude[i]), "N",
                                              "max |F|, F = m (a_bag − g⃗), g⃗ = (0, −g), over the forward swing",
                                              "peak")
        q["mean_net_force_on_bag_n"] = second("mean", float(np.nanmean(magnitude)), "N",
                                              "mean |m (a_bag − g⃗)| over the forward swing", "mean")
        peak_state = q["peak_net_force_on_bag_n"]
        direction = float(math.degrees(math.atan2(f_peak[1], f_peak[0])))
        d_interval = None
        if "direction" in mc:     # wrap draws around the nominal so a direction near ±180° is not split
            wrapped = direction + (mc["direction"] - direction + 180.0) % 360.0 - 180.0
            d_interval = _interval(wrapped)
        d_state, d_reason = peak_state["state"], peak_state["reason"]
        if d_interval is None:
            d_state, d_reason = "estimated", _join(d_reason, "No Monte Carlo interval for the direction.")
        elif (d_interval[1] - d_interval[0]) / 2 >= MAX_DIRECTION_HALF_WIDTH_DEG:
            d_state = "estimated"
            d_reason = _join(f"95 % interval half-width {(d_interval[1] - d_interval[0]) / 2:.0f}° is not below "
                             f"{MAX_DIRECTION_HALF_WIDTH_DEG:.0f}°.", d_reason)
        q["force_direction_at_peak_deg"] = quantity(
            direction, "°", d_state, "atan2(F_y, F_x) at peak |F| (0° = toward the board, 90° = straight up)",
            reason=d_reason, interval=d_interval,
            assumptions=assume + ["At most as certain as the peak force it describes."])
        p_win, r_win = power[window], rate[window]
        ok = np.isfinite(p_win) & np.isfinite(r_win)
        if ok.any():
            peak_p = float(np.max(p_win[ok]))
            gap = float(np.max(np.abs(p_win[ok] - r_win[ok])))
            item = second("power", peak_p, "W", "max F·v_bag over the forward swing (checked against dE/dt)", "power")
            if not gap < MAX_POWER_DISAGREEMENT * abs(peak_p):
                item["state"] = "estimated"
                item["reason"] = _join("power estimates disagree", f"(max |F·v − dE/dt| = {gap:.3g} W, not below "
                                       f"{100 * MAX_POWER_DISAGREEMENT:.0f} % of peak F·v).",
                                       item["reason"] if item["reason"] else None)
            q["peak_power_on_bag_w"] = item
        else:
            q["peak_power_on_bag_w"] = _missing("W", "max F·v", "Power not computable over the forward swing.")
    else:
        for key in ("peak_net_force_on_bag_n", "mean_net_force_on_bag_n", "force_direction_at_peak_deg",
                    "peak_power_on_bag_w"):
            q[key] = _missing(QUANTITY_UNITS[key], "m (a − g⃗)", "Arm landmarks missing in the forward swing.")
    if has_release:
        state, reason = _cap("measured", None, scale_state, scale_reason)
        q["hand_speed_at_release_m_s"] = quantity(float(np.linalg.norm(velocity[release])), "m/s", state,
                                                  "|d(bag point)/dt| at the release frame", reason=reason,
                                                  interval=iv("speed"), assumptions=assume[1:])
        q["hand_acceleration_at_release_m_s2"] = second("accel", float(np.linalg.norm(acceleration[release])),
                                                        "m/s²", "|d²(bag point)/dt²| at the release frame", "accel")
        q["hand_acceleration_at_release_m_s2"]["assumptions"] = assume[1:]
    else:
        for key in ("hand_speed_at_release_m_s", "hand_acceleration_at_release_m_s2"):
            q[key] = _missing(QUANTITY_UNITS[key], "derivative of the bag point", "Arm landmarks missing at release.")
    if board is not None:
        around = 1 <= release < n - 1 and all(np.isfinite(point[k]).all() and np.isfinite(velocity[k]).all()
                                               for k in (release - 1, release, release + 1))
        s_nom = timing_sensitivity(point, velocity, release, fps, -float(point[release, 0]), board) if around else None
        if s_nom is None:
            q["timing_sensitivity_in_per_10ms"] = _missing(
                "in / 10 ms", "timing sensitivity",
                "The hand path at release ± 1 frame does not reach the board (hand moving up or away from it), "
                "so it cannot stand in for the bag's path." if around else "Hand path incomplete around release.")
        else:
            state, reason = _cap("estimated", "Hand path stands in for the bag path; drag-free flight.",
                                 scale_state, scale_reason)
            q["timing_sensitivity_in_per_10ms"] = quantity(
                s_nom / INCH_M, "in / 10 ms", state,
                "Δ landing along the throw line for releasing 10 ms later, from the hand path's position and "
                "velocity at release ± 1 frame propagated through drag-free flight (Nasu et al. 2014)",
                reason=reason, interval=iv("timing"),
                assumptions=["Hand path used as the bag path around release.", "Drag-free flight."])
    return {"quantities": q, "series": {"bag_point_m": point.tolist(), "velocity_m_s": velocity.tolist(),
                                        "acceleration_m_s2": acceleration.tolist(), "force_n": force.tolist(),
                                        "power_w": power.tolist(), "energy_rate_w": rate.tolist()},
            "arm_length_m": float(arm) if np.isfinite(arm) else None}


# ------------------------------------------------------------------------------------------- release

def release_chain(speed: float, angle_deg: float, height_m: float, to_front_m: float | None, se: dict[str, float],
                  mass_range: tuple[float, float] = BAG_MASS_RANGE_KG, rel_scale_sd: float = DEFAULT_SCALE_REL_SD,
                  draws: int = MC_DRAWS, seed: int = 0, board: Board = Board(), *, scale_state: str = "measured",
                  scale_reason: str | None = None, scale_basis: str | None = None) -> dict[str, Any]:
    """Release state (p, KE, PE, E) and the drag-free flight model from (v, θ, h, distance to the board).

    Monte Carlo over the fit's standard errors (`se`: speed m/s, angle °, height m), a common scale
    factor N(1, `rel_scale_sd`) on speed, height and distance, and a uniform bag mass in `mass_range`.
    `to_front_m` (horizontal release → board front edge) None withholds the flight-model quantities.
    """
    rng = np.random.default_rng(seed)
    scale = rng.normal(1.0, rel_scale_sd, draws)
    v = (speed + rng.normal(0, se.get("speed") or 0.0, draws)) * scale
    th = angle_deg + rng.normal(0, se.get("angle") or 0.0, draws)
    h = (height_m + rng.normal(0, se.get("height") or 0.0, draws)) * scale
    m = rng.uniform(*mass_range, draws)
    vx, vy = speed * math.cos(math.radians(angle_deg)), speed * math.sin(math.radians(angle_deg))
    nominal = release_state(vx, vy, height_m, BAG_MASS_KG)
    ke, pe, p = 0.5 * m * v**2, m * GRAVITY_M_S2 * h, m * v
    scale_note = (f"Scale uncertainty {100 * rel_scale_sd:.1f} % (1 SD)"
                  + (f": {scale_basis}." if scale_basis else "."))
    common = [scale_note, "Bag mass 15.5–16 oz (uniform); nominal value at 15.75 oz."]
    metric_state, metric_reason = _cap("measured", None, scale_state, scale_reason)

    def metric(value, unit, formula, samples, extra=()) -> dict[str, Any]:
        return quantity(value, unit, metric_state, formula, reason=metric_reason, interval=_interval(samples),
                        assumptions=list(extra) + common)

    out = {
        "release_speed_m_s": metric(speed, "m/s", "|v| from the gravity-constrained ballistic flight fit", v,
                                    ["Fit standard error propagated."]),
        "release_angle_deg": quantity(angle_deg, "°", "measured", "atan2(v_y, v_x) from the flight fit",
                                      interval=_interval(th), assumptions=["Fit standard error propagated."]),
        "release_height_m": metric(height_m, "m", "bag centroid height above the floor at release", h,
                                   [f"Height SD {100 * (se.get('height') or 0.0):.0f} cm assumed."]),
        "momentum_kg_m_s": metric(nominal["momentum_magnitude_kg_m_s"], "kg·m/s", "|p| = m |v|", p),
        "kinetic_energy_j": metric(nominal["kinetic_energy_j"], "J", "KE = ½ m v²", ke),
        "potential_energy_j": metric(nominal["potential_energy_j"], "J", "PE = m g h (h above the floor)", pe),
        "mechanical_energy_j": metric(nominal["mechanical_energy_j"], "J", "E = KE + PE", ke + pe),
    }
    out["momentum_kg_m_s"]["vector_kg_m_s"] = nominal["momentum_kg_m_s"]
    flight_assume = common + ["Drag-free flight in the board's vertical plane; regulation board geometry."]
    if to_front_m is None:
        reason = "Distance from release to the board is unknown (no throw-plane mapping)."
        out["energy_match_percent"] = _missing("%", "100 (v² / v_req² − 1)", reason)
        out["speed_margin_over_minimum_percent"] = _missing("%", "100 (v / v_min − 1)", reason)
        out["predicted_along_error_in"] = _missing("in", "drag-free landing − hole centre", reason)
        return out
    d = to_front_m * scale
    flight_state, flight_reason = _cap("estimated", "Drag-free flight model.", scale_state, scale_reason)
    req0 = required_speed(angle_deg, height_m, to_front_m, board)
    if req0:
        v_req = np.array([required_speed(a, hh, dd, board) or np.nan for a, hh, dd in zip(th, h, d)])
        out["energy_match_percent"] = quantity(
            100 * (speed**2 / req0**2 - 1), "%", flight_state,
            "100 (v² / v_req² − 1); v_req lands on the hole centre from this release angle and height",
            reason=flight_reason, interval=_interval(100 * (v**2 / v_req**2 - 1)), assumptions=flight_assume)
    else:
        out["energy_match_percent"] = _missing("%", "100 (v² / v_req² − 1)",
                                               "No speed reaches the hole centre at this release angle.")
    v_min0 = minimum_speed(height_m, to_front_m, board)
    v_min = np.array([minimum_speed(hh, dd, board) for hh, dd in zip(h, d)])
    out["speed_margin_over_minimum_percent"] = quantity(
        100 * (speed / v_min0 - 1), "%", flight_state, "100 (v / v_min − 1); v_min over all release angles",
        reason=flight_reason, interval=_interval(100 * (v / v_min - 1)),
        assumptions=flight_assume + ["Venkadesan & Mahadevan (2017): the most accurate throws are slightly "
                                     "above the minimum speed; no fixed ideal."])
    err0 = along_error_m(vx, vy, height_m, to_front_m, board)
    if err0 is None:
        out["predicted_along_error_in"] = _missing("in", "drag-free landing − hole centre",
                                                   "The path never reaches the deck plane.")
    else:
        err = np.array([along_error_m(vv * math.cos(math.radians(a)), vv * math.sin(math.radians(a)), hh, dd, board)
                        or np.nan for vv, a, hh, dd in zip(v, th, h, d)])
        interval = _interval(err)
        out["predicted_along_error_in"] = quantity(
            err0 / INCH_M, "in", flight_state,
            "drag-free landing on the (extended) deck plane − hole centre, along the throw line (+ = long)",
            reason=flight_reason, interval=None if interval is None else [x / INCH_M for x in interval],
            assumptions=flight_assume)
    return out


# --------------------------------------------------------------------------------------------- scale

def scale_relative_sd(scale: dict[str, Any], ppm_at_hfov: Callable[[float], float | None]) -> tuple[float, str]:
    """1-SD relative uncertainty of the metric scale, from the field-of-view uncertainty actually reported.

    - Pooled (session/library) HFOV with an IQR: half the relative spread between the scale at
      the IQR edges (HFOV ± IQR/2). Half the IQR is ≈ 0.67 SD of the per-throw HFOVs — a
      deliberately conservative stand-in for the median's own uncertainty.
    - Otherwise, a single-throw gravity calibration: the relative spread between the scale at
      55° and 75° divided by 4, treating the admissible 55–75° band as ≈ ±2 SD (Task 8b saw
      per-throw HFOVs a few degrees to ten-plus degrees apart on one phone and spot).
    - Nothing reported: `DEFAULT_SCALE_REL_SD` (5 %).
    Floored at `MIN_SCALE_REL_SD`.
    """
    ppm, hfov, iqr = scale.get("pixels_per_meter"), scale.get("hfov_deg"), scale.get("hfov_iqr_deg")
    if ppm and hfov is not None and iqr:
        lo, hi = ppm_at_hfov(hfov - iqr / 2), ppm_at_hfov(hfov + iqr / 2)
        if lo and hi and math.isfinite(lo) and math.isfinite(hi):
            return (max(MIN_SCALE_REL_SD, abs(hi - lo) / ppm / 2),
                    f"half the relative scale spread across the pooled field-of-view IQR "
                    f"({hfov - iqr / 2:.1f}–{hfov + iqr / 2:.1f}°)")
    p55, p75 = scale.get("pixels_per_meter_at_55_deg"), scale.get("pixels_per_meter_at_75_deg")
    if ppm and p55 and p75:
        return (max(MIN_SCALE_REL_SD, abs(p55 - p75) / ppm / 4),
                "a quarter of the relative scale spread between 55° and 75° field of view (band ≈ ±2 SD)")
    return DEFAULT_SCALE_REL_SD, "no scale uncertainty reported; default 5 %"


# ------------------------------------------------------------------------------------------- assembly

def build_chain(*, angles: dict[str, np.ndarray], fps: float, forward_swing: int | None, release: int,
                joints_m: dict[str, np.ndarray] | None, release_values: dict[str, float | None],
                release_se: dict[str, float], to_front_m: float | None, measured_along_error_m: float | None,
                board: Board = Board(), scale_rel_sd: float = DEFAULT_SCALE_REL_SD, scale_state: str = "measured",
                scale_reason: str | None = None, scale_basis: str | None = None, joints_reason: str | None = None,
                wrist_speed: np.ndarray | None = None, landmark_noise_m: float | None = None,
                draws: int = MC_DRAWS, seed: int = 0) -> dict[str, Any]:
    """One throw's chain record. `joints_m` ("shoulder", "elbow", "wrist": (N, 2)) are board throw-plane
    metres (front edge x = 0, y above the floor); None withholds the hand/bag mechanics with `joints_reason`.
    Every name in `QUANTITY_UNITS` is present in `quantities`."""
    q: dict[str, Any] = dict(body_chain(angles, fps, forward_swing, release, wrist_speed))
    series: dict[str, Any] = {}
    notes = [BAG_ONLY_NOTE]
    hand_reason = joints_reason or "Throw-plane joint positions unavailable."
    if joints_m is not None:
        hand = hand_chain(joints_m["shoulder"], joints_m["elbow"], joints_m["wrist"], fps, forward_swing, release,
                          landmark_noise_m=landmark_noise_m, rel_scale_sd=scale_rel_sd, scale_state=scale_state,
                          scale_reason=scale_reason, board=board, draws=draws, seed=seed)
        q.update(hand["quantities"])
        series = hand["series"]
    else:
        notes.append(f"Hand/bag mechanics withheld: {hand_reason}")
    v, a, h = (release_values.get(k) for k in ("speed", "angle", "height"))
    if None not in (v, a, h):
        q.update(release_chain(v, a, h, to_front_m, release_se, rel_scale_sd=scale_rel_sd, draws=draws,
                               seed=seed + 1, board=board, scale_state=scale_state, scale_reason=scale_reason,
                               scale_basis=scale_basis))
        release_reason = None
    else:
        missing = [k for k, x in (("speed (m/s)", v), ("angle", a), ("height (m)", h)) if x is None]
        release_reason = f"Release {', '.join(missing)} not available from the flight fit."
    if measured_along_error_m is not None:
        state, reason = _cap("measured", None, scale_state, scale_reason)
        q["measured_along_error_in"] = quantity(
            measured_along_error_m / INCH_M, "in", state,
            "observed first contact − hole centre along the throw line, in the board plane (+ = long)",
            reason=reason, assumptions=["Contact classified as observed on the deck/floor (contact.py)."])
    else:
        q["measured_along_error_in"] = _missing("in", "observed first contact − hole centre",
                                                "First contact not observed on the deck or floor for this throw.")
    hand_keys = {"hand_speed_at_release_m_s", "hand_acceleration_at_release_m_s2", "peak_net_force_on_bag_n",
                 "mean_net_force_on_bag_n", "force_direction_at_peak_deg", "peak_power_on_bag_w",
                 "timing_sensitivity_in_per_10ms"}
    for name, unit in QUANTITY_UNITS.items():
        if name not in q:
            reason = (hand_reason if name in hand_keys else
                      release_reason or "Distance from release to the board is unknown.")
            q[name] = _missing(unit, name, reason)
    return {"quantities": {name: q[name] for name in QUANTITY_UNITS}, "series": series, "notes": notes,
            "scale": {"state": scale_state, "reason": scale_reason, "relative_sd": scale_rel_sd,
                      "basis": scale_basis}}


def flatten_for_summaries(chain: dict[str, Any]) -> dict[str, float | None]:
    out = {}
    for name, item in chain["quantities"].items():
        value = item["value"] if item["state"] != "unavailable" else None
        out[f"chain_{name}"] = value if not isinstance(value, str) else None
    return out
