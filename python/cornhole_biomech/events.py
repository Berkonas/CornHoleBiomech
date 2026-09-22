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


def detect_events(
    normalized_wrist: np.ndarray,
    fps: float,
    release_candidate: EventValue | None = None,
) -> dict[str, EventValue]:
    """Detect candidate events from filtered shoulder-relative wrist motion.

    When supplied, a reviewed bag-track candidate based on persistent bag/wrist
    divergence takes priority over the wrist-only proxy. Otherwise release is
    peak target-axis wrist velocity after backswing. Both remain frame-limited
    candidates until manually reviewed.
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
    wrist_release = int(start + np.nanargmax(velocity[start : end + 1, 0]))
    if wrist_release <= start:
        later = np.flatnonzero(valid & (np.arange(len(valid)) > start) & (np.arange(len(valid)) <= end))
        if later.size: wrist_release = int(later[0])
    use_bag = (
        release_candidate is not None
        and release_candidate.automatic_frame is not None
        and start < release_candidate.automatic_frame < end
        and valid[release_candidate.automatic_frame]
    )
    provisional_release = int(release_candidate.automatic_frame) if use_bag else wrist_release
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
    result = {
        name: EventValue(
            name=name,
            automatic_frame=frames[name],
            automatic_confidence=confidence,
            automatic_method="filtered_shoulder_relative_wrist_heuristic_v2",
        )
        for name in EVENT_ORDER
    }
    if use_bag:
        result["release"] = EventValue(
            name="release",
            automatic_frame=provisional_release,
            automatic_confidence=release_candidate.automatic_confidence,
            automatic_method=release_candidate.automatic_method,
        )
    return result


def apply_manual_event_overrides(
    events: dict[str, EventValue], overrides: dict[str, int | None]
) -> dict[str, EventValue]:
    """Apply manual values separately while retaining automatic candidates."""
    result = {name: EventValue(**vars(value)) for name, value in events.items()}
    for name, frame in overrides.items():
        if name in result:
            result[name].manual_frame = None if frame is None else int(frame)
    manual = [result[name].manual_frame for name in EVENT_ORDER if result[name].manual_frame is not None]
    if manual != sorted(manual):
        raise ValueError("Reviewed events are out of order. Check the manually marked start, backswing, release and follow-through frames.")
    # A corrected release can legitimately precede/follow the wrist-only proxy.
    # Preserve automatic provenance but withhold conflicting automatic phases;
    # never force the user to accept an incorrect release to satisfy a heuristic.
    for index, name in enumerate(EVENT_ORDER):
        event = result[name]
        event.suppressed_reason = None
        if event.manual_frame is not None or event.automatic_frame is None:
            continue
        before = [result[n].manual_frame for n in EVENT_ORDER[:index] if result[n].manual_frame is not None]
        after = [result[n].manual_frame for n in EVENT_ORDER[index+1:] if result[n].manual_frame is not None]
        if (before and event.automatic_frame < max(before)) or (after and event.automatic_frame > min(after)):
            event.suppressed_reason = "Automatic candidate conflicts with a reviewed event; review this phase separately."
    return result
