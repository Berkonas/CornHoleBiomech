import math

import cv2
import numpy as np
import pytest

from cornhole_biomech.board import (MAX_PHI_DEG, NOMINAL_HFOV_DEG, camera_matrix, detect_board,
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


def test_detect_board_on_apron_render_with_stripe():
    rvec, tvec = side_pose()
    corners = project_board(rvec, tvec)
    out = detect_board(render_apron_board(corners), "left_to_right", B)
    assert out["status"] == "found"
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
    rvec, tvec = side_pose()
    corners = project_board(rvec, tvec)
    mirrored = corners.copy()
    mirrored[:, 0] = W - 1 - mirrored[:, 0]
    out = detect_board(render_apron_board(corners)[:, ::-1].copy(), "right_to_left", B)
    assert out["status"] == "found"
    assert np.abs(np.array(out["corners_px"]) - order_corners(mirrored, "right_to_left")).max() < 12
