import hashlib
import json

import cv2
import numpy as np
import pytest

from cornhole_biomech import REQUIRED_LANDMARKS
from cornhole_biomech.bag import (
    BagAutomaticPoint,
    BagCorrection,
    BagCorrectionSet,
    BagSeed,
    BagTrack,
    SpatialCalibration,
    bag_tracking_qa,
    detect_bag_wrist_release,
    effective_bag_track,
    estimate_projectile_release_kinematics,
    track_bag_from_seed,
)
from cornhole_biomech.events import apply_manual_event_overrides, detect_events
from cornhole_biomech.kinematics import calculate_kinematics, path_shape_metrics
from cornhole_biomech.models import PointEstimate, PoseFrame, PoseSequence, TrialContext
from cornhole_biomech.pipeline import analyze_trial
from cornhole_biomech.video import file_sha256, read_video_metadata


def _video(path, frames=20, fps=60.0, moving_square=False):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (96, 96))
    assert writer.isOpened()
    for frame in range(frames):
        image = np.zeros((96, 96, 3), dtype=np.uint8)
        if moving_square:
            x = 10 + frame
            image[30:42, x:x + 12] = 255
        writer.write(image)
    writer.release()


def _pose(path, frames=20, fps=60.0):
    pose_frames = []
    for frame in range(frames):
        progress = frame / max(1, frames - 1)
        points = {
            "left_shoulder": (35, 32), "right_shoulder": (50, 32),
            "left_elbow": (30, 45), "right_elbow": (56 + 8 * progress, 44),
            "left_wrist": (27, 57), "right_wrist": (61 + 18 * progress, 57 - 8 * progress),
            "left_hip": (38, 65), "right_hip": (51, 65),
        }
        pose_frames.append(PoseFrame(
            frame_index=frame,
            time_seconds=frame / fps,
            landmarks={name: PointEstimate(*points[name], 0.99) for name in REQUIRED_LANDMARKS},
        ))
    PoseSequence(1, fps, 96, 96, frames, "test", "synthetic", "1", pose_frames).save(path)


def test_bag_seed_rejects_degenerate_rectangle():
    with pytest.raises(ValueError):
        BagSeed.from_dict({"frame_index": 2, "bbox_xywh": [1, 2, 0, 5]})


def test_bag_corrections_and_short_gap_provenance_preserve_raw():
    track = BagTrack(
        1, 5, 100, 100, "hash", BagSeed(0, (0, 0, 4, 4)), "template_matching",
        "template_matching",
        [
            BagAutomaticPoint(0, 1, 1, 1), BagAutomaticPoint(1, 2, 2, 1),
            BagAutomaticPoint(2, None, None, 0, status="failed"),
            BagAutomaticPoint(3, 4, 4, 1), BagAutomaticPoint(4, 5, 5, 1),
        ],
        "partial_failure",
    )
    derived = effective_bag_track(
        track, BagCorrectionSet(corrections=[BagCorrection(1, 20, 21)]), 0.2, 1
    )
    assert derived["raw"][1].tolist() == [2, 2]
    assert derived["effective"][1].tolist() == [20, 21]
    assert derived["provenance"][1] == "manual"
    assert derived["provenance"][2] == "automatic_short_gap_interpolation"


def test_bag_review_requires_explicit_frame_coverage(tmp_path):
    path = tmp_path / "bag_corrections.json"
    corrections = BagCorrectionSet(
        corrections=[BagCorrection(4, 10, 11)],
        reviewed_through_frame=12,
        reviewed_at="2026-09-10T12:00:00Z",
        review_note="reviewed frame by frame",
    )
    corrections.save(path)
    loaded = BagCorrectionSet.load(path)
    assert loaded.covers(12)
    assert not loaded.covers(13)
    assert loaded.review_note == "reviewed frame by frame"


def test_bag_wrist_release_uses_persistent_divergence_and_manual_priority():
    wrist = np.zeros((30, 2))
    bag = wrist.copy()
    bag[12:, 0] = np.arange(18) * 2 + 10
    candidate = detect_bag_wrist_release(wrist, bag, 100, 60, 0.08, 0.05)
    assert candidate.automatic_frame == 12
    path = np.column_stack((np.sin(np.linspace(-1, 2, 30)), np.zeros(30)))
    events = detect_events(path, 60, candidate)
    corrected = apply_manual_event_overrides(events, {"release": events["release"].automatic_frame + 1})
    assert corrected["release"].automatic_frame == 12
    assert corrected["release"].effective_frame == 13


def test_local_fit_recovers_known_projectile_velocity_and_normalized_units():
    fps = 60.0
    time = np.arange(12) / fps
    pixels = np.column_stack((100 + 120 * time, 200 - 60 * time))
    result = estimate_projectile_release_kinematics(pixels, 0, fps, 60, "left_to_right")
    assert result["status"] == "estimated"
    assert result["velocity"]["forward_px_s"] == pytest.approx(120, abs=1e-7)
    assert result["velocity"]["vertical_px_s"] == pytest.approx(60, abs=1e-7)
    assert result["velocity"]["speed_arm_lengths_s"] == pytest.approx(np.hypot(120, 60) / 60)
    assert result["physical_units"]["status"] == "not_available_without_valid_athlete_plane_calibration"


def test_polynomial_fit_recovers_acceleration_and_valid_calibration_only():
    fps = 120.0
    time = np.arange(20) / fps
    pixels = np.column_stack((100 + 10 * time + 2 * time**2, 100 - 20 * time - 3 * time**2))
    valid = SpatialCalibration(100, "athlete_release_motion_plane", True, "motion-plane ruler")
    result = estimate_projectile_release_kinematics(pixels, 0, fps, 50, "left_to_right", valid)
    assert result["acceleration"]["status"] == "estimated_exploratory"
    assert result["acceleration"]["forward_px_s2"] == pytest.approx(4, abs=1e-6)
    assert result["acceleration"]["vertical_px_s2"] == pytest.approx(6, abs=1e-6)
    assert result["physical_units"]["velocity"]["forward_m_s"] == pytest.approx(0.1, abs=1e-8)
    invalid = SpatialCalibration(100, "distant_board_plane", True, "board")
    rejected = estimate_projectile_release_kinematics(pixels, 0, fps, 50, "left_to_right", invalid)
    assert rejected["physical_units"]["status"] == "rejected_invalid_or_wrong_plane_calibration"


def test_acceleration_is_suppressed_below_frame_rate_gate():
    time = np.arange(10) / 30
    pixels = np.column_stack((time, -time))
    result = estimate_projectile_release_kinematics(pixels, 0, 30, 1, "left_to_right")
    assert result["velocity"] is not None
    assert result["acceleration"]["status"] == "suppressed"
    assert "below" in result["acceleration"]["reason"]


def test_path_straightness_and_curvature_are_descriptive():
    straight = path_shape_metrics(np.column_stack((np.arange(10), np.zeros(10))))
    curved = path_shape_metrics(np.column_stack((np.cos(np.linspace(0, np.pi, 30)), np.sin(np.linspace(0, np.pi, 30)))))
    assert straight["straightness"] == pytest.approx(1)
    assert straight["rms_line_deviation"] == pytest.approx(0, abs=1e-12)
    assert curved["straightness"] < 1
    assert curved["curvature_rad_per_unit"] > 0


def test_projected_translation_decomposition_and_radius():
    frames = 12
    landmarks = tuple(REQUIRED_LANDMARKS)
    lookup = {name: index for index, name in enumerate(landmarks)}
    coords = np.zeros((frames, len(landmarks), 2), dtype=float)
    for frame in range(frames):
        shoulder = np.array([20 + frame, 20.0])
        values = {
            "right_shoulder": shoulder, "right_elbow": shoulder + (10, 0),
            "right_wrist": shoulder + (20, 0), "left_shoulder": shoulder + (-10, 0),
            "left_elbow": shoulder + (-15, 10), "left_wrist": shoulder + (-20, 20),
            "left_hip": shoulder + (-8, 30), "right_hip": shoulder + (2, 30),
        }
        for name, value in values.items():
            coords[frame, lookup[name]] = value
    result = calculate_kinematics(coords, landmarks, 60, "right", "left_to_right")
    assert np.nanmedian(result.values["shoulder_wrist_radius_arm_lengths"]) == pytest.approx(1)
    assert np.nanmedian(result.values["wrist_relative_speed_arm_lengths_s"]) == pytest.approx(0, abs=1e-10)
    assert np.nanmedian(result.values["shoulder_speed_px_s"]) == pytest.approx(60)


def test_template_tracker_is_seeded_and_never_changes_source(tmp_path):
    video = tmp_path / "bag.mp4"
    _video(video, frames=10, moving_square=True)
    before = hashlib.sha256(video.read_bytes()).hexdigest()
    track = track_bag_from_seed(video, BagSeed(0, (10, 30, 12, 12)), "template_matching", 0.1, 2.5)
    after = hashlib.sha256(video.read_bytes()).hexdigest()
    assert before == after
    assert track.effective_method == "template_matching"
    assert sum(point.x is not None for point in track.automatic_points) >= 8


def test_csrt_seed_uses_opencv5_compatible_integer_rectangle(tmp_path, monkeypatch):
    video = tmp_path / "bag.mp4"
    _video(video, frames=3, moving_square=True)

    class FakeTracker:
        def init(self, _image, bbox):
            assert all(isinstance(value, int) for value in bbox)
            return True

        def update(self, _image):
            return False, None

    monkeypatch.setattr("cornhole_biomech.bag._csrt_factory", lambda: lambda: FakeTracker())
    track = track_bag_from_seed(video, BagSeed(0, (10.2, 30.4, 12.1, 12.2)), "csrt")
    assert track.requested_method == "csrt"
    assert track.effective_method == "csrt"
    assert track.status == "automatic_failed"


def test_bag_tracking_qa_reports_failures_and_frame_uncertainty():
    track = BagTrack(
        1, 2, 10, 10, "hash", BagSeed(0, (0, 0, 2, 2)), "template_matching",
        "template_matching", [BagAutomaticPoint(0, 2, 3, 1)], "partial_failure",
    )
    result = bag_tracking_qa(
        track, [
            {"frame_index": 0, "x": 3, "y": 3, "automatic_identity_failure": True},
            {"frame_index": 1, "x": 4, "y": 4},
        ],
        arm_length_pixels=10, automatic_release_frame=12, manual_release_frame=10, fps=60,
    )
    assert result["missing_track_rate"] == pytest.approx(0.5)
    assert result["pixel_error"]["mean"] == pytest.approx(1)
    assert result["reviewed_identity_failure_frames"] == [0]
    assert result["release_frame_error"]["absolute_milliseconds"] == pytest.approx(1000 / 30)


def test_pipeline_writes_separate_bag_artifacts_and_provenance(tmp_path):
    video = tmp_path / "trial.mp4"
    pose = tmp_path / "pose.json"
    output = tmp_path / "analysis"
    _video(video, frames=20)
    _pose(pose, frames=20)
    metadata = read_video_metadata(video)
    points = [
        BagAutomaticPoint(frame, 60 + frame, 55 - frame * 0.3, 0.95, (56 + frame, 51, 8, 8))
        for frame in range(20)
    ]
    raw_track = tmp_path / "bag-raw-input.json"
    BagTrack(
        1, metadata.frame_count, metadata.width, metadata.height, metadata.sha256,
        BagSeed(0, (56, 51, 8, 8)), "import", "synthetic_test", points, "complete",
    ).save(raw_track)
    result = analyze_trial(
        TrialContext("T1", "A1", "side", "right", "left_to_right", str(video)),
        output, backend="rtmpose", pose_input=pose, bag_track_input=raw_track,
        make_annotated_video=False,
    )
    assert (output / "bag_raw.json").exists()
    assert (output / "bag_track.json").exists()
    assert (output / "bag_keypoints.csv").exists()
    assert result["results"]["bag"]["tracker"]["effective_method"] == "synthetic_test"
    assert result["results"]["bag"]["launch"]["status"] == "suppressed_unreviewed_track"
    assert result["results"]["summaries"]["bag_release_speed_arm_lengths_s"] is None
    assert result["results"]["summaries"]["shoulder_bag_radius_at_release_arm_lengths"] is None
    assert 'bag' not in result["results"]["events"]["release"]["automatic_method"]
    assert result["manifest"]["bag_tracking"]["raw_track_sha256"] == file_sha256(output / "bag_raw.json")
    assert result["results"]["metrics_metadata"]["bag_release_speed_arm_lengths_s"]["units"] == "arm lengths/s"

    review = tmp_path / "bag-corrections.json"
    BagCorrectionSet(reviewed_through_frame=19).save(review)
    reviewed = analyze_trial(
        TrialContext("T1", "A1", "side", "right", "left_to_right", str(video)),
        output, backend="rtmpose", pose_input=pose, bag_corrections_path=review,
        make_annotated_video=False,
    )
    assert reviewed["results"]["bag"]["review"]["covers_launch_fit"] is True
    # Identity approval is not release-event confirmation.
    assert reviewed["results"]["bag"]["launch"]["status"] == "needs_release_confirmation"
    assert reviewed["results"]["summaries"]["bag_release_speed_arm_lengths_s"] is None


def test_offscreen_tracker_candidate_is_missing_not_clamped_or_fatal(tmp_path, monkeypatch):
    video = tmp_path / "exit.mp4"
    _video(video, frames=4, moving_square=True)
    class Tracker:
        def init(self, *_): return True
        def update(self, _): return True, (200, 30, 12, 12)
    monkeypatch.setattr("cornhole_biomech.bag._csrt_factory", lambda: lambda: Tracker())
    track = track_bag_from_seed(video, BagSeed(0, (10, 30, 12, 12)), "csrt")
    assert track.failure_frames == [1, 2, 3]
    assert all(p.x is None and p.status == "outside_frame" for p in track.automatic_points[1:])


def test_reviewed_release_withholds_conflicting_automatic_phases():
    from cornhole_biomech.events import EVENT_ORDER
    from cornhole_biomech.models import EventValue
    events = {n: EventValue(n, automatic_frame=i*10) for i,n in enumerate(EVENT_ORDER)}
    fixed = apply_manual_event_overrides(events, {"release": 45})
    assert fixed['release'].effective_frame == 45
    assert fixed['peak_follow_through'].automatic_frame == 40
    assert fixed['peak_follow_through'].effective_frame is None
    assert fixed['peak_follow_through'].suppressed_reason
    with pytest.raises(ValueError, match="Reviewed events are out of order"):
        apply_manual_event_overrides(events, {"release": 45, "motion_end": 44})


def test_color_motion_follows_fast_bag_and_leaves_occlusion_gaps(tmp_path):
    video = tmp_path / 'color.mp4'
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*'mp4v'), 60, (128,96))
    truth={}
    for f in range(18):
        image=np.full((96,128,3),70,np.uint8)
        image[10:19,45:54]=(0,0,220)  # same-colored stationary distractor
        x,y=10+5*f,35-f
        if f not in (6,7,8): image[y:y+9,x:x+9]=(0,0,220)
        truth[f]=(x+4,y+4)
        writer.write(image)
    writer.release()
    track=track_bag_from_seed(video,BagSeed(0,(9,34,11,11)),'auto')
    assert track.effective_method=='color_motion'
    for point in track.automatic_points:
        if point.frame_index in (6,7,8):
            assert point.x is None
        else:
            assert point.x is not None
            assert np.linalg.norm(np.array([point.x,point.y])-truth[point.frame_index]) < 2


def test_neutral_bag_does_not_take_its_seed_color_from_background():
    from cornhole_biomech.bag import _seed_color_model
    seed=np.zeros((30,30,3),np.uint8)
    seed[:]=(20,100,180)  # warm, saturated background
    seed[5:25,5:25]=(200,200,200)  # neutral bag centered in selected box
    assert _seed_color_model(seed) is None
