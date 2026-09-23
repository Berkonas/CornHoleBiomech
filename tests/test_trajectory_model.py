"""Ballistic model check: exact on a true projectile, honest about a decelerating one."""
import numpy as np

from cornhole_biomech.trajectory_model import ballistic_model_check

FPS = 60.0


def track(n=300, release=100, flight=50, ax=0.0):
    p = np.full((n, 2), np.nan)
    t = np.arange(flight) / FPS
    p[release:release + flight, 0] = 200 + 1000 * t + 0.5 * ax * t**2
    p[release:release + flight, 1] = 500 - 800 * t + 0.5 * 1800 * t**2
    return p


def test_true_projectile_fits_exactly_with_apex_and_units():
    out = ballistic_model_check(track(), 100, 149, FPS, pixels_per_meter=180.0, arm_length_px=100.0)
    assert out["status"] == "fitted"
    assert out["in_sample_rmse_px"] < 1e-6 and out["out_of_sample_rmse_px"] < 1e-6
    assert abs(out["vertical_acceleration_px_s2"] - 1800) < 1e-6
    # apex at t = 800/1800 s → frame 100 + 26.7
    assert out["apex_frame"] == 127
    assert abs(out["apex_rise_px"] - 800**2 / (2 * 1800)) < 1e-6
    assert abs(out["apex_rise_m"] - out["apex_rise_px"] / 180.0) < 1e-9


def test_horizontal_deceleration_is_reported_not_hidden():
    out = ballistic_model_check(track(ax=-300.0), 100, 149, FPS)
    assert out["horizontal_to_vertical_acceleration"] < -0.1
    assert out["out_of_sample_rmse_px"] > out["in_sample_rmse_px"] > 0.5
    assert "cannot separate" in out["interpretation"]


def test_contact_and_missing_samples_are_excluded():
    p = track()
    p[140:] = [9999, 9999]           # impact / slide after first contact
    p[110:113] = np.nan
    out = ballistic_model_check(p, 100, 140, FPS)
    assert out["sample_count"] == 39 - 3
    assert out["in_sample_rmse_px"] < 1e-6


def test_needs_release_and_enough_points():
    assert ballistic_model_check(track(), None, 149, FPS)["status"] == "insufficient_data"
    assert ballistic_model_check(track(), 100, 108, FPS)["status"] == "insufficient_data"
