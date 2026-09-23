"""Timing variables, metric reliability rules, replay assembly and post-contact tracking."""
import math

import cv2
import numpy as np
import pytest

from cornhole_biomech.bag_segment import track_after_contact
from cornhole_biomech.reliability import BY_KEY, assess_metrics, hidden_for_coaching
from cornhole_biomech.replay import build_replay
from cornhole_biomech.timing import release_timing_metrics

FPS = 60.0


def pendulum(n=120, release=80, arm=100.0):
    """Wrist on a circle around a fixed shoulder: angle sweeps from −60° (back) to +60°, fastest at the bottom."""
    t = np.arange(n) / FPS
    phi = np.radians(-60 + 120 * (1 - np.cos(np.pi * np.clip((np.arange(n) - 20) / 90, 0, 1))) / 2)
    shoulder = np.array([500.0, 300.0])
    wrist = np.column_stack([shoulder[0] + arm * np.sin(phi), shoulder[1] + arm * np.cos(phi)])
    return t, wrist, phi


def test_timing_peak_speed_at_bottom_and_direction():
    _, wrist, phi = pendulum()
    bottom = int(np.argmin(np.abs(phi)))
    out = release_timing_metrics(wrist, np.full(len(wrist), 170.0), FPS,
                                 {"release": 80, "peak_backswing": 20}, 100.0, "left_to_right",
                                 bag_release_speed_arm_lengths_s=3.0, bag_release_angle_deg=40.0)
    assert out["peak_wrist_speed_frame"] == pytest.approx(bottom, abs=1)
    assert out["wrist_peak_speed_time_rel_release_ms"] == pytest.approx(1000 * (bottom - 80) / FPS, abs=20)
    # At release the wrist moves forward and up along the circle: direction = arm angle.
    assert out["wrist_direction_at_release_deg"] == pytest.approx(math.degrees(phi[80]), abs=2)
    assert out["hand_to_bag_speed_ratio"] == pytest.approx(3.0 / out["wrist_speed_at_release_arm_lengths_s"])
    assert out["elbow_peak_extension_velocity_deg_s"] is None     # a constant elbow never extends


def _pose(n=60, foreshorten_at=None):
    landmarks = ("right_shoulder", "right_elbow", "right_wrist", "left_shoulder", "left_hip", "right_hip")
    raw = np.zeros((n, len(landmarks), 2))
    raw[:, 0] = [500, 300]; raw[:, 1] = [500, 350]; raw[:, 2] = [500, 400]
    raw[:, 3] = [480, 300]; raw[:, 4] = [480, 420]; raw[:, 5] = [500, 420]
    if foreshorten_at is not None:
        raw[foreshorten_at, 2] = [500, 360]   # forearm pointing at the camera: 20% of its length
    return landmarks, raw, np.full((n, len(landmarks)), 0.9)


def test_foreshortened_segment_and_low_confidence_withhold_value():
    landmarks, raw, conf = _pose(foreshorten_at=30)
    values = {"elbow_angle_deg_at_release": 175.0, "swing_release_arm_angle_deg": 30.0}
    out = assess_metrics(values, raw, conf, raw, landmarks, "right", {"release": 30}, 0.35, 100.0)
    elbow = out["elbow_angle_deg_at_release"]
    assert elbow["status"] == "unreliable" and elbow["value"] is None
    assert any("foreshortened" in r for r in elbow["reasons"])
    conf[29, 0] = 0.1
    out = assess_metrics(values, raw, conf, raw, landmarks, "right", {"release": 30}, 0.35, 100.0)
    assert out["swing_release_arm_angle_deg"]["status"] == "unreliable"


def test_release_window_sensitivity_is_a_caution_not_a_rejection():
    landmarks, raw, conf = _pose()
    out = assess_metrics({"elbow_angle_deg_at_release": 160.0}, raw, conf, raw, landmarks, "right", {"release": 30},
                         0.35, 100.0, release_window=(27, 30), at_other_release={"elbow_angle_deg_at_release": 140.0})
    row = out["elbow_angle_deg_at_release"]
    assert row["status"] == "caution" and row["value"] == 160.0
    assert "exact release frame" in row["reasons"][0]
    assert out["bag_release_angle_deg"]["status"] == "not_measured"


def test_bag_metrics_follow_stage_grades_and_orientation_is_hidden():
    landmarks, raw, conf = _pose()
    out = assess_metrics({"bag_release_speed_m_s": 7.5, "bag_release_angle_deg": 40.0}, raw, conf, raw, landmarks,
                         "right", {"release": 30}, 0.35, 100.0, bag_grade="GOOD", release_grade="GOOD",
                         calibration_grade="WARNING")
    assert out["bag_release_angle_deg"]["status"] == "reliable"
    assert out["bag_release_speed_m_s"]["status"] == "caution"
    out = assess_metrics({"bag_release_angle_deg": 40.0}, raw, conf, raw, landmarks, "right", {"release": 30},
                         0.35, 100.0, bag_grade="POOR")
    assert out["bag_release_angle_deg"]["value"] is None
    assert hidden_for_coaching("forearm_orientation_deg_rom") and not hidden_for_coaching("elbow_angle_deg_at_release")
    assert BY_KEY["elbow_peak_extension_velocity_deg_s"].exploratory


def test_replay_maps_paths_back_onto_each_frame():
    measured = np.full((10, 2), np.nan)
    measured[2:8] = [[100 + 10 * k, 200] for k in range(6)]
    transforms = {str(f): [[1, 0, 2.0 * f], [0, 1, 0]] for f in range(10)}   # raw → release frame
    replay = build_replay(fps=FPS, frame_count=10, width=640, height=480, camera_to_release=transforms,
                          measured=measured, filtered=None, model_check={"apex_frame": None, "curve": []},
                          after_contact=None, events={"release": 2, "first_contact": 7}, summaries={},
                          coach_metrics={}, grades={"bag": {"grade": "GOOD"}}, release_window=(1, 2))
    inverse = np.array(replay["release_to_frame"]["5"])
    assert np.allclose(inverse @ [110, 200, 1], [100, 200])   # release-frame point drawn on frame 5
    assert set(replay["events"]) == {"release", "first_contact"}
    assert replay["events"]["release"]["window"] == [1, 2]
    assert replay["events"]["first_contact"]["position"] == {"x": 150.0, "y": 200.0}
    assert replay["grades"] == {"bag": "GOOD"}


def _slide_scene(stop_at=40, vanish_at=None, n=70):
    rng = np.random.default_rng(1)
    base = np.full((240, 400, 3), 150, np.uint8)
    base = cv2.add(base, rng.integers(0, 8, base.shape, dtype=np.uint8))
    cv2.rectangle(base, (180, 120), (380, 160), (60, 60, 160), -1)   # a board
    frames, truth = [], {}
    for f in range(n):
        frame = base.copy()
        if f < 20:     # in the air, far away
            x, y = 40 + 5 * f, 40
        else:
            x, y = 200 + 4 * min(f - 20, stop_at - 20), 135
        if vanish_at is None or f < vanish_at:
            cv2.ellipse(frame, (int(x), int(y)), (12, 7), 0, 0, 360, (40, 40, 220), -1)
        frames.append(frame); truth[f] = (x, y)
    chains = {f: np.eye(3) for f in range(n)}
    flight = {f: truth[f] for f in range(0, 21)}
    return frames, chains, truth, flight


def test_after_contact_finds_rest():
    frames, chains, truth, flight = _slide_scene()
    out = track_after_contact(frames, chains, 20, truth[20], 0, FPS, 264.0, (4.0, 0.0), flight=flight)
    assert out["status"] == "rest_found"
    assert out["rest"]["x_release_frame"] == pytest.approx(truth[45][0], abs=2)
    assert out["rest"]["frame"] == pytest.approx(40, abs=3)


def test_after_contact_reports_a_vanished_bag_instead_of_guessing():
    frames, chains, truth, flight = _slide_scene(stop_at=60, vanish_at=30)
    out = track_after_contact(frames, chains, 20, truth[20], 0, FPS, 264.0, (4.0, 0.0), flight=flight)
    assert out["status"] == "lost_after_contact" and out["rest"] is None
