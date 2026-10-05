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
from .events import elbow_extension_search_start
from .filtering import derivative, lowpass_zero_phase
from .mechanics import (BAG_ONLY_NOTE, G_VECTOR, along_error_m, energy_rate, landing_jacobian, minimum_speed,
                        net_force_on_bag, power_on_bag, release_state, required_speed)
from .regulation import BAG_MASS_KG, BAG_MASS_RANGE_KG, INCH_M, Board

HAND_OFFSET_ARM_LENGTHS = 0.34   # bag sits about one hand length beyond the wrist (auto_bag.py)
LANDMARK_NOISE_PX = 4.0          # per-frame pose noise on the pilot clips (~300 px tall athlete)
MC_DRAWS = 500
PEAK_WINDOW_AFTER_RELEASE_S = 0.1
FALLBACK_WINDOW_BEFORE_RELEASE_S = 0.6
MAX_FORWARD_SWING_S = 1.0        # a longer "forward swing" is an event error, not a swing
MAX_RELATIVE_HALF_WIDTH = 0.25   # second-derivative quantities: "measured" only below this
MAX_DIRECTION_HALF_WIDTH_DEG = 15.0   # force direction: "measured" only below this (and a measured peak force)
MAX_HAND_BAG_ANGLE_DIFF_DEG = 10.0   # timing sensitivity needs the hand path to point where the bag went
TIMING_STEP_S = 0.010
SERIES_BEFORE_WINDOW_S = 0.2     # stored series: forward-swing start − 0.2 s … release + 0.1 s
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
    "hand_velocity_angle_at_release_deg": "°", "hand_tangential_acceleration_at_release_m_s2": "m/s²",
    "hand_direction_rotation_rate_deg_s": "°/s",
    "peak_net_force_on_bag_n": "N", "mean_net_force_on_bag_n": "N", "force_direction_at_peak_deg": "°",
    "peak_power_on_bag_w": "W", "release_speed_m_s": "m/s", "release_angle_deg": "°", "release_height_m": "m",
    "momentum_kg_m_s": "kg·m/s", "kinetic_energy_j": "J", "potential_energy_j": "J", "mechanical_energy_j": "J",
    "energy_match_percent": "%", "speed_margin_over_minimum_percent": "%",
    "timing_sensitivity_in_per_10ms": "in / 10 ms", "predicted_along_error_in": "in",
    "measured_along_error_in": "in",
}

_POSE = "filtered pose landmarks"
_HAND = ["filtered shoulder/elbow/wrist in the board throw plane", "hand offset 0.34 arm length", "fps"]
_BAG = ["bag release speed (flight fit)", "bag release angle (flight fit)", "bag release height",
        "release → board front distance", "regulation board geometry"]
QUANTITY_INPUTS: dict[str, list[str]] = {
    "shoulder_angle_at_release_deg": [_POSE, "release frame"],
    "elbow_angle_at_release_deg": [_POSE, "release frame"],
    "shoulder_peak_angular_velocity_deg_s": [_POSE, "forward-swing event", "release frame", "fps"],
    "shoulder_peak_time_rel_release_ms": [_POSE, "forward-swing event", "release frame", "fps"],
    "elbow_peak_extension_velocity_deg_s": [_POSE, "forward-swing event", "release frame", "fps"],
    "elbow_peak_time_rel_release_ms": [_POSE, "forward-swing event", "release frame", "fps"],
    "wrist_peak_speed_time_rel_release_ms": ["camera-steadied wrist speed (timing.py)", "release frame", "fps"],
    "peak_sequence": ["shoulder/elbow/wrist peak frames", "release frame"],
    "hand_speed_at_release_m_s": _HAND + ["release frame"],
    "hand_acceleration_at_release_m_s2": _HAND + ["release frame"],
    "hand_velocity_angle_at_release_deg": _HAND + ["release frame"],
    "hand_tangential_acceleration_at_release_m_s2": _HAND + ["release frame"],
    "hand_direction_rotation_rate_deg_s": _HAND + ["release frame"],
    "peak_net_force_on_bag_n": _HAND + ["bag mass", "g", "forward-swing window"],
    "mean_net_force_on_bag_n": _HAND + ["bag mass", "g", "forward-swing window"],
    "force_direction_at_peak_deg": _HAND + ["bag mass", "g", "forward-swing window"],
    "peak_power_on_bag_w": _HAND + ["bag mass", "g", "forward-swing window"],
    "release_speed_m_s": ["bag flight fit", "metric scale"],
    "release_angle_deg": ["bag flight fit"],
    "release_height_m": ["bag release point", "floor line", "metric scale"],
    "momentum_kg_m_s": ["release speed", "bag mass"],
    "kinetic_energy_j": ["release speed", "bag mass"],
    "potential_energy_j": ["release height", "bag mass", "g"],
    "mechanical_energy_j": ["release speed", "release height", "bag mass", "g"],
    "energy_match_percent": _BAG,
    "speed_margin_over_minimum_percent": [b for b in _BAG if "angle" not in b],
    "timing_sensitivity_in_per_10ms": _BAG + ["hand-path tangential acceleration, direction rotation rate and "
                                              "velocity at release"],
    "predicted_along_error_in": _BAG,
    "measured_along_error_in": ["observed first contact (contact.py)", "board model"],
}


def quantity(value, unit: str, state: str, formula: str, *, reason: str | None = None,
             interval: list[float] | None = None, assumptions: tuple[str, ...] | list[str] = (),
             inputs: tuple[str, ...] | list[str] = ()) -> dict[str, Any]:
    return {"value": value, "unit": unit, "state": state, "formula": formula, "reason": reason,
            "interval": interval, "assumptions": list(assumptions), "inputs": list(inputs)}


def _with_inputs(q: dict[str, Any]) -> dict[str, Any]:
    """Fill each quantity's `inputs` (spec §5) from `QUANTITY_INPUTS` when the caller left it empty."""
    for name, item in q.items():
        if not item.get("inputs"):
            item["inputs"] = list(QUANTITY_INPUTS.get(name, []))
    return q


def _sig(values, digits: int = 4):
    """Round nested numbers to `digits` significant digits; non-finite → None (JSON-friendly)."""
    a = np.asarray(values, float)
    flat = [None if not math.isfinite(v) else float(f"{v:.{digits}g}") for v in a.ravel()]
    return np.array(flat, dtype=object).reshape(a.shape).tolist()


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


def forward_swing_window(forward_swing: int | None, release: int, fps: float) -> tuple[int, str]:
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


EDGE_PEAK_REASON = "peak at the edge of the search window"


def _peak_or_edge(series: np.ndarray, start: int, stop: int) -> tuple[int | None, bool]:
    """(frame of the maximum in [start, stop], whether it sits on the window's first or last sample).

    A maximum on a window boundary is not a peak: the series was still rising (or had been
    falling from before the window), so the real peak lies outside the search range.
    """
    lo, hi = max(0, start), min(len(series), stop + 1)
    seg = np.asarray(series, float)[lo:hi]
    if seg.size == 0 or not np.isfinite(seg).any():
        return None, False
    finite = np.flatnonzero(np.isfinite(seg))
    i = int(np.nanargmax(seg))
    return lo + i, i in (int(finite[0]), int(finite[-1]))


def _peak(series: np.ndarray, start: int, stop: int) -> int | None:
    """Interior maximum in [start, stop]; None when there is none or it lies on a window edge."""
    frame, edge = _peak_or_edge(series, start, stop)
    return None if edge else frame


# ---------------------------------------------------------------------------------------------- body

def body_chain(angles: dict[str, np.ndarray], fps: float, forward_swing: int | None, release: int,
               wrist_speed: np.ndarray | None = None) -> dict[str, Any]:
    """Joint angles at release, peak angular velocities and their timing, and the peak order.

    Angles are the already-filtered 2D projected angles (no second filter). Peaks are searched in
    [forward swing, release + 0.1 s] (forward swing missing → release − 0.6 s); the elbow search
    starts once extension carried over from the backswing has ended (`elbow_extension_search_start`).
    `wrist_speed`
    (any unit; only its timing is used) adds the wrist to the peak order.
    """
    out: dict[str, Any] = {}
    start, start_note = forward_swing_window(forward_swing, release, fps)
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
            p, edge = _peak_or_edge(np.abs(velocity), start, stop)
            formula = "max |dθ/dt| of the filtered shoulder angle"
        else:
            # Forward-swing extension only: skip extension carried over from the backswing.
            p, edge = _peak_or_edge(velocity, elbow_extension_search_start(velocity, start, release), stop)
            formula = "max dθ/dt of the filtered elbow angle (positive = extending)"
            if p is not None and velocity[p] <= 0:
                p, edge = None, False
        if p is None or edge:
            why = (f"{name.capitalize()} angular velocity: {EDGE_PEAK_REASON} ({ms(p):+.0f} ms from release)."
                   if edge else f"No {name} angular-velocity peak in the swing window.")
            out[v_key] = _missing("°/s", formula, why)
            out[t_key] = _missing("ms", "t_peak − t_release", why if edge else f"No {name} peak.")
            continue
        peaks[name] = p
        out[v_key] = quantity(float(abs(velocity[p])), "°/s", "measured", formula, assumptions=[window_note])
        out[t_key] = quantity(ms(p), "ms", "measured", "t_peak − t_release (negative = before release)",
                              assumptions=[window_note])
    p_wrist, wrist_edge = ((None, False) if wrist_speed is None
                           else _peak_or_edge(np.asarray(wrist_speed, float), start, stop))
    if p_wrist is None or wrist_edge:
        out["wrist_peak_speed_time_rel_release_ms"] = _missing(
            "ms", "t(max |v_wrist|) − t_release",
            f"Wrist speed: {EDGE_PEAK_REASON} ({ms(p_wrist):+.0f} ms from release)." if wrist_edge
            else "Wrist speed not available in the swing window.")
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
        out["peak_sequence"] = _missing("", "peak order", "Shoulder and elbow peaks are both needed (a maximum on "
                                                          "the edge of the search window is not a peak).")
    return _with_inputs(out)


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
               scale_reason: str | None = None, draws: int = MC_DRAWS, seed: int = 0) -> dict[str, Any]:
    """Bag-point kinematics and bag-only net force F = m (a − g⃗) and power F·v over the forward swing.

    Joint positions are (N, 2) metres in a plane with x toward the target and y up. Also reports the
    hand path's velocity direction, tangential acceleration and direction rotation rate at release
    (`release_rates`, nominal and per draw) for the timing sensitivity. Monte Carlo: each draw adds 6 Hz-filtered white
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
    start, start_note = forward_swing_window(forward_swing, release, fps)
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
            mc.update({f"rate_{k}": v for k, v in _release_rates(v_mc[release], a_mc[release]).items()})
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
    rates = _release_rates(velocity[release], acceleration[release]) if has_release else None
    if rates is not None:
        cap = lambda st, rs: _cap(st, rs, scale_state, scale_reason)
        q["hand_velocity_angle_at_release_deg"] = quantity(
            float(rates["angle_deg"]), "°", "measured", "atan2(v_y, v_x) of the bag point at the release frame",
            interval=iv("rate_angle_deg"), assumptions=assume[1:])
        t_val = float(rates["tangential_m_s2"])
        t_state, t_reason = cap(*_noise_state(t_val, iv("rate_tangential_m_s2"), "m/s²"))
        q["hand_tangential_acceleration_at_release_m_s2"] = quantity(
            t_val, "m/s²", t_state, "a · v̂ of the bag point at release (negative = slowing down)", reason=t_reason,
            interval=iv("rate_tangential_m_s2"), assumptions=assume[1:])
        w_val = float(rates["rotation_deg_s"])
        w_state, w_reason = _noise_state(w_val, iv("rate_rotation_deg_s"), "°/s")
        q["hand_direction_rotation_rate_deg_s"] = quantity(
            w_val, "°/s", w_state, "dθ_v/dt = (v_x a_y − v_y a_x) / |v|² at release (positive = turning upward)",
            reason=w_reason, interval=iv("rate_rotation_deg_s"),
            assumptions=assume[1:] + ["Scale-free: a ratio of plane quantities."])
    else:
        for key in ("hand_velocity_angle_at_release_deg", "hand_tangential_acceleration_at_release_m_s2",
                    "hand_direction_rotation_rate_deg_s"):
            q[key] = _missing(QUANTITY_UNITS[key], "hand path at release", "Arm landmarks missing at release.")
    lo = max(0, start - int(round(SERIES_BEFORE_WINDOW_S * fps)))
    hi = min(n, release + int(round(PEAK_WINDOW_AFTER_RELEASE_S * fps)) + 1)
    series = {"start_frame": lo, "mass_kg": mass_kg, "bag_point_m": _sig(point[lo:hi]),
              "velocity_m_s": _sig(velocity[lo:hi]), "force_n": _sig(force[lo:hi]), "power_w": _sig(power[lo:hi]),
              "energy_rate_w": _sig(rate[lo:hi]),
              "note": "Frames start_frame … start_frame + len − 1; acceleration = force / mass_kg + g⃗."}
    release_rates = None
    if rates is not None:
        release_rates = {"nominal": {k: float(v) for k, v in rates.items()},
                         "draws": {k[5:]: v for k, v in mc.items() if k.startswith("rate_")} or None}
    return {"quantities": _with_inputs(q), "series": series, "release_rates": release_rates,
            "arm_length_m": float(arm) if np.isfinite(arm) else None}


def _release_rates(v: np.ndarray, a: np.ndarray) -> dict[str, np.ndarray]:
    """Velocity direction (°), tangential acceleration (m/s²), direction rotation rate (°/s), v_x, v_y;
    `v`/`a` are (..., 2)."""
    v, a = np.asarray(v, float), np.asarray(a, float)
    speed2 = np.sum(v * v, axis=-1)
    speed = np.sqrt(speed2)
    with np.errstate(invalid="ignore", divide="ignore"):
        return {"angle_deg": np.degrees(np.arctan2(v[..., 1], v[..., 0])),
                "tangential_m_s2": np.sum(a * v, axis=-1) / speed,
                "rotation_deg_s": np.degrees((v[..., 0] * a[..., 1] - v[..., 1] * a[..., 0]) / speed2),
                "vx": v[..., 0], "vy": v[..., 1]}


def timing_sensitivity_from_rates(speed: float, angle_deg: float, height_m: float, to_front_m: float,
                                  dv_dt: float, dtheta_dt_deg_s: float, dh_dt: float, dx_dt: float,
                                  board: Board = Board()) -> dict[str, float] | None:
    """Landing change (m) for releasing `TIMING_STEP_S` later (Nasu et al. 2014; Venkadesan & Mahadevan 2017).

    S = (∂R/∂v · dv/dt + ∂R/∂θ · dθ/dt + ∂R/∂h · dh/dt + ∂R/∂x · dx/dt) × 10 ms, the Jacobian
    (mechanics.landing_jacobian) taken at the BAG's fitted release and the rates from the hand
    path at release. The last term is the release point moving toward the board (∂R/∂x = +1 for
    an error measured from the fixed hole: the whole path shifts). Returns the total and the four
    terms, or None when the Jacobian is undefined.
    """
    jac = landing_jacobian(speed, angle_deg, height_m, to_front_m, board)
    th = math.radians(angle_deg)
    step = 0.01
    e = [along_error_m(speed * math.cos(th), speed * math.sin(th), height_m, to_front_m + d, board)
         for d in (-step, step)]
    if None in e or not all(math.isfinite(jac[k]) for k in ("d_speed", "d_angle", "d_height")):
        return None
    d_x = -(e[1] - e[0]) / (2 * step)        # moving the release point toward the board = shorter distance
    terms = {"speed": jac["d_speed"] * dv_dt, "angle": jac["d_angle"] * dtheta_dt_deg_s,
             "height": jac["d_height"] * dh_dt, "position": d_x * dx_dt}
    terms = {k: v * TIMING_STEP_S for k, v in terms.items()}
    return {"total": sum(terms.values()), **terms}


# ------------------------------------------------------------------------------------------- release

def release_chain(speed: float, angle_deg: float, height_m: float, to_front_m: float | None, se: dict[str, float],
                  mass_range: tuple[float, float] = BAG_MASS_RANGE_KG, rel_scale_sd: float = DEFAULT_SCALE_REL_SD,
                  draws: int = MC_DRAWS, seed: int = 0, board: Board = Board(), *, scale_state: str = "measured",
                  scale_reason: str | None = None, scale_basis: str | None = None, plane_reason: str | None = None,
                  extra_assumptions: tuple[str, ...] | list[str] = ()) -> dict[str, Any]:
    """Release state (p, KE, PE, E) and the drag-free flight model from (v, θ, h, distance to the board).

    Monte Carlo over the fit's standard errors (`se`: speed m/s, angle °, height m), a common scale
    factor N(1, `rel_scale_sd`) on speed, height and distance, and a uniform bag mass in `mass_range`.
    `to_front_m` (horizontal release → board front edge) None withholds the flight-model quantities.
    `scale_*` describe the calibration that scaled the release speed/height; `plane_reason` (throw line
    far out of the image plane) makes even the release angle "estimated".
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
    common = [scale_note, "Bag mass 15.5–16 oz (uniform); nominal value at 15.75 oz.", *extra_assumptions]
    metric_state, metric_reason = _cap("measured", None, scale_state, scale_reason)

    def metric(value, unit, formula, samples, extra=()) -> dict[str, Any]:
        return quantity(value, unit, metric_state, formula, reason=metric_reason, interval=_interval(samples),
                        assumptions=list(extra) + common)

    out = {
        "release_speed_m_s": metric(speed, "m/s", "|v| from the gravity-constrained ballistic flight fit", v,
                                    ["Fit standard error propagated."]),
        "release_angle_deg": quantity(angle_deg, "°", "estimated" if plane_reason else "measured",
                                      "atan2(v_y, v_x) from the flight fit", reason=plane_reason,
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
        return _with_inputs(out)
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
    return _with_inputs(out)


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
                release_scale: dict[str, Any] | None = None, plane_reason: str | None = None,
                si_reason: str | None = None, draws: int = MC_DRAWS, seed: int = 0) -> dict[str, Any]:
    """One throw's chain record. Every name in `QUANTITY_UNITS` is present in `quantities`.

    `joints_m` ("shoulder", "elbow", "wrist": (N, 2)) are board throw-plane metres (front edge x = 0,
    y above the floor), scaled by the board scale described by `scale_*`; None withholds the hand/bag
    mechanics with `joints_reason`. `release_scale` ({"state", "reason", "relative_sd", "basis",
    "source"}) describes the calibration that actually scaled the release speed/height — by default
    the same board scale. `si_reason` (the pipeline's physical-units gate: not a fixed side camera)
    withholds every metre-based quantity. `plane_reason` (φ > 20°) makes the release angle "estimated".
    """
    q: dict[str, Any] = dict(body_chain(angles, fps, forward_swing, release, wrist_speed))
    series: dict[str, Any] = {}
    notes = [BAG_ONLY_NOTE]
    rs = release_scale or {"state": scale_state, "reason": scale_reason, "relative_sd": scale_rel_sd,
                           "basis": scale_basis, "source": "board_throw_plane"}
    hand_reason = si_reason or joints_reason or "Throw-plane joint positions unavailable."
    hand = None
    if joints_m is not None and not si_reason:
        hand = hand_chain(joints_m["shoulder"], joints_m["elbow"], joints_m["wrist"], fps, forward_swing, release,
                          landmark_noise_m=landmark_noise_m, rel_scale_sd=scale_rel_sd, scale_state=scale_state,
                          scale_reason=scale_reason, draws=draws, seed=seed)
        q.update(hand["quantities"])
        series = hand["series"]
    else:
        notes.append(f"Hand/bag mechanics withheld: {hand_reason}")
    v, a, h = (release_values.get(k) for k in ("speed", "angle", "height"))
    release_reason = si_reason
    if si_reason is None and None not in (v, a, h):
        extra = []
        if rs.get("source") != "board_throw_plane" and joints_m is not None:
            extra.append(f"Release speed/height scaled by {rs.get('source')}, while joints and the distance to the "
                         "board use the board's throw-plane scale.")
        q.update(release_chain(v, a, h, to_front_m, release_se, rel_scale_sd=rs["relative_sd"], draws=draws,
                               seed=seed + 1, board=board, scale_state=rs["state"], scale_reason=rs["reason"],
                               scale_basis=rs.get("basis"), plane_reason=plane_reason, extra_assumptions=extra))
    elif si_reason is None:
        missing = [k for k, x in (("speed (m/s)", v), ("angle", a), ("height (m)", h)) if x is None]
        release_reason = f"Release {', '.join(missing)} not available from the flight fit."
    q["timing_sensitivity_in_per_10ms"] = _timing_quantity(
        hand, v, a, h, to_front_m, board, hand_reason if hand is None else release_reason,
        (scale_state, scale_reason), (rs["state"], rs["reason"]))
    if measured_along_error_m is not None and not si_reason:
        state, reason = _cap("measured", None, scale_state, scale_reason)
        q["measured_along_error_in"] = quantity(
            measured_along_error_m / INCH_M, "in", state,
            "observed first contact − hole centre along the throw line, in the board plane (+ = long)",
            reason=reason, assumptions=["Contact classified as observed on the deck/floor (contact.py)."])
    else:
        q["measured_along_error_in"] = _missing("in", "observed first contact − hole centre", si_reason or
                                                "First contact not observed on the deck or floor for this throw.")
    hand_keys = {"hand_speed_at_release_m_s", "hand_acceleration_at_release_m_s2", "peak_net_force_on_bag_n",
                 "mean_net_force_on_bag_n", "force_direction_at_peak_deg", "peak_power_on_bag_w",
                 "hand_velocity_angle_at_release_deg", "hand_tangential_acceleration_at_release_m_s2",
                 "hand_direction_rotation_rate_deg_s"}
    for name, unit in QUANTITY_UNITS.items():
        if name not in q:
            reason = (hand_reason if name in hand_keys else
                      release_reason or "Distance from release to the board is unknown.")
            q[name] = _missing(unit, name, reason)
    return {"quantities": _with_inputs({name: q[name] for name in QUANTITY_UNITS}), "series": series,
            "notes": notes,
            "scale": {"state": scale_state, "reason": scale_reason, "relative_sd": scale_rel_sd,
                      "basis": scale_basis, "applies_to": "joints, hand/bag mechanics, distance to the board"},
            "release_scale": {**rs, "applies_to": "release speed/height, momentum, energies, flight model"}}


def _timing_quantity(hand: dict[str, Any] | None, v, a, h, to_front_m, board: Board, missing_reason: str | None,
                     joint_scale: tuple[str, str | None], release_scale: tuple[str, str | None]) -> dict[str, Any]:
    """Release-timing sensitivity from the bag's fitted release and the hand path's rates at release."""
    unit, formula = "in / 10 ms", ("(∂R/∂v · dv/dt + ∂R/∂θ · dθ/dt + ∂R/∂h · dh/dt + ∂R/∂x · dx/dt) × 10 ms; Jacobian "
                                   "at the bag's fitted release, rates from the hand path at release")
    rates = None if hand is None else hand.get("release_rates")
    if rates is None or None in (v, a, h, to_front_m):
        why = missing_reason if hand is None else (
            "Hand path missing at release." if rates is None else
            "Bag release speed/angle/height or the distance to the board is unavailable.")
        return _missing(unit, formula, why or "Inputs unavailable.")
    nom = rates["nominal"]
    if not all(isinstance(x, (int, float)) and math.isfinite(x) for x in
               (nom.get("angle_deg"), nom.get("tangential_m_s2"), nom.get("rotation_deg_s"), nom.get("vx"),
                nom.get("vy"), v, a, h, to_front_m)):
        # A NaN direction would make the angle gate below compare False and pass silently.
        return _missing(unit, formula, "The hand path's direction or rates at release are not finite (stationary "
                        "or missing hand path), so its rates cannot stand in for the bag's.")
    diff = (nom["angle_deg"] - a + 180.0) % 360.0 - 180.0
    if abs(diff) > MAX_HAND_BAG_ANGLE_DIFF_DEG:
        return _missing(unit, formula, f"The hand path at release points {nom['angle_deg']:.0f}° but the bag left at "
                        f"{a:.0f}° (difference {diff:+.0f}°, > {MAX_HAND_BAG_ANGLE_DIFF_DEG:.0f}°), so the hand's "
                        "rates cannot stand in for the bag's.")
    out = timing_sensitivity_from_rates(v, a, h, to_front_m, nom["tangential_m_s2"], nom["rotation_deg_s"],
                                        nom["vy"], nom["vx"], board)
    if out is None:
        return _missing(unit, formula, "Landing Jacobian undefined at this release (path misses the deck plane).")
    interval = None
    draws = rates.get("draws")
    if draws:
        mc = timing_sensitivity_from_rates(v, a, h, to_front_m, draws["tangential_m_s2"], draws["rotation_deg_s"],
                                           draws["vy"], draws["vx"], board)
        interval = None if mc is None else _interval(np.asarray(mc["total"]) / INCH_M)
    state, reason = _cap("estimated", "Rates from the hand path at release; drag-free flight.", *joint_scale)
    if release_scale[0] != "measured" and joint_scale[0] == "measured":
        state, reason = _cap(state, reason, *release_scale)
    item = quantity(out["total"] / INCH_M, unit, state, formula, reason=reason, interval=interval,
                    assumptions=["Hand path's rates at the release frame stand in for the bag's rate of change of "
                                 "release conditions (Nasu et al. 2014; Venkadesan & Mahadevan 2017).",
                                 f"Used only when the hand-path direction is within {MAX_HAND_BAG_ANGLE_DIFF_DEG:.0f}° "
                                 "of the bag's fitted release angle.", "Drag-free flight."])
    item["terms_in"] = {k: out[k] / INCH_M for k in ("speed", "angle", "height", "position")}
    item["hand_minus_bag_angle_deg"] = diff
    return item


def flatten_for_summaries(chain: dict[str, Any]) -> dict[str, float | None]:
    out = {}
    for name, item in chain["quantities"].items():
        value = item["value"] if item["state"] != "unavailable" else None
        out[f"chain_{name}"] = value if not isinstance(value, str) else None
    return out
