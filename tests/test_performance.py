"""Within-athlete scored-vs-miss summaries and plain-language feedback."""
import numpy as np
import pytest

from cornhole_biomech.performance import (
    cliffs_delta,
    compare_throws,
    group_label,
    hedges_g,
    performance_summary,
)


def rows_with(angle_scored, angle_missed, extra=None):
    rows = []
    for i, a in enumerate(angle_scored):
        rows.append({"trial_id": f"s{i}", "score_category": 3 if i % 2 else 1, "bag_release_angle_deg": a,
                     "bag_release_angle_se_deg": 0.5, **(extra or {})})
    for i, a in enumerate(angle_missed):
        rows.append({"trial_id": f"m{i}", "score_category": 0, "bag_release_angle_deg": a,
                     "bag_release_angle_se_deg": 0.5, **(extra or {})})
    return rows


def test_cliffs_delta_extremes_and_ties():
    assert cliffs_delta([3, 4, 5], [0, 1, 2]) == 1.0
    assert cliffs_delta([0, 1], [5, 6]) == -1.0
    assert cliffs_delta([1, 2], [1, 2]) == 0.0


def test_hedges_g_small_sample_correction():
    g = hedges_g([1.0, 2.0, 3.0], [4.0, 5.0, 6.0])
    # d = -3 / 1 = -3; J = 1 - 3/(4*6-9) = 0.8
    assert g == pytest.approx(-2.4)


def test_success_definition_scored_versus_miss_and_unknown_excluded():
    assert group_label(3) == "scored" and group_label(1) == "scored"
    assert group_label(0) == "miss" and group_label(None) is None


def test_clear_separation_produces_level_two_and_three_feedback():
    rows = rows_with([35, 36, 34, 37, 35, 36], [27, 26, 28, 25, 29])
    labels = {r["trial_id"]: f"Throw {i + 1}" for i, r in enumerate(rows)}
    s = performance_summary(rows, labels)
    angle = s["variables"]["bag_release_angle_deg"]
    assert angle["n_scored"] == 6 and angle["n_miss"] == 5
    assert angle["cliffs_delta"] == 1.0
    assert angle["distinguishes"] is True
    assert s["feedback"]["result"].startswith("6 of 11 throws scored")
    assert "lower release angle" in s["feedback"]["why"].lower()
    assert "Throw" in s["feedback"]["next"]
    assert "not" in s["feedback"]["caveat"].lower()


def test_difference_below_noise_floor_is_not_claimed():
    rows = rows_with([35.2, 35.4, 35.3, 35.5, 35.1], [34.9, 34.8, 35.0, 34.7, 34.9])
    for r in rows:
        r["bag_release_angle_se_deg"] = 2.0          # difference ~0.5° << 2×SE
    s = performance_summary(rows, {})
    angle = s["variables"]["bag_release_angle_deg"]
    assert angle["cliffs_delta"] == 1.0
    assert angle["distinguishes"] is False
    assert angle["below_noise_floor"] is True
    assert "no measured release variable clearly separated" in s["feedback"]["why"].lower()


def test_too_few_per_group_stays_descriptive():
    rows = rows_with([35, 36, 34, 35], [20])
    s = performance_summary(rows, {})
    angle = s["variables"]["bag_release_angle_deg"]
    assert angle["cliffs_delta"] is None and angle["distinguishes"] is False
    assert "more misses" in s["feedback"]["why"].lower() or "not enough" in s["feedback"]["why"].lower()


def test_consistency_statistics_and_cv_only_for_ratio_scale():
    rows = rows_with([30, 32, 34], [30, 40, 20], extra=None)
    for i, r in enumerate(rows):
        r["bag_release_speed_m_s"] = 6.0 + 0.1 * i
    s = performance_summary(rows, {})
    angle, speed = s["variables"]["bag_release_angle_deg"], s["variables"]["bag_release_speed_m_s"]
    assert angle["all"]["sd"] == pytest.approx(np.std([30, 32, 34, 30, 40, 20], ddof=1))
    assert angle["all"]["cv_percent"] is None
    assert speed["all"]["cv_percent"] == pytest.approx(100 * np.std(6 + 0.1 * np.arange(6), ddof=1) / np.mean(6 + 0.1 * np.arange(6)))
    assert angle["sd_ratio_miss_to_scored"] == pytest.approx(np.std([30, 40, 20], ddof=1) / np.std([30, 32, 34], ddof=1))


def test_speed_uses_meters_when_available_else_arm_lengths():
    rows = rows_with([35] * 3, [30] * 3)
    for r in rows:
        r["bag_release_speed_arm_lengths_s"] = 9.0
    s = performance_summary(rows, {})
    assert "bag_release_speed_arm_lengths_s" in s["variables"]
    assert "bag_release_speed_m_s" not in s["variables"]


def test_no_outcomes_says_so():
    s = performance_summary([{"trial_id": "a", "score_category": None, "bag_release_angle_deg": 30}], {})
    assert s["feedback"]["result"].startswith("No observed outcomes")


def test_compare_throws_ranks_by_athlete_variability_and_explains():
    rows = rows_with([35, 36, 34, 37, 35], [27, 26, 28, 25, 29])
    for i, r in enumerate(rows):
        r["elbow_angle_deg_at_release"] = 150 + (i % 3)      # tiny differences in elbow
    a, b = rows[0], rows[5]                                    # 35° scored vs 27° miss
    result = compare_throws(a, b, rows, {"s0": "Throw 1", "m0": "Throw 6"})
    assert result["differences"][0]["key"] == "bag_release_angle_deg"
    assert result["differences"][0]["difference"] == pytest.approx(-8.0)
    assert "Throw 6" in result["summary"] and "lower" in result["summary"]
    elbow = next(d for d in result["differences"] if d["key"] == "elbow_angle_deg_at_release")
    assert elbow["meaningful"] is False


def _library(tmp_path, angles_scored, angles_missed):
    import json
    trials = []
    values = [(a, 1) for a in angles_scored] + [(a, 0) for a in angles_missed]
    for i, (angle, score) in enumerate(values):
        d = tmp_path / f"t{i}"
        d.mkdir()
        trials.append(dict(id=f"T{i}", athleteID="A", analysisRelativePath=f"t{i}", cameraView="side",
                           throwingSide="right", sessionID="S", name=f"Throw {i + 1}", originalFilename=f"{i}.mov",
                           outcome=dict(intended_target="Hole center", throw_type="Standard", score_category=score)))
        (d / "results.json").write_text(json.dumps(dict(
            trial_id=f"T{i}", athlete_id="A", camera_view="side", events={},
            quality=dict(warnings=[], usable_frame_percentage=100),
            summaries=dict(bag_release_angle_deg=angle, bag_release_angle_se_deg=0.5))))
        (d / "normalized.json").write_text(json.dumps(dict(trial_id=f"T{i}", camera_view="side", tau=[0, 1], values={})))
    (tmp_path / "project.json").write_text(json.dumps(dict(trials=trials, athletes=[dict(id="A", participantCode="P")])))


def test_insights_lead_with_three_level_feedback_and_cli_compares_throws(tmp_path):
    import json
    from cornhole_biomech.cli import main
    from cornhole_biomech.insights import generate_insights
    _library(tmp_path, [35, 36, 34, 37, 35, 36], [27, 26, 28, 25, 29])
    r = generate_insights(tmp_path, "T0", export_report=False)
    feedback = r["performance"]["summary"]["feedback"]
    assert r["coach_summary"].startswith(feedback["result"])
    assert "lower release angle" in feedback["why"]
    generate_insights(tmp_path, "T6", export_report=False)
    import io, contextlib
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        assert main(["compare-throws", "--project", str(tmp_path), "--a", "T0", "--b", "T6"]) == 0
    payload = json.loads(stream.getvalue().strip().splitlines()[-1])
    assert "Throw 7" in payload["data"]["summary"] and "lower release angle" in payload["data"]["summary"]


def test_summary_includes_individual_points_with_groups_for_plotting():
    rows = rows_with([35, 36], [27]) + [{"trial_id": "u", "score_category": None, "bag_release_angle_deg": 30}]
    points = performance_summary(rows, {"u": "Throw 4"})["variables"]["bag_release_angle_deg"]["points"]
    assert [p["group"] for p in points] == ["scored", "scored", "miss", None]
    assert points[-1]["label"] == "Throw 4" and points[-1]["value"] == 30
