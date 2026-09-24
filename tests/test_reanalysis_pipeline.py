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


# ---- item 2: an unconfirmed (automatic-candidate) release caps the chain
def test_cap_unconfirmed_release_caps_release_dependent_quantities_only():
    from cornhole_biomech.pipeline import UNCONFIRMED_RELEASE_REASON, _cap_unconfirmed_release
    chain = {"notes": [], "quantities": {
        "release_speed_m_s": {"state": "measured", "reason": None, "value": 6.0},
        "kinetic_energy_j": {"state": "estimated", "reason": "Scale not measured.", "value": 7.0},
        "hand_speed_at_release_m_s": {"state": "unavailable", "reason": "No joints.", "value": None},
        "measured_along_error_in": {"state": "measured", "reason": None, "value": 3.0}}}
    _cap_unconfirmed_release(chain)
    q = chain["quantities"]
    assert q["release_speed_m_s"]["state"] == "estimated"
    assert q["release_speed_m_s"]["reason"] == UNCONFIRMED_RELEASE_REASON
    assert q["kinetic_energy_j"]["reason"] == f"Scale not measured. {UNCONFIRMED_RELEASE_REASON}"
    assert q["hand_speed_at_release_m_s"]["state"] == "unavailable"
    assert q["measured_along_error_in"]["state"] == "measured"
    assert chain["release_confirmed"] is False


def test_unconfirmed_release_nulls_flattened_chain_summaries(tmp_path, no_helper):
    from cornhole_biomech.bag import BagAutomaticPoint, BagCorrectionSet, BagSeed, BagTrack
    from cornhole_biomech.pipeline import analyze_trial
    from cornhole_biomech.video import read_video_metadata
    context, pose, out = _trial(tmp_path)
    frames = FRAMES
    bag_points = []
    for f in range(frames):
        if f <= RELEASE:
            s = f / RELEASE
            x, y = 54 + 10 * s, 58 - 4 * s
        else:
            t = (f - RELEASE) / FPS
            x, y = 64.0 + 500 * t, 54.0 - 300 * t + 490 * t * t
        bag_points.append(BagAutomaticPoint(f, x, y, 0.95))
    meta = read_video_metadata(context.source_video)
    track = tmp_path / "bag_in.json"
    BagTrack(1, frames, 96, 96, meta.sha256, BagSeed(0, (50, 54, 8, 8)), "import", "synthetic",
             bag_points, "complete").save(track)
    BagCorrectionSet(reviewed_through_frame=frames - 1).save(out / "bag_corrections.json")
    r = analyze_trial(context, out, backend="rtmpose", pose_input=pose, bag_track_input=track,
                      make_annotated_video=False)["results"]
    events = json.loads((out / "events.json").read_text())
    assert events["events"]["release"]["confirmed_by"] is None and r["chain"] is not None
    q = r["chain"]["quantities"]
    assert r["chain"]["release_confirmed"] is False
    capped = [name for name, item in q.items() if item["state"] != "unavailable"]
    assert capped, "the body chain should still have release-dependent values"
    for name in capped:
        assert q[name]["state"] == "estimated" and "automatic candidate" in q[name]["reason"]
        assert r["summaries"][f"chain_{name}"] is None
    assert r["summaries"]["release_to_board_front_m"] is None


# ---- item 6: saving the Flight & scale panel over an accepted automatic flight
def test_explicit_blank_contact_is_manual_unseen_never_measured_with_a_null_frame():
    from cornhole_biomech.pipeline import _merge_automatic_flight_review
    auto = {"first_contact_frame": 90, "contact": {"state": "measured", "reason": None}}
    review, warnings = _merge_automatic_flight_review(auto, {"first_contact_frame": None, "note": "n"})
    assert review["first_contact_frame"] is None and review["contact_state"] == "manual_unseen"
    assert any("frame 90 is not used" in w for w in warnings)
    # No key at all: the automatic measured contact still fills in.
    review, _ = _merge_automatic_flight_review(auto, {"note": "n"})
    assert review["first_contact_frame"] == 90 and review["contact_state"] == "measured"


def test_manual_unchecked_fixed_camera_keeps_a_steadied_automatic_flight():
    from cornhole_biomech.pipeline import _merge_automatic_flight_review
    steadied = {"camera_to_release": {"0": [[1, 0, 0], [0, 1, 0]]}, "stabilized_points": [{"frame": 0, "x": 1, "y": 2}]}
    review, warnings = _merge_automatic_flight_review(steadied, {"fixed_camera": False})
    assert review["fixed_camera"] is True and review["manual_fixed_camera"] is False
    assert review["fixed_camera_source"] == "automatic_camera_motion_removed"
    assert any("camera's motion" in w for w in warnings)
    # Without removed camera motion the manual "not fixed" stands.
    review, warnings = _merge_automatic_flight_review({}, {"fixed_camera": False})
    assert review["fixed_camera"] is False and warnings == []


def test_saved_panel_over_accepted_flight_keeps_board_scale(tmp_path, monkeypatch, no_helper):
    import cornhole_biomech.auto_bag as ab
    calls = []
    fake, corners = _stub_auto_track_bag(calls)
    monkeypatch.setattr(ab, "auto_track_bag", fake)
    context, pose, out = _trial(tmp_path)
    (out / "board_corners.json").write_text(json.dumps({"corners_px": corners, "reference_frame": RELEASE}))
    # What FlightReviewEditor.save() writes when only a note is typed.
    (out / "flight_review.json").write_text(json.dumps({"schema_version": 1, "first_contact_frame": None,
                                                        "fixed_camera": False, "note": "looked fine"}))
    r = _analyze(context, pose, out)
    assert r["scale"]["status"] == "measured"
    assert not any("Physical units withheld" in w for w in r["warnings"])
    assert any("camera's motion" in w for w in r["warnings"])
    assert r["chain"]["release_to_board_front_m"] is not None
    assert r["flight"]["time_of_flight_seconds"] is None
