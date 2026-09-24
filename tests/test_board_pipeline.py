import numpy as np
import pytest

from cornhole_biomech.bag import PHYSICAL_SCALE_PLANES
from cornhole_biomech.pipeline import _board_scale, _scale_agreement


def test_board_plane_counts_as_physical_scale():
    assert "board_throw_plane" in PHYSICAL_SCALE_PLANES


def test_scale_agreement_flags_over_ten_percent():
    ok = _scale_agreement(200.0, 205.0, None)
    assert ok["flag"] is False and ok["max_disagreement"] == pytest.approx(0.025, abs=1e-3)
    bad = _scale_agreement(200.0, 240.0, 198.0)
    assert bad["flag"] is True


def test_scale_agreement_with_single_source():
    out = _scale_agreement(200.0, None, None)
    assert out["flag"] is False and out["max_disagreement"] is None


def test_board_scale_unavailable_without_a_found_board():
    out = _board_scale(None, (960.0, 540.0))
    assert out["status"] == "unavailable" and out["pixels_per_meter"] is None
    out = _board_scale({"board": {"status": "not_found", "reasons": ["no board"]}}, (960.0, 540.0))
    assert out["status"] == "unavailable"


def test_board_scale_measured_from_a_found_board():
    import math

    import cv2

    from cornhole_biomech.board import camera_matrix, order_corners, solve_board
    from cornhole_biomech.regulation import Board

    W, H = 1920, 1080
    board = Board()
    Lh, fh = board.horizontal_length_m, board.front_height_m
    bh, w = fh + board.length_m * math.sin(board.angle), board.width_m
    obj = np.array([[0, fh, -w / 2], [0, fh, w / 2], [Lh, bh, w / 2], [Lh, bh, -w / 2]])
    R_look = cv2.Rodrigues(np.array([0.0, math.radians(8.0), 0.0]))[0]
    R_tilt = cv2.Rodrigues(np.array([math.radians(8.0), 0.0, 0.0]))[0]
    flip = np.array([[1, 0, 0], [0, -1, 0], [0, 0, -1]], float)
    rvec, _ = cv2.Rodrigues(R_tilt @ R_look @ flip)
    tvec = np.array([[1.5], [1.2], [6.0]])
    img, _ = cv2.projectPoints(obj, rvec, tvec, camera_matrix(W, H, 65.0), None)
    corners = order_corners(img.reshape(-1, 2), "left_to_right")
    model = solve_board(corners, (W, H), board)
    auto_flight = {"width": W, "height": H,
                   "board": {"status": "found", "corners_px": corners.tolist(), **model.as_dict()}}
    out = _board_scale(auto_flight, (900.0, 500.0))
    assert out["status"] == "measured"
    assert out["pixels_per_meter"] == pytest.approx(model.pixels_per_meter_at((900.0, 500.0)))
    assert len(out["hfov_range_ppm"]) == 2 and out["hfov_range_ppm"][0] <= out["hfov_range_ppm"][1]
    assert out["phi_deg"] == pytest.approx(model.phi_deg)
