"""Launch uncertainty, gravity-constrained launch, gravity scale and release height."""
import numpy as np
import pytest

from cornhole_biomech.bag import SpatialCalibration, estimate_projectile_release_kinematics
from cornhole_biomech.flight import gravity_scale_from_flight, release_height

G = 9.80665
PPM = 180.0  # pixels per meter, similar to the pilot framing


def flight(fps=60.0, n=80, speed=7.0, angle_deg=35.0, noise=0.0, seed=0, target_right=True):
    """Image-pixel projectile (x right, y down) with gravity at PPM px/m."""
    t = np.arange(n) / fps
    vx, vy = speed * np.cos(np.radians(angle_deg)), speed * np.sin(np.radians(angle_deg))
    x = 300 + (1 if target_right else -1) * PPM * vx * t
    y = 600 - PPM * (vy * t - 0.5 * G * t**2)
    points = np.column_stack((x, y))
    if noise:
        points += np.random.default_rng(seed).normal(0, noise, points.shape)
    return points


def test_noise_free_launch_has_near_zero_standard_error():
    r = estimate_projectile_release_kinematics(flight(), 0, 60, 120, "left_to_right")
    assert r["velocity"]["angle_deg"] == pytest.approx(35.0, abs=1e-6)
    assert r["velocity_standard_error"]["angle_deg"] == pytest.approx(0.0, abs=1e-6)


def test_standard_error_tracks_monte_carlo_spread():
    angles, ses = [], []
    for seed in range(300):
        r = estimate_projectile_release_kinematics(flight(noise=2.0, seed=seed), 0, 60, 120, "left_to_right")
        if r["status"] == "estimated":
            angles.append(r["velocity"]["angle_deg"])
            ses.append(r["velocity_standard_error"]["angle_deg"])
    assert len(angles) > 250
    assert 0.6 < np.median(ses) / np.std(angles) < 1.6


def test_gravity_constrained_fit_is_unbiased_and_tighter_with_valid_scale():
    scale = SpatialCalibration(PPM, "athlete_release_motion_plane", True, "meter stick")
    free, constrained = [], []
    for seed in range(300):
        r = estimate_projectile_release_kinematics(flight(noise=2.0, seed=seed), 0, 60, 120, "left_to_right", scale)
        if r["status"] == "estimated":
            free.append(r["velocity"]["angle_deg"])
            constrained.append(r["gravity_constrained"]["angle_deg"])
    assert np.mean(constrained) == pytest.approx(35.0, abs=0.3)
    assert np.std(constrained) < 0.6 * np.std(free)


def test_gravity_constrained_block_absent_without_valid_scale():
    r = estimate_projectile_release_kinematics(flight(), 0, 60, 120, "left_to_right")
    assert r["gravity_constrained"] is None


def test_gravity_scale_recovers_pixels_per_meter_on_fixed_side_camera():
    result = gravity_scale_from_flight(flight(noise=1.0), 0, 75, 60, fixed_camera=True, camera_view="side")
    assert result["status"] == "estimated"
    assert result["pixels_per_meter"] == pytest.approx(PPM, rel=0.02)


@pytest.mark.parametrize("fixed,view", [(False, "side"), (True, "front")])
def test_gravity_scale_refused_for_moving_or_non_side_camera(fixed, view):
    result = gravity_scale_from_flight(flight(), 0, 75, 60, fixed_camera=fixed, camera_view=view)
    assert result["status"] != "estimated" and result["pixels_per_meter"] is None


def test_gravity_scale_needs_enough_reviewed_points():
    points = flight()
    points[5:70] = np.nan
    result = gravity_scale_from_flight(points, 0, 75, 60, fixed_camera=True, camera_view="side")
    assert result["status"] == "insufficient_flight_samples"


def test_apparent_gravity_cross_checks_an_independent_scale():
    wrong = gravity_scale_from_flight(flight(), 0, 75, 60, True, "side", reference_pixels_per_meter=PPM * 1.25)
    right = gravity_scale_from_flight(flight(), 0, 75, 60, True, "side", reference_pixels_per_meter=PPM)
    assert right["apparent_gravity_m_s2"] == pytest.approx(G, rel=0.01)
    assert wrong["apparent_gravity_m_s2"] == pytest.approx(G / 1.25, rel=0.01)


def test_release_height_uses_lowest_foot_point_and_scales():
    frames = 10
    landmarks = {
        "RHeel": np.tile([500.0, 900.0], (frames, 1)),
        "LBigToe": np.tile([560.0, 905.0], (frames, 1)),   # lowest foot point = floor
        "left_ankle": np.tile([540.0, 880.0], (frames, 1)),
    }
    bag = np.full((frames, 2), np.nan)
    bag[5] = (700.0, 725.0)
    r = release_height(bag, landmarks, release_frame=5, arm_length_px=120.0, pixels_per_meter=PPM)
    assert r["height_px"] == pytest.approx(180.0)
    assert r["height_arm_lengths"] == pytest.approx(1.5)
    assert r["height_m"] == pytest.approx(1.0)
    assert r["floor_reference"] == "lowest_heel_or_toe"


def test_release_height_falls_back_to_ankles_and_says_so():
    frames = 10
    landmarks = {"right_ankle": np.tile([500.0, 880.0], (frames, 1))}
    bag = np.full((frames, 2), np.nan)
    bag[5] = (700.0, 700.0)
    r = release_height(bag, landmarks, 5, 120.0, None)
    assert r["floor_reference"] == "lowest_ankle"
    assert r["height_m"] is None and r["height_px"] == pytest.approx(180.0)


def test_release_height_missing_bag_is_unavailable():
    r = release_height(np.full((10, 2), np.nan), {"RHeel": np.zeros((10, 2))}, 5, 120.0, PPM)
    assert r["height_px"] is None


def test_pipeline_reviewed_flight_uses_gravity_scale_constrained_launch_and_height(tmp_path):
    import json
    import cv2
    from cornhole_biomech import REQUIRED_LANDMARKS
    from cornhole_biomech.bag import BagAutomaticPoint, BagCorrectionSet, BagSeed, BagTrack
    from cornhole_biomech.models import PointEstimate, PoseFrame, PoseSequence, TrialContext
    from cornhole_biomech.pipeline import analyze_trial
    from cornhole_biomech.video import read_video_metadata

    fps, frames, release, contact = 60.0, 70, 10, 65
    video = tmp_path / "trial.mp4"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), fps, (96, 96))
    for _ in range(frames):
        writer.write(np.zeros((96, 96, 3), np.uint8))
    writer.release()
    pose_frames = []
    for f in range(frames):
        s = min(f, release) / release
        points = {"left_shoulder": (35, 32), "right_shoulder": (50, 32), "left_elbow": (30, 45),
                  "right_elbow": (52 + 4 * s, 45), "left_wrist": (27, 57),
                  "right_wrist": (54 + 10 * s, 58 - 4 * s), "left_hip": (38, 65), "right_hip": (51, 65)}
        marks = {n: PointEstimate(*points[n], 0.99) for n in REQUIRED_LANDMARKS}
        marks["RHeel"] = PointEstimate(50, 94, 0.9)
        marks["LBigToe"] = PointEstimate(40, 95, 0.9)
        pose_frames.append(PoseFrame(f, f / fps, marks))
    pose = tmp_path / "pose.json"
    PoseSequence(1, fps, 96, 96, frames, "test", "synthetic", "1", pose_frames).save(pose)

    ppm, speed, angle = 100.0, 6.0, 30.0
    vx, vy = speed * np.cos(np.radians(angle)), speed * np.sin(np.radians(angle))
    x0, y0 = 64.0, 54.0
    bag_points = []
    for f in range(frames):
        if f <= release:
            s = f / release
            x, y = 54 + 10 * s, 58 - 4 * s
        else:
            t = (f - release) / fps
            x, y = x0 + ppm * vx * t, y0 - ppm * (vy * t - 0.5 * G * t * t)
        bag_points.append(BagAutomaticPoint(f, x, y, 0.95))
    meta = read_video_metadata(video)
    track = tmp_path / "bag_raw_in.json"
    BagTrack(1, frames, 96, 96, meta.sha256, BagSeed(0, (50, 54, 8, 8)), "import", "synthetic",
             bag_points, "complete").save(track)
    out = tmp_path / "analysis"
    out.mkdir()
    BagCorrectionSet(reviewed_through_frame=frames - 1).save(out / "bag_corrections.json")
    (out / "events.json").write_text(json.dumps({"manual_overrides": {"release": release}}))
    (out / "flight_review.json").write_text(json.dumps({"first_contact_frame": contact, "fixed_camera": True}))

    result = analyze_trial(TrialContext("T1", "A1", "side", "right", "left_to_right", str(video)), out,
                           backend="rtmpose", pose_input=pose, bag_track_input=track, make_annotated_video=False)
    r = result["results"]
    s = r["summaries"]
    assert r["flight"]["gravity_scale"]["status"] == "estimated"
    assert r["flight"]["gravity_scale"]["pixels_per_meter"] == pytest.approx(ppm, rel=0.01)
    assert r["bag"]["launch"]["primary_model"] == "gravity_constrained_linear"
    assert s["bag_release_angle_deg"] == pytest.approx(angle, abs=0.5)
    assert s["bag_release_speed_m_s"] == pytest.approx(speed, rel=0.02)
    assert s["bag_release_height_m"] == pytest.approx((95 - y0) / ppm, abs=0.01)
    assert r["metrics_metadata"]["bag_release_height_m"]["units"] == "m"
