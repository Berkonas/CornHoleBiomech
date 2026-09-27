"""Athlete dashboard: performance, release profile, consistency, evidence chain and coaching priorities.

Everything is within one athlete (their throws compared with each other); the
statistics are those of `performance.py` (Cliff's δ with family-wise control,
noise floors). This module decides what a coach sees and how strongly it is worded.

Difference → association → action (brief §41). A variable becomes a
COACHING PRIORITY only if all of these hold:
  1. associated with outcome: `performance.py` says it distinguishes scored throws
     from misses (≥5 throws per group, large δ above the chance level for this many
     tests), either as a shift or as misses lying further from the scored value;
  2. larger than measurement uncertainty: the median difference exceeds the
     variable's noise floor;
  3. repeatable: a bootstrap 95% CI of the median difference excludes 0;
  4. measured reliably: ≥80% of the athlete's values passed the per-throw
     reliability rules (reliability.py);
  5. interpretable and modifiable: a movement or release feature an athlete can
     change on purpose (not an exploratory derivative).
A difference passing 2 but not all of the rest is an OBSERVED DIFFERENCE: shown,
never phrased as advice.

Consistency: typical variation (SD, CV for ratio-scale variables, IQR) is judged
against the measurement noise floor, and with Hopkins' smallest worthwhile change
(0.2 × between-throw SD) as the smallest difference worth discussing.

Release compensation (after Müller & Sternad 2004, tolerance–noise–covariation):
with release speed, angle and height in metres, the drag-free model predicts each
throw's first-contact distance. If the athlete's speed and angle co-vary so that
errors cancel, the spread of predicted distances is smaller than when the same
values are recombined at random. ratio = SD(shuffled) / SD(observed) > 1 means
compensation. Model-based and descriptive; needs ≥ 8 scaled throws.

Evidence chain (body → release → flight → outcome) is a hypothesis structure:
each link is a within-athlete Spearman correlation with a bootstrap CI; a link is
"supported" only when the CI excludes 0 with ≥ 8 throws. Not causal.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from .reliability import BY_KEY
from .statistics import relationship

PROFILE_KEYS = ("bag_release_speed_m_s", "bag_release_angle_deg", "bag_release_height_m",
                "wrist_speed_at_release_arm_lengths_s", "wrist_peak_speed_time_rel_release_ms",
                "swing_release_arm_angle_deg", "swing_backswing_angle_deg", "elbow_angle_deg_at_release",
                "trunk_inclination_deg_at_release", "swing_tempo_ratio")
RATIO_SCALE = {"bag_release_speed_m_s", "bag_release_height_m", "wrist_speed_at_release_arm_lengths_s",
               "swing_tempo_ratio"}
CHAIN = (
    ("Body → release", "wrist_speed_at_release_arm_lengths_s", "bag_release_speed_m_s"),
    ("Body → release", "swing_release_arm_angle_deg", "bag_release_angle_deg"),
    ("Body → release", "wrist_peak_speed_time_rel_release_ms", "bag_release_angle_deg"),
    ("Release → flight", "bag_release_angle_deg", "bag_trajectory_apex_rise_m"),
    ("Release → flight", "bag_release_speed_m_s", "bag_time_of_flight_seconds"),
    ("Release → outcome", "bag_release_angle_deg", "score_category"),
    ("Release → outcome", "bag_release_speed_m_s", "score_category"),
    ("Body → outcome", "wrist_peak_speed_time_rel_release_ms", "score_category"),
)
MIN_CHAIN = 8
RELIABLE_SHARE = 0.8
PRACTICE = {
    "bag_release_angle_deg": "the release angle of the scored throws: watch the arm angle and hand direction at release",
    "bag_release_speed_m_s": "the release speed of the scored throws: keep the swing length and tempo the same",
    "bag_release_speed_arm_lengths_s": "the release speed of the scored throws: keep the swing length and tempo the same",
    "bag_release_height_m": "the release height of the scored throws: same knee bend and release point",
    "bag_release_height_arm_lengths": "the release height of the scored throws: same knee bend and release point",
    "bag_release_position_forward_arm_lengths": "releasing at the same point in front of the body as on scored throws",
    "swing_release_arm_angle_deg": "letting go at the same arm angle as on scored throws",
    "swing_backswing_angle_deg": "the same backswing height as on scored throws",
    "swing_tempo_ratio": "the same backswing-to-forward-swing rhythm as on scored throws",
    "swing_peak_angular_velocity_deg_s": "the same swing speed as on scored throws",
    "elbow_angle_deg_at_release": "the elbow position at release seen on scored throws",
    "trunk_inclination_deg_at_release": "the trunk lean at release seen on scored throws",
    "wrist_speed_at_release_arm_lengths_s": "the hand speed at release seen on scored throws",
    "wrist_peak_speed_time_rel_release_ms": "the timing of the fastest hand speed relative to release on scored throws",
}


def _values(rows, key, group=None):
    out = []
    for r in rows:
        v = r.get(key)
        s = r.get("score_category")
        if v is None or not math.isfinite(v):
            continue
        if group == "scored" and s not in (1, 3):
            continue
        if group == "miss" and s != 0:
            continue
        out.append(float(v))
    return np.asarray(out)


def _bootstrap_median_difference(miss: np.ndarray, scored: np.ndarray, resamples: int = 2000,
                                 seed: int = 20260923) -> tuple[float | None, float | None]:
    if len(miss) < 3 or len(scored) < 3:
        return None, None
    rng = np.random.default_rng(seed)
    diffs = [np.median(rng.choice(miss, len(miss))) - np.median(rng.choice(scored, len(scored)))
             for _ in range(resamples)]
    low, high = np.percentile(diffs, [2.5, 97.5])
    return float(low), float(high)


def release_profile(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Typical value and throw-to-throw consistency of each coach release/movement metric."""
    out = []
    for key in PROFILE_KEYS:
        v = _values(rows, key)
        metric = BY_KEY.get(key)
        if metric is None or v.size < 3:
            continue
        sd = float(np.std(v, ddof=1))
        q25, q75 = np.percentile(v, [25, 75])
        floor = metric.noise_floor
        ratio = sd / floor if floor else None
        consistency = ("within measurement noise" if ratio is not None and ratio <= 1
                       else "variable" if ratio is not None and ratio > 2 else "moderate")
        out.append({"key": key, "label": metric.label, "unit": metric.unit, "group": metric.group, "n": int(v.size),
                    "median": float(np.median(v)), "q25": float(q25), "q75": float(q75), "sd": sd,
                    "cv_percent": float(100 * sd / abs(np.mean(v))) if key in RATIO_SCALE and np.mean(v) else None,
                    "noise_floor": floor, "sd_to_noise": ratio, "consistency": consistency,
                    "smallest_worthwhile_change": 0.2 * sd,
                    "values": [{"trial_id": r["trial_id"], "value": float(r[key]), "score": r.get("score_category")}
                               for r in rows if r.get(key) is not None and math.isfinite(r[key])]})
    return out


def release_compensation(rows: list[dict[str, Any]], settings, permutations: int = 500,
                         seed: int = 20260923) -> dict[str, Any]:
    """Do speed and angle co-vary so that landing errors cancel? (model-based, descriptive)."""
    from .zones import landing
    keys = ("bag_release_speed_m_s", "bag_release_angle_deg", "bag_release_height_m")
    usable = [r for r in rows if all(r.get(k) is not None and math.isfinite(r[k]) for k in keys)]
    base = {"n": len(usable), "status": "insufficient_data", "ratio": None,
            "message": f"Needs ≥ {MIN_CHAIN} throws with release speed, angle and height in metres."}
    if len(usable) < MIN_CHAIN:
        return base
    speed = np.array([r[keys[0]] for r in usable]); angle = np.array([r[keys[1]] for r in usable])
    height = np.array([r[keys[2]] for r in usable])

    def distances(s, a, h):
        return np.array([landing(si, ai, hi, settings.release_to_board_m, settings.board)["horizontal_m"]
                         for si, ai, hi in zip(s, a, h)])
    observed = float(np.std(distances(speed, angle, height), ddof=1))
    rng = np.random.default_rng(seed)
    shuffled = [float(np.std(distances(rng.permutation(speed), angle, height), ddof=1)) for _ in range(permutations)]
    expected = float(np.mean(shuffled))
    ratio = expected / observed if observed > 0 else None
    share = float(np.mean(np.array(shuffled) <= observed))   # how often chance pairing is as tight as observed
    if ratio is None:
        message = "Predicted landing distance did not vary."
    elif ratio > 1.1 and share < 0.05:
        message = (f"Speed and angle compensate: predicted landing spread is {observed:.2f} m, versus {expected:.2f} m "
                   "if the same speeds and angles were paired at random. Keep the combination, not each value separately.")
    elif ratio < 0.9 and share > 0.95:
        message = (f"Speed and angle errors add up: predicted landing spread {observed:.2f} m versus {expected:.2f} m "
                   "at random pairing. Faster throws also tend to be launched in the direction that lengthens them.")
    elif 0.9 <= ratio <= 1.1:
        message = "No clear compensation between release speed and angle (spread close to random pairing)."
    elif ratio > 1.1:
        # Tighter than random pairing on average, but a random pairing matches it too often to rule out chance.
        message = (f"No clear compensation between release speed and angle: a random pairing of the same speeds and "
                   f"angles was as tight {share:.0%} of the time, too often to rule out chance.")
    else:
        message = ("No clear pattern between release speed and angle: the spread as thrown is wider than at random "
                   "pairing, but not beyond chance.")
    return {"n": len(usable), "status": "estimated", "observed_spread_m": observed, "random_pairing_spread_m": expected,
            "ratio": ratio, "chance_as_tight": share, "message": message,
            "method": "Drag-free first-contact distance; release speed permuted across throws (Müller & Sternad 2004)."}


def evidence_chain(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for stage, a, b in CHAIN:
        r = relationship([row.get(a) for row in rows], [row.get(b) for row in rows], MIN_CHAIN)
        ci = r.get("spearman_bootstrap_95_ci") or [None, None]
        supported = bool(r.get("status") == "estimated" and ci[0] is not None and (ci[0] > 0 or ci[1] < 0))
        out.append({"stage": stage, "from": a, "to": b, "n": r["n"], "rho": r.get("spearman_rho"), "ci": ci,
                    "status": r["status"], "supported": supported,
                    "from_label": BY_KEY[a].label if a in BY_KEY else _plain(a),
                    "to_label": BY_KEY[b].label if b in BY_KEY else _plain(b)})
    return out


def _plain(key: str) -> str:
    return {"score_category": "Points", "bag_trajectory_apex_rise_m": "Apex height",
            "bag_time_of_flight_seconds": "Flight time"}.get(key, key.replace("_", " "))


def coaching_priorities(rows: list[dict[str, Any]], summary: dict[str, Any], labels: dict[str, str],
                        reliable_share: dict[str, float]) -> dict[str, Any]:
    """Apply the five-part gate to every analysed variable; return priorities and observed differences."""
    priorities, observed = [], []
    for key, a in (summary.get("variables") or {}).items():
        metric = BY_KEY.get(key)
        label = a.get("label") or (metric.label if metric else key)
        unit = a.get("unit", metric.unit if metric else "")
        scored, miss = _values(rows, key, "scored"), _values(rows, key, "miss")
        diff = a.get("median_difference_miss_minus_scored")
        floor = a.get("noise_floor")
        if diff is None or not (a.get("n_scored", 0) and a.get("n_miss", 0)):
            continue
        above_noise = floor is None or abs(diff) > floor
        low, high = _bootstrap_median_difference(miss, scored)
        checks = {
            "associated_with_outcome": bool(a.get("distinguishes") or a.get("spread_distinguishes")),
            "larger_than_measurement_uncertainty": bool(above_noise),
            "repeatable": bool(low is not None and (low > 0 or high < 0)) or bool(a.get("spread_distinguishes")),
            "measured_reliably": reliable_share.get(key, 1.0) >= RELIABLE_SHARE,
            "interpretable_and_modifiable": bool(metric is None or (metric.modifiable and not metric.exploratory)),
        }
        entry = {"key": key, "label": label, "unit": unit, "checks": checks,
                 "median_scored": a.get("scored", {}).get("median"), "median_miss": a.get("miss", {}).get("median"),
                 "difference_miss_minus_scored": diff, "ci_95": [low, high], "cliffs_delta": a.get("cliffs_delta"),
                 "n_scored": a.get("n_scored"), "n_miss": a.get("n_miss"), "noise_floor": floor,
                 "kind": "consistency" if a.get("spread_distinguishes") and not a.get("distinguishes") else "shift",
                 "scored_range": [a.get("scored", {}).get("q25"), a.get("scored", {}).get("q75")]}
        if all(checks.values()):
            entry["practice"] = PRACTICE.get(key, f"the {label.lower()} seen on scored throws")
            entry["example_throws"] = _typical_scored(rows, key, labels)
            priorities.append(entry)
        elif above_noise and abs(a.get("cliffs_delta") or 0) >= 0.33:
            entry["why_not_a_priority"] = [name.replace("_", " ") for name, ok in checks.items() if not ok]
            observed.append(entry)
    priorities.sort(key=lambda e: -abs(e["cliffs_delta"] or 0))
    observed.sort(key=lambda e: -abs(e["cliffs_delta"] or 0))
    return {"priorities": priorities[:3], "observed_differences": observed[:5]}


def _typical_scored(rows, key, labels, count=2):
    scored = [r for r in rows if r.get("score_category") in (1, 3) and r.get(key) is not None]
    if not scored:
        return []
    median = float(np.median([r[key] for r in scored]))
    best = sorted(scored, key=lambda r: abs(r[key] - median))[:count]
    return [{"trial_id": r["trial_id"], "label": labels.get(r["trial_id"], r["trial_id"])} for r in best]


def priority_sentence(p: dict[str, Any]) -> str:
    unit = "" if p["unit"] in ("°", "") else " "
    fmt = lambda v: "—" if v is None else (f"{v:.0f}" if p["unit"] in ("°", "ms") else f"{v:.2f}")
    if p["kind"] == "consistency":
        return (f"Misses drifted away from this athlete's scored {p['label'].lower()} "
                f"(scored throws {fmt(p['scored_range'][0])}–{fmt(p['scored_range'][1])}{unit}{p['unit']}).")
    word = "higher" if p["difference_miss_minus_scored"] > 0 else "lower"
    return (f"Misses had a {word} {p['label'].lower()}: median {fmt(p['median_miss'])}{unit}{p['unit']} vs "
            f"{fmt(p['median_scored'])}{unit}{p['unit']} on scored throws (n = {p['n_miss']} vs {p['n_scored']}).")


def data_trust(grade_rows: list[dict[str, str]], coach_rows: list[dict[str, Any]]) -> dict[str, Any]:
    stages = ("pose", "bag", "calibration", "release")
    counts = {s: {g: sum(1 for r in grade_rows if r.get(s) == g) for g in ("GOOD", "WARNING", "POOR")} for s in stages}
    statuses = [m.get("status") for row in coach_rows for m in row.values()]
    measured = [s for s in statuses if s != "not_measured"]
    share = sum(1 for s in measured if s in ("reliable", "caution")) / len(measured) if measured else None
    worst = {s: ("POOR" if counts[s]["POOR"] > len(grade_rows) / 2 else "WARNING"
                 if counts[s]["POOR"] + counts[s]["WARNING"] > len(grade_rows) / 2 else "GOOD") for s in stages}
    return {"throws": len(grade_rows), "grades": counts, "overall": worst, "reliable_metric_share": share}


def athlete_dashboard(rows: list[dict[str, Any]], summary: dict[str, Any], sports: dict[str, Any],
                      dispersion: dict[str, Any], zones: dict[str, Any], settings, labels: dict[str, str],
                      grade_rows: list[dict[str, str]], coach_rows: list[dict[str, Any]]) -> dict[str, Any]:
    reliable_share = {}
    for key in BY_KEY:
        statuses = [row.get(key, {}).get("status") for row in coach_rows]
        measured = [s for s in statuses if s and s != "not_measured"]
        if measured:
            reliable_share[key] = sum(1 for s in measured if s in ("reliable", "caution")) / len(measured)
    gate = coaching_priorities(rows, summary, labels, reliable_share)
    for p in gate["priorities"]:
        p["sentence"] = priority_sentence(p)
    for p in gate["observed_differences"]:
        p["sentence"] = priority_sentence(p)
    profile = release_profile(rows)
    most_variable = max((p for p in profile if p["sd_to_noise"] is not None), key=lambda p: p["sd_to_noise"], default=None)
    radial = [r.get("radial_error_inches") for r in rows if r.get("radial_error_inches") is not None]
    counts = summary.get("counts", {})
    known = sum(counts.get(k, 0) for k in ("hole", "board", "miss"))
    if gate["priorities"]:
        headline = gate["priorities"][0]["sentence"]
    elif known == 0:
        headline = "Record hole / board / miss for these throws to find what separates this athlete's good throws."
    elif most_variable and most_variable["consistency"] == "variable":
        headline = (f"No release feature clearly separated scored throws from misses yet. The least consistent "
                    f"measured feature was {most_variable['label'].lower()}.")
    else:
        headline = "No release feature clearly separated scored throws from misses yet; keep recording."
    return {
        "schema_version": 1,
        "throws": len(rows), "throws_with_outcome": known,
        "performance": {"sports": sports, "counts": counts,
                        "scored_percent": 100 * (counts.get("hole", 0) + counts.get("board", 0)) / known if known else None,
                        "hole_percent": 100 * counts.get("hole", 0) / known if known else None,
                        "mean_target_error_inches": float(np.mean(radial)) if radial else None,
                        "landing_dispersion": dispersion},
        "headline": headline,
        "release_profile": profile,
        "most_variable": None if most_variable is None else {k: most_variable[k] for k in ("key", "label", "sd", "unit", "sd_to_noise")},
        "compensation": release_compensation(rows, settings),
        "evidence_chain": evidence_chain(rows),
        "priorities": gate["priorities"], "observed_differences": gate["observed_differences"],
        "physics": zones.get("priority") if zones.get("status") == "available" else None,
        "trust": data_trust(grade_rows, coach_rows),
        "method": __doc__.split("\n\n", 1)[1] if __doc__ else "",
    }
