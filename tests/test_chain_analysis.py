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
