import math

import pytest

from cornhole_biomech.validation import (
    annotation_points,
    elbow_angle_errors,
    event_errors,
    landmark_errors,
    select_validation_frames,
)


def test_frame_selection_keeps_events_neighbors_and_bounds():
    frames = select_validation_frames(100, {"release": 50, "peak_backswing": 0, "motion_end": 99}, count=12, seed=1)
    assert {49, 50, 51, 0, 99} <= set(frames)
    assert frames == sorted(set(frames))
    assert len(frames) == 12
    assert all(0 <= f < 100 for f in frames)
    assert frames == select_validation_frames(100, {"release": 50, "peak_backswing": 0, "motion_end": 99}, count=12, seed=1)


def test_frame_selection_without_events_is_spread_over_clip():
    frames = select_validation_frames(300, None, count=10, seed=3)
    assert len(frames) == 10
    assert frames[0] < 60 and frames[-1] > 240


def test_annotation_points_skip_not_visible_and_keep_visibility_count():
    ann = {"annotations": [
        {"frame_index": 3, "landmark": "right_wrist", "x": 10, "y": 20},
        {"frame_index": 3, "landmark": "bag", "visible": False},
    ]}
    points, hidden = annotation_points(ann)
    assert points == {(3, "right_wrist"): (10.0, 20.0)}
    assert hidden == {(3, "bag")}


def test_landmark_errors_known_offsets_bias_and_failures():
    reference = {(f, "right_wrist"): (100.0, 100.0) for f in range(4)}
    estimate = {(0, "right_wrist"): (103.0, 104.0),   # 5 px
                (1, "right_wrist"): (100.0, 105.0),   # 5 px
                (2, "right_wrist"): (106.0, 108.0),   # 10 px
                (3, "right_wrist"): None}              # detection failure
    result = landmark_errors(reference, estimate, normalizer_px=50.0)["right_wrist"]
    assert result["n_reference"] == 4
    assert result["n_compared"] == 3
    assert result["detection_failure_rate"] == pytest.approx(0.25)
    assert result["mean_px"] == pytest.approx(20 / 3)
    assert result["median_px"] == pytest.approx(5.0)
    assert result["rmse_px"] == pytest.approx(math.sqrt((25 + 25 + 100) / 3))
    assert result["bias_x_px"] == pytest.approx(3.0)
    assert result["bias_y_px"] == pytest.approx(17 / 3)
    assert result["mean_arm_lengths"] == pytest.approx(20 / 3 / 50)


def test_landmark_errors_all_missing_reports_failure_not_zero_error():
    result = landmark_errors({(0, "bag"): (1.0, 1.0)}, {}, None)["bag"]
    assert result["n_compared"] == 0
    assert result["detection_failure_rate"] == 1.0
    assert result["mean_px"] is None


def test_elbow_angle_errors_uses_complete_triplets_only():
    shoulder, elbow = (0.0, 0.0), (0.0, 60.0)
    straight_wrist, bent_wrist = (0.0, 120.0), (60.0, 60.0)       # 180° vs 90°
    reference = {(0, "right_shoulder"): shoulder, (0, "right_elbow"): elbow, (0, "right_wrist"): straight_wrist,
                 (1, "right_shoulder"): shoulder, (1, "right_elbow"): elbow}  # frame 1 incomplete
    estimate = {(0, "right_shoulder"): shoulder, (0, "right_elbow"): elbow, (0, "right_wrist"): bent_wrist}
    result = elbow_angle_errors(reference, estimate, "right")
    assert result["n_compared"] == 1
    assert result["mean_abs_deg"] == pytest.approx(90.0)
    assert result["bias_deg"] == pytest.approx(-90.0)
    assert result["observations"][0]["reference_deg"] == pytest.approx(180.0)


def test_event_errors_signed_frames_and_milliseconds():
    result = event_errors({"release": 200, "first_contact": 270}, {"release": 197, "first_contact": None}, fps=60.0)
    assert result["release"]["signed_frames"] == -3
    assert result["release"]["signed_ms"] == pytest.approx(-50.0)
    assert result["first_contact"]["status"] == "no_automatic_estimate"


def test_landmark_errors_ignore_landmarks_absent_from_reference():
    result = landmark_errors({(0, "right_elbow"): (0.0, 0.0)}, {(0, "right_elbow"): (3.0, 4.0), (0, "nose"): (1.0, 1.0)}, None)
    assert set(result) == {"right_elbow"}
    assert result["right_elbow"]["mean_px"] == pytest.approx(5.0)
