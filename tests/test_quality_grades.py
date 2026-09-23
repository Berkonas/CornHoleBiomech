"""Per-trial GOOD / WARNING / POOR grades follow their stated rules."""
from cornhole_biomech.quality import quality_grades


def flight(coverage_frames=60, span=60, gap=1, outliers=0, sigma=0.8):
    return {"status": "filtered", "first_frame": 100, "last_frame": 100 + span - 1,
            "measured_frames": list(range(coverage_frames)), "measurement_count": coverage_frames + outliers,
            "rejected_outlier_frames": list(range(outliers)), "longest_gap_frames": gap, "measurement_sigma_px": sigma}


POSE_OK = {"usable_frame_percentage": 95.0, "release_visibility": 1.0}


def test_all_good():
    g = quality_grades(POSE_OK, flight(), {"status": "estimated", "scale_ratio_to_reference": 1.04}, True,
                       "automatic_physics", 0.3, 8, 1.2)
    assert [g[k]["grade"] for k in ("pose", "bag", "calibration", "release")] == ["GOOD"] * 4


def test_degraded_inputs_lower_each_grade():
    g = quality_grades({"usable_frame_percentage": 75.0, "release_visibility": 0.7}, flight(coverage_frames=48, gap=5),
                       {"status": "estimated", "scale_ratio_to_reference": None}, False, "automatic_physics", 0.9, 8, 1.0)
    assert g["pose"]["grade"] == "WARNING"
    assert g["bag"]["grade"] == "WARNING"
    assert g["calibration"]["grade"] == "WARNING"     # gravity scale only
    assert g["release"]["grade"] == "WARNING"         # first flight point far from the wrist


def test_missing_data_is_poor_not_invented():
    g = quality_grades({"usable_frame_percentage": 40.0, "release_visibility": None}, None, None, False, None, None, None, None)
    assert all(g[k]["grade"] == "POOR" for k in ("pose", "bag", "calibration", "release"))
    assert "insufficient tracking quality" in g["bag"]["reason"]


def test_manual_release_is_good_and_scale_disagreement_is_not():
    g = quality_grades(POSE_OK, flight(), {"status": "estimated", "scale_ratio_to_reference": 1.3}, True, "manual",
                       None, None, None)
    assert g["release"]["grade"] == "GOOD"
    assert g["calibration"]["grade"] == "WARNING"
