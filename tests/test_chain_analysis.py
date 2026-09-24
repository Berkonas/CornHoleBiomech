import math

import numpy as np
import pytest

from cornhole_biomech import chain_analysis as ca
from cornhole_biomech.mechanics import along_error_m
from cornhole_biomech.regulation import Board


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
    assert out["shares_if_independent"]["speed"] > 0.9


def test_error_budget_covariation_reduces_predicted_sd():
    # Strongly negatively correlated speed/angle (an athlete compensating: faster -> flatter):
    # the covariance-aware SD should sit well below the independent-variable SD, close to the
    # SD of each throw's own nonlinear prediction.
    board = Board()
    rng = np.random.default_rng(2)
    n = 12
    angle = 25.0 + rng.normal(0, 3.0, n)
    speed = 9.0 - 0.15 * (angle - 25.0) + rng.normal(0, 0.05, n)
    height = np.full(n, 0.9)
    distance = np.full(n, 7.3)
    rows = []
    for i in range(n):
        th = math.radians(angle[i])
        err_m = along_error_m(speed[i] * math.cos(th), speed[i] * math.sin(th), height[i], distance[i], board)
        rows.append({
            "trial_id": f"t{i}", "score_category": None,
            "chain_release_speed_m_s": speed[i], "chain_release_angle_deg": angle[i],
            "chain_release_height_m": height[i], "release_to_board_front_m": distance[i],
            "chain_predicted_along_error_in": err_m / ca.INCH_M if err_m is not None else None,
            "chain_measured_along_error_in": None,
        })
    out = ca.error_budget_analysis(rows)
    assert out["status"] == "available"
    assert out["predicted_sd_cov_in"] < out["independent_sd_in"]
    assert abs(out["predicted_sd_cov_in"] - out["predicted_sd_in"]) < abs(out["independent_sd_in"] - out["predicted_sd_in"])


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
    curves = [curve.copy() for _ in range(ca.MIN_THROWS)]
    ids = [f"t{i}" for i in range(ca.MIN_THROWS)]
    out = ca.coordination_variability(curves, ids)
    assert out["status"] == "available"
    assert out["mean_sd_deg"] == pytest.approx(0.0)
    assert set(out["rms_from_mean_deg"]) == set(ids)


def test_outcome_links_excludes_non_finite_values_from_group_arrays():
    # 5 scored + 5 miss with clean values, plus a NaN and an infinite value labeled with a
    # score_category that would otherwise put them in a group. Before the fix, `r.get(key) is
    # not None` let NaN/inf into the Cliff's-delta arrays even though every other analysis in
    # this module filters with `_finite`.
    speed = [8.0, 8.1, 8.2, 8.3, 8.4, 6.0, 6.1, 6.2, 6.3, 6.4]
    score = [3] * 5 + [0] * 5   # group_label: 1 or 3 -> "scored", 0 -> "miss"
    rows = rows_from(speed, [30.0] * 10, [0.9] * 10, score=score)
    rows.append({"trial_id": "nan-scored", "score_category": 3,
                "chain_release_speed_m_s": float("nan")})
    rows.append({"trial_id": "inf-miss", "score_category": 0,
                "chain_release_speed_m_s": float("inf")})
    out = ca.outcome_links(rows, seed=0)
    link = next(l for l in out if l["variable"] == "chain_release_speed_m_s")
    assert link["n_scored"] == 5 and link["n_miss"] == 5
    assert math.isfinite(link["cliffs_delta"])


def test_coordination_variability_drops_high_nan_curves():
    curve = np.column_stack([np.linspace(0, 40, 101), np.linspace(150, 170, 101)])
    bad = curve.copy()
    bad[:30] = np.nan   # ~30% missing, above the 20% drop threshold
    curves = [curve.copy() for _ in range(ca.MIN_THROWS)] + [bad]
    ids = [f"t{i}" for i in range(ca.MIN_THROWS)] + ["bad"]
    out = ca.coordination_variability(curves, ids)
    assert out["status"] == "available"
    assert "bad" not in out["rms_from_mean_deg"]
    assert out["n"] == ca.MIN_THROWS
