"""replay.json must decode in the app (Swift `ReplayDocument`), or the report shows no replay and no video.

The Swift decoder is strict: `after_contact` is a list of {frame:int, x, y}; every event has an int frame and a
string label; grades are strings; the file has no NaN/Infinity. A board-phase slide summary once overwrote
`after_contact` with a dict, and every re-analyzed throw lost its video replay.
"""
import json

import numpy as np

from cornhole_biomech.board import solve_board
from cornhole_biomech.board_phase import summarize_board_phase
from cornhole_biomech.replay import build_replay

from test_board_phase import CORNERS, FPS, decelerating, track


def assert_swift_decodable(replay: dict) -> None:
    text = json.dumps(replay, allow_nan=False)          # JSONDecoder rejects NaN / Infinity
    doc = json.loads(text)
    assert isinstance(doc["fps"], (int, float))
    for key in ("frame_count", "width", "height"):
        assert isinstance(doc[key], int) and not isinstance(doc[key], bool), key
    assert isinstance(doc["coordinates"], str)
    for key in ("measured", "filtered", "model", "after_contact"):
        assert isinstance(doc[key], list), key
        for point in doc[key]:
            assert isinstance(point["frame"], int), (key, point)
            assert isinstance(point["x"], (int, float)) and isinstance(point["y"], (int, float)), (key, point)
    assert isinstance(doc["events"], dict)
    for name, event in doc["events"].items():
        assert isinstance(event["frame"], int), name
        assert isinstance(event["label"], str), name
        if event.get("position") is not None:
            assert all(isinstance(event["position"][c], (int, float)) for c in "xy"), name
        for value in event.get("values") or []:
            assert all(isinstance(value[f], str) for f in ("key", "label", "unit", "status")), (name, value)
            assert value.get("value") is None or isinstance(value["value"], (int, float)), (name, value)
    assert isinstance(doc["grades"], dict) and all(isinstance(v, str) for v in doc["grades"].values())


def _replay(phase):
    measured = np.full((200, 2), np.nan)
    measured[50:90] = np.column_stack([np.linspace(200, 1500, 40), np.linspace(500, 640, 40)])
    return build_replay(
        fps=FPS, frame_count=200 + 200, width=1920, height=1080, camera_to_release=None, measured=measured,
        filtered=None, model_check=None, after_contact=None,
        events={"release": 50, "first_contact": None, "peak_backswing": 30},
        summaries={}, coach_metrics={}, grades={"bag": {"grade": "good"}, "scale": {"grade": None}},
        release_window=(49, 51), board_phase=phase)


def test_replay_with_a_board_bag_decodes_in_the_app():
    model = solve_board(CORNERS, (1920, 1080))
    along = decelerating(90, 220, 12.0, 40)
    along += [along[-1]] * 60
    phase = summarize_board_phase(track(model, along), model, FPS, 100 + len(along))
    replay = _replay(phase)
    assert_swift_decodable(replay)
    # The slide is drawn from the board phase even though the flight itself was not accepted.
    assert replay["after_contact"] and replay["after_contact"][0]["frame"] == phase["touchdown"]["frame"]
    assert replay["after_contact"][-1]["frame"] <= phase["end"]["frame"]
    assert replay["events"]["final_rest"]["frame"] == phase["end"]["frame"]
    assert replay["events"]["first_contact"]["frame"] == phase["touchdown"]["frame"]


def test_replay_with_a_bag_into_the_hole_decodes_in_the_app():
    model = solve_board(CORNERS, (1920, 1080))
    along = decelerating(80, 160, 20.0, 30) + [40.5] * 36 + [None] * 40
    areas = [800.0] * 50 + list(np.linspace(800, 350, 16)) + [0] * 40
    phase = summarize_board_phase(track(model, along, areas=areas), model, FPS, 100 + len(along))
    replay = _replay(phase)
    assert_swift_decodable(replay)
    assert "into_hole" in replay["events"]
    assert replay["grades"] == {"bag": "good"}


def test_replay_without_a_board_phase_decodes_in_the_app():
    assert_swift_decodable(_replay(None))
