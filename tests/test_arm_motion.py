import numpy as np
import pytest

from cornhole_biomech.arm_motion import analyze_arm_motion, ARM_METRICS
from cornhole_biomech.pipeline import _metrics_metadata


def analyze(angle, radius=None, **kwargs):
    return analyze_arm_motion(
        {"elbow_angle_deg": np.asarray(angle), "shoulder_wrist_radius_arm_lengths":
         np.ones(len(angle)) if radius is None else np.asarray(radius)},
        kwargs.get("start", 0), kwargs.get("end", len(angle)-1),
        kwargs.get("forward", 0), kwargs.get("release", len(angle)-1), kwargs.get("view", "side"))


def test_straight_and_fixed_bent_elbows_have_same_zero_excursion():
    for angle, flexion in [(180, 0), (135, 45)]:
        result = analyze([angle]*10)
        assert result["status"] == "available"
        assert result["summaries"]["arm_motion_mean_flexion_deg"] == flexion
        assert result["summaries"]["arm_motion_flexion_rom_deg"] == 0
        assert result["summaries"]["arm_motion_flexion_sd_deg"] == 0
        assert result["summaries"]["arm_motion_radius_cv_ratio"] == 0


def test_known_motion_and_native_phase_only():
    result = analyze([0, 150, 155, 160, 165, 170, 0], forward=1, release=5)
    assert result["sample_count"] == 5
    m = result["summaries"]
    assert m["arm_motion_mean_flexion_deg"] == 20
    assert m["arm_motion_flexion_rom_deg"] == 20
    assert m["arm_motion_flexion_sd_deg"] == pytest.approx(np.sqrt(62.5))


@pytest.mark.parametrize("kwargs", [{"forward": None}, {"release": None}, {"forward": 9}, {"forward": -1}, {"release": 10}, {"start": 2}, {"end": 7}])
def test_missing_or_out_of_movement_phase_is_unavailable(kwargs):
    r = analyze([160]*10, **kwargs)
    assert r["status"] == "unavailable_phase"
    assert all(value is None for value in r["summaries"].values())


@pytest.mark.parametrize("angles", [[np.nan]*10, [180]*4, [180]*7+[np.nan]*3, [181]*10, [-1]*10])
def test_bad_data_suppressed_not_converted_to_zero(angles):
    r = analyze(angles)
    assert r["status"] == "insufficient_tracking"
    assert all(value is None for value in r["summaries"].values())


def test_coverage_boundary_and_independent_radius_gate():
    r = analyze([150]*8+[np.nan]*2, [1]*7+[np.nan]*3)
    assert r["coverage"] == .8
    assert r["status"] == "available"
    assert r["radius_coverage"] == .7
    assert r["summaries"]["arm_motion_radius_cv_ratio"] is None
    assert r["summaries"]["arm_motion_mean_flexion_deg"] == 30
    assert analyze([150]*10, [0]*10)["summaries"]["arm_motion_radius_cv_ratio"] is None


def test_radius_cv_scale_invariance():
    radius = np.arange(1, 11)
    small = analyze([150]*10, radius)["summaries"]["arm_motion_radius_cv_ratio"]
    large = analyze([150]*10, radius*100)["summaries"]["arm_motion_radius_cv_ratio"]
    assert small == pytest.approx(np.std(radius, ddof=1)/np.mean(radius))
    assert small == pytest.approx(large)


def test_non_side_projection_is_withheld():
    r = analyze([150]*10, view="front")
    assert r["status"] == "unavailable_view"
    assert all(value is None for value in r["summaries"].values())


def test_metadata_preserves_units_and_scope():
    metadata = _metrics_metadata(dict.fromkeys(ARM_METRICS), "side")
    assert metadata["arm_motion_mean_flexion_deg"]["units"] == "degrees"
    assert metadata["arm_motion_radius_cv_ratio"]["units"] == "dimensionless"
    assert metadata["arm_motion_flexion_rom_deg"]["claim_scope"] == "descriptive_projected_2d_kinematics"


def test_report_uses_saved_gates_and_removes_stale_plot(tmp_path):
    import json
    from cornhole_biomech.report import arm_motion_report
    result = analyze([150, 155, 160, 165, 170])
    (tmp_path / "results.json").write_text(json.dumps({"arm_motion": result}))
    normalized = {"tau": [0, .25, .5, .75, 1], "values": {"elbow_angle_deg": [150, 155, 160, 165, 170]},
                  "event_timing": {"forward_swing": 0, "release": 1}}
    html = arm_motion_report(tmp_path, normalized)
    assert "20.00" in html
    assert "data:image/png;base64," in html
    assert (tmp_path / "arm_motion.png").exists()
    stale = arm_motion_report(tmp_path, normalized, stale=True)
    assert "Reanalyze" in stale
    assert "20.00" not in stale
    assert not (tmp_path / "arm_motion.png").exists()
    result["status"] = "insufficient_tracking"
    result["summaries"] = dict.fromkeys(ARM_METRICS)
    (tmp_path / "results.json").write_text(json.dumps({"arm_motion": result}))
    assert "data:image" not in arm_motion_report(tmp_path, normalized)
