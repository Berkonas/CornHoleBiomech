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


def _inches(value: float) -> str:
    return f"{abs(value):.0f} in"


def measured_end(board_phase: dict[str, Any] | None) -> dict[str, Any] | None:
    """Plain facts about where the bag landed and ended, from the board phase (inches along the deck)."""
    if not board_phase or board_phase.get("status") != "measured":
        return None
    touch, end, slide = board_phase["touchdown"], board_phase["end"], board_phase.get("slide") or {}
    return {"kind": end["kind"], "landed_from_hole_in": touch.get("from_hole_in"),
            "end_from_hole_in": end.get("from_hole_in") if end["kind"] in ("rest", "fell_in_hole") else None,
            "slide_in": slide.get("distance_in"), "hang_s": (board_phase.get("hang") or {}).get("seconds"),
            "suggested_score": (board_phase.get("suggested_outcome") or {}).get("score")}


def _slide_sentence(end: dict[str, Any]) -> str | None:
    landed, slide = end.get("landed_from_hole_in"), end.get("slide_in")
    if landed is None:
        return None
    where = "at the hole" if abs(landed) <= 3 else f"{_inches(landed)} {'past' if landed > 0 else 'short of'} the hole"
    text = f"It landed {where}"
    if slide is not None and abs(slide) >= 2:
        text += f" and slid {_inches(slide)}"
    return text


def _scored_verdict(physics: dict[str, Any] | None, end: dict[str, Any] | None, flags: list[dict], metrics: dict,
                    approx: str) -> tuple[str, list[dict[str, Any]]]:
    """A hole: say what worked. No corrections, whatever the flight model or usual pattern says."""
    items: list[dict[str, Any]] = []
    headline = "In the hole: 3 points."
    if end:
        sentence = _slide_sentence(end)
        if sentence:
            headline += f" {sentence}{' into the hole' if (end.get('slide_in') or 0) >= 2 else ''}."
        if end.get("hang_s"):
            headline += f" It hung on the lip for {end['hang_s']:.1f} s before dropping."
    if physics:
        items.append({"kind": "good", "metric_key": "bag_release_speed_m_s",
                      "text": f"Keep this release as a reference: {physics['angle_deg']:.0f}° at {approx}{physics['speed_m_s']:.1f} m/s "
                              f"from {physics['height_m']:.2f} m."})
    if end and (end.get("slide_in") or 0) >= 4:
        items.append({"kind": "good", "metric_key": None,
                      "text": "The slide was part of the shot: landing short and sliding in is a valid way to score."})
    if physics and physics.get("zone") != "green":
        items.append({"kind": "note", "metric_key": None,
                      "text": "The drag-free flight model alone did not predict the hole for this release; the slide, bounce "
                              "or aim made it. The result is what counts; the model is only a guide."})
    for flag in [f for f in flags if _nameable(metrics, f["key"])][:2]:
        words = BODY_WORDS[flag["key"]]
        word = words[0] if flag["direction"] == "high" else words[1]
        items.append({"kind": "note", "metric_key": flag["key"],
                      "text": f"Different from this athlete's usual throw, and it still scored: {word} "
                              f"({_fmt(flag['value'], flag['unit'])}; usual {_fmt_range(flag['q25'], flag['q75'], flag['unit'])})."})
    return headline, items


def _distance_advice(physics: dict[str, Any] | None, end_from_hole_in: float, settings: ZoneSettings,
                     approx: str) -> dict[str, Any]:
    """Signed advice from where the bag actually ENDED: how much farther/shorter, and the speed change."""
    short = end_from_hole_in < 0
    text = f"The bag ended {_inches(end_from_hole_in)} {'short of' if short else 'past'} the hole."
    sens = (physics or {}).get("sensitivity_m_per_m_s")
    if sens and abs(sens) > 1e-6:
        # Move first contact by the same along-deck amount (the slide is assumed unchanged).
        shift_m = -end_from_hole_in * 0.0254 * np.cos(settings.board.angle)
        dv = shift_m / sens
        text += (f" At the same angle, about {approx}{abs(dv):.2f} m/s {'faster' if dv > 0 else 'slower'} "
                 f"would have carried it to the hole (if it slides the same way).")
    else:
        text += f" It needed {'a little more' if short else 'a little less'} distance."
    return {"kind": "fix", "metric_key": "bag_release_speed_m_s", "text": text,
            "signed_error_in": end_from_hole_in, "direction": "short" if short else "long"}


def throw_verdict(metrics: dict, others: list[dict], grades: dict, release_to_board_m: float | None,
                  settings: ZoneSettings, athlete_median_m: float | None = None,
                  observed_score: int | None = None, board_phase: dict[str, Any] | None = None) -> dict[str, Any]:
    physics = physics_check(metrics, release_to_board_m, settings, athlete_median_m)
    end = measured_end(board_phase)
    if observed_score == 3:
        flags = personal_flags(metrics, others)
        approx = "≈" if grades.get("calibration") != "GOOD" else ""
        headline, items = _scored_verdict(physics, end, flags, metrics, approx)
        return {"headline": headline, "items": items[:5], "physics": physics, "personal": flags, "outcome": "hole",
                "measured_end": end,
                "method": "Scored throw: no corrections are given. Drag-free point-mass flight to first contact "
                          "(zones.landing) is shown for reference; where the bag ended comes from the board video."}
    verdict = _unscored_verdict(metrics, others, grades, settings, physics)
    verdict["measured_end"] = end
    verdict["outcome"] = {1: "board", 0: "miss"}.get(observed_score)
    if end and end.get("end_from_hole_in") is not None and end["kind"] == "rest" and observed_score in (0, 1):
        # Replace the model-only distance advice with advice from where the bag really stopped.
        approx = "≈" if grades.get("calibration") != "GOOD" else ""
        advice = _distance_advice(physics, end["end_from_hole_in"], settings, approx)
        items = [i for i in verdict["items"] if i.get("metric_key") != "bag_release_speed_m_s" or i["kind"] == "note"]
        verdict["items"] = [advice] + items
        sentence = _slide_sentence(end)
        verdict["headline"] = (f"{'On the board: 1 point.' if observed_score == 1 else 'Off the board: 0 points.'} "
                               + (f"{sentence}, stopping {_inches(end['end_from_hole_in'])} "
                                  f"{'short of' if end['end_from_hole_in'] < 0 else 'past'} the hole." if sentence else ""))
    verdict["items"] = verdict["items"][:5]
    return verdict


def _unscored_verdict(metrics: dict, others: list[dict], grades: dict, settings: ZoneSettings,
                      physics: dict[str, Any] | None) -> dict[str, Any]:
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
