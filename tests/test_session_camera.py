"""Task 8b: pooling a recording session's per-throw board HFOV calibrations."""
import json
import math

import cv2
import numpy as np
import pytest

from cornhole_biomech.board import (LIBRARY_HFOV_SOURCE, MAX_SESSION_DEVIATION_DEG, MAX_SESSION_IQR_DEG,
                                    MIN_SESSION_THROWS, SESSION_HFOV_SOURCE, camera_matrix, order_corners,
                                    pool_library_hfov, pool_session_hfov)
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


def _clip(path, day):
    """An empty clip file whose modification date (the recording-date stand-in) is `day` (yyyy-mm-dd)."""
    import os
    from datetime import datetime
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    stamp = datetime.fromisoformat(f"{day}T12:00:00").timestamp()
    os.utime(path, (stamp, stamp))
    return path


def test_session_grouping_key_groups_by_athlete_and_recording_date(tmp_path):
    a = _clip(tmp_path / "throws" / "clip1.mp4", "2026-09-17")
    b = _clip(tmp_path / "other_folder" / "clip2.mp4", "2026-09-17")
    c = _clip(tmp_path / "throws" / "clip3.mp4", "2026-09-24")
    key = lambda athlete, video: session_grouping_key({"athlete_id": athlete, "source_video": str(video)})
    assert key("ath1", a) == key("ath1", b) == "ath1::2026-09-17"   # same athlete and day, any folder
    assert key("ath1", a) != key("ath1", c)                         # same folder, another day
    assert key("ath1", a) != key("ath2", a)                         # different athlete
    assert key("ath1", tmp_path / "missing.mp4") == "ath1::unknown-date"
    # A recording date stated in the manifest wins over the file date.
    stated = {"athlete_id": "ath1", "source_video": str(c), "recording_date": "2026-09-17"}
    assert session_grouping_key(stated) == key("ath1", a)


def test_session_with_unknown_recording_date_is_capped_at_estimated(tmp_path):
    dirs = [_write_throw(tmp_path, f"t{i}", "ath1", tmp_path / "gone" / f"{i}.mp4", h, "measured")
            for i, h in enumerate([60.0, 61.0, 59.5])]
    (camera,) = pool_session_camera_files(dirs).values()
    assert camera["source"] == SESSION_HFOV_SOURCE and camera["n"] == 3
    assert camera["status"] == "estimated" and "recording date" in camera["reason"]
    assert camera["recording_dates"] == ["unknown"]


def _write_throw(root, name, athlete_id, video_path, hfov_deg, status):
    d = root / name
    d.mkdir()
    write_json(d / "manifest.json", {"trial_context": {"trial_id": name, "athlete_id": athlete_id,
                                                        "source_video": str(video_path)}})
    write_json(d / "results.json", {"scale": {"per_throw_hfov_deg": hfov_deg, "per_throw_hfov_status": status}})
    return d


def test_pool_session_camera_files_groups_pools_and_writes_every_member(tmp_path):
    videos = tmp_path / "clips"
    for name in ("a.mp4", "b.mp4", "c.mp4"):
        _clip(videos / name, "2026-09-17")
    other = tmp_path / "clips"
    _clip(other / "z.mp4", "2026-09-24")      # same folder, another day: another session

    session_dirs = [
        _write_throw(tmp_path, "t0", "ath1", videos / "a.mp4", 60.0, "measured"),
        _write_throw(tmp_path, "t1", "ath1", videos / "b.mp4", 61.0, "measured"),
        _write_throw(tmp_path, "t2", "ath1", videos / "c.mp4", 59.5, "measured"),
    ]
    other_dir = _write_throw(tmp_path, "t3", "ath1", other / "z.mp4", 70.0, "measured")

    pooled = pool_session_camera_files(session_dirs + [other_dir])

    assert len(pooled) == 2          # two distinct sessions (different recording dates)
    for d in session_dirs:
        camera = json.loads((d / "camera.json").read_text())
        assert camera["n"] == 3 and camera["status"] == "measured" and camera["recording_dates"] == ["2026-09-17"]
        assert sorted(camera["members"]) == ["t0", "t1", "t2"]
        assert camera["source"] == SESSION_HFOV_SOURCE
    # only one measured throw in its own session: falls back to the library-wide pool (Task 8c)
    other_camera = json.loads((other_dir / "camera.json").read_text())
    assert other_camera["source"] == LIBRARY_HFOV_SOURCE
    assert sorted(other_camera["members"]) == ["t0", "t1", "t2", "t3"]
    assert other_camera["hfov_deg"] == pytest.approx(60.5)
    # 4 throws, IQR 3.4° <= 6° pass the pool's own rules, but the same-camera assumption caps it
    assert other_camera["pool_status"] == "measured" and other_camera["status"] == "estimated"
    assert other_camera["session_pool"]["members"] == ["t3"]
    assert other_camera["session_pool"]["status"] == "estimated"


# ---- task 8c: library-wide fallback for a session with too few measured throws
def test_pool_library_hfov_is_at_most_estimated_and_states_the_same_camera_assumption():
    session = pool_session_hfov([_measured("p3a", 55.3)])
    out = pool_library_hfov([_measured(f"t{i}", v) for i, v in enumerate([58.8, 60.3, 56.6, 61.7, 55.3])],
                            session=session)
    # The pool itself meets the median/n/IQR rules, but it rests on an unverified same-camera/zoom assumption.
    assert out["pool_status"] == "measured"
    assert out["status"] == "estimated" and out["source"] == LIBRARY_HFOV_SOURCE
    assert "not verified" in out["reason"]
    assert out["hfov_deg"] == pytest.approx(58.8) and out["n"] == 5
    assert "same camera and zoom" in out["reason"]
    assert out["session_pool"] == session


def test_pool_library_hfov_estimated_when_the_library_spread_is_too_wide():
    out = pool_library_hfov([_measured(f"t{i}", v) for i, v in enumerate([55.0, 56.0, 68.0, 70.0])])
    assert out["iqr_deg"] > MAX_SESSION_IQR_DEG
    assert out["status"] == "estimated" and out["source"] == LIBRARY_HFOV_SOURCE
    assert "same camera and zoom" in out["reason"] and "library run" in out["reason"]


def test_pool_library_hfov_estimated_when_the_library_has_too_few_throws():
    out = pool_library_hfov([_measured("a", 60.0), _measured("b", 61.0)])
    assert out["status"] == "estimated" and out["n"] == 2
    assert f"at least {MIN_SESSION_THROWS}" in out["reason"]


def test_small_session_keeps_its_own_pool_when_the_library_has_nothing_more(tmp_path):
    videos = tmp_path / "clips"
    videos.mkdir()
    (videos / "a.mp4").touch()
    (videos / "b.mp4").touch()
    dirs = [_write_throw(tmp_path, "t0", "ath1", videos / "a.mp4", 60.0, "measured"),
            _write_throw(tmp_path, "t1", "ath1", videos / "b.mp4", None, None)]
    pooled = pool_session_camera_files(dirs)
    (camera,) = pooled.values()
    assert camera["source"] == SESSION_HFOV_SOURCE and camera["status"] == "estimated" and camera["n"] == 1


def test_board_scale_uses_a_library_camera_file(tmp_path):
    auto_flight = _rendered_board_and_flight(true_hfov=62.0)
    library = pool_library_hfov([_measured(f"t{i}", v) for i, v in enumerate([58.0, 59.0, 60.0])])
    write_json(tmp_path / "camera.json", {**library, "session_key": "p3"})
    out = _board_scale(auto_flight, tmp_path)
    assert out["status"] == "estimated" and out["hfov_status"] == "estimated"
    assert out["hfov_source"] == LIBRARY_HFOV_SOURCE
    assert out["hfov_deg"] == pytest.approx(59.0)
    assert "same camera and zoom" in out["hfov_reason"]
