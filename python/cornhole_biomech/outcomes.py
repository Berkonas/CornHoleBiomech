"""Cornhole board coordinates and transparent task-outcome errors."""

from __future__ import annotations

from dataclasses import asdict
import math
from typing import Any

from .models import BoardPoint, TrialOutcome

BOARD_WIDTH_IN = 24.0
BOARD_LENGTH_IN = 48.0
HOLE_CENTER_IN = (12.0, 39.0)
HOLE_RADIUS_IN = 3.0


def board_point_from_normalized(x: float, y: float) -> BoardPoint:
    """Map a clamped top-down UI click to documented board-surface inches."""
    return BoardPoint(
        x_inches=min(1.0, max(0.0, float(x))) * BOARD_WIDTH_IN,
        y_inches=min(1.0, max(0.0, float(y))) * BOARD_LENGTH_IN,
    )


def point_errors(target: BoardPoint, actual: BoardPoint) -> dict[str, float]:
    """Return signed lateral/longitudinal and radial error in board inches."""
    lateral = actual.x_inches - target.x_inches
    longitudinal = actual.y_inches - target.y_inches
    return {
        "lateral_error_inches": lateral,
        "longitudinal_error_inches": longitudinal,
        "radial_error_inches": math.hypot(lateral, longitudinal),
    }


def outcome_summary(outcome: TrialOutcome) -> dict[str, Any]:
    if outcome.score_category not in (None, 0, 1, 3):
        raise ValueError("score_category must be unknown (null), 0, 1, or 3")
    result: dict[str, Any] = asdict(outcome)
    for endpoint in ("first_contact", "final_resting"):
        actual = getattr(outcome, endpoint + "_point")
        result[endpoint + "_error"] = point_errors(outcome.intended_point, actual) if outcome.intended_point and actual else None
    # Legacy field now has ONE stable definition. Never substitute rest for contact.
    result["spatial_error"] = result["first_contact_error"]
    result["spatial_endpoint"] = "first_contact_point"
    result["score_status"] = "unobserved" if outcome.score_category is None else "observed_per_bag_value"
    result["precision_note"] = (
        "Board coordinates are approximate manual clicks and must not be interpreted as instrument-level precision."
    )
    return result

