import numpy as np
import pytest

from cornhole_biomech.comparison import (
    assert_compatible_views,
    build_reference_set,
    compare_normalized,
)
from cornhole_biomech.events import EVENT_ORDER, apply_manual_event_overrides, detect_events
from cornhole_biomech.kinematics import calculate_kinematics


LANDMARKS = (
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
)


def skeleton_sequence(frames=101):
    t = np.linspace(0, 1, frames)
    data = np.zeros((frames, len(LANDMARKS), 2), float)
    points = {
        "left_shoulder": np.column_stack((100 + 2*t, np.full(frames, 100))),
        "right_shoulder": np.column_stack((140 + 2*t, np.full(frames, 100))),
        "left_elbow": np.column_stack((80 + 2*t, 140 - 15*np.sin(np.pi*t))),
        "right_elbow": np.column_stack((175 + 30*t, 130 - 10*np.sin(np.pi*t))),
        "left_wrist": np.column_stack((65 + 2*t, 175 - 20*np.sin(np.pi*t))),
        "right_wrist": np.column_stack((190 + 80*t, 170 - 35*np.sin(np.pi*t))),
        "left_hip": np.column_stack((105 + 2*t, np.full(frames, 210))),
        "right_hip": np.column_stack((135 + 2*t, np.full(frames, 210))),
    }
    for i, name in enumerate(LANDMARKS):
        data[:, i] = points[name]
    return data


def test_kinematics_are_scale_and_translation_invariant():
    base = skeleton_sequence()
    result = calculate_kinematics(base, LANDMARKS, 60, "right", "left_to_right")
    transformed = base * 2 + np.array([400.0, -80.0])
    other = calculate_kinematics(transformed, LANDMARKS, 60, "right", "left_to_right")
    for field in ("elbow_angle_deg", "arm_to_trunk_deg", "trunk_inclination_deg",
                  "wrist_path_arm_lengths", "elbow_path_arm_lengths"):
        np.testing.assert_allclose(result.values[field], other.values[field], atol=1e-10)


def test_mirrored_left_throw_matches_throw_centered_right_throw():
    right = skeleton_sequence()
    mirrored = right.copy()
    mirrored[..., 0] = 500 - mirrored[..., 0]
    swap_pairs = ((0, 1), (2, 3), (4, 5), (6, 7))
    for a, b in swap_pairs:
        mirrored[:, [a, b]] = mirrored[:, [b, a]]
    right_result = calculate_kinematics(right, LANDMARKS, 60, "right", "left_to_right")
    left_result = calculate_kinematics(mirrored, LANDMARKS, 60, "left", "right_to_left")
    for field in ("elbow_angle_deg", "upper_arm_orientation_deg", "forearm_orientation_deg",
                  "arm_to_trunk_deg", "trunk_inclination_deg", "wrist_path_arm_lengths"):
        np.testing.assert_allclose(right_result.values[field], left_result.values[field], atol=1e-10)


def test_events_are_ordered_and_manual_values_preserve_automatic():
    t = np.linspace(0, 1, 101)
    wrist = np.column_stack((-0.3*np.sin(2*np.pi*t) + 1.2*t, 0.2*np.sin(np.pi*t)))
    events = detect_events(wrist, 100)
    frames = [events[name].effective_frame for name in EVENT_ORDER]
    assert frames == sorted(frames)
    automatic = events["release"].automatic_frame
    corrected = apply_manual_event_overrides(events, {"release": automatic + 1})
    assert corrected["release"].automatic_frame == automatic
    assert corrected["release"].manual_frame == automatic + 1


def test_comparison_reports_raw_errors():
    reference = {"elbow_angle_deg": np.linspace(80, 140, 101),
                 "wrist_path_arm_lengths": np.column_stack((np.linspace(0, 1, 101), np.zeros(101)))}
    test = {"elbow_angle_deg": reference["elbow_angle_deg"] + 3,
            "wrist_path_arm_lengths": reference["wrist_path_arm_lengths"] + np.array([0, 0.1])}
    refset = build_reference_set([reference])
    metrics = compare_normalized(test, refset, {"release": 0.55}, {"release": 0.50})
    assert metrics["elbow_angle_mae_deg"] == pytest.approx(3)
    assert metrics["wrist_path_rmse_arm_lengths"] == pytest.approx(0.1)


def test_incompatible_views_are_blocked():
    with pytest.raises(ValueError, match="incompatible"):
        assert_compatible_views("side", ["side", "front"])



def _ramp(a, b, n):
    """Smooth (cosine) move from a to b over n frames."""
    return a + (b - a) * (1 - np.cos(np.linspace(0, np.pi, n))) / 2


def realistic_throw_wrist(fps=60):
    """Shoulder-relative wrist (arm lengths, x toward the target, y up) for one throw.

    Frames 0–39: practice swings while walking in (arm angle 40° ± 30°, faster than the
    motion threshold); 40–79: arm raised slowly to the aiming position at 60°; 80–119: backswing 60° → −40° (top at 119);
    120–139: forward swing −40° → 85° (release ≈ 136, arm still rising); 140–169: the
    follow-through keeps rising to 140° while slowing down; 170–209: hold; 210–239: arm lowered.
    """
    phi = np.concatenate([
        40 + 30 * np.sin(np.linspace(0, 3 * np.pi, 40)),
        np.full(40, 40.0) + _ramp(0, 20, 40),
        _ramp(60, -40, 40),
        _ramp(-40, 85, 20),
        _ramp(85, 140, 30),
        np.full(40, 140.0),
        _ramp(140, 0, 30),
    ])
    r = np.radians(phi)
    return np.column_stack((np.sin(r), -np.cos(r))), phi


def test_motion_start_ignores_pre_throw_fidget_and_follow_through_is_the_highest_point():
    from cornhole_biomech.models import EventValue
    wrist, phi = realistic_throw_wrist()
    release = EventValue("release", automatic_frame=136, automatic_confidence=1.0, automatic_method="bag")
    events = detect_events(wrist, 60, release)
    frames = {name: events[name].effective_frame for name in EVENT_ORDER}
    assert frames["release"] == 136                       # release is untouched
    assert frames["peak_backswing"] == pytest.approx(119, abs=1)
    # The practice swings at frames 0–39 are faster than the motion threshold; the throw starts
    # where the backswing leaves the aiming position (frame 80; the wrist crosses the motion
    # threshold a few frames later), not at the first movement in the clip.
    assert 76 <= frames["motion_start"] <= 86
    # The wrist is most forward at φ = 90° (just after release); the follow-through keeps rising
    # until the arm reaches its highest point at frame ~169.
    assert frames["peak_follow_through"] == pytest.approx(int(np.argmax(phi[136:220])) + 136, abs=6)
    assert frames["peak_follow_through"] > 160
    assert list(frames.values()) == sorted(frames.values())


def test_held_follow_through_marks_arrival_at_the_top_not_a_frame_inside_the_hold():
    wrist, phi = realistic_throw_wrist()
    wrist = wrist.copy()
    wrist[170:210, 1] += 0.01 * np.sin(np.arange(40))      # a held pose wobbles by < 0.02 arm lengths
    events = detect_events(wrist, 60)
    assert 160 <= events["peak_follow_through"].effective_frame <= 171


def test_motion_start_falls_back_when_the_wrist_never_goes_quiet():
    t = np.arange(240) / 60
    wrist = np.column_stack((np.sin(2 * np.pi * 0.8 * t), np.cos(2 * np.pi * 0.8 * t)))
    events = detect_events(wrist, 60)
    frames = [events[name].effective_frame for name in EVENT_ORDER]
    assert frames == sorted(frames)
    assert events["motion_start"].effective_frame is not None
