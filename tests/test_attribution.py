"""Miss attribution (attribution.py): additive parts, naming rule, drivers, bandwidth gate and the v2 sentence."""
from __future__ import annotations

import itertools
import json
import math
import random
import re
import sys
from pathlib import Path

from cornhole_biomech import attribution as at
from cornhole_biomech import two_view as tv
from cornhole_biomech.regulation import INCH_M, Board

sys.path.insert(0, str(Path(__file__).resolve().parent))
from swift_contract import problems  # noqa: E402

RELEASE_M = 6.5          # release → board front (m)
BANNED = re.compile(r"\b(because|caused|fault|should)\b", re.IGNORECASE)


def _run_m(contact_y_in: float) -> float:
    return RELEASE_M + contact_y_in * INCH_M * math.cos(Board().angle)


def _line_x(psi_deg: float, x0_m: float, contact_y_in: float) -> float:
    """Board x (in) where a launch from x0 at ψ meets the deck at contact_y."""
    return 12.0 + (x0_m + _run_m(contact_y_in) * math.tan(math.radians(psi_deg))) / INCH_M


def _record(category="onBoard", contact=(12.0, 30.0), rest=(12.0, 39.0), x0_m=0.0, psi=0.0, source="heading",
            rest_on=None, flight_status="measured"):
    landing = {"contact": None if contact is None else {"x_in": contact[0], "y_in": contact[1]},
               "rest": None if rest is None else {
                   "x_in": rest[0], "y_in": rest[1],
                   "on": rest_on or {"throughHole": "hole", "onBoard": "board"}.get(category, "floor")}}
    record = {"status": "measured", "result": {"category": category}, "landing": landing,
              "miss": tv.miss_vector(landing), "heading": {}, "frontal": {}}
    if psi is not None and source == "heading":
        record["heading"] = {"status": "measured", "deg": psi, "release_offset_m": x0_m}
    elif psi is not None and source == "flight":
        record["flight_3d"] = {"status": flight_status, "lateral_launch_angle_deg": psi,
                               "release": {"lateral_m": x0_m, "to_board_front_m": RELEASE_M}}
    return record


def _results(speed=9.0, angle=40.0, speed_status="reliable"):
    return {"summaries": {"bag_release_speed_m_s": speed, "bag_release_angle_deg": angle,
                          "release_to_board_front_m": RELEASE_M},
            "coach_metrics": {"bag_release_speed_m_s": {"value": speed, "status": speed_status},
                              "bag_release_angle_deg": {"value": angle, "status": "reliable"}}}


def _siblings(n=12, seed=1, contact_y=30.0, slide=9.0, speed=9.0, x0_m=0.0, psi=0.0, spread=2.0, source="heading",
              lateral_spread=None):
    """n ordinary throws around a usual group: contact 30 in up the deck, slide 9 in (rest 39 in = on the hole's
    line), release at x0 and launched at ψ so they land on the centre line, speed 9 m/s."""
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        cy = contact_y + rng.uniform(-spread, spread)
        sl = slide + rng.uniform(-spread, spread)
        cx = _line_x(psi, x0_m, cy) + rng.uniform(-1, 1) * (spread if lateral_spread is None else lateral_spread)
        rx = cx + rng.uniform(-0.5, 0.5)
        out.append((_record(contact=(cx, cy), rest=(rx, cy + sl), x0_m=x0_m, psi=psi, source=source),
                    _results(speed=speed + rng.uniform(-0.05, 0.05))))
    return out


def _comp(att, axis, key):
    return next(c for c in att[axis]["components"] if c["key"] == key)


def _driver(att, key):
    return next(d for d in att["drivers"] if d["key"] == key)


def _named(att):
    return [c for axis in ("lateral", "depth") for c in ((att.get(axis) or {}).get("components") or []) if c["named"]]


def test_lateral_parts_add_up_to_the_miss():
    record = _record(contact=(20.0, 30.0), rest=(22.0, 38.0), x0_m=0.05, psi=1.0)
    att = at.attribute(record, _results(), release_distance_m=RELEASE_M)
    lat = att["lateral"]
    parts = {c["key"]: c["in"] for c in lat["components"]}
    assert lat["miss_in"] == 10.0
    assert parts["release_position"] == round(0.05 / INCH_M, 2)
    assert abs(parts["aim"] - _run_m(30.0) * math.tan(math.radians(1.0)) / INCH_M) < 0.01
    assert parts["slide_drift"] == 2.0
    assert abs(lat["residual_in"] - (10.0 - sum(parts.values()))) < 0.02
    # Through the heading (drawn through the contact) the identity closes exactly.
    psi = math.degrees(math.atan2((20.0 - 12.0) * INCH_M - 0.05, _run_m(30.0)))
    exact = at.attribute(_record(contact=(20.0, 30.0), rest=(22.0, 38.0), x0_m=0.05, psi=psi), _results(),
                         release_distance_m=RELEASE_M)
    assert abs(exact["lateral"]["residual_in"]) < 0.02


def test_the_3d_flight_is_used_before_the_heading():
    record = _record(contact=(18.0, 30.0), rest=(18.0, 38.0), x0_m=0.0, psi=1.2, source="flight")
    record["heading"] = {"status": "measured", "deg": -3.0, "release_offset_m": 0.2}
    att = at.attribute(record, _results(), release_distance_m=None)
    aim = _comp(att, "lateral", "aim")
    assert aim["source"] == "flight_3d" and aim["angle_deg"] == 1.2 and aim["in"] > 0
    assert _comp(att, "lateral", "release_position")["in"] == 0.0
    # A rejected 3D flight falls back to the release hand + heading.
    record["flight_3d"]["status"] = "unavailable"
    fallback = at.attribute(record, _results(), release_distance_m=RELEASE_M)
    assert _comp(fallback, "lateral", "aim")["source"] == "heading"
    assert _comp(fallback, "lateral", "release_position")["in"] == round(0.2 / INCH_M, 2)
    # An estimated 3D flight makes the block estimated.
    record["flight_3d"]["status"] = "estimated"
    assert at.attribute(record, _results(), release_distance_m=None)["status"] == "estimated"


def test_a_heading_without_the_release_hand_is_not_used():
    record = _record(contact=(18.0, 30.0), rest=(18.0, 38.0))
    record["heading"] = {"status": "estimated", "deg": 1.0, "release_offset_m": None}
    att = at.attribute(record, _results(), release_distance_m=RELEASE_M)
    assert _comp(att, "lateral", "aim")["in"] is None and _comp(att, "lateral", "release_position")["in"] is None
    assert att["lateral"]["residual_in"] is None and "launch direction were not measured" in att["reason"]


def test_missing_parts_stay_missing():
    att = at.attribute(_record(contact=None, rest=(20.0, 44.0), psi=None), _results())
    lat, dep = att["lateral"], att["depth"]
    assert all(c["in"] is None for c in lat["components"]) and lat["residual_in"] is None
    assert all(c["in"] is None for c in dep["components"]) and dep["residual_in"] is None
    assert lat["miss_in"] == 8.0 and dep["miss_in"] == 5.0
    assert att["reason"] and not _named(att)
    assert _driver(att, "launch_direction")["value"] is None


def test_depth_parts_are_against_the_athletes_usual_and_add_up():
    record = _record(contact=(12.0, 20.0), rest=(12.5, 29.0))
    att = at.attribute(record, _results(), siblings=_siblings(), release_distance_m=RELEASE_M)
    dep = att["depth"]
    assert dep["reference"] == "usual" and dep["miss_in"] == -10.0 and att["usual"]["throws"] == 12
    keys = [c["key"] for c in dep["components"]]
    assert keys == ["usual_spot", "carry", "slide"]
    assert abs(sum(c["in"] for c in dep["components"]) - dep["miss_in"]) < 0.05 and abs(dep["residual_in"]) < 0.05
    carry = _comp(att, "depth", "carry")
    assert abs(carry["in"] - (20.0 - 39.0 - carry["usual_in"])) < 0.02 and carry["named"]
    assert _comp(att, "depth", "usual_spot")["noise_in"] is None and not _comp(att, "depth", "usual_spot")["named"]


def test_without_eight_other_throws_there_is_no_usual_and_no_gate():
    record = _record(contact=(12.0, 20.0), rest=(12.5, 29.0))
    att = at.attribute(record, _results(), siblings=_siblings(n=7), release_distance_m=RELEASE_M)
    usual = att["usual"]
    assert usual["throws"] == 7 and usual["spread_depth_in"] is None and usual["centre_depth_in"] is None
    assert usual["reason"] and att["within_usual_spread"] is None
    assert att["depth"]["reference"] == "hole"
    assert all(d["usual"] is None and d["delta"] is None and not d["named"] for d in att["drivers"])
    carry = _comp(att, "depth", "carry")
    assert carry["in"] == -19.0 and carry["named"]           # 19 in short of the hole
    assert "landed 19 in short of the hole" in att["sentence"]
    assert att["cue"] == "Next: throw a touch harder."         # no gate without a usual


def test_the_throw_itself_is_not_part_of_its_usual(tmp_path):
    analyses = tmp_path / "analyses"
    for i, (record, results) in enumerate(_siblings(n=8)):
        folder = analyses / f"Throw-{i}"
        folder.mkdir(parents=True)
        (folder / "two_view.json").write_text(json.dumps(record))
        (folder / "results.json").write_text(json.dumps(results))
    me = analyses / "Throw-0"
    assert len(at.sibling_records(me)) == 7
    att = at.attribution_for_analysis(me)
    assert att["usual"]["throws"] == 7 and att["usual"]["spread_lateral_in"] is None


def test_sibling_records_skip_throws_without_a_front_camera_result(tmp_path):
    analyses = tmp_path / "analyses"
    for name, status in (("Throw-A", "measured"), ("Throw-B", "measured"), ("Throw-C", "unavailable"), ("Throw-D", None)):
        folder = analyses / name
        folder.mkdir(parents=True)
        if status is not None:
            (folder / "two_view.json").write_text(json.dumps({"status": status}))
        (folder / "results.json").write_text("{}")
    pairs = at.sibling_records(analyses / "Throw-A")
    assert len(pairs) == 1 and pairs[0][0]["status"] == "measured"


def test_naming_rule_noise_size_share_and_sign():
    # 2.5 in of drift on a 10 in right miss: under 3 in.
    small = at.attribute(_record(contact=(19.5, 30.0), rest=(22.0, 39.0), psi=None), _results())
    assert not _comp(small, "lateral", "slide_drift")["named"]
    # 4 in of drift on a 12 in right miss: above noise and 3 in, but 33 % of the miss.
    share = at.attribute(_record(contact=(20.0, 30.0), rest=(24.0, 39.0), psi=None), _results())
    assert not _comp(share, "lateral", "slide_drift")["named"]
    # 6 in of drift on a 10 in right miss: named, 60 %.
    named = at.attribute(_record(contact=(16.0, 30.0), rest=(22.0, 39.0), psi=None), _results())
    drift = _comp(named, "lateral", "slide_drift")
    assert drift["named"] and drift["share"] == 0.6
    # Drift to the left on a right miss: never named, whatever its size.
    opposite = at.attribute(_record(contact=(30.0, 30.0), rest=(20.0, 39.0), psi=None), _results())
    assert not _comp(opposite, "lateral", "slide_drift")["named"]
    # An axis within the hole radius names nothing.
    close = at.attribute(_record(contact=(8.0, 30.0), rest=(14.0, 39.0), psi=None), _results())
    assert not _comp(close, "lateral", "slide_drift")["named"]


def test_noise_scales_the_aim_with_distance():
    att = at.attribute(_record(contact=(14.0, 30.0), rest=(14.0, 39.0), psi=0.3), _results(), release_distance_m=RELEASE_M)
    aim = _comp(att, "lateral", "aim")
    expected = _run_m(30.0) * math.tan(math.radians(at.LAUNCH_DIRECTION_NOISE_DEG)) / INCH_M
    assert abs(aim["noise_in"] - expected) < 0.01 and 2.0 < aim["noise_in"] < 3.0     # ≈ 2.4 in at ~7.1 m
    assert _comp(att, "lateral", "release_position")["noise_in"] == round(0.03 / INCH_M, 2)


def test_at_most_two_parts_are_named():
    rng = random.Random(3)
    for _ in range(200):
        record = _record(contact=(rng.uniform(-5, 30), rng.uniform(5, 45)), rest=(rng.uniform(-20, 45), rng.uniform(0, 70)),
                         x0_m=rng.uniform(-0.2, 0.2), psi=rng.uniform(-4, 4))
        att = at.attribute(record, _results(speed=rng.uniform(8, 10)), siblings=_siblings(spread=1.0),
                           release_distance_m=RELEASE_M)
        assert len(_named(att)) <= at.MAX_NAMED


def test_release_position_is_named_only_as_a_change_from_the_usual():
    # Releasing 8 in right and aiming back: on its own the offset never explains a miss.
    psi = math.degrees(math.atan2((22.0 - 12.0) * INCH_M - 0.2, _run_m(30.0)))
    record = _record(contact=(22.0, 30.0), rest=(22.0, 39.0), x0_m=0.2, psi=psi)
    alone = at.attribute(record, _results(), release_distance_m=RELEASE_M)
    assert not _comp(alone, "lateral", "release_position")["named"]
    same = at.attribute(record, _results(), siblings=_siblings(x0_m=0.2, psi=-1.6), release_distance_m=RELEASE_M)
    assert abs(_comp(same, "lateral", "release_position")["vs_usual_in"]) < 0.01
    assert not _comp(same, "lateral", "release_position")["named"]
    # The same throw from an athlete who usually releases 10 in further left: the move is named.
    moved = at.attribute(record, _results(), siblings=_siblings(x0_m=-0.05, psi=0.44), release_distance_m=RELEASE_M)
    rp = _comp(moved, "lateral", "release_position")
    assert rp["named"] and rp["basis"] == "usual" and rp["vs_usual_in"] > 9


def test_speed_is_named_only_with_a_named_carry_of_the_same_sign():
    record = _record(contact=(12.0, 18.0), rest=(12.0, 27.0))
    slower = at.attribute(record, _results(speed=8.7), siblings=_siblings(), release_distance_m=RELEASE_M)
    speed = _driver(slower, "release_speed")
    assert speed["named"] and speed["implied_in"] < 0 and slower["tier"] == "physics"
    assert "about 0.3 m/s slower release" in slower["sentence"]
    faster = at.attribute(record, _results(speed=9.3), siblings=_siblings(), release_distance_m=RELEASE_M)
    assert not _driver(faster, "release_speed")["named"] and faster["tier"] == "geometry"      # sign disagrees
    tiny = at.attribute(record, _results(speed=8.9), siblings=_siblings(), release_distance_m=RELEASE_M)
    assert not _driver(tiny, "release_speed")["named"]                                          # under 0.15 m/s
    # Speed alone never names itself: a carry within noise keeps it quiet.
    near = at.attribute(_record(contact=(12.0, 29.0), rest=(12.0, 38.0)), _results(speed=8.5),
                        siblings=_siblings(spread=0.5), release_distance_m=RELEASE_M)
    assert not _driver(near, "release_speed")["named"]


def test_release_angle_is_never_named():
    record = _record(contact=(12.0, 18.0), rest=(12.0, 27.0))
    for angle in (25.0, 32.0, 48.0, 55.0):
        att = at.attribute(record, _results(angle=angle), siblings=_siblings(), release_distance_m=RELEASE_M)
        assert not _driver(att, "release_angle")["named"] and "angle" not in att["sentence"]


def test_withheld_release_values_stay_missing():
    results = _results(speed=8.0)
    results["coach_metrics"]["bag_release_speed_m_s"]["status"] = "unreliable"
    att = at.attribute(_record(contact=(12.0, 18.0), rest=(12.0, 27.0)), results, siblings=_siblings(),
                       release_distance_m=RELEASE_M)
    speed = _driver(att, "release_speed")
    assert speed["value"] is None and speed["delta"] is None and not speed["named"]


def test_a_miss_inside_the_usual_spread_names_nothing_and_gets_no_cue():
    record = _record(contact=(13.0, 28.0), rest=(13.5, 35.0))
    att = at.attribute(record, _results(), siblings=_siblings(spread=4.0), release_distance_m=RELEASE_M)
    assert att["within_usual_spread"] is True and att["tier"] == "within_spread"
    assert att["cue"] is None and att["sentence"].endswith("Normal spread: keep the same throw.")
    assert not _named(att) and not any(d["named"] for d in att["drivers"])
    outside = at.attribute(_record(contact=(12.0, 18.0), rest=(12.0, 27.0)), _results(),
                           siblings=_siblings(spread=4.0), release_distance_m=RELEASE_M)
    assert outside["within_usual_spread"] is False and outside["cue"] == "Next: throw a touch harder."
    assert outside["sentence"].endswith(outside["cue"])


def test_the_cue_needs_the_named_axis_outside_the_spread():
    # A larger short (carry) inside a wide depth group and a smaller right (aim) outside a tight lateral group:
    # the sentence speaks about the axis outside the spread, and only that one gets a cue.
    psi = 1.5
    x = _line_x(psi, 0.0, 16.0)
    siblings = _siblings(spread=12.0, lateral_spread=1.0)
    att = at.attribute(_record(contact=(x, 16.0), rest=(x, 27.0), psi=psi), _results(), siblings=siblings,
                       release_distance_m=RELEASE_M)
    assert att["inside_spread"] == {"lateral": False, "depth": True}
    assert _comp(att, "depth", "carry")["named"] and _comp(att, "lateral", "aim")["named"]
    assert "of the right came from aim" in att["sentence"] and att["cue"].startswith("Next: aim about")


def test_a_hole_names_nothing():
    att = at.attribute(_record("throughHole", contact=(14.0, 33.0), rest=(12.0, 39.0)), _results(speed=8.0),
                       siblings=_siblings(), release_distance_m=RELEASE_M)
    assert att["sentence"] == "In the hole. Nothing to change." and att["cue"] is None
    assert att["lateral"]["components"] == [] and att["depth"]["components"] == []
    assert not any(d["named"] for d in att["drivers"])
    assert tv.explain({}, {}, att)["kind"] == "made"


def test_off_board_with_unknown_rest_is_partial_with_reasons_and_nulls():
    record = _record("offBoard", contact=None, rest=None, x0_m=0.0, psi=-2.0)
    att = at.attribute(record, _results(), siblings=_siblings(), release_distance_m=RELEASE_M)
    assert att["status"] == "partial" and att["reasons"] and att["reason"]
    assert att["lateral"]["miss_in"] is None and att["depth"]["miss_in"] is None
    assert att["lateral"]["residual_in"] is None and att["within_usual_spread"] is None
    assert not _named(att) and att["cue"] is None
    assert att["sentence"] == ("Off the board: where it stopped was out of the cameras' view. "
                               "It was launched about 2° left of your usual line.")
    assert tv.explain({}, {}, att)["kind"] == "miss"


def test_an_unknown_result_points_to_the_video():
    record = {"status": "measured", "result": {"category": None, "reason": "The side camera saw the bag hit the floor first."}}
    att = at.attribute(record, {})
    assert att["status"] == "unavailable" and att["sentence"].endswith("Check the video.") and att["cue"] is None
    assert tv.explain({}, {}, att)["kind"] == "unknown"


def test_sentence_rounding_and_format():
    att = at.attribute(_record(contact=(19.6, 30.0), rest=(21.4, 26.4), psi=1.37), _results(),
                       siblings=_siblings(), release_distance_m=RELEASE_M)
    assert att["sentence"].startswith("Board: 13 in short, 9 in right.")
    assert not re.search(r"\d+\.\d+ in\b", att["sentence"]) and not re.search(r"\d+\.\d+°", att["sentence"])
    slower = at.attribute(_record(contact=(12.0, 18.0), rest=(12.0, 27.0)), _results(speed=8.737),
                          siblings=_siblings(), release_distance_m=RELEASE_M)
    assert re.search(r"about \d\.\d m/s slower", slower["sentence"])


def test_aim_against_the_usual_names_the_launch_direction():
    psi = 2.0
    x = _line_x(psi, 0.0, 30.0)
    att = at.attribute(_record(contact=(x, 30.0), rest=(x, 39.0), psi=psi), _results(), siblings=_siblings(),
                       release_distance_m=RELEASE_M)
    aim, direction = _comp(att, "lateral", "aim"), _driver(att, "launch_direction")
    assert aim["named"] and aim["basis"] == "usual" and direction["named"] and direction["delta"] == 2.0
    assert att["tier"] == "physics"
    assert "Most of the right came from aim (launched about 2° right of your usual line)." in att["sentence"]
    assert att["cue"] == f"Next: aim about {round(aim['test_in'])} in further left."


def test_aim_without_a_usual_is_measured_against_the_hole():
    psi = 2.0
    x = _line_x(psi, 0.0, 30.0)
    att = at.attribute(_record(contact=(x, 30.0), rest=(x, 39.0), psi=psi), _results(), release_distance_m=RELEASE_M)
    aim = _comp(att, "lateral", "aim")
    assert aim["named"] and aim["basis"] == "line_to_hole"
    assert "aim (launched about 2° right of the hole)" in att["sentence"] and att["tier"] == "geometry"


def test_a_named_slide_gets_no_cue():
    att = at.attribute(_record(contact=(12.0, 30.0), rest=(12.0, 55.0)), _results(), siblings=_siblings(),
                       release_distance_m=RELEASE_M)
    assert "came from the slide (it slid 16 in further than usual)" in att["sentence"]
    assert att["cue"] is None and att["within_usual_spread"] is False


def test_banned_words_never_appear_in_any_sentence_or_cue():
    sibling_sets = [[], _siblings(n=5), _siblings(spread=1.0), _siblings(spread=6.0, x0_m=0.15, psi=-1.2),
                    _siblings(source="flight")]
    reasons = ["Needs confirmation.", "The side camera saw the bag hit the floor first, never the board.",
               "This should be checked because the fault caused it."]
    rng = random.Random(7)
    count = 0
    for category, siblings, source in itertools.product(("onBoard", "offBoard", "throughHole", None),
                                                         sibling_sets, ("heading", "flight", None)):
        for _ in range(30):
            contact = None if rng.random() < 0.15 else (rng.uniform(-10, 34), rng.uniform(-5, 50))
            rest = None if rng.random() < 0.15 else (rng.uniform(-30, 54), rng.uniform(-10, 80))
            record = _record(category or "onBoard", contact=contact, rest=rest, x0_m=rng.uniform(-0.2, 0.2),
                             psi=None if source is None else rng.uniform(-5, 5), source=source or "heading")
            if category is None:
                record["result"] = {"category": None, "reason": rng.choice(reasons)}
            att = at.attribute(record, _results(speed=rng.uniform(7.5, 10.5), angle=rng.uniform(25, 55)),
                               siblings=siblings, release_distance_m=RELEASE_M)
            for text in (att["sentence"], att["cue"] or ""):
                assert not BANNED.search(text), text
                assert "nan" not in text.lower().split() and "None" not in text and "%" not in text
            assert att["sentence"] and att["sentence"].endswith(".")
            assert len(_named(att)) <= at.MAX_NAMED
            for axis in ("lateral", "depth"):
                block = att[axis] or {}
                for c in block.get("components") or []:
                    if c["named"]:
                        assert c["test_in"] * block["miss_in"] > 0          # named parts point the same way
                        assert abs(c["test_in"]) >= max(at.NAME_MIN_IN, 2 * c["test_noise_in"])
            if att["within_usual_spread"]:
                assert att["cue"] is None and att["tier"] == "within_spread"
            if category == "throughHole":
                assert att["sentence"] == "In the hole. Nothing to change."
            count += 1
    assert count == 4 * 5 * 3 * 30


def test_two_view_keeps_the_app_contract():
    record = _record(contact=(12.0, 18.0), rest=(12.0, 27.0))
    record["attribution"] = at.attribute(record, _results(), siblings=_siblings(), release_distance_m=RELEASE_M)
    record["explanation"] = tv.explain(record, _results(), record["attribution"])
    assert set(record["explanation"]) >= {"sentence", "kind", "parts", "cue", "tier"}
    assert record["explanation"]["sentence"] == record["attribution"]["sentence"]
    assert problems("TwoViewDocument", json.loads(json.dumps(record))) == []


def test_a_failed_attribution_still_gives_the_outcome_sentence(tmp_path, monkeypatch):
    def broken(*args, **kwargs):
        raise ValueError("boom")
    monkeypatch.setattr(at, "attribute", broken)
    record = _record(contact=(12.0, 18.0), rest=(12.0, 27.0))
    block = tv.attribution_for_record(tmp_path, record, _results(), RELEASE_M)
    assert block["status"] == "unavailable" and "ValueError" in block["reason"]
    assert block["sentence"] == "Board: 12 in short, on line. No single measured part stands out." and block["cue"] is None


def test_sibling_records_skip_throws_from_another_method_version(tmp_path):
    analyses = tmp_path / "analyses"
    for name, version in (("Throw-A", "v2"), ("Throw-B", "v2"), ("Throw-C", "v1"), ("Throw-D", None)):
        folder = analyses / name
        folder.mkdir(parents=True)
        (folder / "two_view.json").write_text(json.dumps({"status": "measured"}))
        (folder / "results.json").write_text("{}")
        if version is not None:
            (folder / "manifest.json").write_text(json.dumps({"method_version": version}))
    assert len(at.sibling_records(analyses / "Throw-A")) == 1          # B only: C is v1, D has no manifest
    assert len(at.sibling_records(analyses / "Throw-D")) == 3          # no own manifest: nothing excluded


def test_carry_sensitivity_is_the_deck_contact_derivative_not_the_flat_ground_one():
    """Drag-free flight onto the 10.8° deck at the pilot median release (d 5.68 m, h 1.0 m, 40.6°, 7.49 m/s):
    ≈ 1.33 m of first contact per m/s (flat ground would give 2R/v ≈ 1.8), so 0.15 m/s ≈ 7.9 in, not 10.6 in."""
    s = at.carry_sensitivity(7.49, 40.6, 1.0, 5.68)
    assert abs(s["m_per_m_s"] - 1.33) < 0.02
    assert 7.0 < 0.15 * s["m_per_m_s"] / INCH_M < 9.0
    flat = at.carry_sensitivity(7.0, 28.0, 1.0, 5.0)["m_per_deg"]           # flatter release: angle matters more
    assert flat is not None and abs(flat) > 3 * abs(s["m_per_deg"])
    assert at.carry_sensitivity(None, 40.0, 1.0, 5.68) == {"m_per_m_s": None, "m_per_deg": None}


def test_four_part_explanation_separates_flight_from_after_landing():
    record = _record(contact=(12.0, 18.0), rest=(12.0, 27.0))
    slower = at.attribute(record, _results(speed=8.7), siblings=_siblings(), release_distance_m=RELEASE_M)["explanation"]
    assert slower["phase"] == "flight" and slower["observed"].startswith("Stopped on the board, 12 in short")
    assert "m/s lower than usual" in slower["possible_explanation"]
    assert "swing length and tempo" in slower["suggestion"]
    slide = at.attribute(_record(contact=(12.0, 30.0), rest=(12.0, 55.0)), _results(), siblings=_siblings(),
                         release_distance_m=RELEASE_M)["explanation"]
    assert slide["phase"] == "after_landing" and "after landing" in slide["possible_explanation"]
    # A carry with no release difference beyond noise is not given a release explanation.
    unexplained = at.attribute(record, _results(speed=9.0), siblings=_siblings(), release_distance_m=RELEASE_M)
    assert "does not account for it" in unexplained["explanation"]["possible_explanation"]
    made = at.attribute(_record(category="throughHole", contact=(12, 36), rest=(12, 39)), _results(),
                        siblings=_siblings(), release_distance_m=RELEASE_M)["explanation"]
    assert made["observed"] == "In the hole." and made["possible_explanation"] is None


def test_front_view_body_difference_is_evidence_not_a_named_part():
    psi = 2.0
    x = _line_x(psi, 0.0, 30.0)
    siblings = _siblings()
    for record, _ in siblings:
        record["frontal"] = {"arm_across_body_sw": {"value": 0.10, "status": "measured"}}
    me = _record(contact=(x, 30.0), rest=(x, 39.0), psi=psi)
    me["frontal"] = {"arm_across_body_sw": {"value": 0.50, "status": "measured"}}
    att = at.attribute(me, _results(), siblings=siblings, release_distance_m=RELEASE_M)
    arm = next(b for b in att["body_evidence"] if b["key"] == "arm_across_body_sw")
    assert arm["delta"] == 0.4 and arm["beyond_noise"] is True
    assert any(e.startswith("Front view: hand across the body") for e in att["explanation"]["evidence"])
    assert "further across the body than usual (+0.40 shoulder widths)" in att["explanation"]["suggestion"]
    unmeasured = next(b for b in at.attribute(_record(), _results(), siblings=siblings)["body_evidence"]
                      if b["key"] == "arm_across_body_sw")
    assert unmeasured["value"] is None and unmeasured["beyond_noise"] is None       # missing stays missing


def test_near_miss_inside_the_hole_radius_is_not_explained():
    att = at.attribute(_record(contact=(13.0, 20.0), rest=(14.0, 37.0)), _results(), release_distance_m=RELEASE_M)
    assert "near miss" in att["explanation"]["possible_explanation"] and att["explanation"]["suggestion"] is None


def test_offsetting_release_changes_are_reported_not_called_unchanged():
    """A short carry while release speed was faster and the angle flatter than usual: the explanation must report
    both changes and their net drag-free carry, and no 'throw harder' cue contradicts the faster release."""
    record = _record(contact=(12.0, 18.0), rest=(12.0, 27.0))
    att = at.attribute(record, _results(speed=9.25, angle=34.0), siblings=_siblings(), release_distance_m=RELEASE_M)
    e = att["explanation"]
    assert "release speed (about" in e["possible_explanation"] and "does not account for it" in e["possible_explanation"]
    assert "did not differ beyond their noise" not in e["possible_explanation"]
    assert att["cue"] is None and "harder" not in att["sentence"]
    assert e["observed_detail"].startswith("First contact")
