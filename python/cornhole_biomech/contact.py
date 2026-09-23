"""First contact against the deck/floor (not "where tracking stopped"), predicted contact, landing, outcome.

A flight whose last tracked point is still in the air is `lost_in_flight`: its
parabola is extended to the first deck/floor intersection and reported as an
ESTIMATED contact, never as a measured one.
"""
from __future__ import annotations

import math
from typing import Any, Callable

import numpy as np

from .regulation import BAG_SIDE_M

DECK_TOLERANCE_M = 0.06      # bag half-thickness + plane-mapping noise
FLOOR_TOLERANCE_M = 0.06
HOLE_VANISH_RADIUS_IN = 4.0  # hole radius 3 in + 1 in tracking slack
MAX_PREDICT_SECONDS = 1.5


def _plane(point_px, model) -> np.ndarray:
    return model.to_plane(np.asarray(point_px, float).reshape(1, 2))[0]


def surface_at(point_px, model) -> str:
    """Which surface the plane point sits on: "deck", "front" (board face), "floor" or "air".

    The front face and the deck both sit near the front edge (x = 0), so the front
    check runs first and wins there; the deck check then covers its own footprint
    (extended by half a bag width at each end, for a bag overhanging an edge); the
    floor check catches everything else at ground height.
    """
    b = model.board
    x, y = _plane(point_px, model)
    half = BAG_SIDE_M / 2
    if -half <= x <= b.horizontal_length_m + half:
        if x < half and 0 <= y <= b.front_height_m + DECK_TOLERANCE_M:
            return "front"
        deck_x = min(max(x, 0.0), b.horizontal_length_m)
        if abs(y - b.deck_height_at(deck_x)) <= DECK_TOLERANCE_M:
            return "deck"
    if y <= FLOOR_TOLERANCE_M:
        return "floor"
    return "air"


def classify_flight_end(end_point_px, model) -> dict[str, Any]:
    """Classify the last tracked point of a flight: a surface, or `lost_in_flight` if it is air."""
    kind = surface_at(end_point_px, model)
    return {"kind": "lost_in_flight" if kind == "air" else kind, "plane_xy_m": _plane(end_point_px, model).tolist()}


def predict_contact(coef_x, coef_y, reference_frame: int, fps: float, last_frame: int, frame_count: int,
                    to_reference: Callable[[int, np.ndarray], np.ndarray], model) -> dict[str, Any] | None:
    """Extend the fitted parabola past `last_frame`, frame by frame, to the first deck/floor hit.

    `coef_x`/`coef_y` are ascending-power polynomials in t = (frame − reference_frame) / fps.
    Returns an ESTIMATED contact (never a measured one), or None if no surface is
    reached within `MAX_PREDICT_SECONDS` or before the clip ends.
    """
    stop = min(frame_count - 1, last_frame + int(MAX_PREDICT_SECONDS * fps))
    for f in range(last_frame + 1, stop + 1):
        t = (f - reference_frame) / fps
        raw = np.array([np.polyval(list(coef_x)[::-1], t), np.polyval(list(coef_y)[::-1], t)])
        p = to_reference(f, raw)
        kind = surface_at(p, model)
        if kind != "air":
            return {"frame": f, "x_px": float(p[0]), "y_px": float(p[1]), "kind": kind, "state": "estimated",
                    "reason": "Bag lost in the air; contact predicted by extending the fitted flight to the deck/floor."}
    return None


def landing_summary(contact_point_px, model) -> dict[str, Any]:
    """Metric and deck-inch position of a contact point, and error relative to the hole."""
    b = model.board
    x, y = _plane(contact_point_px, model)
    u, v = model.to_deck_inches(np.asarray(contact_point_px, float).reshape(1, 2))[0]
    return {"plane_x_m": float(x), "plane_y_m": float(y),
            "along_error_m": float(x - b.hole_along * math.cos(b.angle)),
            "deck_u_in": float(u), "deck_v_in": float(v),
            "on_deck": bool(0 <= u <= 24 and 0 <= v <= 48),
            "along_precision_in": model.along_precision_in_per_px(contact_point_px),
            "across_precision_in": model.across_precision_in_per_px(contact_point_px)}


def suggest_outcome(after_contact: dict[str, Any] | None, model) -> dict[str, Any]:
    """Score a throw from its post-contact track: 3 (hole), 1 (rest on deck), 0 (rest off deck) or None."""
    base = {"needs_confirmation": True}
    if not after_contact:
        return {**base, "score": None, "basis": "No post-contact track; confirm in the video."}
    rest = after_contact.get("rest")
    if after_contact.get("status") == "rest_found" and rest:
        u, v = model.to_deck_inches(np.array([[rest["x_release_frame"], rest["y_release_frame"]]]))[0]
        on = 0 <= u <= 24 and 0 <= v <= 48
        return {**base, "score": 1 if on else 0,
                "basis": f"Bag came to rest {'on' if on else 'off'} the deck (u {u:.0f} in, v {v:.0f} in)."}
    path = after_contact.get("path") or []
    if path:
        last = path[-1]
        u, v = model.to_deck_inches(np.array([[last["x_release_frame"], last["y_release_frame"]]]))[0]
        if math.hypot(u - 12.0, v - 39.0) <= HOLE_VANISH_RADIUS_IN:
            return {**base, "score": 3, "basis": "Bag disappeared at the hole."}
    return {**base, "score": None, "basis": "Final rest not found; confirm in the video."}
