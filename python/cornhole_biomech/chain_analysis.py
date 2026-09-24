"""Within-athlete analyses linking the chain to performance (spec §6).

All variables are pre-specified (lists below), claims are associational, and each
block reports `status` so the UI never shows a finding without enough throws.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy import stats

from .mechanics import error_budget, landing_jacobian
from .performance import cliffs_delta, critical_delta, group_label
from .regulation import INCH_M, Board

MIN_THROWS = 8
MIN_PER_GROUP = 5
BOOTSTRAP = 2000
BODY_RELEASE_PAIRS = (
    ("chain_elbow_peak_extension_velocity_deg_s", "chain_release_speed_m_s"),
    ("chain_shoulder_peak_angular_velocity_deg_s", "chain_release_speed_m_s"),
    ("chain_shoulder_angle_at_release_deg", "chain_release_angle_deg"),
    ("chain_elbow_angle_at_release_deg", "chain_release_angle_deg"),
    ("chain_hand_speed_at_release_m_s", "chain_release_speed_m_s"),
)
OUTCOME_VARIABLES = (
    "chain_release_speed_m_s", "chain_release_angle_deg", "chain_release_height_m", "chain_energy_match_percent",
    "chain_timing_sensitivity_in_per_10ms", "chain_elbow_peak_extension_velocity_deg_s",
    "chain_shoulder_peak_angular_velocity_deg_s",
)
LABELS = {
    "chain_elbow_peak_extension_velocity_deg_s": "peak elbow extension velocity",
    "chain_shoulder_peak_angular_velocity_deg_s": "peak shoulder angular velocity",
    "chain_shoulder_angle_at_release_deg": "shoulder angle at release",
    "chain_elbow_angle_at_release_deg": "elbow angle at release",
    "chain_hand_speed_at_release_m_s": "hand speed at release",
    "chain_release_speed_m_s": "release speed", "chain_release_angle_deg": "release angle",
    "chain_release_height_m": "release height", "chain_energy_match_percent": "energy match",
    "chain_timing_sensitivity_in_per_10ms": "release-timing sensitivity",
}


def _pairs(rows, x, y):
    xs, ys = [], []
    for r in rows:
        a, b = r.get(x), r.get(y)
        if a is not None and b is not None and math.isfinite(a) and math.isfinite(b):
            xs.append(a); ys.append(b)
    return np.array(xs, float), np.array(ys, float)


def _insufficient(n, need=MIN_THROWS, **extra):
    return {"status": "insufficient_data", "n": int(n), "message": f"Needs ≥ {need} throws with these values (has {n}).",
            **extra}


def error_budget_analysis(rows, board: Board = Board()) -> dict[str, Any]:
    keys = ("chain_release_speed_m_s", "chain_release_angle_deg", "chain_release_height_m", "release_to_board_front_m")
    usable = [r for r in rows if all(r.get(k) is not None for k in keys)]
    if len(usable) < MIN_THROWS:
        return _insufficient(len(usable))
    arr = {k: np.array([r[k] for r in usable], float) for k in keys}
    center = {k: float(np.median(v)) for k, v in arr.items()}
    jac = landing_jacobian(center[keys[0]], center[keys[1]], center[keys[2]], center[keys[3]], board)
    sd = {"speed": float(np.std(arr[keys[0]], ddof=1)), "angle": float(np.std(arr[keys[1]], ddof=1)),
          "height": float(np.std(arr[keys[2]], ddof=1))}
    budget = error_budget(jac, sd)
    measured = [r["chain_measured_along_error_in"] for r in usable if r.get("chain_measured_along_error_in") is not None]
    top = max(budget["shares"], key=budget["shares"].get)
    return {"status": "available", "n": len(usable), "jacobian": jac, "sd": sd, **budget,
            "predicted_sd_in": budget["predicted_sd_m"] / INCH_M,
            "measured_sd_in": float(np.std(measured, ddof=1)) if len(measured) >= 3 else None,
            "sentence": (f"About {100 * budget['shares'][top]:.0f}% of the landing spread explained by release "
                         f"comes from variation in release {top}."),
            "method": "Jacobian of drag-free landing w.r.t. release speed, angle, height (Venkadesan & Mahadevan 2017)."}


def predicted_vs_measured(rows) -> dict[str, Any]:
    p, m = _pairs(rows, "chain_predicted_along_error_in", "chain_measured_along_error_in")
    if len(p) < MIN_THROWS:
        return _insufficient(len(p))
    r = float(np.corrcoef(p, m)[0, 1]) if np.std(p) > 0 and np.std(m) > 0 else 0.0
    return {"status": "available", "n": len(p), "r_squared": r * r, "mean_offset_in": float(np.mean(m - p)),
            "sentence": (f"Release conditions explain {100 * r * r:.0f}% of the measured landing variation; the rest "
                         "reflects bag slide, air drag and measurement error.")}


def _spearman_ci(x, y, seed):
    rng = np.random.default_rng(seed)
    n = len(x)
    boots = []
    for _ in range(BOOTSTRAP):
        idx = rng.integers(0, n, n)
        if np.ptp(x[idx]) == 0 or np.ptp(y[idx]) == 0:
            continue
        boots.append(stats.spearmanr(x[idx], y[idx]).statistic)
    return [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))] if boots else None


def body_release_links(rows, seed: int = 0) -> list[dict[str, Any]]:
    out = []
    for x, y in BODY_RELEASE_PAIRS:
        a, b = _pairs(rows, x, y)
        if len(a) < MIN_THROWS or np.ptp(a) == 0 or np.ptp(b) == 0:
            out.append({"x": x, "y": y, **_insufficient(len(a))})
            continue
        rho = float(stats.spearmanr(a, b).statistic)
        ci = _spearman_ci(a, b, seed)
        clear = ci is not None and (ci[0] > 0 or ci[1] < 0)
        direction = "higher" if rho > 0 else "lower"
        sentence = (f"Throws with higher {LABELS[x]} were associated with {direction} {LABELS[y]} "
                    f"(ρ = {rho:.2f}, 95% CI {ci[0]:.2f} to {ci[1]:.2f})." if clear else
                    f"No clear association between {LABELS[x]} and {LABELS[y]} (ρ = {rho:.2f}).")
        out.append({"x": x, "y": y, "status": "available", "n": len(a), "rho": rho, "ci": ci, "clear": clear,
                    "sentence": sentence})
    return out


def outcome_links(rows) -> list[dict[str, Any]]:
    out = []
    for key in OUTCOME_VARIABLES:
        scored = np.array([r[key] for r in rows if r.get(key) is not None and group_label(r.get("score_category")) == "scored"], float)
        miss = np.array([r[key] for r in rows if r.get(key) is not None and group_label(r.get("score_category")) == "miss"], float)
        err_x, err_y = _pairs(rows, key, "chain_measured_along_error_in")
        item: dict[str, Any] = {"variable": key, "label": LABELS[key], "n_scored": len(scored), "n_miss": len(miss)}
        if len(scored) >= MIN_PER_GROUP and len(miss) >= MIN_PER_GROUP:
            delta = cliffs_delta(miss, scored)
            threshold = critical_delta(len(miss), len(scored), comparisons=len(OUTCOME_VARIABLES))
            item.update(cliffs_delta=delta, critical_delta=threshold, distinguishes=abs(delta) >= threshold)
        else:
            item.update(cliffs_delta=None, distinguishes=None,
                        group_message=f"Needs ≥ {MIN_PER_GROUP} scored and ≥ {MIN_PER_GROUP} missed throws.")
        if len(err_x) >= MIN_THROWS and np.ptp(err_x) > 0 and np.ptp(err_y) > 0:
            item["rho_abs_landing_error"] = float(stats.spearmanr(err_x, np.abs(err_y)).statistic)
        item["status"] = "available" if item.get("cliffs_delta") is not None or "rho_abs_landing_error" in item \
            else "insufficient_data"
        out.append(item)
    return out


def speed_angle_tradeoff(rows) -> dict[str, Any]:
    angle, speed = _pairs(rows, "chain_release_angle_deg", "chain_release_speed_m_s")
    if len(angle) < MIN_THROWS or np.ptp(angle) == 0:
        return _insufficient(len(angle))
    slope, intercept, lo, hi = stats.theilslopes(speed, angle)
    rho = float(stats.spearmanr(angle, speed).statistic)
    return {"status": "available", "n": len(angle), "slope_m_s_per_deg": float(slope), "slope_ci": [float(lo), float(hi)],
            "rho": rho, "sentence": f"Each extra degree of release angle came with {slope:+.2f} m/s of release speed "
                                    "(Linthorne 2001: the best angle is individual)."}


def coordination_variability(curves: list[np.ndarray]) -> dict[str, Any]:
    if len(curves) < 3:
        return _insufficient(len(curves), need=3)
    stack = np.stack([np.asarray(c, float) for c in curves])      # throws x 101 x 2
    mean = np.nanmean(stack, axis=0)
    sd = np.sqrt(np.nanvar(stack[..., 0], axis=0, ddof=1) + np.nanvar(stack[..., 1], axis=0, ddof=1))
    rms = np.sqrt(np.nanmean(np.sum((stack - mean) ** 2, axis=2), axis=1))
    return {"status": "available", "n": len(curves), "mean_sd_deg": float(np.nanmean(sd)),
            "rms_from_mean_deg": rms.tolist(),
            "method": "Point-wise SD of the shoulder–elbow angle–angle curve over the time-normalised forward swing."}


def summarize(rows, curves: list[np.ndarray] | None = None) -> dict[str, Any]:
    return {"error_budget": error_budget_analysis(rows), "predicted_vs_measured": predicted_vs_measured(rows),
            "body_release": body_release_links(rows), "outcome": outcome_links(rows),
            "speed_angle_tradeoff": speed_angle_tradeoff(rows),
            "coordination": coordination_variability(curves or []),
            "wording": "Associations within this athlete's throws; not causes."}
