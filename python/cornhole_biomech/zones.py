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
from .regulation import Board  # noqa: F401  (re-exported; regulation.py is the single source)


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


# ---------------------------------------------------------------------------------------------
# Personal green zone: this athlete's height, distance, slide and consistency
# ---------------------------------------------------------------------------------------------

DEFAULT_SLIDE_ALLOWANCE_M = ZoneSettings.slide_allowance_m
MIN_PERSONAL_THROWS = 3
SLIDE_ALLOWANCE_LIMITS_M = (0.10, 0.70)
PERSONAL_ANGLE_GRID = (10.0, 70.0, 0.5)
PERSONAL_SPEED_GRID = (3.0, 11.0, 0.02)
ANGLE_REACH_DEG = 8.0     # best aim is searched within the athlete's own angle range ± this


def personal_slide_allowance(slides_in: list[float]) -> tuple[float, str, int]:
    """How far short of the hole centre this athlete's bags can land and still slide to the hole.

    From the board video: each throw's measured slide (touchdown → rest or drop, inches along the deck).
    The median slide of throws that stayed on the board is the personal allowance; with fewer than
    three measured slides the stated default is kept.
    """
    values = [float(v) for v in slides_in if v is not None and np.isfinite(v) and v >= 0]
    if len(values) < MIN_PERSONAL_THROWS:
        return DEFAULT_SLIDE_ALLOWANCE_M, "assumed", len(values)
    metres = float(np.median(values)) * 0.0254
    lo, hi = SLIDE_ALLOWANCE_LIMITS_M
    return float(min(max(metres, lo), hi)), "measured_median_slide", len(values)


def green_grid(height: float, settings: ZoneSettings) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Boolean hole-window map over release angle (columns) × speed (rows) at one height and distance."""
    a0, a1, da = PERSONAL_ANGLE_GRID
    s0, s1, ds = PERSONAL_SPEED_GRID
    angles = np.arange(a0, a1 + da / 2, da)
    speeds = np.arange(s0, s1 + ds / 2, ds)
    green = np.zeros((len(speeds), len(angles)), bool)
    for j, angle in enumerate(angles):
        # For a fixed angle first contact moves forward with speed: bisect the window edges.
        for i, speed in enumerate(speeds):
            green[i, j] = predicted_zone(float(speed), float(angle), height, settings)["zone"] == "green"
    return angles, speeds, green


def _smooth_probability(green: np.ndarray, sd_rows: float, sd_cols: float) -> np.ndarray:
    """P(green) when aiming at each cell with Gaussian release noise (SDs in grid cells)."""
    import cv2
    img = green.astype(np.float32)
    kx = max(1, int(6 * sd_cols) | 1)
    ky = max(1, int(6 * sd_rows) | 1)
    return cv2.GaussianBlur(img, (kx, ky), sigmaX=max(sd_cols, 1e-3), sigmaY=max(sd_rows, 1e-3),
                            borderType=cv2.BORDER_CONSTANT)


def personal_zone(rows: list[dict[str, Any]], settings: ZoneSettings, slides_in: list[float],
                  distance_source: str) -> dict[str, Any]:
    """The athlete's own green zone and the release that gives them the best chance of the hole window.

    Personal inputs: median measured release HEIGHT (stature, knee bend and arm length show up here),
    the measured release-to-board DISTANCE, the athlete's measured SLIDE on the board, and their
    throw-to-throw SPREAD of speed and angle (biomechanical consistency). For every aim point
    (speed, angle) the probability that a release scattered by that spread lands in the hole window
    is the green map blurred by a Gaussian of the athlete's SDs (speed and angle treated as
    independent; see the compensation analysis for their covariation). The best aim is searched
    within the athlete's own angle range ± 8°, so the suggestion stays a change they can make.
    A drag-free model: a guide for practice, not a guarantee.
    """
    keys = {"speed": "bag_release_speed_m_s", "angle": "bag_release_angle_deg", "height": "bag_release_height_m"}
    scaled = [r for r in rows if all(r.get(k) is not None and np.isfinite(r[k]) for k in keys.values())]
    slide_m, slide_source, n_slides = personal_slide_allowance(slides_in)
    base = {"slide_allowance_m": slide_m, "slide_source": slide_source, "slides_measured": n_slides,
            "distance_m": settings.release_to_board_m, "distance_source": distance_source,
            "regulation_distance_m": ZoneSettings().release_to_board_m,
            "method": personal_zone.__doc__.split("\n\n", 1)[1].strip() if personal_zone.__doc__ else ""}
    if len(scaled) < MIN_PERSONAL_THROWS:
        return {**base, "status": "needs_throws",
                "message": f"The personal green zone needs release speed, angle and height on at least "
                           f"{MIN_PERSONAL_THROWS} throws ({len(scaled)} so far)."}
    speed = np.array([r[keys["speed"]] for r in scaled], float)
    angle = np.array([r[keys["angle"]] for r in scaled], float)
    height = float(np.median([r[keys["height"]] for r in scaled]))
    personal = ZoneSettings(release_to_board_m=settings.release_to_board_m, slide_allowance_m=slide_m,
                            slide_up_m=settings.slide_up_m, board=settings.board)
    angles, speeds, green = green_grid(height, personal)
    sd_speed = float(np.std(speed, ddof=1)) if len(speed) > 1 else 0.0
    sd_angle = float(np.std(angle, ddof=1)) if len(angle) > 1 else 0.0
    da, ds = PERSONAL_ANGLE_GRID[2], PERSONAL_SPEED_GRID[2]
    prob = _smooth_probability(green, max(sd_speed, 0.05) / ds, max(sd_angle, 0.5) / da)

    def cell(v: float, a: float) -> tuple[int, int]:
        return (int(np.clip(round((v - speeds[0]) / ds), 0, len(speeds) - 1)),
                int(np.clip(round((a - angles[0]) / da), 0, len(angles) - 1)))

    current = (float(np.median(speed)), float(np.median(angle)))
    ci, cj = cell(*current)
    lo_angle = max(angles[0], float(np.min(angle)) - ANGLE_REACH_DEG)
    hi_angle = min(angles[-1], float(np.max(angle)) + ANGLE_REACH_DEG)
    allowed = (angles >= lo_angle) & (angles <= hi_angle)
    masked = np.where(allowed[None, :], prob, -1.0)
    bi, bj = np.unravel_index(int(np.argmax(masked)), masked.shape)
    column = green[:, cj]
    window = [float(speeds[column].min()), float(speeds[column].max())] if column.any() else None
    widths = [(float(angles[j]), float(green[:, j].sum() * ds)) for j in range(len(angles)) if allowed[j]]
    forgiving = max(widths, key=lambda w: w[1]) if widths else None
    in_green = [bool(green[cell(v, a)]) for v, a in zip(speed, angle)]
    return {**base, "status": "available", "height_m": height, "n": len(scaled),
            "sd_speed_m_s": sd_speed, "sd_angle_deg": sd_angle,
            "current": {"speed_m_s": current[0], "angle_deg": current[1], "p_green": float(prob[ci, cj]),
                        "speed_window_m_s": window},
            "best": {"speed_m_s": float(speeds[bi]), "angle_deg": float(angles[bj]), "p_green": float(prob[bi, bj])},
            "angle_limits_deg": [float(lo_angle), float(hi_angle)],
            "most_forgiving_angle": None if forgiving is None else {"angle_deg": forgiving[0], "speed_window_m_s": forgiving[1]},
            "throws_in_green": int(sum(in_green)),
            "sentence": personal_sentence(current, (float(speeds[bi]), float(angles[bj])), float(prob[ci, cj]),
                                          float(prob[bi, bj]))}


def personal_sentence(current: tuple[float, float], best: tuple[float, float], p_now: float, p_best: float) -> str:
    """Plain-language summary of the personal green zone for a coach."""
    if p_best - p_now < 0.05 or (abs(best[1] - current[1]) < 2 and abs(best[0] - current[0]) < 0.1):
        return (f"This athlete's usual release ({current[1]:.0f}° at {current[0]:.1f} m/s) already sits in the best part "
                f"of their green zone; the gain now comes from repeating it.")
    return (f"Aiming for about {best[1]:.0f}° at {best[0]:.1f} m/s instead of the usual {current[1]:.0f}° at "
            f"{current[0]:.1f} m/s would raise the model's chance of reaching the hole window from "
            f"{100 * p_now:.0f}% to {100 * p_best:.0f}%, with this athlete's current consistency.")
