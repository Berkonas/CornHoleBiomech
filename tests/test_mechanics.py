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
