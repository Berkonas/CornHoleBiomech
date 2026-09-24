"""Within-athlete analyses linking the chain to performance (spec §6).

All variables are pre-specified (lists below), claims are associational, and each
block reports `status` so the UI never shows a finding without enough throws.
"""
from __future__ import annotations

import math
import warnings
from typing import Any

import numpy as np
from scipy import stats

from .mechanics import error_budget, landing_jacobian
from .performance import cliffs_delta, critical_delta, group_label
from .regulation import INCH_M, Board

MIN_THROWS = 8
MIN_PER_GROUP = 5
BOOTSTRAP = 2000
COVARIATION_MATERIAL = 0.15   # covariation_reduction above this is called out in the sentence
BODY_RELEASE_PAIRS = (
    ("chain_elbow_peak_extension_velocity_deg_s", "chain_release_speed_m_s"),
    ("chain_shoulder_peak_angular_velocity_deg_s", "chain_release_speed_m_s"),
    ("chain_shoulder_angle_at_release_deg", "chain_release_angle_deg"),
    ("chain_elbow_angle_at_release_deg", "chain_release_angle_deg"),
    ("chain_hand_speed_at_release_m_s", "chain_release_speed_m_s"),
)
# The bag is in the hand at release, so hand speed vs release speed is near-tautological
# (mostly shared measurement geometry, not an independent movement finding).
NEAR_TAUTOLOGICAL_PAIRS = {"chain_hand_speed_at_release_m_s"}
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


def _finite(v: Any) -> bool:
    return v is not None and isinstance(v, (int, float)) and math.isfinite(v)


def _pairs(rows, x, y):
    xs, ys = [], []
    for r in rows:
        a, b = r.get(x), r.get(y)
        if _finite(a) and _finite(b):
            xs.append(a); ys.append(b)
    return np.array(xs, float), np.array(ys, float)


def _insufficient(n, need=MIN_THROWS, **extra):
    return {"status": "insufficient_data", "n": int(n), "message": f"Needs ≥ {need} throws with these values (has {n}).",
            **extra}


def error_budget_analysis(rows, board: Board = Board()) -> dict[str, Any]:
    """Share of the drag-free model's landing spread from release speed/angle/height.

    The headline `predicted_sd_in` is the SD, across throws, of each throw's OWN release
    condition run through the drag-free model (`chain_predicted_along_error_in`; nonlinear, no
    independence assumption). Next to it: `predicted_sd_cov_in`, a linearised check
    (sqrt(J Sigma J^T) using the empirical release covariance Sigma), and `independent_sd_in`,
    the same Jacobian but assuming speed/angle/height vary independently — the gap between the
    two is `covariation_reduction`. `shares_if_independent` describes only the independent-
    variable hypothetical, never stated as the athlete's actual landing-spread breakdown.
    """
    keys = ("chain_release_speed_m_s", "chain_release_angle_deg", "chain_release_height_m", "release_to_board_front_m")
    var_names = ("speed", "angle", "height", "distance")
    usable = [r for r in rows if all(_finite(r.get(k)) for k in keys)]
    if len(usable) < MIN_THROWS:
        return _insufficient(len(usable))
    arr = {name: np.array([r[k] for r in usable], float) for name, k in zip(var_names, keys)}
    center = {name: float(np.mean(v)) for name, v in arr.items()}   # spec: mean release condition
    jac = landing_jacobian(center["speed"], center["angle"], center["height"], center["distance"], board)
    if not all(math.isfinite(v) for v in jac.values()):
        return {"status": "model_unavailable", "n": len(usable),
                "reason": "Landing Jacobian is non-finite at the mean release condition (too close to a model "
                          "singularity — e.g. a near-zero or negative approach speed)."}
    sd = {"speed": float(np.std(arr["speed"], ddof=1)), "angle": float(np.std(arr["angle"], ddof=1)),
          "height": float(np.std(arr["height"], ddof=1))}
    cov = np.cov(np.stack([arr["speed"], arr["angle"], arr["height"]]), ddof=1)   # 3x3, order speed/angle/height
    j_vec = np.array([jac["d_speed"], jac["d_angle"], jac["d_height"]])
    independent = error_budget(jac, sd)
    independent_sd_m = independent["predicted_sd_m"]
    cov_var_m2 = float(j_vec @ cov @ j_vec)
    predicted_sd_cov_m = math.sqrt(max(cov_var_m2, 0.0))
    covariation_reduction = (1 - predicted_sd_cov_m / independent_sd_m) if independent_sd_m > 0 else None

    predicted_vals = [r["chain_predicted_along_error_in"] for r in usable
                       if _finite(r.get("chain_predicted_along_error_in"))]
    predicted_n = len(predicted_vals)
    predicted_sd_in = float(np.std(predicted_vals, ddof=1)) if predicted_n >= 2 else None

    matched_measured = [r["chain_measured_along_error_in"] for r in usable
                         if _finite(r.get("chain_predicted_along_error_in")) and _finite(r.get("chain_measured_along_error_in"))]
    measured_n = len(matched_measured)
    measured_sd_in = float(np.std(matched_measured, ddof=1)) if measured_n >= 3 else None

    top = max(independent["shares"], key=independent["shares"].get)
    sentence = (f"If speed, angle and height varied independently, {top} variation would account for about "
                f"{100 * independent['shares'][top]:.0f}% of the model's landing spread.")
    covariance_shares = None
    idx = {"speed": 0, "angle": 1, "height": 2}
    if independent_sd_m > 0 and cov_var_m2 != 0:
        sigma_j = cov @ j_vec
        covariance_shares = {name: float(j_vec[i] * sigma_j[i] / cov_var_m2) for name, i in idx.items()}
    if covariation_reduction is not None and covariation_reduction > COVARIATION_MATERIAL:
        pairs = (("speed", "angle"), ("speed", "height"), ("angle", "height"))
        cross = {(a, b): 2 * j_vec[idx[a]] * j_vec[idx[b]] * cov[idx[a], idx[b]] for a, b in pairs}
        dom_a, dom_b = min(cross, key=cross.get)
        sentence += (f" Release {dom_a} and {dom_b} co-varied in a way associated with about "
                     f"{100 * covariation_reduction:.0f}% less landing spread than if they had varied independently.")

    return {
        "status": "available", "n": len(usable), "center": "mean", "release_center": center,
        "jacobian": jac, "sd": sd,
        "shares_if_independent": independent["shares"], "components_if_independent_m": independent["components_m"],
        "covariance_shares": covariance_shares,
        "independent_sd_in": independent_sd_m / INCH_M,
        "predicted_sd_cov_in": predicted_sd_cov_m / INCH_M,
        "covariation_reduction": covariation_reduction,
        "predicted_sd_in": predicted_sd_in, "predicted_n": predicted_n,
        "measured_sd_in": measured_sd_in, "measured_n": measured_n,
        "sentence": sentence,
        "method": ("predicted_sd_in: SD across throws of each throw's own release speed/angle/height/distance run "
                   "through the drag-free model (Venkadesan & Mahadevan 2017). predicted_sd_cov_in: linearised "
                   "check, sqrt(J Sigma J^T) with the empirical release covariance. independent_sd_in: the same "
                   "Jacobian assuming speed/angle/height vary independently (ignores observed covariation); "
                   "covariance_shares can be negative when a pair's covariation reduces landing spread."),
    }


def predicted_vs_measured(rows) -> dict[str, Any]:
    p, m = _pairs(rows, "chain_predicted_along_error_in", "chain_measured_along_error_in")
    if len(p) < MIN_THROWS:
        return _insufficient(len(p))
    if np.std(p) == 0 or np.std(m) == 0:
        return _insufficient(len(p), message="Predicted or measured landing error has zero variance in this set; "
                                             "correlation is undefined.")
    r = float(np.corrcoef(p, m)[0, 1])
    return {"status": "available", "n": len(p), "r_squared": r * r, "mean_offset_in": float(np.mean(m - p)),
            "r_squared_note": "Pearson r^2 (squared correlation), not 1 - SSE/SST; the two coincide only when the "
                              "predictions are an unbiased linear fit to the measured values.",
            "sentence": (f"Release conditions explain {100 * r * r:.0f}% of the measured landing variation; the "
                         "remainder is attributed to (not separated here) bag slide, air drag and measurement error.")}


def _spearman_ci(x, y, seed, alpha: float = 0.05):
    rng = np.random.default_rng(seed)
    n = len(x)
    boots = []
    for _ in range(BOOTSTRAP):
        idx = rng.integers(0, n, n)
        if np.ptp(x[idx]) == 0 or np.ptp(y[idx]) == 0:
            continue
        boots.append(stats.spearmanr(x[idx], y[idx]).statistic)
    if not boots:
        return None
    lo, hi = 100 * alpha / 2, 100 * (1 - alpha / 2)
    return [float(np.percentile(boots, lo)), float(np.percentile(boots, hi))]


def body_release_links(rows, seed: int = 0) -> list[dict[str, Any]]:
    alpha = 0.05 / len(BODY_RELEASE_PAIRS)   # Bonferroni across the 5 pre-specified pairs
    out = []
    for x, y in BODY_RELEASE_PAIRS:
        a, b = _pairs(rows, x, y)
        if len(a) < MIN_THROWS or np.ptp(a) == 0 or np.ptp(b) == 0:
            item = {"x": x, "y": y, **_insufficient(len(a))}
        else:
            rho = float(stats.spearmanr(a, b).statistic)
            ci = _spearman_ci(a, b, seed, alpha=alpha)
            clear = ci is not None and (ci[0] > 0 or ci[1] < 0)
            direction = "higher" if rho > 0 else "lower"
            sentence = (f"Throws with higher {LABELS[x]} were associated with {direction} {LABELS[y]} "
                        f"(ρ = {rho:.2f}, {100 * (1 - alpha):.1f}% CI {ci[0]:.2f} to {ci[1]:.2f})." if clear else
                        f"No clear association between {LABELS[x]} and {LABELS[y]} (ρ = {rho:.2f}).")
            item = {"x": x, "y": y, "status": "available", "n": len(a), "rho": rho, "ci": ci, "clear": clear,
                    "sentence": sentence}
        if x in NEAR_TAUTOLOGICAL_PAIRS:
            item["caveat"] = ("Near-tautological: the bag is in the hand at release, so this mostly reflects "
                              "measurement geometry rather than an independent movement finding.")
        out.append(item)
    return out


def outcome_links(rows, seed: int = 0) -> list[dict[str, Any]]:
    alpha = 0.05 / len(OUTCOME_VARIABLES)   # Bonferroni across the pre-specified outcome variables
    out = []
    for key in OUTCOME_VARIABLES:
        scored = np.array([r[key] for r in rows if r.get(key) is not None and group_label(r.get("score_category")) == "scored"], float)
        miss = np.array([r[key] for r in rows if r.get(key) is not None and group_label(r.get("score_category")) == "miss"], float)
        err_x, err_y = _pairs(rows, key, "chain_measured_along_error_in")
        item: dict[str, Any] = {"variable": key, "label": LABELS[key], "n_scored": len(scored), "n_miss": len(miss),
                                "delta_orientation": "scored_minus_miss"}
        if len(scored) >= MIN_PER_GROUP and len(miss) >= MIN_PER_GROUP:
            delta = cliffs_delta(scored, miss)
            threshold = critical_delta(len(scored), len(miss), comparisons=len(OUTCOME_VARIABLES))
            distinguishes = bool(abs(delta) >= threshold)
            item.update(cliffs_delta=delta, critical_delta=threshold, distinguishes=distinguishes)
            if distinguishes:
                direction = "higher" if delta > 0 else "lower"
                item["outcome_sentence"] = (f"Scored throws were associated with {direction} {LABELS[key]} than "
                                            f"misses (Cliff's δ = {delta:.2f}, scored − miss).")
        else:
            item.update(cliffs_delta=None, distinguishes=None,
                        group_message=f"Needs ≥ {MIN_PER_GROUP} scored and ≥ {MIN_PER_GROUP} missed throws.")
        if len(err_x) >= MIN_THROWS and np.ptp(err_x) > 0 and np.ptp(err_y) > 0:
            abs_err = np.abs(err_y)
            rho = float(stats.spearmanr(err_x, abs_err).statistic)
            ci = _spearman_ci(err_x, abs_err, seed, alpha=alpha)
            clear = ci is not None and (ci[0] > 0 or ci[1] < 0)
            item["rho_abs_landing_error"] = rho
            item["rho_abs_landing_error_ci"] = ci
            item["rho_abs_landing_error_clear"] = clear
            if clear:
                trend = "larger" if rho > 0 else "smaller"
                item["rho_abs_landing_error_sentence"] = (
                    f"Higher {LABELS[key]} was associated with {trend} landing error (ρ = {rho:.2f}, "
                    f"{100 * (1 - alpha):.1f}% CI {ci[0]:.2f} to {ci[1]:.2f}).")
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
    clear = bool(lo > 0 or hi < 0)
    sentence = (f"Each extra degree of release angle was associated with {slope:+.2f} m/s of release speed "
                "(Linthorne 2001: the best angle is individual)." if clear else
                "No clear speed-angle trade-off (the Theil-Sen slope's 95% CI includes 0).")
    return {"status": "available", "n": len(angle), "slope_m_s_per_deg": float(slope), "slope_ci": [float(lo), float(hi)],
            "rho": rho, "clear": clear, "sentence": sentence}


def coordination_variability(curves: list[np.ndarray], trial_ids: list[str] | None = None) -> dict[str, Any]:
    """Point-wise SD of the stacked shoulder/elbow angle–angle curves (throws x 101 x 2).

    Curves with more than 20% missing samples are dropped before averaging. `rms_from_mean_deg`
    maps each KEPT throw's trial_id to its RMS deviation from the athlete's mean curve.
    """
    ids = list(trial_ids) if trial_ids is not None else [f"throw_{i}" for i in range(len(curves))]
    kept, kept_ids = [], []
    for c, tid in zip(curves, ids):
        arr = np.asarray(c, float)
        if arr.size == 0 or np.isnan(arr).mean() > 0.20:
            continue
        kept.append(arr)
        kept_ids.append(tid)
    if len(kept) < MIN_THROWS:
        return _insufficient(len(kept), need=MIN_THROWS)
    stack = np.stack(kept)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)   # all-NaN columns are possible at curve edges
        mean = np.nanmean(stack, axis=0)
        sd = np.sqrt(np.nanvar(stack[..., 0], axis=0, ddof=1) + np.nanvar(stack[..., 1], axis=0, ddof=1))
        rms = np.sqrt(np.nanmean(np.sum((stack - mean) ** 2, axis=2), axis=1))
    return {"status": "available", "n": len(kept), "trial_ids": kept_ids,
            "mean_sd_deg": float(np.nanmean(sd)),
            "rms_from_mean_deg": {tid: float(r) for tid, r in zip(kept_ids, rms)},
            "method": "Point-wise SD of the shoulder–elbow angle–angle curve over the time-normalised forward swing."}


def summarize(rows, curves: list[np.ndarray] | None = None, curve_trial_ids: list[str] | None = None,
             seed: int = 0) -> dict[str, Any]:
    return {"error_budget": error_budget_analysis(rows), "predicted_vs_measured": predicted_vs_measured(rows),
            "body_release": body_release_links(rows, seed=seed), "outcome": outcome_links(rows, seed=seed),
            "speed_angle_tradeoff": speed_angle_tradeoff(rows),
            "coordination": coordination_variability(curves or [], curve_trial_ids),
            "wording": "Associations within this athlete's throws; not causes."}
