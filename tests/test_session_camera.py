"""Task 8b: pooling a recording session's per-throw board HFOV calibrations."""
import json
import math

import cv2
import numpy as np
import pytest

from cornhole_biomech.board import (MAX_SESSION_DEVIATION_DEG, MAX_SESSION_IQR_DEG, MIN_SESSION_THROWS,
                                    SESSION_HFOV_SOURCE, camera_matrix, order_corners, pool_session_hfov)
from cornhole_biomech.pipeline import _board_scale, pool_session_camera_files, session_grouping_key
from cornhole_biomech.regulation import Board
from cornhole_biomech.serialization import write_json


def _measured(trial_id: str, hfov_deg: float) -> dict:
    return {"trial_id": trial_id, "hfov_deg": hfov_deg, "status": "measured"}


def test_pool_session_hfov_unavailable_with_no_measured_throws():
    out = pool_session_hfov([{"trial_id": "a", "hfov_deg": 65.0, "status": "estimated"},
                             {"trial_id": "b", "hfov_deg": None, "status": "unavailable"}])
    assert out["status"] == "unavailable"
    assert out["hfov_deg"] is None and out["n"] == 0
    assert out["members"] == [] and out["outliers"] == []
    assert out["source"] == SESSION_HFOV_SOURCE


def test_pool_session_hfov_estimated_status_inputs_are_ignored():
    # Only "measured" throws count; "estimated" throws (edge-of-band or nominal fallback) must
    # not pull the pooled estimate toward their own noisy or fallback value.
    calibrations = [_measured("m1", 60.0), _measured("m2", 61.0), _measured("m3", 59.5),
                    {"trial_id": "e1", "hfov_deg": 75.0, "status": "estimated"}]
    out = pool_session_hfov(calibrations)
    assert out["n"] == 3
    assert "e1" not in out["members"]
    assert out["status"] == "measured"


def test_pool_session_hfov_needs_minimum_throws():
    assert MIN_SESSION_THROWS == 3
    out = pool_session_hfov([_measured("a", 60.0), _measured("b", 62.0)])
    assert out["status"] == "estimated"
    assert out["n"] == 2
    assert "2" in out["reason"] and str(MIN_SESSION_THROWS) in out["reason"]
    assert out["hfov_deg"] == pytest.approx(61.0)


def test_pool_session_hfov_measured_with_tight_spread():
    calibrations = [_measured(f"t{i}", h) for i, h in enumerate([60.0, 61.0, 59.0, 60.5])]
    out = pool_session_hfov(calibrations)
    assert out["status"] == "measured"
    assert out["n"] == 4
    assert out["iqr_deg"] is not None and out["iqr_deg"] <= MAX_SESSION_IQR_DEG
    assert out["reason"] is None
    assert sorted(out["members"]) == ["t0", "t1", "t2", "t3"]
    assert out["outliers"] == []
    assert out["hfov_deg"] == pytest.approx(np.median([60.0, 61.0, 59.0, 60.5]))


def test_pool_session_hfov_estimated_with_wide_spread():
    calibrations = [_measured(f"t{i}", h) for i, h in enumerate([50.0, 60.0, 70.0, 80.0])]
    out = pool_session_hfov(calibrations)
    assert out["status"] == "estimated"
    assert out["n"] == 4
    assert out["iqr_deg"] > MAX_SESSION_IQR_DEG
    assert "IQR" in out["reason"]


def test_pool_session_hfov_flags_a_deviant_member_as_an_outlier():
    calibrations = [_measured("t0", 60.0), _measured("t1", 61.0), _measured("t2", 59.0),
                    _measured("t3", 60.0), _measured("outlier", 60.0 + MAX_SESSION_DEVIATION_DEG + 5.0)]
    out = pool_session_hfov(calibrations)
    assert out["n"] == 5      # the outlier still counts toward n and the median
    assert out["outliers"] == ["outlier"]
    assert "outlier" in out["members"]


def _rendered_board_and_flight(true_hfov: float = 62.0):
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
    auto_flight = {"width": W, "height": H, "fps": fps,
                   "board": {"status": "found", "corners_px": corners.tolist()},
                   "stabilized_points": stabilized_points, "fit": {"vertical_acceleration_px_s2": 1000.0}}
    return auto_flight


def test_board_scale_prefers_a_measured_session_camera_file(tmp_path):
    auto_flight = _rendered_board_and_flight(true_hfov=62.0)
    per_throw = _board_scale(auto_flight)
    assert per_throw["per_throw_hfov_deg"] == pytest.approx(62.0, abs=1.0)

    write_json(tmp_path / "camera.json",
              {"hfov_deg": 58.0, "status": "measured", "n": 5, "iqr_deg": 2.0, "spread_deg": 4.0,
               "members": ["a", "b", "c", "d", "e"], "outliers": [], "reason": None,
               "source": SESSION_HFOV_SOURCE, "session_key": "sess1"})
    out = _board_scale(auto_flight, tmp_path)
    assert out["status"] == "measured"
    assert out["hfov_deg"] == pytest.approx(58.0)
    assert out["hfov_source"] == SESSION_HFOV_SOURCE
    assert out["hfov_gravity_used"] is True
    assert out["per_throw_hfov_deg"] == pytest.approx(62.0, abs=1.0)
    assert out["per_throw_hfov_deviation_deg"] == pytest.approx(abs(58.0 - out["per_throw_hfov_deg"]))
    assert out["pixels_per_meter"] != per_throw["pixels_per_meter"]


def test_board_scale_estimated_session_makes_the_scale_estimated(tmp_path):
    auto_flight = _rendered_board_and_flight(true_hfov=62.0)
    write_json(tmp_path / "camera.json",
              {"hfov_deg": 66.0, "status": "estimated", "n": 2, "iqr_deg": None, "spread_deg": 3.0,
               "members": ["a", "b"], "outliers": [], "reason": "Only 2 throws.", "source": SESSION_HFOV_SOURCE,
               "session_key": "sess1"})
    out = _board_scale(auto_flight, tmp_path)
    assert out["status"] == "estimated"
    assert out["hfov_deg"] == pytest.approx(66.0)
    assert out["hfov_reason"] == "Only 2 throws."


def test_board_scale_ignores_an_unavailable_session_camera_file(tmp_path):
    auto_flight = _rendered_board_and_flight(true_hfov=62.0)
    write_json(tmp_path / "camera.json",
              {"hfov_deg": None, "status": "unavailable", "n": 0, "iqr_deg": None, "spread_deg": None,
               "members": [], "outliers": [], "reason": "No throw measured.", "source": SESSION_HFOV_SOURCE,
               "session_key": "sess1"})
    out = _board_scale(auto_flight, tmp_path)
    assert out["hfov_source"] == "single_throw_gravity_fov"
    assert out["hfov_deg"] == pytest.approx(62.0, abs=1.0)


def test_board_scale_without_camera_json_matches_per_throw_calibration(tmp_path):
    auto_flight = _rendered_board_and_flight(true_hfov=62.0)
    direct = _board_scale(auto_flight)
    via_empty_dir = _board_scale(auto_flight, tmp_path)
    assert via_empty_dir["hfov_deg"] == pytest.approx(direct["hfov_deg"])
    assert via_empty_dir["status"] == direct["status"]
    assert via_empty_dir["hfov_source"] == "single_throw_gravity_fov"
    assert via_empty_dir["per_throw_hfov_deviation_deg"] is None


def test_session_grouping_key_groups_by_athlete_and_clip_folder():
    a = session_grouping_key({"athlete_id": "ath1", "source_video": "/videos/day1/clip1.mp4"})
    b = session_grouping_key({"athlete_id": "ath1", "source_video": "/videos/day1/clip2.mp4"})
    c = session_grouping_key({"athlete_id": "ath1", "source_video": "/videos/day2/clip1.mp4"})
    d = session_grouping_key({"athlete_id": "ath2", "source_video": "/videos/day1/clip1.mp4"})
    assert a == b            # same athlete, same clip folder
    assert a != c            # different clip folder
    assert a != d            # different athlete


def _write_throw(root, name, athlete_id, video_path, hfov_deg, status):
    d = root / name
    d.mkdir()
    write_json(d / "manifest.json", {"trial_context": {"trial_id": name, "athlete_id": athlete_id,
                                                        "source_video": str(video_path)}})
    write_json(d / "results.json", {"scale": {"per_throw_hfov_deg": hfov_deg, "per_throw_hfov_status": status}})
    return d


def test_pool_session_camera_files_groups_pools_and_writes_every_member(tmp_path):
    videos = tmp_path / "clips"
    videos.mkdir()
    for name in ("a.mp4", "b.mp4", "c.mp4"):
        (videos / name).touch()
    other = tmp_path / "other_clips"
    other.mkdir()
    (other / "z.mp4").touch()

    session_dirs = [
        _write_throw(tmp_path, "t0", "ath1", videos / "a.mp4", 60.0, "measured"),
        _write_throw(tmp_path, "t1", "ath1", videos / "b.mp4", 61.0, "measured"),
        _write_throw(tmp_path, "t2", "ath1", videos / "c.mp4", 59.5, "measured"),
    ]
    other_dir = _write_throw(tmp_path, "t3", "ath1", other / "z.mp4", 70.0, "measured")

    pooled = pool_session_camera_files(session_dirs + [other_dir])

    assert len(pooled) == 2          # two distinct sessions (different clip folders)
    for d in session_dirs:
        camera = json.loads((d / "camera.json").read_text())
        assert camera["n"] == 3 and camera["status"] == "measured"
        assert sorted(camera["members"]) == ["t0", "t1", "t2"]
    other_camera = json.loads((other_dir / "camera.json").read_text())
    assert other_camera["members"] == ["t3"]
    assert other_camera["status"] == "estimated"   # only one measured throw in its session
