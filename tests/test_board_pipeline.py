import math

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
    out = _board_scale(None)
    assert out["status"] == "unavailable" and out["pixels_per_meter"] is None
    out = _board_scale({"board": {"status": "not_found", "reasons": ["no board"]}})
    assert out["status"] == "unavailable"


def test_board_scale_unavailable_without_flight_points_to_calibrate_from():
    # A board can be found even when the chosen flight was not accepted; without an accepted
    # flight's own points there is nothing to calibrate the field of view from gravity with.
    out = _board_scale({"board": {"status": "found", "corners_px": [[0, 0], [1, 0], [1, 1], [0, 1]]}})
    assert out["status"] == "unavailable" and out["pixels_per_meter"] is None


def _rendered_board_and_flight(true_hfov: float = 62.0):
    """A board seen at a known HFOV, and a synthetic (-g) free-fall flight rendered through it."""
    import cv2

    from cornhole_biomech.board import camera_matrix, order_corners
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
    K = camera_matrix(W, H, true_hfov)
    img, _ = cv2.projectPoints(obj, rvec, tvec, K, None)
    corners = order_corners(img.reshape(-1, 2), "left_to_right")

    fps = 60.0
    n = 20
    t = np.arange(n) / fps
    flight_obj = np.stack([0.5 + 3.0 * t, 1.3 + 1.0 * t - 0.5 * 9.80665 * t * t, np.zeros(n)], axis=1)
    points_px = cv2.projectPoints(flight_obj, rvec, tvec, K, None)[0].reshape(-1, 2)
    stabilized_points = [{"frame": int(f), "x": float(x), "y": float(y)} for f, (x, y) in zip(range(n), points_px)]
    return W, H, fps, corners, stabilized_points


def test_board_scale_measured_from_an_accepted_flight():
    W, H, fps, corners, stabilized_points = _rendered_board_and_flight(true_hfov=62.0)
    auto_flight = {"width": W, "height": H, "fps": fps,
                   "board": {"status": "found", "corners_px": corners.tolist()},
                   "stabilized_points": stabilized_points,
                   "fit": {"vertical_acceleration_px_s2": 1000.0}}
    out = _board_scale(auto_flight)
    assert out["status"] == "measured"
    assert out["hfov_deg"] == pytest.approx(62.0, abs=1.0)
    assert out["pixels_per_meter"] is not None and out["pixels_per_meter"] > 0
    assert out["pixels_per_meter_at_55_deg"] is not None and out["pixels_per_meter_at_75_deg"] is not None
    assert out["apparent_gravity_m_s2_at_nominal_hfov"] is not None
    assert out["hfov_gravity_used"] is True
    assert out["per_throw_hfov_deg"] == pytest.approx(out["hfov_deg"])
    assert out["per_throw_hfov_deviation_deg"] is None
    assert out["phi_deg"] is not None and 0.0 <= out["phi_deg"] < 20.0


def test_board_scale_estimated_when_gravity_not_matched_in_band():
    W, H, fps, corners, _ = _rendered_board_and_flight()
    # A straight pixel-space line has zero plane-mapped curvature under any board homography
    # (see test_board.calibrate_hfov_from_flight), so gravity is never matched in the band.
    stabilized_points = [{"frame": f, "x": 900.0 + 3.0 * f, "y": 500.0 + f} for f in range(20)]
    auto_flight = {"width": W, "height": H, "fps": fps,
                   "board": {"status": "found", "corners_px": corners.tolist()},
                   "stabilized_points": stabilized_points, "fit": {}}
    out = _board_scale(auto_flight)
    assert out["status"] == "estimated" and out["reason"] is not None


def test_board_scale_survives_a_pose_failure_at_the_nominal_fov(monkeypatch):
    import cornhole_biomech.board as board_module
    from cornhole_biomech.board import NOMINAL_HFOV_DEG
    real = board_module.solve_board

    def failing_at_nominal(corners, size, board=None, hfov_deg=NOMINAL_HFOV_DEG):
        if hfov_deg == NOMINAL_HFOV_DEG:
            raise ValueError("Board pose could not be solved from these corners.")
        return real(corners, size, hfov_deg=hfov_deg) if board is None else real(corners, size, board, hfov_deg)

    monkeypatch.setattr(board_module, "solve_board", failing_at_nominal)
    W, H, fps, corners, stabilized_points = _rendered_board_and_flight(true_hfov=62.0)
    auto_flight = {"width": W, "height": H, "fps": fps,
                   "board": {"status": "found", "corners_px": corners.tolist()},
                   "stabilized_points": stabilized_points,
                   "fit": {"vertical_acceleration_px_s2": 1000.0}}
    out = _board_scale(auto_flight)
    assert out["apparent_gravity_m_s2_at_nominal_hfov"] is None
    assert out["status"] == "measured" and out["pixels_per_meter"] > 0


def test_board_scale_reports_phi_status():
    from cornhole_biomech.board import MAX_PHI_DEG
    from cornhole_biomech.pipeline import _phi_status
    W, H, fps, corners, stabilized_points = _rendered_board_and_flight(true_hfov=62.0)
    auto_flight = {"width": W, "height": H, "fps": fps, "board": {"status": "found", "corners_px": corners.tolist()},
                   "stabilized_points": stabilized_points, "fit": {}}
    out = _board_scale(auto_flight)
    assert out["phi_status"] == ("measured" if out["phi_deg"] <= MAX_PHI_DEG else "estimated")
    assert _phi_status(MAX_PHI_DEG + 5)["phi_status"] == "estimated"
    assert "out of the image plane" in _phi_status(MAX_PHI_DEG + 5)["phi_reason"]
    assert _phi_status(None)["phi_status"] == "unavailable"
    assert _board_scale(None)["phi_status"] == "unavailable"
