"""Regulation cornhole equipment — one source for every calculation.

American Cornhole League rules and equipment pages (docs/REFERENCES.md). The front
height varies between certified boards (2.5–4 in); 3 in is the default and a
session may override it with the measured value.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

INCH_M = 0.0254
OUNCE_KG = 0.028349523125
BAG_SIDE_M = 6 * INCH_M
BAG_MASS_KG = 15.75 * OUNCE_KG
BAG_MASS_RANGE_KG = (15.5 * OUNCE_KG, 16.0 * OUNCE_KG)
PITCH_FRONT_TO_FRONT_M = 27 * 12 * INCH_M


@dataclass(frozen=True)
class Board:
    length_m: float = 48 * INCH_M
    width_m: float = 24 * INCH_M
    front_height_m: float = 3 * INCH_M
    back_height_m: float = 12 * INCH_M
    hole_from_back_m: float = 9 * INCH_M
    hole_radius_m: float = 3 * INCH_M
    hole_from_side_m: float = 12 * INCH_M

    @property
    def angle(self) -> float:
        """Deck slope in radians."""
        return math.asin((self.back_height_m - self.front_height_m) / self.length_m)

    @property
    def hole_along(self) -> float:
        """Hole centre, metres from the front edge measured along the deck."""
        return self.length_m - self.hole_from_back_m

    @property
    def horizontal_length_m(self) -> float:
        return self.length_m * math.cos(self.angle)

    def deck_height_at(self, x_m: float) -> float:
        """Deck surface height above the floor at horizontal distance x_m past the front edge."""
        return self.front_height_m + x_m * math.tan(self.angle)
