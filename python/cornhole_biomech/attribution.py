"""Miss attribution for one two-camera throw: which measured part of the throw the miss at rest came from.

The miss at rest (two_view ``miss``: hole centre → where the bag stopped, thrower's frame, inches; right +,
long +) is split into measured parts that add up to it. Each part carries its own noise, and a part is only
*named* to the coach when it clearly stands above that noise.

**Left/right** (an identity in the board's frame):

    miss_x = release position X0 + aim D·tan ψ + slide drift (x_rest − x_contact) + residual

X0 is the bag's sideways release position from the board's centre line and ψ its sideways launch direction,
both from the 3D flight (flight3d.py, METHODS_AND_MATH §5.4) when that fit was accepted, otherwise from the front
camera's release hand and heading (front_view.heading, §5.2). D is the horizontal distance from the release to
first contact. Through the heading the identity is exact by construction (the heading is drawn through the
contact); through the 3D flight the residual is the flight's lateral contact against the front camera's measured
one (SD 1.35 in on the library, §5.4).

**Short/long** (against the athlete's usual, the median over the athlete's other analysed two-camera throws):

    miss_y = usual spot + carry (y_contact − usual y_contact) + slide (slide − usual slide) + residual

"Usual spot" is the athlete's usual first contact plus usual slide, measured from the hole (39 in up the deck),
so the parts still add to the miss from the hole. Without a usual (fewer than 8 other throws) carry is first
contact against the hole and the slide is the slide itself.

**Naming rule** (council decision §4): a part is named when it is ≥ 2× its noise, ≥ 3 in (the hole radius),
≥ 40 % of that axis's miss and points the same way as the miss; at most two parts are named over both axes.
Release position and aim are judged by their *change* from the athlete's usual when a usual exists (an athlete
who always releases 8 in right of centre aims back left on every throw; only a change says something about this
miss). The release position is never named without a usual (council §7: release offset is not a cause, ρ ≈ 0).

**Drivers** (release values against the athlete's usual): release speed is named only next to a named carry, at
|Δv| ≥ 0.15 m/s (its noise floor) and with the same sign; release angle is never named for carry (≈ 0.03 m per
degree near 40–45°, research brief §0); launch direction only next to a named aim, at ≥ 0.5° and the same sign.

**Bandwidth gate**: a miss inside the athlete's usual 1-SD group on both axes names nothing and gets no cue
(``within_usual_spread``). A made throw gets "In the hole. Nothing to change." Missing stays missing: any number
may be null, never 0.

Methods and thresholds: docs/METHODS_AND_MATH.md §5.5 and docs/METRICS.md ("Miss attribution").
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .regulation import INCH_M, Board

ATTRIBUTION_VERSION = "attribution_v1"
SENTENCE_VERSION = "sentence_v2"
HOLE_X_IN, HOLE_Y_IN, HOLE_R_IN = 12.0, 39.0, 3.0      # hole centre and radius, board inches (front_view)

# --- The athlete's usual -------------------------------------------------------------------------------------
USUAL_MIN_THROWS = 8              # council §3: no usual / spread from fewer throws (no SD from < 5; 8 as for ρ)
MAD_TO_SD = 1.4826                # robust SD = 1.4826 × median absolute deviation (one 37-in slide off the board
                                  # must not widen the "normal spread" of a 20-throw athlete)

# --- Noise per part (inches unless stated). METRICS.md "Miss attribution" gives the propagation. -------------
RELEASE_POSITION_NOISE_M = 0.03   # front_release_offset_m noise floor (METRICS.md front camera table) ≈ 1.2 in
LAUNCH_DIRECTION_NOISE_DEG = 0.5  # front_heading_deg noise floor; the 3D flight agrees with it to 0.34° (median)
SLIDE_DRIFT_NOISE_IN = 1.0        # two deck-homography positions, ±0.5 in each (± bag-centre wobble)
CARRY_NOISE_IN = 2.0              # first contact along the deck from the side board phase (±2 in)
SLIDE_NOISE_IN = 2.0              # contact → rest along the deck, same board phase
RELEASE_SPEED_NOISE_M_S = 0.15    # bag_release_speed_m_s noise floor (reliability.py / performance.py)
RELEASE_ANGLE_NOISE_DEG = 3.0     # bag_release_angle_deg noise floor (reliability.py / performance.py)

# --- Naming rule ---------------------------------------------------------------------------------------------
NAME_MIN_NOISE_RATIO = 2.0        # ≥ 2× its own noise
NAME_MIN_IN = HOLE_R_IN           # ≥ 3 in: a smaller part could not have put the bag in the hole
NAME_MIN_SHARE = 0.4              # ≥ 40 % of that axis's miss
MAX_NAMED = 2
AXIS_MIN_MISS_IN = HOLE_R_IN      # an axis already within the hole radius needs no explanation
MOST_SHARE = 0.6                  # "Most of the …" from 60 %, "About half of the …" from 40 %

# --- Physics (research brief §0, drag-free, near 40–45°) -----------------------------------------------------
CARRY_M_PER_M_S = 1.8             # ≈ 0.18 m more carry per 0.1 m/s more release speed

BANNED_WORDS = ("because", "caused", "fault", "should")
_BANNED = re.compile(r"\b(" + "|".join(BANNED_WORDS) + r")\b", re.IGNORECASE)

LABELS = {"release_position": "Release position", "aim": "Aim (launch direction)", "slide_drift": "Slide drift",
          "usual_spot": "Your usual spot", "carry": "Carry (where it landed)", "slide": "Slide"}


# ------------------------------------------------------------------------------------------------
# Small helpers


def _num(value: Any) -> float | None:
    """A finite float, or None (bools, strings, NaN and ±inf are missing)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _r(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(float(value), digits)


def _sign(value: float | None) -> int:
    return 0 if value is None or value == 0 else (1 if value > 0 else -1)


def _sub(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else a - b


def _median_sd(values: Iterable[float | None]) -> tuple[float | None, float | None, int]:
    """(median, robust SD, n) of the non-missing values; median and SD only from ≥ USUAL_MIN_THROWS values."""
    vals = np.asarray([v for v in values if v is not None], float)
    if len(vals) < USUAL_MIN_THROWS:
        return None, None, int(len(vals))
    median = float(np.median(vals))
    return median, float(MAD_TO_SD * np.median(np.abs(vals - median))), int(len(vals))


# ------------------------------------------------------------------------------------------------
# What one throw measured (used for this throw and, the same way, for its siblings)


def _release_value(results: dict[str, Any], key: str) -> tuple[float | None, str | None]:
    """A side-camera release value and its status. Values the reliability check withheld stay missing."""
    metrics = results.get("coach_metrics") if isinstance(results.get("coach_metrics"), dict) else {}
    metric = metrics.get(key)
    if isinstance(metric, dict):
        if metric.get("status") in ("unreliable", "unavailable", "not_measured"):
            return None, None
        value = _num(metric.get("value"))
        if value is not None:
            return value, "estimated" if metric.get("status") == "caution" else "measured"
    value = _num((results.get("summaries") or {}).get(key))
    return value, None if value is None else "measured"


def throw_measures(record: dict[str, Any], results: dict[str, Any],
                   release_distance_m: float | None = None) -> dict[str, Any]:
    """The raw numbers attribution needs from one two_view record and its results.json (None when missing).

    ``release_distance_m`` (release → board front) is only needed when the launch direction comes from the
    heading; the 3D flight carries its own."""
    landing = record.get("landing") or {}
    contact = landing.get("contact") if isinstance(landing.get("contact"), dict) else {}
    rest = landing.get("rest") if isinstance(landing.get("rest"), dict) else {}
    miss = record.get("miss") or {}
    category = (record.get("result") or {}).get("category")
    m: dict[str, Any] = {
        "category": category, "rest_on": rest.get("on"),
        "miss_x": _num(miss.get("left_right_in")), "miss_y": _num(miss.get("short_long_in")),
        "x_c": _num(contact.get("x_in")), "y_c": _num(contact.get("y_in")),
        "x_r": _num(rest.get("x_in")), "y_r": _num(rest.get("y_in")),
        "statuses": [s for s in (miss.get("status"), contact.get("status"), rest.get("status")) if s]}
    if category == "throughHole":
        m.update(miss_x=0.0, miss_y=0.0, x_r=HOLE_X_IN, y_r=HOLE_Y_IN, rest_on="hole")
    # Release position and launch direction: the accepted 3D flight first, then the release hand + heading.
    flight = record.get("flight_3d") if isinstance(record.get("flight_3d"), dict) else {}
    heading = record.get("heading") if isinstance(record.get("heading"), dict) else {}
    x0 = psi = run0 = source = status = None
    if flight.get("status") in ("measured", "estimated"):
        release = flight.get("release") or {}
        x0, psi = _num(release.get("lateral_m")), _num(flight.get("lateral_launch_angle_deg"))
        run0 = _num(release.get("to_board_front_m"))
        if None not in (x0, psi, run0):
            source, status = "flight_3d", flight["status"]
    if source is None:
        x0, psi, run0 = _num(heading.get("release_offset_m")), _num(heading.get("deg")), _num(release_distance_m)
        # Without the release hand the heading assumes a release on the centre line: a guess, so not used.
        if None not in (x0, psi, run0):
            source, status = "heading", heading.get("status") or "measured"
            if record.get("release_distance_source") == "athlete_median":
                status = "estimated"
        else:
            x0 = psi = run0 = None
    # Horizontal distance from release to first contact (to the rest on the board, or the hole, if contact is
    # unknown): the D in D·tan ψ.
    y_touch = m["y_c"] if m["y_c"] is not None else m["y_r"] if m["y_r"] is not None else HOLE_Y_IN
    run = None if run0 is None else run0 + y_touch * INCH_M * math.cos(Board().angle)
    speed, speed_status = _release_value(results, "bag_release_speed_m_s")
    angle, angle_status = _release_value(results, "bag_release_angle_deg")
    m.update(x0_m=x0, psi_deg=psi, run_m=run, direction_source=source, direction_status=status,
             speed=speed, speed_status=speed_status, angle=angle, angle_status=angle_status)
    m["release_position_in"] = None if x0 is None else x0 / INCH_M
    m["aim_in"] = None if psi is None or run is None else run * math.tan(math.radians(psi)) / INCH_M
    m["slide_drift_in"] = None if m["x_c"] is None or m["x_r"] is None else m["x_r"] - m["x_c"]
    m["carry_in"] = None if m["y_c"] is None else m["y_c"] - HOLE_Y_IN           # first contact vs the hole
    m["slide_in"] = None if m["y_c"] is None or m["y_r"] is None else m["y_r"] - m["y_c"]
    return m


# ------------------------------------------------------------------------------------------------
# The athlete's usual (other analysed two-camera throws)


def sibling_records(analysis_dir: str | Path) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """(two_view record, results) of the athlete's other analysed two-camera throws: the sibling analysis
    folders, as ``two_view.athlete_release_distance`` finds them, whose front camera was analysed. The throw
    itself is excluded."""
    here = Path(analysis_dir)
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    if not here.parent.is_dir():
        return pairs
    for folder in sorted(p for p in here.parent.iterdir() if p.is_dir()):
        if folder.resolve() == here.resolve():
            continue
        try:
            record = json.loads((folder / "two_view.json").read_text())
            results = json.loads((folder / "results.json").read_text())
        except (OSError, ValueError):
            continue
        if isinstance(record, dict) and isinstance(results, dict) and record.get("status") == "measured":
            pairs.append((record, results))
    return pairs


def usual_from_siblings(rows: list[dict[str, Any]], direction_source: str | None) -> dict[str, Any]:
    """Medians of each part and driver over the sibling throws, and the 1-SD spread of where they stopped.

    Release position and launch direction only from siblings measured the same way as this throw (3D flight
    or heading: the two routes differ by up to ~1° on a throw, which must not read as a change of aim)."""
    same = [r for r in rows if direction_source is not None and r["direction_source"] == direction_source]
    located = [r for r in rows if r["miss_x"] is not None and r["miss_y"] is not None]
    cx, sx, _ = _median_sd(r["miss_x"] for r in located)
    cy, sy, n_located = _median_sd(r["miss_y"] for r in located)
    usual = {"throws": len(rows), "located": n_located, "centre_lateral_in": cx, "centre_depth_in": cy,
             "spread_lateral_in": sx, "spread_depth_in": sy}
    usual["x0_m"] = _median_sd(r["x0_m"] for r in same)[0]
    usual["psi_deg"] = _median_sd(r["psi_deg"] for r in same)[0]
    for key in ("slide_drift_in", "carry_in", "slide_in", "speed", "angle"):
        usual[key] = _median_sd(r[key] for r in rows)[0]
    return usual


# ------------------------------------------------------------------------------------------------
# The attribution block


def _component(key: str, value: float | None, noise: float | None, *, usual: float | None = None,
               vs_usual: float | None = None, **extra: Any) -> dict[str, Any]:
    return {"key": key, "label": LABELS[key], "in": _r(value), "noise_in": _r(noise), "named": False,
            "usual_in": _r(usual), "vs_usual_in": _r(vs_usual), **extra}


def _residual(miss: float | None, parts: list[float | None]) -> float | None:
    if miss is None or any(p is None for p in parts):
        return None
    return miss - sum(parts)


def _test_value(c: dict[str, Any], lateral: list[dict[str, Any]]) -> tuple[float | None, float | None, str | None]:
    """(inches, noise, basis) the naming rule tests for one part."""
    key = c["key"]
    if key == "release_position":
        return (c["vs_usual_in"], c["noise_in"], "usual") if c["vs_usual_in"] is not None else (None, None, None)
    if key == "aim":
        if c["vs_usual_in"] is not None:
            return c["vs_usual_in"], c["noise_in"], "usual"
        position = next((p for p in lateral if p["key"] == "release_position"), {})
        if c["in"] is None or position.get("in") is None or c["noise_in"] is None:
            return None, None, None
        # Where the launch line met the deck against the hole's line: aim and release position together.
        noise = math.hypot(c["noise_in"], position.get("noise_in") or 0.0)
        return c["in"] + position["in"], noise, "line_to_hole"
    if key == "usual_spot":
        return None, None, None
    return c["in"], c["noise_in"], c.get("basis")


def attribute(record: dict[str, Any], results: dict[str, Any], *,
              siblings: list[tuple[dict[str, Any], dict[str, Any]]] | None = None,
              release_distance_m: float | None = None) -> dict[str, Any]:
    """The ``attribution`` block of two_view.json for one throw (schema: docs/METRICS.md "Miss attribution").

    ``siblings``: (two_view record, results) of the athlete's other throws (``sibling_records``);
    ``release_distance_m``: this throw's release → board-front distance, for a heading-based aim."""
    me = throw_measures(record, results, release_distance_m)
    category = me["category"]
    rows = [throw_measures(r, res, _num((res.get("summaries") or {}).get("release_to_board_front_m"))
                           or release_distance_m) for r, res in (siblings or [])]
    usual = usual_from_siblings(rows, me["direction_source"])
    n_other = len(rows)
    out: dict[str, Any] = {
        "version": ATTRIBUTION_VERSION, "status": "measured", "reason": None, "reasons": [], "result": category,
        "rest_on": me["rest_on"], "lateral": None, "depth": None, "drivers": [],
        "usual": {"throws": n_other, "located": usual["located"],
                  "spread_lateral_in": _r(usual["spread_lateral_in"]), "spread_depth_in": _r(usual["spread_depth_in"]),
                  "centre_lateral_in": _r(usual["centre_lateral_in"]), "centre_depth_in": _r(usual["centre_depth_in"]),
                  "source": "this athlete's other throws",
                  "reason": None if usual["spread_lateral_in"] is not None else
                  f"Fewer than {USUAL_MIN_THROWS} of this athlete's other analysed two-camera throws stopped at a "
                  f"measured place ({usual['located']}), so there is no usual group and no spread."},
        "within_usual_spread": None, "inside_spread": {"lateral": None, "depth": None},
        "sentence": None, "cue": None, "tier": "geometry"}
    if record.get("status") not in (None, "measured") or category is None:
        reason = ((record.get("result") or {}).get("reason") or record.get("reason")
                  or "There is no hole / board / off result for this throw yet.")
        out.update(status="unavailable", reason=reason, reasons=[reason])
        return _finish(out)
    if category == "throughHole":
        # Outcome first: a made throw is not taken apart.
        out["lateral"] = {"miss_in": 0.0, "reference": None, "components": [], "residual_in": None}
        out["depth"] = {"miss_in": 0.0, "reference": None, "components": [], "residual_in": None}
        out["drivers"] = _drivers(me, usual, None, None, within=True)
        return _finish(out)
    reasons: list[str] = out["reasons"]

    # Left/right: the identity in the board's frame.
    run = me["run_m"]
    aim_noise = None if run is None else run * math.tan(math.radians(LAUNCH_DIRECTION_NOISE_DEG)) / INCH_M
    x0_usual_in = None if usual["x0_m"] is None else usual["x0_m"] / INCH_M
    aim_usual_in = (None if usual["psi_deg"] is None or run is None
                    else run * math.tan(math.radians(usual["psi_deg"])) / INCH_M)   # usual angle at this distance
    lateral = [
        _component("release_position", me["release_position_in"], RELEASE_POSITION_NOISE_M / INCH_M,
                   usual=x0_usual_in, vs_usual=_sub(me["release_position_in"], x0_usual_in),
                   source=me["direction_source"]),
        _component("aim", me["aim_in"], aim_noise, usual=aim_usual_in, vs_usual=_sub(me["aim_in"], aim_usual_in),
                   source=me["direction_source"], angle_deg=_r(me["psi_deg"]), distance_m=_r(run, 3)),
        _component("slide_drift", me["slide_drift_in"], SLIDE_DRIFT_NOISE_IN, usual=usual["slide_drift_in"],
                   vs_usual=_sub(me["slide_drift_in"], usual["slide_drift_in"]), basis="absolute"),
    ]
    out["lateral"] = {"miss_in": _r(me["miss_x"]), "reference": "centre_line", "components": lateral,
                      "residual_in": _r(_residual(me["miss_x"], [me["release_position_in"], me["aim_in"],
                                                                 me["slide_drift_in"]]))}
    if me["direction_source"] is None:
        reasons.append("The release position and launch direction were not measured on this throw (no accepted 3D "
                       "flight and no release hand in the front camera).")
    if me["x_c"] is None:
        reasons.append("First contact on the board was not seen, so the sideways slide is not measured.")

    # Short/long: carry and slide against the athlete's usual (else against the hole).
    u_carry, u_slide = usual["carry_in"], usual["slide_in"]
    if u_carry is not None and u_slide is not None:
        carry, slide, spot = _sub(me["carry_in"], u_carry), _sub(me["slide_in"], u_slide), u_carry + u_slide
        depth = [_component("usual_spot", spot, None, usual=spot, reference=True),
                 _component("carry", carry, CARRY_NOISE_IN, usual=u_carry, vs_usual=carry, basis="usual"),
                 _component("slide", slide, SLIDE_NOISE_IN, usual=u_slide, vs_usual=slide, basis="usual")]
        depth_parts, reference = [spot, carry, slide], "usual"
    else:
        depth = [_component("carry", me["carry_in"], CARRY_NOISE_IN, basis="hole"),
                 _component("slide", me["slide_in"], SLIDE_NOISE_IN, basis="hole")]
        depth_parts, reference = [me["carry_in"], me["slide_in"]], "hole"
    out["depth"] = {"miss_in": _r(me["miss_y"]), "reference": reference, "components": depth,
                    "residual_in": _r(_residual(me["miss_y"], depth_parts))}
    if me["y_c"] is None and me["miss_y"] is not None:
        reasons.append("First contact along the board was not measured, so carry and slide are not split.")
    if me["miss_x"] is None or me["miss_y"] is None:
        reasons.append("Where the bag stopped is not known in both directions"
                       + (" (it left the board where the cameras could not place it)." if category == "offBoard" else "."))

    # Bandwidth gate: inside the athlete's usual 1-SD group, per axis and on both.
    inside: dict[str, bool | None] = {}
    for axis, miss, centre, spread in (("lateral", me["miss_x"], usual["centre_lateral_in"], usual["spread_lateral_in"]),
                                       ("depth", me["miss_y"], usual["centre_depth_in"], usual["spread_depth_in"])):
        inside[axis] = None if None in (miss, centre, spread) else bool(abs(miss - centre) <= spread)
    within = None if None in inside.values() else bool(inside["lateral"] and inside["depth"])
    out["within_usual_spread"], out["inside_spread"] = within, inside

    # Naming (never inside the usual spread; never on an axis already within the hole radius).
    candidates = []
    for axis, components, miss in (("lateral", lateral, me["miss_x"]), ("depth", depth, me["miss_y"])):
        for c in components:
            value, noise, basis = _test_value(c, lateral)
            if value is None or noise is None:
                continue
            c["basis"], c["test_in"], c["test_noise_in"] = basis, _r(value), _r(noise)
            if within or miss is None or abs(miss) < AXIS_MIN_MISS_IN:
                continue
            if (abs(value) >= NAME_MIN_NOISE_RATIO * noise and abs(value) >= NAME_MIN_IN
                    and _sign(value) == _sign(miss) and abs(value) >= NAME_MIN_SHARE * abs(miss)):
                candidates.append((abs(value), axis, c, value, miss))
    for _, axis, c, value, miss in sorted(candidates, key=lambda t: -t[0])[:MAX_NAMED]:
        c.update(named=True, share=_r(value / miss))
    out["drivers"] = _drivers(me, usual, lateral, depth, within=bool(within))

    # Status and tier.
    speed_named = any(d["key"] == "release_speed" and d["named"] for d in out["drivers"])
    used_statuses = me["statuses"] + [s for s in (me["direction_status"], me["speed_status"] if speed_named else None) if s]
    if me["miss_x"] is None or me["miss_y"] is None:
        out["status"] = "partial"
    elif "estimated" in used_statuses:
        out["status"] = "estimated"
    out["reason"] = " ".join(reasons) or None
    return _finish(out)


def _drivers(me: dict[str, Any], usual: dict[str, Any], lateral: list[dict[str, Any]] | None,
             depth: list[dict[str, Any]] | None, *, within: bool) -> list[dict[str, Any]]:
    """Release speed, release angle and launch direction against the athlete's usual."""
    carry = next((c for c in depth or [] if c["key"] == "carry"), {})
    aim = next((c for c in lateral or [] if c["key"] == "aim"), {})
    run = me["run_m"]
    out = []

    def add(key: str, label: str, value, typical, noise, unit, status, implied=None, named=False):
        delta = _sub(value, typical)
        out.append({"key": key, "label": label, "value": _r(value, 3), "usual": _r(typical, 3), "delta": _r(delta, 3),
                    "noise": noise, "unit": unit, "status": status,
                    "implied_in": _r(implied(delta)) if implied is not None and delta is not None else None,
                    "named": bool(not within and delta is not None and named and named(delta))})

    add("release_speed", "Release speed", me["speed"], usual["speed"], RELEASE_SPEED_NOISE_M_S, "m/s", me["speed_status"],
        implied=lambda d: d * CARRY_M_PER_M_S / INCH_M,
        named=lambda d: (carry.get("named") and carry.get("basis") == "usual" and carry.get("in") is not None
                         and abs(d) >= RELEASE_SPEED_NOISE_M_S and _sign(d) == _sign(carry["in"])))
    # Never named: near 40–45° one degree moves the carry ≈ 0.03 m (≈ 1 in), under the carry's own noise.
    add("release_angle", "Release angle", me["angle"], usual["angle"], RELEASE_ANGLE_NOISE_DEG, "°", me["angle_status"])
    usual_psi = usual["psi_deg"] if me["direction_source"] is not None else None
    add("launch_direction", "Launch direction", me["psi_deg"], usual_psi, LAUNCH_DIRECTION_NOISE_DEG, "°",
        me["direction_status"],
        implied=(lambda d: run * math.tan(math.radians(d)) / INCH_M) if run is not None else None,
        named=lambda d: (aim.get("named") and aim.get("basis") == "usual" and abs(d) >= LAUNCH_DIRECTION_NOISE_DEG
                         and _sign(d) == _sign(aim.get("test_in"))))
    return out


# ------------------------------------------------------------------------------------------------
# The coach sentence (v2)


def _inches(value: float) -> int:
    return int(round(abs(value)))


def _side(value: float) -> str:
    return "right" if value > 0 else "left"


def _depth_text(value: float | None) -> str:
    if value is None:
        return "distance not measured"
    return "on distance" if _inches(value) == 0 else f"{_inches(value)} in {'long' if value > 0 else 'short'}"


def _lateral_text(value: float | None) -> str:
    if value is None:
        return "left/right not measured"
    return "on line" if _inches(value) == 0 else f"{_inches(value)} in {_side(value)}"


def _degrees(value: float) -> str:
    return "less than 1°" if round(abs(value)) == 0 else f"about {round(abs(value)):.0f}°"


def _speed(value: float) -> str:
    return f"about {abs(value):.1f} m/s {'faster' if value > 0 else 'slower'}"


def _lead_part(att: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    """The named part the sentence speaks about: on an axis outside the usual spread when there is one, then the
    largest."""
    inside = att.get("inside_spread") or {}
    named = [(axis, c) for axis in ("lateral", "depth") for c in ((att.get(axis) or {}).get("components") or [])
             if c.get("named") and c.get("test_in") is not None]
    if not named:
        return None
    return min(named, key=lambda t: (inside.get(t[0]) is True, -abs(t[1]["test_in"])))


def _part_phrase(c: dict[str, Any], drivers: dict[str, dict[str, Any]]) -> str:
    key, test, basis = c["key"], c["test_in"], c.get("basis")
    n = _inches(test)
    if key == "release_position":
        return f"the release point ({n} in further {_side(test)} than usual)"
    if key == "aim":
        direction = drivers.get("launch_direction") or {}
        if basis == "usual":
            delta = direction.get("delta")
            if delta is not None and _sign(delta) == _sign(test):
                return f"aim (launched {_degrees(delta)} {_side(test)} of your usual line)"
            return f"aim (launched {n} in {_side(test)} of your usual line)"
        distance = c.get("distance_m")
        if distance:
            return f"aim (launched {_degrees(math.degrees(math.atan2(test * INCH_M, distance)))} {_side(test)} of the hole)"
        return f"aim (it touched down {n} in {_side(test)} of the hole)"
    if key == "slide_drift":
        return f"the slide (it moved {n} in {_side(test)} after landing)"
    if key == "carry":
        if basis == "usual":
            speed = drivers.get("release_speed") or {}
            extra = f", {_speed(speed['delta'])} release" if speed.get("named") and speed.get("delta") is not None else ""
            return f"the carry (it landed {n} in {'longer' if test > 0 else 'shorter'} than usual{extra})"
        return f"the carry (it landed {n} in {'past' if test > 0 else 'short of'} the hole)"
    if key == "slide":
        if basis == "usual":
            return f"the slide (it slid {n} in {'further' if test > 0 else 'less'} than usual)"
        return f"the slide (it slid {n} in after landing)" if test > 0 else f"the slide (it moved back {n} in after landing)"
    return str(c.get("label", key)).lower()


def _cue(c: dict[str, Any]) -> str | None:
    """One next-throw cue in the athlete's words (external focus) for the part the sentence names.

    The slide (along or sideways) gets none: no measured release value explains it per throw (release angle →
    slide is an athlete-level association that no athlete passes yet), and moving the aim point after one odd
    slide only adds variance (council: Deming's funnel)."""
    key, test = c["key"], c["test_in"]
    if key == "aim":
        return f"Next: aim about {_inches(test)} in further {_side(-test)}."
    if key == "release_position":
        return "Next: release from your usual spot."
    if key == "carry":
        return "Next: throw a touch softer." if test > 0 else "Next: throw a touch harder."
    return None


def _clean(sentence: str, fallback: str) -> str:
    """Wording guard: nothing that reads as blame or a cause reaches the coach."""
    return fallback if _BANNED.search(sentence) else sentence


def build_sentence(att: dict[str, Any]) -> tuple[str, str | None]:
    """``[Result]: [N in short/long], [N in left/right]. [Largest named part]. [Next-throw cue].``

    Built from the attribution block alone, so the wording rules can be tested on any case. Inches are whole
    numbers, angles whole degrees, speed differences 0.1 m/s. The cue comes only when the miss is outside the
    athlete's normal spread on that axis (or when there is no usual yet)."""
    result = att.get("result")
    if result == "throughHole":
        return "In the hole. Nothing to change.", None
    if result is None or att.get("status") == "unavailable":
        reason = str(att.get("reason") or "There is no result for this throw yet.").strip().rstrip(".")
        return _clean(f"{reason}. Check the video.", "No result for this throw yet. Check the video."), None
    lead = {"onBoard": "Board", "offBoard": "Off the board"}.get(result, "Ended")
    lateral, depth = att.get("lateral") or {}, att.get("depth") or {}
    mx, my = lateral.get("miss_in"), depth.get("miss_in")
    drivers = {d["key"]: d for d in att.get("drivers") or []}
    if mx is None and my is None:
        where = ("it stopped on the floor where the cameras could not measure it" if att.get("rest_on") == "floor"
                 else "where it stopped was out of the cameras' view")
        sentence = f"{lead}: {where}."
        delta = (drivers.get("launch_direction") or {}).get("delta")
        if delta is not None and abs(delta) >= NAME_MIN_NOISE_RATIO * LAUNCH_DIRECTION_NOISE_DEG:
            sentence += f" It was launched {_degrees(delta)} {_side(delta)} of your usual line."
        return _clean(sentence, f"{lead}."), None
    if mx is None or my is None:
        # One direction only (a bag off the board placed across but not along, or the reverse): the known part,
        # what is missing, nothing named and no cue.
        known = _lateral_text(mx) if my is None else _depth_text(my)
        missing = ("it stopped on the floor where the distance could not be measured"
                   if my is None and att.get("rest_on") == "floor" else
                   "distance not measured" if my is None else "left/right not measured")
        return _clean(f"{lead}: {known}; {missing}.", f"{lead}."), None
    sentence = f"{lead}: {_depth_text(my)}, {_lateral_text(mx)}."
    if att.get("within_usual_spread"):
        tail = " Normal spread: keep the same throw." if result == "onBoard" else " Within your normal spread."
        return _clean(sentence + tail, sentence), None
    if mx is not None and my is not None and abs(mx) < AXIS_MIN_MISS_IN and abs(my) < AXIS_MIN_MISS_IN:
        return _clean(sentence + " Close to the hole: keep the same throw.", sentence), None
    picked = _lead_part(att)
    if picked is None:
        return _clean(sentence + " No single measured part stands out.", sentence), None
    axis, part = picked
    miss = mx if axis == "lateral" else my
    word = (_side(miss) if axis == "lateral" else ("long" if miss > 0 else "short"))
    share = abs(part.get("share") or 0.0)
    opener = "Most of the" if share >= MOST_SHARE else "About half of the"
    sentence += f" {opener} {word} came from {_part_phrase(part, drivers)}."
    gate = (att.get("inside_spread") or {}).get(axis)
    cue = _cue(part) if gate is not True else None
    if cue:
        sentence += f" {cue}"
    base = f"{lead}: {_depth_text(my)}, {_lateral_text(mx)}."
    cleaned = _clean(sentence, base)
    return cleaned, (cue if cleaned == sentence else None)


def tier_of(att: dict[str, Any]) -> str:
    """Wording tier (council §1): "within_spread" inside the usual group; "physics" when the sentence's part has a
    named release driver next to it (speed with carry, launch direction with aim); otherwise "geometry"."""
    if att.get("within_usual_spread"):
        return "within_spread"
    picked = _lead_part(att)
    if picked is None:
        return "geometry"
    driver = {"carry": "release_speed", "aim": "launch_direction"}.get(picked[1]["key"])
    named = {d["key"] for d in att.get("drivers") or [] if d.get("named")}
    return "physics" if driver in named else "geometry"


def explanation_from_attribution(att: dict[str, Any]) -> dict[str, Any]:
    """two_view ``explanation`` built from the attribution: the keys the app reads (``sentence``, ``kind``,
    ``parts``) plus ``cue``, ``tier`` and ``version``."""
    result = att.get("result")
    mx, my = (att.get("lateral") or {}).get("miss_in"), (att.get("depth") or {}).get("miss_in")
    parts = []
    if result not in (None, "throughHole"):
        if my is not None and abs(my) >= AXIS_MIN_MISS_IN:
            parts.append({"axis": "distance", "inches": my, "word": "long" if my > 0 else "short"})
        if mx is not None and abs(mx) >= AXIS_MIN_MISS_IN:
            parts.append({"axis": "direction", "inches": mx, "word": _side(mx)})
    if result == "throughHole":
        kind = "made"
    elif result is None or att.get("status") == "unavailable":
        kind = "unknown"
    elif mx is not None and my is not None and abs(mx) < AXIS_MIN_MISS_IN and abs(my) < AXIS_MIN_MISS_IN:
        kind = "close"
    else:
        kind = "miss"
    return {"sentence": att.get("sentence"), "kind": kind, "parts": parts, "cue": att.get("cue"),
            "tier": att.get("tier"), "version": SENTENCE_VERSION}


def _finish(att: dict[str, Any]) -> dict[str, Any]:
    att["tier"] = tier_of(att)
    att["sentence"], att["cue"] = build_sentence(att)
    return att


def attribution_for_analysis(analysis_dir: str | Path, record: dict[str, Any] | None = None,
                             results: dict[str, Any] | None = None,
                             release_distance_m: float | None = None) -> dict[str, Any]:
    """Attribution for a throw folder against the athlete's other analysed throws (no video is read)."""
    here = Path(analysis_dir)
    record = record if record is not None else json.loads((here / "two_view.json").read_text())
    results = results if results is not None else json.loads((here / "results.json").read_text())
    if release_distance_m is None:
        release_distance_m = _num((results.get("summaries") or {}).get("release_to_board_front_m"))
    if release_distance_m is None:
        from .two_view import athlete_release_distance
        release_distance_m = athlete_release_distance(here)
    return attribute(record, results, siblings=sibling_records(here), release_distance_m=release_distance_m)
