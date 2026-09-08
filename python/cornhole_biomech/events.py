"""Transparent, frame-limited cornhole movement-event detection."""

from __future__ import annotations

import numpy as np

from .models import EventValue


EVENT_ORDER = (
    "motion_start",
    "peak_backswing",
    "forward_swing",
    "release",
    "peak_follow_through",
    "motion_end",
)


def _sustained(mask: np.ndarray, count: int) -> np.ndarray:
    if count <= 1:
        return mask
    convolution = np.convolve(mask.astype(int), np.ones(count, dtype=int), mode="same")
    return convolution >= count


def detect_events(normalized_wrist: np.ndarray, fps: float) -> dict[str, EventValue]:
    """Detect candidate events from filtered shoulder-relative wrist motion.

    Release is a visible-kinematic proxy: peak target-axis wrist velocity after
    backswing. It is not direct projectile-hand separation and carries at least
    frame-interval uncertainty.
    """
    wrist = np.asarray(normalized_wrist, float)
    valid = np.isfinite(wrist).all(axis=-1)
    if np.count_nonzero(valid) < 5:
        return {name: EventValue(name=name) for name in EVENT_ORDER}
    from .filtering import derivative
    # Never invent velocity across a long occlusion for event selection.
    velocity = derivative(wrist, fps)
    valid = valid & np.isfinite(velocity).all(axis=-1)
    if np.count_nonzero(valid) < 3:
        return {name: EventValue(name=name) for name in EVENT_ORDER}
    velocity[~valid] = np.nan
    speed = np.linalg.norm(velocity, axis=-1)
    speed[~valid] = np.nan
    peak_speed = float(np.nanmax(speed))
    if peak_speed < 0.05:
        return {name: EventValue(name=name) for name in EVENT_ORDER}
    threshold = max(0.05, 0.12 * peak_speed)
    moving = _sustained(np.nan_to_num(speed) >= threshold, max(2, int(round(0.05 * fps))))
    moving_indices = np.flatnonzero(moving & valid)
    if not moving_indices.size:
        start, end = int(np.flatnonzero(valid)[0]), int(np.flatnonzero(valid)[-1])
    else:
        start, end = int(moving_indices[0]), int(moving_indices[-1])
    x = np.where(valid, wrist[:, 0], np.nan)
    provisional_release = int(start + np.nanargmax(velocity[start : end + 1, 0]))
    if provisional_release <= start:
        later = np.flatnonzero(valid & (np.arange(len(valid)) > start) & (np.arange(len(valid)) <= end))
        if later.size: provisional_release = int(later[0])
    backswing = int(start + np.nanargmin(x[start : provisional_release + 1]))
    follow = int(provisional_release + np.nanargmax(x[provisional_release : end + 1]))
    forward_candidates = np.flatnonzero(valid & (np.arange(len(valid)) > backswing) & (np.arange(len(valid)) <= provisional_release))
    forward = int(forward_candidates[0]) if forward_candidates.size else provisional_release
    confidence = float(np.clip(np.nanmean(valid[start : end + 1]), 0.0, 1.0))
    frames = {
        "motion_start": start,
        "peak_backswing": backswing,
        "forward_swing": forward,
        "release": provisional_release,
        "peak_follow_through": follow,
        "motion_end": end,
    }
    return {
        name: EventValue(
            name=name,
            automatic_frame=frames[name],
            automatic_confidence=confidence,
            automatic_method="filtered_shoulder_relative_wrist_heuristic_v2",
        )
        for name in EVENT_ORDER
    }


def apply_manual_event_overrides(
    events: dict[str, EventValue], overrides: dict[str, int | None]
) -> dict[str, EventValue]:
    """Apply manual values separately while retaining automatic candidates."""
    result = {name: EventValue(**vars(value)) for name, value in events.items()}
    for name, frame in overrides.items():
        if name in result:
            result[name].manual_frame = None if frame is None else int(frame)
    effective = [result[name].effective_frame for name in EVENT_ORDER]
    known = [v for v in effective if v is not None]
    if known != sorted(known):
        raise ValueError("manual event frames must preserve movement-event order")
    return result

