"""Front camera bag tracking: the flight path (projectile model + RANSAC) and the moving bag on the deck."""
from __future__ import annotations

import math

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from cornhole_biomech import front_track as ft  # noqa: E402
from cornhole_biomech import two_view as tv  # noqa: E402

W, H, FPS = 1280, 720, 30.0
HFOV = 66.0
RELEASE, CONTACT = 30, 63                  # 33 frames of flight, as on the real clips (29–40)
BAG_BGR = (70, 55, 140)                    # maroon: hue ≈ 175, S ≈ 155 (real bags S 63–145, median 100)
FLOOR_BGR = (150, 185, 200)                # beige floor (hue ≈ 21)
DECK_BGR = (125, 118, 150)                 # deck paint: red hue, low saturation (S ≈ 54; real deck 25–60)


def _camera(pitch_deg: float = 3.0, height_m: float = 1.0):
    f = (W / 2) / math.tan(math.radians(HFOV) / 2)
    K = np.array([[f, 0, W / 2], [0, f, H / 2], [0, 0, 1.0]])
    p = math.radians(pitch_deg)
    right = np.array([1.0, 0, 0])
    forward = np.array([0, math.cos(p), -math.sin(p)])            # looking along +Y (towards the thrower)
    down = np.cross(forward, right)
    R = np.vstack([right, down, forward])
    C = np.array([0.0, 0.0, height_m])
    return K, R, -R @ C


def _project(cam, points):
    K, R, t = cam
    c = (R @ np.atleast_2d(points).T).T + t
    uv = (K @ c.T).T
    return uv[:, :2] / uv[:, 2:3], c[:, 2]


def _bag_world(frame: int) -> np.ndarray:
    """Drag-free flight from 13 m in front of the camera (1 m up) to the deck at 5 m (0.25 m up)."""
    T = (CONTACT - RELEASE) / FPS
    t = (frame - RELEASE) / FPS
    y0, y1, z0, z1, x0, x1 = 13.0, 5.0, 1.0, 0.25, 0.30, -0.05
    vz = (z1 - z0 + 0.5 * 9.81 * T * T) / T
    return np.array([x0 + (x1 - x0) * t / T, y0 + (y1 - y0) * t / T, z0 + vz * t - 0.5 * 9.81 * t * t])


def _background(rng) -> np.ndarray:
    img = np.full((H, W, 3), FLOOR_BGR, np.uint8)
    # Texture: wooden slats (orange, hue ≈ 15–20) and window bars, like the hall behind the thrower.
    for x in range(0, W, 24):
        cv2.line(img, (x, 0), (x + 200, 300), (60, 120, 190), 3)
    for x in range(300, 1000, 60):
        cv2.line(img, (x, 120), (x, 320), (230, 230, 225), 2)
    noise = rng.integers(-5, 6, img.shape)
    return np.clip(img.astype(int) + noise, 0, 255).astype(np.uint8)


def _render_throw(seed: int = 0, with_bag: bool = True, pitch_deg: float = 3.0):
    """A clip with the bag in flight, a thrower who sways (blue shirt), a walking bystander in a red shirt
    (moving red, not a projectile), a static red object and a shiny-floor reflection of the bag."""
    rng = np.random.default_rng(seed)
    cam = _camera(pitch_deg)
    base = _background(rng)
    cv2.rectangle(base, (860, 300), (885, 318), BAG_BGR, -1)        # spare bags on a ledge: static red
    frames, truth = [], {}
    for k in range(CONTACT + 20):
        img = base.copy()
        sway = int(8 * math.sin(k / 5))
        cv2.rectangle(img, (620 + sway, 250), (660 + sway, 330), (140, 70, 40), -1)    # thrower: blue shirt
        cv2.rectangle(img, (625 + sway, 330), (655 + sway, 390), (60, 50, 40), -1)
        bx = 200 + 6 * k                                                              # bystander, red shirt
        cv2.rectangle(img, (bx, 260), (bx + 30, 310), (50, 40, 160), -1)
        if with_bag and RELEASE <= k <= CONTACT + 1:
            centre = _bag_world(k)
            ring = [centre + 0.075 * np.array([math.cos(a + k * 0.3), 0, math.sin(a + k * 0.3)])
                    for a in np.linspace(0, 2 * math.pi, 4, endpoint=False)]
            uv, depth = _project(cam, ring)
            if np.all(depth > 0):
                cv2.fillPoly(img, [uv.round().astype(np.int32)], BAG_BGR)
                truth[k] = _project(cam, centre)[0][0]
                # Reflection in the floor: the mirror image under the floor, faint and desaturated.
                mirror = np.array([[p[0], p[1], -p[2]] for p in ring])
                uvm, dm = _project(cam, mirror)
                if np.all(dm > 0):
                    overlay = img.copy()
                    cv2.fillPoly(overlay, [uvm.round().astype(np.int32)], (120, 125, 160))
                    img = cv2.addWeighted(overlay, 0.35, img, 0.65, 0)
        frames.append(cv2.GaussianBlur(img, (3, 3), 0))
    return frames, truth, cam


def test_projectile_model_is_exact_for_a_level_camera():
    cam = _camera(pitch_deg=0.0)
    ks = np.arange(RELEASE, CONTACT + 1)
    uv = np.array([_project(cam, _bag_world(k))[0][0] for k in ks])
    t = (ks - RELEASE).astype(float)
    p = ft.fit_level(t[[0, 15, 30]], uv[[0, 15, 30], 0], uv[[0, 15, 30], 1])     # three points
    pu, pv, D = ft.predict(p, t)
    assert np.max(np.hypot(pu - uv[:, 0], pv - uv[:, 1])) < 1e-6
    assert np.all(np.diff(D) < 0)                     # the bag approaches the camera
    focal = (W / 2) / math.tan(math.radians(HFOV) / 2)
    assert abs(ft.release_depth_m(p, focal, FPS) - 13.0) < 0.01      # gravity gives the starting distance


def test_flight_path_follows_the_bag_not_the_distractors():
    frames, truth, _ = _render_throw()
    out = ft.flight_path(frames, RELEASE, CONTACT, fps=FPS, hfov_deg=HFOV)
    assert out["status"] == "measured"
    path = {p["frame"]: np.asarray(p["px"]) for p in out["path"]}
    span = range(RELEASE, CONTACT + 1)
    assert sum(f in path for f in span) >= 0.85 * len(span)
    errors = [float(np.linalg.norm(path[f] - truth[f])) for f in path]
    assert max(errors) < 6.0 and float(np.median(errors)) < 2.0      # never on the bystander or the reflection
    assert min(path) >= RELEASE and max(path) <= CONTACT + ft.CONTACT_SYNC_FRAMES
    assert 8.0 < out["release_depth_m"] < 20.0


def test_flight_path_with_a_pitched_camera_and_deck_corners():
    frames, truth, cam = _render_throw(seed=3, pitch_deg=10.0)
    deck = np.array([[-0.3, 4.6, 0.1], [0.3, 4.6, 0.1], [0.3, 5.8, 0.3], [-0.3, 5.8, 0.3]])
    quad = _project(cam, deck)[0]
    corners = np.repeat(quad[None], len(frames), axis=0)
    path = tv.front_flight_path(frames, RELEASE, CONTACT, None, corners, FPS)
    assert len(path) >= 28 and set(path[0]) == {"frame", "px"}
    assert all(np.linalg.norm(np.asarray(p["px"]) - truth[p["frame"]]) < 6.0 for p in path)


def test_no_bag_means_no_path():
    frames, _, _ = _render_throw(seed=1, with_bag=False)
    out = ft.flight_path(frames, RELEASE, CONTACT, fps=FPS)
    assert out["status"] == "unavailable" and out["path"] == []
    assert tv.front_flight_path(frames, RELEASE, CONTACT, None) == []
    assert tv.front_flight_path(frames, None, CONTACT, None) == []


def test_bag_on_the_deck_is_placed_in_its_own_frame():
    """Frame-pair differencing put the bag one frame early or late; the tracker must not."""
    rng = np.random.default_rng(2)
    base = np.clip(np.full((H, W, 3), FLOOR_BGR, int) + rng.integers(-4, 5, (H, W, 3)), 0, 255).astype(np.uint8)
    cv2.fillPoly(base, [np.array([[480, 420], [800, 420], [900, 640], [380, 640]], np.int32)], DECK_BGR)
    roi = np.ones((H, W), np.uint8)
    truth = {}
    frames = []
    for k in range(60):
        img = base.copy()
        if 30 <= k:
            # Lands at frame 36 and slides, slowing down: 40 px per frame falling, then 25 → 0 on the deck.
            if k < 36:
                x, y = 600 + 2 * (k - 30), 250 + 40 * (k - 30)
            else:
                s = min(k - 36, 12)
                x, y = 612 + s, 490 + 25 * s - 1.0 * s * s
            cv2.rectangle(img, (int(x - 22), int(y - 14)), (int(x + 22), int(y + 14)), BAG_BGR, -1)
            truth[k] = (x, y)
        frames.append(img)
    anchors = np.tile([640.0, 530.0], (len(frames), 1))
    path = ft.track_on_deck(frames, anchors, 31, 59, roi, min_area=600.0, max_area=4000.0)
    got = {p["frame"]: p["px"] for p in path}
    moving = [k for k in range(32, 47)]
    assert sum(k in got for k in moving) >= 12
    for k, (x, y) in got.items():
        assert math.hypot(x - truth[k][0], y - truth[k][1]) < 4.0, k
