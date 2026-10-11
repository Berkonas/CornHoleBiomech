"""3D bag flight from the side and front cameras (flight3d.py): synthetic cameras, known projectile."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")
pytest.importorskip("scipy")

from cornhole_biomech import flight3d as f3  # noqa: E402
from cornhole_biomech import front_view as fv  # noqa: E402
from cornhole_biomech import two_view as tv  # noqa: E402
from cornhole_biomech.board import _deck_object_points  # noqa: E402
from cornhole_biomech.regulation import BAG_SIDE_M, INCH_M, Board  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from swift_contract import problems  # noqa: E402

G = 9.80665
SIDE_FPS, FRONT_FPS = 59.94, 30.0
SIDE_SIZE, FRONT_SIZE = (1920, 1080), (1280, 720)
SIDE_HFOV = 60.0
RELEASE_SIDE = 100
SYNC_T0 = 0.4                     # front time of side frame 0
TRUE = {"x0": 0.15, "vx": -0.12, "y0": -5.8, "vy": 5.6, "z0": 1.0, "vz": 3.0}


def _look_at(centre, target, up):
    f = np.asarray(target, float) - centre
    f /= np.linalg.norm(f)
    r = np.cross(f, up)
    r /= np.linalg.norm(r)
    d = np.cross(f, r)
    R = np.vstack([r, d, f])
    return R, -R @ centre


def _K(size, hfov):
    f = (size[0] / 2) / math.tan(math.radians(hfov) / 2)
    return np.array([[f, 0, size[0] / 2], [0, f, size[1] / 2], [0, 0, 1.0]])


def _project(K, R, t, pts):
    cam = (R @ np.asarray(pts, float).reshape(-1, 3).T).T + t
    return np.column_stack([K[0, 0] * cam[:, 0] / cam[:, 2] + K[0, 2], K[1, 1] * cam[:, 1] / cam[:, 2] + K[1, 2]]), cam[:, 2]


def _world(tau, p=TRUE):
    tau = np.asarray(tau, float)
    return np.column_stack([p["x0"] + p["vx"] * tau, p["y0"] + p["vy"] * tau,
                            p["z0"] + p["vz"] * tau - 0.5 * G * tau ** 2])


def _scene(*, front_hfov=66.0, timing_shift_s=0.0, clutter=True, keep_share=0.8, seed=1, p=TRUE, flight_ok=True,
           bag_frames=None):
    """Synthetic throw: side camera stabilized points, front candidates with clutter, the dicts reconstruct_flight
    reads. ``timing_shift_s``: the front camera really shows the bag this much later than the sync says."""
    rng = np.random.default_rng(seed)
    # Side camera (board frame x along, y up, z across = thrower's right for a left-to-right throw).
    Ks = _K(SIDE_SIZE, SIDE_HFOV)
    Rs, ts = _look_at(np.array([-2.8, 1.3, 7.0]), np.array([-2.8, 1.0, 0.0]), np.array([0.0, 1.0, 0.0]))
    side_corners, _ = _project(Ks, Rs, ts, _deck_object_points(Board()))
    side_times = np.arange(400) / SIDE_FPS
    # Landing: where the arc meets the deck surface (centre 0.6 in above it).
    taus = np.arange(0, 2.5, 0.0005)
    w = _world(taus, p)
    deck = Board().front_height_m + w[:, 1] * math.tan(Board().angle) + 0.6 * INCH_M
    on = (w[:, 1] >= 0) & (w[:, 1] <= Board().horizontal_length_m) & (np.abs(w[:, 0]) <= Board().width_m / 2)
    land_tau = float(taus[np.nonzero((w[:, 2] <= np.where(on, deck, 0.6 * INCH_M)) & (taus > 0.3))[0][0]])
    contact_side = RELEASE_SIDE + int(round(land_tau * SIDE_FPS))
    frames_side = np.arange(RELEASE_SIDE, contact_side - 1)
    tau_s = side_times[frames_side] - side_times[RELEASE_SIDE]
    ws = _world(tau_s, p)
    px_s, _ = _project(Ks, Rs, ts, np.column_stack([ws[:, 1], ws[:, 2], ws[:, 0]]))
    px_s += rng.normal(0, 0.5, px_s.shape)
    stabilized = [{"frame": int(f), "x": float(x), "y": float(y)} for f, (x, y) in zip(frames_side, px_s)]
    # Front camera behind the board, looking back at the thrower (image mirrored), slow drift down the image.
    Kf = _K(FRONT_SIZE, front_hfov)
    Rf, tf = _look_at(np.array([0.03, 5.15, 1.27]), np.array([0.0, -4.0, 0.8]), np.array([0.0, 0.0, 1.0]))
    n_front = 140
    front_times = np.arange(n_front) / FRONT_FPS
    deck_px, _ = _project(Kf, Rf, tf, fv.deck_object_points())
    drift = np.column_stack([np.zeros(n_front), 0.15 * np.arange(n_front)])
    corners = np.stack([deck_px + d for d in drift])
    to_side = SYNC_T0 + side_times[RELEASE_SIDE]
    release_front = int(round(to_side * FRONT_FPS))
    contact_front = int(round((SYNC_T0 + side_times[contact_side]) * FRONT_FPS))
    cands, seen = {}, 0
    for k in range(release_front - 2, min(n_front, contact_front + 3)):
        tau = front_times[k] - to_side - timing_shift_s
        blobs = []
        if 0 <= tau <= land_tau and rng.random() < keep_share and (bag_frames is None or seen < bag_frames):
            seen += 1
            px, depth = _project(Kf, Rf, tf, _world([tau], p))
            area = (Kf[0, 0] * BAG_SIDE_M / depth[0]) ** 2 * rng.uniform(0.4, 0.9)
            blobs.append([*(px[0] + drift[k] + rng.normal(0, 1.0, 2)), area])
        if clutter:
            for _ in range(4):        # static-ish clutter (wall, posters, people) of bag-like size
                blobs.append([rng.uniform(300, 1000), rng.uniform(100, 600), rng.uniform(100, 900)])
            # the thrower's arm swinging up, and a bystander walking across
            blobs.append([700 + 2 * (k - release_front), 330 - 6 * (k - release_front), 250.0])
            blobs.append([200 + 9 * (k - release_front), 300.0, 400.0])
        cands[k] = np.array(blobs, float).reshape(-1, 3)
    results = {"scale": {"hfov_deg": SIDE_HFOV, "status": "measured"}, "target_direction": "left_to_right",
               "quality": {"frame_rate_fps": SIDE_FPS}, "bag": {"flight_filter": {"rejected_outlier_frames": []}}}
    auto_flight = {"status": "accepted" if flight_ok else "needs_review", "release_frame": RELEASE_SIDE,
                   "board": {"status": "found", "corners_px": side_corners.tolist(), "reference_frame": RELEASE_SIDE},
                   "stabilized_points": stabilized, "width": SIDE_SIZE[0], "height": SIDE_SIZE[1]}
    link = {"side_clip": {"frame_times_s": side_times.tolist(), "fps": SIDE_FPS, "frame_count": len(side_times)},
            "front_clip": {"frame_times_s": front_times.tolist(), "fps": FRONT_FPS, "side_frame0_front_time_s": SYNC_T0},
            "front_lag_s": 0.0}
    blank = np.zeros((FRONT_SIZE[1], FRONT_SIZE[0], 3), np.uint8)
    true_land_x = float(_world([land_tau], p)[0, 0])
    return dict(frames=[blank] * n_front, results=results, auto_flight=auto_flight, link=link, corners_per_frame=corners,
                release_side=RELEASE_SIDE, contact_side=contact_side, release_front=release_front,
                contact_front=contact_front, candidates=cands), true_land_x


def _run(scene, **kw):
    args = {"front_hfov_deg": 66.0, "camera_status": "measured", **kw}
    return f3.reconstruct_flight(**scene, **args)


def test_side_rays_at_the_centre_line_match_the_board_throw_plane():
    scene, _ = _scene(clutter=False)
    af = scene["auto_flight"]
    px = np.array([[p["x"], p["y"]] for p in af["stabilized_points"][:10]])
    centre, rays, model = f3.side_rays(af["board"]["corners_px"], SIDE_SIZE, SIDE_HFOV, px)
    np.testing.assert_allclose(f3.rays_at_lateral(centre, rays, np.zeros(len(px))), model.to_plane(px), atol=1e-6)


def test_side_model_put_at_the_true_lateral_recovers_the_flight():
    scene, _ = _scene(clutter=False)
    side_times = np.asarray(scene["link"]["side_clip"]["frame_times_s"])
    side = f3.side_flight(scene["results"], scene["auto_flight"], side_times, RELEASE_SIDE)
    at_true = f3.fit_side_model(side, TRUE["x0"] + TRUE["vx"] * side["tau"])
    in_plane = f3.fit_side_model(side, 0.0)
    assert at_true["along"][0] == pytest.approx(TRUE["y0"], abs=0.01)
    assert at_true["along"][1] == pytest.approx(TRUE["vy"], abs=0.05)
    assert at_true["height"][1] == pytest.approx(TRUE["vz"], abs=0.05)
    assert at_true["apparent_gravity_m_s2"] == pytest.approx(G, rel=0.02)
    # A bag 15 cm towards the side camera looks closer and larger when assumed in the centre plane.
    assert abs(in_plane["along"][0] - TRUE["y0"]) > abs(at_true["along"][0] - TRUE["y0"])


def test_recovers_lateral_release_and_velocity_through_clutter():
    scene, true_land = _scene()
    out = _run(scene)
    assert out["status"] == "measured", out.get("reason")
    assert out["release"]["lateral_m"] == pytest.approx(TRUE["x0"], abs=0.02)
    assert out["velocity_m_s"]["lateral"] == pytest.approx(TRUE["vx"], abs=0.04)
    assert out["lateral_launch_angle_deg"] == pytest.approx(math.degrees(math.atan2(TRUE["vx"], TRUE["vy"])), abs=0.4)
    assert (out["landing"]["predicted_x_in"] - 12.0) * INCH_M == pytest.approx(true_land, abs=0.03)
    assert out["fit"]["inlier_frames"] >= 0.7 * out["fit"]["frames_searched"]
    # Clutter is never taken: every detection lies on the bag's own projection.
    assert all(d["residual_px"] < 6 for d in out["detections"])
    # Path samples run from release to first contact; the image path covers the front frames in between.
    assert out["path_m"][0]["x_m"] == 0.0 and out["path_m"][-1]["z_m"] < 0.4
    assert out["front_path"][0]["frame"] >= scene["release_front"] - 1


def test_wrong_pooled_front_field_of_view_is_corrected_by_the_side_heights():
    scene, _ = _scene(front_hfov=63.0)
    out = _run(scene, front_hfov_deg=66.0)
    assert out["status"] == "measured", out.get("reason")
    assert out["fit"]["front_hfov_deg"] == pytest.approx(63.0, abs=1.0)
    assert out["release"]["lateral_m"] == pytest.approx(TRUE["x0"], abs=0.02)


def test_timing_offset_between_the_cameras_is_measured():
    scene, _ = _scene(timing_shift_s=1.0 / FRONT_FPS)
    out = _run(scene)
    assert out["status"] == "measured", out.get("reason")
    assert out["fit"]["timing_offset_s"] == pytest.approx(-1.0 / FRONT_FPS, abs=0.01)
    assert out["release"]["lateral_m"] == pytest.approx(TRUE["x0"], abs=0.02)


def test_front_first_contact_is_an_end_constraint_only_when_it_agrees():
    scene, true_land = _scene()
    agree = _run(scene, front_contact={"x_in": true_land / INCH_M + 12.0 + 1.0})
    assert agree["fit"]["contact_constraint_used"] is True
    assert agree["landing"]["flight_only_difference_in"] == pytest.approx(-1.0, abs=1.5)
    far = _run(scene, front_contact={"x_in": true_land / INCH_M + 12.0 + 10.0})
    assert far["fit"]["contact_constraint_used"] is False
    assert far["release"]["lateral_m"] == pytest.approx(TRUE["x0"], abs=0.02)


def test_wide_throw_to_the_left_is_followed():
    p = {**TRUE, "x0": -0.2, "vx": -0.9}
    scene, true_land = _scene(p=p)
    out = _run(scene)
    assert out["status"] == "measured", out.get("reason")
    assert out["velocity_m_s"]["lateral"] == pytest.approx(-0.9, abs=0.05)
    assert out["landing"]["at"].endswith("floor") or out["landing"]["predicted_x_in"] < 0


@pytest.mark.parametrize("change, reason", [
    ({"corners_suspect": True}, "corners look misplaced"),
    ({"front_hfov_deg": None}, "field of view is not known"),
])
def test_missing_inputs_stay_missing(change, reason):
    scene, _ = _scene()
    out = _run(scene, **change)
    assert out["status"] == "unavailable" and reason in out["reason"]
    assert "release" not in out and "front_path" not in out


def test_unaccepted_side_flight_is_unavailable():
    scene, _ = _scene(flight_ok=False)
    out = _run(scene)
    assert out["status"] == "unavailable" and "side camera's bag flight was not accepted" in out["reason"]


def test_bag_seen_in_too_few_front_frames_reports_no_numbers():
    scene, _ = _scene(bag_frames=4)
    out = _run(scene)
    assert out["status"] == "unavailable"
    assert "release" not in out and "lateral_launch_angle_deg" not in out and "front_path" not in out


def test_estimated_side_scale_gives_an_estimated_flight():
    scene, _ = _scene()
    scene["results"]["scale"]["status"] = "estimated"
    assert _run(scene)["status"] == "estimated"


def test_hook_never_breaks_the_two_view_result(tmp_path):
    record = {"camera": {"status": "measured"}, "frames": {"contact_side": 10}, "landing": {}, "heading": {}}
    out = tv.flight_3d_for_throw(tmp_path, [], {}, {}, np.zeros((1, 4, 2)), record, camera_hfov=66.0,
                                 corners_suspect=False, release_side=0, release_front=0, contact_front=5)
    assert out["status"] == "unavailable" and out["reason"]
    assert (tmp_path / f3.FLIGHT3D_FILENAME).exists()


def test_projected_path_keeps_the_front_path_contract():
    scene, _ = _scene()
    out = _run(scene)
    record = {"status": "measured", "front_path": out["front_path"], "flight_3d": out, "front_path_source": "flight_3d"}
    assert problems("TwoViewDocument", record) == []
