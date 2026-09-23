"""Stress test of the analysis layer with simulated athletes whose ground truth is known.

Each simulated throw draws true release values around an athlete's mean, lets the
drag-free model decide where it first lands (zones.predicted_zone), converts that to
an observed bag value with some "bag behaviour" randomness (bounces/slides that change
the outcome independently of release), then adds measurement noise before the
analysis sees it. We then ask: does the scored-vs-missed analysis name the variable
that truly drives outcomes, and does it stay quiet when nothing does?
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .performance import performance_summary
from .zones import ZoneSettings, predicted_zone, speed_to_hole, zone_report

ZONE_SCORE = {"green": 3, "yellow": 1, "red": 0}


@dataclass(frozen=True)
class Athlete:
    name: str
    speed_sd: float           # m/s, true throw-to-throw spread
    angle_sd: float           # degrees
    height_sd: float          # m
    bag_randomness: float     # probability the outcome is replaced by a random one (bounce/slide/aim)
    outcomes_from_physics: bool = True


@dataclass(frozen=True)
class Noise:                  # measurement error of the video system (1 SD)
    speed: float = 0.12       # m/s
    angle: float = 1.0        # degrees
    height: float = 0.02      # m


def simulate_session(athlete: Athlete, n: int, rng: np.random.Generator, noise: Noise = Noise(),
                     settings: ZoneSettings = ZoneSettings()) -> list[dict[str, Any]]:
    angle0, height0 = 35.0, 0.85
    speed0 = speed_to_hole(angle0, height0, settings)
    rows = []
    for i in range(n):
        v = speed0 + rng.normal(0, athlete.speed_sd)
        a = angle0 + rng.normal(0, athlete.angle_sd)
        h = height0 + rng.normal(0, athlete.height_sd)
        score = ZONE_SCORE[predicted_zone(v, a, h, settings)["zone"]] if athlete.outcomes_from_physics \
            else int(rng.choice([0, 1, 3], p=[0.35, 0.45, 0.2]))
        if rng.random() < athlete.bag_randomness:
            score = int(rng.choice([0, 1, 3], p=[0.35, 0.45, 0.2]))
        rows.append({"trial_id": f"t{i}", "score_category": score,
                     "bag_release_speed_m_s": v + rng.normal(0, noise.speed),
                     "bag_release_angle_deg": a + rng.normal(0, noise.angle),
                     "bag_release_angle_se_deg": noise.angle / 2,
                     "bag_release_height_m": h + rng.normal(0, noise.height)})
    return rows


def run_scenario(athlete: Athlete, n: int, repeats: int, seed: int = 11) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    flagged: dict[str, int] = {}
    priority: dict[str, int] = {}
    any_flag = 0
    for _ in range(repeats):
        rows = simulate_session(athlete, n, rng)
        summary = performance_summary(rows, {})
        hits = [k for k, v in summary["variables"].items() if v["distinguishes"]]
        any_flag += bool(hits)
        for k in hits:
            flagged[k] = flagged.get(k, 0) + 1
        top = (zone_report(rows, ZoneSettings()).get("priority") or {}).get("variable")
        if top:
            priority[top] = priority.get(top, 0) + 1
    return {"athlete": athlete.name, "throws": n, "repeats": repeats,
            "any_difference_rate": any_flag / repeats,
            "flag_rate": {k: v / repeats for k, v in sorted(flagged.items())},
            "physics_priority_rate": {k: v / repeats for k, v in sorted(priority.items())}}


SCENARIOS = [
    Athlete("novice: inconsistent speed", speed_sd=0.45, angle_sd=2.0, height_sd=0.03, bag_randomness=0.15),
    Athlete("intermediate: inconsistent angle", speed_sd=0.10, angle_sd=6.0, height_sd=0.03, bag_randomness=0.15),
    Athlete("pro: tight release, misses from bag behaviour", speed_sd=0.08, angle_sd=1.0, height_sd=0.01, bag_randomness=0.30),
    Athlete("null: outcome unrelated to release", speed_sd=0.30, angle_sd=4.0, height_sd=0.03, bag_randomness=0.0,
            outcomes_from_physics=False),
]
