"""Physics-based green / yellow / red release zones and ACL-style sports statistics.

Zones answer "which release values put the bag where it scores?" for one athlete:

1. A drag-free 2D point-mass model (same equations as the app's Launch Explorer;
   drag changes the arc < 1.5 % for a 0.45 kg bag) predicts the bag's FIRST
   CONTACT from release speed, angle and height, and the release-to-board distance.
2. First contact maps to a zone, like a lab reference range for the outcome:
   green  = on the deck inside the hole window (from `slide_allowance_m` short of
            the hole centre to its far edge: bags landing short usually slide in),
   yellow = elsewhere on the deck, or up to `slide_up_m` short of the front edge,
   red    = further short, past the board, or into the front face.
   The two allowances are stated assumptions (editable), not measured constants.
3. For each release variable, the others are held at the athlete's median and the
   variable is scanned: the green/yellow/red intervals are its tolerance windows.
4. Every scaled throw is also placed in a zone and compared with its OBSERVED
   outcome (green↔3, yellow↔1, red↔0). The agreement rate tells the coach how far
   to trust the zones for this athlete and setup.

Sports statistics follow the American Cornhole League: points per round (PPR) =
4 bags × mean points per bag (gross, no cancellation), In% / On% / Off%.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .bag import GRAVITY_M_S2


@dataclass(frozen=True)
class Board:
    length_m: float = 1.2192          # 48 in deck
    front_height_m: float = 0.0762    # 3 in (regulation boards vary 2.5–4 in)
    back_height_m: float = 0.3048     # 12 in
    hole_from_back_m: float = 0.2286  # hole centre 9 in from the back
    hole_radius_m: float = 0.0762     # 6 in hole

    @property
    def angle(self) -> float:
        return float(np.arcsin((self.back_height_m - self.front_height_m) / self.length_m))

    @property
    def hole_along(self) -> float:
        return self.length_m - self.hole_from_back_m


@dataclass(frozen=True)
class ZoneSettings:
    release_to_board_m: float = 7.7   # horizontal, release point to the board's front edge (27 ft pitch minus reach)
    slide_allowance_m: float = 0.45   # green window extends this far short of the hole centre
    slide_up_m: float = 0.30          # a bag landing this close short of the board can still end on it
    board: Board = field(default_factory=Board)

    def zone_for(self, kind: str, along: float | None) -> str:
        b = self.board
        if kind == "board" and along is not None:
            if b.hole_along - self.slide_allowance_m <= along <= b.hole_along + b.hole_radius_m:
                return "green"
            return "yellow"
        if kind == "short" and along is not None and along >= -self.slide_up_m:
            return "yellow"
        return "red"


ZONE_OUTCOME = {"green": 3, "yellow": 1, "red": 0}


def _first_root(a: float, b: float, c: float) -> float | None:
    disc = b * b - 4 * a * c
    if disc < 0:
        return None
    roots = sorted(r for r in ((-b - np.sqrt(disc)) / (2 * a), (-b + np.sqrt(disc)) / (2 * a)) if r > 1e-12)
    return float(roots[0]) if roots else None


def landing(speed: float, angle_deg: float, height: float, distance: float, board: Board) -> dict[str, Any]:
    """First contact of a drag-free throw: floor before the board, front face, deck, or past it."""
    g = GRAVITY_M_S2
    vx, vy = speed * np.cos(np.radians(angle_deg)), speed * np.sin(np.radians(angle_deg))
    t_floor = _first_root(-0.5 * g, vy, height) or 0.0
    x_floor = vx * t_floor
    if x_floor < distance:
        return {"kind": "short", "horizontal_m": x_floor, "along_m": x_floor - distance, "time_s": t_floor}
    t_front = distance / vx
    if height + vy * t_front - 0.5 * g * t_front**2 < board.front_height_m:
        return {"kind": "front", "horizontal_m": distance, "along_m": None, "time_s": t_front}
    tan_a = np.tan(board.angle)
    t = _first_root(-0.5 * g, vy - vx * tan_a, height - board.front_height_m + distance * tan_a)
    if t is not None:
        along = (vx * t - distance) / np.cos(board.angle)
        if 0 <= along <= board.length_m:
            return {"kind": "board", "horizontal_m": vx * t, "along_m": float(along), "time_s": t}
    return {"kind": "long", "horizontal_m": x_floor, "along_m": None, "time_s": t_floor}


def predicted_zone(speed: float, angle_deg: float, height: float, settings: ZoneSettings) -> dict[str, Any]:
    hit = landing(speed, angle_deg, height, settings.release_to_board_m, settings.board)
    hole = None if hit["kind"] != "board" else hit["along_m"] - settings.board.hole_along
    return {**hit, "zone": settings.zone_for(hit["kind"], hit["along_m"]), "from_hole_m": hole}


def speed_to_hole(angle_deg: float, height: float, settings: ZoneSettings) -> float | None:
    """Release speed whose first contact is the hole centre (bisection; used for examples/tests)."""
    lo, hi = 0.5, 25.0
    def err(v: float) -> float:
        hit = landing(v, angle_deg, height, settings.release_to_board_m, settings.board)
        if hit["kind"] == "board":
            return hit["along_m"] - settings.board.hole_along
        return -1.0 if hit["kind"] in ("short", "front") else 1.0
    if not (err(lo) < 0 < err(hi)):
        return None
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if err(mid) < 0 else (lo, mid)
    return 0.5 * (lo + hi)


VARIABLE_RANGES = {   # scan ranges (units: m/s, degrees, metres)
    "speed": ("bag_release_speed_m_s", "Release speed", "m/s", 2.0, 14.0, 0.02),
    "angle": ("bag_release_angle_deg", "Release angle", "°", 0.0, 75.0, 0.1),
    "height": ("bag_release_height_m", "Release height", "m", 0.1, 2.2, 0.005),
}


def variable_zones(variable: str, center: dict[str, float], settings: ZoneSettings) -> dict[str, Any]:
    """Contiguous zone bands for one release variable, others held at `center`."""
    key, label, unit, lo, hi, step = VARIABLE_RANGES[variable]
    grid = np.arange(lo, hi + step / 2, step)
    zones = []
    for value in grid:
        p = dict(center)
        p[variable] = float(value)
        zones.append(predicted_zone(p["speed"], p["angle"], p["height"], settings)["zone"])
    bands: list[dict[str, Any]] = []
    for value, zone in zip(grid, zones):
        if bands and bands[-1]["zone"] == zone:
            bands[-1]["high"] = float(value)
        else:
            bands.append({"zone": zone, "low": float(value), "high": float(value)})
    return {"variable": variable, "key": key, "label": label, "unit": unit, "center": center[variable], "bands": bands}


def zone_report(rows: list[dict[str, Any]], settings: ZoneSettings) -> dict[str, Any]:
    """Zones around the athlete's median release plus a per-throw model-vs-outcome check."""
    keys = {name: spec[0] for name, spec in VARIABLE_RANGES.items()}
    scaled = [r for r in rows if all(r.get(k) is not None and np.isfinite(r[k]) for k in keys.values())]
    base = {"settings": {"release_to_board_m": settings.release_to_board_m, "slide_allowance_m": settings.slide_allowance_m,
                         "slide_up_m": settings.slide_up_m},
            "meaning": "Green/yellow/red = where a drag-free bag with these release values first lands: hole window / "
                       "elsewhere on the board / off. Model zones, checked against observed outcomes.",
            "variables": [], "throws": [], "agreement": {"n": 0, "agree": 0, "rate": None}}
    if not scaled:
        return {**base, "status": "needs_scale",
                "message": "Zones need release speed and height in metres (meter stick or a reviewed fixed-camera flight)."}
    center = {name: float(np.median([r[k] for r in scaled])) for name, k in keys.items()}
    throws = []
    for r in scaled:
        p = predicted_zone(r[keys["speed"]], r[keys["angle"]], r[keys["height"]], settings)
        observed = r.get("score_category")
        throws.append({"trial_id": r["trial_id"], "zone": p["zone"], "landing": p["kind"],
                       "from_hole_m": p["from_hole_m"], "observed": observed,
                       "agrees": None if observed is None else ZONE_OUTCOME[p["zone"]] == observed,
                       **{name: r[k] for name, k in keys.items()}})
    judged = [t for t in throws if t["agrees"] is not None]
    agree = sum(t["agrees"] for t in judged)
    variables = []
    for name, key in keys.items():
        zone = variable_zones(name, center, settings)
        greens = [b for b in zone["bands"] if b["zone"] == "green"]
        # Nearest green window to the athlete's median (a low and a high arc can both reach the hole).
        green = min(greens, key=lambda b: 0 if b["low"] <= center[name] <= b["high"]
                    else min(abs(center[name] - b["low"]), abs(center[name] - b["high"]))) if greens else None
        values = np.array([r[key] for r in scaled], float)
        sd = float(np.std(values, ddof=1)) if len(values) > 1 else None
        # Two separate coaching errors: variability (SD vs window half-width) and aim bias
        # (median vs window centre). A window is a model tolerance, not a measured one.
        half = None if green is None else (green["high"] - green["low"]) / 2
        middle = None if green is None else (green["high"] + green["low"]) / 2
        zone.update(green_window=None if green is None else [green["low"], green["high"]],
                    green_half_width=half, athlete_sd=sd,
                    aim_bias=None if middle is None else center[name] - middle,
                    demand_ratio=None if not half or sd is None or half <= 0 else sd / half)
        variables.append(zone)
    ranked = [v for v in variables if v["demand_ratio"] is not None]
    priority = max(ranked, key=lambda v: v["demand_ratio"]) if ranked else None
    return {**base, "status": "available", "center": center,
            "variables": variables,
            "priority": None if priority is None else {"variable": priority["variable"], "label": priority["label"],
                                                       "unit": priority["unit"], "sd": priority["athlete_sd"],
                                                       "half_width": priority["green_half_width"],
                                                       "demand_ratio": priority["demand_ratio"]},
            "throws": throws,
            "agreement": {"n": len(judged), "agree": agree, "rate": agree / len(judged) if judged else None}}


def sports_stats(scores: list[int | None]) -> dict[str, Any]:
    """ACL-style statistics from per-bag values (3 hole, 1 board, 0 off); unknown excluded."""
    known = [s for s in scores if s in (0, 1, 3)]
    n = len(known)
    pct = lambda value: 100 * sum(s == value for s in known) / n if n else None
    ppb = sum(known) / n if n else None
    return {"bags": n, "unknown": len(scores) - n, "points_per_bag": ppb,
            "ppr": None if ppb is None else 4 * ppb,
            "in_percent": pct(3), "on_percent": pct(1), "off_percent": pct(0),
            "definition": "PPR = 4 × mean points per bag (gross, no cancellation), as reported by the American Cornhole League."}
