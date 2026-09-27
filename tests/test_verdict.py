from cornhole_biomech.verdict import throw_verdict, personal_flags, physics_check
from cornhole_biomech.zones import ZoneSettings, speed_to_hole


def metric(value, status="reliable", noise=0.1, label="m", unit=""):
    return {"value": value, "status": status, "noise_floor": noise, "label": label, "unit": unit}


def release(speed, angle=40.0, height=0.9, status="reliable"):
    return {"bag_release_speed_m_s": metric(speed, status, 0.15, "Release speed", "m/s"),
            "bag_release_angle_deg": metric(angle, "reliable", 3.0, "Release angle", "°"),
            "bag_release_height_m": metric(height, status, 0.03, "Release height", "m")}


def test_physics_uses_measured_distance_and_required_speed():
    settings = ZoneSettings()
    p = physics_check(release(7.0), 6.0, settings)
    assert p["distance_source"] == "measured" and p["distance_m"] == 6.0
    need = speed_to_hole(40.0, 0.9, ZoneSettings(release_to_board_m=6.0))
    assert abs(p["required_speed_m_s"] - need) < 1e-6
    assert abs(p["delta_speed_m_s"] - (7.0 - need)) < 1e-6
    assert p["sensitivity_m_per_m_s"] > 0


def test_physics_falls_back_to_assumed_distance():
    p = physics_check(release(8.0), None, ZoneSettings())
    assert p["distance_source"] == "assumed" and p["distance_m"] == 7.7


def test_no_scale_skips_physics():
    v = throw_verdict(release(7.0, status="unreliable"), [], {}, 6.0, ZoneSettings())
    assert v["physics"] is None
    assert "m/s" not in v["headline"]


def test_unreachable_hole():
    p = physics_check(release(2.0, angle=5.0, height=0.3), 6.0, ZoneSettings())
    assert p["required_speed_m_s"] is None or p["landing"] in ("short", "front")
    v = throw_verdict(release(2.0, angle=5.0, height=0.3), [], {}, 6.0, ZoneSettings())
    assert v["headline"]


def test_few_throws_no_personal_flags():
    others = [{"elbow_angle_deg_at_release": metric(150.0, noise=10.0)} for _ in range(4)]
    assert personal_flags({"elbow_angle_deg_at_release": metric(190.0, noise=10.0)}, others) == []


def test_personal_flag_needs_noise_and_spread():
    others = [{"elbow_angle_deg_at_release": metric(v, noise=10.0)} for v in (148, 150, 151, 152, 150, 149)]
    flags = personal_flags({"elbow_angle_deg_at_release": metric(175.0, noise=10.0)}, others)
    assert flags and flags[0]["key"] == "elbow_angle_deg_at_release" and flags[0]["direction"] == "high"
    assert personal_flags({"elbow_angle_deg_at_release": metric(156.0, noise=10.0)}, others) == []


def test_fix_item_names_speed_when_speed_is_off():
    settings = ZoneSettings()
    need = speed_to_hole(40.0, 0.9, ZoneSettings(release_to_board_m=6.0))
    v = throw_verdict(release(need + 0.8), [], {"calibration": "WARNING"}, 6.0, settings)
    fixes = [i for i in v["items"] if i["kind"] == "fix"]
    assert fixes and fixes[0]["metric_key"] == "bag_release_speed_m_s"
    assert any(i["kind"] == "note" for i in v["items"])      # WARNING grade becomes a data note
    assert "long" in v["headline"] or "past" in v["headline"]


def test_physics_uses_athlete_median_when_throw_unmeasured():
    settings = ZoneSettings()
    p = physics_check(release(7.0), None, settings, athlete_median_m=6.2)
    assert p["distance_source"] == "athlete_median" and p["distance_m"] == 6.2


def test_physics_assumed_distance_both_none():
    p = physics_check(release(8.0), None, ZoneSettings(), athlete_median_m=None)
    assert p["distance_source"] == "assumed" and p["distance_m"] == 7.7


def test_release_angle_flag_is_fix_when_physics_exists():
    others = [{"bag_release_angle_deg": metric(v, noise=3.0)} for v in (38, 39, 40, 41, 40)]
    others.extend([{"bag_release_angle_deg": metric(40.0)} for _ in range(1)])  # 6 total
    v = throw_verdict(release(7.0, angle=55.0), others, {}, 6.0, ZoneSettings())
    angle_items = [i for i in v["items"] if i["metric_key"] == "bag_release_angle_deg"]
    assert angle_items and angle_items[0]["kind"] == "fix"


def test_fmt_range_negative_degrees():
    from cornhole_biomech.verdict import _fmt_range
    s = _fmt_range(-99, -85, "°")
    assert s == "−99 to −85°"


def test_fmt_range_multi_word_unit():
    from cornhole_biomech.verdict import _fmt_range
    s = _fmt_range(1.3, 1.7, "back ÷ forward")
    assert s == "1.3–1.7 back ÷ forward"


def test_release_speed_flag_is_note_when_physics_exists():
    others = [{"bag_release_speed_m_s": metric(v, noise=0.15)} for v in (7.0, 7.2, 7.1, 7.3, 7.0)]
    others.extend([{"bag_release_speed_m_s": metric(7.1)} for _ in range(1)])  # 6 total
    v = throw_verdict(release(8.5), others, {}, 6.0, ZoneSettings())
    speed_items = [i for i in v["items"] if i["metric_key"] == "bag_release_speed_m_s" and "Unusual for this athlete" in i["text"]]
    assert speed_items and speed_items[0]["kind"] == "note"


def test_release_angle_not_dropped_by_body_flags():
    others = [{"bag_release_angle_deg": metric(v, noise=3.0)} for v in (38, 39, 40, 41, 40, 39)]
    others.extend([{"elbow_angle_deg_at_release": metric(v, noise=10.0)} for v in (145, 150, 148, 152, 150, 149)])
    others.extend([{"trunk_inclination_deg_at_release": metric(v, noise=5.0)} for v in (25, 26, 27, 28, 26, 27)])
    others.extend([{"wrist_peak_speed_arm_lengths_s": metric(v, noise=0.5)} for v in (3.2, 3.3, 3.1, 3.4, 3.2, 3.3)])
    v = throw_verdict(release(7.0, angle=55.0, height=1.2), others, {}, 6.0, ZoneSettings())
    angle_items = [i for i in v["items"] if i["metric_key"] == "bag_release_angle_deg"]
    assert angle_items and angle_items[0]["kind"] == "fix", "Angle flag should be present with kind fix"


def test_headline_counts_only_named_flags():
    # An exploratory flag (no plain-language description) must not be counted in the headline.
    key_x = "elbow_peak_extension_velocity_deg_s"
    others = [{key_x: {**metric(v, noise=150.0), "exploratory": True}} for v in (900, 950, 1000, 1050, 1000, 980)]
    this = {key_x: {**metric(2200.0, noise=150.0), "exploratory": True}}
    assert personal_flags(this, others)  # it is flagged ...
    v = throw_verdict(this, others, {}, None, ZoneSettings())
    assert "differed" not in v["headline"]  # ... but not announced without being named
    # A nameable flag is both counted and written as an item.
    others2 = [{"elbow_angle_deg_at_release": metric(x, noise=10.0), key_x: {**metric(1000.0, noise=150.0), "exploratory": True}}
               for x in (148, 150, 151, 152, 150, 149)]
    this2 = {"elbow_angle_deg_at_release": metric(175.0, noise=10.0), key_x: {**metric(2200.0, noise=150.0), "exploratory": True}}
    v2 = throw_verdict(this2, others2, {}, None, ZoneSettings())
    assert "in 1 measured variable." in v2["headline"]
    named = [i for i in v2["items"] if "Unusual for this athlete" in i["text"]]
    assert [i["metric_key"] for i in named] == ["elbow_angle_deg_at_release"]


def test_usual_range_needs_a_real_comparison():
    # Six other throws, but none has a usable value for the measured key: nothing was compared.
    others = [{"elbow_angle_deg_at_release": metric(None, status="unavailable")} for _ in range(6)]
    v = throw_verdict({"elbow_angle_deg_at_release": metric(150.0, noise=10.0)}, others, {}, None, ZoneSettings())
    assert "within this athlete's usual range" not in v["headline"]
    assert "more analyzed throws" in v["headline"]
    # With five usable history values it is a genuine comparison.
    others = [{"elbow_angle_deg_at_release": metric(x, noise=10.0)} for x in (148, 150, 151, 152, 150)]
    v = throw_verdict({"elbow_angle_deg_at_release": metric(150.0, noise=10.0)}, others, {}, None, ZoneSettings())
    assert v["headline"] == "Every reliable measurement was within this athlete's usual range."


def test_more_throws_needed_grammar():
    others = [{} for _ in range(4)]
    v = throw_verdict({"elbow_angle_deg_at_release": metric(150.0)}, others, {}, None, ZoneSettings())
    assert "1 more analyzed throw is needed" in v["headline"]
    v = throw_verdict({"elbow_angle_deg_at_release": metric(150.0)}, [], {}, None, ZoneSettings())
    assert "5 more analyzed throws are needed" in v["headline"]


def test_fmt_uses_unicode_minus():
    from cornhole_biomech.verdict import _fmt
    assert _fmt(-12.0, "°") == "−12°"
    assert _fmt(-0.25, "m") == "−0.25 m"
    assert _fmt(1.5, "back ÷ forward") == "1.5 back ÷ forward"
