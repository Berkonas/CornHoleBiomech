"""Regulation cornhole equipment — ACL board and bag constants."""
import math

import pytest

from cornhole_biomech import regulation, zones
from cornhole_biomech.regulation import BAG_MASS_KG, BAG_MASS_RANGE_KG, Board


def test_board_geometry_matches_acl():
    b = Board()
    assert b.length_m == pytest.approx(48 * 0.0254)
    assert b.width_m == pytest.approx(24 * 0.0254)
    assert b.hole_radius_m == pytest.approx(3 * 0.0254)
    assert b.hole_along == pytest.approx(39 * 0.0254)
    assert math.degrees(b.angle) == pytest.approx(10.8, abs=0.1)
    assert b.deck_height_at(0.0) == pytest.approx(3 * 0.0254)
    assert b.deck_height_at(b.horizontal_length_m) == pytest.approx(12 * 0.0254, abs=1e-6)


def test_bag_mass_range_contains_nominal():
    lo, hi = BAG_MASS_RANGE_KG
    assert lo == pytest.approx(0.4394, abs=1e-4) and hi == pytest.approx(0.4536, abs=1e-4)
    assert lo < BAG_MASS_KG < hi


def test_zones_uses_regulation_board():
    assert zones.Board is regulation.Board
    assert regulation.PITCH_FRONT_TO_FRONT_M == pytest.approx(8.2296)
