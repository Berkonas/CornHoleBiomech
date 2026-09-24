import math

import cv2
import numpy as np
import pytest

from cornhole_biomech.board import (HFOV_RANGE_DEG, HIDDEN_FRONT_CORNER_REASON, HOLE_TOLERANCE_IN, MAX_PHI_DEG,
                                    NOMINAL_HFOV_DEG, calibrate_hfov_from_flight, camera_matrix, detect_board,
                                    order_corners, solve_board)
from cornhole_biomech.regulation import INCH_M, Board

W, H = 1920, 1080
B = Board()


def project_board(rvec, tvec, hfov=NOMINAL_HFOV_DEG):
    Lh, fh, bh, w = B.horizontal_length_m, B.front_height_m, B.front_height_m + B.length_m * math.sin(B.angle), B.width_m
    obj = np.array([[0, fh, -w / 2], [0, fh, w / 2], [Lh, bh, w / 2], [Lh, bh, -w / 2]], float)
    img, _ = cv2.projectPoints(obj, rvec, tvec, camera_matrix(W, H, hfov), None)
    return img.reshape(-1, 2)


def side_pose(phi_deg=8.0, distance=6.0):
    # camera looks along −Z of the board frame (board seen from its near side), slightly above
    R_look = cv2.Rodrigues(np.array([0.0, math.radians(phi_deg), 0.0]))[0]
    R_tilt = cv2.Rodrigues(np.array([math.radians(8.0), 0.0, 0.0]))[0]
    flip = np.array([[1, 0, 0], [0, -1, 0], [0, 0, -1]], float)   # board Y up → image y down, Z toward camera
    R = R_tilt @ R_look @ flip
    tvec = np.array([[1.5], [1.2], [distance]])
    return cv2.Rodrigues(R)[0], tvec


def render(corners, size=(H, W)):
    img = np.full(size + (3,), 150, np.uint8)
    cv2.fillConvexPoly(img, corners.astype(np.int32), (25, 25, 25))           # dark rim
    inner = corners.mean(axis=0) + 0.88 * (corners - corners.mean(axis=0))
    cv2.fillConvexPoly(img, inner.astype(np.int32), (30, 30, 190))           # red deck
    # dark hole: 3 in radius at deck (u=12 in across, v=39 in from the front edge)
    to_img = cv2.getPerspectiveTransform(np.float32([[0, 0], [24, 0], [24, 48], [0, 48]]), corners.astype(np.float32))
    a = np.linspace(0, 2 * np.pi, 48, endpoint=False)
    hole = np.stack([12 + 3 * np.cos(a), 39 + 3 * np.sin(a)], axis=1).reshape(-1, 1, 2)
    cv2.fillConvexPoly(img, cv2.perspectiveTransform(hole, to_img).reshape(-1, 2).astype(np.int32), (15, 15, 15))
    return img


def test_solve_recovers_plane_scale_and_phi():
    rvec, tvec = side_pose(phi_deg=8.0)
    corners = project_board(rvec, tvec)
    model = solve_board(order_corners(corners, "left_to_right"), (W, H), B)
    assert model.phi_deg == pytest.approx(8.0, abs=1.0)
    ends = model.to_plane(corners[[0, 3]])       # front-far and back-far lie off the Z=0 plane; use centreline
    mid_front, mid_back = corners[[0, 1]].mean(axis=0), corners[[2, 3]].mean(axis=0)
    xy = model.to_plane(np.array([mid_front, mid_back]))
    assert xy[1, 0] - xy[0, 0] == pytest.approx(B.horizontal_length_m, rel=0.03)
    assert xy[0, 1] == pytest.approx(B.front_height_m, abs=0.02)


def test_deck_inches_of_corners():
    rvec, tvec = side_pose()
    corners = order_corners(project_board(rvec, tvec), "left_to_right")
    model = solve_board(corners, (W, H), B)
    uv = model.to_deck_inches(corners)
    assert uv == pytest.approx(np.array([[0, 0], [24, 0], [24, 48], [0, 48]]), abs=0.5)


def test_calibrate_hfov_from_flight_recovers_known_hfov():
    true_hfov = 60.0
    rvec, tvec = side_pose(phi_deg=6.0)
    corners = order_corners(project_board(rvec, tvec, hfov=true_hfov), "left_to_right")
    K = camera_matrix(W, H, true_hfov)
    fps = 60.0
    n = 20
    t = np.arange(n) / fps
    # A free-fall path in the board's own throw plane (Z=0): x(t) linear, y(t) quadratic
    # (downward, -g), so its true HFOV is recoverable from gravity alone.
    obj = np.stack([0.5 + 3.0 * t, 1.3 + 1.0 * t - 0.5 * 9.80665 * t * t, np.zeros(n)], axis=1)
    points_px = cv2.projectPoints(obj, rvec, tvec, K, None)[0].reshape(-1, 2)
    result = calibrate_hfov_from_flight(corners, (W, H), points_px, np.arange(n), fps, B)
    assert result["status"] == "measured"
    assert result["hfov_deg"] == pytest.approx(true_hfov, abs=1.0)
    assert result["horizontal_acceleration_m_s2"] == pytest.approx(0.0, abs=0.5)
    assert result["pixels_per_meter"] is not None


def test_calibrate_hfov_from_flight_estimated_when_gravity_not_matched_in_band():
    rvec, tvec = side_pose(phi_deg=6.0)
    corners = order_corners(project_board(rvec, tvec), "left_to_right")
    # A perfectly straight pixel-space line stays straight under ANY board homography
    # (homographies preserve collinearity), so its plane-mapped vertical curvature is zero for
    # every HFOV: gravity is never matched anywhere in the band.
    frames = np.arange(20)
    points_px = np.stack([900.0 + 3.0 * frames, 500.0 + 1.0 * frames], axis=1)
    result = calibrate_hfov_from_flight(corners, (W, H), points_px, frames, 60.0, B)
    assert result["status"] == "estimated"
    assert result["hfov_deg"] in (pytest.approx(HFOV_RANGE_DEG[0]), pytest.approx(HFOV_RANGE_DEG[1]))
    assert result["reason"] is not None


def test_calibrate_hfov_from_flight_estimated_with_too_few_points():
    rvec, tvec = side_pose()
    corners = order_corners(project_board(rvec, tvec), "left_to_right")
    result = calibrate_hfov_from_flight(corners, (W, H), [[900.0, 500.0], [905.0, 502.0]], [0, 1], 60.0, B)
    assert result["status"] == "estimated" and result["hfov_deg"] == NOMINAL_HFOV_DEG
    assert "nominal" in result["reason"]


def test_detect_board_on_rendered_plate():
    rvec, tvec = side_pose()
    corners = project_board(rvec, tvec)
    out = detect_board(render(corners), "left_to_right", B)
    assert out["status"] == "found"
    assert np.abs(np.array(out["corners_px"]) - order_corners(corners, "left_to_right")).max() < 12


def test_blank_plate_returns_not_found():
    out = detect_board(np.full((H, W, 3), 150, np.uint8), "left_to_right", B)
    assert out["status"] == "not_found" and out["reasons"]


def test_red_bag_alone_is_not_a_board():
    img = np.full((H, W, 3), 150, np.uint8)
    cv2.rectangle(img, (900, 700), (930, 715), (30, 30, 190), -1)       # bag-sized red patch
    assert detect_board(img, "left_to_right", B)["status"] == "not_found"


def test_oblique_board_flags_phi():
    rvec, tvec = side_pose(phi_deg=35.0)
    model = solve_board(order_corners(project_board(rvec, tvec), "left_to_right"), (W, H), B)
    assert model.phi_deg > MAX_PHI_DEG
    assert model.as_dict()["phi_status"] == "estimated"


def render_apron_board(corners, apron_px=24, stripe=True, hole=True):
    """Pilot-board look: red deck top, dark near-side apron under the near edge, optional
    white stripe that reaches the far edge near the front, dark hole at (12 in, 39 in)."""
    img = np.full((H, W, 3), 150, np.uint8)
    front_near, back_near = corners[1], corners[2]
    apron = np.array([front_near, back_near, back_near + [0, apron_px], front_near + [0, apron_px]])
    cv2.fillConvexPoly(img, apron.astype(np.int32), (25, 25, 25))
    cv2.fillConvexPoly(img, corners.astype(np.int32), (30, 30, 190))
    to_img = cv2.getPerspectiveTransform(np.float32([[0, 0], [24, 0], [24, 48], [0, 48]]), corners.astype(np.float32))
    to_px = lambda uv: cv2.perspectiveTransform(np.float32(uv).reshape(-1, 1, 2), to_img).reshape(-1, 2)  # noqa: E731
    if stripe:
        cv2.fillConvexPoly(img, to_px([[0, 0], [14, 0], [0, 10]]).astype(np.int32), (225, 225, 225))
    if hole:
        a = np.linspace(0, 2 * np.pi, 48, endpoint=False)
        cv2.fillConvexPoly(img, to_px(np.stack([12 + 3 * np.cos(a), 39 + 3 * np.sin(a)], 1)).astype(np.int32),
                           (15, 15, 15))
    return img


def test_hidden_front_corner_is_not_found_but_prefills_corners():
    # No end face visible and a stripe covering the front-far corner: that corner can only be
    # inferred (PnP scan at the nominal FOV), so the detector must not claim "found".
    rvec, tvec = side_pose()
    corners = project_board(rvec, tvec)
    out = detect_board(render_apron_board(corners), "left_to_right", B)
    assert out["status"] == "not_found"
    assert out["reasons"] == [HIDDEN_FRONT_CORNER_REASON]
    assert out["hole_offset_in"] is not None and out["hole_offset_in"] <= HOLE_TOLERANCE_IN
    assert np.abs(np.array(out["corners_px"]) - order_corners(corners, "left_to_right")).max() < 12


def test_board_without_hole_is_not_found_but_keeps_best_guess():
    rvec, tvec = side_pose()
    corners = project_board(rvec, tvec)
    out = detect_board(render_apron_board(corners, hole=False), "left_to_right", B)
    assert out["status"] == "not_found" and out["reasons"]
    assert np.abs(np.array(out["corners_px"]) - order_corners(corners, "left_to_right")).max() < 12


def test_quad_that_is_not_a_regulation_deck_is_rejected():
    rvec, tvec = side_pose()
    corners = project_board(rvec, tvec)
    squashed = corners.copy()
    squashed[[0, 3], 1] += 0.6 * (corners[[1, 2], 1] - corners[[0, 3], 1])    # far edge dropped toward the near edge
    squashed[3, 0] -= 60
    out = detect_board(render(squashed), "left_to_right", B)
    assert out["status"] == "not_found"


def test_detect_board_mirrored_for_right_to_left_throws():
    corners = pilot_like_corners()
    mirrored = corners.copy()
    mirrored[:, 0] = W - 1 - mirrored[:, 0]
    out = detect_board(render_pilot_board(order_corners(corners, "left_to_right"))[:, ::-1].copy(),
                       "right_to_left", B)
    assert out["status"] == "found"
    assert np.abs(np.array(out["corners_px"]) - order_corners(mirrored, "right_to_left")).max() < 12


# ---- pilot-plate findings (task 4b): end face, mixed far-edge profile, faint hole, deck graphic
def _deck_to_px(corners):
    to_img = cv2.getPerspectiveTransform(np.float32([[0, 0], [24, 0], [24, 48], [0, 48]]), corners.astype(np.float32))
    return lambda uv: cv2.perspectiveTransform(np.float32(uv).reshape(-1, 1, 2), to_img).reshape(-1, 2)


def render_pilot_board(corners, apron_px=24, hole_bgr=(18, 18, 110), logo=True, hole=True):
    """Apron board as on the pilot plates: visible dark front face, a faint hole (only ~0.6 of
    the deck brightness) and a dark deck graphic near the front larger than the hole."""
    img = render_apron_board(corners, apron_px, stripe=True, hole=False)
    ordered = order_corners(corners, "left_to_right")
    ff, fn = ordered[0], ordered[1]
    cv2.fillConvexPoly(img, np.array([ff, fn, fn + [0, apron_px], ff + [0, apron_px]]).astype(np.int32),
                       (25, 25, 25))
    to_px = _deck_to_px(ordered)
    a = np.linspace(0, 2 * np.pi, 48, endpoint=False)
    if logo:
        cv2.fillConvexPoly(img, to_px(np.stack([12 + 5 * np.cos(a), 16 + 4 * np.sin(a)], 1)).astype(np.int32),
                           (20, 20, 90))
    if hole:
        cv2.fillConvexPoly(img, to_px(np.stack([12 + 3 * np.cos(a), 39 + 3 * np.sin(a)], 1)).astype(np.int32),
                           hole_bgr)
    return img


def pilot_like_corners():
    # front-far corner ahead of the front-near one (front face visible) and a deck only ~22 px
    # deep, as on the pilot plates
    rvec, tvec = side_pose(phi_deg=-20.0, distance=10.0)
    return project_board(rvec, tvec)


def test_visible_front_face_does_not_move_the_front_corners():
    corners = pilot_like_corners()
    out = detect_board(render_pilot_board(corners), "left_to_right", B)
    assert out["status"] == "found"
    assert np.abs(np.array(out["corners_px"]) - order_corners(corners, "left_to_right")).max() < 12


def test_faint_hole_beside_a_larger_deck_graphic_is_found():
    corners = pilot_like_corners()
    out = detect_board(render_pilot_board(corners), "left_to_right", B)
    assert out["status"] == "found"
    assert out["hole_offset_in"] < 1.5


def test_deck_graphic_without_a_hole_is_not_found():
    corners = pilot_like_corners()
    out = detect_board(render_pilot_board(corners, hole=False), "left_to_right", B)
    assert out["status"] == "not_found"


def test_hole_check_rejects_corners_shifted_along_the_deck():
    from cornhole_biomech.board import _hole_offset_in
    corners = order_corners(pilot_like_corners(), "left_to_right")
    img = render_pilot_board(corners)
    to_px = _deck_to_px(corners)
    shifted = to_px([[0, 8], [24, 8], [24, 56], [0, 56]])       # quad 8 in toward the back
    assert _hole_offset_in(img, corners) < 1.5
    offset = _hole_offset_in(img, shifted)
    assert offset is None or offset > HOLE_TOLERANCE_IN


def test_edge_line_follows_the_majority_edge_not_other_edges():
    from cornhole_biomech.board import _robust_line
    xs = np.arange(200.0)
    ys = 0.15 * xs + 50
    ys[:40] += 10          # deck graphic seen where a stripe hides the far edge
    ys[-40:] -= 8          # the back edge
    (a, b), keep = _robust_line(xs, ys)
    assert a == pytest.approx(0.15, abs=0.005) and b == pytest.approx(50, abs=1.0)
    assert keep[40:160].all() and not keep[:40].any() and not keep[-40:].any()


def test_rim_grown_into_apron_and_face_does_not_win_over_the_apron_quad():
    # Closer board: the red deck grown into the dark apron + face forms a rim quad whose near
    # corners sit on the floor edge (27 px off here) yet still passes the hole check.
    rvec, tvec = side_pose(phi_deg=-10.0, distance=8.0)
    corners = project_board(rvec, tvec)
    out = detect_board(render_pilot_board(corners), "left_to_right", B)
    assert out["status"] == "found"
    assert np.abs(np.array(out["corners_px"]) - order_corners(corners, "left_to_right")).max() < 12
