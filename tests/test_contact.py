import math

import numpy as np
import pytest

from cornhole_biomech.contact import (classify_flight_end, landing_summary, predict_contact, suggest_outcome,
                                      surface_at)
from cornhole_biomech.regulation import INCH_M, Board


class PlaneStub:
    """Image pixel (x, y) → plane metres: x/100 − 8, (1000 − y)/100 ; deck inches via the same map."""
    board = Board()

    def to_plane(self, pts):
        p = np.asarray(pts, float).reshape(-1, 2)
        return np.column_stack([p[:, 0] / 100 - 8.0, (1000 - p[:, 1]) / 100])

    def to_deck_inches(self, pts):
        xy = self.to_plane(pts)
        v = xy[:, 0] / math.cos(self.board.angle) / INCH_M
        return np.column_stack([np.full(len(v), 12.0), v])

    def along_precision_in_per_px(self, p):
        return 0.01 / INCH_M

    def across_precision_in_per_px(self, p):
        return 0.5


M = PlaneStub()


def px(x_m, y_m):
    return np.array([(x_m + 8.0) * 100, 1000 - y_m * 100])


def test_surfaces():
    b = M.board
    assert surface_at(px(0.5, b.deck_height_at(0.5) + 0.03), M) == "deck"
    assert surface_at(px(0.5, 0.8), M) == "air"
    assert surface_at(px(-1.0, 0.02), M) == "floor"
    assert surface_at(px(0.0, 0.03), M) == "front"


def test_mid_air_end_is_lost_in_flight():
    assert classify_flight_end(px(0.2, 0.9), M)["kind"] == "lost_in_flight"
    assert classify_flight_end(px(0.6, M.board.deck_height_at(0.6) + 0.02), M)["kind"] == "deck"


def test_predicted_contact_extends_parabola_to_deck():
    fps = 60.0
    # plane motion x = −2 + 6 t, y = 1.2 + 1 t − 4.9 t² expressed in pixels (stub map is linear)
    coef_x = [600.0, 600.0, 0.0]          # x_px = 600 + 600 t  →  plane x = −2 + 6 t
    coef_y = [1000 - 120.0, -100.0, 490.0]
    out = predict_contact(coef_x, coef_y, 0, fps, last_frame=10, frame_count=200,
                          to_reference=lambda f, p: p, model=M)
    assert out is not None and out["state"] == "estimated"
    assert out["kind"] in ("deck", "front", "floor")
    assert out["frame"] > 10


def test_landing_summary_along_error_relative_to_hole():
    b = M.board
    hole_x = b.hole_along * math.cos(b.angle)
    out = landing_summary(px(hole_x + 0.1, b.deck_height_at(hole_x + 0.1)), M)
    assert out["along_error_m"] == pytest.approx(0.1, abs=1e-6)
    assert out["on_deck"] is True


def test_suggest_outcome_rules():
    b = M.board
    hole_x = b.hole_along * math.cos(b.angle)
    hole_px = px(hole_x, b.deck_height_at(hole_x))
    lost_at_hole = {"status": "lost_after_contact", "rest": None,
                    "path": [{"x_release_frame": hole_px[0], "y_release_frame": hole_px[1]}]}
    assert suggest_outcome(lost_at_hole, M)["score"] == 3
    rest_on = {"status": "rest_found", "path": [], "rest": {"x_release_frame": px(0.4, 0.2)[0],
                                                           "y_release_frame": px(0.4, 0.2)[1]}}
    assert suggest_outcome(rest_on, M)["score"] == 1
    rest_off = {"status": "rest_found", "path": [], "rest": {"x_release_frame": px(-1.5, 0.0)[0],
                                                            "y_release_frame": px(-1.5, 0.0)[1]}}
    assert suggest_outcome(rest_off, M)["score"] == 0
    assert suggest_outcome(None, M)["score"] is None
