"""Physics-based green/yellow/red release zones and sports statistics."""
import numpy as np
import pytest

from cornhole_biomech.zones import (
    Board,
    ZoneSettings,
    landing,
    predicted_zone,
    sports_stats,
    speed_to_hole,
    variable_zones,
    zone_report,
)

S = ZoneSettings()


def test_landing_matches_closed_form_on_flat_ground():
    r = landing(7.0, 30.0, 0.0, 50.0, S.board)
    assert r["kind"] == "short"
    assert r["horizontal_m"] == pytest.approx(49 * np.sin(np.radians(60)) / 9.80665, rel=1e-6)


def test_hole_speed_lands_green_and_extremes_red():
    v = speed_to_hole(35.0, 0.8, S)
    assert predicted_zone(v, 35.0, 0.8, S)["zone"] == "green"
    assert predicted_zone(v * 0.6, 35.0, 0.8, S)["zone"] == "red"
    assert predicted_zone(v * 1.5, 35.0, 0.8, S)["zone"] == "red"


def test_landing_slightly_short_of_hole_is_green_but_far_short_on_deck_is_yellow():
    # Along-deck positions relative to the hole centre.
    board = S.board
    assert S.zone_for("board", board.hole_along - 0.30) == "green"      # slides in
    assert S.zone_for("board", board.hole_along - 0.80) == "yellow"
    assert S.zone_for("board", board.hole_along + 0.20) == "yellow"     # past the hole, on the deck
    assert S.zone_for("short", -0.2) == "yellow"                          # can slide up onto the deck
    assert S.zone_for("short", -0.6) == "red"
    assert S.zone_for("long", None) == "red"


def test_speed_zone_is_narrower_than_angle_zone_in_relative_terms():
    center = {"speed": speed_to_hole(35.0, 0.8, S), "angle": 35.0, "height": 0.8}
    speed = variable_zones("speed", center, S)
    angle = variable_zones("angle", center, S)
    green_speed = next(b for b in speed["bands"] if b["zone"] == "green")
    green_angle = next(b for b in angle["bands"] if b["zone"] == "green")
    assert green_speed["low"] < center["speed"] < green_speed["high"]
    assert green_angle["low"] < 35.0 < green_angle["high"]
    rel_speed = (green_speed["high"] - green_speed["low"]) / center["speed"]
    rel_angle = (green_angle["high"] - green_angle["low"]) / 35.0
    assert rel_speed < rel_angle


def test_zone_report_checks_model_against_real_outcomes():
    v = speed_to_hole(35.0, 0.8, S)
    rows = [
        {"trial_id": "a", "score_category": 3, "bag_release_speed_m_s": v, "bag_release_angle_deg": 35.0, "bag_release_height_m": 0.8},
        {"trial_id": "b", "score_category": 0, "bag_release_speed_m_s": v * 0.6, "bag_release_angle_deg": 35.0, "bag_release_height_m": 0.8},
        {"trial_id": "c", "score_category": 1, "bag_release_speed_m_s": v, "bag_release_angle_deg": 35.0, "bag_release_height_m": 0.8},
        {"trial_id": "d", "score_category": None, "bag_release_speed_m_s": v, "bag_release_angle_deg": 35.0, "bag_release_height_m": 0.8},
        {"trial_id": "e", "score_category": 3},   # unscaled: no prediction
    ]
    report = zone_report(rows, S)
    assert report["status"] == "available"
    by_id = {t["trial_id"]: t for t in report["throws"]}
    assert by_id["a"]["zone"] == "green" and by_id["a"]["agrees"] is True
    assert by_id["b"]["zone"] == "red" and by_id["b"]["agrees"] is True
    assert by_id["c"]["agrees"] is False                   # predicted hole, observed board
    assert by_id["d"]["agrees"] is None
    assert "e" not in by_id
    assert report["agreement"] == {"n": 3, "agree": 2, "rate": pytest.approx(2 / 3)}
    assert {v["variable"] for v in report["variables"]} == {"angle", "speed", "height"}


def test_zone_report_needs_scaled_release_values():
    report = zone_report([{"trial_id": "x", "score_category": 1, "bag_release_angle_deg": 30}], S)
    assert report["status"] == "needs_scale"


def test_sports_stats_follow_acl_definitions():
    scores = [3, 1, 0, 1, 3, None, 0, 1]
    st = sports_stats(scores)
    assert st["bags"] == 7
    assert st["points_per_bag"] == pytest.approx(9 / 7)
    assert st["ppr"] == pytest.approx(4 * 9 / 7)
    assert st["in_percent"] == pytest.approx(100 * 2 / 7)
    assert st["on_percent"] == pytest.approx(100 * 3 / 7)
    assert st["off_percent"] == pytest.approx(100 * 2 / 7)
    assert st["unknown"] == 1
    assert sports_stats([])["ppr"] is None


def test_priority_is_the_variable_whose_spread_most_exceeds_its_green_window():
    v = speed_to_hole(35.0, 0.8, S)
    rng = np.random.default_rng(0)
    rows = [{"trial_id": str(i), "score_category": 1, "bag_release_speed_m_s": v + rng.normal(0, 0.4),
             "bag_release_angle_deg": 35.0 + rng.normal(0, 0.5), "bag_release_height_m": 0.8 + rng.normal(0, 0.01)}
            for i in range(12)]
    report = zone_report(rows, S)
    assert report["priority"]["variable"] == "speed"
    assert report["priority"]["demand_ratio"] > 1
