"""Bag-only mechanics and drag-free projectile sensitivities (2D throw plane, x toward board, y up, SI).

Everything here describes the BAG: net external force and power on a regulation
bag, its momentum and energy. None of it is a muscle, joint or hand-contact force.

References: Venkadesan & Mahadevan 2017 (error propagation through the flight;
the most accurate throw is slightly faster than the minimum speed); Nasu et al.
2014 and Hore & Watts 2011 (release-timing sensitivity along the hand path).
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from .bag import GRAVITY_M_S2
from .filtering import derivative
from .regulation import BAG_MASS_KG, Board
from .zones import _first_root

G_VECTOR = np.array([0.0, -GRAVITY_M_S2])
BAG_ONLY_NOTE = ("Bag-only: net external force/power on the bag. Not a muscle, joint or hand-contact force, "
                 "and says nothing about shoulder or elbow loading.")


def release_state(vx: float, vy: float, height_m: float, mass_kg: float = BAG_MASS_KG) -> dict[str, Any]:
    speed2 = vx * vx + vy * vy
    ke = 0.5 * mass_kg * speed2
    pe = mass_kg * GRAVITY_M_S2 * height_m
    return {"momentum_kg_m_s": [mass_kg * vx, mass_kg * vy],
            "momentum_magnitude_kg_m_s": mass_kg * math.sqrt(speed2),
            "kinetic_energy_j": ke, "potential_energy_j": pe, "mechanical_energy_j": ke + pe}


def net_force_on_bag(acceleration_m_s2: np.ndarray, mass_kg: float) -> np.ndarray:
    """F = m (a − g⃗), g⃗ = (0, −g): the force the hand must apply for the bag to accelerate by a."""
    return mass_kg * (np.asarray(acceleration_m_s2, float) - G_VECTOR)


def power_on_bag(force_n: np.ndarray, velocity_m_s: np.ndarray) -> np.ndarray:
    return np.einsum("ij,ij->i", np.asarray(force_n, float), np.asarray(velocity_m_s, float))


def energy_rate(velocity_m_s: np.ndarray, position_m: np.ndarray, mass_kg: float, fps: float) -> np.ndarray:
    """dE/dt with E = ½ m |v|² + m g y (numerical consistency check for F·v)."""
    v = np.asarray(velocity_m_s, float)
    energy = 0.5 * mass_kg * np.sum(v * v, axis=1) + mass_kg * GRAVITY_M_S2 * np.asarray(position_m, float)[:, 1]
    return derivative(energy, fps)


def deck_plane_landing(vx: float, vy: float, height_m: float, to_front_m: float, board: Board) -> float | None:
    """Horizontal distance from release to where the path meets the (extended) deck plane."""
    if vx <= 0:
        return None
    tan_a = math.tan(board.angle)
    t = _first_root(-0.5 * GRAVITY_M_S2, vy - vx * tan_a, height_m - board.front_height_m + to_front_m * tan_a)
    return None if t is None else vx * t


def _hole_x(to_front_m: float, board: Board) -> float:
    return to_front_m + board.hole_along * math.cos(board.angle)


def along_error_m(vx: float, vy: float, height_m: float, to_front_m: float, board: Board) -> float | None:
    x = deck_plane_landing(vx, vy, height_m, to_front_m, board)
    return None if x is None else x - _hole_x(to_front_m, board)


def required_speed(angle_deg: float, height_m: float, to_front_m: float, board: Board) -> float | None:
    """Closed form: y(X) = h + X tanθ − g X² / (2 v² cos²θ) passes through the hole centre."""
    X = _hole_x(to_front_m, board)
    Y = board.deck_height_at(board.hole_along * math.cos(board.angle))
    th = math.radians(angle_deg)
    denom = 2 * math.cos(th) ** 2 * (height_m + X * math.tan(th) - Y)
    return None if denom <= 0 else math.sqrt(GRAVITY_M_S2 * X * X / denom)


def minimum_speed(height_m: float, to_front_m: float, board: Board) -> float:
    """Minimum release speed over all angles that reaches the hole centre: v² = g (Δy + √(X² + Δy²))."""
    X = _hole_x(to_front_m, board)
    dy = board.deck_height_at(board.hole_along * math.cos(board.angle)) - height_m
    return math.sqrt(GRAVITY_M_S2 * (dy + math.hypot(X, dy)))


def _error(speed: float, angle_deg: float, height_m: float, to_front_m: float, board: Board) -> float | None:
    th = math.radians(angle_deg)
    return along_error_m(speed * math.cos(th), speed * math.sin(th), height_m, to_front_m, board)


def landing_jacobian(speed: float, angle_deg: float, height_m: float, to_front_m: float, board: Board) -> dict[str, float]:
    """Central differences of landing position (m) w.r.t. release speed (m/s), angle (°) and height (m)."""
    steps = {"speed": 0.01, "angle": 0.1, "height": 0.005}
    base = {"speed": speed, "angle": angle_deg, "height": height_m}
    out = {}
    for name, h in steps.items():
        hi, lo = dict(base), dict(base)
        hi[name] += h
        lo[name] -= h
        e_hi = _error(hi["speed"], hi["angle"], hi["height"], to_front_m, board)
        e_lo = _error(lo["speed"], lo["angle"], lo["height"], to_front_m, board)
        out[f"d_{name}"] = float("nan") if e_hi is None or e_lo is None else (e_hi - e_lo) / (2 * h)
    return out


def error_budget(jacobian: dict[str, float], sd: dict[str, float]) -> dict[str, Any]:
    """σ_R² ≈ Σ (∂R/∂q σ_q)² — share of landing spread from each release variable (independence assumed)."""
    comps = {k: abs(jacobian[f"d_{k}"] * sd[k]) for k in ("speed", "angle", "height")}
    total2 = sum(c * c for c in comps.values())
    shares = {k: (c * c / total2 if total2 > 0 else 0.0) for k, c in comps.items()}
    return {"components_m": comps, "shares": shares, "predicted_sd_m": math.sqrt(total2),
            "assumption": "Release variables treated as independent; covariation is reported separately."}


def _landing_x_from_state(position, velocity, to_front_now, board) -> float | None:
    x = deck_plane_landing(float(velocity[0]), float(velocity[1]), float(position[1]), to_front_now, board)
    return None if x is None else float(position[0]) + x


def timing_sensitivity(position_m: np.ndarray, velocity_m_s: np.ndarray, release: int, fps: float,
                       to_front_at_release_m: float, board: Board) -> float | None:
    """Landing change (m) per 10 ms later release, from the hand path around release (Nasu et al. 2014)."""
    if not 1 <= release < len(position_m) - 1:
        return None
    x_front = float(position_m[release, 0]) + to_front_at_release_m
    xs = []
    for k in (release - 1, release + 1):
        if not (np.isfinite(position_m[k]).all() and np.isfinite(velocity_m_s[k]).all()):
            return None
        xs.append(_landing_x_from_state(position_m[k], velocity_m_s[k], x_front - float(position_m[k, 0]), board))
    if None in xs:
        return None
    return (xs[1] - xs[0]) / (2.0 / fps) * 0.010
