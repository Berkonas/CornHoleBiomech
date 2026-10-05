"""Two cameras combined: landing fusion, result, signed miss and the coach sentence."""
from __future__ import annotations

import json
from pathlib import Path

from cornhole_biomech import two_view as tv


def test_landing_uses_front_across_and_side_along():
    front = {"where": "board", "contact": {"x_in": 9.0, "y_in_front": 30.0},
             "rest": {"x_in": 8.5, "y_in_front": 44.0}}
    phase = {"status": "measured", "touchdown": {"v_in": 22.0}, "end": {"kind": "rest", "v_in": 35.0}}
    fused = tv.fuse_landing(front, phase, {}, {})
    assert fused["contact"] == {"x_in": 9.0, "y_in": 22.0, "y_source": "side camera"}
    assert fused["rest"]["x_in"] == 8.5 and fused["rest"]["y_in"] == 35.0 and fused["rest"]["y_source"] == "side camera"


def test_landing_falls_back_to_the_front_along_value_without_the_side():
    front = {"where": "board", "contact": None, "rest": {"x_in": 15.0, "y_in_front": 41.0}}
    fused = tv.fuse_landing(front, {}, {}, {})
    assert fused["rest"]["y_in"] == 41.0 and fused["rest"]["y_source"] == "front camera"


def test_miss_vector_signs_are_in_the_throwers_frame():
    miss = tv.miss_vector({"rest": {"x_in": 18.0, "y_in": 30.0, "on": "board"}})
    assert miss["left_right_in"] == 6.0 and miss["short_long_in"] == -9.0      # right +, short −
    assert tv.miss_vector({"rest": {"x_in": 12.0, "y_in": 39.0, "on": "hole"}})["distance_in"] == 0.0
    assert tv.miss_vector({"rest": None})["status"] == "unavailable"


def test_result_comes_from_the_front_camera_and_flags_disagreement():
    agree = tv.decide_result({"where": "hole"}, {"board_phase": {"end": {"kind": "fell_in_hole"}}})
    assert agree["category"] == "throughHole" and agree["points"] == 3 and agree["status"] == "suggested"
    disagree = tv.decide_result({"where": "board"}, {"board_phase": {"end": {"kind": "fell_in_hole"}}})
    assert disagree["views_agree"] is False and disagree["status"] == "needs_confirmation"
    unknown = tv.decide_result({"where": None}, {})
    assert unknown["category"] is None and unknown["status"] == "needs_confirmation"


def _record(result, rest, heading=None, frontal=None):
    landing = {"rest": rest}
    return {"result": {"category": result}, "miss": tv.miss_vector(landing), "heading": heading or {},
            "frontal": frontal or {}}


def test_a_made_throw_gets_no_correction():
    text = tv.explain(_record("throughHole", {"x_in": 12, "y_in": 39, "on": "hole"}), {})
    assert text["kind"] == "made" and "nothing to correct" in text["sentence"]


def test_a_miss_names_distance_and_direction_with_measured_values():
    record = _record("onBoard", {"x_in": 4.0, "y_in": 27.0, "on": "board"},
                     heading={"deg": -1.4}, frontal={"arm_across_body_sw": {"value": 0.4},
                                                     "trunk_side_lean_deg": {"value": 2.0}})
    text = tv.explain(record, {"summaries": {"bag_release_speed_m_s": 6.31}})
    assert text["kind"] == "miss"
    assert "12 in short" in text["sentence"] and "8 in left" in text["sentence"]
    assert "aimed 1.4° left" in text["sentence"] and "across the body" in text["sentence"]
    assert "trunk" not in text["sentence"]                  # 2° is within normal sway
    assert "because" not in text["sentence"]                # associations, not causes


def test_close_board_throw_is_not_called_a_miss():
    text = tv.explain(_record("onBoard", {"x_in": 13.0, "y_in": 37.5, "on": "board"}), {})
    assert text["kind"] == "close"


def test_take_link_resolves_the_take_record(tmp_path: Path):
    take = tmp_path / "Athletes" / "P1" / "takes" / "Take-01-abc"
    take.mkdir(parents=True)
    (take / "throw_01_front.mp4").write_bytes(b"x")
    (take / "take.json").write_text(json.dumps({
        "take": 1, "sync": {"status": "measured", "offset_s": 0.2},
        "front_board": {"status": "found", "corners_px": [[1, 1], [2, 1], [2, 2], [1, 2]], "reference_image": "front_reference.png"},
        "throws": [{"number": 1, "front_clip": {"path": "/elsewhere/throw_01_front.mp4", "side_frame0_front_time_s": 0.1}}]}))
    analysis = tmp_path / "Athletes" / "P1" / "analyses" / "Throw-1"
    analysis.mkdir(parents=True)
    (analysis / tv.TAKE_LINK_FILENAME).write_text(json.dumps({"take_record": "../../takes/Take-01-abc/take.json",
                                                              "throw_number": 1}))
    link = tv.load_take_link(analysis)
    assert link["take"] == 1 and Path(link["front_clip_path"]) == take / "throw_01_front.mp4"   # library moved: local copy
    assert link["front_reference_path"].endswith("front_reference.png")


def test_side_frames_map_to_front_frames_through_timestamps():
    link = {"front_clip": {"side_frame0_front_time_s": 0.06, "frame_times_s": [i / 30 for i in range(100)], "fps": 30},
            "side_clip": {"frame_times_s": [i / 59.94 for i in range(300)]}}
    assert tv.side_to_front_frame(0, 59.94, link) == 2          # 0.06 s → nearest 30 fps frame is 2 (0.0667)
    assert tv.side_to_front_frame(120, 59.94, link) == round((120 / 59.94 + 0.06) * 30)
    assert tv.side_to_front_frame(None, 59.94, link) is None


def _textured(seed: int = 3, size=(240, 320)):
    import cv2
    import numpy as np
    rng = np.random.default_rng(seed)
    noise = rng.integers(0, 255, size=(size[0] // 8, size[1] // 8, 3), dtype=np.uint8)
    return cv2.resize(noise, (size[1], size[0]), interpolation=cv2.INTER_CUBIC)


def _sibling_library(tmp_path: Path, shift=(5, 3)):
    import cv2
    import numpy as np
    image = _textured()
    take = tmp_path / "takes" / "Take-01-x"
    take.mkdir(parents=True)
    moved = cv2.warpAffine(image, np.float32([[1, 0, shift[0]], [0, 1, shift[1]]]), (320, 240),
                           borderMode=cv2.BORDER_REFLECT)
    writer = cv2.VideoWriter(str(take / "throw_02_side.avi"), cv2.VideoWriter_fourcc(*"MJPG"), 30, (320, 240))
    for _ in range(3):
        writer.write(moved)
    writer.release()
    (take / "take.json").write_text(json.dumps({"take": 1, "throws": [
        {"number": 1, "side_clip": {"path": "throw_01_side.avi"}},
        {"number": 2, "side_clip": {"path": "throw_02_side.avi"}}]}))
    analyses = tmp_path / "analyses"
    corners = [[200.0, 150.0], [230.0, 170.0], [300.0, 160.0], [280.0, 140.0]]
    for name, number in (("Throw-A", 1), ("Throw-B", 2)):
        folder = analyses / name
        folder.mkdir(parents=True)
        (folder / tv.TAKE_LINK_FILENAME).write_text(json.dumps({"take_record": "../../takes/Take-01-x/take.json",
                                                                "throw_number": number}))
    (analyses / "Throw-A" / "auto_flight.json").write_text(json.dumps(
        {"board": {"status": "found", "confidence": 0.9, "corners_px": corners}}))
    cv2.imwrite(str(analyses / "Throw-A" / "plate.jpg"), image, [cv2.IMWRITE_JPEG_QUALITY, 98])
    return analyses, corners


def test_a_throw_without_a_side_deck_gets_the_one_a_sibling_found(tmp_path: Path):
    import numpy as np
    analyses, corners = _sibling_library(tmp_path)
    record = tv.share_side_board(analyses / "Throw-B")
    assert record is not None and record["source"] == "sibling_throw" and record["from_throw"] == "Throw-A"
    assert record["same_take"] is True and record["reference_frame"] == 0
    assert np.allclose(record["corners_px"], np.asarray(corners) + [5, 3], atol=0.6)
    assert json.loads((analyses / "Throw-B" / "board_corners.json").read_text())["source"] == "sibling_throw"


def test_shared_deck_never_replaces_clicked_corners_or_comes_from_a_shared_one(tmp_path: Path):
    analyses, corners = _sibling_library(tmp_path)
    (analyses / "Throw-B" / "board_corners.json").write_text(json.dumps({"corners_px": corners, "reference_frame": 0}))
    assert tv.share_side_board(analyses / "Throw-B") is None                         # clicked: kept
    (analyses / "Throw-A" / "board_corners.json").write_text(json.dumps({"corners_px": corners, "source": "sibling_throw"}))
    (analyses / "Throw-B" / "board_corners.json").unlink()
    assert tv.share_side_board(analyses / "Throw-B") is None                         # A's deck was itself shared


def test_no_new_bag_on_the_visible_deck_means_off_the_board():
    off = tv.decide_result({"where": None, "deck_clear": True}, {"board_phase": {"end": {"kind": "left_deck"}}})
    assert off["category"] == "offBoard" and off["points"] == 0 and off["status"] == "suggested"
    unsure = tv.decide_result({"where": None, "deck_clear": True}, {"board_phase": {"end": {"kind": "rest"}}})
    assert unsure["category"] == "offBoard" and unsure["status"] == "needs_confirmation"
    alone = tv.decide_result({"where": None, "deck_clear": True}, {})
    assert alone["status"] == "needs_confirmation"
    text = tv.explain({"result": off, "miss": tv.miss_vector({"rest": None}), "heading": {"deg": -4.3}, "frontal": {}}, {})
    assert text["sentence"].startswith("Off the board — aimed 4.3° left") and text["kind"] == "miss"


def test_throws_from_one_side_camera_setup_pool_together_across_athletes(tmp_path: Path):
    take = tmp_path / "takes" / "Take-01-x"
    take.mkdir(parents=True)
    (take / "take.json").write_text(json.dumps({"take": 1, "side": {"model": "iPhone 15 Pro Max", "size": [1920, 1080],
                                                                    "recorded": "2026-10-01"},
                                                "throws": [{"number": n} for n in (1, 2, 3)]}))
    centres = {"A": (1700, 640), "B": (1711, 638), "C": (1300, 600)}      # C: the tripod moved
    folders = []
    for n, (name, (x, y)) in enumerate(centres.items(), 1):
        folder = tmp_path / "analyses" / name
        folder.mkdir(parents=True)
        (folder / tv.TAKE_LINK_FILENAME).write_text(json.dumps({"take_record": "../../takes/Take-01-x/take.json",
                                                                "throw_number": n}))
        corners = [[x - 150, y], [x - 110, y + 20], [x + 150, y], [x + 110, y - 20]]
        (folder / "auto_flight.json").write_text(json.dumps({"board": {"status": "found", "corners_px": corners}}))
        folders.append(folder)
    groups = tv.side_camera_setups(folders)
    sizes = sorted(len(v) for v in groups.values())
    assert sizes == [1, 2] and all(k.startswith("iPhone 15 Pro Max 1920x1080 2026-10-01") for k in groups)


def test_the_side_camera_decides_which_bag_was_thrown_when_one_was_knocked():
    front = {"where": "hole", "ambiguous": True, "notes": ["This throw moved a bag that was already on the board."],
             "rest": {"x_in": 12.0, "y_in_front": 39.0},
             "ambiguous_candidates": {"board": {"x_in": 12.6, "y_in_front": 37.0, "px": [1, 2]},
                                      "hole": {"x_in": 12.0, "y_in_front": 39.0, "px": [3, 4]}}}
    lip = tv.resolve_knocked_bag(front, {"status": "measured", "end": {"kind": "rest", "v_in": 38.7}})
    assert lip["where"] == "board" and lip["rest"]["x_in"] == 12.6 and lip["ambiguous_resolved_by"] == "side camera"
    record = {"status": "measured", "front_landing": lip, "landing": tv.fuse_landing(lip, {}, {}, {}),
              "result": tv.decide_result({"where": "board"}, {"board_phase": {"end": {"kind": "rest"}}})}
    assert tv.outcome_from_two_view(record)["score_category"] == 1
    unknown = tv.resolve_knocked_bag(front, {"status": "not_found"})
    assert unknown is front                                          # no side ending: still ambiguous
    assert tv.outcome_from_two_view({**record, "front_landing": front}) is None


def test_the_front_picture_lag_shifts_the_mapping():
    link = {"front_clip": {"side_frame0_front_time_s": 0.0, "frame_times_s": [i / 30 for i in range(100)], "fps": 30},
            "side_clip": {"frame_times_s": [i / 59.94 for i in range(300)]}, "front_lag_s": 1 / 30}
    assert tv.side_to_front_frame(120, 59.94, link) == round(120 / 59.94 * 30) + 1


def _lag_library(tmp_path: Path, differences, applied=0.0):
    take = tmp_path / "takes" / "Take-01-x"
    take.mkdir(parents=True)
    (take / "take.json").write_text(json.dumps({"take": 1, "front": {"model": "iPhone 17 Pro", "size": [1920, 1080],
                                                                     "recorded": "2026-10-01"},
                                                "throws": [{"number": n} for n in range(1, len(differences) + 1)]}))
    folders = []
    for n, diff in enumerate(differences, 1):
        folder = tmp_path / "analyses" / f"T{n}"
        folder.mkdir(parents=True)
        (folder / tv.TAKE_LINK_FILENAME).write_text(json.dumps({"take_record": "../../takes/Take-01-x/take.json",
                                                                "throw_number": n}))
        check = {"status": "unavailable"} if diff is None else {"status": "measured", "front_frames_difference": diff}
        (folder / "two_view.json").write_text(json.dumps({"status": "measured", "method_version": tv.TWO_VIEW_VERSION,
                                                          "sync_check": check,
                                                          "frames": {"front_fps": 30.0, "front_lag_s": applied}}))
        folders.append(folder)
    return take / "take.json", folders


def test_front_lag_is_the_setup_median_and_is_written_into_the_take(tmp_path: Path):
    take, folders = _lag_library(tmp_path, [1, 1, 2, 0, 1, 1, -1, 1, 2, None, 1])
    pools = tv.pool_front_lag(folders)
    (pool,) = pools.values()
    expected = 1 / 30 - (0.5 / 30 - 0.5 / 60)       # one front frame minus the expected frame quantisation
    assert pool["status"] == "measured" and pool["throws"] == 10
    assert abs(pool["lag_s"] - expected) < 1e-9
    assert abs(json.loads(take.read_text())["front_lag_s"] - expected) < 1e-9
    assert abs(tv.load_take_link(folders[0])["front_lag_s"] - expected) < 1e-9


def test_front_lag_adds_the_lag_already_applied_and_needs_enough_throws(tmp_path: Path):
    _, folders = _lag_library(tmp_path / "a", [0] * 9, applied=1 / 30)      # already corrected: residual 0
    (pool,) = tv.pool_front_lag(folders).values()
    assert abs(pool["lag_s"] - (1 / 30 - (0.5 / 30 - 0.5 / 60))) < 1e-9
    _, few = _lag_library(tmp_path / "b", [1, 1, 1])
    (pool,) = tv.pool_front_lag(few).values()
    assert pool["status"] == "unavailable"
    take, wild = _lag_library(tmp_path / "c", [6, 7, 6, 8, 6, 7, 6, 7])    # 0.2 s: a fault, not a picture lag
    (pool,) = tv.pool_front_lag(wild).values()
    assert pool["status"] == "rejected" and json.loads(take.read_text())["front_lag_s"] == 0.0


def test_new_takes_of_a_setup_get_its_measured_lag(tmp_path: Path):
    from cornhole_biomech.takes import share_front_lag
    measured = tmp_path / "a.json"
    new = tmp_path / "b.json"
    measured.write_text(json.dumps({"front_lag_s": 0.03, "front_lag_pool": {"status": "measured", "lag_s": 0.03,
                                                                           "throws": 40}}))
    new.write_text(json.dumps({}))
    share_front_lag([measured, new])
    assert json.loads(new.read_text())["front_lag_s"] == 0.03
