"""Board phase: touchdown, slide, rest vs. drop into the hole, slide physics (board_phase.py)."""
import math

import cv2
import numpy as np
import pytest

from cornhole_biomech.board import solve_board
from cornhole_biomech.board_phase import (HOLE_V_IN, as_after_contact, slide_kinematics,
                                          summarize_board_phase)
from cornhole_biomech.regulation import INCH_M, Board

# Deck corners of a real pilot board (tripod clip, 1080p): front-far, front-near, back-near, back-far.
CORNERS = np.array([[1593.0, 671.4], [1643.0, 699.6], [1919.0, 656.9], [1850.0, 629.3]])
FPS = 59.94


@pytest.fixture(scope="module")
def model():
    return solve_board(CORNERS, (1920, 1080))


def pixel(model, u, v):
    inverse = np.linalg.inv(model.deck_H)
    return cv2.perspectiveTransform(np.array([[[u, v]]], float), inverse)[0, 0]


def track(model, along, start=100, area=800.0, u=12.0, areas=None):
    """Samples of a bag on the deck at the given along-deck positions (one per frame)."""
    out = []
    for i, v in enumerate(along):
        if v is None:
            out.append({"frame": start + i, "present": False})
            continue
        x, y = pixel(model, u, v)
        out.append({"frame": start + i, "present": True, "x_release_frame": float(x), "y_release_frame": float(y),
                    "area_px": areas[i] if areas else area})
    return out


def decelerating(v0_in_s, a_in_s2, start_in, n):
    t = np.arange(n) / FPS
    s = start_in + v0_in_s * t - 0.5 * a_in_s2 * t ** 2
    stop = v0_in_s / a_in_s2
    s[t > stop] = start_in + v0_in_s * stop - 0.5 * a_in_s2 * stop ** 2
    return list(s)


def test_bag_that_stops_on_the_deck_is_a_board_bag(model):
    along = decelerating(90, 220, 12.0, 40) + [None] * 0
    along += [along[-1]] * 60                        # still there when the clip ends
    phase = summarize_board_phase(track(model, along), model, FPS, 100 + len(along))
    assert phase["status"] == "measured"
    assert phase["end"]["kind"] == "rest"
    assert phase["suggested_outcome"]["score"] == 1
    assert phase["end"]["from_hole_in"] == pytest.approx(along[-1] - HOLE_V_IN, abs=0.5)
    assert phase["slide"]["distance_in"] == pytest.approx(along[-1] - 12.0, abs=1.0)


def test_pause_on_the_lip_then_drop_is_a_hole_not_a_board_bag(model):
    """The old rule took the first quiet 0.2 s as the final rest; a bag hanging on the lip then dropping is a 3."""
    slide = decelerating(80, 160, 20.0, 30)
    hang = [40.5] * 36
    areas = [800.0] * (len(slide) + 20) + list(np.linspace(800, 350, 16))
    along = slide + hang + [None] * 40
    phase = summarize_board_phase(track(model, along, areas=areas + [0] * 40), model, FPS, 100 + len(along))
    assert phase["end"]["kind"] == "fell_in_hole"
    assert phase["hang"] is not None and phase["hang"]["seconds"] > 0.3
    assert phase["drained"] is True
    assert phase["suggested_outcome"]["score"] == 3
    assert as_after_contact(phase)["status"] == "fell_in_hole"


def test_bag_that_vanishes_away_from_the_hole_is_not_scored_as_a_hole(model):
    along = decelerating(60, 200, 10.0, 20) + [None] * 30
    phase = summarize_board_phase(track(model, along), model, FPS, 100 + len(along))
    assert phase["end"]["kind"] in ("lost", "left_deck")
    assert (phase["suggested_outcome"] or {}).get("score") != 3


def test_bag_sliding_off_the_back_is_a_miss(model):
    along = [30 + 2.5 * i for i in range(12)] + [None] * 30   # passes the hole's far side and off the back
    phase = summarize_board_phase(track(model, along, u=3.0), model, FPS, 100 + len(along))
    assert phase["end"]["kind"] == "left_deck"
    assert phase["suggested_outcome"]["score"] == 0


def test_moving_bag_that_vanishes_at_a_side_edge_left_the_deck(model):
    """QA D5 (Player 2 take 5 throw 4): last seen sliding at about 21.6 in across, then on the floor."""
    along = [14 + 1.5 * i for i in range(10)] + [None] * 30
    for u in (23.0, 0.0):
        phase = summarize_board_phase(track(model, along, u=u), model, FPS, 100 + len(along))
        assert phase["end"]["kind"] == "left_deck" and phase["end"].get("edge") == "side"
        assert phase["suggested_outcome"]["score"] == 0


def test_moving_bag_that_vanishes_mid_deck_is_still_lost(model):
    along = [14 + 1.5 * i for i in range(10)] + [None] * 30
    phase = summarize_board_phase(track(model, along, u=12.0), model, FPS, 100 + len(along))
    assert phase["end"]["kind"] == "lost"


def test_no_samples_on_the_board():
    phase = summarize_board_phase([{"frame": 5, "present": False}], solve_board(CORNERS, (1920, 1080)), FPS, 50)
    assert phase["status"] == "not_found"
    assert phase["suggested_outcome"] is None


def test_slide_friction_recovers_the_simulated_coefficient():
    board = Board()
    mu = 0.4
    a = 9.80665 * (math.sin(board.angle) + mu * math.cos(board.angle))    # m/s², up the slope
    t = np.arange(0, 0.3, 1 / FPS)
    s = (2.4 * t - 0.5 * a * t ** 2) / INCH_M
    kin = slide_kinematics(t, s, board.angle)
    assert kin["state"] == "estimated"
    assert kin["entry_speed_m_s"] == pytest.approx(2.4, abs=0.01)
    assert kin["mu_effective"] == pytest.approx(mu, abs=0.01)


def test_short_slide_gives_no_friction():
    kin = slide_kinematics(np.arange(4) / FPS, np.array([10, 10.5, 10.8, 11.0]), Board().angle)
    assert kin["mu_effective"] is None and kin["reason"]


def _image_of_bag_centre(model, u_in, v_in, lift_in=0.6):
    """Pixel of a point u, v on the deck, lifted lift_in above it (camera pose from the board corners)."""
    b = model.board
    origin = np.array([0.0, b.front_height_m, -b.width_m / 2])
    along = np.array([math.cos(b.angle), math.sin(b.angle), 0.0])
    normal = np.array([-math.sin(b.angle), math.cos(b.angle), 0.0])
    world = origin + along * v_in * INCH_M + np.array([0, 0, u_in * INCH_M]) + normal * lift_in * INCH_M
    px, _ = cv2.projectPoints(world.reshape(1, 3), model.rvec, model.tvec, model.K, None)
    return px.reshape(2)


@pytest.mark.parametrize("u_true", [4.0, 12.0, 20.0])
def test_left_right_position_on_the_board_is_recovered(model, u_true):
    """Bags land all over the board: the across-deck position is measured (bag centre above the deck), not centred."""
    samples = []
    for i in range(60):
        x, y = _image_of_bag_centre(model, u_true, 30.0)
        samples.append({"frame": 100 + i, "present": True, "x_release_frame": float(x), "y_release_frame": float(y),
                        "area_px": 800.0})
    right = summarize_board_phase(samples, model, FPS, 160, target_direction="left_to_right")
    assert right["end"]["kind"] == "rest"
    assert right["end"]["u_in"] == pytest.approx(u_true, abs=0.5)
    assert right["end"]["right_of_centre_in"] == pytest.approx(u_true - 12.0, abs=0.5)
    assert right["touchdown"]["right_of_centre_in"] == pytest.approx(u_true - 12.0, abs=0.5)
    # Thrown the other way, the camera side is the thrower's left.
    left = summarize_board_phase(samples, model, FPS, 160, target_direction="right_to_left")
    assert left["end"]["right_of_centre_in"] == pytest.approx(12.0 - u_true, abs=0.5)
    # The old deck-plane mapping put a lifted bag centre inches toward the far side.
    assert right["path"][0]["right_of_centre_in"] == pytest.approx(u_true - 12.0, abs=0.5)
