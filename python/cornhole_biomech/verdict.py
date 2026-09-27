"""Per-throw coaching verdict: what happened, what went well, what to work on.

Two independent checks, both stated in plain words and both reproducible:

1. Physics (drag-free point mass, zones.landing): with this throw's measured release speed v,
   angle θ and height h, and the measured release-to-board distance d (else the athlete's median
   measured distance, else the Settings distance, default 7.7 m, labelled "assumed"), where would
   the bag first land? The speed that reaches the hole
   centre at the same θ and h is v*; Δv = v − v*. ∂x/∂v (central difference, ±0.05 m/s) converts
   a speed error into metres of landing error.
2. Personal (within-athlete): the throw's value against the athlete's other throws, flagged only
   when |value − median| > max(noise floor, 1.5 · IQR/1.349) and at least 5 other throws have a usable
   value. The headline counts only flags it can name (non-exploratory metrics in BODY_WORDS), and says
   "within the usual range" only when at least one such metric was actually compared.

Associations only; the text never claims a body variable caused the landing.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

import numpy as np

from .reliability import BY_KEY
from .zones import ZoneSettings, landing, predicted_zone, speed_to_hole

MINIMUM_OTHERS = 5
RELEASE = ("bag_release_speed_m_s", "bag_release_angle_deg", "bag_release_height_m")
BODY_WORDS = {  # key: (word when higher than usual, word when lower)
    "elbow_angle_deg_at_release": ("straighter elbow", "more bent elbow"),
    "trunk_inclination_deg_at_release": ("more forward trunk lean", "more upright trunk"),
    "wrist_peak_speed_arm_lengths_s": ("faster peak hand speed", "slower peak hand speed"),
    "swing_backswing_angle_deg": ("shorter backswing", "bigger backswing"),
    "swing_forward_duration_s": ("slower forward swing", "quicker forward swing"),
    "swing_tempo_ratio": ("longer backswing relative to the forward swing", "shorter backswing relative to the forward swing"),
    "wrist_direction_at_release_deg": ("hand moving more upward at release", "hand moving flatter at release"),
    "wrist_peak_speed_time_rel_release_ms": ("peak hand speed closer to release", "peak hand speed earlier before release"),
    "bag_release_angle_deg": ("higher release angle", "lower release angle"),
    "bag_release_speed_m_s": ("faster release", "slower release"),
    "bag_release_height_m": ("higher release point", "lower release point"),
    "bag_release_position_forward_arm_lengths": ("release point further in front of the shoulder",
                                                 "release point closer to the shoulder"),
    "wrist_speed_at_release_arm_lengths_s": ("faster hand at release", "slower hand at release"),
    "swing_release_arm_angle_deg": ("arm further forward at release", "arm further back at release"),
}


def _exploratory(metrics: dict, key: str) -> bool:
    row = metrics.get(key) or {}
    metric = BY_KEY.get(key)
    return bool(row.get("exploratory") or (metric is not None and metric.exploratory))


def _nameable(metrics: dict, key: str) -> bool:
    """Flags the verdict can put into words: non-exploratory metrics with a plain-language description."""
    return key in BODY_WORDS and not _exploratory(metrics, key)


def _usable(metrics: dict, key: str) -> float | None:
    row = metrics.get(key) or {}
    value = row.get("value")
    if value is None or row.get("status") in ("unreliable", "unavailable", None) or not np.isfinite(value):
        return None
    return float(value)


def physics_check(metrics: dict, release_to_board_m: float | None, settings: ZoneSettings, athlete_median_m: float | None = None) -> dict[str, Any] | None:
    v, a, h = (_usable(metrics, k) for k in RELEASE)
    if v is None or a is None or h is None:
        return None
    measured = release_to_board_m is not None and np.isfinite(release_to_board_m) and release_to_board_m > 0
    if measured:
        distance, source = float(release_to_board_m), "measured"
    elif athlete_median_m is not None and np.isfinite(athlete_median_m) and athlete_median_m > 0:
        distance, source = float(athlete_median_m), "athlete_median"
    else:
        distance, source = settings.release_to_board_m, "assumed"
    s = replace(settings, release_to_board_m=distance)
    hit = predicted_zone(v, a, h, s)
    need = speed_to_hole(a, h, s)
    dv = 0.05
    x_hi = landing(v + dv, a, h, s.release_to_board_m, s.board)["horizontal_m"]
    x_lo = landing(v - dv, a, h, s.release_to_board_m, s.board)["horizontal_m"]
    hole_x = s.release_to_board_m + s.board.hole_along * np.cos(s.board.angle)
    return {"distance_m": s.release_to_board_m, "distance_source": source,
            "speed_m_s": v, "angle_deg": a, "height_m": h,
            "landing": hit["kind"], "zone": hit["zone"], "from_hole_m": hit["from_hole_m"],
            "landing_x_m": hit["horizontal_m"], "hole_x_m": float(hole_x),
            "required_speed_m_s": need, "delta_speed_m_s": None if need is None else v - need,
            "sensitivity_m_per_m_s": (x_hi - x_lo) / (2 * dv)}


def personal_flags(metrics: dict, others: list[dict]) -> list[dict[str, Any]]:
    flags = []
    for key, row in metrics.items():
        value = _usable(metrics, key)
        history = [x for x in (_usable(o, key) for o in others) if x is not None]
        if value is None or len(history) < MINIMUM_OTHERS:
            continue
        median = float(np.median(history))
        q25, q75 = np.percentile(history, [25, 75])
        threshold = max(float(row.get("noise_floor") or 0.0), 1.5 * (q75 - q25) / 1.349)
        if abs(value - median) > threshold and threshold > 0:
            flags.append({"key": key, "label": row.get("label", key), "unit": row.get("unit", ""), "value": value,
                          "median": median, "q25": float(q25), "q75": float(q75),
                          "direction": "high" if value > median else "low",
                          "size": abs(value - median) / threshold})
    return sorted(flags, key=lambda f: -f["size"])


def _fmt(value: float, unit: str) -> str:
    digits = 0 if unit in ("°", "ms", "°/s") else 2 if unit in ("m", "s") else 1
    return f"{value:.{digits}f}".replace("-", "−") + f"{'' if unit == '°' else ' '}{unit}".rstrip()


def _fmt_range(low: float, high: float, unit: str) -> str:
    digits = 0 if unit in ("°", "ms", "°/s") else 2 if unit in ("m", "s") else 1
    low_str = f"{low:.{digits}f}".replace("-", "−")
    high_str = f"{high:.{digits}f}".replace("-", "−")
    sep = " to " if (low < 0 or high < 0) else "–"
    return f"{low_str}{sep}{high_str}{'' if unit == '°' else ' '}{unit}".strip()


def throw_verdict(metrics: dict, others: list[dict], grades: dict, release_to_board_m: float | None,
                  settings: ZoneSettings, athlete_median_m: float | None = None) -> dict[str, Any]:
    physics = physics_check(metrics, release_to_board_m, settings, athlete_median_m)
    flags = personal_flags(metrics, others)
    approx = "≈" if grades.get("calibration") != "GOOD" else ""
    items: list[dict[str, Any]] = []
    if physics:
        where = {"short": "short of the board", "front": "into the front of the board", "long": "past the board"}
        if physics["landing"] == "board":
            off = physics["from_hole_m"]
            place = "at the hole" if abs(off) < 0.08 else f"{approx}{abs(off):.2f} m {'past' if off > 0 else 'short of'} the hole"
            headline = f"Released at {physics['angle_deg']:.0f}° and {approx}{physics['speed_m_s']:.1f} m/s: the flight model puts first contact on the board, {place}."
        else:
            headline = f"Released at {physics['angle_deg']:.0f}° and {approx}{physics['speed_m_s']:.1f} m/s: the flight model puts first contact {where[physics['landing']]}."
        need = physics["required_speed_m_s"]
        if need is None:
            items.append({"kind": "fix", "metric_key": "bag_release_angle_deg",
                          "text": f"No release speed reaches the hole from {physics['height_m']:.2f} m at {physics['angle_deg']:.0f}°; the release angle is the limit."})
        elif abs(physics["delta_speed_m_s"]) * abs(physics["sensitivity_m_per_m_s"]) > 0.15:
            more = "less" if physics["delta_speed_m_s"] > 0 else "more"
            items.append({"kind": "fix", "metric_key": "bag_release_speed_m_s",
                          "text": f"Release speed: {approx}{need:.1f} m/s reaches the hole at this angle and height; this throw was {approx}{abs(physics['delta_speed_m_s']):.1f} m/s {'faster' if more == 'less' else 'slower'}. "
                                  f"Each 0.1 m/s moves first contact about {abs(physics['sensitivity_m_per_m_s']) * 0.1:.2f} m."})
        else:
            items.append({"kind": "good", "metric_key": "bag_release_speed_m_s",
                          "text": f"Release speed matched the hole ({approx}{physics['speed_m_s']:.1f} m/s vs {approx}{need:.1f} m/s needed)."})
    named = [f for f in flags if _nameable(metrics, f["key"])]
    release_flags = [f for f in named if f["key"] in RELEASE]
    body_flags = [f for f in named if f["key"] not in RELEASE]
    shown = release_flags + body_flags[:2]
    compared = [k for k in BODY_WORDS if _nameable(metrics, k) and _usable(metrics, k) is not None
                and sum(_usable(o, k) is not None for o in others) >= MINIMUM_OTHERS]
    if physics:
        pass  # the physics headline above stands
    elif named:
        headline = f"This throw differed from the athlete's usual pattern in {len(named)} measured variable{'s' if len(named) != 1 else ''}"
        headline += f" (the {len(shown)} largest are listed)." if len(shown) < len(named) else "."
    elif compared:
        headline = "Every reliable measurement was within this athlete's usual range."
    else:
        missing = max(MINIMUM_OTHERS - len(others), 1)
        if len(others) >= MINIMUM_OTHERS:
            headline = ("Measured. Too few of this athlete's other throws have reliable values for the same measurements; "
                        "more analyzed throws are needed to compare it with this athlete's usual pattern.")
        else:
            headline = (f"Measured. {missing} more analyzed throw{'s are' if missing != 1 else ' is'} needed "
                        "to compare it with this athlete's usual pattern.")
    for flag in shown:
        words = BODY_WORDS[flag["key"]]
        word = words[0] if flag["direction"] == "high" else words[1]
        kind = "note" if physics and flag["key"] == "bag_release_speed_m_s" else "fix"
        items.append({"kind": kind, "metric_key": flag["key"],
                      "text": f"Unusual for this athlete: {word} ({_fmt(flag['value'], flag['unit'])}; usual {_fmt_range(flag['q25'], flag['q75'], flag['unit'])})."})
    steady = [k for k in ("elbow_angle_deg_at_release", "trunk_inclination_deg_at_release", "wrist_peak_speed_arm_lengths_s")
              if _usable(metrics, k) is not None and k not in {f["key"] for f in flags}
              and sum(_usable(o, k) is not None for o in others) >= MINIMUM_OTHERS]
    if steady:
        labels = [str((metrics[k] or {}).get("label", k)).lower() for k in steady]
        items.append({"kind": "good", "metric_key": steady[0], "text": f"Within the usual range: {', '.join(labels)}."})
    for stage, name in (("pose", "Body tracking"), ("bag", "Bag tracking"), ("release", "Release timing"), ("calibration", "Scale")):
        grade = grades.get(stage)
        if grade in ("WARNING", "POOR"):
            text = ("Scale comes from the bag's fall under gravity only; metres are approximate." if stage == "calibration" and grade == "WARNING"
                    else f"{name} quality is {grade.lower()}; treat related numbers with care.")
            items.append({"kind": "note", "metric_key": None, "text": text})
    order = {"fix": 0, "good": 1, "note": 2}
    items.sort(key=lambda i: order[i["kind"]])
    return {"headline": headline, "items": items[:5], "physics": physics, "personal": flags,
            "method": "Drag-free point-mass flight to first contact (zones.landing); personal flags when "
                      "|value − median| > max(noise floor, 1.5·IQR/1.349) with ≥ 5 other throws."}
