"""Front camera: deck detection on a rendered view, camera model, landing classification, frontal measures."""
from __future__ import annotations

import math

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from cornhole_biomech import front_view as fv  # noqa: E402
from cornhole_biomech.regulation import INCH_M, Board  # noqa: E402

W, H = 1280, 720
FLOOR_BGR = (150, 185, 200)       # beige (OpenCV hue ≈ 21): CIELAB b* well above the deck's
DECK_BGR = (70, 55, 175)
STRIPE_BGR = (228, 228, 230)


def camera(hfov: float = 64.0, centre=(0.03, 4.0, 1.3), pitch_deg: float = 14.0):
    f = (W / 2) / math.tan(math.radians(hfov) / 2)
    K = np.array([[f, 0, W / 2], [0, f, H / 2], [0, 0, 1]], float)
    p = math.radians(pitch_deg)
    right = np.array([-1.0, 0, 0])                              # facing the thrower: image right = thrower's left
    forward = np.array([0, -math.cos(p), -math.sin(p)])
    down = np.cross(forward, right)
    R = np.vstack([right, down, forward])
    C = np.asarray(centre, float)
    return K, R, -R @ C


def project(K, R, t, points):
    cam = (R @ np.asarray(points, float).T).T + t
    uv = (K @ cam.T).T
    return uv[:, :2] / uv[:, 2:3]


def deck_world(x_in, y_in, lift_m=0.0):
    """Board inches (thrower's frame) → world metres on the sloped deck."""
    b = Board()
    y_m = y_in * INCH_M
    return np.array([(x_in - 12.0) * INCH_M, y_m * math.cos(b.angle), b.front_height_m + y_m * math.sin(b.angle) + lift_m])


def render(cam, bags=()):
    K, R, t = cam
    img = np.full((H, W, 3), FLOOR_BGR, np.uint8)
    rng = np.random.default_rng(0)
    img = np.clip(img.astype(int) + rng.integers(-6, 7, img.shape), 0, 255).astype(np.uint8)
    b = Board()
    # Apron (the board's back end) and legs.
    back = [deck_world(0, 48), deck_world(24, 48)]
    apron = np.array([back[0], back[1], back[1] - [0, 0, 0.13], back[0] - [0, 0, 0.13]])
    cv2.fillPoly(img, [project(K, R, t, apron).round().astype(np.int32)], (30, 26, 26))
    for x in (1.5, 22.5):
        top, bottom = deck_world(x, 46), deck_world(x, 46)
        bottom[2] = 0.0
        p = project(K, R, t, [top - [0, 0, 0.13], bottom]).round().astype(int)
        cv2.line(img, tuple(p[0]), tuple(p[1]), (60, 50, 190), 9)
    corners = np.array([deck_world(0, 0), deck_world(24, 0), deck_world(24, 48), deck_world(0, 48)])
    quad = project(K, R, t, corners)
    cv2.fillPoly(img, [quad.round().astype(np.int32)], DECK_BGR)
    for x0 in (0.0, 24.0):     # white V stripes from the far corners towards the hole
        stripe = project(K, R, t, [deck_world(x0, 0), deck_world(12 + (x0 - 12) * 0.15, 36)]).round().astype(int)
        cv2.line(img, tuple(stripe[0]), tuple(stripe[1]), STRIPE_BGR, 4)
    hole = project(K, R, t, [deck_world(12 + 3 * math.cos(a), 39 + 3 * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 40)])
    cv2.fillPoly(img, [hole.round().astype(np.int32)], (35, 25, 80))
    for kind, x_in, y_in in bags:
        if kind == "deck":
            centre = deck_world(x_in, y_in, 0.02)
        else:                  # floor
            centre = np.array([(x_in - 12) * INCH_M, y_in * INCH_M, 0.02])
        # A 6 × 6 in bag about 4 cm thick: its silhouette is the hull of the box's corners (top face + side).
        half = 3.0 * INCH_M
        box = [centre + [dx, dy, dz] for dx in (-half, half) for dy in (-half, half) for dz in (-0.02, 0.02)]
        hull = cv2.convexHull(project(K, R, t, box).astype(np.float32)).round().astype(np.int32)
        cv2.fillPoly(img, [hull], (40, 30, 215))
    return img, quad


def test_deck_detection_finds_the_four_corners_in_the_thrower_frame():
    cam = camera()
    img, truth = render(cam)
    found = fv.detect_front_board(img)
    assert found["status"] == "found", found.get("reason")
    corners = np.asarray(found["corners_px"])
    assert np.max(np.linalg.norm(corners - truth, axis=1)) < 3.0
    # Mirror: the thrower's front-left corner is the far corner on the image's RIGHT.
    assert corners[0, 0] > corners[1, 0] and corners[3, 0] > corners[2, 0]
    assert found["checks"]["hole"]["offset_in"] < 1.5


def test_deck_homography_maps_hole_and_sides():
    cam = camera()
    _, quad = render(cam)
    Hm = fv.deck_homography(quad)
    K, R, t = cam
    hole_px = project(K, R, t, [deck_world(12, 39)])
    assert np.allclose(fv.to_deck(Hm, hole_px)[0], [12, 39], atol=0.05)
    left_px = project(K, R, t, [deck_world(3, 30)])   # thrower's left half of the deck
    assert left_px[0, 0] > hole_px[0, 0]               # appears on the image's right


def test_field_of_view_from_the_deck_shape():
    for hfov in (58.0, 66.0, 72.0):
        cam = camera(hfov=hfov)
        _, quad = render(cam)
        est = fv.deck_shape_hfov(quad, (W, H))
        assert est["status"] == "measured" and abs(est["hfov_deg"] - hfov) < 1.0


def test_camera_pose_puts_the_camera_behind_the_board():
    cam = camera(centre=(0.05, 4.1, 1.25))
    _, quad = render(cam)
    pose = fv.front_camera_pose(quad, (W, H), 64.0)
    assert np.allclose(pose["centre_m"], [0.05, 4.1, 1.25], atol=0.02)
    floor = fv.ray_to_floor(pose, project(*cam, [[0.3, -0.5, 0.0]])[0])
    assert np.allclose(floor, [0.3, -0.5, 0.0], atol=0.01)


def test_alignment_follows_a_drifting_camera():
    cam = camera()
    img, quad = render(cam)
    drifted = np.roll(img, (17, -6), axis=(0, 1))
    reference = {"image": img, "corners_px": quad}
    out = fv.frame_corners(reference, [img, drifted, drifted])
    assert out["status"] == "measured"
    assert np.allclose(out["corners"][-1], quad + [-6, 17], atol=1.0)


def _clip(cam, after_bags, n=30, before_bags=()):
    before, _ = render(cam, before_bags)
    after, _ = render(cam, tuple(before_bags) + tuple(after_bags))
    frames = [before] * (n // 2) + [after] * (n - n // 2)
    return frames, before


def test_landing_on_the_deck_gives_the_sideways_position():
    cam = camera()
    _, quad = render(cam)
    frames, empty = _clip(cam, [("deck", 6.0, 40.0)])
    corners = np.repeat(quad[None], len(frames), axis=0)
    out = fv.landing_from_front(frames, 30.0, corners, release_frame=12, contact_frame=None,
                                empty_reference={"image": empty, "corners_px": quad})
    assert out["where"] == "board"
    assert abs(out["rest"]["x_in"] - 6.0) < 1.5


def test_a_bag_under_the_board_means_it_went_through_the_hole():
    cam = camera()
    _, quad = render(cam)
    frames, empty = _clip(cam, [("floor", 12.0, 44.0)])   # floor under the back end, between the legs
    corners = np.repeat(quad[None], len(frames), axis=0)
    out = fv.landing_from_front(frames, 30.0, corners, 12, None, {"image": empty, "corners_px": quad})
    assert out["where"] == "hole"


def test_a_bag_beside_the_board_is_off():
    cam = camera()
    _, quad = render(cam)
    frames, empty = _clip(cam, [("floor", 40.0, 10.0)])
    corners = np.repeat(quad[None], len(frames), axis=0)
    out = fv.landing_from_front(frames, 30.0, corners, 12, None, {"image": empty, "corners_px": quad})
    assert out["where"] == "off"


def test_an_old_bag_already_on_the_board_is_ignored():
    cam = camera()
    _, quad = render(cam)
    frames, empty = _clip(cam, [("deck", 18.0, 30.0)], before_bags=[("deck", 6.0, 40.0)])
    corners = np.repeat(quad[None], len(frames), axis=0)
    out = fv.landing_from_front(frames, 30.0, corners, 12, None, {"image": empty, "corners_px": quad})
    assert out["where"] == "board" and abs(out["rest"]["x_in"] - 18.0) < 1.5


def _pose_frame(**points):
    return {name: (x, y, 0.9) for name, (x, y) in points.items()}


def test_frontal_measures_use_the_throwers_frame():
    # Right-hander seen from the front camera: their right shoulder is on the image's LEFT.
    frame = _pose_frame(right_shoulder=(600, 300), left_shoulder=(680, 300), right_hip=(610, 400), left_hip=(670, 400),
                        right_wrist=(630, 420), left_wrist=(690, 380), right_ankle=(615, 560), left_ankle=(665, 560))
    frames = [frame] * 40
    m = fv.frontal_metrics(frames, 30, 30.0, "right", None, None)
    assert m["arm_across_body_sw"]["value"] == pytest.approx(30 / 80, abs=1e-6)     # towards the midline: +
    assert abs(m["trunk_side_lean_deg"]["value"]) < 1e-6
    leaning = [_pose_frame(right_shoulder=(580, 300), left_shoulder=(660, 300), right_hip=(610, 400), left_hip=(670, 400),
                           right_wrist=(560, 420))] * 40
    lean = fv.frontal_metrics(leaning, 30, 30.0, "right", None, None)["trunk_side_lean_deg"]["value"]
    assert lean > 10                               # shoulders shifted towards the throwing (right) side: +
    out = fv.frontal_metrics(leaning, 30, 30.0, "right", None, None)["arm_across_body_sw"]["value"]
    assert out < 0                                 # hand outside the throwing shoulder: −


def test_missing_joints_stay_missing():
    frames = [{"right_shoulder": (None, None, 0.0)}] * 40
    m = fv.frontal_metrics(frames, 30, 30.0, "right", None, None)
    assert m["trunk_side_lean_deg"]["value"] is None and m["trunk_side_lean_deg"]["status"] == "unavailable"
    assert m["trunk_side_lean_deg"]["reason"]


def test_heading_separates_aim_from_where_the_hand_released():
    straight = fv.heading(0.0, 12.0, 6.0, 39.0)
    assert abs(straight["deg"]) < 1e-9 and abs(straight["sideways_at_hole_in"]) < 1e-9
    right = fv.heading(0.0, 18.0, 6.0, 30.0)
    assert right["deg"] > 0 and right["sideways_at_hole_in"] > 6.0
    offset_only = fv.heading(0.1, 12.0 + 0.1 / INCH_M, 6.0, 39.0)    # stood right, threw parallel
    assert abs(offset_only["deg"]) < 1e-6 and offset_only["from_release_position_in"] == pytest.approx(0.1 / INCH_M)
    assert fv.heading(None, None, 6.0, None)["status"] == "unavailable"


def test_camera_roll_is_removed_from_frontal_angles():
    import math as m
    roll = 4.0
    r = m.radians(roll)

    def rot(x, y):    # rotate about (640, 360) clockwise by `roll` as displayed (y down)
        x, y = x - 640, y - 360
        return (640 + x * m.cos(r) - y * m.sin(r), 360 + x * m.sin(r) + y * m.cos(r))

    upright = dict(right_shoulder=(600, 300), left_shoulder=(680, 300), right_hip=(610, 400), left_hip=(670, 400),
                   right_wrist=(600, 420))
    rolled = {k: rot(*v) for k, v in upright.items()}
    frames = [_pose_frame(**rolled)] * 40
    corners = np.array([[700, 500], [580, 500], [540, 560], [760, 560]], float)
    corners = np.array([rot(*c) for c in corners])
    measured = fv.camera_roll_deg(corners)
    assert abs(measured - roll) < 0.01
    out = fv.frontal_metrics(frames, 30, 30.0, "right", None, None, roll_deg=measured)
    assert abs(out["trunk_side_lean_deg"]["value"]) < 0.05
    assert abs(out["shoulder_tilt_deg"]["value"]) < 0.05


def test_alignment_ignores_a_bag_that_lands_by_the_far_edge():
    """Player 2 take 4 throw 2: a bag landing by the far edge pulled the far corners 27 px, the camera still."""
    cam = camera()
    img, quad = render(cam)
    with_bags, _ = render(cam, [("deck", 18.0, 4.0), ("deck", 6.0, 4.0), ("deck", 12.0, 8.0)])
    out = fv.frame_corners({"image": img, "corners_px": quad}, [img] * 6 + [with_bags] * 6)
    assert np.allclose(out["corners"][-1], quad, atol=0.3)     # unmasked: 0.7 px on this clean synthetic view


def test_a_key_frame_whose_deck_changes_shape_is_dropped(monkeypatch):
    cam = camera()
    img, quad = render(cam)
    marked = np.clip(img.astype(int) + 3, 0, 255).astype(np.uint8)      # same scene, told apart by brightness
    marker = float(cv2.cvtColor(marked, cv2.COLOR_BGR2GRAY).mean())
    original = fv.align_to_reference

    def pulled(reference_gray, gray, window, initial=None, ignore_mask=None):
        result = original(reference_gray, gray, window, initial, ignore_mask)
        if result["ok"] and abs(float(gray.mean()) - marker) < 0.01:
            centre = quad.mean(axis=0)
            result = {**result, "warp": np.array([[1.0, 0.0, 0.0], [0.0, 1.15, -0.15 * centre[1]]])}
        return result
    monkeypatch.setattr(fv, "align_to_reference", pulled)
    out = fv.frame_corners({"image": img, "corners_px": quad}, [img] * 5 + [marked] + [img] * 5)
    assert out["shape_rejected_frames"] == 1 and out["max_shape_change_px"] > fv.ALIGN_SHAPE_TOLERANCE_PX
    assert np.allclose(out["corners"][5], quad, atol=1.0)


def test_a_bag_on_the_floor_near_the_camera_is_found_at_its_own_size():
    """Player 1 take 5 throw 4: the bag slid off the back end and lay near the camera, 17× the deck-centre bag."""
    cam = camera(pitch_deg=22.0)                                # looking down enough to see the floor near the camera
    _, quad = render(cam)
    frames, empty = _clip(cam, [("floor", 10.0, 95.0)])
    corners = np.repeat(quad[None], len(frames), axis=0)
    out = fv.landing_from_front(frames, 30.0, corners, 12, None, {"image": empty, "corners_px": quad}, hfov_deg=64.0)
    assert out["where"] == "off"
    assert out["candidates"][0]["area_px"] > 15 * out["expected_bag_area_px"]


def _speck(cam, frames, x_in, y_in, radius_m=0.04):
    K, R, t = cam
    centre = deck_world(x_in, y_in, 0.005)
    ring = [centre + [radius_m * math.cos(a), radius_m * math.sin(a), 0] for a in np.linspace(0, 2 * math.pi, 16)]
    poly = project(K, R, t, ring).round().astype(np.int32)
    out = []
    for k, frame in enumerate(frames):
        frame = frame.copy()
        if k >= len(frames) // 2:
            cv2.fillPoly(frame, [poly], (40, 30, 215))
        out.append(frame)
    return out


def test_a_change_smaller_than_a_bag_on_the_deck_is_not_a_bag_at_rest():
    cam = camera()
    _, quad = render(cam)
    frames, empty = _clip(cam, [])
    frames = _speck(cam, frames, 16.0, 42.0)
    corners = np.repeat(quad[None], len(frames), axis=0)
    out = fv.landing_from_front(frames, 30.0, corners, 12, None, {"image": empty, "corners_px": quad}, hfov_deg=64.0)
    assert out["where"] is None and out["deck_clear"] is True
    assert out["changes"]["small_on_deck"] == 1


def _fake_track(monkeypatch, points):
    """Replace the deck tracker by a fixed path of (frame, px, deck_in)."""
    path = [{"frame": f, "px": list(px), "bottom_px": list(px), "deck_in": list(d)} for f, px, d in points]
    monkeypatch.setattr(fv, "track_bag_on_deck", lambda *a, **k: path)


def test_a_bag_followed_off_the_deck_to_the_floor_is_off_even_if_the_deck_changed(monkeypatch):
    cam = camera()
    K, R, t = cam
    _, quad = render(cam)
    frames, empty = _clip(cam, [("deck", 6.0, 40.0), ("floor", 18.0, 70.0)])   # a nudged bag + the thrown one
    corners = np.repeat(quad[None], len(frames), axis=0)
    floor_px = project(K, R, t, [[(18.0 - 12) * INCH_M, 70.0 * INCH_M, 0.02]])[0]
    deck_px = project(K, R, t, [deck_world(17.0, 30.0)])[0]
    _fake_track(monkeypatch, [(14, deck_px, (17.0, 30.0)), (15, deck_px, (17.0, 31.0)),
                              (17, floor_px - [0, 20], (18.0, 62.0)), (18, floor_px - [0, 5], (18.0, 66.0)),
                              (19, floor_px, (18.0, 68.0))])
    out = fv.landing_from_front(frames, 30.0, corners, 2, 14, {"image": empty, "corners_px": quad}, hfov_deg=64.0)
    assert out["path_left_deck"] is True and out["where"] == "off"
    # The same changes with the bag tracked to a stop on the deck: the deck bag is the thrown one.
    _fake_track(monkeypatch, [(14, deck_px, (17.0, 30.0)), (15, deck_px, (16.0, 34.0)), (16, deck_px, (7.0, 39.0)),
                              (17, deck_px, (6.0, 40.0))])
    out = fv.landing_from_front(frames, 30.0, corners, 2, 14, {"image": empty, "corners_px": quad}, hfov_deg=64.0)
    assert out["where"] == "board"


def test_the_hole_from_the_tracked_path_needs_a_path_from_first_contact(monkeypatch):
    """Player 3 take 2 throw 1: a 'path' that began 36 frames after contact, in the hole, said hole."""
    cam = camera()
    K, R, t = cam
    _, quad = render(cam)
    frames, empty = _clip(cam, [])
    corners = np.repeat(quad[None], len(frames), axis=0)
    hole_px = project(K, R, t, [deck_world(12.0, 39.0)])[0]
    on_deck = project(K, R, t, [deck_world(12.0, 28.0)])[0]
    _fake_track(monkeypatch, [(f, hole_px, (12.0, 39.5)) for f in range(24, 29)])          # late, static
    late = fv.landing_from_front(frames, 30.0, corners, 2, 14, {"image": empty, "corners_px": quad}, hfov_deg=64.0)
    assert late["where"] is None and late["path_starts_at_contact"] is False
    _fake_track(monkeypatch, [(14, on_deck, (12.0, 28.0)), (15, on_deck, (12.0, 32.0)), (16, hole_px, (12.0, 37.0)),
                              (17, hole_px, (12.0, 39.0))])
    tracked = fv.landing_from_front(frames, 30.0, corners, 2, 14, {"image": empty, "corners_px": quad}, hfov_deg=64.0)
    assert tracked["where"] == "hole" and tracked["rest_basis"] == "tracked path into the hole"


def test_withheld_camera_gives_the_true_reason_for_missing_positions():
    frame = _pose_frame(right_shoulder=(600, 300), left_shoulder=(680, 300), right_hip=(610, 400), left_hip=(670, 400),
                        right_wrist=(630, 420), right_ankle=(615, 560), left_ankle=(665, 560))
    camera_record = {"status": "estimated", "pose": None, "pose_withheld": "The board's corners look misplaced."}
    m = fv.frontal_metrics([frame] * 40, 30, 30.0, "right", camera_record, 6.0)
    for key in ("release_point_offset_m", "stance_offset_m", "stance_width_m"):
        assert m[key]["value"] is None and m[key]["reason"] == "The board's corners look misplaced."


def test_deck_track_points_before_first_contact_are_marked_in_the_air():
    """The deck track starts ~0.15 s before the side camera's contact; the replay must not draw those points as
    the slide (it did, 2–3 frames early on 76 of 86 library throws)."""
    path = [{"frame": f} for f in range(120, 127)]
    fv.tag_path_phases(path, 123)
    assert [p["phase"] for p in path] == ["air"] * 3 + ["deck"] * 4
    untagged = [{"frame": 1}]
    fv.tag_path_phases(untagged, None)
    assert "phase" not in untagged[0]


# ------------------------------------------------------------------------------------------------
# Frontal-plane time series around release (front_view.front_kinematics / swing_measures).

FPS, RELEASE = 30.0, 60


def _ramp(t, start, end, value):
    """0 before ``start``, ``value`` after ``end``, a smooth cosine step in between (well inside 6 Hz)."""
    if t <= start:
        return 0.0
    if t >= end:
        return value
    return value * 0.5 * (1 - math.cos(math.pi * (t - start) / (end - start)))


def _swing_frames(sway_sw=0.2, lean_deg=8.0, wrist_sw=0.3, wrist_start_sw=None, n=80, width=80.0):
    """A right-hander seen by the front camera (their right on the image's left), with a known hip sway towards the
    throwing arm, trunk lean towards it and the wrist across the body at release; set-up is still before −1.0 s."""
    frames = []
    for f in range(n):
        t = (f - RELEASE) / FPS
        hip_x = 640.0 - _ramp(t, -1.0, -0.4, sway_sw) * width            # towards the throwing arm = image left
        lean = _ramp(t, -1.0, -0.4, lean_deg)
        sc_x = hip_x - 100.0 * math.tan(math.radians(lean))                 # trunk 100 px tall, top towards image left
        rs, ls = (sc_x - width / 2, 300.0), (sc_x + width / 2, 300.0)
        if wrist_start_sw is None:
            across = _ramp(t, -1.0, -0.4, wrist_sw)
        else:   # forward swing: from wrist_start_sw at −0.5 s to wrist_sw at −0.1 s
            across = wrist_start_sw + _ramp(t, -0.5, -0.1, wrist_sw - wrist_start_sw)
        frames.append(_pose_frame(right_shoulder=rs, left_shoulder=ls, right_hip=(hip_x - 30, 400.0),
                                  left_hip=(hip_x + 30, 400.0), right_wrist=(rs[0] + across * width, 420.0),
                                  left_wrist=(ls[0] + 10, 420.0)))
    return frames


def _mirror(frames):
    """The same throw by a left-hander: image mirrored and the joint sides swapped."""
    swap = {"left": "right", "right": "left"}
    out = []
    for frame in frames:
        mirrored = {}
        for name, (x, y, c) in frame.items():
            side, joint = name.split("_", 1)
            mirrored[f"{swap[side]}_{joint}"] = (None if x is None else 1280.0 - x, y, c)
        out.append(mirrored)
    return out


def _at_release(kin, key):
    return kin[key][kin["t_s"].index(0.0)]


def test_front_kinematics_recovers_known_sway_lean_and_wrist_offset():
    kin = fv.front_kinematics(_swing_frames(), RELEASE, FPS, "right")
    assert kin["status"] == "measured" and kin["view"] == fv.FRONT_VIEW_LABEL
    assert kin["t_s"][0] == pytest.approx(-1.4) and kin["t_s"][-1] == pytest.approx(0.4)
    assert _at_release(kin, "hip_sway_sw") == pytest.approx(0.2, abs=0.005)
    assert _at_release(kin, "trunk_lean_deg") == pytest.approx(8.0, abs=0.1)
    assert _at_release(kin, "wrist_across_sw") == pytest.approx(0.3, abs=0.005)
    assert kin["hip_sway_sw"][0] == pytest.approx(0.0, abs=0.005)        # set-up is the reference
    assert kin["shoulder_width_px"] == pytest.approx(80.0, abs=0.1)
    # The same convention as the release measures in `frontal`.
    frontal = fv.frontal_metrics(_swing_frames(), RELEASE, FPS, "right", None, None)
    assert frontal["arm_across_body_sw"]["value"] == pytest.approx(_at_release(kin, "wrist_across_sw"), abs=0.01)
    assert frontal["trunk_side_lean_deg"]["value"] == pytest.approx(_at_release(kin, "trunk_lean_deg"), abs=0.1)
    m = fv.swing_measures(kin)
    assert m["trunk_lean_change_deg"]["value"] == pytest.approx(8.0, abs=0.15)
    assert m["trunk_lean_change_deg"]["view"] == fv.FRONT_VIEW_LABEL


def test_front_kinematics_hand_path_range_over_the_forward_swing():
    frames = _swing_frames(wrist_start_sw=0.1, wrist_sw=-0.3)
    kin = fv.front_kinematics(frames, RELEASE, FPS, "right", forward_swing_frame=RELEASE - 15)
    m = fv.swing_measures(kin)["hand_path_range_sw"]
    assert m["value"] == pytest.approx(0.4, abs=0.01) and m["status"] == "measured"
    assert kin["forward_swing_start_s"] == pytest.approx(-0.5) and m["forward_swing_source"] == "side peak backswing"
    fallback = fv.front_kinematics(frames, RELEASE, FPS, "right")
    assert fallback["forward_swing_source"].startswith("fixed 0.5 s")
    assert fv.swing_measures(fallback)["hand_path_range_sw"]["value"] == pytest.approx(0.4, abs=0.01)


def test_front_kinematics_mirrored_throwing_side_gives_the_same_signed_values():
    frames = _swing_frames(sway_sw=0.15, lean_deg=-5.0, wrist_sw=-0.25)
    right = fv.front_kinematics(frames, RELEASE, FPS, "right", roll_deg=0.0)
    left = fv.front_kinematics(_mirror(frames), RELEASE, FPS, "left", roll_deg=0.0)
    for key in ("wrist_across_sw", "trunk_lean_deg", "hip_sway_sw"):
        assert left[key] == pytest.approx(right[key], abs=1e-3)
    assert _at_release(left, "hip_sway_sw") == pytest.approx(0.15, abs=0.005)
    assert _at_release(left, "trunk_lean_deg") == pytest.approx(-5.0, abs=0.1)
    assert _at_release(left, "wrist_across_sw") == pytest.approx(-0.25, abs=0.005)
    assert fv.swing_measures(left)["trunk_lean_change_deg"]["value"] == pytest.approx(
        fv.swing_measures(right)["trunk_lean_change_deg"]["value"], abs=1e-6)


def test_front_kinematics_missing_joints_stay_null_and_gaps_are_not_filled():
    frames = [dict(f) for f in _swing_frames()]
    for f in range(RELEASE - 3, RELEASE + 2):            # wrist unclear around release (5 frames)
        frames[f]["right_wrist"] = (frames[f]["right_wrist"][0], frames[f]["right_wrist"][1], 0.1)
    for f in range(len(frames)):                          # hips never seen
        frames[f].pop("left_hip"), frames[f].pop("right_hip")
    kin = fv.front_kinematics(frames, RELEASE, FPS, "right")
    i0 = kin["t_s"].index(0.0)
    assert all(kin["wrist_across_sw"][i] is None for i in range(i0 - 3, i0 + 2))
    assert kin["wrist_across_sw"][i0 - 5] is not None and kin["wrist_across_sw"][i0 + 3] is not None
    assert all(v is None for v in kin["hip_sway_sw"]) and all(v is None for v in kin["trunk_lean_deg"])
    m = fv.swing_measures(kin)
    assert m["trunk_lean_change_deg"]["value"] is None and m["trunk_lean_change_deg"]["status"] == "unavailable"
    assert m["trunk_lean_change_deg"]["reason"]
    assert m["hand_path_range_sw"]["value"] is None and "forward-swing frames" in m["hand_path_range_sw"]["reason"]
    # A window that runs off the start of the clip is null there, not zero.
    early = fv.front_kinematics(_swing_frames()[20:], RELEASE - 20, FPS, "right")
    assert early["wrist_across_sw"][0] is None and early["hip_sway_sw"][-1] is not None


def test_front_kinematics_without_pose_or_release_is_unavailable():
    kin = fv.front_kinematics([], None, FPS, "right")
    assert kin["status"] == "unavailable" and kin["reason"]
    m = fv.swing_measures(kin)
    assert all(item["value"] is None and item["status"] == "unavailable" and item["reason"] for item in m.values())


def test_a_hand_hidden_behind_the_body_makes_the_range_estimated():
    frames = [dict(f) for f in _swing_frames(wrist_start_sw=0.1, wrist_sw=-0.3)]
    for f in range(RELEASE - 15, RELEASE - 8):           # 7 of 16 forward-swing frames: seen but not clearly
        x, y, _ = frames[f]["right_wrist"]
        frames[f]["right_wrist"] = (x, y, 0.4)
    m = fv.swing_measures(fv.front_kinematics(frames, RELEASE, FPS, "right", forward_swing_frame=RELEASE - 15))
    assert m["hand_path_range_sw"]["status"] == "estimated" and "hidden" in m["hand_path_range_sw"]["reason"]


def test_new_frontal_measures_reach_the_athlete_rows(tmp_path):
    import json
    from cornhole_biomech import pipeline
    record = {"status": "measured", "frontal": {
        "hand_path_range_sw": {"value": 0.42, "status": "estimated"},
        "trunk_lean_change_deg": {"value": None, "status": "unavailable"}}}
    (tmp_path / "two_view.json").write_text(json.dumps(record))
    row = pipeline.two_view_row(tmp_path)
    assert row["front_hand_path_range_sw"] == pytest.approx(0.42)
    assert row["front_trunk_lean_change_deg"] is None


def test_front_kinematics_removes_camera_roll():
    roll = 4.0
    r = math.radians(roll)

    def rot(x, y):    # clockwise roll as displayed (y down), about the image centre
        x, y = x - 640, y - 360
        return (640 + x * math.cos(r) - y * math.sin(r), 360 + x * math.sin(r) + y * math.cos(r))

    frames = _swing_frames()
    rolled = [{k: (*rot(x, y), c) for k, (x, y, c) in f.items()} for f in frames]
    level = fv.front_kinematics(frames, RELEASE, FPS, "right")
    corrected = fv.front_kinematics(rolled, RELEASE, FPS, "right", roll_deg=roll)
    for key in ("wrist_across_sw", "trunk_lean_deg", "hip_sway_sw"):
        assert corrected[key] == pytest.approx(level[key], abs=2e-3 if key != "trunk_lean_deg" else 0.11)


def test_landing_and_sliding_off_the_edge_is_not_a_knock_but_a_turn_on_the_deck_is():
    def pt(frame, phase, on, turn=False):
        p = {"frame": frame, "phase": phase, "deck_in": [12.0, 30.0] if on else [12.0, 80.0]}
        if turn:
            p["turn"] = True
        return p
    landing = [pt(1, "air", False), pt(2, "air", False), pt(3, "deck", True), pt(4, "deck", True, turn=True),
               pt(5, "deck", True), pt(6, "deck", True), pt(7, "deck", True), pt(8, "deck", True)]
    assert not fv.slide_turned_on_deck(landing)                     # window reaches back into the air
    off_edge = [pt(f, "deck", True) for f in range(1, 5)] + [pt(5, "deck", True, turn=True)] + \
        [pt(f, "deck", f < 7) for f in range(6, 10)]
    assert not fv.slide_turned_on_deck(off_edge)                    # falls off the deck after the turn
    knock = [pt(f, "deck", True) for f in range(1, 5)] + [pt(5, "deck", True, turn=True)] + \
        [pt(f, "deck", True) for f in range(6, 10)]
    assert fv.slide_turned_on_deck(knock)
