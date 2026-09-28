"""Release onset (Task 9b): the first free-flight frame is the first bag centre beyond the hand.

The pilot audit (docs/SCENE_REGRESSION.md, "Release onset audit") found release detected EARLY,
never late: on 5 of 21 throws the chosen flight began 2–3 frames before the bag visibly left the
fingers, because the bag's last frames in the hand lie on nearly the same arc as its free flight
and were accepted as flight. The in-hand gate (IN_HAND_ARM_LENGTHS of the wrist) was applied only
while extending the flight backwards, never to the flight's own first points.
"""
import cv2
import numpy as np
import pytest

import cornhole_biomech.auto_bag as ab
from cornhole_biomech.auto_bag import IN_HAND_ARM_LENGTHS, MIN_INLIERS, held_at_start

FPS = 60.0
ARM = 100.0                      # arm length, px
TRUE_RELEASE = 40


def _scenario(k_in_hand=3, n=30):
    """Bag centre on one arc from TRUE_RELEASE − k; the wrist trails it by 0.34 arm while held.

    After release the hand slows and turns upward, so the bag–wrist gap grows past the
    in-hand radius (0.45 arm) from the true release frame on.
    """
    first = TRUE_RELEASE - k_in_hand
    points, wrist = [], np.full((120, 2), np.nan)
    for f in range(first - 10, first + n):
        t = (f - TRUE_RELEASE) / FPS
        bag = np.array([500 + 900 * t, 500 - 300 * t + 0.5 * 1800 * t * t])
        held_gap = 0.34 * ARM
        extra = 0.0 if f < TRUE_RELEASE else 0.12 * ARM + 0.15 * ARM * (f - TRUE_RELEASE)
        wrist[f] = bag - np.array([held_gap + extra, 0.0])
        if f >= first:
            points.append({"frame": f, "x": float(bag[0]), "y": float(bag[1])})
    return points, wrist


def test_leading_points_still_in_the_hand_are_counted_status_applied():
    points, wrist = _scenario(k_in_hand=3)
    onset = held_at_start(points, wrist, IN_HAND_ARM_LENGTHS * ARM)
    assert onset == {"held": 3, "status": "applied"}
    assert points[3]["frame"] == TRUE_RELEASE


def test_status_no_in_hand_points_when_the_flight_starts_beyond_the_hand():
    points, wrist = _scenario(k_in_hand=0)
    assert held_at_start(points, wrist, IN_HAND_ARM_LENGTHS * ARM) == {"held": 0, "status": "no_in_hand_points"}


def test_status_no_wrist_when_the_check_cannot_run():
    points, wrist = _scenario(k_in_hand=3)
    missing = wrist.copy()
    missing[:] = np.nan
    for w, radius in ((missing, IN_HAND_ARM_LENGTHS * ARM), (None, IN_HAND_ARM_LENGTHS * ARM), (wrist, None)):
        assert held_at_start(points, w, radius) == {"held": 0, "status": "no_wrist"}
    # The wrist disappears after one held frame: the second frame cannot be decided.
    gap = wrist.copy()
    gap[TRUE_RELEASE - 2] = np.nan
    assert held_at_start(points, gap, IN_HAND_ARM_LENGTHS * ARM) == {"held": 1, "status": "no_wrist"}


def test_status_capped_when_trimming_would_leave_too_few_detections():
    points, wrist = _scenario(k_in_hand=3, n=MIN_INLIERS + 1)   # dropping all 3 held would leave too few
    onset = held_at_start(points, wrist, IN_HAND_ARM_LENGTHS * ARM)
    assert onset["status"] == "capped_min_inliers"
    assert len(points) - onset["held"] >= MIN_INLIERS


def test_keep_guard_counts_detections_not_reacquired_frames():
    # Frames TRUE_RELEASE and +1 were re-acquired by the segmentation, not detected: they do not
    # count toward the MIN_INLIERS kept (the fit's `inliers` counts detections only).
    points, wrist = _scenario(k_in_hand=3, n=MIN_INLIERS + 4)
    detections = [p["frame"] for p in points if not TRUE_RELEASE <= p["frame"] < TRUE_RELEASE + 2]
    onset = held_at_start(points, wrist, IN_HAND_ARM_LENGTHS * ARM, detection_frames=detections)
    assert onset["status"] == "capped_min_inliers"
    assert sum(1 for f in detections if f > points[onset["held"] - 1]["frame"]) >= MIN_INLIERS


def _track_with_flight(monkeypatch, points, wrist, reacquired=()):
    """auto_track_bag on a stubbed clip whose one flight is `points` (no board, no masks).

    `reacquired` are points the segmentation fills in between detections (not flight points).
    """
    frames = [np.zeros((1080, 1920, 3), np.uint8) for _ in range(120)]
    monkeypatch.setattr(ab, "read_frames", lambda path, scale=1.0: (frames, FPS))
    monkeypatch.setattr(ab, "detect_moving_blobs_in_frames",
                        lambda fr: ([], [np.eye(3)[:2] for _ in range(len(fr))]))
    run = [p["frame"] for p in points]
    fit = {"reference_frame": run[0], "coef_x": [500.0, 900.0, 0.0], "coef_y": [500.0, -300.0, 900.0],
           "vertical_acceleration_px_s2": 1800.0, "horizontal_acceleration_px_s2": 0.0, "rms_residual_px": 1.0,
           "rms_coordinates": "raw_video_pixels", "first_frame": run[0], "last_frame": run[-1],
           "span_seconds": (run[-1] - run[0]) / FPS, "coverage": 1.0, "inliers": len(run),
           "early_points": points[:8]}
    flight = {"status": "accepted", "reasons": [], "points": [{**p, "area": 400.0} for p in points], "fit": fit}
    monkeypatch.setattr(ab, "find_flights", lambda *a, **k: [flight])
    monkeypatch.setattr(ab, "refine_flight", lambda frames, chain, pts: sorted([
        {"frame": p["frame"], "x": p["x"], "y": p["y"], "source": source, "area_px": 400.0,
         "orientation_deg": 0.0, "detection_x": p["x"], "detection_y": p["y"]}
        for p, source in [(q, "mask") for q in pts] + [(q, "reacquired_mask") for q in reacquired]],
        key=lambda r: r["frame"]))
    monkeypatch.setattr(ab, "_scene_and_board", lambda *a, **k: ({"plate_samples": 0}, {"status": "not_found",
                                                                                       "model": None}))
    monkeypatch.setattr(ab, "_after_contact", lambda *a, **k: (None, False))
    return ab.auto_track_bag("clip.mov", wrist, ARM, "left_to_right")


def test_auto_track_reports_release_where_the_bag_leaves_the_hand(monkeypatch):
    points, wrist = _scenario(k_in_hand=3)
    out = _track_with_flight(monkeypatch, points, wrist)
    assert out["release_frame"] == TRUE_RELEASE
    assert out["fit"]["first_frame"] == TRUE_RELEASE
    assert out["points"][0]["frame"] == TRUE_RELEASE
    assert out["fit"]["inliers"] == len(points) - 3
    assert out["board"]["reference_frame"] == TRUE_RELEASE
    assert set(out["camera_to_release"]) == {str(f) for f in range(120)}
    onset = out["release_onset"]
    assert onset["method"] == "first_flight_point_beyond_hand" and onset["status"] == "applied"
    assert out["fit"]["refit_after_release_onset"] is True
    assert out["fit"]["vertical_acceleration_px_s2"] == pytest.approx(1800.0, rel=1e-6)   # the arc, refitted
    assert out["fit"]["rms_residual_px"] < 1e-6
    assert onset["held_frames"] == [TRUE_RELEASE - 3, TRUE_RELEASE - 2, TRUE_RELEASE - 1]
    assert onset["first_detection_frame"] == TRUE_RELEASE - 3


def test_auto_track_keeps_a_flight_that_already_starts_beyond_the_hand(monkeypatch):
    points, wrist = _scenario(k_in_hand=0)
    out = _track_with_flight(monkeypatch, points, wrist)
    assert out["release_frame"] == TRUE_RELEASE
    assert out["fit"]["inliers"] == len(points)
    assert out["release_onset"]["held_frames"] == []
    assert out["release_onset"]["status"] == "no_in_hand_points"
    assert "refit_after_release_onset" not in out["fit"]


def test_auto_track_without_a_wrist_says_the_check_did_not_run(monkeypatch):
    points, _ = _scenario(k_in_hand=3)
    out = _track_with_flight(monkeypatch, points, None)
    assert out["release_frame"] == TRUE_RELEASE - 3
    assert out["release_onset"]["status"] == "no_wrist" and "could not be checked" in out["release_onset"]["reason"]


def test_release_grade_is_at_most_warning_when_the_onset_was_not_checked():
    from cornhole_biomech.quality import quality_grades
    pose = {"usable_frame_percentage": 95.0, "release_visibility": 1.0}
    for status, expected in (("applied", "GOOD"), ("no_in_hand_points", "GOOD"),
                             ("no_wrist", "WARNING"), ("capped_min_inliers", "WARNING")):
        g = quality_grades(pose, None, None, False, "automatic_physics", 3, 8, 1.0,
                           {"status": status, "reason": "r"})["release"]
        assert g["grade"] == expected and g["release_onset_status"] == status
        assert g["reason"] == ("r" if expected == "WARNING" else None)
    # A person's release label is not affected.
    assert quality_grades(pose, None, None, False, "manual", None, None, None,
                          {"status": "no_wrist", "reason": "r"})["release"]["grade"] == "GOOD"


def test_release_can_be_a_frame_the_segmentation_reacquired(monkeypatch):
    # Pilot 126CCAD1: detections at 118–121 (in the hand) and from 124; 122–123 re-acquired by
    # the segmentation. Release is the first bag centre beyond the hand in ANY refined frame.
    points, wrist = _scenario(k_in_hand=3)
    gap = [p for p in points if TRUE_RELEASE <= p["frame"] < TRUE_RELEASE + 2]
    detected = [p for p in points if p not in gap]
    out = _track_with_flight(monkeypatch, detected, wrist, reacquired=gap)
    assert out["release_frame"] == TRUE_RELEASE
    assert out["points"][0]["frame"] == TRUE_RELEASE and out["points"][0]["source"] == "reacquired_mask"
    assert out["fit"]["inliers"] == len(detected) - 3
    assert out["release_onset"]["held_frames"] == [TRUE_RELEASE - 3, TRUE_RELEASE - 2, TRUE_RELEASE - 1]


def test_4k_clip_is_searched_at_1080p_and_reported_in_source_pixels(monkeypatch):
    # The same throw filmed at 4K: the caller passes 4K wrist/arm; the search runs on 1080p
    # frames (the stubs below are working-resolution), and every pixel output comes back x2.
    points, wrist = _scenario(k_in_hand=3)
    hd = _track_with_flight(monkeypatch, points, wrist)
    monkeypatch.setattr(ab, "_video_size", lambda path: (3840.0, 2160.0, 120.0))
    seen = {}
    real_read = ab.read_frames
    monkeypatch.setattr(ab, "read_frames", lambda path, scale=1.0: (seen.setdefault("scale", scale), real_read(path))[1])
    uhd = ab.auto_track_bag("clip.mov", wrist * 2.0, ARM * 2.0, "left_to_right")
    assert seen["scale"] == 0.5
    assert uhd["width"] == 3840 and uhd["height"] == 2160 and uhd["working_scale"] == 0.5
    assert uhd["release_frame"] == hd["release_frame"] == TRUE_RELEASE          # same onset: inputs were scaled
    assert uhd["release_onset"]["held_frames"] == hd["release_onset"]["held_frames"]
    for a, b in zip(hd["points"], uhd["points"]):
        assert (b["x"], b["y"], b["detection_x"]) == pytest.approx((2 * a["x"], 2 * a["y"], 2 * a["detection_x"]))
        assert b["area_px"] == pytest.approx(4 * a["area_px"])
    assert uhd["fit"]["coef_y"] == pytest.approx([2 * v for v in hd["fit"]["coef_y"]])
    assert uhd["fit"]["vertical_acceleration_px_s2"] == pytest.approx(2 * hd["fit"]["vertical_acceleration_px_s2"])
    assert uhd["release_onset"]["in_hand_px"] == pytest.approx(2 * hd["release_onset"]["in_hand_px"])
    assert uhd["typical_bag_area_px"] == pytest.approx(4 * hd["typical_bag_area_px"])


def test_source_pixel_mapping_of_board_transforms_and_camera_motion():
    from cornhole_biomech.auto_bag import to_source_pixels
    H = np.array([[100.0, 0, 50], [0, 100.0, 20], [0, 0, 1]])        # metres -> working px
    D = np.linalg.inv(H)                                                # working px -> plane
    out = to_source_pixels({"plane_H": H.tolist(), "deck_H": D.tolist(), "hfov_deg": 60.0, "phi_deg": 3.0,
                            "corners_px": [[10.0, 20.0]], "camera_to_release": {"5": [[1.0, 0.01, 3.0], [0.0, 1.0, -4.0]]},
                            "frame": 7, "plane_xy_m": [1.5, 0.2], "hole_offset_in": 2.0}, 2.0)
    src = np.array([240.0, 60.0, 1.0])                                   # a source pixel
    plane = np.asarray(out["deck_H"]) @ src
    assert plane[:2] / plane[2] == pytest.approx((D @ np.array([120.0, 30.0, 1.0]))[:2])
    back = np.asarray(out["plane_H"]) @ np.array([0.7, 0.1, 1.0])
    assert back[:2] / back[2] == pytest.approx(2 * (H @ np.array([0.7, 0.1, 1.0]))[:2])
    assert out["camera_to_release"]["5"] == [[1.0, 0.01, 6.0], [0.0, 1.0, -8.0]]
    assert out["corners_px"] == [[20.0, 40.0]]
    assert (out["frame"], out["plane_xy_m"], out["hfov_deg"], out["hole_offset_in"]) == (7, [1.5, 0.2], 60.0, 2.0)


def test_backfill_recovers_the_frames_the_detector_missed_up_to_the_hand():
    from cornhole_biomech.bag_segment import backfill_to_hand
    fps, n = 60.0, 50
    pos = lambda f: (40 + 9.0 * f, 200 - 7.0 * f + 0.12 * f * f)          # the bag's arc (px)
    frames = []
    for f in range(n):
        im = np.full((320, 560, 3), (40, 60, 120), np.uint8)               # brown wall
        x, y = pos(f)
        cv2.rectangle(im, (int(x) - 5, int(y) - 5), (int(x) + 5, int(y) + 5), (30, 30, 200), -1)   # red bag
        frames.append(im)
    chains = {f: np.eye(3) for f in range(n)}
    rows = [{"frame": f, "x": pos(f)[0], "y": pos(f)[1], "area_px": 121.0, "source": "mask"} for f in range(20, 32)]
    wrist = np.array([pos(12)] * n)                                         # hand where the bag was at frame 12
    back = backfill_to_hand(frames, chains, rows, wrist, in_hand_px=30.0)
    frames_found = [r["frame"] for r in back]
    assert frames_found == list(range(frames_found[0], 20)) and frames_found[0] <= 16   # contiguous to the detections
    assert all(np.hypot(r["x"] - pos(r["frame"])[0], r["y"] - pos(r["frame"])[1]) < 2.0 for r in back)
    assert all(np.hypot(r["x"] - wrist[0][0], r["y"] - wrist[0][1]) >= 30.0 for r in back)  # never inside the hand
    assert backfill_to_hand(frames, chains, rows, None, 30.0) == []         # no wrist: no backfill
