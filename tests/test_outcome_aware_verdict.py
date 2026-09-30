"""A made throw gets no corrections; a board bag gets signed advice from where it really stopped."""
from cornhole_biomech.verdict import throw_verdict
from cornhole_biomech.zones import ZoneSettings, personal_slide_allowance, personal_zone


def metric(value, unit="m/s", label="Release speed"):
    return {"value": value, "status": "reliable", "unit": unit, "label": label, "noise_floor": 0.1}


def release(speed, angle=38.0, height=0.9):
    return {"bag_release_speed_m_s": metric(speed), "bag_release_angle_deg": metric(angle, "°", "Release angle"),
            "bag_release_height_m": metric(height, "m", "Release height")}


def phase(kind, landed, end, slide, hang=None):
    return {"status": "measured", "touchdown": {"frame": 10, "u_in": 12, "v_in": 39 + landed, "from_hole_in": landed},
            "end": {"kind": kind, "frame": 30, "u_in": 12, "v_in": 39 + end, "from_hole_in": end, "note": ""},
            "slide": {"distance_in": slide}, "hang": {"seconds": hang} if hang else None,
            "suggested_outcome": {"score": 3 if kind == "fell_in_hole" else 1}}


def test_hole_gets_no_fix_even_when_the_model_says_short():
    settings = ZoneSettings(release_to_board_m=5.5)
    v = throw_verdict(release(5.0), [], {}, 5.5, settings, observed_score=3,
                      board_phase=phase("fell_in_hole", -15, 0, 15, hang=0.6))
    assert v["outcome"] == "hole"
    assert v["headline"].startswith("In the hole")
    assert "slid 15 in" in v["headline"] and "lip" in v["headline"]
    assert not [i for i in v["items"] if i["kind"] == "fix"]
    assert any("slide was part of the shot" in i["text"] for i in v["items"])


def test_board_bag_advice_is_signed_from_the_measured_end():
    settings = ZoneSettings(release_to_board_m=5.5)
    v = throw_verdict(release(7.0), [], {"calibration": "GOOD"}, 5.5, settings, observed_score=1,
                      board_phase=phase("rest", -20, -9, 11))
    fix = v["items"][0]
    assert fix["kind"] == "fix" and fix["direction"] == "short" and fix["signed_error_in"] == -9
    assert "9 in short of the hole" in fix["text"] and "faster" in fix["text"]
    assert v["headline"].startswith("On the board: 1 point.")


def test_long_board_bag_says_slower():
    v = throw_verdict(release(7.5), [], {"calibration": "GOOD"}, 5.5, ZoneSettings(release_to_board_m=5.5),
                      observed_score=1, board_phase=phase("rest", 0, 6, 6))
    assert v["items"][0]["direction"] == "long" and "slower" in v["items"][0]["text"]


def test_without_an_outcome_the_old_verdict_stands():
    v = throw_verdict(release(7.0), [], {}, 5.5, ZoneSettings(release_to_board_m=5.5))
    assert "outcome" in v and v["outcome"] is None


def test_personal_slide_allowance_needs_three_slides():
    assert personal_slide_allowance([10, 12])[1] == "assumed"
    metres, source, n = personal_slide_allowance([10, 20, 18, 15])
    assert source == "measured_median_slide" and n == 4 and abs(metres - 16.5 * 0.0254) < 1e-9


def test_personal_zone_best_aim_is_at_least_as_good_as_usual():
    import numpy as np
    rng = np.random.default_rng(1)
    rows = [{"bag_release_speed_m_s": 6.6 + 0.3 * rng.standard_normal(), "bag_release_angle_deg": 30 + 3 * rng.standard_normal(),
             "bag_release_height_m": 0.9} for _ in range(12)]
    zone = personal_zone(rows, ZoneSettings(release_to_board_m=5.3), [15, 18, 20], "measured_median")
    assert zone["status"] == "available"
    assert zone["slide_source"] == "measured_median_slide"
    assert zone["best"]["p_green"] >= zone["current"]["p_green"]
    assert zone["angle_limits_deg"][0] <= zone["best"]["angle_deg"] <= zone["angle_limits_deg"][1]
    assert zone["sentence"]


def test_personal_zone_needs_three_measured_throws():
    zone = personal_zone([], ZoneSettings(), [], "settings")
    assert zone["status"] == "needs_throws"
