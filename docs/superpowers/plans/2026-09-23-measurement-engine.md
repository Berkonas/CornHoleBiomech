# Measurement Engine Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Locate the athlete and the regulation board in each hand-held pilot clip, decide bag contact against the deck/floor instead of "where tracking stopped", express everything in a metric throw plane, and compute a body → release → flight → outcome chain with bag-only mechanics and within-athlete performance analyses.

**Architecture:** A Swift helper (`scene-vision`, Apple Vision person segmentation) writes person masks; Python tags bag candidates inside people so they cannot seed a flight. After the flight is chosen, a background plate in release-frame pixels is built, the board is detected on it and solved with `solvePnP` against regulation geometry, giving a metric **throw plane** (vertical plane through the board centreline). Contact, landing, suggested outcome, scale, chain quantities and analyses all use that plane.

**Tech Stack:** Python 3.12 (numpy, scipy, OpenCV 4.x), pytest; Swift 6.2 / SwiftPM, macOS 15, Vision + AVFoundation + ImageIO.

**Spec:** `docs/superpowers/specs/2026-09-23-measurement-engine-design.md`

## Global Constraints

- Regulation values (ACL): deck 48 × 24 in; back 12 in; front 3 in default (2.5–4 in allowed); hole Ø 6 in, centre 9 in from top edge, 12 in from sides; bag 6 × 6 in, 15.5–16 oz, nominal 15.75 oz = 0.4465 kg; pitch 27 ft front-to-front (sanity check only); g = `bag.GRAVITY_M_S2`.
- Axes everywhere in the chain: x toward the board (horizontal), y up, metres, SI units.
- Every reported quantity carries `state` ∈ {`measured`, `estimated`, `unavailable`} plus a reason when not measured.
- Mechanics are labelled **bag-only** ("net external force/power on the bag; not a muscle, joint or hand-contact force").
- Never report: joint moments, joint/muscle forces, wrist flexion, trunk axial rotation, lateral release direction, bag spin.
- Claims: within-athlete, associational wording, ≥ 5 throws per group, effect larger than noise floor, Holm correction across a pre-specified list.
- No new Python packages; no model downloads.
- Release frames on the 26 pilot clips must stay identical or within ±1 frame.
- Python test command: `MPLCONFIGDIR=$TMPDIR/mpl PYTHONPATH=python .venv/bin/python -m pytest tests -q`
- Swift build/test: `DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer CLANG_MODULE_CACHE_PATH=$TMPDIR/cmc SWIFTPM_MODULECACHE_OVERRIDE=$TMPDIR/cmc swift build --disable-sandbox --package-path app/CornholeBiomechanics`
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Board not visible / wrong red object picked** (a red bag lying on the floor, the red wall panel) → board confidence low, `board.status == "not_found"`, pipeline falls back to gravity scale with a labelled reason, no landing, no crash. Test in Task 4 (`test_red_bag_alone_is_not_a_board`, `test_blank_plate_returns_not_found`).
2. **Bag lost in mid-air above the board** (the reported bug) → `contact.kind == "lost_in_flight"`, `first_contact_frame is None`, predicted contact labelled `estimated`. Test in Task 5 (`test_mid_air_end_is_lost_in_flight`) and Task 7 (`test_auto_track_does_not_report_mid_air_contact`).
3. **`scene-vision` binary missing or masks mis-sized** (rotated video, different resolution) → masks ignored, `scene.masks_status == "unavailable"`, tracking identical to today. Test in Task 6 (`test_missing_binary_is_unavailable`, `test_mask_size_mismatch_is_rejected`).
4. **Throw line strongly oblique (φ > 20°)** → plane quantities flagged `estimated` with reason, not silently used as measured. Test in Task 4 (`test_oblique_board_flags_phi`).
5. **Too few throws / all outcomes missing** for analyses → each analysis returns `status: "insufficient_data"` with the count needed, never a claim. Test in Task 10 (`test_analyses_insufficient_data`).

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `python/cornhole_biomech/regulation.py` | create | regulation constants + `Board` dataclass |
| `python/cornhole_biomech/zones.py` | modify | import `Board` from `regulation` (re-export) |
| `python/cornhole_biomech/mechanics.py` | create | bag-only mechanics, deck-plane landing, sensitivities, energy match, timing sensitivity |
| `python/cornhole_biomech/background.py` | create | background plate in reference-frame pixels |
| `python/cornhole_biomech/board.py` | create | board detection, validation, PnP throw plane, deck homography, manual corners |
| `python/cornhole_biomech/contact.py` | create | contact classification, predicted contact, landing + suggested outcome |
| `app/CornholeBiomechanics/Sources/SceneVision/main.swift` | create | Vision person masks → PNG + index.json |
| `app/CornholeBiomechanics/Package.swift` | modify | add `SceneVision` executable target |
| `python/cornhole_biomech/scene.py` | create | run/locate `scene-vision`, load masks, tag candidates |
| `python/cornhole_biomech/auto_bag.py` | modify | person tags, board + contact integration, revision bump |
| `python/cornhole_biomech/pipeline.py` | modify | board scale, landing/outcome, chain record into results/summaries |
| `python/cornhole_biomech/chain.py` | create | per-throw chain record + Monte Carlo |
| `python/cornhole_biomech/chain_analysis.py` | create | within-athlete analyses |
| `python/cornhole_biomech/cli.py` | modify | `set-board-corners` command |
| `scripts/build_app.sh`, `app/.../AnalysisService.swift` | modify | ship and expose `scene-vision` |
| `scripts/regression_check.py` | modify | report contact kind, board status, release deltas |
| `docs/REFERENCES.md`, `docs/BIOMECHANICS_METHODS.md`, `docs/SCENE_REGRESSION.md` | modify/create | sources, methods, regression results |
| `python/cornhole_biomech/__init__.py` | modify | `METHOD_VERSION = "2026.09.23-scene"` |

---

### Task 1: Regulation constants

**Files:**
- Create: `python/cornhole_biomech/regulation.py`
- Modify: `python/cornhole_biomech/zones.py:1-50` (remove `Board` class body, import it)
- Test: `tests/test_regulation.py`

**Interfaces:**
- Produces: `INCH_M`, `OUNCE_KG`, `BAG_SIDE_M`, `BAG_MASS_KG`, `BAG_MASS_RANGE_KG: tuple[float, float]`, `PITCH_FRONT_TO_FRONT_M`, `Board` (frozen dataclass: `length_m, width_m, front_height_m, back_height_m, hole_from_back_m, hole_radius_m, hole_from_side_m`; properties `angle` (rad), `hole_along` (m from front edge along deck), `horizontal_length_m`, `deck_height_at(x_m) -> float`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_regulation.py
import math

import pytest

from cornhole_biomech import regulation, zones
from cornhole_biomech.regulation import BAG_MASS_KG, BAG_MASS_RANGE_KG, Board


def test_board_geometry_matches_acl():
    b = Board()
    assert b.length_m == pytest.approx(48 * 0.0254)
    assert b.width_m == pytest.approx(24 * 0.0254)
    assert b.hole_radius_m == pytest.approx(3 * 0.0254)
    assert b.hole_along == pytest.approx(39 * 0.0254)
    assert math.degrees(b.angle) == pytest.approx(10.8, abs=0.1)
    assert b.deck_height_at(0.0) == pytest.approx(3 * 0.0254)
    assert b.deck_height_at(b.horizontal_length_m) == pytest.approx(12 * 0.0254, abs=1e-6)


def test_bag_mass_range_contains_nominal():
    lo, hi = BAG_MASS_RANGE_KG
    assert lo == pytest.approx(0.4394, abs=1e-4) and hi == pytest.approx(0.4536, abs=1e-4)
    assert lo < BAG_MASS_KG < hi


def test_zones_uses_regulation_board():
    assert zones.Board is regulation.Board
    assert regulation.PITCH_FRONT_TO_FRONT_M == pytest.approx(8.2296)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `MPLCONFIGDIR=$TMPDIR/mpl PYTHONPATH=python .venv/bin/python -m pytest tests/test_regulation.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'cornhole_biomech.regulation'`

- [ ] **Step 3: Implement**

```python
# python/cornhole_biomech/regulation.py
"""Regulation cornhole equipment — one source for every calculation.

American Cornhole League rules and equipment pages (docs/REFERENCES.md). The front
height varies between certified boards (2.5–4 in); 3 in is the default and a
session may override it with the measured value.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

INCH_M = 0.0254
OUNCE_KG = 0.028349523125
BAG_SIDE_M = 6 * INCH_M
BAG_MASS_KG = 15.75 * OUNCE_KG
BAG_MASS_RANGE_KG = (15.5 * OUNCE_KG, 16.0 * OUNCE_KG)
PITCH_FRONT_TO_FRONT_M = 27 * 12 * INCH_M


@dataclass(frozen=True)
class Board:
    length_m: float = 48 * INCH_M
    width_m: float = 24 * INCH_M
    front_height_m: float = 3 * INCH_M
    back_height_m: float = 12 * INCH_M
    hole_from_back_m: float = 9 * INCH_M
    hole_radius_m: float = 3 * INCH_M
    hole_from_side_m: float = 12 * INCH_M

    @property
    def angle(self) -> float:
        """Deck slope in radians."""
        return math.asin((self.back_height_m - self.front_height_m) / self.length_m)

    @property
    def hole_along(self) -> float:
        """Hole centre, metres from the front edge measured along the deck."""
        return self.length_m - self.hole_from_back_m

    @property
    def horizontal_length_m(self) -> float:
        return self.length_m * math.cos(self.angle)

    def deck_height_at(self, x_m: float) -> float:
        """Deck surface height above the floor at horizontal distance x_m past the front edge."""
        return self.front_height_m + x_m * math.tan(self.angle)
```

In `python/cornhole_biomech/zones.py`, delete the `@dataclass(frozen=True) class Board: ...` block (fields `length_m` … `hole_along`) and add after the existing imports:

```python
from .regulation import Board  # noqa: F401  (re-exported; regulation.py is the single source)
```

- [ ] **Step 4: Run tests**

Run: `MPLCONFIGDIR=$TMPDIR/mpl PYTHONPATH=python .venv/bin/python -m pytest tests/test_regulation.py tests/test_zones.py tests/test_stress.py tests/test_coaching.py -q`
Expected: PASS (zones behaviour unchanged: same default values).

- [ ] **Step 5: Commit**

```bash
git add python/cornhole_biomech/regulation.py python/cornhole_biomech/zones.py tests/test_regulation.py
git commit -m "Add regulation.py as the single source of ACL board and bag constants

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Bag-only mechanics and projectile sensitivities

**Files:**
- Create: `python/cornhole_biomech/mechanics.py`
- Test: `tests/test_mechanics.py`

**Interfaces:**
- Consumes: `regulation.Board`, `regulation.BAG_MASS_KG`, `bag.GRAVITY_M_S2`, `zones._first_root`, `filtering.derivative`.
- Produces:
  - `release_state(vx: float, vy: float, height_m: float, mass_kg: float = BAG_MASS_KG) -> dict` keys `momentum_kg_m_s` ([px, py]), `momentum_magnitude_kg_m_s`, `kinetic_energy_j`, `potential_energy_j`, `mechanical_energy_j`.
  - `net_force_on_bag(acceleration_m_s2: np.ndarray (N,2), mass_kg) -> np.ndarray (N,2)`.
  - `power_on_bag(force_n: np.ndarray (N,2), velocity_m_s: np.ndarray (N,2)) -> np.ndarray (N,)`.
  - `energy_rate(velocity_m_s, position_m, mass_kg, fps) -> np.ndarray (N,)`.
  - `deck_plane_landing(vx, vy, height_m, to_front_m, board) -> float | None` (horizontal metres from release to where the path meets the extended deck plane).
  - `along_error_m(vx, vy, height_m, to_front_m, board) -> float | None` (landing minus hole centre, horizontal metres; + = long).
  - `required_speed(angle_deg, height_m, to_front_m, board) -> float | None` (speed that lands on the hole centre at this angle and height).
  - `minimum_speed(height_m, to_front_m, board) -> float` (minimum over angles).
  - `landing_jacobian(speed, angle_deg, height_m, to_front_m, board) -> dict` keys `d_speed` (m per m/s), `d_angle` (m per °), `d_height` (m per m).
  - `error_budget(jacobian: dict, sd: dict) -> dict` keys `components_m` {speed, angle, height}, `shares` {…}, `predicted_sd_m`.
  - `timing_sensitivity(position_m: np.ndarray (N,2), velocity_m_s: np.ndarray (N,2), release: int, fps: float, to_front_at_release_m: float, board) -> float | None` (metres of landing change per 10 ms of release delay).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_mechanics.py
import math

import numpy as np
import pytest

from cornhole_biomech import mechanics as m
from cornhole_biomech.bag import GRAVITY_M_S2 as G
from cornhole_biomech.regulation import BAG_MASS_KG, Board

B = Board()


def test_release_state_hand_computed():
    out = m.release_state(4.0, 3.0, 1.0, mass_kg=0.5)
    assert out["momentum_kg_m_s"] == pytest.approx([2.0, 1.5])
    assert out["momentum_magnitude_kg_m_s"] == pytest.approx(2.5)
    assert out["kinetic_energy_j"] == pytest.approx(0.5 * 0.5 * 25.0)
    assert out["potential_energy_j"] == pytest.approx(0.5 * G * 1.0)
    assert out["mechanical_energy_j"] == pytest.approx(6.25 + 0.5 * G)


def test_force_is_vector_with_gravity_on_y_only():
    a = np.array([[2.0, 0.0], [0.0, 0.0], [0.0, -G]])
    f = m.net_force_on_bag(a, 0.5)
    assert f[0] == pytest.approx([1.0, 0.5 * G])      # hand pushes forward AND holds the bag up
    assert f[1] == pytest.approx([0.0, 0.5 * G])      # bag at rest: hand supports its weight
    assert f[2] == pytest.approx([0.0, 0.0])          # free fall: no hand force


def test_power_equals_energy_rate_for_smooth_motion():
    fps = 240.0
    t = np.arange(0, 0.5, 1 / fps)
    pos = np.column_stack([3 * t + t**2, 1 + 2 * t - t**3])
    vel = np.column_stack([3 + 2 * t, 2 - 3 * t**2])
    acc = np.column_stack([np.full_like(t, 2.0), -6 * t])
    p_force = m.power_on_bag(m.net_force_on_bag(acc, BAG_MASS_KG), vel)
    p_energy = m.energy_rate(vel, pos, BAG_MASS_KG, fps)
    inner = slice(5, -5)
    assert np.allclose(p_force[inner], p_energy[inner], rtol=1e-2, atol=1e-2)


def test_deck_plane_landing_hits_hole_for_required_speed():
    v = m.required_speed(35.0, 0.9, 7.7, B)
    vx, vy = v * math.cos(math.radians(35)), v * math.sin(math.radians(35))
    assert m.along_error_m(vx, vy, 0.9, 7.7, B) == pytest.approx(0.0, abs=1e-6)
    assert m.minimum_speed(0.9, 7.7, B) <= v + 1e-9


def test_jacobian_matches_finite_difference_and_budget_sums():
    jac = m.landing_jacobian(9.0, 30.0, 0.9, 7.7, B)
    assert jac["d_speed"] > 0
    budget = m.error_budget(jac, {"speed": 0.2, "angle": 2.0, "height": 0.03})
    comps = budget["components_m"]
    assert budget["predicted_sd_m"] == pytest.approx(math.sqrt(sum(c**2 for c in comps.values())))
    assert sum(budget["shares"].values()) == pytest.approx(1.0)


def test_timing_sensitivity_zero_when_hand_path_matches_flight():
    # Hand already on the free-flight parabola: releasing earlier/later lands at the same place.
    fps = 60.0
    t = np.arange(0, 0.5, 1 / fps)
    pos = np.column_stack([-7.7 + 8 * t, 1.0 + 4 * t - 0.5 * G * t**2])
    vel = np.column_stack([np.full_like(t, 8.0), 4 - G * t])
    s = m.timing_sensitivity(pos, vel, 10, fps, 7.7 - 8 * t[10], B)
    assert s == pytest.approx(0.0, abs=5e-3)


def test_timing_sensitivity_positive_for_accelerating_hand():
    fps = 60.0
    t = np.arange(0, 0.5, 1 / fps)
    pos = np.column_stack([-7.7 + 4 * t + 10 * t**2, np.full_like(t, 1.0)])
    vel = np.column_stack([4 + 20 * t, np.full_like(t, 3.0)])
    assert m.timing_sensitivity(pos, vel, 10, fps, -pos[10, 0], B) > 0   # board front edge at x = 0
```

- [ ] **Step 2: Run to verify failure**

Run: `MPLCONFIGDIR=$TMPDIR/mpl PYTHONPATH=python .venv/bin/python -m pytest tests/test_mechanics.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'cornhole_biomech.mechanics'`

- [ ] **Step 3: Implement**

```python
# python/cornhole_biomech/mechanics.py
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
```

Positions passed to `timing_sensitivity` may use any horizontal origin; only the distance to the board's front edge at release matters.

- [ ] **Step 4: Run tests**

Run: `MPLCONFIGDIR=$TMPDIR/mpl PYTHONPATH=python .venv/bin/python -m pytest tests/test_mechanics.py -q`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add python/cornhole_biomech/mechanics.py tests/test_mechanics.py
git commit -m "Add bag-only mechanics: vector force, power, energy match, landing Jacobian, timing sensitivity

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Background plate

**Files:**
- Create: `python/cornhole_biomech/background.py`
- Test: `tests/test_background.py`

**Interfaces:**
- Consumes: `auto_bag.reference_chain` output (`dict[int, np.ndarray 3×3]`, frame pixels → reference pixels).
- Produces: `build_plate(frames: Sequence[np.ndarray], chain: dict[int, np.ndarray], person_masks: dict[int, np.ndarray] | None = None, max_samples: int = 60, scale: float = 0.5) -> dict` with keys `plate` (uint8 BGR, full resolution, reference pixels), `coverage` (float32 H×W, fraction of samples used), `samples` (int).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_background.py
import numpy as np

from cornhole_biomech.background import build_plate


def test_plate_removes_moving_object_and_undoes_camera_shift():
    h, w = 120, 160
    scene = np.zeros((h, w, 3), np.uint8)
    scene[40:80, 60:100] = (0, 0, 200)            # static red "board"
    frames, chain = [], {}
    for f in range(30):
        dx = f % 5                                  # hand-held drift, known transform
        img = np.roll(scene, dx, axis=1).copy()
        img[10:20, 5 * f % w:5 * f % w + 6] = 255   # moving white "bag"
        frames.append(img)
        chain[f] = np.array([[1, 0, -dx], [0, 1, 0], [0, 0, 1]], float)   # frame → reference
    out = build_plate(frames, chain, scale=1.0)
    plate = out["plate"]
    assert plate.shape == scene.shape
    assert np.abs(plate[45:75, 65:95].astype(int) - scene[45:75, 65:95]).max() <= 2
    assert plate[10:20, 20:140].max() < 60        # moving object gone


def test_person_mask_pixels_are_excluded():
    h, w = 60, 80
    frames = [np.full((h, w, 3), 100, np.uint8) for _ in range(10)]
    masks = {}
    for f in range(0, 10):
        frames[f][20:40, 20:40] = 250               # a person standing still in every frame
        m = np.zeros((h, w), np.uint8); m[20:40, 20:40] = 255
        masks[f] = m
    chain = {f: np.eye(3) for f in range(10)}
    out = build_plate(frames, chain, person_masks=masks, scale=1.0)
    assert out["coverage"][30, 30] == 0.0           # never visible → no plate evidence
    assert out["coverage"][5, 5] == 1.0
```

- [ ] **Step 2: Run to verify failure**

Run: `MPLCONFIGDIR=$TMPDIR/mpl PYTHONPATH=python .venv/bin/python -m pytest tests/test_background.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```python
# python/cornhole_biomech/background.py
"""Clean background plate in reference-frame pixels (hand-held camera motion removed).

Median over up to `max_samples` evenly spaced frames, each warped into the
reference frame; person-mask pixels are treated as missing. Computed at `scale`
per channel to bound memory, then resized to full resolution.
"""
from __future__ import annotations

from typing import Any, Sequence

import cv2
import numpy as np


def build_plate(frames: Sequence[np.ndarray], chain: dict[int, np.ndarray],
                person_masks: dict[int, np.ndarray] | None = None, max_samples: int = 60,
                scale: float = 0.5) -> dict[str, Any]:
    h, w = frames[0].shape[:2]
    sh, sw = max(1, int(round(h * scale))), max(1, int(round(w * scale)))
    S = np.diag([scale, scale, 1.0])
    usable = [f for f in range(len(frames)) if f in chain]
    picks = usable if len(usable) <= max_samples else [usable[i] for i in np.linspace(0, len(usable) - 1, max_samples).astype(int)]
    stack = np.full((len(picks), sh, sw, 3), np.nan, np.float32)
    for i, f in enumerate(picks):
        M = (S @ chain[f] @ np.linalg.inv(S))[:2]
        small = cv2.resize(frames[f], (sw, sh), interpolation=cv2.INTER_AREA) if scale != 1 else frames[f]
        warped = cv2.warpAffine(small, M, (sw, sh), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0))
        valid = cv2.warpAffine(np.full((sh, sw), 255, np.uint8), M, (sw, sh), flags=cv2.INTER_NEAREST) > 0
        if person_masks is not None:
            mask = _nearest_mask(person_masks, f)
            if mask is not None:
                mask = cv2.resize(mask, (sw, sh), interpolation=cv2.INTER_NEAREST)
                valid &= cv2.warpAffine(mask, M, (sw, sh), flags=cv2.INTER_NEAREST) == 0
        layer = warped.astype(np.float32)
        layer[~valid] = np.nan
        stack[i] = layer
    coverage = np.mean(np.isfinite(stack[..., 0]), axis=0).astype(np.float32)
    plate = np.zeros((sh, sw, 3), np.uint8)
    for c in range(3):
        with np.errstate(all="ignore"):
            med = np.nanmedian(stack[..., c], axis=0)
        plate[..., c] = np.nan_to_num(med, nan=0.0).clip(0, 255).astype(np.uint8)
    if scale != 1:
        plate = cv2.resize(plate, (w, h), interpolation=cv2.INTER_LINEAR)
        coverage = cv2.resize(coverage, (w, h), interpolation=cv2.INTER_NEAREST)
    return {"plate": plate, "coverage": coverage, "samples": len(picks)}


def _nearest_mask(masks: dict[int, np.ndarray], frame: int) -> np.ndarray | None:
    if frame in masks:
        return masks[frame]
    if not masks:
        return None
    nearest = min(masks, key=lambda k: abs(k - frame))
    return masks[nearest] if abs(nearest - frame) <= 2 else None
```

- [ ] **Step 4: Run tests** — same command; Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add python/cornhole_biomech/background.py tests/test_background.py
git commit -m "Add background plate in reference-frame pixels with person pixels excluded

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Board detection and metric throw plane

**Files:**
- Create: `python/cornhole_biomech/board.py`
- Test: `tests/test_board.py`

**Interfaces:**
- Consumes: `regulation.Board`, `regulation.INCH_M`.
- Produces:
  - `camera_matrix(width: int, height: int, hfov_deg: float) -> np.ndarray` (3×3).
  - `NOMINAL_HFOV_DEG = 65.0`, `HFOV_RANGE_DEG = (55.0, 75.0)`, `MAX_PHI_DEG = 20.0`.
  - `order_corners(quad: np.ndarray (4,2), target_direction: str) -> np.ndarray (4,2)` order: front-far, front-near, back-near, back-far.
  - `solve_board(corners_px: np.ndarray (4,2), image_size: tuple[int,int], board: Board = Board(), hfov_deg: float = NOMINAL_HFOV_DEG) -> BoardModel`.
  - `detect_board(plate: np.ndarray, target_direction: str, board: Board = Board()) -> dict` keys `status` ("found" | "not_found"), `corners_px` (list 4×2 in plate/reference pixels or None), `confidence` (0–1), `hole_offset_in` (float or None), `reasons` (list[str]).
  - `transfer_corners(src_plate, dst_plate, corners_px) -> np.ndarray | None` (ORB similarity between plates).
  - `class BoardModel` (dataclass) fields: `corners_px`, `hfov_deg`, `rvec`, `tvec`, `K`, `phi_deg`, `plane_H` (plane→image 3×3), `deck_H` (image→deck inches 3×3); methods:
    - `to_plane(points_px: np.ndarray (N,2)) -> np.ndarray (N,2)` → (x metres along throw line, +toward board back, origin under deck front-edge midpoint; y metres height above floor).
    - `to_deck_inches(points_px) -> np.ndarray (N,2)` → (u across 0..24 from far side, v along 0..48 from front edge).
    - `pixels_per_meter_at(point_px) -> float` (local plane scale).
    - `along_precision_in_per_px(point_px) -> float`, `across_precision_in_per_px(point_px) -> float`.
    - `as_dict() -> dict` (JSON-ready).

Geometry: board frame origin on the floor below the deck front-edge midpoint; X along throw line toward the back edge; Y up; Z across (near side +). Deck corners in 3D (m): front-far `(0, fh, −w/2)`, front-near `(0, fh, +w/2)`, back-near `(Lh, bh, +w/2)`, back-far `(Lh, bh, −w/2)` with `Lh = L cos α`, `bh = fh + L sin α`. Throw plane = `Z = 0`; plane→image homography `K [r_X r_Y t]`. φ = out-of-image-plane angle of the X axis = `degrees(asin(|R[2,0]|))`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_board.py
import math

import cv2
import numpy as np
import pytest

from cornhole_biomech.board import (MAX_PHI_DEG, NOMINAL_HFOV_DEG, camera_matrix, detect_board,
                                    order_corners, solve_board)
from cornhole_biomech.regulation import INCH_M, Board

W, H = 1920, 1080
B = Board()


def project_board(rvec, tvec, hfov=NOMINAL_HFOV_DEG):
    Lh, fh, bh, w = B.horizontal_length_m, B.front_height_m, B.front_height_m + B.length_m * math.sin(B.angle), B.width_m
    obj = np.array([[0, fh, -w / 2], [0, fh, w / 2], [Lh, bh, w / 2], [Lh, bh, -w / 2]], float)
    img, _ = cv2.projectPoints(obj, rvec, tvec, camera_matrix(W, H, hfov), None)
    return img.reshape(-1, 2)


def side_pose(phi_deg=8.0, distance=6.0):
    # camera looks along −Z of the board frame (board seen from its near side), slightly above
    R_look = cv2.Rodrigues(np.array([0.0, math.radians(phi_deg), 0.0]))[0]
    R_tilt = cv2.Rodrigues(np.array([math.radians(8.0), 0.0, 0.0]))[0]
    flip = np.array([[1, 0, 0], [0, -1, 0], [0, 0, -1]], float)   # board Y up → image y down, Z toward camera
    R = R_tilt @ R_look @ flip
    tvec = np.array([[1.5], [1.2], [distance]])
    return cv2.Rodrigues(R)[0], tvec


def render(corners, size=(H, W)):
    img = np.full(size + (3,), 150, np.uint8)
    cv2.fillConvexPoly(img, corners.astype(np.int32), (25, 25, 25))           # dark rim
    inner = corners.mean(axis=0) + 0.88 * (corners - corners.mean(axis=0))
    cv2.fillConvexPoly(img, inner.astype(np.int32), (30, 30, 190))           # red deck
    return img


def test_solve_recovers_plane_scale_and_phi():
    rvec, tvec = side_pose(phi_deg=8.0)
    corners = project_board(rvec, tvec)
    model = solve_board(order_corners(corners, "left_to_right"), (W, H), B)
    assert model.phi_deg == pytest.approx(8.0, abs=1.0)
    ends = model.to_plane(corners[[0, 3]])       # front-far and back-far lie off the Z=0 plane; use centreline
    mid_front, mid_back = corners[[0, 1]].mean(axis=0), corners[[2, 3]].mean(axis=0)
    xy = model.to_plane(np.array([mid_front, mid_back]))
    assert xy[1, 0] - xy[0, 0] == pytest.approx(B.horizontal_length_m, rel=0.03)
    assert xy[0, 1] == pytest.approx(B.front_height_m, abs=0.02)


def test_deck_inches_of_corners():
    rvec, tvec = side_pose()
    corners = order_corners(project_board(rvec, tvec), "left_to_right")
    model = solve_board(corners, (W, H), B)
    uv = model.to_deck_inches(corners)
    assert uv == pytest.approx(np.array([[0, 0], [24, 0], [24, 48], [0, 48]]), abs=0.5)


def test_detect_board_on_rendered_plate():
    rvec, tvec = side_pose()
    corners = project_board(rvec, tvec)
    out = detect_board(render(corners), "left_to_right", B)
    assert out["status"] == "found"
    assert np.abs(np.array(out["corners_px"]) - order_corners(corners, "left_to_right")).max() < 12


def test_blank_plate_returns_not_found():
    out = detect_board(np.full((H, W, 3), 150, np.uint8), "left_to_right", B)
    assert out["status"] == "not_found" and out["reasons"]


def test_red_bag_alone_is_not_a_board():
    img = np.full((H, W, 3), 150, np.uint8)
    cv2.rectangle(img, (900, 700), (930, 715), (30, 30, 190), -1)       # bag-sized red patch
    assert detect_board(img, "left_to_right", B)["status"] == "not_found"


def test_oblique_board_flags_phi():
    rvec, tvec = side_pose(phi_deg=35.0)
    model = solve_board(order_corners(project_board(rvec, tvec), "left_to_right"), (W, H), B)
    assert model.phi_deg > MAX_PHI_DEG
    assert model.as_dict()["phi_status"] == "estimated"
```

- [ ] **Step 2: Run to verify failure**

Run: `MPLCONFIGDIR=$TMPDIR/mpl PYTHONPATH=python .venv/bin/python -m pytest tests/test_board.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```python
# python/cornhole_biomech/board.py
"""Regulation board → metric throw plane.

Detection: red deck + dark rim on the background plate → convex quadrilateral.
Pose: solvePnP (IPPE, 4 coplanar deck corners with the regulation slope) under an
assumed horizontal field of view; the FOV range gives the scale uncertainty.
Throw plane: the vertical plane through the board centreline (athlete and bag are
assumed to move in it; out-of-plane angle φ is reported, > 20° is flagged).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from .regulation import INCH_M, Board

NOMINAL_HFOV_DEG = 65.0
HFOV_RANGE_DEG = (55.0, 75.0)
MAX_PHI_DEG = 20.0
MIN_DECK_AREA_FRACTION = 0.0015     # of the image; a lone bag is ~0.0002
MIN_CONFIDENCE = 0.5


def camera_matrix(width: int, height: int, hfov_deg: float) -> np.ndarray:
    f = (width / 2) / math.tan(math.radians(hfov_deg) / 2)
    return np.array([[f, 0, width / 2], [0, f, height / 2], [0, 0, 1]], float)


def _deck_object_points(board: Board) -> np.ndarray:
    Lh, fh, w = board.horizontal_length_m, board.front_height_m, board.width_m
    bh = fh + board.length_m * math.sin(board.angle)
    return np.array([[0, fh, -w / 2], [0, fh, w / 2], [Lh, bh, w / 2], [Lh, bh, -w / 2]], float)


def order_corners(quad: np.ndarray, target_direction: str) -> np.ndarray:
    """front-far, front-near, back-near, back-far. Front = end nearer the thrower; near = lower in image."""
    q = np.asarray(quad, float).reshape(4, 2)
    sign = 1.0 if target_direction == "left_to_right" else -1.0
    by_along = q[np.argsort(sign * q[:, 0])]
    front, back = by_along[:2], by_along[2:]
    front = front[np.argsort(front[:, 1])]   # smaller y (higher in image) = far side
    back = back[np.argsort(back[:, 1])]
    return np.array([front[0], front[1], back[1], back[0]])


@dataclass
class BoardModel:
    corners_px: np.ndarray
    hfov_deg: float
    K: np.ndarray
    rvec: np.ndarray
    tvec: np.ndarray
    phi_deg: float
    plane_H: np.ndarray
    deck_H: np.ndarray
    board: Board = field(default_factory=Board)

    def to_plane(self, points_px: np.ndarray) -> np.ndarray:
        p = cv2.perspectiveTransform(np.asarray(points_px, float).reshape(-1, 1, 2), np.linalg.inv(self.plane_H))
        return p.reshape(-1, 2)

    def to_deck_inches(self, points_px: np.ndarray) -> np.ndarray:
        return cv2.perspectiveTransform(np.asarray(points_px, float).reshape(-1, 1, 2), self.deck_H).reshape(-1, 2)

    def pixels_per_meter_at(self, point_px) -> float:
        p = np.asarray(point_px, float)
        a, b = self.to_plane(np.array([p, p + [1.0, 0.0]]))
        return 1.0 / max(1e-9, float(np.hypot(*(b - a))))

    def along_precision_in_per_px(self, point_px) -> float:
        p = np.asarray(point_px, float)
        a, b = self.to_plane(np.array([p, p + [1.0, 0.0]]))
        return abs(float(b[0] - a[0])) / INCH_M

    def across_precision_in_per_px(self, point_px) -> float:
        p = np.asarray(point_px, float)
        a, b = self.to_deck_inches(np.array([p, p + [0.0, 1.0]]))
        return abs(float(b[0] - a[0]))

    def as_dict(self) -> dict[str, Any]:
        return {"corners_px": self.corners_px.tolist(), "hfov_deg": self.hfov_deg, "phi_deg": self.phi_deg,
                "phi_status": "measured" if self.phi_deg <= MAX_PHI_DEG else "estimated",
                "phi_reason": None if self.phi_deg <= MAX_PHI_DEG else
                f"Throw line is {self.phi_deg:.0f}° out of the image plane (> {MAX_PHI_DEG:.0f}°); plane distances "
                "depend strongly on the assumed field of view.",
                "plane_H": self.plane_H.tolist(), "deck_H": self.deck_H.tolist(),
                "front_height_in": self.board.front_height_m / INCH_M}


def solve_board(corners_px: np.ndarray, image_size: tuple[int, int], board: Board = Board(),
                hfov_deg: float = NOMINAL_HFOV_DEG) -> BoardModel:
    corners = np.asarray(corners_px, float).reshape(4, 2)
    K = camera_matrix(image_size[0], image_size[1], hfov_deg)
    ok, rvec, tvec = cv2.solvePnP(_deck_object_points(board), corners, K, None, flags=cv2.SOLVEPNP_IPPE)
    if not ok:
        raise ValueError("Board pose could not be solved from these corners.")
    R = cv2.Rodrigues(rvec)[0]
    phi = math.degrees(math.asin(min(1.0, abs(R[2, 0]))))
    plane_H = K @ np.column_stack([R[:, 0], R[:, 1], tvec.ravel()])
    deck_uv = np.array([[0, 0], [24, 0], [24, 48], [0, 48]], np.float32)
    deck_H = cv2.getPerspectiveTransform(corners.astype(np.float32), deck_uv)
    return BoardModel(corners, hfov_deg, K, rvec, tvec, phi, plane_H, deck_H, board)


def _red_and_rim(plate: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    hsv = cv2.cvtColor(plate, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    red = (((h <= 10) | (h >= 170)) & (s >= 80) & (v >= 50)).astype(np.uint8)
    dark = (v <= 70).astype(np.uint8)
    return red, dark


def detect_board(plate: np.ndarray, target_direction: str, board: Board = Board()) -> dict[str, Any]:
    height, width = plate.shape[:2]
    red, dark = _red_and_rim(plate)
    red = cv2.morphologyEx(red, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(red, 8)
    best, reasons = None, []
    for i in range(1, count):
        area = stats[i, cv2.CC_STAT_AREA]
        if area < MIN_DECK_AREA_FRACTION * width * height:
            continue
        component = (labels == i).astype(np.uint8)
        # Grow into the adjacent dark rim so the quad reaches the deck's outer edge.
        grown = cv2.dilate(component, np.ones((9, 9), np.uint8))
        region = ((grown & dark) | component).astype(np.uint8)
        contours, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        hull = cv2.convexHull(max(contours, key=cv2.contourArea))
        quad = _four_corners(hull)
        if quad is None:
            continue
        ordered = order_corners(quad, target_direction)
        span = np.ptp(ordered[:, 0])
        if span < 2.0 * np.ptp(ordered[:, 1]) * 0.5:     # a side-view deck is wider than tall in the image
            continue
        fill = float(component.sum()) / max(1.0, cv2.contourArea(ordered.astype(np.float32)))
        hole_offset = _hole_offset_in(plate, ordered)
        confidence = 0.5 * min(1.0, fill / 0.6) + (0.5 if hole_offset is not None and hole_offset <= 4.0 else 0.0)
        if best is None or confidence > best["confidence"]:
            best = {"corners_px": ordered.tolist(), "confidence": confidence, "hole_offset_in": hole_offset}
    if best is None:
        return {"status": "not_found", "corners_px": None, "confidence": 0.0, "hole_offset_in": None,
                "reasons": ["No red deck with a dark rim large enough to be a regulation board was found."]}
    if best["confidence"] < MIN_CONFIDENCE:
        reasons.append(f"Best board candidate has confidence {best['confidence']:.2f} (< {MIN_CONFIDENCE}); "
                       "click the four deck corners instead.")
        return {**best, "status": "not_found", "reasons": reasons}
    return {**best, "status": "found", "reasons": reasons}


def _four_corners(hull: np.ndarray) -> np.ndarray | None:
    perimeter = cv2.arcLength(hull, True)
    for eps in np.linspace(0.01, 0.1, 19):
        approx = cv2.approxPolyDP(hull, eps * perimeter, True)
        if len(approx) == 4:
            return approx.reshape(4, 2).astype(float)
    return None


def _hole_offset_in(plate: np.ndarray, corners: np.ndarray, px_per_in: int = 6) -> float | None:
    """Rectify the deck and look for the dark hole near (12 in, 39 in from the front)."""
    dst = np.array([[0, 0], [24, 0], [24, 48], [0, 48]], np.float32) * px_per_in
    M = cv2.getPerspectiveTransform(corners.astype(np.float32), dst)
    deck = cv2.warpPerspective(plate, M, (24 * px_per_in, 48 * px_per_in))
    gray = cv2.cvtColor(deck, cv2.COLOR_BGR2GRAY)
    margin = 2 * px_per_in
    inner = gray[margin:-margin, margin:-margin]
    dark = (inner < max(20, np.percentile(inner, 5))).astype(np.uint8)
    count, _, stats, centroids = cv2.connectedComponentsWithStats(dark, 8)
    if count <= 1:
        return None
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    u, v = (centroids[i] + margin) / px_per_in
    return float(math.hypot(u - 12.0, v - 39.0))


def transfer_corners(src_plate: np.ndarray, dst_plate: np.ndarray, corners_px) -> np.ndarray | None:
    """Carry clicked corners from one clip's plate to another shot from the same position."""
    orb = cv2.ORB_create(3000)
    a = orb.detectAndCompute(cv2.cvtColor(src_plate, cv2.COLOR_BGR2GRAY), None)
    b = orb.detectAndCompute(cv2.cvtColor(dst_plate, cv2.COLOR_BGR2GRAY), None)
    if a[1] is None or b[1] is None:
        return None
    matches = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(a[1], b[1])
    if len(matches) < 30:
        return None
    src = np.float32([a[0][m.queryIdx].pt for m in matches])
    dst = np.float32([b[0][m.trainIdx].pt for m in matches])
    M, inliers = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=3.0)
    if M is None or int(inliers.sum()) < 20:
        return None
    c = np.asarray(corners_px, float).reshape(4, 2)
    return (M[:, :2] @ c.T).T + M[:, 2]
```

- [ ] **Step 4: Run tests**

Run: `MPLCONFIGDIR=$TMPDIR/mpl PYTHONPATH=python .venv/bin/python -m pytest tests/test_board.py -q`
Expected: PASS (6 tests). If `test_detect_board_on_rendered_plate` fails on the "wider than tall" guard, print `np.ptp` values and adjust only the synthetic `side_pose` tilt, not the guard: the pilot board is ~330 × 75 px.

- [ ] **Step 5: Check the real pilot plate (manual QA, 2 minutes)**

```bash
MPLCONFIGDIR=$TMPDIR/mpl PYTHONPATH=python .venv/bin/python - <<'EOF'
import cv2, json
from cornhole_biomech.auto_bag import read_frames, detect_moving_blobs_in_frames, reference_chain
from cornhole_biomech.background import build_plate
from cornhole_biomech.board import detect_board
frames, fps = read_frames("data/videos/Player 1/testsep17 - 1.mov")
_, to_prev = detect_moving_blobs_in_frames(frames)
plate = build_plate(frames, reference_chain(to_prev, 0))["plate"]
out = detect_board(plate, "left_to_right")
print(json.dumps({k: out[k] for k in ("status", "confidence", "hole_offset_in", "reasons")}))
if out["corners_px"]:
    import numpy as np
    cv2.polylines(plate, [np.int32(out["corners_px"])], True, (0, 255, 0), 3)
cv2.imwrite("/private/tmp/board_check.jpg", plate)
EOF
```

Open `/private/tmp/board_check.jpg`; the green outline must follow the deck. Record the result in the commit message.

- [ ] **Step 6: Commit**

```bash
git add python/cornhole_biomech/board.py tests/test_board.py
git commit -m "Detect the regulation board and solve a metric throw plane (PnP, phi, deck inches)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Contact classification, predicted contact, landing and suggested outcome

**Files:**
- Create: `python/cornhole_biomech/contact.py`
- Test: `tests/test_contact.py`

**Interfaces:**
- Consumes: `BoardModel.to_plane`, `BoardModel.to_deck_inches`, `regulation.Board`, `regulation.INCH_M`.
- Produces:
  - `DECK_TOLERANCE_M = 0.06`, `FLOOR_TOLERANCE_M = 0.06`, `HOLE_VANISH_RADIUS_IN = 4.0`.
  - `surface_at(point_px, model: BoardModel) -> str` ∈ {"deck", "front", "floor", "air"}.
  - `classify_flight_end(end_point_px, model) -> dict` keys `kind` ∈ {"deck", "front", "floor", "lost_in_flight"}, `plane_xy_m`.
  - `predict_contact(coef_x, coef_y, reference_frame: int, fps: float, last_frame: int, frame_count: int, to_reference: Callable[[int, np.ndarray], np.ndarray], model) -> dict | None` keys `frame`, `x_px`, `y_px` (reference pixels), `kind`, `state="estimated"`, `reason`.
  - `landing_summary(contact_point_px, model) -> dict` keys `plane_x_m`, `plane_y_m`, `along_error_m` (x − hole x), `deck_u_in`, `deck_v_in`, `on_deck` (bool), `along_precision_in`, `across_precision_in`.
  - `suggest_outcome(after_contact: dict | None, model) -> dict` keys `score` (3 | 1 | 0 | None), `basis` (str), `needs_confirmation=True`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_contact.py
import math

import numpy as np
import pytest

from cornhole_biomech.contact import (classify_flight_end, landing_summary, predict_contact, suggest_outcome,
                                      surface_at)
from cornhole_biomech.regulation import INCH_M, Board


class PlaneStub:
    """Image pixel (x, y) → plane metres: x/100 − 8, (1000 − y)/100 ; deck inches via the same map."""
    board = Board()

    def to_plane(self, pts):
        p = np.asarray(pts, float).reshape(-1, 2)
        return np.column_stack([p[:, 0] / 100 - 8.0, (1000 - p[:, 1]) / 100])

    def to_deck_inches(self, pts):
        xy = self.to_plane(pts)
        v = xy[:, 0] / math.cos(self.board.angle) / INCH_M
        return np.column_stack([np.full(len(v), 12.0), v])

    def along_precision_in_per_px(self, p):
        return 0.01 / INCH_M

    def across_precision_in_per_px(self, p):
        return 0.5


M = PlaneStub()


def px(x_m, y_m):
    return np.array([(x_m + 8.0) * 100, 1000 - y_m * 100])


def test_surfaces():
    b = M.board
    assert surface_at(px(0.5, b.deck_height_at(0.5) + 0.03), M) == "deck"
    assert surface_at(px(0.5, 0.8), M) == "air"
    assert surface_at(px(-1.0, 0.02), M) == "floor"
    assert surface_at(px(0.0, 0.03), M) == "front"


def test_mid_air_end_is_lost_in_flight():
    assert classify_flight_end(px(0.2, 0.9), M)["kind"] == "lost_in_flight"
    assert classify_flight_end(px(0.6, M.board.deck_height_at(0.6) + 0.02), M)["kind"] == "deck"


def test_predicted_contact_extends_parabola_to_deck():
    fps = 60.0
    # plane motion x = −2 + 6 t, y = 1.2 + 1 t − 4.9 t² expressed in pixels (stub map is linear)
    coef_x = [600.0, 600.0, 0.0]          # x_px = 600 + 600 t  →  plane x = −2 + 6 t
    coef_y = [1000 - 120.0, -100.0, 490.0]
    out = predict_contact(coef_x, coef_y, 0, fps, last_frame=10, frame_count=200,
                          to_reference=lambda f, p: p, model=M)
    assert out is not None and out["state"] == "estimated"
    assert out["kind"] in ("deck", "front", "floor")
    assert out["frame"] > 10


def test_landing_summary_along_error_relative_to_hole():
    b = M.board
    hole_x = b.hole_along * math.cos(b.angle)
    out = landing_summary(px(hole_x + 0.1, b.deck_height_at(hole_x + 0.1)), M)
    assert out["along_error_m"] == pytest.approx(0.1, abs=1e-6)
    assert out["on_deck"] is True


def test_suggest_outcome_rules():
    b = M.board
    hole_x = b.hole_along * math.cos(b.angle)
    hole_px = px(hole_x, b.deck_height_at(hole_x))
    lost_at_hole = {"status": "lost_after_contact", "rest": None,
                    "path": [{"x_release_frame": hole_px[0], "y_release_frame": hole_px[1]}]}
    assert suggest_outcome(lost_at_hole, M)["score"] == 3
    rest_on = {"status": "rest_found", "path": [], "rest": {"x_release_frame": px(0.4, 0.2)[0],
                                                           "y_release_frame": px(0.4, 0.2)[1]}}
    assert suggest_outcome(rest_on, M)["score"] == 1
    rest_off = {"status": "rest_found", "path": [], "rest": {"x_release_frame": px(-1.5, 0.0)[0],
                                                            "y_release_frame": px(-1.5, 0.0)[1]}}
    assert suggest_outcome(rest_off, M)["score"] == 0
    assert suggest_outcome(None, M)["score"] is None
```

- [ ] **Step 2: Run to verify failure**

Run: `MPLCONFIGDIR=$TMPDIR/mpl PYTHONPATH=python .venv/bin/python -m pytest tests/test_contact.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```python
# python/cornhole_biomech/contact.py
"""First contact against the deck/floor (not "where tracking stopped"), predicted contact, landing, outcome.

A flight whose last tracked point is still in the air is `lost_in_flight`: its
parabola is extended to the first deck/floor intersection and reported as an
ESTIMATED contact, never as a measured one.
"""
from __future__ import annotations

import math
from typing import Any, Callable

import numpy as np

from .regulation import INCH_M, BAG_SIDE_M

DECK_TOLERANCE_M = 0.06      # bag half-thickness + plane-mapping noise
FLOOR_TOLERANCE_M = 0.06
HOLE_VANISH_RADIUS_IN = 4.0  # hole radius 3 in + 1 in tracking slack
MAX_PREDICT_SECONDS = 1.5


def _plane(point_px, model) -> np.ndarray:
    return model.to_plane(np.asarray(point_px, float).reshape(1, 2))[0]


def surface_at(point_px, model) -> str:
    b = model.board
    x, y = _plane(point_px, model)
    half = BAG_SIDE_M / 2
    if -half <= x <= b.horizontal_length_m + half:
        if x < half and y <= b.front_height_m + DECK_TOLERANCE_M and y > FLOOR_TOLERANCE_M:
            return "front"
        if y - b.deck_height_at(min(max(x, 0.0), b.horizontal_length_m)) <= DECK_TOLERANCE_M:
            return "deck"
    if y <= FLOOR_TOLERANCE_M:
        return "floor"
    return "air"


def classify_flight_end(end_point_px, model) -> dict[str, Any]:
    kind = surface_at(end_point_px, model)
    return {"kind": "lost_in_flight" if kind == "air" else kind, "plane_xy_m": _plane(end_point_px, model).tolist()}


def predict_contact(coef_x, coef_y, reference_frame: int, fps: float, last_frame: int, frame_count: int,
                    to_reference: Callable[[int, np.ndarray], np.ndarray], model) -> dict[str, Any] | None:
    stop = min(frame_count - 1, last_frame + int(MAX_PREDICT_SECONDS * fps))
    for f in range(last_frame + 1, stop + 1):
        t = (f - reference_frame) / fps
        raw = np.array([np.polyval(list(coef_x)[::-1], t), np.polyval(list(coef_y)[::-1], t)])
        p = to_reference(f, raw)
        kind = surface_at(p, model)
        if kind != "air":
            return {"frame": f, "x_px": float(p[0]), "y_px": float(p[1]), "kind": kind, "state": "estimated",
                    "reason": "Bag lost in the air; contact predicted by extending the fitted flight to the deck/floor."}
    return None


def landing_summary(contact_point_px, model) -> dict[str, Any]:
    b = model.board
    x, y = _plane(contact_point_px, model)
    u, v = model.to_deck_inches(np.asarray(contact_point_px, float).reshape(1, 2))[0]
    return {"plane_x_m": float(x), "plane_y_m": float(y),
            "along_error_m": float(x - b.hole_along * math.cos(b.angle)),
            "deck_u_in": float(u), "deck_v_in": float(v),
            "on_deck": bool(0 <= u <= 24 and 0 <= v <= 48),
            "along_precision_in": model.along_precision_in_per_px(contact_point_px),
            "across_precision_in": model.across_precision_in_per_px(contact_point_px)}


def suggest_outcome(after_contact: dict[str, Any] | None, model) -> dict[str, Any]:
    base = {"needs_confirmation": True}
    if not after_contact:
        return {**base, "score": None, "basis": "No post-contact track; confirm in the video."}
    rest = after_contact.get("rest")
    if after_contact.get("status") == "rest_found" and rest:
        u, v = model.to_deck_inches(np.array([[rest["x_release_frame"], rest["y_release_frame"]]]))[0]
        on = 0 <= u <= 24 and 0 <= v <= 48
        return {**base, "score": 1 if on else 0,
                "basis": f"Bag came to rest {'on' if on else 'off'} the deck (u {u:.0f} in, v {v:.0f} in)."}
    path = after_contact.get("path") or []
    if path:
        last = path[-1]
        u, v = model.to_deck_inches(np.array([[last["x_release_frame"], last["y_release_frame"]]]))[0]
        if math.hypot(u - 12.0, v - 39.0) <= HOLE_VANISH_RADIUS_IN:
            return {**base, "score": 3, "basis": "Bag disappeared at the hole."}
    return {**base, "score": None, "basis": "Final rest not found; confirm in the video."}
```

- [ ] **Step 4: Run tests** — Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add python/cornhole_biomech/contact.py tests/test_contact.py
git commit -m "Classify first contact against deck/floor; predict contact for bags lost mid-air

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: `scene-vision` Swift helper and Python loader

**Files:**
- Create: `app/CornholeBiomechanics/Sources/SceneVision/main.swift`
- Modify: `app/CornholeBiomechanics/Package.swift`
- Create: `python/cornhole_biomech/scene.py`
- Test: `tests/test_scene.py`

**Interfaces:**
- `scene-vision --input <video> --output <dir> [--step 2] [--scale 0.5]` writes `<dir>/mask_%06d.png` (8-bit, 255 = person, size = video × scale after applying the track's preferred transform) and `<dir>/index.json` `{"fps", "width", "height", "mask_width", "mask_height", "step", "frames": [int]}`; exit 0 on success, 1 with a message on stderr.
- Python produces:
  - `find_binary() -> Path | None` (env `CORNHOLE_SCENE_VISION`, then `app/CornholeBiomechanics/.build/{release,debug}/SceneVision`).
  - `person_masks(video_path: str, cache_dir: Path, frame_size: tuple[int, int], binary: Path | None = ...) -> dict` keys `status` ("measured" | "unavailable"), `reason`, `masks` (`dict[int, np.ndarray uint8]` full-resolution), `step`.
  - `tag_people(candidates: list[Candidate], masks: dict[int, np.ndarray]) -> list[Candidate]` (sets `in_person=True`).

- [ ] **Step 1: Add the Swift target**

In `Package.swift` add to `products`:

```swift
        .executable(name: "SceneVision", targets: ["SceneVision"]),
```

and to `targets`:

```swift
        .executableTarget(
            name: "SceneVision",
            path: "Sources/SceneVision"
        ),
```

- [ ] **Step 2: Write `main.swift`**

```swift
// app/CornholeBiomechanics/Sources/SceneVision/main.swift
// Person masks for the analysis engine (Apple Vision, on-device, no downloads).
import AVFoundation
import CoreImage
import Foundation
import ImageIO
import UniformTypeIdentifiers
import Vision

struct Options {
    var input: URL
    var output: URL
    var step = 2
    var scale = 0.5
}

enum SceneError: Error, CustomStringConvertible {
    case usage, noVideoTrack, readerFailed(String), writeFailed(String)
    var description: String {
        switch self {
        case .usage: return "usage: scene-vision --input <video> --output <dir> [--step N] [--scale S]"
        case .noVideoTrack: return "the file has no video track"
        case .readerFailed(let m): return "could not read video: \(m)"
        case .writeFailed(let m): return "could not write mask: \(m)"
        }
    }
}

func parse(_ args: [String]) throws -> Options {
    var input: URL?, output: URL?, step = 2, scale = 0.5
    var i = 1
    while i < args.count {
        let key = args[i]
        guard i + 1 < args.count else { throw SceneError.usage }
        let value = args[i + 1]
        switch key {
        case "--input": input = URL(fileURLWithPath: value)
        case "--output": output = URL(fileURLWithPath: value)
        case "--step": step = max(1, Int(value) ?? 2)
        case "--scale": scale = min(1, max(0.1, Double(value) ?? 0.5))
        default: throw SceneError.usage
        }
        i += 2
    }
    guard let input, let output else { throw SceneError.usage }
    return Options(input: input, output: output, step: step, scale: scale)
}

func writePNG(_ image: CGImage, to url: URL) throws {
    guard let dest = CGImageDestinationCreateWithURL(url as CFURL, UTType.png.identifier as CFString, 1, nil) else {
        throw SceneError.writeFailed(url.path)
    }
    CGImageDestinationAddImage(dest, image, nil)
    if !CGImageDestinationFinalize(dest) { throw SceneError.writeFailed(url.path) }
}

func run(_ o: Options) async throws {
    let asset = AVURLAsset(url: o.input)
    guard let track = try await asset.loadTracks(withMediaType: .video).first else { throw SceneError.noVideoTrack }
    let (natural, transform, fps) = try await track.load(.naturalSize, .preferredTransform, .nominalFrameRate)
    let oriented = CGRect(origin: .zero, size: natural).applying(transform)
    let width = Int(abs(oriented.width).rounded()), height = Int(abs(oriented.height).rounded())
    let maskW = Int((Double(width) * o.scale).rounded()), maskH = Int((Double(height) * o.scale).rounded())
    let reader = try AVAssetReader(asset: asset)
    let output = AVAssetReaderTrackOutput(track: track, outputSettings: [
        kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA])
    reader.add(output)
    guard reader.startReading() else { throw SceneError.readerFailed(reader.error?.localizedDescription ?? "unknown") }
    try FileManager.default.createDirectory(at: o.output, withIntermediateDirectories: true)
    let request = VNGeneratePersonSegmentationRequest()
    request.qualityLevel = .accurate
    request.outputPixelFormat = kCVPixelFormatType_OneComponent8
    let context = CIContext()
    var index = 0
    var written: [Int] = []
    while let sample = output.copyNextSampleBuffer() {
        defer { index += 1 }
        guard index % o.step == 0, let pixels = CMSampleBufferGetImageBuffer(sample) else { continue }
        try VNImageRequestHandler(cvPixelBuffer: pixels, orientation: .up).perform([request])
        guard let mask = request.results?.first?.pixelBuffer else { continue }
        var image = CIImage(cvPixelBuffer: mask)
        let maskNatural = image.extent.size
        // Mask → video natural size → preferred orientation → output scale.
        image = image.transformed(by: CGAffineTransform(scaleX: natural.width / maskNatural.width,
                                                        y: natural.height / maskNatural.height))
        image = image.transformed(by: transform)
        image = image.transformed(by: CGAffineTransform(translationX: -image.extent.minX, y: -image.extent.minY))
        image = image.transformed(by: CGAffineTransform(scaleX: CGFloat(maskW) / image.extent.width,
                                                        y: CGFloat(maskH) / image.extent.height))
        guard let cg = context.createCGImage(image, from: CGRect(x: 0, y: 0, width: maskW, height: maskH),
                                             format: .L8, colorSpace: CGColorSpaceCreateDeviceGray()) else { continue }
        try writePNG(cg, to: o.output.appendingPathComponent(String(format: "mask_%06d.png", index)))
        written.append(index)
    }
    if reader.status == .failed { throw SceneError.readerFailed(reader.error?.localizedDescription ?? "unknown") }
    let payload: [String: Any] = ["fps": Double(fps), "width": width, "height": height, "mask_width": maskW,
                                  "mask_height": maskH, "step": o.step, "frames": written]
    let data = try JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys])
    try data.write(to: o.output.appendingPathComponent("index.json"))
}

do {
    try await run(try parse(CommandLine.arguments))
} catch {
    FileHandle.standardError.write(Data("scene-vision: \(error)\n".utf8))
    exit(1)
}
```

- [ ] **Step 3: Build and try it on a pilot clip**

Run: `DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer CLANG_MODULE_CACHE_PATH=$TMPDIR/cmc SWIFTPM_MODULECACHE_OVERRIDE=$TMPDIR/cmc swift build --disable-sandbox --package-path app/CornholeBiomechanics --product SceneVision`
Expected: `Build complete!`

Run: `app/CornholeBiomechanics/.build/debug/SceneVision --input "data/videos/Player 1/testsep17 - 1.mov" --output /private/tmp/sv1 && ls /private/tmp/sv1 | head -3 && cat /private/tmp/sv1/index.json | head -8`
Expected: `mask_000000.png …`, `"mask_width" : 960`, `"mask_height" : 540`. Open one mask: the athlete is white, the background black. If the mask is upside down relative to the video (CIImage origin is bottom-left), add `image = image.transformed(by: CGAffineTransform(scaleX: 1, y: -1).translatedBy(x: 0, y: -image.extent.height))` before `createCGImage` and re-check.

- [ ] **Step 4: Write the failing Python tests**

```python
# tests/test_scene.py
import json
from pathlib import Path

import cv2
import numpy as np

from cornhole_biomech.auto_bag import Candidate
from cornhole_biomech.scene import person_masks, tag_people


def test_missing_binary_is_unavailable(tmp_path):
    out = person_masks("x.mov", tmp_path, (1920, 1080), binary=None)
    assert out["status"] == "unavailable" and "scene-vision" in out["reason"]
    assert out["masks"] == {}


def _fake_cache(tmp_path: Path, w, h):
    cache = tmp_path / "scene_vision"
    cache.mkdir()
    m = np.zeros((h, w), np.uint8); m[10:20, 10:20] = 255
    cv2.imwrite(str(cache / "mask_000000.png"), m)
    (cache / "index.json").write_text(json.dumps({"fps": 60, "width": 2 * w, "height": 2 * h, "mask_width": w,
                                                   "mask_height": h, "step": 2, "frames": [0]}))
    return cache


def test_cached_masks_are_loaded_at_full_resolution(tmp_path):
    _fake_cache(tmp_path, 40, 30)
    out = person_masks("x.mov", tmp_path, (80, 60), binary=None)
    assert out["status"] == "measured"
    assert out["masks"][0].shape == (60, 80) and out["masks"][0][30, 30] == 255


def test_mask_size_mismatch_is_rejected(tmp_path):
    _fake_cache(tmp_path, 40, 30)
    out = person_masks("x.mov", tmp_path, (1080, 1920), binary=None)   # rotated video
    assert out["status"] == "unavailable" and "size" in out["reason"]


def test_tag_people_marks_candidates_inside_masks():
    m = np.zeros((60, 80), np.uint8); m[20:40, 20:40] = 255
    tagged = tag_people([Candidate(0, 30.0, 30.0, 5.0), Candidate(0, 70.0, 5.0, 5.0), Candidate(1, 30.0, 30.0, 5.0)],
                        {0: m})
    assert [c.in_person for c in tagged] == [True, False, True]   # frame 1 uses nearest mask (frame 0)
```

- [ ] **Step 5: Add `in_person` to `Candidate`** in `python/cornhole_biomech/auto_bag.py:44-50`:

```python
@dataclass(frozen=True)
class Candidate:
    frame: int
    x: float        # full-resolution pixels, x right
    y: float        # full-resolution pixels, y down
    area: float
    in_person: bool = False   # inside an Apple Vision person mask (athlete or bystander)
```

- [ ] **Step 6: Implement `scene.py`**

```python
# python/cornhole_biomech/scene.py
"""Person masks from the `scene-vision` helper (Apple Vision), cached per trial.

Masks only ever REMOVE evidence (people cannot seed a bag flight, and are left out
of the background plate). If the helper is missing or its output does not match
the video, tracking runs exactly as before and the reason is recorded.
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .auto_bag import Candidate

SCENE_REVISION = "scene_vision_v1"
_REPO = Path(__file__).resolve().parents[2]
_DEFAULT = object()


def find_binary() -> Path | None:
    env = os.environ.get("CORNHOLE_SCENE_VISION")
    candidates = [Path(env)] if env else []
    candidates += [_REPO / "app/CornholeBiomechanics/.build/release/SceneVision",
                   _REPO / "app/CornholeBiomechanics/.build/debug/SceneVision"]
    return next((p for p in candidates if p.is_file() and os.access(p, os.X_OK)), None)


def person_masks(video_path: str, cache_dir: Path, frame_size: tuple[int, int], binary: Any = _DEFAULT) -> dict[str, Any]:
    cache = Path(cache_dir) / "scene_vision"
    index_path = cache / "index.json"
    if not index_path.exists():
        exe = find_binary() if binary is _DEFAULT else binary
        if exe is None:
            return {"status": "unavailable", "reason": "scene-vision helper not found; person masks skipped.",
                    "masks": {}, "step": None}
        done = subprocess.run([str(exe), "--input", str(video_path), "--output", str(cache)],
                              capture_output=True, text=True, timeout=900)
        if done.returncode != 0 or not index_path.exists():
            return {"status": "unavailable", "reason": f"scene-vision failed: {done.stderr.strip()[:300]}",
                    "masks": {}, "step": None}
    index = json.loads(index_path.read_text())
    width, height = frame_size
    if abs(index["mask_width"] / index["mask_height"] - width / height) > 0.01:
        return {"status": "unavailable", "masks": {}, "step": index.get("step"),
                "reason": f"Mask size {index['mask_width']}×{index['mask_height']} does not match the video "
                          f"{width}×{height} (orientation?); person masks skipped."}
    masks = {}
    for f in index["frames"]:
        m = cv2.imread(str(cache / f"mask_{f:06d}.png"), cv2.IMREAD_GRAYSCALE)
        if m is not None:
            masks[int(f)] = (cv2.resize(m, (width, height), interpolation=cv2.INTER_NEAREST) >= 128).astype(np.uint8) * 255
    return {"status": "measured", "reason": None, "masks": masks, "step": index["step"], "revision": SCENE_REVISION}


def tag_people(candidates: list[Candidate], masks: dict[int, np.ndarray]) -> list[Candidate]:
    if not masks:
        return list(candidates)
    keys = sorted(masks)
    out = []
    for c in candidates:
        nearest = min(keys, key=lambda k: abs(k - c.frame))
        m = masks[nearest]
        x, y = int(round(c.x)), int(round(c.y))
        inside = abs(nearest - c.frame) <= 2 and 0 <= y < m.shape[0] and 0 <= x < m.shape[1] and m[y, x] > 0
        out.append(replace(c, in_person=bool(inside)))
    return out
```

- [ ] **Step 7: Run tests**

Run: `MPLCONFIGDIR=$TMPDIR/mpl PYTHONPATH=python .venv/bin/python -m pytest tests/test_scene.py tests/test_auto_bag.py -q`
Expected: PASS.

- [ ] **Step 8: Ship the helper with the app**

In `scripts/build_app.sh` after the main `cp .../CornholeBiomechanics ...` line add:

```zsh
cp "$SWIFT_PACKAGE/.build/release/SceneVision" "$APP_DIR/Contents/MacOS/scene-vision"
```

In `AnalysisService.swift` next to the `CORNHOLE_MEDIAPIPE_MODEL` line (≈293) add:

```swift
        if let helper = Bundle.main.executableURL?.deletingLastPathComponent().appendingPathComponent("scene-vision"),
           manager.fileExists(atPath: helper.path) { environment["CORNHOLE_SCENE_VISION"] = helper.path }
```

Run the Swift build command from Global Constraints. Expected: `Build complete!`

- [ ] **Step 9: Commit**

```bash
git add app/CornholeBiomechanics/Package.swift app/CornholeBiomechanics/Sources/SceneVision python/cornhole_biomech/scene.py python/cornhole_biomech/auto_bag.py tests/test_scene.py scripts/build_app.sh app/CornholeBiomechanics/Sources/CornholeBiomechanics/AnalysisService.swift
git commit -m "Add scene-vision helper (Apple Vision person masks) and Python loader

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Integrate people, board and contact into automatic flight tracking

**Files:**
- Modify: `python/cornhole_biomech/auto_bag.py` (`find_flight` seeding, `auto_track_bag`, `AUTO_BAG_REVISION`)
- Test: `tests/test_auto_bag.py` (append)

**Interfaces:**
- Consumes: `scene.person_masks`, `scene.tag_people`, `background.build_plate`, `board.detect_board`, `board.solve_board`, `contact.classify_flight_end`, `contact.predict_contact`, `contact.landing_summary`, `contact.suggest_outcome`.
- Produces (new/changed keys in the `auto_track_bag` result):
  - `revision = "auto_motion_parabola_v11_scene"`
  - `first_contact_frame`: int only when `contact.kind` ∈ {deck, front, floor} (observed); else `None`.
  - `contact`: `{"kind", "state": "measured"|"estimated"|"unavailable", "reason", "plane_xy_m"}`
  - `predicted_contact`: dict from `predict_contact` or `None`
  - `board`: `{"status", "confidence", "reasons", **BoardModel.as_dict()}` (reference = release-frame pixels)
  - `landing`: `landing_summary(...)` + `"state"` or `None`
  - `suggested_outcome`: dict from `suggest_outcome`
  - `scene`: `{"masks_status", "masks_reason", "plate_samples"}`
- New signature: `auto_track_bag(video_path, wrist, arm_length_px, target_direction, preferred_release=None, cache_dir: Path | None = None, board_corners_px: list | None = None)`. `board_corners_px`, when given, are clicked corners in release-frame pixels and bypass detection.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_auto_bag.py
from cornhole_biomech.auto_bag import find_flight as _find_flight


def test_person_candidates_cannot_seed_a_flight():
    flight = true_flight()
    cands = [Candidate(c.frame, c.x, c.y, c.area, in_person=True)
             for c in candidates_with_clutter(flight, clutter_per_frame=0, drop=0.0)]
    result = _find_flight(cands, FPS, "left_to_right", arm_length_px=PPM * 0.62)
    assert result["status"] == "not_found"


def test_auto_track_does_not_report_mid_air_contact(monkeypatch):
    import cornhole_biomech.auto_bag as ab
    # A flight that ends high in the air: the classifier says lost_in_flight.
    monkeypatch.setattr(ab, "classify_flight_end", lambda p, m: {"kind": "lost_in_flight", "plane_xy_m": [0.0, 1.0]})
    monkeypatch.setattr(ab, "predict_contact", lambda *a, **k: None)
    out = ab._contact_from_board({"status": "found", "model": _StubModel()}, (500.0, 300.0), fit={
        "coef_x": [0, 1, 0], "coef_y": [0, 0, 1], "reference_frame": 0}, fps=FPS, last_frame=80,
        frame_count=200, chain={f: np.eye(3) for f in range(200)})
    assert out["first_contact_frame"] is None
    assert out["contact"]["kind"] == "lost_in_flight" and out["contact"]["state"] == "unavailable"


class _StubModel:
    def as_dict(self):
        return {"phi_deg": 5.0}
```

- [ ] **Step 2: Run to verify failure**

Run: `MPLCONFIGDIR=$TMPDIR/mpl PYTHONPATH=python .venv/bin/python -m pytest tests/test_auto_bag.py -q`
Expected: the two new tests FAIL (`in_person` candidates still seed; `_contact_from_board` missing).

- [ ] **Step 3: Seed only from non-person candidates** in `find_flight` (≈ line 340): right after `by_frame` is built, add

```python
    seedable = [c for c in candidates if not c.in_person]
    seed_by_frame: dict[int, list[Candidate]] = {}
    for c in seedable:
        seed_by_frame.setdefault(c.frame, []).append(c)
    seed_frames = sorted(seed_by_frame)
```

then change `build_tracklets(candidates, ...)` → `build_tracklets(seedable, ...)`, and in the RANSAC loop replace `frames` by `seed_frames` in the three sampling lines (`f1 = seed_frames[...]`, `later = [f for f in seed_frames ...]`, `latest = [f for f in seed_frames ...]`) and `by_frame[f]` by `seed_by_frame[f]` in `picks`. Add `if len(seed_frames) < 3: return result` after the existing `len(frames) < 3` check. Inlier collection, extension and trimming keep using all candidates (a bag right at the hand may sit inside the person mask; the release frame must not move).

- [ ] **Step 4: Add scene/board/contact helpers and wire them in `auto_track_bag`**

Add imports at the top of `auto_bag.py`:

```python
from pathlib import Path

from .background import build_plate
from .board import detect_board, solve_board
from .contact import classify_flight_end, landing_summary, predict_contact, suggest_outcome
```

(`scene` imports `Candidate` from this module, so import `scene` lazily inside the function below.)

Add these functions above `auto_track_bag`:

```python
def _scene_and_board(frames, chain, target_direction, masks, board_corners_px=None, cache_dir=None):
    """Background plate + board in release-frame pixels (reference of `chain`)."""
    plate = build_plate(frames, chain, person_masks=masks or None)
    if cache_dir is not None:   # kept for `set-board-corners --apply-to` (plate-to-plate corner transfer)
        cv2.imwrite(str(Path(cache_dir) / "plate.jpg"), plate["plate"])
    height, width = frames[0].shape[:2]
    scene_info = {"plate_samples": plate["samples"]}
    if board_corners_px is not None:
        found = {"status": "found", "corners_px": board_corners_px, "confidence": 1.0, "reasons": ["clicked corners"]}
    else:
        found = detect_board(plate["plate"], target_direction)
    if found["status"] != "found":
        return scene_info, {**found, "model": None}
    model = solve_board(np.asarray(found["corners_px"], float), (width, height))
    return scene_info, {**found, "model": model}


def _contact_from_board(board, end_point_ref, fit, fps, last_frame, frame_count, chain):
    """Observed contact only when the flight ends at the deck/front/floor; otherwise predicted."""
    if board.get("model") is None:
        return {"first_contact_frame": None, "predicted_contact": None,
                "contact": {"kind": "unknown", "state": "unavailable", "plane_xy_m": None,
                            "reason": "Board not located, so contact cannot be checked against the deck or floor."}}
    model = board["model"]
    end = classify_flight_end(end_point_ref, model)
    if end["kind"] != "lost_in_flight":
        return {"first_contact_frame": last_frame, "predicted_contact": None,
                "contact": {"kind": end["kind"], "state": "measured", "plane_xy_m": end["plane_xy_m"], "reason": None}}
    to_ref = lambda f, p: (chain[f] @ np.array([p[0], p[1], 1.0]))[:2] if f in chain else p
    predicted = predict_contact(fit["coef_x"], fit["coef_y"], fit["reference_frame"], fps, last_frame, frame_count,
                                to_ref, model)
    return {"first_contact_frame": None, "predicted_contact": predicted,
            "contact": {"kind": "lost_in_flight", "state": "unavailable", "plane_xy_m": end["plane_xy_m"],
                        "reason": "The bag was lost while still in the air; first contact was not observed."}}
```

Change `AUTO_BAG_REVISION = "auto_motion_parabola_v11_scene"` and the signature to add `cache_dir: Path | None = None, board_corners_px: list | None = None`.

In `auto_track_bag` body:

1. After `frames, fps = read_frames(video_path)` and `candidates, to_prev = detect_moving_blobs_in_frames(frames)` insert:

```python
    from .scene import person_masks, tag_people
    height, width = frames[0].shape[:2]
    masks_info = (person_masks(video_path, cache_dir, (width, height)) if cache_dir is not None
                  else {"status": "unavailable", "reason": "No cache directory for person masks.", "masks": {}})
    candidates = tag_people(candidates, masks_info["masks"])
```

2. Replace the block from `height, width = frames[0].shape[:2]` (existing, after `release, contact = ...`) through `contact_known = descending and not at_edge` with:

```python
    last = next(p for p in chosen["points"] if p["frame"] == contact)
    chain = reference_chain(to_prev, release)
    scene_info, board = _scene_and_board(frames, chain, target_direction, masks_info["masks"], board_corners_px,
                                         cache_dir)
    end_ref = (chain[contact] @ np.array([last["x"], last["y"], 1.0]))[:2]
    decided = _contact_from_board(board, end_ref, fit, fps, contact, len(frames), chain)
    if board.get("model") is None:
        # No board: keep the previous geometric rule, but say it is unverified.
        t_last = (contact - fit["reference_frame"]) / fps
        descending = fit["coef_y"][1] + 2 * fit["coef_y"][2] * t_last > 0
        at_edge = min(last["x"], width - last["x"], last["y"], height - last["y"]) < 0.02 * width
        contact_known = descending and not at_edge
        decided["contact"]["reason"] += " Using the older end-of-track rule, unverified."
    else:
        contact_known = decided["first_contact_frame"] is not None
```

and delete the now-duplicate `chain = reference_chain(to_prev, release)` line that follows.

3. Before `return {`, build landing and outcome:

```python
    landing = suggested = None
    if board.get("model") is not None:
        model = board["model"]
        if contact_known and contact in refined:
            p = chain[contact] @ np.array([refined[contact]["x"], refined[contact]["y"], 1.0])
            landing = {**landing_summary(p[:2], model), "state": "measured"}
        elif decided["predicted_contact"] is not None:
            pc = decided["predicted_contact"]
            landing = {**landing_summary((pc["x_px"], pc["y_px"]), model), "state": "estimated",
                       "reason": pc["reason"]}
        suggested = suggest_outcome(after_contact, model)
    board_payload = {k: v for k, v in board.items() if k != "model"}
    if board.get("model") is not None:
        board_payload.update(board["model"].as_dict())
```

4. In the returned dict: keep `"first_contact_frame": contact if contact_known else None`, and add

```python
        "contact": decided["contact"], "predicted_contact": decided["predicted_contact"],
        "board": board_payload, "landing": landing, "suggested_outcome": suggested,
        "scene": {"masks_status": masks_info["status"], "masks_reason": masks_info.get("reason"),
                  "plate_samples": scene_info["plate_samples"]},
```

and when `not contact_known`, replace the old reason text with `decided["contact"]["reason"]` (append `" Mark contact in Flight & scale if it is visible."`).

- [ ] **Step 5: Pass the cache dir from the pipeline** — `pipeline.py:_automatic_flight` (line ~76):

```python
    corners = _load_json(output / "board_corners.json", None)
    result = auto_track_bag(video.path, wrist, arm if np.isfinite(arm) else None, context.target_direction,
                            cache_dir=output, board_corners_px=None if corners is None else corners["corners_px"])
```

and extend the cache check so clicked corners invalidate it: `cached.get("board_corners") == corners` (store `result["board_corners"] = corners` before writing).

- [ ] **Step 6: Run the whole Python suite**

Run: `MPLCONFIGDIR=$TMPDIR/mpl PYTHONPATH=python .venv/bin/python -m pytest tests -q`
Expected: PASS. Existing tests that assert the old revision string must be updated to `AUTO_BAG_REVISION` imports, not literals.

- [ ] **Step 7: Commit**

```bash
git add python/cornhole_biomech/auto_bag.py python/cornhole_biomech/pipeline.py tests/test_auto_bag.py
git commit -m "Decide first contact against the detected board; people cannot seed a bag flight

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Board-based scale, landing and suggested outcome in the pipeline

**Files:**
- Modify: `python/cornhole_biomech/bag.py:32` (`PHYSICAL_SCALE_PLANES`)
- Modify: `python/cornhole_biomech/pipeline.py` (calibration block ≈514–566; results assembly ≈900–920)
- Modify: `python/cornhole_biomech/cli.py` (new `set-board-corners` command)
- Test: `tests/test_board_pipeline.py`

**Interfaces:**
- Produces:
  - `PHYSICAL_SCALE_PLANES` gains `"board_throw_plane"`.
  - `pipeline._board_scale(auto_flight, release_frame, shoulder_px) -> dict` keys `status`, `pixels_per_meter`, `hfov_range_ppm` [lo, hi], `phi_deg`, `reason`.
  - `pipeline._scale_agreement(board_ppm, gravity_ppm, stature_ppm) -> dict` keys `max_disagreement`, `flag` (bool, > 0.10).
  - results.json gains `"board"`, `"landing"`, `"suggested_outcome"`, `"contact"`, `"scale_check"`; summaries gain `landing_along_error_m` (measured landings only), `release_to_board_front_m`, `board_phi_deg`.
  - CLI: `python -m cornhole_biomech set-board-corners --trial-dir DIR --corners x1,y1,x2,y2,x3,y3,x4,y4 [--apply-to DIR ...]` writes `board_corners.json` (release-frame pixels of that trial) and, for each `--apply-to`, transfers them via `board.transfer_corners` between the trials' plates (`plate.jpg`, written by Task 7's `_scene_and_board`).

Scale rule: board plane scale is used when `board.status == "found"` and `phi_status == "measured"`; source string `"regulation_board_pnp"`. The HFOV range (55–75°) is re-solved to give `hfov_range_ppm`. Gravity scale remains the fallback and the cross-check. Stature scale = athlete standing height px / 1.70 m is **only** a coarse check (height unknown), weighted as such in the message.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_board_pipeline.py
import pytest

from cornhole_biomech.bag import PHYSICAL_SCALE_PLANES
from cornhole_biomech.pipeline import _scale_agreement


def test_board_plane_counts_as_physical_scale():
    assert "board_throw_plane" in PHYSICAL_SCALE_PLANES


def test_scale_agreement_flags_over_ten_percent():
    ok = _scale_agreement(200.0, 205.0, None)
    assert ok["flag"] is False and ok["max_disagreement"] == pytest.approx(0.025, abs=1e-3)
    bad = _scale_agreement(200.0, 240.0, 198.0)
    assert bad["flag"] is True


def test_scale_agreement_with_single_source():
    out = _scale_agreement(200.0, None, None)
    assert out["flag"] is False and out["max_disagreement"] is None
```

- [ ] **Step 2: Run to verify failure** — `pytest tests/test_board_pipeline.py -q` → FAIL (ImportError).

- [ ] **Step 3: Implement**

`bag.py`:

```python
PHYSICAL_SCALE_PLANES = frozenset({"athlete_release_motion_plane", "bag_flight_plane_gravity", "board_throw_plane"})
```

`pipeline.py` (module level, near `_automatic_flight`):

```python
def _scale_agreement(board_ppm: float | None, gravity_ppm: float | None, stature_ppm: float | None) -> dict[str, Any]:
    values = [v for v in (board_ppm, gravity_ppm, stature_ppm) if v]
    if len(values) < 2:
        return {"max_disagreement": None, "flag": False, "sources": len(values)}
    worst = max(abs(a - b) / min(a, b) for i, a in enumerate(values) for b in values[i + 1:])
    return {"max_disagreement": float(worst), "flag": bool(worst > 0.10), "sources": len(values),
            "board_ppm": board_ppm, "gravity_ppm": gravity_ppm, "stature_ppm": stature_ppm}


def _board_scale(auto_flight: dict[str, Any] | None, point_px) -> dict[str, Any]:
    from .board import HFOV_RANGE_DEG, solve_board
    board = (auto_flight or {}).get("board") or {}
    if board.get("status") != "found" or not board.get("corners_px"):
        return {"status": "unavailable", "pixels_per_meter": None,
                "reason": "Board not located; " + "; ".join(board.get("reasons") or ["no board result"])}
    import numpy as np
    corners = np.asarray(board["corners_px"], float)
    size = (int(auto_flight.get("width") or 1920), int(auto_flight.get("height") or 1080))
    ppm = [solve_board(corners, size, hfov_deg=h).pixels_per_meter_at(point_px) for h in (*HFOV_RANGE_DEG, 65.0)]
    status = "measured" if board.get("phi_status") == "measured" else "estimated"
    return {"status": status, "pixels_per_meter": ppm[2], "hfov_range_ppm": sorted(ppm[:2]),
            "phi_deg": board.get("phi_deg"), "reason": board.get("phi_reason")}
```

Also add `"width": width, "height": height` to the `auto_track_bag` result dict (Task 7 file) so `_board_scale` knows the image size.

In `analyze_trial`, right after `calibration = SpatialCalibration.load(calibration_path)` (≈514):

```python
    board_scale = _board_scale(auto_flight if auto_accepted else None,
                               filtered[release_frame, landmarks.index(f"{context.throwing_side}_shoulder")]
                               if release_frame is not None else (960.0, 540.0))
    if calibration is None and board_scale["status"] == "measured":
        calibration = SpatialCalibration(board_scale["pixels_per_meter"], "board_throw_plane", True,
                                         "regulation_board_pnp")
```

After `gravity_scale` is computed (≈560) add:

```python
    scale_check = _scale_agreement(board_scale.get("pixels_per_meter"), gravity_scale.get("pixels_per_meter"), None)
    if scale_check["flag"]:
        bag_warnings.append(f"Board and flight-gravity scales disagree by {100 * scale_check['max_disagreement']:.0f}% "
                            "(> 10%); metre values are flagged.")
```

In the results assembly (before `write_json(output / "results.json", results)`):

```python
    if auto_flight:
        results["board"] = auto_flight.get("board")
        results["contact"] = auto_flight.get("contact")
        results["predicted_contact"] = auto_flight.get("predicted_contact")
        results["landing"] = auto_flight.get("landing")
        results["suggested_outcome"] = auto_flight.get("suggested_outcome")
        results["scene"] = auto_flight.get("scene")
    results["scale_check"] = scale_check
    landing = (auto_flight or {}).get("landing") or {}
    summaries["landing_along_error_m"] = landing.get("along_error_m") if landing.get("state") == "measured" else None
    summaries["board_phi_deg"] = board_scale.get("phi_deg")
```

(`release_to_board_front_m` is computed in Task 9 from the plane.)

`cli.py` — add the parser next to the other commands:

```python
    corners = commands.add_parser("set-board-corners", help="Store four clicked deck corners for a trial (and others)")
    corners.add_argument("--trial-dir", required=True)
    corners.add_argument("--corners", required=True, help="x1,y1,...,x4,y4 in the release frame's pixels")
    corners.add_argument("--apply-to", nargs="*", default=[])
    corners.set_defaults(handler=handle_set_board_corners)
```

```python
def handle_set_board_corners(args: argparse.Namespace) -> dict[str, Any]:
    import cv2
    from .board import transfer_corners
    values = [float(v) for v in args.corners.split(",")]
    if len(values) != 8:
        raise ValueError("Give exactly four corners: x1,y1,x2,y2,x3,y3,x4,y4.")
    source = Path(args.trial_dir)
    write_json(source / "board_corners.json", {"corners_px": [values[i:i + 2] for i in range(0, 8, 2)],
                                               "source": "clicked"})
    applied, failed = [], []
    src_plate = cv2.imread(str(source / "plate.jpg"))
    for other in args.apply_to:
        dst_plate = cv2.imread(str(Path(other) / "plate.jpg"))
        moved = None if src_plate is None or dst_plate is None else transfer_corners(src_plate, dst_plate, values)
        if moved is None:
            failed.append(other)
            continue
        write_json(Path(other) / "board_corners.json", {"corners_px": moved.tolist(), "source": f"transferred:{source.name}"})
        applied.append(other)
    return {"written": str(source / "board_corners.json"), "applied": applied, "failed": failed}
```

(ensure `from pathlib import Path` and `write_json` are imported in `cli.py`; they are used elsewhere in the file — check with `grep -n "^from\|^import" python/cornhole_biomech/cli.py`.)

- [ ] **Step 4: Run tests** — `pytest tests -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add python/cornhole_biomech/bag.py python/cornhole_biomech/pipeline.py python/cornhole_biomech/cli.py python/cornhole_biomech/auto_bag.py tests/test_board_pipeline.py
git commit -m "Use the board's throw plane as the metric scale; landing, outcome suggestion and corner clicks

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Per-throw body → release → flight → outcome chain

**Files:**
- Create: `python/cornhole_biomech/chain.py`
- Modify: `python/cornhole_biomech/pipeline.py` (after timing metrics ≈ line 795; results assembly)
- Test: `tests/test_chain.py`

**Interfaces:**
- Consumes: `mechanics.*`, `regulation.BAG_MASS_KG`, `regulation.BAG_MASS_RANGE_KG`, `filtering.derivative`, `filtering.lowpass_zero_phase(values, fps, cutoff_hz=6.0) -> (filtered, cutoff, warnings)`, `BoardModel`-like object with `to_plane(points_px)` (release-frame pixels → plane metres).
- Produces:
  - `HAND_OFFSET_ARM_LENGTHS = 0.34`, `LANDMARK_NOISE_PX = 4.0`, `MC_DRAWS = 500`.
  - `quantity(value, unit, state, formula, *, reason=None, interval=None, assumptions=()) -> dict`.
  - `body_chain(angles: dict[str, np.ndarray], fps: float, forward_swing: int | None, release: int) -> dict[str, dict]` (keys below).
  - `hand_chain(shoulder_m, elbow_m, wrist_m: np.ndarray (N,2), fps, forward_swing, release, mass_kg=BAG_MASS_KG) -> dict` with series `bag_point_m`, `velocity_m_s`, `acceleration_m_s2`, `force_n`, `power_w`, `energy_rate_w` and scalar quantities.
  - `release_chain(speed, angle_deg, height_m, to_front_m, se: dict, mass_range=BAG_MASS_RANGE_KG, rel_scale_sd=0.05, draws=MC_DRAWS, seed=0) -> dict` (momentum, KE, PE, E, energy match, speed margin, predicted along error — each with a 95 % Monte Carlo interval).
  - `build_chain(...) -> dict` `{"quantities": {name: quantity}, "series": {...}, "notes": [BAG_ONLY_NOTE, ...]}` and `flatten_for_summaries(chain) -> dict[str, float | None]` (`chain_<name>` keys, value only when `state != "unavailable"`).

Quantity names (all in `quantities`):
`shoulder_angle_at_release_deg`, `elbow_angle_at_release_deg`, `shoulder_peak_angular_velocity_deg_s`, `shoulder_peak_time_rel_release_ms`, `elbow_peak_extension_velocity_deg_s`, `elbow_peak_time_rel_release_ms`, `wrist_peak_speed_time_rel_release_ms`, `peak_sequence` (value = e.g. "shoulder → elbow → wrist"), `hand_speed_at_release_m_s`, `hand_acceleration_at_release_m_s2`, `peak_net_force_on_bag_n`, `mean_net_force_on_bag_n`, `force_direction_at_peak_deg`, `peak_power_on_bag_w`, `release_speed_m_s`, `release_angle_deg`, `release_height_m`, `momentum_kg_m_s`, `kinetic_energy_j`, `potential_energy_j`, `mechanical_energy_j`, `energy_match_percent`, `speed_margin_over_minimum_percent`, `timing_sensitivity_in_per_10ms`, `predicted_along_error_in`, `measured_along_error_in`.

Definitions: shoulder angle = `arm_to_trunk_deg` (existing kinematics field); elbow = `elbow_angle_deg`; angular velocity = `derivative` of the filtered angle; peaks searched in `[forward_swing, release + 0.1 s]` (same window as `timing.py`); energy match % = `100 (v² / v_req² − 1)`; speed margin % = `100 (v / v_min − 1)`; power reported only when `max |F·v − dE/dt|` over the forward swing < 10 % of peak |F·v| (else `estimated` with reason "power estimates disagree"); acceleration/force quantities are `estimated` unless their 95 % interval half-width < 25 % of the value.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_chain.py
import math

import numpy as np
import pytest

from cornhole_biomech.bag import GRAVITY_M_S2 as G
from cornhole_biomech.chain import body_chain, flatten_for_summaries, hand_chain, quantity, release_chain
from cornhole_biomech.regulation import BAG_MASS_KG

FPS = 60.0


def test_quantity_shape():
    q = quantity(1.0, "m", "measured", "x = 1")
    assert set(q) >= {"value", "unit", "state", "formula", "reason", "interval", "assumptions"}


def test_body_chain_peak_order_proximal_to_distal():
    n, release = 120, 90
    t = np.arange(n) / FPS
    shoulder = 40 * np.tanh((np.arange(n) - 60) / 8.0)          # fastest at frame 60
    elbow = 150 + 20 * np.tanh((np.arange(n) - 75) / 5.0)        # extends fastest at frame 75
    out = body_chain({"arm_to_trunk_deg": shoulder, "elbow_angle_deg": elbow}, FPS, 40, release)
    assert out["shoulder_peak_time_rel_release_ms"]["value"] == pytest.approx(1000 * (60 - 90) / FPS, abs=17)
    assert out["elbow_peak_time_rel_release_ms"]["value"] == pytest.approx(1000 * (75 - 90) / FPS, abs=17)
    assert out["peak_sequence"]["value"].startswith("shoulder → elbow")
    assert out["peak_sequence"]["state"] == "measured"


def test_hand_chain_force_vector_for_circular_swing():
    # Rigid arm swinging on a circle at constant ω: hand force = m(−ω²r r̂ − g⃗)
    n, release, r, w = 90, 60, 0.6, 6.0
    t = np.arange(n) / FPS
    th = -math.pi / 2 + w * (t - t[release]) * 0.3
    shoulder = np.tile([0.0, 1.4], (n, 1))
    wrist = shoulder + np.column_stack([r * np.cos(th), r * np.sin(th)]) * (1 / (1 + 0.34 * 1.0))
    elbow = shoulder + 0.5 * (wrist - shoulder)
    out = hand_chain(shoulder, elbow, wrist, FPS, 20, release)
    f = np.asarray(out["series"]["force_n"])[release]
    assert f[1] > BAG_MASS_KG * G      # at the bottom of the swing the hand pulls up more than the weight
    assert out["quantities"]["peak_net_force_on_bag_n"]["unit"] == "N"
    assert "Bag-only" in out["quantities"]["peak_net_force_on_bag_n"]["assumptions"][0]


def test_release_chain_intervals_contain_nominal():
    out = release_chain(8.5, 32.0, 0.95, 7.3, {"speed": 0.1, "angle": 1.0, "height": 0.02}, draws=300, seed=1)
    ke = out["kinetic_energy_j"]
    assert ke["value"] == pytest.approx(0.5 * BAG_MASS_KG * 8.5**2)
    lo, hi = ke["interval"]
    assert lo < ke["value"] < hi
    assert out["energy_match_percent"]["state"] in ("measured", "estimated")


def test_flatten_skips_unavailable():
    chain = {"quantities": {"a": quantity(1.0, "m", "measured", "a"),
                            "b": quantity(None, "m", "unavailable", "b", reason="no data")}}
    flat = flatten_for_summaries(chain)
    assert flat == {"chain_a": 1.0, "chain_b": None}
```

- [ ] **Step 2: Run to verify failure** — `pytest tests/test_chain.py -q` → FAIL (module not found).

- [ ] **Step 3: Implement**

```python
# python/cornhole_biomech/chain.py
"""Per-throw chain: body → release → flight → outcome, each quantity with state, formula and uncertainty.

2D throw plane (board.py): x toward the board, y up, metres. Angles from the 6 Hz
zero-lag filtered pose. Peak order is DESCRIBED, not graded (Putnam 1993 concerns
fast throws; cornhole is a slow accuracy swing).
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from .filtering import derivative
from .mechanics import (BAG_ONLY_NOTE, along_error_m, energy_rate, minimum_speed, net_force_on_bag, power_on_bag,
                        release_state, required_speed, timing_sensitivity)
from .regulation import BAG_MASS_KG, BAG_MASS_RANGE_KG, INCH_M, Board

HAND_OFFSET_ARM_LENGTHS = 0.34   # bag sits about one hand length beyond the wrist (auto_bag.py)
LANDMARK_NOISE_PX = 4.0
MC_DRAWS = 500
PEAK_WINDOW_AFTER_RELEASE_S = 0.1


def quantity(value, unit: str, state: str, formula: str, *, reason: str | None = None,
             interval: list[float] | None = None, assumptions: tuple[str, ...] | list[str] = ()) -> dict[str, Any]:
    return {"value": value, "unit": unit, "state": state, "formula": formula, "reason": reason,
            "interval": interval, "assumptions": list(assumptions)}


def _missing(unit: str, formula: str, reason: str) -> dict[str, Any]:
    return quantity(None, unit, "unavailable", formula, reason=reason)


def _peak(series: np.ndarray, start: int, stop: int, sign: float = 1.0) -> int | None:
    seg = sign * np.asarray(series, float)[max(0, start):min(len(series), stop + 1)]
    if seg.size == 0 or not np.isfinite(seg).any():
        return None
    return max(0, start) + int(np.nanargmax(seg))


def body_chain(angles: dict[str, np.ndarray], fps: float, forward_swing: int | None, release: int) -> dict[str, Any]:
    out: dict[str, Any] = {}
    start = forward_swing if forward_swing is not None and forward_swing < release else release - int(0.6 * fps)
    stop = release + int(PEAK_WINDOW_AFTER_RELEASE_S * fps)
    ms = lambda f: 1000.0 * (f - release) / fps
    shoulder = np.asarray(angles["arm_to_trunk_deg"], float)
    elbow = np.asarray(angles["elbow_angle_deg"], float)
    peaks = {}
    for name, series, label, sign in (("shoulder", shoulder, "shoulder_peak", 1.0), ("elbow", elbow, "elbow_peak", 1.0)):
        at = series[release] if 0 <= release < len(series) and math.isfinite(series[release]) else None
        key = "shoulder_angle_at_release_deg" if name == "shoulder" else "elbow_angle_at_release_deg"
        out[key] = (quantity(float(at), "°", "measured", f"{name} angle (2D projected) at the release frame")
                    if at is not None else _missing("°", f"{name} angle at release", "Landmark missing at release."))
        velocity = derivative(series, fps)
        p = _peak(np.abs(velocity) if name == "shoulder" else velocity, start, stop, sign)
        vkey = "shoulder_peak_angular_velocity_deg_s" if name == "shoulder" else "elbow_peak_extension_velocity_deg_s"
        tkey = f"{label}_time_rel_release_ms"
        if p is None:
            out[vkey] = _missing("°/s", f"max dθ/dt ({name})", "Angle not available in the swing window.")
            out[tkey] = _missing("ms", "t_peak − t_release", "No peak.")
            continue
        peaks[name] = p
        out[vkey] = quantity(float(velocity[p] if name == "elbow" else abs(velocity[p])), "°/s", "measured",
                             f"max dθ/dt of the filtered {name} angle between forward swing and release + 0.1 s")
        out[tkey] = quantity(ms(p), "ms", "measured", "t_peak − t_release", assumptions=["Resolution 1 frame."])
    order = sorted(peaks, key=peaks.get)
    out["peak_sequence"] = (quantity(" → ".join(order + ["release"]), "", "measured",
                                     "order of peak angular velocities (described, not graded)",
                                     assumptions=["Putnam (1993) describes fast throws; cornhole is an accuracy swing."])
                            if len(order) == 2 else _missing("", "peak order", "Both peaks are needed."))
    return out


def _hand_point(elbow: np.ndarray, wrist: np.ndarray, arm_length_m: float) -> np.ndarray:
    forearm = wrist - elbow
    unit = forearm / np.linalg.norm(forearm, axis=1, keepdims=True)
    return wrist + HAND_OFFSET_ARM_LENGTHS * arm_length_m * unit


def hand_chain(shoulder_m: np.ndarray, elbow_m: np.ndarray, wrist_m: np.ndarray, fps: float,
               forward_swing: int | None, release: int, mass_kg: float = BAG_MASS_KG) -> dict[str, Any]:
    arm = float(np.nanmedian(np.linalg.norm(elbow_m - shoulder_m, axis=1) + np.linalg.norm(wrist_m - elbow_m, axis=1)))
    point = _hand_point(elbow_m, wrist_m, arm)
    velocity = np.column_stack([derivative(point[:, 0], fps), derivative(point[:, 1], fps)])
    acceleration = np.column_stack([derivative(velocity[:, 0], fps), derivative(velocity[:, 1], fps)])
    force = net_force_on_bag(acceleration, mass_kg)
    power = power_on_bag(force, velocity)
    rate = energy_rate(velocity, point, mass_kg, fps)
    start = forward_swing if forward_swing is not None and forward_swing < release else release - int(0.6 * fps)
    window = slice(max(0, start), release + 1)
    magnitude = np.linalg.norm(force[window], axis=1)
    q: dict[str, Any] = {}
    assume = [BAG_ONLY_NOTE, "Bag assumed rigidly held one hand length beyond the wrist along the forearm.",
              "2D throw plane; second derivative of 6 Hz filtered landmarks (noise-sensitive)."]
    if np.isfinite(magnitude).any():
        i = int(np.nanargmax(magnitude))
        f_peak = force[window][i]
        q["peak_net_force_on_bag_n"] = quantity(float(magnitude[i]), "N", "estimated", "max |m (a_bag − g⃗)|",
                                                assumptions=assume)
        q["mean_net_force_on_bag_n"] = quantity(float(np.nanmean(magnitude)), "N", "estimated",
                                                "mean |m (a_bag − g⃗)| over the forward swing", assumptions=assume)
        q["force_direction_at_peak_deg"] = quantity(float(math.degrees(math.atan2(f_peak[1], f_peak[0]))), "°",
                                                    "estimated", "atan2(F_y, F_x) at peak |F|", assumptions=assume)
        p_win, r_win = power[window], rate[window]
        ok = np.isfinite(p_win) & np.isfinite(r_win)
        peak_p = float(np.nanmax(p_win)) if ok.any() else None
        agree = ok.any() and peak_p and float(np.max(np.abs(p_win[ok] - r_win[ok]))) < 0.10 * abs(peak_p)
        q["peak_power_on_bag_w"] = (quantity(peak_p, "W", "estimated", "max F·v (checked against dE/dt)",
                                             assumptions=assume) if agree else
                                    _missing("W", "max F·v", "Power estimates (F·v vs dE/dt) disagree by > 10 %."))
    else:
        for key, unit in (("peak_net_force_on_bag_n", "N"), ("mean_net_force_on_bag_n", "N"),
                          ("force_direction_at_peak_deg", "°"), ("peak_power_on_bag_w", "W")):
            q[key] = _missing(unit, "m (a − g⃗)", "Arm landmarks missing in the forward swing.")
    if 0 <= release < len(point) and np.isfinite(velocity[release]).all():
        q["hand_speed_at_release_m_s"] = quantity(float(np.linalg.norm(velocity[release])), "m/s", "measured",
                                                  "|d(hand point)/dt| at release", assumptions=assume[1:])
        q["hand_acceleration_at_release_m_s2"] = quantity(float(np.linalg.norm(acceleration[release])), "m/s²",
                                                          "estimated", "|d²(hand point)/dt²| at release",
                                                          assumptions=assume[1:])
    return {"quantities": q, "series": {"bag_point_m": point.tolist(), "velocity_m_s": velocity.tolist(),
                                        "acceleration_m_s2": acceleration.tolist(), "force_n": force.tolist(),
                                        "power_w": power.tolist(), "energy_rate_w": rate.tolist()},
            "arm_length_m": arm}


def _interval(samples: np.ndarray) -> list[float] | None:
    s = samples[np.isfinite(samples)]
    return None if s.size < 20 else [float(np.percentile(s, 2.5)), float(np.percentile(s, 97.5))]


def release_chain(speed: float, angle_deg: float, height_m: float, to_front_m: float, se: dict[str, float],
                  mass_range: tuple[float, float] = BAG_MASS_RANGE_KG, rel_scale_sd: float = 0.05,
                  draws: int = MC_DRAWS, seed: int = 0, board: Board = Board()) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    scale = rng.normal(1.0, rel_scale_sd, draws)          # metric scale error affects speed, height, distance
    v = (speed + rng.normal(0, se.get("speed", 0.0), draws)) * scale
    th = angle_deg + rng.normal(0, se.get("angle", 0.0), draws)
    h = (height_m + rng.normal(0, se.get("height", 0.0), draws)) * scale
    d = to_front_m * scale
    m = rng.uniform(*mass_range, draws)
    nominal_m = BAG_MASS_KG
    vx, vy = speed * math.cos(math.radians(angle_deg)), speed * math.sin(math.radians(angle_deg))
    nominal = release_state(vx, vy, height_m, nominal_m)
    ke = 0.5 * m * v**2
    pe = m * 9.81 * h
    p = m * v
    v_req = np.array([required_speed(a, hh, dd, board) or np.nan for a, hh, dd in zip(th, h, d)])
    v_min = np.array([minimum_speed(hh, dd, board) for hh, dd in zip(h, d)])
    err = np.array([along_error_m(vv * math.cos(math.radians(a)), vv * math.sin(math.radians(a)), hh, dd, board)
                    or np.nan for vv, a, hh, dd in zip(v, th, h, d)])
    req0 = required_speed(angle_deg, height_m, to_front_m, board)
    err0 = along_error_m(vx, vy, height_m, to_front_m, board)
    common = ["Scale uncertainty ±5 % (1 SD) unless the scale check gives a tighter value.",
              "Bag mass 15.5–16 oz (uniform).", "Drag-free flight."]
    out = {
        "release_speed_m_s": quantity(speed, "m/s", "measured", "|v| from the ballistic flight fit",
                                      interval=_interval(v), assumptions=common[:1]),
        "release_angle_deg": quantity(angle_deg, "°", "measured", "atan2(v_y, v_x) from the flight fit",
                                      interval=_interval(th)),
        "release_height_m": quantity(height_m, "m", "measured", "bag height above the floor line at release",
                                     interval=_interval(h), assumptions=common[:1]),
        "momentum_kg_m_s": quantity(nominal["momentum_magnitude_kg_m_s"], "kg·m/s", "measured", "p = m v",
                                    interval=_interval(p), assumptions=common[:2]),
        "kinetic_energy_j": quantity(nominal["kinetic_energy_j"], "J", "measured", "KE = ½ m v²",
                                     interval=_interval(ke), assumptions=common[:2]),
        "potential_energy_j": quantity(nominal["potential_energy_j"], "J", "measured", "PE = m g h",
                                       interval=_interval(pe), assumptions=common[:2]),
        "mechanical_energy_j": quantity(nominal["mechanical_energy_j"], "J", "measured", "E = KE + PE",
                                        interval=_interval(ke + pe), assumptions=common[:2]),
        "energy_match_percent": (quantity(100 * (speed**2 / req0**2 - 1), "%", "estimated",
                                          "100 (v² / v_req² − 1), v_req lands on the hole centre at this angle/height",
                                          interval=_interval(100 * (v**2 / v_req**2 - 1)), assumptions=common)
                                 if req0 else _missing("%", "energy match", "No speed reaches the hole at this angle.")),
        "speed_margin_over_minimum_percent": quantity(100 * (speed / minimum_speed(height_m, to_front_m, board) - 1),
                                                      "%", "estimated", "100 (v / v_min − 1), v_min over all angles",
                                                      interval=_interval(100 * (v / v_min - 1)),
                                                      assumptions=common + ["Venkadesan & Mahadevan (2017): most "
                                                                            "accurate throws are slightly above v_min."]),
        "predicted_along_error_in": (quantity(err0 / INCH_M, "in", "estimated",
                                              "drag-free landing on the deck plane − hole centre (+ = long)",
                                              interval=None if _interval(err) is None else
                                              [x / INCH_M for x in _interval(err)], assumptions=common)
                                     if err0 is not None else _missing("in", "predicted landing", "Path never reaches the deck plane.")),
    }
    return out


def build_chain(*, angles, fps, forward_swing, release, joints_m: dict[str, np.ndarray] | None,
                release_values: dict[str, float | None], release_se: dict[str, float], to_front_m: float | None,
                measured_along_error_m: float | None, board: Board = Board(), scale_rel_sd: float = 0.05) -> dict[str, Any]:
    q = dict(body_chain(angles, fps, forward_swing, release))
    series: dict[str, Any] = {}
    notes = [BAG_ONLY_NOTE]
    if joints_m is not None:
        hand = hand_chain(joints_m["shoulder"], joints_m["elbow"], joints_m["wrist"], fps, forward_swing, release)
        q.update(hand["quantities"])
        series = hand["series"]
        if to_front_m is not None:
            pos = np.asarray(series["bag_point_m"])
            vel = np.asarray(series["velocity_m_s"])
            s = timing_sensitivity(pos, vel, release, fps, to_front_m, board)
            q["timing_sensitivity_in_per_10ms"] = (
                quantity(s / INCH_M, "in / 10 ms", "estimated",
                         "Δ landing for releasing 10 ms later, from the hand path at release (Nasu et al. 2014)",
                         assumptions=["Hand path used as the bag path around release.", "Drag-free flight."])
                if s is not None else _missing("in / 10 ms", "timing sensitivity", "Hand path incomplete at release."))
    else:
        notes.append("Throw-plane joint positions unavailable (no board scale); hand/bag mechanics withheld.")
    v, a, h = (release_values.get(k) for k in ("speed", "angle", "height"))
    if None not in (v, a, h, to_front_m):
        q.update(release_chain(v, a, h, to_front_m, release_se, rel_scale_sd=scale_rel_sd, board=board))
    q["measured_along_error_in"] = (quantity(measured_along_error_m / INCH_M, "in", "measured",
                                             "observed first contact − hole centre along the throw line (+ = long)")
                                    if measured_along_error_m is not None else
                                    _missing("in", "measured landing", "First contact not observed on this throw."))
    return {"quantities": q, "series": series, "notes": notes}


def flatten_for_summaries(chain: dict[str, Any]) -> dict[str, float | None]:
    out = {}
    for name, item in chain["quantities"].items():
        value = item["value"] if item["state"] != "unavailable" else None
        out[f"chain_{name}"] = value if not isinstance(value, str) else None
    return out
```

Note on the circular-swing test: the geometry there puts the hand point at radius `r`; the assertion only checks the sign/size of the vertical force at the bottom of the swing (centripetal + weight), which holds for any positive angular speed.

- [ ] **Step 4: Wire into the pipeline** — after `summaries.update(timing)` (≈ line 795) in `analyze_trial`:

```python
    from .chain import build_chain, flatten_for_summaries
    from .regulation import Board
    board_payload = (auto_flight or {}).get("board") if auto_accepted else None
    joints_m = to_front = None
    if board_payload and board_payload.get("status") == "found" and camera_to_release:
        from .board import solve_board
        model = solve_board(np.asarray(board_payload["corners_px"], float), (video.width, video.height))
        def plane(name):
            steady = stabilize_points(filtered[:, landmarks.index(f"{context.throwing_side}_{name}")], camera_to_release)
            out = np.full_like(steady, np.nan)
            ok = np.isfinite(steady).all(axis=1)
            if ok.any():
                out[ok] = model.to_plane(steady[ok])
            return out
        joints_m = {j: plane(j) for j in ("shoulder", "elbow", "wrist")}
        if release_frame is not None and np.isfinite(joints_m["wrist"][release_frame]).all():
            to_front = float(-joints_m["wrist"][release_frame][0])   # board front edge is at plane x = 0
            summaries["release_to_board_front_m"] = to_front
    chain = build_chain(
        angles={"arm_to_trunk_deg": kinematics.values["arm_to_trunk_deg"],
                "elbow_angle_deg": kinematics.values["elbow_angle_deg"]},
        fps=video.fps, forward_swing=events["forward_swing"].effective_frame, release=release_frame,
        joints_m=joints_m,
        release_values={"speed": summaries.get("bag_release_speed_m_s"), "angle": summaries.get("bag_release_angle_deg"),
                        "height": summaries.get("bag_release_height_m")},
        release_se={"speed": summaries.get("bag_release_speed_se_m_s") or 0.1,
                    "angle": summaries.get("bag_release_angle_se_deg") or 1.0, "height": 0.02},
        to_front_m=to_front, measured_along_error_m=summaries.get("landing_along_error_m"),
        scale_rel_sd=max(0.02, (scale_check.get("max_disagreement") or 0.05) / 2))
    summaries.update(flatten_for_summaries(chain))
```

Guard the block with `if release_frame is not None:` (set `chain = None` otherwise), and add `results["chain"] = chain` in the results assembly. `summaries.get("bag_release_speed_se_m_s")` may not exist — check with `grep -n "_se_" python/cornhole_biomech/pipeline.py`; if absent, the `or 0.1` fallback applies and the assumption list already states it.

- [ ] **Step 5: Run the whole suite**

Run: `MPLCONFIGDIR=$TMPDIR/mpl PYTHONPATH=python .venv/bin/python -m pytest tests -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add python/cornhole_biomech/chain.py python/cornhole_biomech/pipeline.py tests/test_chain.py
git commit -m "Per-throw body-to-outcome chain: joint timing, bag-only force/power, energy, Monte Carlo intervals

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Within-athlete analyses linking movement to performance

**Files:**
- Create: `python/cornhole_biomech/chain_analysis.py`
- Modify: `python/cornhole_biomech/pipeline.py:analyze_relationships` (add `result["chain_analysis"]`)
- Test: `tests/test_chain_analysis.py`

**Interfaces:**
- Consumes: rows from `analyze_relationships` (each row has `score_category` and every `chain_*` summary), `mechanics.landing_jacobian`, `mechanics.error_budget`, `performance.cliffs_delta`, `performance.critical_delta(n1, n2, comparisons)`, `performance.group_label(score) -> "scored" | "miss" | None`.
- Produces:
  - `MIN_THROWS = 8`, `BOOTSTRAP = 2000`.
  - `BODY_RELEASE_PAIRS` (fixed list, pre-specified):
    `("chain_elbow_peak_extension_velocity_deg_s", "chain_release_speed_m_s")`,
    `("chain_shoulder_peak_angular_velocity_deg_s", "chain_release_speed_m_s")`,
    `("chain_shoulder_angle_at_release_deg", "chain_release_angle_deg")`,
    `("chain_elbow_angle_at_release_deg", "chain_release_angle_deg")`,
    `("chain_hand_speed_at_release_m_s", "chain_release_speed_m_s")`.
  - `OUTCOME_VARIABLES` (fixed list): `chain_release_speed_m_s`, `chain_release_angle_deg`, `chain_release_height_m`, `chain_energy_match_percent`, `chain_timing_sensitivity_in_per_10ms`, `chain_elbow_peak_extension_velocity_deg_s`, `chain_shoulder_peak_angular_velocity_deg_s`.
  - `error_budget_analysis(rows, board=Board()) -> dict`
  - `predicted_vs_measured(rows) -> dict` (`r_squared`, `n`, `status`)
  - `body_release_links(rows, seed=0) -> list[dict]` (`x`, `y`, `rho`, `ci`, `n`, `status`, `sentence`)
  - `outcome_links(rows) -> list[dict]` (Cliff's δ scored vs miss, Holm-style `critical_delta(..., comparisons=len(OUTCOME_VARIABLES))`, rank correlation with |measured along error|)
  - `speed_angle_tradeoff(rows) -> dict` (Theil–Sen slope, Spearman ρ)
  - `coordination_variability(curves: list[np.ndarray]) -> dict` (curves = per-throw (101, 2) time-normalised shoulder/elbow angles over the forward swing; returns `mean_sd_deg`, per-throw `rms_from_mean_deg`)
  - `summarize(rows, curves=None) -> dict` (all of the above; every block has `status`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_chain_analysis.py
import numpy as np
import pytest

from cornhole_biomech import chain_analysis as ca


def rows_from(speed, angle, height, err=None, score=None, elbow=None):
    out = []
    for i in range(len(speed)):
        out.append({"trial_id": f"t{i}", "score_category": None if score is None else score[i],
                    "chain_release_speed_m_s": speed[i], "chain_release_angle_deg": angle[i],
                    "chain_release_height_m": height[i],
                    "chain_measured_along_error_in": None if err is None else err[i],
                    "chain_predicted_along_error_in": None if err is None else err[i] + 0.5,
                    "chain_elbow_peak_extension_velocity_deg_s": None if elbow is None else elbow[i]})
    return out


def test_error_budget_speed_dominates_when_only_speed_varies():
    rng = np.random.default_rng(0)
    n = 12
    rows = rows_from(8.5 + rng.normal(0, 0.3, n), np.full(n, 30.0) + rng.normal(0, 0.01, n), np.full(n, 0.9), )
    for r in rows:
        r["release_to_board_front_m"] = 7.3
    out = ca.error_budget_analysis(rows)
    assert out["status"] == "available"
    assert out["shares"]["speed"] > 0.9


def test_predicted_vs_measured_r2():
    rng = np.random.default_rng(1)
    err = rng.normal(0, 10, 12)
    out = ca.predicted_vs_measured(rows_from(np.full(12, 8.0), np.full(12, 30.0), np.full(12, 0.9), err=err))
    assert out["r_squared"] == pytest.approx(1.0, abs=1e-9)


def test_body_release_link_detects_monotone_relation():
    elbow = np.linspace(200, 400, 12)
    speed = 6 + 0.01 * elbow
    links = ca.body_release_links(rows_from(speed, np.full(12, 30.0), np.full(12, 0.9), elbow=elbow), seed=0)
    link = next(l for l in links if l["x"] == "chain_elbow_peak_extension_velocity_deg_s")
    assert link["rho"] == pytest.approx(1.0)
    assert link["ci"][0] > 0.5
    assert "associated" in link["sentence"]


def test_analyses_insufficient_data():
    rows = rows_from([8.0, 8.1], [30, 31], [0.9, 0.9])
    out = ca.summarize(rows)
    for key in ("error_budget", "predicted_vs_measured", "speed_angle_tradeoff"):
        assert out[key]["status"] == "insufficient_data"
    assert all(l["status"] == "insufficient_data" for l in out["body_release"])


def test_coordination_variability_zero_for_identical_curves():
    curve = np.column_stack([np.linspace(0, 40, 101), np.linspace(150, 170, 101)])
    out = ca.coordination_variability([curve, curve.copy(), curve.copy()])
    assert out["mean_sd_deg"] == pytest.approx(0.0)
```

- [ ] **Step 2: Run to verify failure** — `pytest tests/test_chain_analysis.py -q` → FAIL.

- [ ] **Step 3: Implement**

```python
# python/cornhole_biomech/chain_analysis.py
"""Within-athlete analyses linking the chain to performance (spec §6).

All variables are pre-specified (lists below), claims are associational, and each
block reports `status` so the UI never shows a finding without enough throws.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy import stats

from .mechanics import error_budget, landing_jacobian
from .performance import cliffs_delta, critical_delta, group_label
from .regulation import INCH_M, Board

MIN_THROWS = 8
MIN_PER_GROUP = 5
BOOTSTRAP = 2000
BODY_RELEASE_PAIRS = (
    ("chain_elbow_peak_extension_velocity_deg_s", "chain_release_speed_m_s"),
    ("chain_shoulder_peak_angular_velocity_deg_s", "chain_release_speed_m_s"),
    ("chain_shoulder_angle_at_release_deg", "chain_release_angle_deg"),
    ("chain_elbow_angle_at_release_deg", "chain_release_angle_deg"),
    ("chain_hand_speed_at_release_m_s", "chain_release_speed_m_s"),
)
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


def _pairs(rows, x, y):
    xs, ys = [], []
    for r in rows:
        a, b = r.get(x), r.get(y)
        if a is not None and b is not None and math.isfinite(a) and math.isfinite(b):
            xs.append(a); ys.append(b)
    return np.array(xs, float), np.array(ys, float)


def _insufficient(n, need=MIN_THROWS, **extra):
    return {"status": "insufficient_data", "n": int(n), "message": f"Needs ≥ {need} throws with these values (has {n}).",
            **extra}


def error_budget_analysis(rows, board: Board = Board()) -> dict[str, Any]:
    keys = ("chain_release_speed_m_s", "chain_release_angle_deg", "chain_release_height_m", "release_to_board_front_m")
    usable = [r for r in rows if all(r.get(k) is not None for k in keys)]
    if len(usable) < MIN_THROWS:
        return _insufficient(len(usable))
    arr = {k: np.array([r[k] for r in usable], float) for k in keys}
    center = {k: float(np.median(v)) for k, v in arr.items()}
    jac = landing_jacobian(center[keys[0]], center[keys[1]], center[keys[2]], center[keys[3]], board)
    sd = {"speed": float(np.std(arr[keys[0]], ddof=1)), "angle": float(np.std(arr[keys[1]], ddof=1)),
          "height": float(np.std(arr[keys[2]], ddof=1))}
    budget = error_budget(jac, sd)
    measured = [r["chain_measured_along_error_in"] for r in usable if r.get("chain_measured_along_error_in") is not None]
    top = max(budget["shares"], key=budget["shares"].get)
    return {"status": "available", "n": len(usable), "jacobian": jac, "sd": sd, **budget,
            "predicted_sd_in": budget["predicted_sd_m"] / INCH_M,
            "measured_sd_in": float(np.std(measured, ddof=1)) if len(measured) >= 3 else None,
            "sentence": (f"About {100 * budget['shares'][top]:.0f}% of the landing spread explained by release "
                         f"comes from variation in release {top}."),
            "method": "Jacobian of drag-free landing w.r.t. release speed, angle, height (Venkadesan & Mahadevan 2017)."}


def predicted_vs_measured(rows) -> dict[str, Any]:
    p, m = _pairs(rows, "chain_predicted_along_error_in", "chain_measured_along_error_in")
    if len(p) < MIN_THROWS:
        return _insufficient(len(p))
    r = float(np.corrcoef(p, m)[0, 1]) if np.std(p) > 0 and np.std(m) > 0 else 0.0
    return {"status": "available", "n": len(p), "r_squared": r * r, "mean_offset_in": float(np.mean(m - p)),
            "sentence": (f"Release conditions explain {100 * r * r:.0f}% of the measured landing variation; the rest "
                         "reflects bag slide, air drag and measurement error.")}


def _spearman_ci(x, y, seed):
    rng = np.random.default_rng(seed)
    n = len(x)
    boots = []
    for _ in range(BOOTSTRAP):
        idx = rng.integers(0, n, n)
        if np.ptp(x[idx]) == 0 or np.ptp(y[idx]) == 0:
            continue
        boots.append(stats.spearmanr(x[idx], y[idx]).statistic)
    return [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))] if boots else None


def body_release_links(rows, seed: int = 0) -> list[dict[str, Any]]:
    out = []
    for x, y in BODY_RELEASE_PAIRS:
        a, b = _pairs(rows, x, y)
        if len(a) < MIN_THROWS or np.ptp(a) == 0 or np.ptp(b) == 0:
            out.append({"x": x, "y": y, **_insufficient(len(a))})
            continue
        rho = float(stats.spearmanr(a, b).statistic)
        ci = _spearman_ci(a, b, seed)
        clear = ci is not None and (ci[0] > 0 or ci[1] < 0)
        direction = "higher" if rho > 0 else "lower"
        sentence = (f"Throws with higher {LABELS[x]} were associated with {direction} {LABELS[y]} "
                    f"(ρ = {rho:.2f}, 95% CI {ci[0]:.2f} to {ci[1]:.2f})." if clear else
                    f"No clear association between {LABELS[x]} and {LABELS[y]} (ρ = {rho:.2f}).")
        out.append({"x": x, "y": y, "status": "available", "n": len(a), "rho": rho, "ci": ci, "clear": clear,
                    "sentence": sentence})
    return out


def outcome_links(rows) -> list[dict[str, Any]]:
    out = []
    for key in OUTCOME_VARIABLES:
        scored = np.array([r[key] for r in rows if r.get(key) is not None and group_label(r.get("score_category")) == "scored"], float)
        miss = np.array([r[key] for r in rows if r.get(key) is not None and group_label(r.get("score_category")) == "miss"], float)
        err_x, err_y = _pairs(rows, key, "chain_measured_along_error_in")
        item: dict[str, Any] = {"variable": key, "label": LABELS[key], "n_scored": len(scored), "n_miss": len(miss)}
        if len(scored) >= MIN_PER_GROUP and len(miss) >= MIN_PER_GROUP:
            delta = cliffs_delta(miss, scored)
            threshold = critical_delta(len(miss), len(scored), comparisons=len(OUTCOME_VARIABLES))
            item.update(cliffs_delta=delta, critical_delta=threshold, distinguishes=abs(delta) >= threshold)
        else:
            item.update(cliffs_delta=None, distinguishes=None,
                        group_message=f"Needs ≥ {MIN_PER_GROUP} scored and ≥ {MIN_PER_GROUP} missed throws.")
        if len(err_x) >= MIN_THROWS and np.ptp(err_x) > 0 and np.ptp(err_y) > 0:
            item["rho_abs_landing_error"] = float(stats.spearmanr(err_x, np.abs(err_y)).statistic)
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
    return {"status": "available", "n": len(angle), "slope_m_s_per_deg": float(slope), "slope_ci": [float(lo), float(hi)],
            "rho": rho, "sentence": f"Each extra degree of release angle came with {slope:+.2f} m/s of release speed "
                                    "(Linthorne 2001: the best angle is individual)."}


def coordination_variability(curves: list[np.ndarray]) -> dict[str, Any]:
    if len(curves) < 3:
        return _insufficient(len(curves), need=3)
    stack = np.stack([np.asarray(c, float) for c in curves])      # throws × 101 × 2
    mean = np.nanmean(stack, axis=0)
    sd = np.sqrt(np.nanvar(stack[..., 0], axis=0, ddof=1) + np.nanvar(stack[..., 1], axis=0, ddof=1))
    rms = np.sqrt(np.nanmean(np.sum((stack - mean) ** 2, axis=2), axis=1))
    return {"status": "available", "n": len(curves), "mean_sd_deg": float(np.nanmean(sd)),
            "rms_from_mean_deg": rms.tolist(),
            "method": "Point-wise SD of the shoulder–elbow angle–angle curve over the time-normalised forward swing."}


def summarize(rows, curves: list[np.ndarray] | None = None) -> dict[str, Any]:
    return {"error_budget": error_budget_analysis(rows), "predicted_vs_measured": predicted_vs_measured(rows),
            "body_release": body_release_links(rows), "outcome": outcome_links(rows),
            "speed_angle_tradeoff": speed_angle_tradeoff(rows),
            "coordination": coordination_variability(curves or []),
            "wording": "Associations within this athlete's throws; not causes."}
```

- [ ] **Step 4: Save swing curves per throw and hook into `analyze_relationships`**

In `analyze_trial` (Task 9 block), when `events["forward_swing"].effective_frame` and `release_frame` exist, add to results:

```python
    fs = events["forward_swing"].effective_frame
    if fs is not None and release_frame is not None and release_frame > fs + 2:
        grid = np.linspace(fs, release_frame, 101)
        frames_idx = np.arange(len(kinematics.values["elbow_angle_deg"]))
        results["swing_curve_deg"] = np.column_stack([
            np.interp(grid, frames_idx, kinematics.values["arm_to_trunk_deg"]),
            np.interp(grid, frames_idx, kinematics.values["elbow_angle_deg"])]).tolist()
```

In `analyze_relationships`, collect `curves.append(np.asarray(result["swing_curve_deg"]))` when present, copy `result["summaries"]["release_to_board_front_m"]` into rows (already via `row.update(result.get("summaries", {}))`), and before `write_json(output_path, result)` add:

```python
    from .chain_analysis import summarize as chain_summarize
    result["chain_analysis"] = chain_summarize(rows, curves)
```

- [ ] **Step 5: Run the whole suite** — `pytest tests -q` → PASS.

- [ ] **Step 6: Commit**

```bash
git add python/cornhole_biomech/chain_analysis.py python/cornhole_biomech/pipeline.py tests/test_chain_analysis.py
git commit -m "Within-athlete analyses: landing error budget, body-to-release links, outcome links, coordination

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Version bump, pilot regression, documentation

**Files:**
- Modify: `python/cornhole_biomech/__init__.py:10`
- Modify: `scripts/regression_check.py` (report new fields)
- Create: `docs/SCENE_REGRESSION.md`
- Modify: `docs/REFERENCES.md`, `docs/BIOMECHANICS_METHODS.md`

- [ ] **Step 1: Bump the method version**

```python
METHOD_VERSION = "2026.09.23-scene"
```

Run `pytest tests -q`; fix any test that pins the old version literal by importing `METHOD_VERSION`.

- [ ] **Step 2: Extend the regression report** — in `scripts/regression_check.py` add to the per-throw record (after the rerun, reading the new `results.json` and `auto_flight.json`):

```python
        auto = json.loads((target / "auto_flight.json").read_text()) if (target / "auto_flight.json").exists() else {}
        old_auto = json.loads((analysis / "auto_flight.json").read_text()) if (analysis / "auto_flight.json").exists() else {}
        record.update({
            "board_status": (auto.get("board") or {}).get("status"),
            "board_confidence": (auto.get("board") or {}).get("confidence"),
            "contact_kind": (auto.get("contact") or {}).get("kind"),
            "old_contact_frame": old_auto.get("first_contact_frame"),
            "new_contact_frame": auto.get("first_contact_frame"),
            "release_delta_frames": (None if auto.get("release_frame") is None or old_auto.get("release_frame") is None
                                     else auto["release_frame"] - old_auto["release_frame"]),
            "suggested_score": (auto.get("suggested_outcome") or {}).get("score"),
            "masks_status": (auto.get("scene") or {}).get("masks_status"),
        })
```

(`record` is the dict the script already builds per throw — confirm its name with `grep -n "def rerun" -A 40 scripts/regression_check.py` and use that name.)

- [ ] **Step 3: Run the regression on the pilot library**

Run (≈ 20–40 min; run in background):

```bash
app/CornholeBiomechanics/.build/debug/SceneVision --help >/dev/null 2>&1 || true
MPLCONFIGDIR=$TMPDIR/mpl PYTHONPATH=python .venv/bin/python scripts/regression_check.py \
  --library "$HOME/Documents/Cornhole Pilot Library" --scratch "$TMPDIR/scene-regression" \
  --output "$TMPDIR/scene-regression.json"
```

Expected acceptance (spec §1):
- `board_status == "found"` on ≥ 22 of 26 clips;
- every `release_delta_frames` ∈ {−1, 0, 1};
- every clip whose old contact was mid-air now has `contact_kind == "lost_in_flight"` and `new_contact_frame is None`.

For each clip whose contact changed, extract the old and new contact frames with the snippet from Task 4 Step 5 (swap in `cap.set(1, frame)`) and look at them. Record a table in `docs/SCENE_REGRESSION.md`: clip, board status/confidence, old contact, new contact kind/frame, release delta, suggested score, what the frame shows. If < 22 boards are found, list the failures and use `set-board-corners --apply-to` for that session; do **not** retune thresholds on the pilot set without writing down why.

- [ ] **Step 4: Documentation**

Append to `docs/REFERENCES.md` a section "## Throwing accuracy and release mechanics (added 2026-09-23)" with the eight references exactly as listed in the spec §10 (full citations, DOIs).

Append to `docs/BIOMECHANICS_METHODS.md` a section "## Scene, throw plane and body-to-outcome chain (METHOD_VERSION 2026.09.23-scene)" covering: throw-plane geometry and assumptions (athlete on board centreline, FOV range 55–75°, φ flag at 20°); contact rule and tolerances (6 cm deck/floor, 4 in hole-vanish radius); the quantity table from spec §5 with formulas; the bag-only labelling rule; Monte Carlo inputs; the analyses of spec §6; the "not reported" list of spec §7.

- [ ] **Step 5: Full verification**

Run: `./verify.sh` (runs Python and Swift suites). Expected: all pass. If `verify.sh` does not build `SceneVision`, add `swift build ... --product SceneVision` to it.

- [ ] **Step 6: Commit**

```bash
git add python/cornhole_biomech/__init__.py scripts/regression_check.py docs/SCENE_REGRESSION.md docs/REFERENCES.md docs/BIOMECHANICS_METHODS.md verify.sh
git commit -m "Scene engine method version, pilot regression results and methods documentation

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Spec coverage check

| Spec section | Task |
|---|---|
| §2.1 scene_vision | 6 |
| §2.1 regulation.py / §3 | 1 |
| §2.1 background.py / §4.2 | 3 |
| §2.1 board.py / §4.3 / §4.5 scale + φ | 4, 8 |
| §4.1 athlete masks (seeding, plate) | 6, 7 |
| §4.4 contact, predicted contact, landing, outcome | 5, 7, 8 |
| §5 chain quantities + Monte Carlo + labelling | 2, 9 |
| §6 analyses 1–6 | 10 (timing strategy = `chain_timing_sensitivity_in_per_10ms` in `outcome_links`) |
| §7 not reported | Global Constraints; Task 11 docs |
| §8 failure handling | 4, 5, 6, 7, 8, 10 (status fields) |
| §9 testing | every task + 11 |
| §10 references | 11 |

Deviations from the spec, decided while planning (reviewer: check these):
1. **Reflections**: no separate reflection filter — a mirrored flight curves upward in the image and is already rejected by `_plausible` (downward curvature required).
2. **Out-of-plane correction**: instead of dividing speeds by cos φ, the board pose (solvePnP) gives a full throw-plane homography, which already handles perspective along the throw line; φ is still reported and flagged above 20°.
3. **Person boxes**: `scene-vision` writes masks only; the pose tracker already keeps the athlete by continuity, so boxes were dropped (YAGNI).
4. **Plate timing**: the plate and board are computed after the flight is chosen (release-frame reference), so bystander suppression during seeding comes from person masks, not the plate.
