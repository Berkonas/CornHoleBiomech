"""Swing (pendulum) metrics from shoulder and wrist paths."""
import numpy as np
import pytest

from cornhole_biomech.swing import arm_angle_deg, swing_metrics

FPS = 60.0


def pendulum_arm(amplitude_deg=-60, release_deg=40, duration=0.5, arm_px=100.0, frames=120, start=20):
    """Shoulder fixed; wrist sweeps from backswing to past release with a smooth angle profile."""
    shoulder = np.tile([500.0, 300.0], (frames, 1))
    phi = np.full(frames, amplitude_deg, float)
    n = int(duration * FPS)
    s = np.linspace(0, 1, n)
    phi[start:start + n] = amplitude_deg + (release_deg + 30 - amplitude_deg) * (1 - np.cos(np.pi * s)) / 2
    phi[start + n:] = release_deg + 30
    rad = np.radians(phi)
    # Image coordinates, target to the right: forward = +x, up = −y.
    wrist = np.column_stack((500 + arm_px * np.sin(rad), 300 + arm_px * np.cos(rad)))
    return shoulder, wrist, phi


def test_arm_angle_convention():
    origin = np.array([[0.0, 0.0]])
    one = lambda w, d: float(arm_angle_deg(origin, np.array([w]), d)[0])   # single samples: no unwrapping
    assert [one(w, "left_to_right") for w in ([0, 10], [10, 0], [-10, 0], [0, -10])] == pytest.approx([0, 90, -90, 180])
    assert [one(w, "right_to_left") for w in ([0, 10], [10, 0], [-10, 0])] == pytest.approx([0, -90, 90])


def test_swing_metrics_recover_known_profile():
    shoulder, wrist, phi = pendulum_arm()
    release = int(np.argmin(np.abs(phi - 40)))
    m = swing_metrics(shoulder, wrist, FPS, "left_to_right", events={"motion_start": 5, "peak_backswing": 20,
                      "release": release, "peak_follow_through": 50}, arm_length_px=100.0)
    assert m["swing_backswing_angle_deg"] == pytest.approx(-60, abs=1.5)
    assert m["swing_release_arm_angle_deg"] == pytest.approx(40, abs=2.5)
    assert m["swing_peak_angular_velocity_deg_s"] == pytest.approx(np.pi / 2 * 130 / 0.5, rel=0.06)
    assert m["swing_forward_duration_s"] == pytest.approx((release - 20) / FPS)
    # The arm is still before frame 20 in this profile, so the backswing starts where motion begins.
    assert m["swing_backswing_start_frame"] <= 20
    # Hand speed = omega * radius, in arm lengths per second.
    omega = m["swing_angular_velocity_at_release_deg_s"]
    assert m["swing_hand_speed_at_release_arm_lengths_s"] == pytest.approx(np.radians(omega), rel=0.05)
    assert m["swing_pendulum_drive_ratio"] is None      # needs a physical scale


def test_pendulum_drive_ratio_is_one_for_a_passive_rod():
    g, L, A = 9.80665, 0.6, np.radians(60)
    ppm = 200.0
    omega_bottom = np.sqrt(3 * g * (1 - np.cos(A)) / L)            # passive uniform-rod pendulum
    frames = 200
    t = np.arange(frames) / FPS
    # Constant passive bottom speed through the bottom; release (frame 62) is before the clip at 80°.
    phi = -60 + np.degrees(omega_bottom) * (t - t[40])
    phi = np.clip(phi, -60, 80)
    rad = np.radians(phi)
    shoulder = np.tile([500.0, 300.0], (frames, 1))
    wrist = np.column_stack((500 + L * ppm * np.sin(rad), 300 + L * ppm * np.cos(rad)))
    m = swing_metrics(shoulder, wrist, FPS, "left_to_right",
                      events={"motion_start": 30, "peak_backswing": 40, "release": 62, "peak_follow_through": 90},
                      arm_length_px=L * ppm, pixels_per_meter=ppm)
    assert m["swing_pendulum_drive_ratio"] == pytest.approx(1.0, rel=0.05)
    assert m["swing_hand_speed_at_release_m_s"] == pytest.approx(omega_bottom * L, rel=0.05)


def test_missing_events_leave_metrics_unavailable():
    shoulder, wrist, _ = pendulum_arm()
    m = swing_metrics(shoulder, wrist, FPS, "left_to_right", events={}, arm_length_px=100.0)
    assert m["swing_release_arm_angle_deg"] is None and m["swing_tempo_ratio"] is None
