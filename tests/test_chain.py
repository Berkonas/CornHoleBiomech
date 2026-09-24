import math

import numpy as np
import pytest

from cornhole_biomech.bag import GRAVITY_M_S2 as G
from cornhole_biomech.chain import (body_chain, build_chain, flatten_for_summaries, hand_chain, quantity,
                                    release_chain, scale_relative_sd)
from cornhole_biomech.regulation import BAG_MASS_KG

FPS = 60.0


def test_quantity_shape():
    q = quantity(1.0, "m", "measured", "x = 1")
    assert set(q) >= {"value", "unit", "state", "formula", "reason", "interval", "assumptions"}


def test_body_chain_peak_order_proximal_to_distal():
    n, release = 120, 90
    shoulder = 40 * np.tanh((np.arange(n) - 60) / 8.0)          # fastest at frame 60
    elbow = 150 + 20 * np.tanh((np.arange(n) - 75) / 5.0)        # extends fastest at frame 75
    out = body_chain({"arm_to_trunk_deg": shoulder, "elbow_angle_deg": elbow}, FPS, 40, release)
    assert out["shoulder_peak_time_rel_release_ms"]["value"] == pytest.approx(1000 * (60 - 90) / FPS, abs=17)
    assert out["elbow_peak_time_rel_release_ms"]["value"] == pytest.approx(1000 * (75 - 90) / FPS, abs=17)
    assert out["peak_sequence"]["value"].startswith("shoulder → elbow")
    assert out["peak_sequence"]["state"] == "measured"
    assert out["wrist_peak_speed_time_rel_release_ms"]["state"] == "unavailable"


def test_body_chain_includes_wrist_speed_peak_when_given():
    n, release = 120, 90
    shoulder = 40 * np.tanh((np.arange(n) - 60) / 8.0)
    elbow = 150 + 20 * np.tanh((np.arange(n) - 75) / 5.0)
    wrist_speed = np.exp(-((np.arange(n) - 84) / 6.0) ** 2)
    out = body_chain({"arm_to_trunk_deg": shoulder, "elbow_angle_deg": elbow}, FPS, 40, release,
                     wrist_speed=wrist_speed)
    assert out["wrist_peak_speed_time_rel_release_ms"]["value"] == pytest.approx(1000 * (84 - 90) / FPS, abs=17)
    assert out["peak_sequence"]["value"] == "shoulder → elbow → wrist → release"
    assert out["peak_sequence"]["lags_ms"]["shoulder → elbow"] == pytest.approx(1000 * 15 / FPS, abs=17)


def _circular_swing(n=90, release=60, r=0.6, w=6.0):
    t = np.arange(n) / FPS
    th = -math.pi / 2 + w * (t - t[release]) * 0.3
    shoulder = np.tile([0.0, 1.4], (n, 1))
    wrist = shoulder + np.column_stack([r * np.cos(th), r * np.sin(th)]) * (1 / (1 + 0.34 * 1.0))
    elbow = shoulder + 0.5 * (wrist - shoulder)
    return shoulder, elbow, wrist, release


def test_hand_chain_force_vector_for_circular_swing():
    # Rigid arm swinging on a circle at constant ω: hand force = m(−ω²r r̂ − g⃗)
    shoulder, elbow, wrist, release = _circular_swing()
    out = hand_chain(shoulder, elbow, wrist, FPS, 20, release)
    f = np.asarray(out["series"]["force_n"])[release]
    assert f[1] > BAG_MASS_KG * G      # at the bottom of the swing the hand pulls up more than the weight
    assert out["quantities"]["peak_net_force_on_bag_n"]["unit"] == "N"
    assert "Bag-only" in out["quantities"]["peak_net_force_on_bag_n"]["assumptions"][0]


def test_hand_chain_values_match_the_analytic_circle():
    shoulder, elbow, wrist, release = _circular_swing()
    omega, r = 6.0 * 0.3, 0.6
    out = hand_chain(shoulder, elbow, wrist, FPS, 20, release)
    q = out["quantities"]
    assert q["hand_speed_at_release_m_s"]["value"] == pytest.approx(omega * r, rel=1e-3)
    assert q["hand_acceleration_at_release_m_s2"]["value"] == pytest.approx(omega**2 * r, rel=1e-2)
    # |F| = m |a − g⃗| = m (ω² r + g) at the bottom: the peak over the swing is at least that.
    assert q["peak_net_force_on_bag_n"]["value"] >= BAG_MASS_KG * (omega**2 * r + G) * 0.99
    # F·v agrees with dE/dt for a smooth path, so power is reported.
    assert q["peak_power_on_bag_w"]["state"] != "unavailable"
    assert q["peak_power_on_bag_w"]["reason"] != "power estimates disagree"


def test_hand_chain_noise_gives_intervals_and_downgrades_noisy_force():
    shoulder, elbow, wrist, release = _circular_swing()
    quiet = hand_chain(shoulder, elbow, wrist, FPS, 20, release, landmark_noise_m=0.0005, draws=200)
    noisy = hand_chain(shoulder, elbow, wrist, FPS, 20, release, landmark_noise_m=0.05, draws=200)
    lo, hi = quiet["quantities"]["peak_net_force_on_bag_n"]["interval"]
    assert lo <= quiet["quantities"]["peak_net_force_on_bag_n"]["value"] <= hi
    assert quiet["quantities"]["peak_net_force_on_bag_n"]["state"] == "measured"
    assert noisy["quantities"]["hand_acceleration_at_release_m_s2"]["state"] == "estimated"
    assert "interval" in noisy["quantities"]["hand_acceleration_at_release_m_s2"]["reason"]


def test_hand_chain_scale_state_caps_every_metre_quantity():
    shoulder, elbow, wrist, release = _circular_swing()
    out = hand_chain(shoulder, elbow, wrist, FPS, 20, release, landmark_noise_m=0.0005, draws=100,
                     scale_state="estimated", scale_reason="HFOV at the band edge")
    for name, item in out["quantities"].items():
        assert item["state"] in ("estimated", "unavailable"), name
        if item["state"] == "estimated":
            assert "HFOV at the band edge" in item["reason"], name


def test_release_chain_intervals_contain_nominal():
    out = release_chain(8.5, 32.0, 0.95, 7.3, {"speed": 0.1, "angle": 1.0, "height": 0.02}, draws=300, seed=1)
    ke = out["kinetic_energy_j"]
    assert ke["value"] == pytest.approx(0.5 * BAG_MASS_KG * 8.5**2)
    lo, hi = ke["interval"]
    assert lo < ke["value"] < hi
    assert out["energy_match_percent"]["state"] in ("measured", "estimated")


def test_release_chain_without_distance_keeps_energies_and_withholds_the_flight_model():
    out = release_chain(8.0, 30.0, 1.0, None, {"speed": 0.1, "angle": 1.0, "height": 0.02}, draws=100,
                        scale_state="estimated", scale_reason="gravity scale")
    assert out["momentum_kg_m_s"]["value"] == pytest.approx(BAG_MASS_KG * 8.0)
    assert out["momentum_kg_m_s"]["state"] == "estimated" and "gravity scale" in out["momentum_kg_m_s"]["reason"]
    assert out["release_angle_deg"]["state"] == "measured"          # an angle does not depend on the scale
    for name in ("energy_match_percent", "speed_margin_over_minimum_percent", "predicted_along_error_in"):
        assert out[name]["state"] == "unavailable"


def test_release_chain_energy_match_is_zero_at_the_required_speed():
    from cornhole_biomech.mechanics import minimum_speed, required_speed
    from cornhole_biomech.regulation import Board
    v = required_speed(35.0, 1.0, 7.5, Board())
    out = release_chain(v, 35.0, 1.0, 7.5, {}, draws=50)
    assert out["energy_match_percent"]["value"] == pytest.approx(0.0, abs=1e-9)
    assert out["predicted_along_error_in"]["value"] == pytest.approx(0.0, abs=0.05)
    margin = 100 * (v / minimum_speed(1.0, 7.5, Board()) - 1)
    assert out["speed_margin_over_minimum_percent"]["value"] == pytest.approx(margin)


def test_flatten_skips_unavailable():
    chain = {"quantities": {"a": quantity(1.0, "m", "measured", "a"),
                            "b": quantity(None, "m", "unavailable", "b", reason="no data")}}
    flat = flatten_for_summaries(chain)
    assert flat == {"chain_a": 1.0, "chain_b": None}


def test_scale_relative_sd_prefers_the_session_iqr():
    ppm_at = lambda h: 100.0 * 65.0 / h          # toy: scale inversely proportional to HFOV
    session = {"pixels_per_meter": 100.0, "hfov_deg": 65.0, "hfov_iqr_deg": 4.0,
               "pixels_per_meter_at_55_deg": 118.0, "pixels_per_meter_at_75_deg": 86.7}
    sd, basis = scale_relative_sd(session, ppm_at)
    expected = abs(ppm_at(63.0) - ppm_at(67.0)) / 100.0 / 2
    assert sd == pytest.approx(expected)
    assert "IQR" in basis
    single = {**session, "hfov_iqr_deg": None}
    sd, basis = scale_relative_sd(single, ppm_at)
    assert sd == pytest.approx((118.0 - 86.7) / 100.0 / 4)
    assert "55" in basis
    sd, basis = scale_relative_sd({"pixels_per_meter": None}, ppm_at)
    assert sd == pytest.approx(0.05)


def test_build_chain_without_joints_states_why():
    n, release = 120, 90
    shoulder = 40 * np.tanh((np.arange(n) - 60) / 8.0)
    elbow = 150 + 20 * np.tanh((np.arange(n) - 75) / 5.0)
    chain = build_chain(angles={"arm_to_trunk_deg": shoulder, "elbow_angle_deg": elbow}, fps=FPS, forward_swing=40,
                        release=release, joints_m=None, joints_reason="Board not located.",
                        release_values={"speed": None, "angle": None, "height": None}, release_se={},
                        to_front_m=None, measured_along_error_m=None)
    q = chain["quantities"]
    assert q["peak_net_force_on_bag_n"]["state"] == "unavailable"
    assert "Board not located." in q["peak_net_force_on_bag_n"]["reason"]
    assert q["kinetic_energy_j"]["state"] == "unavailable"
    assert q["peak_sequence"]["state"] == "measured"
    assert any("Bag-only" in note for note in chain["notes"])
    flat = flatten_for_summaries(chain)
    assert flat["chain_peak_net_force_on_bag_n"] is None
    assert flat["chain_peak_sequence"] is None           # strings never go into numeric summaries


def _rendered_scene(true_hfov=62.0):
    """A board and a side-on arm rendered with a known camera; returns (auto_flight, filtered, landmarks, truth)."""
    import cv2

    from cornhole_biomech.board import camera_matrix, order_corners
    from cornhole_biomech.regulation import Board
    W, H = 1920, 1080
    b = Board()
    Lh, fh = b.horizontal_length_m, b.front_height_m
    bh, w = fh + b.length_m * math.sin(b.angle), b.width_m
    obj = np.array([[0, fh, -w / 2], [0, fh, w / 2], [Lh, bh, w / 2], [Lh, bh, -w / 2]])
    R_look = cv2.Rodrigues(np.array([0.0, math.radians(8.0), 0.0]))[0]
    R_tilt = cv2.Rodrigues(np.array([math.radians(8.0), 0.0, 0.0]))[0]
    flip = np.array([[1, 0, 0], [0, -1, 0], [0, 0, -1]], float)
    rvec, _ = cv2.Rodrigues(R_tilt @ R_look @ flip)
    tvec = np.array([[1.5], [1.2], [6.0]])
    K = camera_matrix(W, H, true_hfov)
    project = lambda pts: cv2.projectPoints(np.asarray(pts, float), rvec, tvec, K, None)[0].reshape(-1, 2)
    corners = order_corners(project(obj), "left_to_right")
    shoulder, elbow, wrist, release = _circular_swing()
    offset = np.array([-1.0, 0.0])           # arm 1 m in front of the board's front edge, in its plane
    to3d = lambda p: np.column_stack([p[:, 0] + offset[0], p[:, 1], np.zeros(len(p))])
    filtered = np.stack([project(to3d(j)) for j in (shoulder, elbow, wrist)], axis=1)
    identity = {str(f): [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]] for f in range(len(wrist))}
    auto_flight = {"width": W, "height": H, "release_frame": release, "camera_to_release": identity,
                   "board": {"status": "found", "corners_px": corners.tolist(), "reference_frame": release}}
    truth = {"shoulder": shoulder + offset, "elbow": elbow + offset, "wrist": wrist + offset}
    return auto_flight, filtered, ("right_shoulder", "right_elbow", "right_wrist"), truth


def test_throw_plane_joints_use_the_scale_hfov_and_recover_metres():
    from cornhole_biomech.pipeline import _throw_plane_joints
    auto_flight, filtered, landmarks, truth = _rendered_scene(true_hfov=62.0)
    joints, model, reason = _throw_plane_joints(auto_flight, {"hfov_deg": 62.0}, filtered, landmarks, "right",
                                                auto_flight["camera_to_release"])
    assert reason is None and model.hfov_deg == 62.0
    for name in ("shoulder", "elbow", "wrist"):
        assert np.allclose(joints[name], truth[name], atol=1e-3), name
    wrong, _, _ = _throw_plane_joints(auto_flight, {"hfov_deg": 75.0}, filtered, landmarks, "right",
                                      auto_flight["camera_to_release"])
    assert not np.allclose(wrong["wrist"], truth["wrist"], atol=1e-2)   # the HFOV passed in is really used


def test_throw_plane_joints_refuse_a_board_in_another_frame_or_without_hfov():
    from cornhole_biomech.pipeline import _throw_plane_joints
    auto_flight, filtered, landmarks, _ = _rendered_scene()
    other = {**auto_flight, "board": {**auto_flight["board"], "reference_frame": 10}}
    joints, _, reason = _throw_plane_joints(other, {"hfov_deg": 62.0}, filtered, landmarks, "right",
                                            auto_flight["camera_to_release"])
    assert joints is None and "frame 10" in reason
    joints, _, reason = _throw_plane_joints(auto_flight, {"hfov_deg": None, "reason": "no flight"}, filtered,
                                            landmarks, "right", auto_flight["camera_to_release"])
    assert joints is None and "no flight" in reason


def test_throw_chain_end_to_end_on_a_rendered_scene():
    from cornhole_biomech.pipeline import _throw_chain
    auto_flight, filtered, landmarks, truth = _rendered_scene(true_hfov=62.0)
    n = len(filtered)
    release = auto_flight["release_frame"]
    fit_points = filtered[:, 2, :].copy()        # bag at the wrist in this toy scene
    scale = {"status": "estimated", "reason": "HFOV at band edge", "hfov_deg": 62.0, "pixels_per_meter": 150.0,
             "pixels_per_meter_at_55_deg": 170.0, "pixels_per_meter_at_75_deg": 120.0}
    summaries = {"bag_release_speed_m_s": 8.0, "bag_release_angle_deg": 30.0, "bag_release_speed_se_m_s": 0.1,
                 "bag_release_angle_se_deg": 1.0, "landing_along_error_m": 0.1}
    chain = _throw_chain(auto_flight=auto_flight, board_scale=scale, filtered=filtered, landmarks=landmarks,
                         side="right", camera_to_release=auto_flight["camera_to_release"],
                         angles={"arm_to_trunk_deg": np.linspace(0, 60, n), "elbow_angle_deg": np.full(n, 170.0)},
                         fps=FPS, forward_swing=20, release_frame=release, fit_points=fit_points,
                         summaries=summaries, wrist_speed=None)
    q = chain["quantities"]
    assert chain["release_to_board_front_m"] == pytest.approx(-truth["wrist"][release][0], abs=1e-3)
    assert q["release_height_m"]["value"] == pytest.approx(truth["wrist"][release][1], abs=1e-3)
    assert q["kinetic_energy_j"]["state"] == "estimated" and "HFOV at band edge" in q["kinetic_energy_j"]["reason"]
    assert q["release_angle_deg"]["state"] == "measured"
    assert q["peak_net_force_on_bag_n"]["state"] == "estimated"
    assert q["timing_sensitivity_in_per_10ms"]["state"] == "estimated"
    assert q["measured_along_error_in"]["value"] == pytest.approx(0.1 / 0.0254)
    assert chain["scale"]["relative_sd"] == pytest.approx(50.0 / 150.0 / 4)


def test_peak_sequence_places_release_by_time_when_a_peak_follows_it():
    n, release = 120, 90
    shoulder = 40 * np.tanh((np.arange(n) - 95) / 3.0)            # shoulder peaks 5 frames after release
    elbow = 150 + 20 * np.tanh((np.arange(n) - 75) / 5.0)
    out = body_chain({"arm_to_trunk_deg": shoulder, "elbow_angle_deg": elbow}, FPS, 40, release)
    seq = out["peak_sequence"]
    assert seq["value"] == "elbow → release → shoulder"
    assert seq["lags_ms"]["release → shoulder"] == pytest.approx(1000 * 5 / FPS, abs=17)
    assert all(v >= 0 for v in seq["lags_ms"].values())


def test_force_direction_needs_its_own_narrow_interval():
    shoulder, elbow, wrist, release = _circular_swing()
    out = hand_chain(shoulder, elbow, wrist, FPS, 20, release, landmark_noise_m=0.0005, draws=200)
    direction = out["quantities"]["force_direction_at_peak_deg"]
    assert direction["state"] == "measured"
    lo, hi = direction["interval"]
    assert lo <= direction["value"] <= hi
    noisy = hand_chain(shoulder, elbow, wrist, FPS, 20, release, landmark_noise_m=0.03, draws=200)
    d = noisy["quantities"]["force_direction_at_peak_deg"]
    assert d["state"] == "estimated" and "°" in d["reason"]


def test_implausibly_early_forward_swing_falls_back_to_a_window_before_release():
    n, release = 600, 500
    shoulder = 40 * np.tanh((np.arange(n) - 470) / 8.0)
    elbow = 150 + 20 * np.tanh((np.arange(n) - 485) / 5.0) + 60 * np.tanh((np.arange(n) - 100) / 2.0)
    out = body_chain({"arm_to_trunk_deg": shoulder, "elbow_angle_deg": elbow}, FPS, 50, release)
    # The fast "extension" at frame 100 is 6.7 s before release: outside any plausible forward swing.
    assert out["elbow_peak_time_rel_release_ms"]["value"] == pytest.approx(1000 * (485 - 500) / FPS, abs=17)
    assert any("forward-swing event" in a for a in out["elbow_peak_time_rel_release_ms"]["assumptions"])


def test_timing_sensitivity_reason_when_the_hand_moves_away_from_the_board():
    from cornhole_biomech.regulation import Board
    shoulder, elbow, wrist, release = _circular_swing()
    shift = np.array([-7.0, -0.4])
    # Reverse time: the hand now swings backward (away from the board) through release.
    rev = lambda a: (a + shift)[::-1].copy()
    out = hand_chain(rev(shoulder), rev(elbow), rev(wrist), FPS, 20, len(wrist) - 1 - release, board=Board())
    item = out["quantities"]["timing_sensitivity_in_per_10ms"]
    assert item["state"] == "unavailable" and "does not reach the board" in item["reason"]
    ok = hand_chain(shoulder + shift, elbow + shift, wrist + shift, FPS, 20, release, board=Board())
    assert ok["quantities"]["timing_sensitivity_in_per_10ms"]["state"] == "estimated"
