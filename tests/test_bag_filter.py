"""Flight filter: raw data preserved, noise reduced, outliers rejected, gaps bounded."""
import numpy as np

from cornhole_biomech.bag_filter import (
    filtered_to_raw,
    smooth_flight,
    stabilize_points,
    third_difference_sigma,
)

FPS = 60.0


def truth(n=50, drag=0.0):
    t = np.arange(n) / FPS
    x = 300 + 1100 * t - 0.5 * drag * t**2
    y = 600 - 700 * t + 0.5 * 1800 * t**2
    return t, x, y


def points_from(x, y, frames, start=100):
    return [{"frame": start + int(i), "x": float(x[i]), "y": float(y[i])} for i in frames]


def test_filter_reduces_noise_and_keeps_raw_values():
    rng = np.random.default_rng(3)
    _, x, y = truth()
    nx, ny = x + rng.normal(0, 1.5, x.size), y + rng.normal(0, 1.5, y.size)
    out = smooth_flight(points_from(nx, ny, range(x.size)), FPS)
    assert out["status"] == "filtered"
    rows = out["frames"]
    raw_err = np.hypot(nx - x, ny - y)
    filt_err = np.hypot(np.array([r["x"] for r in rows]) - x, np.array([r["y"] for r in rows]) - y)
    assert np.sqrt(np.mean(filt_err**2)) < 0.7 * np.sqrt(np.mean(raw_err**2))
    assert [r["raw_x"] for r in rows] == [float(v) for v in nx]   # raw copied unchanged
    assert 0.8 < out["measurement_sigma_px"] < 2.5


def test_outlier_is_rejected_but_kept_in_raw():
    rng = np.random.default_rng(4)
    _, x, y = truth()
    nx, ny = x + rng.normal(0, 1.0, x.size), y + rng.normal(0, 1.0, y.size)
    nx[25] += 40.0   # a jump to a wrong blob
    out = smooth_flight(points_from(nx, ny, range(x.size)), FPS)
    row = out["frames"][25]
    assert row["status"] == "rejected_outlier"
    assert row["raw_x"] == float(nx[25])
    assert abs(row["x"] - x[25]) < 4.0
    assert 125 in out["rejected_outlier_frames"]


def test_short_gaps_are_predicted_and_long_gaps_left_empty():
    _, x, y = truth(n=60)
    keep = [i for i in range(60) if not (20 <= i < 23) and not (35 <= i < 45)]
    out = smooth_flight(points_from(x, y, keep), FPS, max_gap_frames=6, sigma_px=1.0, q=1e5)
    rows = {r["frame"] - 100: r for r in out["frames"]}
    assert rows[21]["status"] == "predicted_gap"
    assert abs(rows[21]["x"] - x[21]) < 2.0 and abs(rows[21]["y"] - y[21]) < 2.0
    assert rows[21]["sd_x"] > rows[10]["sd_x"]   # uncertainty grows without measurements
    assert rows[40]["status"] == "predicted_gap_too_long" and rows[40]["x"] is None
    assert out["longest_gap_frames"] == 10


def test_filter_does_not_force_a_parabola():
    # Strong horizontal deceleration (perspective/drag): the filter follows it.
    _, x, y = truth(n=60, drag=1500.0)
    out = smooth_flight(points_from(x, y, range(60)), FPS)
    err = [abs(r["x"] - xx) for r, xx in zip(out["frames"], x)]
    assert max(err) < 1.0


def test_never_extrapolates_beyond_measurements():
    _, x, y = truth()
    out = smooth_flight(points_from(x, y, range(5, 45)), FPS)
    assert out["first_frame"] == 105 and out["last_frame"] == 144


def test_too_few_points():
    assert smooth_flight([{"frame": 1, "x": 1.0, "y": 1.0}], FPS)["status"] == "insufficient_data"


def test_third_difference_sigma_recovers_white_noise():
    rng = np.random.default_rng(5)
    _, x, y = truth(n=200)
    z = np.column_stack([x, y]) + rng.normal(0, 2.0, (200, 2))
    assert abs(third_difference_sigma(np.arange(200), z) - 2.0) < 0.4


def test_stabilization_round_trip():
    transforms = {"10": [[1, 0, 5.0], [0, 1, -3.0]], "11": [[1, 0, 6.0], [0, 1, -2.0]]}
    raw = np.full((20, 2), np.nan)
    raw[10] = [100, 200]; raw[11] = [110, 190]; raw[12] = [120, 180]
    stab = stabilize_points(raw, transforms)
    assert np.allclose(stab[10], [105, 197]) and np.allclose(stab[11], [116, 188])
    assert np.isnan(stab[12]).all()   # no transform: camera motion unknown, not guessed
    back = filtered_to_raw({"frames": [{"frame": 11, "x": 116.0, "y": 188.0}]}, transforms)
    assert np.allclose(back[11], (110, 190))
