"""Pipeline-level reanalysis of an accepted automatic flight (final whole-branch review fixes).

`auto_track_bag` is replaced by a fast stub that returns an accepted flight rendered through a
known board (see test_board_pipeline._rendered_board_and_flight); everything else -- caching,
the reanalysis branch, board scale, flight review merge, warnings -- is the real pipeline.
"""
import json
import math

import cv2
import numpy as np
import pytest

from cornhole_biomech import REQUIRED_LANDMARKS
from cornhole_biomech.auto_bag import AUTO_BAG_REVISION
from cornhole_biomech.board import camera_matrix, order_corners
from cornhole_biomech.models import PointEstimate, PoseFrame, PoseSequence, TrialContext
from cornhole_biomech.regulation import Board

FPS, FRAMES, RELEASE, N_FLIGHT = 60.0, 40, 10, 20
W, H = 1920, 1080


def _board_and_flight(true_hfov: float = 62.0):
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
    t = np.arange(N_FLIGHT) / FPS
    flight_obj = np.stack([0.5 + 3.0 * t, 1.3 + 1.0 * t - 0.5 * 9.80665 * t * t, np.zeros(N_FLIGHT)], axis=1)
    points_px = cv2.projectPoints(flight_obj, rvec, tvec, K, None)[0].reshape(-1, 2)
    points = [{"frame": RELEASE + i, "x": float(x), "y": float(y)} for i, (x, y) in enumerate(points_px)]
    return corners.tolist(), points


def _stub_auto_track_bag(calls, scene=None):
    corners_true, points = _board_and_flight()

    def fake(video_path, wrist, arm, direction, cache_dir=None, board_corners_px=None, board_corners_frame=None):
        calls.append({"board_corners_px": board_corners_px, "board_corners_frame": board_corners_frame})
        if board_corners_px is not None:
            board = {"status": "found", "corners_px": board_corners_px, "confidence": 1.0, "hole_offset_in": None,
                     "reasons": ["clicked corners"], "clicked_in_frame": int(board_corners_frame)}
        else:
            board = {"status": "not_found", "corners_px": None, "confidence": 0.0,
                     "reasons": ["No red deck with a dark rim or apron large enough to be a regulation board was found."]}
        board.update({"reference_frame": RELEASE, "reference": "release_frame"})
        return {
            "status": "accepted", "revision": AUTO_BAG_REVISION, "fps": FPS, "reasons": [],
            "release_frame": RELEASE, "first_contact_frame": None, "last_tracked_frame": RELEASE + N_FLIGHT - 1,
            "contact": {"kind": "unknown", "state": "unavailable", "plane_xy_m": None, "reason": "stub"},
            "predicted_contact": None, "board": board, "landing": None, "suggested_outcome": None,
            "scene": scene or {"masks_status": "measured", "masks_reason": None, "masks_empty_frames": 0,
                               "plate_samples": 5},
            "width": W, "height": H, "points": [dict(p) for p in points],
            "stabilized_points": [dict(p) for p in points],
            "camera_to_release": {str(f): [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]] for f in range(FRAMES)},
            "fit": {"inliers": N_FLIGHT, "rms_residual_px": 0.5, "vertical_acceleration_px_s2": 1000.0},
            "release_check": None, "release_onset": None, "after_contact": None,
        }
    return fake, corners_true


def _trial(tmp_path):
    video = tmp_path / "trial.mp4"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (96, 96))
    for _ in range(FRAMES):
        writer.write(np.zeros((96, 96, 3), np.uint8))
    writer.release()
    pose_frames = []
    for f in range(FRAMES):
        s = min(f, RELEASE) / RELEASE
        points = {"left_shoulder": (35, 32), "right_shoulder": (50, 32), "left_elbow": (30, 45),
                  "right_elbow": (52 + 4 * s, 45), "left_wrist": (27, 57),
                  "right_wrist": (54 + 10 * s, 58 - 4 * s), "left_hip": (38, 65), "right_hip": (51, 65)}
        marks = {n: PointEstimate(*points[n], 0.99) for n in REQUIRED_LANDMARKS}
        pose_frames.append(PoseFrame(f, f / FPS, marks))
    pose = tmp_path / "pose.json"
    PoseSequence(1, FPS, 96, 96, FRAMES, "test", "synthetic", "1", pose_frames).save(pose)
    out = tmp_path / "analysis"
    out.mkdir()
    context = TrialContext("T1", "A1", "side", "right", "left_to_right", str(video))
    return context, pose, out


def _analyze(context, pose, out):
    from cornhole_biomech.pipeline import analyze_trial
    return analyze_trial(context, out, backend="rtmpose", pose_input=pose, make_annotated_video=False)["results"]


@pytest.fixture
def no_helper(monkeypatch):
    import cornhole_biomech.scene as scene
    monkeypatch.setattr(scene, "find_binary", lambda: None)


def test_reanalysis_uses_clicked_board_corners(tmp_path, monkeypatch, no_helper):
    import cornhole_biomech.auto_bag as ab
    calls = []
    fake, corners = _stub_auto_track_bag(calls)
    monkeypatch.setattr(ab, "auto_track_bag", fake)
    context, pose, out = _trial(tmp_path)

    first = _analyze(context, pose, out)
    assert first["board"]["status"] == "not_found"
    assert first["scale"]["status"] == "unavailable" and "Board not located" in first["scale"]["reason"]
    assert json.loads((out / "bag_raw.json").read_text())["effective_method"] == AUTO_BAG_REVISION

    # Reanalysis without new corners reuses the cache (no second tracking run).
    _analyze(context, pose, out)
    assert len(calls) == 1

    (out / "board_corners.json").write_text(json.dumps({"corners_px": corners, "reference_frame": RELEASE}))
    second = _analyze(context, pose, out)
    assert len(calls) == 2 and calls[1]["board_corners_px"] == corners
    assert calls[1]["board_corners_frame"] == RELEASE
    assert second["board"]["status"] == "found"
    assert second["board"]["reasons"] == ["clicked corners"] and second["board"]["clicked_in_frame"] == RELEASE
    assert second["scale"]["status"] == "measured" and second["scale"]["pixels_per_meter"] > 0
    assert not any("Board not located" in w for w in second["warnings"])


def test_mask_failure_is_warned_and_cache_retried_once_helper_appears(tmp_path, monkeypatch):
    import cornhole_biomech.auto_bag as ab
    import cornhole_biomech.scene as scene
    calls = []
    fake, _ = _stub_auto_track_bag(calls, scene={
        "masks_status": "unavailable", "masks_reason": "scene-vision helper not found; person masks skipped.",
        "masks_empty_frames": None, "plate_samples": 5})
    monkeypatch.setattr(ab, "auto_track_bag", fake)
    monkeypatch.setattr(scene, "find_binary", lambda: None)
    context, pose, out = _trial(tmp_path)

    first = _analyze(context, pose, out)
    assert any("Person masks were not used" in w and "helper not found" in w for w in first["warnings"])
    assert json.loads((out / "auto_flight.json").read_text())["scene_helper_present"] is False
    _analyze(context, pose, out)
    assert len(calls) == 1                     # still no helper: the cache stands

    monkeypatch.setattr(scene, "find_binary", lambda: tmp_path / "SceneVision")
    _analyze(context, pose, out)
    assert len(calls) == 2                     # helper now installed: the mask-less cache is stale
    assert json.loads((out / "auto_flight.json").read_text())["scene_helper_present"] is True
    _analyze(context, pose, out)
    assert len(calls) == 2                     # helper present when cached: not retried every time
