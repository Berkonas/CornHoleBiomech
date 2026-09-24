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


def render(corners, size=(H, W), deck_bgr=(30, 30, 190)):
    img = np.full(size + (3,), 150, np.uint8)
    cv2.fillConvexPoly(img, corners.astype(np.int32), (25, 25, 25))           # dark rim
    inner = corners.mean(axis=0) + 0.88 * (corners - corners.mean(axis=0))
    cv2.fillConvexPoly(img, inner.astype(np.int32), deck_bgr)                # red deck
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
    assert result["gravity_fit_used"] is False


def _known_hfov_flight(true_hfov: float = 60.0, phi_deg: float = 6.0):
    rvec, tvec = side_pose(phi_deg=phi_deg)
    corners = order_corners(project_board(rvec, tvec, hfov=true_hfov), "left_to_right")
    K = camera_matrix(W, H, true_hfov)
    fps = 60.0
    n = 20
    t = np.arange(n) / fps
    obj = np.stack([0.5 + 3.0 * t, 1.3 + 1.0 * t - 0.5 * 9.80665 * t * t, np.zeros(n)], axis=1)
    points_px = cv2.projectPoints(obj, rvec, tvec, K, None)[0].reshape(-1, 2)
    return corners, points_px, np.arange(n), fps


def test_calibrate_hfov_from_flight_reports_gravity_used_and_labeled_band():
    corners, points_px, frames, fps = _known_hfov_flight()
    result = calibrate_hfov_from_flight(corners, (W, H), points_px, frames, fps, B)
    assert result["status"] == "measured"
    assert result["gravity_fit_used"] is True
    assert result["pixels_per_meter_at_55_deg"] is not None
    assert result["pixels_per_meter_at_75_deg"] is not None
    assert result["pixels_per_meter_at_55_deg"] != result["pixels_per_meter_at_75_deg"]
    assert "pixels_per_meter_band" not in result


def test_calibrate_hfov_from_flight_skips_a_hfov_where_pnp_fails(monkeypatch):
    """A PnP failure at some HFOVs (a degenerate pose for that assumed focal length) must not
    raise; the search works around it using the HFOVs that do solve."""
    corners, points_px, frames, fps = _known_hfov_flight(true_hfov=60.0)
    import cornhole_biomech.board as board_module
    real_solve_board = board_module.solve_board

    def flaky_solve_board(corners_px, image_size, board=Board(), hfov_deg=NOMINAL_HFOV_DEG):
        if 58.0 <= hfov_deg <= 62.0:       # brackets the true HFOV: exercises mid-bisection failures too
            raise ValueError("synthetic PnP failure")
        return real_solve_board(corners_px, image_size, board, hfov_deg=hfov_deg)

    monkeypatch.setattr(board_module, "solve_board", flaky_solve_board)
    result = calibrate_hfov_from_flight(corners, (W, H), points_px, frames, fps, B)
    assert result["hfov_deg"] is not None and result["pixels_per_meter"] is not None
    assert not (58.0 <= result["hfov_deg"] <= 62.0)


def test_calibrate_hfov_from_flight_falls_back_when_almost_no_hfov_solves(monkeypatch):
    corners, points_px, frames, fps = _known_hfov_flight(true_hfov=60.0)
    import cornhole_biomech.board as board_module
    real_solve_board = board_module.solve_board

    def mostly_broken_solve_board(corners_px, image_size, board=Board(), hfov_deg=NOMINAL_HFOV_DEG):
        if hfov_deg != NOMINAL_HFOV_DEG:
            raise ValueError("synthetic PnP failure")
        return real_solve_board(corners_px, image_size, board, hfov_deg=hfov_deg)

    monkeypatch.setattr(board_module, "solve_board", mostly_broken_solve_board)
    result = calibrate_hfov_from_flight(corners, (W, H), points_px, frames, fps, B)
    assert result["status"] == "estimated"
    assert result["hfov_deg"] == NOMINAL_HFOV_DEG
    assert result["gravity_fit_used"] is False


def test_calibrate_hfov_from_flight_recovers_a_root_hidden_at_the_bisection_midpoint(monkeypatch):
    """Fix round 1: a PnP failure exactly at a bisection midpoint must not just discard that
    midpoint forever (recomputing the identical failing point on every remaining iteration and
    falling through to the nominal HFOV) when the true root is recoverable a fraction of a degree
    away. The failing band here (58.9-59.1 deg) is narrow enough that the true root (59.0 deg,
    the first bisection midpoint of the (58, 60) grid bracket) is unsolvable, but nearby points
    are not."""
    true_hfov = 59.0
    corners, points_px, frames, fps = _known_hfov_flight(true_hfov=true_hfov)
    import cornhole_biomech.board as board_module
    real_solve_board = board_module.solve_board
    calls = {"n": 0}

    def narrowly_flaky_solve_board(corners_px, image_size, board=Board(), hfov_deg=NOMINAL_HFOV_DEG):
        calls["n"] += 1
        if 58.9 < hfov_deg < 59.1:
            raise ValueError("synthetic PnP failure exactly at the bisection midpoint")
        return real_solve_board(corners_px, image_size, board, hfov_deg=hfov_deg)

    monkeypatch.setattr(board_module, "solve_board", narrowly_flaky_solve_board)
    # hfov_range=(58, 62), grid_deg=2.0: grid points 58/60/62 all solve (bracket is (58, 60)), so
    # only the bisection midpoint (59.0, in the failing band) is affected -- exactly the case the
    # naive "continue" used to discard.
    result = calibrate_hfov_from_flight(corners, (W, H), points_px, frames, fps, B,
                                         hfov_range=(58.0, 62.0), grid_deg=2.0)
    assert result["status"] == "measured"
    assert abs(result["hfov_deg"] - true_hfov) < 1.0
    assert result["gravity_fit_used"] is True
    assert calls["n"] < 150


def test_calibrate_hfov_from_flight_stalled_bisection_falls_back_to_a_bracket_endpoint(monkeypatch):
    """When neither a bisection midpoint nor any nearby probe solves anywhere in the bracket's
    interior, bisection must stop (not loop through all 40 iterations recomputing the same
    unsolvable points) and report one of the two already-solved bracket endpoints, never the
    unrelated nominal HFOV."""
    true_hfov = 59.0
    corners, points_px, frames, fps = _known_hfov_flight(true_hfov=true_hfov)
    import cornhole_biomech.board as board_module
    real_solve_board = board_module.solve_board
    calls = {"n": 0}

    def interior_broken_solve_board(corners_px, image_size, board=Board(), hfov_deg=NOMINAL_HFOV_DEG):
        calls["n"] += 1
        if 58.0001 < hfov_deg < 59.9999:      # only the bracket's own endpoints (58, 60) solve
            raise ValueError("synthetic PnP failure")
        return real_solve_board(corners_px, image_size, board, hfov_deg=hfov_deg)

    monkeypatch.setattr(board_module, "solve_board", interior_broken_solve_board)
    result = calibrate_hfov_from_flight(corners, (W, H), points_px, frames, fps, B,
                                         hfov_range=(58.0, 62.0), grid_deg=2.0)
    assert result["hfov_deg"] in (pytest.approx(58.0), pytest.approx(60.0))
    assert result["gravity_fit_used"] is True
    assert result["status"] in ("measured", "estimated")
    assert calls["n"] < 150
    assert result["pixels_per_meter"] is not None


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


def render_apron_board(corners, apron_px=24, stripe=True, hole=True, deck_bgr=(30, 30, 190)):
    """Pilot-board look: red deck top, dark near-side apron under the near edge, optional
    white stripe that reaches the far edge near the front, dark hole at (12 in, 39 in)."""
    img = np.full((H, W, 3), 150, np.uint8)
    front_near, back_near = corners[1], corners[2]
    apron = np.array([front_near, back_near, back_near + [0, apron_px], front_near + [0, apron_px]])
    cv2.fillConvexPoly(img, apron.astype(np.int32), (25, 25, 25))
    cv2.fillConvexPoly(img, corners.astype(np.int32), deck_bgr)
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


def render_pilot_board(corners, apron_px=24, hole_bgr=(18, 18, 110), logo=True, hole=True, deck_bgr=(30, 30, 190)):
    """Apron board as on the pilot plates: visible dark front face, a faint hole (only ~0.6 of
    the deck brightness) and a dark deck graphic near the front larger than the hole."""
    img = render_apron_board(corners, apron_px, stripe=True, hole=False, deck_bgr=deck_bgr)
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


# ---- task 8c: pale decks (Player-3 plates: deck median S 26–34, below RED_MIN_SAT = 40)
PALE_DECK_BGR = (165, 165, 190)      # HSV S = 34: the missed pilot decks' median S (26–34)


def test_pale_pilot_board_is_found_by_the_relaxed_apron_pass():
    from cornhole_biomech.board import RED_MIN_SAT, RELAXED_RED_MIN_SATS
    corners = pilot_like_corners()
    out = detect_board(render_pilot_board(corners, deck_bgr=PALE_DECK_BGR), "left_to_right", B)
    assert out["status"] == "found"
    assert out["red_min_sat"] in RELAXED_RED_MIN_SATS and out["red_min_sat"] < RED_MIN_SAT
    assert np.abs(np.array(out["corners_px"]) - order_corners(corners, "left_to_right")).max() < 12


def test_pale_pilot_board_is_missed_without_the_relaxed_pass(monkeypatch):
    # the failure mode the relaxed pass fixes: at the standard threshold the pale deck is not red
    monkeypatch.setattr("cornhole_biomech.board.RELAXED_RED_MIN_SATS", ())
    out = detect_board(render_pilot_board(pilot_like_corners(), deck_bgr=PALE_DECK_BGR), "left_to_right", B)
    assert out["status"] == "not_found"


def test_saturated_board_keeps_the_standard_threshold():
    from cornhole_biomech.board import RED_MIN_SAT
    out = detect_board(render_pilot_board(pilot_like_corners()), "left_to_right", B)
    assert out["status"] == "found" and out["red_min_sat"] == RED_MIN_SAT


def test_relaxed_pass_ignores_rim_candidates():
    # A pale red patch framed by a dark border (on the pilot plates: a pink TV-screen banner)
    # is a rim candidate; the relaxed pass must not turn it into "found".
    rvec, tvec = side_pose()
    out = detect_board(render(project_board(rvec, tvec), deck_bgr=PALE_DECK_BGR), "left_to_right", B)
    assert out["status"] == "not_found"


def test_pale_board_without_hole_is_still_not_found():
    corners = pilot_like_corners()
    out = detect_board(render_pilot_board(corners, deck_bgr=PALE_DECK_BGR, hole=False), "left_to_right", B)
    assert out["status"] == "not_found"


def render_pale_decoy(far_l, far_r, near_l, near_r, band=24, face=True):
    """No board: a pale pink/red quad of non-regulation proportions over a long dark band (and,
    with `face`, a dark end face so the front-far corner counts as observed), with a dark blob
    where (12, 39) in maps if the quad is taken as a 24 × 48 in deck."""
    img = np.full((H, W, 3), 150, np.uint8)
    quad = np.array([far_l, near_l, near_r, far_r], float)     # front-far, front-near, back-near, back-far
    cv2.fillConvexPoly(img, np.array([near_l, near_r, [near_r[0], near_r[1] + band],
                                      [near_l[0], near_l[1] + band]], np.int32), (25, 25, 25))
    if face:
        cv2.fillConvexPoly(img, np.array([far_l, near_l, [near_l[0], near_l[1] + band],
                                          [far_l[0], far_l[1] + band]], np.int32), (25, 25, 25))
    cv2.fillConvexPoly(img, quad.astype(np.int32), PALE_DECK_BGR)
    a = np.linspace(0, 2 * np.pi, 48, endpoint=False)
    cv2.fillConvexPoly(img, _deck_to_px(quad)(np.stack([12 + 3 * np.cos(a), 39 + 3 * np.sin(a)], 1)).astype(np.int32),
                       (18, 18, 110))
    return img


@pytest.mark.parametrize("far_l, far_r, near_l, near_r, face", [
    ([660, 500], [1260, 500], [700, 540], [1300, 540], True),    # 15:1 slab: PnP residual 32 px > 19 px limit
    ([660, 500], [1320, 480], [700, 540], [1300, 540], True),    # far edge longer than near: residual 26 px
    ([660, 440], [960, 440], [700, 540], [1000, 540], True),     # square: passes PnP, hole check fails
    ([700, 500], [1300, 500], [700, 540], [1300, 540], False),   # no end face: front-far corner only inferred
])
def test_pale_non_regulation_decoy_is_not_found_through_the_full_cascade(far_l, far_r, near_l, near_r, face):
    from cornhole_biomech.board import RELAXED_RED_MIN_SATS, _apron_candidates, _red_and_rim
    img = render_pale_decoy(far_l, far_r, near_l, near_r, face=face)
    # the decoy does reach the relaxed pass's gates as an apron candidate ...
    red, dark = _red_and_rim(img, min(RELAXED_RED_MIN_SATS))
    assert _apron_candidates(red, dark, "left_to_right", B)
    # ... and every pass rejects it
    out = detect_board(img, "left_to_right", B)
    assert out["status"] == "not_found" and out["reasons"]
