"""Known-answer tests from the calculation audit (docs/CALCULATION_AUDIT.md).

Each test builds a synthetic movement whose answer is known in closed form (a rigid arm rotating at
a known rate, a projectile with known launch, a slide with known friction, ...) and checks the engine
recovers it. Section letters match the audit document.
"""
import itertools
import math

import cv2
import numpy as np
import pytest

from cornhole_biomech.bag import (GRAVITY_M_S2, SpatialCalibration, estimate_projectile_release_kinematics,
                                  plane_launch_fit)
from cornhole_biomech.board import _deck_object_points, calibrate_hfov_from_flight, solve_board
from cornhole_biomech.board_phase import MAX_MU_SE, SLIDE_SETTLE_S, slide_kinematics
from cornhole_biomech.chain import hand_chain, release_chain
from cornhole_biomech.events import RELEASE_AFTER_PEAK_WRIST_SPEED_S, _sustained, detect_events
from cornhole_biomech.filtering import derivative, lowpass_zero_phase
from cornhole_biomech.flight import gravity_scale_from_flight
from cornhole_biomech.kinematics import calculate_kinematics
from cornhole_biomech.mechanics import along_error_m, minimum_speed, required_speed
from cornhole_biomech.performance import cliffs_delta, critical_delta, hedges_g
from cornhole_biomech.regulation import BAG_MASS_KG, INCH_M, Board
from cornhole_biomech.swing import swing_metrics

FPS = 60000 / 1001          # phone "60 fps"
LANDMARKS = ("left_shoulder", "right_shoulder", "left_elbow", "right_elbow", "left_wrist", "right_wrist",
             "left_hip", "right_hip")


# ------------------------------------------------------------------------------------------ helpers

def _pose(flexion_deg, elbow_deg=180.0, trunk_lean_deg=0.0, direction="left_to_right", side="right",
          upper=60.0, fore=55.0, trunk=150.0, origin=(900.0, 400.0)):
    """Image-pixel pose of a side view from analysis-axis geometry (x toward the target, y up).

    Shoulder flexion is the upper arm's angle from the trunk's downward axis (+ toward the target);
    the elbow flexes the forearm forward by 180 − elbow_deg. Both shoulders overlap (side view).
    """
    f = np.radians(np.atleast_1d(np.asarray(flexion_deg, float)))
    n = len(f)
    lean = math.radians(trunk_lean_deg)
    down = np.array([-math.sin(lean), -math.cos(lean)])               # shoulder -> hip direction
    shoulder = np.zeros((n, 2))
    hip = shoulder + trunk * down
    rot = lambda v, a: np.column_stack([v[0] * np.cos(a) - v[1] * np.sin(a), v[0] * np.sin(a) + v[1] * np.cos(a)])
    arm_dir = rot(down, f)                                             # counter-clockwise = forward
    elbow = shoulder + upper * arm_dir
    fore_dir = rot(down, f + math.radians(180.0 - elbow_deg))
    wrist = elbow + fore * fore_dir
    sign = 1.0 if direction == "left_to_right" else -1.0
    to_img = lambda p: np.column_stack([origin[0] + sign * p[:, 0], origin[1] - p[:, 1]])
    pts = {f"{s}_{j}": to_img(v) for s in ("left", "right") for j, v in
           (("shoulder", shoulder), ("hip", hip))}
    other = "left" if side == "right" else "right"
    pts[f"{side}_elbow"], pts[f"{side}_wrist"] = to_img(elbow), to_img(wrist)
    pts[f"{other}_elbow"], pts[f"{other}_wrist"] = to_img(shoulder + upper * down), to_img(shoulder + (upper + fore) * down)
    return np.stack([pts[name] for name in LANDMARKS], axis=1)


def _camera(hfov=62.0, centre=(-2.2, 1.1, 6.0), look=(-2.2, 0.7, 0.0), size=(1920, 1080)):
    """Pinhole camera in the board frame (x toward the back of the board, y up, z toward the camera)."""
    c = np.array(centre, float)
    fwd = np.array(look, float) - c
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, [0.0, 1.0, 0.0])
    right /= np.linalg.norm(right)
    R = np.vstack([right, np.cross(fwd, right), fwd])
    f = (size[0] / 2) / math.tan(math.radians(hfov) / 2)
    K = np.array([[f, 0, size[0] / 2], [0, f, size[1] / 2], [0, 0, 1.0]])
    return lambda P: (lambda X: X[:, :2] / X[:, 2:])((K @ ((R @ np.asarray(P, float).T).T - R @ c).T).T)


def _flight(v0=7.0, angle=40.0, x0=-5.5, y0=1.0, z=0.0, duration=0.55):
    t = np.arange(0, duration, 1 / FPS)
    th = math.radians(angle)
    return t, np.column_stack([x0 + v0 * math.cos(th) * t, y0 + v0 * math.sin(th) * t - 0.5 * GRAVITY_M_S2 * t ** 2,
                               np.full_like(t, z)])


# ---------------------------------------------------------------------------- A. body kinematics

def test_a1_elbow_trunk_and_shoulder_angles_are_exact_and_mirror_invariant():
    flexion = np.linspace(-50, 120, 40)
    results = []
    for direction, side in (("left_to_right", "right"), ("right_to_left", "right"), ("right_to_left", "left")):
        coords = _pose(flexion, elbow_deg=150.0, trunk_lean_deg=12.0, direction=direction, side=side)
        k = calculate_kinematics(coords, LANDMARKS, FPS, side, direction)
        results.append(k.values)
        assert k.values["elbow_angle_deg"] == pytest.approx(np.full(40, 150.0), abs=1e-9)
        assert k.values["trunk_inclination_deg"] == pytest.approx(np.full(40, 12.0), abs=1e-9)
        assert k.values["arm_to_trunk_deg"] == pytest.approx(180.0 - flexion, abs=1e-9)
    for other in results[1:]:     # filmed the other way round, or a left-hander: identical numbers
        for key in ("elbow_angle_deg", "arm_to_trunk_deg", "trunk_inclination_deg", "wrist_path_arm_lengths"):
            assert np.allclose(other[key], results[0][key], atol=1e-9)


def test_a3_shoulder_angle_is_continuous_through_the_trunk_line():
    """Upper arm swinging from 60° behind the trunk to 150° in front at 300°/s.

    The old unsigned angle folded at 180° where the arm crossed the trunk: ROM 150° instead of 210°
    and |dθ/dt| collapsing to ~0 at the crossing frame. The continuous angle is exact.
    """
    rate = 300.0
    t = np.arange(0, 210.0 / rate, 1 / FPS)
    flexion = -60.0 + rate * t
    k = calculate_kinematics(_pose(flexion), LANDMARKS, FPS, "right", "left_to_right")
    angle = k.values["arm_to_trunk_deg"]
    assert np.nanmax(angle) - np.nanmin(angle) == pytest.approx(rate * t[-1], abs=1e-6)
    assert k.values["arm_to_trunk_velocity_deg_s"] == pytest.approx(np.full(len(t), -rate), rel=1e-6)
    folded = np.degrees(np.arccos(np.clip(np.cos(np.radians(angle)), -1, 1)))      # the old definition
    assert np.min(np.abs(derivative(folded, FPS))) < 0.5 * rate                      # the dip that was removed


def test_a3_shoulder_angle_overhead_follow_through_has_no_wrap():
    flexion = np.linspace(-70, 200, 60)          # deeper than any pilot backswing, past vertical overhead
    k = calculate_kinematics(_pose(flexion), LANDMARKS, FPS, "right", "left_to_right")
    assert k.values["arm_to_trunk_deg"] == pytest.approx(180.0 - flexion, abs=1e-9)


def test_a4_pendulum_drive_ratio_of_a_passive_rod_is_one():
    """Uniform rigid rod released from rest at A = −60°: θ'' = −(3g / 2L) sin θ (RK4, 0.1 ms steps)."""
    L, ppm, amp = 0.70, 200.0, math.radians(-60.0)
    dt = 1e-4
    theta, omega, t, samples = amp, 0.0, 0.0, []
    k = 3 * GRAVITY_M_S2 / (2 * L)
    acc = lambda th: -k * math.sin(th)
    for frame in range(60):
        samples.append(theta)
        target = (frame + 1) / FPS
        while t < target - 1e-12:
            h = min(dt, target - t)
            k1t, k1w = omega, acc(theta)
            k2t, k2w = omega + 0.5 * h * k1w, acc(theta + 0.5 * h * k1t)
            k3t, k3w = omega + 0.5 * h * k2w, acc(theta + 0.5 * h * k2t)
            k4t, k4w = omega + h * k3w, acc(theta + h * k3t)
            theta += h / 6 * (k1t + 2 * k2t + 2 * k3t + k4t)
            omega += h / 6 * (k1w + 2 * k2w + 2 * k3w + k4w)
            t += h
    phi = np.array([math.radians(-60.0)] * 10 + samples)
    shoulder = np.tile([500.0, 300.0], (len(phi), 1))
    wrist = shoulder + L * ppm * np.column_stack([np.sin(phi), np.cos(phi)])     # image y down
    release = int(np.flatnonzero(np.degrees(phi) > 40)[0])
    out = swing_metrics(shoulder, wrist, FPS, "left_to_right", {"peak_backswing": 10, "release": release},
                        L * ppm, pixels_per_meter=ppm)
    assert out["swing_backswing_angle_deg"] == pytest.approx(-60.0, abs=0.01)
    assert out["swing_pendulum_drive_ratio"] == pytest.approx(1.0, abs=0.02)


def test_a5_orientation_velocity_is_unwrapped_through_180_degrees():
    # Forearm rotating at 400°/s from 150° to 270° (through ±180°) about a fixed elbow; ≥ 16 frames, the
    # shortest run the zero-phase filter smooths (shorter runs give no velocity).
    t = np.arange(0, 0.3, 1 / FPS)
    orient = np.radians(150 + 400 * t)
    coords = _pose(np.zeros(len(t)))
    elbow = coords[:, LANDMARKS.index("right_elbow")]
    coords[:, LANDMARKS.index("right_wrist")] = elbow + 55 * np.column_stack([np.cos(orient), -np.sin(orient)])
    k = calculate_kinematics(coords, LANDMARKS, FPS, "right", "left_to_right")
    assert k.values["forearm_orientation_velocity_deg_s"] == pytest.approx(np.full(len(t), 400.0), rel=1e-6)


def test_a6_time_base_uses_the_real_frame_rate():
    coords = np.repeat(_pose([0.0]), 30, axis=0)
    coords[:, LANDMARKS.index("right_wrist"), 0] += 100.0 * np.arange(30) / FPS     # 100 px/s
    k = calculate_kinematics(coords, LANDMARKS, FPS, "right", "left_to_right")
    assert k.time_seconds[29] == pytest.approx(29 * 1001 / 60000)
    assert np.nanmedian(k.values["wrist_global_speed_px_s"]) == pytest.approx(100.0, rel=1e-9)


# ---------------------------------------------------------------- B. filtering and differentiation

@pytest.mark.parametrize("freq,gain", [(1.0, 1.0), (3.0, 1 / (1 + 0.5 ** 8)), (6.0, 0.5)])
def test_b1_butterworth_zero_phase_gain_is_h_squared(freq, gain):
    t = np.arange(0, 20, 1 / FPS)
    out = lowpass_zero_phase(np.sin(2 * np.pi * freq * t), FPS)[0]
    mid = slice(len(t) // 4, 3 * len(t) // 4)
    assert np.max(np.abs(out[mid])) == pytest.approx(gain, abs=0.005)


@pytest.mark.parametrize("fwhm_s,retained", [(0.24, 0.972), (0.14, 0.926)])
def test_b2_filter_keeps_peak_timing_and_flattens_peak_speed_by_a_known_amount(fwhm_s, retained):
    """Rigid 100 px arm whose angular speed is a Gaussian pulse (real wrist pulses: FWHM 0.23–0.38 s)."""
    sigma = fwhm_s / 2.3548
    t = np.arange(0, 3, 1 / FPS)
    omega = np.radians(700) * np.exp(-0.5 * ((t - 1.5003) / sigma) ** 2)
    phi = np.cumsum(omega) / FPS
    xy = 100 * np.column_stack([np.sin(phi), -np.cos(phi)])
    truth = np.linalg.norm(derivative(xy, FPS), axis=1)
    filtered = np.linalg.norm(derivative(lowpass_zero_phase(xy, FPS)[0], FPS), axis=1)
    assert np.argmax(filtered) == np.argmax(truth)                           # zero phase: no timing shift
    assert filtered.max() / truth.max() == pytest.approx(retained, abs=0.005)


def test_b3_ramps_edges_and_gaps():
    ramp = np.arange(200, dtype=float) * 2.5 + 7
    out = lowpass_zero_phase(ramp, FPS)[0]
    assert out[25:-25] == pytest.approx(ramp[25:-25], abs=1e-3)      # a ramp passes the filter unchanged
    assert np.max(np.abs(out - ramp)) < 0.1                          # edge transient < 0.1 px at 150 px/s
    gappy = np.sin(np.arange(80) / 5.0)
    gappy[30:33] = np.nan
    gappy[70:] = np.nan
    gappy[60] = np.nan                                                       # 61..69 is a 9-sample run
    out, _, warnings = lowpass_zero_phase(gappy, FPS)
    assert np.isnan(out[[30, 31, 32, 60]]).all() and np.isnan(out[70:]).all()  # missing stays missing
    assert out[61:70] == pytest.approx(gappy[61:70]) and warnings              # too short: left raw, warned
    q = 3 * (np.arange(10) / FPS) ** 2 - np.arange(10) / FPS
    assert derivative(q, FPS) == pytest.approx(6 * np.arange(10) / FPS - 1, abs=1e-9)   # exact for quadratics
    d = derivative(gappy, FPS)
    assert np.isnan(d[[30, 31, 32]]).all()                                   # gaps never bridged


# ------------------------------------------------------------------------------------- C. events

def test_c1_sustained_keeps_every_frame_of_a_long_enough_run():
    mask = np.zeros(30, bool)
    mask[10:21] = True
    mask[25:27] = True
    for count in (2, 3, 6):
        kept = np.flatnonzero(_sustained(mask, count))
        assert kept[0] == 10 and 20 in kept and (count > 2) != (26 in kept)


def test_c2_events_on_a_synthetic_swing():
    """Aim hold, eased backswing to −60° (top at frame 54), forward swing to 150°, held follow-through."""
    phi = np.concatenate([np.full(30, 20.0),
                          20 - 80 * (1 - np.cos(np.pi * np.arange(25) / 24)) / 2,
                          -60 + 210 * (1 - np.cos(np.pi * np.arange(1, 32) / 31)) / 2,
                          np.full(60, 150.0)])
    r = np.radians(phi)
    wrist = np.column_stack([np.sin(r), -np.cos(r)])                          # arm lengths, shoulder-relative
    ev = {k: v.automatic_frame for k, v in detect_events(wrist, FPS).items()}
    velocity = derivative(wrist, FPS)
    speed = np.linalg.norm(velocity, axis=1)
    threshold = max(0.05, 0.12 * speed.max())
    assert ev["peak_backswing"] == 54
    assert 29 <= ev["motion_start"] <= 33
    assert ev["motion_end"] == int(np.flatnonzero(speed >= threshold)[-1])    # was one frame early
    peak = int(np.argmax(velocity[:, 0]))
    assert ev["release"] == peak + round(RELEASE_AFTER_PEAK_WRIST_SPEED_S * FPS)
    window = wrist[ev["release"]:ev["motion_end"] + 1, 1]          # highest point in [release, motion end]
    assert ev["peak_follow_through"] == ev["release"] + int(np.flatnonzero(window >= window.max() - 0.02)[0])


# ----------------------------------------------------------------------- D. bag flight and scale

def _launch_pixels(rng, v0=7.0, angle=38.0, ppm=120.0, noise=1.5, direction="left_to_right", n=30):
    t = np.arange(n) / FPS
    th = math.radians(angle)
    sign = 1.0 if direction == "left_to_right" else -1.0
    x = 960 + sign * v0 * math.cos(th) * ppm * t
    y = 500 - v0 * math.sin(th) * ppm * t + 0.5 * GRAVITY_M_S2 * ppm * t ** 2
    return np.column_stack([x, y]) + rng.normal(0, noise, (n, 2))


def test_d1_launch_fit_is_unbiased_and_its_standard_error_is_honest():
    rng = np.random.default_rng(7)
    cal = SpatialCalibration(120.0, "board_throw_plane", True, "test")
    speed, angle, se_angle, se_speed = [], [], [], []
    for _ in range(300):
        est = estimate_projectile_release_kinematics(_launch_pixels(rng), 0, FPS, 140.0, "left_to_right", cal)
        g = est["gravity_constrained"]
        speed.append(g["speed_m_s"]); angle.append(g["angle_deg"])
        se_angle.append(g["standard_error"]["angle_deg"]); se_speed.append(g["standard_error"]["speed_m_s"])
    speed, angle = np.array(speed), np.array(angle)
    assert speed.mean() == pytest.approx(7.0, rel=0.005)
    assert angle.mean() == pytest.approx(38.0, abs=0.15)
    # Fit SEs match the real scatter (within 30 %) and the ±1.96 SE interval covers 88–99 % of draws.
    assert np.median(se_angle) == pytest.approx(angle.std(ddof=1), rel=0.3)
    assert np.median(se_speed) == pytest.approx(speed.std(ddof=1), rel=0.3)
    cover = np.mean(np.abs(angle - 38.0) <= 1.96 * np.array(se_angle))
    assert 0.88 <= cover <= 0.99


def test_d1_launch_fit_is_mirror_invariant():
    cal = SpatialCalibration(120.0, "board_throw_plane", True, "test")
    a = estimate_projectile_release_kinematics(_launch_pixels(np.random.default_rng(1), noise=0), 0, FPS, 140.0,
                                               "left_to_right", cal)["gravity_constrained"]
    b = estimate_projectile_release_kinematics(_launch_pixels(np.random.default_rng(1), noise=0,
                                                              direction="right_to_left"), 0, FPS, 140.0,
                                               "right_to_left", cal)["gravity_constrained"]
    assert (a["speed_m_s"], a["angle_deg"]) == pytest.approx((7.0, 38.0), abs=1e-6)
    assert (b["speed_m_s"], b["angle_deg"]) == pytest.approx((a["speed_m_s"], a["angle_deg"]), abs=1e-9)


@pytest.mark.parametrize("camera_x,pixel_error_deg", [(-2.2, (0.4, 1.2)), (-1.0, (2.5, 4.5))])
def test_d2_gravity_calibrated_fov_and_plane_launch_recover_a_known_throw(camera_x, pixel_error_deg):
    """Synthetic phone (HFOV 62°) 6 m to the side; bag launched at 7 m/s, 40° in the board's centre plane."""
    project = _camera(centre=(camera_x, 1.1, 6.0))
    corners = project(_deck_object_points(Board()))
    t, world = _flight()
    px = project(world)
    cal = calibrate_hfov_from_flight(corners, (1920, 1080), px, np.arange(len(t)), FPS)
    assert cal["status"] == "measured" and cal["hfov_deg"] == pytest.approx(62.0, abs=0.05)
    model = solve_board(corners, (1920, 1080), hfov_deg=cal["hfov_deg"])
    plane = plane_launch_fit(px, 0, FPS, model.to_plane)
    assert (plane["speed_m_s"], plane["angle_deg"]) == pytest.approx((7.0, 40.0), abs=0.01)
    assert model.to_plane(px[:1])[0] == pytest.approx([-5.5, 1.0], abs=0.002)        # release point, height
    # The pixel fit + one horizontal scale is off by a known amount (audit §D2), hence the plane fit.
    pixel = estimate_projectile_release_kinematics(
        px, 0, FPS, 140.0, "left_to_right",
        SpatialCalibration(cal["pixels_per_meter"], "board_throw_plane", True, "test"))["gravity_constrained"]
    assert pixel_error_deg[0] < abs(pixel["angle_deg"] - 40.0) < pixel_error_deg[1]


def test_d2_pipeline_uses_the_plane_fit_only_when_the_board_is_in_the_release_frame():
    """`pipeline._plane_launch` maps the release-frame pixels through the board and recovers 7 m/s, 40°;
    a board measured in another frame, or no field of view, leaves it unavailable with a reason."""
    from cornhole_biomech.pipeline import _plane_launch
    project = _camera(centre=(-1.0, 1.1, 6.0))
    corners = project(_deck_object_points(Board()))
    t, world = _flight()
    px = project(world)
    px[3] = np.nan                                                  # a gap in the window is tolerated
    identity = {str(f): [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]] for f in range(len(t))}
    auto_flight = {"width": 1920, "height": 1080, "release_frame": 0, "camera_to_release": identity,
                   "board": {"status": "found", "corners_px": corners.tolist(), "reference_frame": 0}}
    config = {"release_fit_window_seconds": 0.12, "minimum_velocity_points": 4}
    fit = _plane_launch(auto_flight, {"hfov_deg": 62.0}, identity, px, 0, FPS, config)
    assert fit["status"] == "measured" and fit["model"] == "gravity_constrained_linear_throw_plane"
    assert (fit["speed_m_s"], fit["angle_deg"]) == pytest.approx((7.0, 40.0), abs=0.02)
    other = {**auto_flight, "board": {**auto_flight["board"], "reference_frame": 5}}
    assert _plane_launch(other, {"hfov_deg": 62.0}, identity, px, 0, FPS, config)["status"] == "unavailable"
    missing = _plane_launch(auto_flight, {"hfov_deg": None, "reason": "no flight"}, identity, px, 0, FPS, config)
    assert missing["status"] == "unavailable" and "no flight" in missing["reason"]


def test_d3_bag_flying_off_the_board_centre_line_biases_the_scale():
    """Bag released 0.4 m nearer the camera than the board's centre line (thrower beside the board):
    the gravity calibration absorbs it into the FOV (62° → 55.6°); in the plane the release is then
    −0.4 % in speed, +1.2° in angle and 8 cm low (the current pixel route: −2.7 % in speed)."""
    project = _camera()
    corners = project(_deck_object_points(Board()))
    t, world = _flight(z=0.4)
    px = project(world)
    cal = calibrate_hfov_from_flight(corners, (1920, 1080), px, np.arange(len(t)), FPS)
    model = solve_board(corners, (1920, 1080), hfov_deg=cal["hfov_deg"])
    plane = plane_launch_fit(px, 0, FPS, model.to_plane)
    assert abs(plane["speed_m_s"] / 7.0 - 1) < 0.01                 # speed nearly kept (−0.4 %)
    assert 0.5 < plane["angle_deg"] - 40.0 < 2.0                     # angle +1.2°
    assert -0.10 < model.to_plane(px[:1])[0][1] - 1.0 < -0.05       # release height −8 cm


def test_d4_gravity_scale_from_a_fixed_camera_flight():
    rng = np.random.default_rng(3)
    pts = _launch_pixels(rng, ppm=150.0, noise=1.0, n=40)
    out = gravity_scale_from_flight(pts, 0, 39, FPS, True, "side")
    assert out["pixels_per_meter"] == pytest.approx(150.0, rel=0.02)
    assert abs(out["pixels_per_meter"] - 150.0) < 3 * out["pixels_per_meter_se"]


# ------------------------------------------------------------------------------- E. board phase

def _slide(mu, v0=2.4, duration=0.3, noise_in=0.0, impact=(), seed=0):
    board = Board()
    a = GRAVITY_M_S2 * (math.sin(board.angle) + mu * math.cos(board.angle))
    t = np.arange(0, duration, 1 / FPS)
    s = (v0 * t - 0.5 * a * t ** 2) / INCH_M + 20.0
    s += np.random.default_rng(seed).normal(0, noise_in, len(t))
    for i, offset in enumerate(impact):
        s[i] += offset
    return t, s, board.angle


def test_e1_friction_equation_and_incline():
    t, s, alpha = _slide(0.4)
    kin = slide_kinematics(t, s, alpha)
    assert kin["mu_effective"] == pytest.approx(0.4, abs=1e-6)
    assert kin["entry_speed_m_s"] == pytest.approx(2.4, abs=1e-6)
    a = kin["deceleration_m_s2"]
    assert kin["mu_effective"] == pytest.approx(a / (GRAVITY_M_S2 * math.cos(alpha)) - math.tan(alpha))


def test_e2_impact_transient_no_longer_gives_negative_friction():
    """Pilot slides: the touchdown sample sat ~1.5 in AHEAD of the later slide (e.g. 21.8, 22.2, 24.2,
    26.0 in: a first step of 0.4 in, then ~2 in per frame), and the plain-deck window before the hole was
    often only 0.1–0.2 s. True μ = 0.4, 0.1 in noise."""
    def old_mu(t, s, alpha):                                   # the previous fit used every sample
        c = np.polyfit(t, s * INCH_M, 2)
        return (-2 * c[0] / GRAVITY_M_S2 - math.sin(alpha)) / math.cos(alpha)
    t, s, alpha = _slide(0.4, duration=0.15, noise_in=0.1, impact=(1.5,))
    assert old_mu(t, s, alpha) < 0                             # the negative μ the council saw
    kin = slide_kinematics(t, s, alpha)
    assert kin["mu_effective"] is None and kin["mu_se"] > MAX_MU_SE   # too short to resolve: withheld
    t, s, alpha = _slide(0.4, duration=0.2, noise_in=0.1, impact=(1.5,))
    assert old_mu(t, s, alpha) < 0.1
    kin = slide_kinematics(t, s, alpha)
    assert kin["fit"]["from_s"] >= SLIDE_SETTLE_S - 1e-9
    assert kin["mu_effective"] == pytest.approx(0.4, abs=0.05) and kin["mu_se"] <= MAX_MU_SE


def test_e3_unresolved_or_non_frictional_slides_are_withheld():
    t, s, alpha = _slide(0.4, duration=0.13, noise_in=0.3, seed=2)       # 0.1 s of plain deck, noisy
    kin = slide_kinematics(t, s, alpha)
    assert kin["mu_effective"] is None and kin["deceleration_m_s2"] is None
    assert "standard error" in kin["reason"] or "g sin" in kin["reason"]
    t, s, alpha = _slide(-0.1)                                            # slows less than g sin α alone
    kin = slide_kinematics(t, s, alpha)
    assert kin["mu_effective"] is None and kin["fit"]["deceleration_m_s2"] > 0 and "g sin" in kin["reason"]
    kin = slide_kinematics(t, 40 - (s - 20), alpha)                      # sliding back down the deck
    assert kin["mu_effective"] is None


# --------------------------------------------------------------------- F. bag mechanics and model

def test_f1_hand_point_on_a_rigid_arm_rotating_at_constant_rate():
    """Straight 0.6 m arm, ω = 6 rad/s, φ −60° → +60°: bag point radius R = 0.6 (1 + 0.34) m."""
    omega, arm = 6.0, 0.6
    t = (np.arange(40) - 15) / FPS                    # bottom of the swing exactly at frame 15
    phi = omega * t
    release = 25                                      # φ = 57°, interior frame
    unit = np.column_stack([np.sin(phi), -np.cos(phi)])
    shoulder = np.tile([0.0, 1.5], (len(t), 1))
    out = hand_chain(shoulder, shoulder + 0.3 * unit, shoulder + arm * unit, FPS, 0, release, draws=0)
    q = out["quantities"]
    R = arm * 1.34
    assert q["hand_speed_at_release_m_s"]["value"] == pytest.approx(omega * R, rel=0.003)
    assert q["hand_acceleration_at_release_m_s2"]["value"] == pytest.approx(omega ** 2 * R, rel=0.01)
    assert q["peak_net_force_on_bag_n"]["value"] == pytest.approx(BAG_MASS_KG * (omega ** 2 * R + GRAVITY_M_S2),
                                                                  rel=0.01)   # at the bottom, a points up
    # a ⟂ v, so P = F·v = m g v_y, largest at release; equals dE/dt.
    assert q["peak_power_on_bag_w"]["value"] == pytest.approx(
        BAG_MASS_KG * GRAVITY_M_S2 * omega * R * math.sin(phi[release]), rel=0.01)
    assert "disagree" not in (q["peak_power_on_bag_w"]["reason"] or "")


def test_f2_release_energies_and_flight_model():
    chain = release_chain(7.0, 40.0, 1.0, 5.5, {}, rel_scale_sd=0.0, draws=50)
    assert chain["kinetic_energy_j"]["value"] == pytest.approx(0.5 * BAG_MASS_KG * 49.0)
    assert chain["potential_energy_j"]["value"] == pytest.approx(BAG_MASS_KG * GRAVITY_M_S2 * 1.0)
    board = Board()
    for angle in (25.0, 40.0, 55.0):
        v = required_speed(angle, 1.0, 5.5, board)
        th = math.radians(angle)
        assert along_error_m(v * math.cos(th), v * math.sin(th), 1.0, 5.5, board) == pytest.approx(0.0, abs=1e-6)
    brute = min(required_speed(a, 1.0, 5.5, board) or np.inf for a in np.arange(10, 80, 0.01))
    assert minimum_speed(1.0, 5.5, board) == pytest.approx(brute, rel=1e-6)


# ------------------------------------------------------------------------------- G. statistics

def test_g1_effect_sizes_known_answers():
    assert cliffs_delta([6, 7, 8, 9, 10], [1, 2, 3, 4, 5]) == 1.0
    assert cliffs_delta([1, 2, 3], [1, 2, 3]) == 0.0
    a, b = np.array([1.0, 2, 3, 4, 5]), np.array([3.0, 4, 5, 6, 7])
    assert hedges_g(a, b) == pytest.approx(-2 / math.sqrt(2.5) * (1 - 3 / 31))


def test_g2_critical_delta_false_positive_rate_at_the_smallest_groups():
    """Exact permutation null for 5 vs 5 (252 splits): normal-approximation δ_crit = 0.75 is crossed
    by 14/252 = 5.6 % of splits — slightly above the nominal 5 % (stated limitation)."""
    crit = critical_delta(5, 5, comparisons=1)
    assert crit == pytest.approx(1.96 * math.sqrt(11 / 75), abs=1e-3)
    values = np.arange(10.0)
    hits = sum(abs(cliffs_delta(values[list(c)], np.delete(values, list(c)))) >= crit
               for c in itertools.combinations(range(10), 5))
    assert hits == 14


def test_a3_foreshortened_upper_arm_across_the_cut_gives_no_spurious_rom_or_velocity():
    """Flexion −120° → −130° (across the −125° cut) with the upper arm pointing almost at the camera (6 px of a
    60 px segment): its 2D direction is noise, so those frames are missing instead of a 360° ROM."""
    n = 80
    flexion = np.linspace(-120.0, -130.0, n)
    coords = _pose(flexion)
    shoulder = coords[:, LANDMARKS.index("right_shoulder")]
    elbow = coords[:, LANDMARKS.index("right_elbow")]
    wrist = coords[:, LANDMARKS.index("right_wrist")]
    short = slice(36, 44)
    coords[short, LANDMARKS.index("right_elbow")] = shoulder[short] + 0.1 * (elbow[short] - shoulder[short])
    coords[short, LANDMARKS.index("right_wrist")] = coords[short, LANDMARKS.index("right_elbow")] + (wrist[short] - elbow[short])
    k = calculate_kinematics(coords, LANDMARKS, FPS, "right", "left_to_right")
    angle = k.values["arm_to_trunk_deg"]
    assert np.isnan(angle[short]).all()
    assert np.nanmax(angle) - np.nanmin(angle) < 15.0
    assert np.nanmax(np.abs(k.values["arm_to_trunk_velocity_deg_s"])) < 100.0


def test_short_unfiltered_runs_give_no_velocity():
    from cornhole_biomech.filtering import FILTERED_MIN_RUN, derivative
    series = np.full(60, np.nan)
    series[5:5 + FILTERED_MIN_RUN - 1] = np.arange(FILTERED_MIN_RUN - 1)       # 15 samples: left raw by the filter
    series[30:50] = np.arange(20)
    v = derivative(series, 60.0, FILTERED_MIN_RUN)
    assert np.isnan(v[5:20]).all() and np.allclose(v[30:50], 60.0)


def test_outcome_with_a_source_field_is_accepted():
    """The app records who entered a result (`source`); the engine must read such outcomes (insights crashed)."""
    from cornhole_biomech.models import TrialOutcome
    outcome = TrialOutcome(intended_target="Hole center", score_category=1, throw_type="Standard", source="person")
    assert outcome.source == "person"
