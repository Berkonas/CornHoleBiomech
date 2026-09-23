"""Within-athlete scored-versus-miss comparison and plain-language coaching feedback.

Design rules:
- Success is "scored" (bag value 1 or 3) versus "miss" (0); unknown outcomes
  are excluded, never treated as misses. Hole versus board is reported as counts.
- A short, fixed list of release variables is examined, chosen before looking at
  data, to limit chance findings from testing many variables.
- Effect size is Cliff's delta (rank-based, robust for 5–15 throws per group).
  |δ| ≥ 0.474 is "large" (Romano et al., 2006). A variable is only said to
  distinguish outcomes with ≥ 5 throws per group, a large effect, AND a median
  difference larger than that variable's measurement noise floor.
- Wording is associational ("associated with", "were released"), never causal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
from scipy.stats import norm

MIN_DESCRIPTIVE_PER_GROUP = 3
MIN_CLAIM_PER_GROUP = 5
LARGE_EFFECT = 0.474  # Romano et al. (2006) threshold for a large Cliff's delta
VARIABILITY_RATIO = 1.5  # SD ratio treated as a noteworthy consistency difference


@dataclass(frozen=True)
class Variable:
    key: str
    label: str
    unit: str
    lower_word: str
    higher_word: str
    decimals: int
    ratio_scale: bool          # CV is meaningful only for positive ratio-scale data
    noise_floor: float | None  # smallest difference we are willing to interpret
    noise_source: str


# Provisional noise floors, to be replaced by tracking-validation results
# (docs/VALIDATION_PROTOCOL.md). Elbow: simulated 4 px landmark noise at pilot
# framing gives ~10° SD. Trunk: longer segment, ~5°. Positions: ~3–4 px bag
# centroid noise over a ~115 px arm length. Duration: ±2 frames at 60 fps plus
# heuristic onset. Release angle uses the per-throw fit standard error instead.
VARIABLES: tuple[Variable, ...] = (
    Variable("bag_release_angle_deg", "Release angle", "°", "lower", "higher", 0, False, 3.0,
             "2 × median per-throw fit standard error (3° if unavailable)"),
    Variable("bag_release_speed_m_s", "Release speed", "m/s", "slower", "faster", 2, True, 0.15,
             "~2 × typical fit standard error at 60 fps"),
    Variable("bag_release_speed_arm_lengths_s", "Release speed", "arm lengths/s", "slower", "faster", 2, True, 0.2,
             "~2 × typical fit standard error at 60 fps"),
    Variable("bag_release_height_m", "Release height", "m", "lower", "higher", 2, True, 0.03,
             "bag centroid and foot-landmark noise"),
    Variable("bag_release_height_arm_lengths", "Release height", "arm lengths", "lower", "higher", 2, True, 0.05,
             "bag centroid and foot-landmark noise"),
    Variable("bag_release_position_forward_arm_lengths", "Release point (forward of shoulder)", "arm lengths",
             "further back", "further forward", 2, False, 0.05, "bag centroid and shoulder landmark noise"),
    Variable("swing_release_arm_angle_deg", "Arm angle at release", "°", "lower (earlier) arm", "higher (later) arm", 0,
             False, 5.0, "~4 px landmark noise over a ~100 px shoulder–wrist line (≈3°), rounded up"),
    Variable("swing_peak_angular_velocity_deg_s", "Peak arm swing speed", "°/s", "slower", "faster", 0, True, 40.0,
             "arm-angle noise differentiated at 60 fps after the 6 Hz filter"),
    Variable("swing_backswing_angle_deg", "Backswing height", "°", "bigger (further back)", "smaller", 0, False, 5.0,
             "same arm-angle noise as release arm angle"),
    Variable("swing_tempo_ratio", "Tempo (backswing ÷ forward swing)", "", "quicker backswing", "slower backswing", 2,
             True, 0.15, "±2 frames on each phase boundary at 60 fps"),
    Variable("elbow_angle_deg_at_release", "Elbow angle at release", "°", "more bent", "straighter", 0, False, 10.0,
             "simulated 4 px landmark noise at pilot framing; replace with validation"),
    Variable("trunk_inclination_deg_at_release", "Trunk lean at release", "°", "more upright", "more forward", 0,
             False, 5.0, "simulated landmark noise on the hip–shoulder segment; replace with validation"),
)
# Same quantity in two unit systems: prefer meters when most throws have them.
ALTERNATIVES = (("bag_release_speed_m_s", "bag_release_speed_arm_lengths_s"),
                ("bag_release_height_m", "bag_release_height_arm_lengths"))


def group_label(score: int | None) -> str | None:
    """Success definition: scored (1 or 3) versus miss (0); unknown stays unknown."""
    if score in (1, 3):
        return "scored"
    if score == 0:
        return "miss"
    return None


def cliffs_delta(a: Iterable[float], b: Iterable[float]) -> float:
    """P(a > b) − P(a < b) over all pairs; +1 means every a exceeds every b."""
    x, y = np.asarray(list(a), float), np.asarray(list(b), float)
    diff = x[:, None] - y[None, :]
    return float((np.sum(diff > 0) - np.sum(diff < 0)) / diff.size)


def hedges_g(a: Iterable[float], b: Iterable[float]) -> float | None:
    """Standardized mean difference (a − b) with the small-sample correction J."""
    x, y = np.asarray(list(a), float), np.asarray(list(b), float)
    n1, n2 = len(x), len(y)
    if n1 < 2 or n2 < 2:
        return None
    pooled = np.sqrt(((n1 - 1) * x.var(ddof=1) + (n2 - 1) * y.var(ddof=1)) / (n1 + n2 - 2))
    if pooled <= 0:
        return None
    return float((x.mean() - y.mean()) / pooled * (1 - 3 / (4 * (n1 + n2) - 9)))


def _describe(values: np.ndarray, ratio_scale: bool) -> dict[str, Any]:
    n = len(values)
    mean = float(np.mean(values)) if n else None
    sd = float(np.std(values, ddof=1)) if n > 1 else None
    return {
        "n": n, "mean": mean, "median": float(np.median(values)) if n else None, "sd": sd,
        "cv_percent": 100 * sd / mean if ratio_scale and sd is not None and mean and mean > 0 else None,
        "min": float(np.min(values)) if n else None, "max": float(np.max(values)) if n else None,
        "q25": float(np.percentile(values, 25)) if n else None,
        "q75": float(np.percentile(values, 75)) if n else None,
    }


def _values(rows: list[dict[str, Any]], key: str, group: str | None = None) -> np.ndarray:
    data = [r.get(key) for r in rows if group is None or group_label(r.get("score_category")) == group]
    a = np.asarray([v for v in data if v is not None], float)
    return a[np.isfinite(a)]


def _selected_variables(rows: list[dict[str, Any]]) -> list[Variable]:
    skip: set[str] = set()
    for preferred, fallback in ALTERNATIVES:
        # Use meters only when at least half of the throws have them.
        skip.add(fallback if len(_values(rows, preferred)) * 2 >= max(1, len(rows)) else preferred)
    return [v for v in VARIABLES if v.key not in skip and len(_values(rows, v.key))]


def _noise_floor(variable: Variable, rows: list[dict[str, Any]]) -> float | None:
    if variable.key == "bag_release_angle_deg":
        se = _values(rows, "bag_release_angle_se_deg")
        if se.size:
            return float(2 * np.median(se))
    return variable.noise_floor


def _fmt(value: float | None, variable: Variable) -> str:
    if value is None:
        return "—"
    return f"{value:.{variable.decimals}f}"


def _unit(unit: str) -> str:
    """Degrees attach to the number (35°); other units take a space (6.4 m/s); ratios have none."""
    return unit if unit in ("°", "") else f" {unit}"


def critical_delta(n1: int, n2: int, comparisons: int, alpha: float = 0.05) -> float:
    """Smallest |Cliff's δ| unlikely by chance, family-wise across `comparisons` tests.

    Under no difference, δ has variance (n1 + n2 + 1) / (3 n1 n2) (the Mann–Whitney
    null distribution rescaled). A Bonferroni two-sided z keeps the chance of any
    false claim across all tested variables near `alpha`. Never below the 0.474
    "large" threshold, so small but "significant" differences are not reported either.
    """
    if n1 < 1 or n2 < 1:
        return 1.0
    z = float(norm.ppf(1 - alpha / (2 * max(1, comparisons))))
    return max(LARGE_EFFECT, z * np.sqrt((n1 + n2 + 1) / (3 * n1 * n2)))


def _deviation_from_scored_center(scored: np.ndarray, miss: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """|value − median of scored throws|; each scored throw uses the median of the OTHER scored throws."""
    loo = np.array([abs(v - np.median(np.delete(scored, i))) for i, v in enumerate(scored)]) if len(scored) > 1 else np.array([])
    return loo, np.abs(miss - np.median(scored)) if len(scored) else np.array([])


def _analyze_variable(variable: Variable, rows: list[dict[str, Any]], comparisons: int = 1) -> dict[str, Any]:
    scored, miss = _values(rows, variable.key, "scored"), _values(rows, variable.key, "miss")
    everything = _values(rows, variable.key)
    floor = _noise_floor(variable, rows)
    enough = len(scored) >= MIN_DESCRIPTIVE_PER_GROUP and len(miss) >= MIN_DESCRIPTIVE_PER_GROUP
    delta = cliffs_delta(scored, miss) if enough else None
    median_difference = float(np.median(miss) - np.median(scored)) if len(scored) and len(miss) else None
    below_floor = (median_difference is not None and floor is not None and abs(median_difference) < floor)
    claimable = len(scored) >= MIN_CLAIM_PER_GROUP and len(miss) >= MIN_CLAIM_PER_GROUP
    threshold = critical_delta(len(scored), len(miss), comparisons)
    distinguishes = bool(delta is not None and claimable and abs(delta) >= threshold and not below_floor)
    # Two-sided effects (too high AND too low both miss) do not shift the median;
    # they show up as misses lying further from the athlete's scored release.
    dev_scored, dev_miss = _deviation_from_scored_center(scored, miss) if enough else (np.array([]), np.array([]))
    spread_delta = cliffs_delta(dev_miss, dev_scored) if len(dev_scored) and len(dev_miss) else None
    spread_gap = float(np.median(dev_miss) - np.median(dev_scored)) if len(dev_scored) and len(dev_miss) else None
    spread_distinguishes = bool(spread_delta is not None and claimable and spread_delta >= threshold
                                and spread_gap is not None and (floor is None or spread_gap > floor) and not distinguishes)
    sd_s, sd_m = (np.std(scored, ddof=1) if len(scored) > 1 else None), (np.std(miss, ddof=1) if len(miss) > 1 else None)
    return {
        "label": variable.label, "unit": variable.unit, "decimals": variable.decimals,
        "all": _describe(everything, variable.ratio_scale),
        "scored": _describe(scored, variable.ratio_scale), "miss": _describe(miss, variable.ratio_scale),
        "n_scored": len(scored), "n_miss": len(miss),
        "median_difference_miss_minus_scored": median_difference,
        "cliffs_delta": delta, "hedges_g": hedges_g(miss, scored) if enough else None,
        "sd_ratio_miss_to_scored": float(sd_m / sd_s) if sd_s and sd_m is not None and sd_s > 0 else None,
        "noise_floor": floor, "noise_floor_source": variable.noise_source,
        "below_noise_floor": bool(below_floor), "distinguishes": distinguishes,
        "critical_delta": threshold,
        "spread_cliffs_delta": spread_delta, "spread_distinguishes": spread_distinguishes,
        "miss_median_deviation": float(np.median(dev_miss)) if len(dev_miss) else None,
        "scored_median_deviation": float(np.median(dev_scored)) if len(dev_scored) else None,
        "cliffs_delta_note": "Scored-minus-miss direction: +1 means every scored throw was higher than every miss.",
    }


def _join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _exemplars(rows, variable: Variable, labels: dict[str, str], count: int = 3) -> list[str]:
    """Scored throws closest to the scored median of the leading variable."""
    scored = [r for r in rows if group_label(r.get("score_category")) == "scored"
              and r.get(variable.key) is not None and np.isfinite(r[variable.key])]
    if not scored:
        return []
    center = float(np.median([r[variable.key] for r in scored]))
    order = {id(r): i for i, r in enumerate(rows)}
    ranked = sorted(sorted(scored, key=lambda r: abs(r[variable.key] - center))[:count], key=lambda r: order[id(r)])
    return [labels.get(r["trial_id"], r["trial_id"]) for r in ranked]


def performance_summary(rows: list[dict[str, Any]], labels: dict[str, str]) -> dict[str, Any]:
    """Summarize one athlete's comparable throws and write three-level feedback."""
    scores = [r.get("score_category") for r in rows]
    counts = {"hole": scores.count(3), "board": scores.count(1), "miss": scores.count(0),
              "unknown": sum(s is None for s in scores)}
    n_scored, n_known = counts["hole"] + counts["board"], len(rows) - counts["unknown"]
    variables = _selected_variables(rows)
    # Each variable is tested for a shift and for a spread difference.
    analyzed = {v.key: _analyze_variable(v, rows, comparisons=2 * len(variables)) for v in variables}
    by_key = {v.key: v for v in variables}
    for key, a in analyzed.items():
        # Individual throws for plotting; unknown outcomes keep group None.
        a["points"] = [{"trial_id": r["trial_id"], "label": labels.get(r["trial_id"], r["trial_id"]),
                        "value": float(r[key]), "group": group_label(r.get("score_category"))}
                       for r in rows if r.get(key) is not None and np.isfinite(r[key])]

    if n_known == 0:
        result = "No observed outcomes yet. Record 0, 1 or 3 points for each throw to compare scored throws with misses."
    else:
        result = (f"{n_scored} of {n_known} throws scored ({counts['hole']} in the hole, {counts['board']} on the "
                  f"board); {counts['miss']} missed.")
        if counts["unknown"]:
            result += f" {counts['unknown']} throw(s) have no recorded outcome and are left out."

    leaders = sorted((k for k, a in analyzed.items() if a["distinguishes"]),
                     key=lambda k: abs(analyzed[k]["cliffs_delta"]), reverse=True)[:2]
    sentences = []
    for key in leaders:
        a, v = analyzed[key], by_key[key]
        word = v.lower_word if a["median_difference_miss_minus_scored"] < 0 else v.higher_word
        sentences.append(f"Misses were associated with a {word} {v.label.lower()} (median "
                         f"{_fmt(a['miss']['median'], v)}{_unit(v.unit)} vs {_fmt(a['scored']['median'], v)}{_unit(v.unit)} on scored throws).")
    spread_leaders = sorted((k for k, a in analyzed.items() if a["spread_distinguishes"]),
                            key=lambda k: -analyzed[k]["spread_cliffs_delta"])[:2]
    for key in spread_leaders:
        a, v = analyzed[key], by_key[key]
        if len(sentences) < 3:
            sentences.append(f"Misses were further from this athlete's scored {v.label.lower()} (typically "
                             f"{_fmt(a['miss_median_deviation'], v)}{_unit(v.unit)} off vs "
                             f"{_fmt(a['scored_median_deviation'], v)}{_unit(v.unit)} on scored throws).")
    for key, a in analyzed.items():
        ratio, v = a["sd_ratio_miss_to_scored"], by_key[key]
        if (ratio and ratio >= VARIABILITY_RATIO and a["n_scored"] >= MIN_CLAIM_PER_GROUP
                and a["n_miss"] >= MIN_CLAIM_PER_GROUP and key not in leaders and key not in spread_leaders
                and len(sentences) < 3):
            sentences.append(f"{v.label} was more spread out on misses (SD {_fmt(a['miss']['sd'], v)} vs "
                             f"{_fmt(a['scored']['sd'], v)}{_unit(v.unit)}).")
    if not sentences:
        if n_scored < MIN_CLAIM_PER_GROUP or counts["miss"] < MIN_CLAIM_PER_GROUP:
            sentences.append(f"Not enough scored throws ({n_scored}) or misses ({counts['miss']}) yet to compare "
                             f"them; aim for at least {MIN_CLAIM_PER_GROUP} of each.")
        else:
            sentences.append(f"No measured release variable clearly separated scored throws from misses in these "
                             f"{n_known} throws.")
    why = " ".join(sentences)

    focus = leaders or spread_leaders
    if focus:
        v, a = by_key[focus[0]], analyzed[focus[0]]
        examples = _exemplars(rows, v, labels)
        next_step = (f"Scored throws had a {v.label.lower()} of {_fmt(a['scored']['q25'], v)}–"
                     f"{_fmt(a['scored']['q75'], v)}{_unit(v.unit)} (middle half). ")
        if examples:
            next_step += f"Review {_join(examples)} on video as typical scored throws and practise reproducing that release."
    else:
        relative = {k: a["all"]["sd"] / a["noise_floor"] for k, a in analyzed.items()
                    if a["all"]["sd"] is not None and a["noise_floor"]}
        if relative:
            v = by_key[max(relative, key=relative.get)]
            next_step = (f"Keep recording. The least repeatable measured variable was {v.label.lower()} "
                         f"(SD {_fmt(analyzed[v.key]['all']['sd'], v)}{_unit(v.unit)}); watch it in the next session.")
        else:
            next_step = "Keep recording throws with confirmed release and outcomes to build the comparison."
    caveat = (f"Based on {len(rows)} throws from this athlete. These are associations, not proven causes; "
              "differences smaller than measurement uncertainty are not reported.")
    return {
        "schema_version": 1, "success_definition": "scored (1 or 3 points) versus miss (0)",
        "counts": counts, "variables": analyzed,
        "feedback": {"result": result, "why": why, "next": next_step, "caveat": caveat},
        "method": ("Cliff's delta for a shift in each variable and for misses lying further from the scored-throw "
                   "median; claimed only with ≥ 5 throws per group, |δ| above both 0.474 (large) and the chance level for "
                   "this sample size (Bonferroni across all variables tested), and a difference above the noise floor. "
                   "Stress-tested on simulated athletes (docs/STRESS_TEST.md)."),
    }


def compare_throws(a: dict[str, Any], b: dict[str, Any], rows: list[dict[str, Any]],
                   labels: dict[str, str]) -> dict[str, Any]:
    """Explain how throw B differs from throw A, relative to this athlete's normal variation.

    A difference is 'meaningful' when it exceeds the noise floor and at least
    one SD of the athlete's throw-to-throw variation on that variable.
    """
    name_a, name_b = labels.get(a["trial_id"], a["trial_id"]), labels.get(b["trial_id"], b["trial_id"])
    differences = []
    for v in _selected_variables(rows):
        va, vb = a.get(v.key), b.get(v.key)
        if va is None or vb is None or not (np.isfinite(va) and np.isfinite(vb)):
            continue
        spread = _values(rows, v.key)
        sd = float(np.std(spread, ddof=1)) if spread.size >= 3 else None
        diff = float(vb - va)
        z = diff / sd if sd else None
        floor = _noise_floor(v, rows)
        meaningful = bool(z is not None and abs(z) >= 1 and (floor is None or abs(diff) > floor))
        differences.append({"key": v.key, "label": v.label, "unit": v.unit, "a": va, "b": vb,
                            "difference": diff, "athlete_sd": sd, "standardized": z, "meaningful": meaningful,
                            "word": v.lower_word if diff < 0 else v.higher_word, "decimals": v.decimals})
    differences.sort(key=lambda d: (d["meaningful"], abs(d["standardized"] or 0)), reverse=True)
    top = [d for d in differences if d["meaningful"]][:2]
    if top:
        parts = [f"a {d['word']} {d['label'].lower()} ({d['b']:.{d['decimals']}f}{_unit(d['unit'])} vs "
                 f"{d['a']:.{d['decimals']}f}{_unit(d['unit'])})"
                 for d in top]
        summary = f"Compared with {name_a}, {name_b} had {_join(parts)}."
    else:
        summary = (f"{name_a} and {name_b} differed by less than this athlete's normal throw-to-throw variation "
                   "on every measured variable.")
    return {"a": a["trial_id"], "b": b["trial_id"], "summary": summary, "differences": differences}
