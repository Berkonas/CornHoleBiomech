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


EVENT_METHOD = "filtered_shoulder_relative_wrist_heuristic_v4_peak_plus_delay"

# Wrist-only release (used only when no accepted bag flight supplies release): the bag leaves the
# hand AFTER the shoulder-relative wrist reaches its peak forward speed -- the hand decelerates as
# the arm rises while the bag rolls off the fingers. On 13 pilot throws with a frame-checked release
# (four players, 59.94 fps) the peak came 4-7 frames before release (median 5.5, mean 5.4 = 90 ms).
# Release is therefore the peak plus this delay; the residual on those throws was -2 to +1 frames
# (12 of 13 within +-1). Before this delay the proxy was 4-7 frames early on every throw.
RELEASE_AFTER_PEAK_WRIST_SPEED_S = 0.09

# The fastest rearward wrist movement of the backswing is sought this far before the top of the
# backswing. On the six audited throws it came 0.23–0.43 s before the top (whole backswing
# 0.5–0.8 s); 1 s covers that without reaching back into aiming or practice swings.
SWING_ONSET_SEARCH_S = 1.0
# Peak follow-through: the arm's highest point is sought this long after release. On the six
# audited two-camera throws the arm reached its highest point 0.12–1.6 s after release.
FOLLOW_THROUGH_WINDOW_S = 2.0
# A held follow-through pose wobbles (0.024 arm lengths ≈ 3 px peak-to-peak over a 1 s hold on an
# audited throw); the event is the first frame within this much of the highest point, so it marks
# the arrival at the top rather than an arbitrary frame inside the hold.
FOLLOW_THROUGH_TOLERANCE_ARM_LENGTHS = 0.02


def _sustained(mask: np.ndarray, count: int) -> np.ndarray:
    if count <= 1:
        return mask
    convolution = np.convolve(mask.astype(int), np.ones(count, dtype=int), mode="same")
    return convolution >= count


def _swing_onset(speed: np.ndarray, velocity_x: np.ndarray, valid: np.ndarray, top: int,
                 threshold: float, fps: float) -> int | None:
    """Last quiet frame before the backswing (the throw's motion start).

    The wrist also stops at the top of the backswing, so the search runs back from the fastest
    rearward wrist movement in the `SWING_ONSET_SEARCH_S` before the top, not from the top itself.
    Walking in, aiming, practice swings or fidgeting earlier in the clip end with a quiet frame
    (shoulder-relative wrist speed below the motion threshold), so they are not counted.
    """
    lo = max(0, top - int(round(SWING_ONSET_SEARCH_S * fps)))
    rearward = np.where(valid[lo:top], -velocity_x[lo:top], np.nan)
    if not np.isfinite(rearward).any() or np.nanmax(rearward) <= 0:
        return None
    fastest = lo + int(np.nanargmax(rearward))
    quiet = np.flatnonzero(valid[:fastest] & (np.nan_to_num(speed[:fastest], nan=np.inf) < threshold))
    return int(quiet[-1]) if quiet.size else None


def _peak_follow_through(height: np.ndarray, release: int, end: int, fps: float) -> int | None:
    """Arrival of the throwing wrist at its highest shoulder-relative point after release."""
    stop = min(end, release + int(round(FOLLOW_THROUGH_WINDOW_S * fps)))
    segment = height[release:stop + 1]
    if not np.isfinite(segment).any():
        return None
    near_top = np.nan_to_num(segment, nan=-np.inf) >= np.nanmax(segment) - FOLLOW_THROUGH_TOLERANCE_ARM_LENGTHS
    return int(release + np.flatnonzero(near_top)[0])


def elbow_extension_search_start(extension_velocity: np.ndarray, start: int, release: int) -> int:
    """Start of the forward-swing search for peak elbow extension velocity.

    The elbow often straightens during the backswing and that extension decays across the top.
    Its tail is not forward-swing extension (two audited throws reported it as the "peak" 5 and
    2 frames after the top while the elbow only flexed in the forward swing), so the search
    starts at the first frame from `start` (top of the backswing) to release where dθ/dt ≤ 0.
    If the elbow extends without pause from the top to release, the search starts at `start`.
    """
    v = np.asarray(extension_velocity, float)
    lo, hi = max(0, start), min(len(v) - 1, release)
    stopped = np.flatnonzero(np.nan_to_num(v[lo:hi + 1], nan=np.inf) <= 0) if hi >= lo else np.array([], int)
    return int(lo + stopped[0]) if stopped.size else start


def detect_events(
    normalized_wrist: np.ndarray,
    fps: float,
    release_candidate: EventValue | None = None,
) -> dict[str, EventValue]:
    """Detect candidate events from filtered shoulder-relative wrist motion.

    When supplied, a reviewed bag-track candidate based on persistent bag/wrist
    divergence takes priority over the wrist-only proxy. Otherwise release is
    the frame of peak target-axis wrist velocity plus RELEASE_AFTER_PEAK_WRIST_SPEED_S
    (0.09 s, pilot calibration), within the motion. Both remain frame-limited
    candidates until manually reviewed.

    Moving = shoulder-relative wrist speed ≥ max(0.05, 0.12 × peak) arm lengths/s.
    - motion_end: last frame of sustained (≥ 0.05 s) moving.
    - peak_backswing: most rearward wrist (min target-axis x) before release.
    - motion_start: last non-moving frame before the fastest rearward wrist movement in the
      1 s before peak_backswing (the start of the throwing swing). Falls back to the first
      sustained moving frame when the wrist never goes quiet.
    - peak_follow_through: first frame after release within 0.02 arm lengths of the wrist's
      highest shoulder-relative point in [release, min(motion_end, release + 2 s)].
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
    wrist_peak = int(start + np.nanargmax(velocity[start : end + 1, 0]))
    if wrist_peak <= start:
        later = np.flatnonzero(valid & (np.arange(len(valid)) > start) & (np.arange(len(valid)) <= end))
        if later.size: wrist_peak = int(later[0])
    # Release follows the peak forward wrist speed by RELEASE_AFTER_PEAK_WRIST_SPEED_S (pilot
    # calibration above); kept inside the motion and on a frame with a valid wrist.
    wrist_release = min(end, wrist_peak + int(round(RELEASE_AFTER_PEAK_WRIST_SPEED_S * fps)))
    while wrist_release > wrist_peak and not valid[wrist_release]:
        wrist_release -= 1
    use_bag = (
        release_candidate is not None
        and release_candidate.automatic_frame is not None
        and start < release_candidate.automatic_frame < end
        and valid[release_candidate.automatic_frame]
    )
    provisional_release = int(release_candidate.automatic_frame) if use_bag else wrist_release
    backswing = int(start + np.nanargmin(x[start : provisional_release + 1]))
    # Motion start: the throwing swing, not the first sustained wrist motion in the clip
    # (walking in, aiming and practice swings made that fire at frame 1–37 on 5 of 6 audited throws).
    onset = _swing_onset(speed, velocity[:, 0], valid, backswing, threshold, fps)
    if onset is not None:
        start = onset
    height = np.where(valid, wrist[:, 1], np.nan)
    follow = _peak_follow_through(height, provisional_release, end, fps)
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
            automatic_confidence=None if frames[name] is None else confidence,
            automatic_method=EVENT_METHOD,
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
