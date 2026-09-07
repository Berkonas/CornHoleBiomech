from dataclasses import asdict
import json

import cv2
import numpy as np
import pytest

from cornhole_biomech.models import BoardPoint, PointEstimate, PoseFrame, PoseSequence, TrialContext, TrialOutcome
from cornhole_biomech.outcomes import board_point_from_normalized, outcome_summary, point_errors
from cornhole_biomech.pipeline import analyze_trial
from cornhole_biomech.statistics import INSUFFICIENT_MESSAGE, relationship


def test_board_coordinate_mapping_and_error():
    point = board_point_from_normalized(0.5, 0.5)
    assert point.x_inches == 12
    assert point.y_inches == 24
    error = point_errors(BoardPoint(12, 39), BoardPoint(15, 43))
    assert error["radial_error_inches"] == 5


def test_outcome_categories_are_validated():
    result = outcome_summary(TrialOutcome("hole", 3, "airmail"))
    assert result["score_category"] == 3
    with pytest.raises(ValueError):
        outcome_summary(TrialOutcome("hole", 2, "airmail"))


def test_relationship_requires_data_and_uses_spearman_when_available():
    insufficient = relationship([1, 2, 3], [3, 2, 1], minimum_trials=8)
    assert insufficient["message"] == INSUFFICIENT_MESSAGE
    result = relationship(list(range(10)), list(reversed(range(10))), minimum_trials=8)
    assert result["status"] == "estimated"
    assert result["spearman_rho"] == pytest.approx(-1)


def _make_video(path, frame_count=40, fps=60):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), fps, (320, 240))
    assert writer.isOpened()
    for i in range(frame_count):
        image = np.full((240, 320, 3), 240, np.uint8)
        cv2.circle(image, (80 + i, 100), 5, (0, 0, 0), -1)
        writer.write(image)
    writer.release()


def _make_pose(path, frame_count=40, fps=60):
    frames = []
    for i in range(frame_count):
        t = i / (frame_count - 1)
        values = {
            "left_shoulder": (120, 80), "right_shoulder": (160, 80),
            "left_elbow": (100, 120), "right_elbow": (185 + 10*t, 115),
            "left_wrist": (90, 155), "right_wrist": (195 + 60*t, 155 - 30*np.sin(np.pi*t)),
            "left_hip": (125, 190), "right_hip": (155, 190),
        }
        landmarks = {name: PointEstimate(float(x), float(y), 0.95) for name, (x, y) in values.items()}
        frames.append(PoseFrame(i, i / fps, landmarks))
    PoseSequence(1, fps, 320, 240, frame_count, "synthetic_test", "known", "1", frames).save(path)


def test_pipeline_exports_reproducible_package_from_imported_pose(tmp_path):
    video = tmp_path / "trial.avi"
    pose = tmp_path / "pose.json"
    output = tmp_path / "analysis"
    _make_video(video)
    _make_pose(pose)
    context = TrialContext("T001", "A001", "side", "right", "left_to_right", str(video))
    result = analyze_trial(
        context,
        output,
        pose_input=pose,
        make_annotated_video=False,
    )
    expected = {
        "pose_raw.json", "corrections.json", "events.json", "keypoints.csv",
        "kinematics.csv", "normalized.json", "results.json", "manifest.json",
        "angle_trajectories.png", "wrist_trajectory.png", "summary.md",
    }
    assert expected <= {item.name for item in output.iterdir()}
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["source_video"]["sha256"]
    assert manifest["analysis_configuration"]["filter"]["cutoff_hz"] == 6.0
    assert result["results"]["claim_scope"].startswith("projected_2d")

