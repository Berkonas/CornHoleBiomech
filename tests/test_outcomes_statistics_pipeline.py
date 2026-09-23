from dataclasses import asdict
import json

import cv2
import numpy as np
import pytest

from cornhole_biomech.models import BoardPoint, PointEstimate, PoseFrame, PoseSequence, TrialContext, TrialOutcome
from cornhole_biomech.outcomes import board_point_from_normalized, outcome_summary, point_errors
from cornhole_biomech.pipeline import analyze_relationships, analyze_trial, compare_trial
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


def test_comparison_exports_curves_for_native_plot_and_ghost_arm(tmp_path):
    tau = np.linspace(0, 1, 101).tolist()
    reference = tmp_path / "reference"
    test = tmp_path / "test"
    reference.mkdir()
    test.mkdir()
    base = np.linspace(80, 140, 101)
    wrist = np.column_stack((np.linspace(0, 1, 101), np.zeros(101)))
    elbow = 0.5 * wrist
    for directory, trial_id, offset in ((reference, "R1", 0), (test, "T1", 3)):
        payload = {
            "trial_id": trial_id,
            "athlete_id": "A1",
            "camera_view": "side",
            "tau": tau,
            "event_timing": {"release": 0.5},
            "values": {
                "elbow_angle_deg": (base + offset).tolist(),
                "wrist_path_arm_lengths": wrist.tolist(),
                "elbow_path_arm_lengths": elbow.tolist(),
            },
        }
        (directory / "normalized.json").write_text(json.dumps(payload))
    output = tmp_path / "comparison"
    result = compare_trial(test, [reference], output)
    assert result["curves"]["test"]["elbow_angle_deg"][0] == pytest.approx(83)
    assert result["curves"]["reference_mean"]["elbow_path_arm_lengths"][50][0] == pytest.approx(0.25)
    assert (output / "comparison_elbow_angle.png").exists()


def test_relationships_use_raw_board_outcomes_and_separate_consistency_features(tmp_path):
    analysis_dirs = []
    comparison_dirs = []
    outcomes = {}
    for index in range(8):
        trial_id = f"T{index}"
        analysis = tmp_path / f"analysis-{index}"
        analysis.mkdir()
        analysis_dirs.append(analysis)
        summary = {
            "trial_id": trial_id,
            "athlete_id": "A1",
            "summaries": {
                "elbow_angle_deg_at_release": 100 + index,
                "elbow_angle_deg_rom": 30 + index,
                "trunk_inclination_deg_at_release": 5 + index,
                "movement_duration_seconds": 0.8 + index / 100,
                "release_timing_cycle": 0.5 + index / 100,
            },
        }
        (analysis / "results.json").write_text(json.dumps(summary))
        wrist = np.column_stack((np.linspace(0, 1, 101), np.full(101, index / 100)))
        (analysis / "normalized.json").write_text(json.dumps({
            "trial_id": trial_id,
            "athlete_id": "A1",
            "camera_view": "side",
            "values": {"wrist_path_arm_lengths": wrist.tolist()},
        }))
        comparison = tmp_path / f"comparison-{index}"
        comparison.mkdir()
        comparison_dirs.append(comparison)
        (comparison / "comparison.json").write_text(json.dumps({
            "test_trial_id": trial_id,
            "raw_metrics": {"wrist_path_rmse_arm_lengths": index / 100},
        }))
        outcomes[trial_id] = {
            "intended_target": "Hole center",
            "score_category": 1,
            "throw_type": "Standard",
            "intended_point": {"x_inches": 12, "y_inches": 39},
            "first_contact_point": {"x_inches": 12 + index, "y_inches": 39},
        }
    output = tmp_path / "relationships.json"
    result = analyze_relationships(
        analysis_dirs, outcomes, output, comparison_dirs=comparison_dirs, minimum_trials=8
    )
    assert result["outcome_variable"] == "radial_error_inches"
    assert "reference_similarity_score" not in result["relationships"]
    assert result["relationships"]["wrist_reference_deviation_arm_lengths"]["n"] == 8
    assert result["within_athlete_consistency"]["elbow_angle_deg_at_release"]["standard_deviation"] > 0
    assert result["data_rows"][4]["radial_error_inches"] == pytest.approx(4)
    assert result["data_rows"][4]["wrist_path_deviation_from_athlete_mean_arm_lengths"] is not None


def test_sports2d_cached_pose_corrections_and_movement_interval(tmp_path,monkeypatch):
    from cornhole_biomech.sports2d_adapter import Sports2DAdapter
    from cornhole_biomech.video import file_sha256
    from cornhole_biomech.kinematics import calculate_kinematics
    video=tmp_path/'trial.avi';pose=tmp_path/'pose.json';output=tmp_path/'analysis'
    _make_video(video);_make_pose(pose)
    sequence=PoseSequence.load(pose);sequence.backend='sports2d';sequence.backend_version='0.8.34'
    calls=[]
    def run(*args,**kwargs):calls.append(1);return sequence
    monkeypatch.setattr(Sports2DAdapter,'analyze',run)
    context=TrialContext('T1','A1','side','right','left_to_right',str(video))
    analyze_trial(context,output,make_annotated_video=False)
    original=file_sha256(output/'pose_raw.json')
    corrections={'schema_version':1,'corrections':[{'frame_index':20,'landmark':'right_wrist','x':220,'y':110,'kind':'manual'}]}
    (output/'corrections.json').write_text(json.dumps(corrections))
    event_frames={'motion_start':10,'peak_backswing':12,'forward_swing':14,'release':20,'peak_follow_through':25,'motion_end':30}
    (output/'events.json').write_text(json.dumps({'manual_overrides':event_frames}))
    result=analyze_trial(context,output,make_annotated_video=False)
    assert len(calls)==1
    assert file_sha256(output/'pose_raw.json')==original
    assert result['results']['quality']['manual_correction_count']==1
    assert result['results']['summaries']['movement_duration_seconds']==pytest.approx(20/60)
    import pandas as pd
    rows=pd.read_csv(output/'kinematics.csv')
    assert result['results']['summaries']['elbow_angle_deg_mean']==pytest.approx(rows['elbow_angle_deg'].iloc[10:31].mean())
    event_frames['release']=5
    (output/'events.json').write_text(json.dumps({'manual_overrides':event_frames}))
    with pytest.raises(ValueError,match='order'):analyze_trial(context,output,make_annotated_video=False)


def test_automatic_contact_not_checked_against_board_is_flagged():
    from cornhole_biomech.pipeline import _merge_automatic_flight_review
    auto = {"first_contact_frame": 90, "contact": {"state": "unverified", "reason": "Board not located."}}
    review, warnings = _merge_automatic_flight_review(auto, {})
    assert review["first_contact_frame"] == 90 and review["contact_state"] == "unverified"
    assert any("not checked against the board" in w for w in warnings)
    review, warnings = _merge_automatic_flight_review(
        {"first_contact_frame": 90, "contact": {"state": "measured", "reason": None}}, {})
    assert review["contact_state"] == "measured" and warnings == []
    # A manually reviewed contact wins and is not flagged.
    review, warnings = _merge_automatic_flight_review(auto, {"first_contact_frame": 95})
    assert review["first_contact_frame"] == 95 and review["contact_state"] == "manual" and warnings == []
