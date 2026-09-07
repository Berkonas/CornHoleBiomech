"""Non-destructive manual correction and confidence masking."""

from __future__ import annotations

import numpy as np

from .models import CorrectionSet, PoseSequence


def pose_arrays(sequence: PoseSequence, landmarks: tuple[str, ...]) -> tuple[np.ndarray, np.ndarray]:
    """Convert a transparent pose sequence to coordinate and confidence arrays."""
    coords = np.full((len(sequence.frames), len(landmarks), 2), np.nan, dtype=float)
    confidence = np.zeros((len(sequence.frames), len(landmarks)), dtype=float)
    for i, frame in enumerate(sequence.frames):
        for j, name in enumerate(landmarks):
            point = frame.landmarks.get(name)
            if point is None:
                continue
            confidence[i, j] = point.confidence
            if point.x is not None and point.y is not None:
                coords[i, j] = (point.x, point.y)
    return coords, confidence


def apply_corrections(
    raw: np.ndarray,
    confidence: np.ndarray,
    landmarks: tuple[str, ...],
    corrections: CorrectionSet,
    confidence_threshold: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return effective points, manual mask, and low-confidence mask.

    The input `raw` is copied and never modified. Manual values remain usable
    even when the corresponding model prediction has low confidence.
    """
    effective = np.array(raw, dtype=float, copy=True)
    manual_mask = np.zeros(confidence.shape, dtype=bool)
    low_confidence = (confidence < confidence_threshold) | ~np.isfinite(raw).all(axis=-1)
    effective[low_confidence] = np.nan
    lookup = {name: index for index, name in enumerate(landmarks)}
    for correction in corrections.corrections:
        if correction.landmark not in lookup:
            continue
        if not 0 <= correction.frame_index < effective.shape[0]:
            continue
        j = lookup[correction.landmark]
        effective[correction.frame_index, j] = (correction.x, correction.y)
        manual_mask[correction.frame_index, j] = correction.kind == "manual"
    return effective, manual_mask, low_confidence


def interpolate_short_gaps(coords: np.ndarray, max_gap: int) -> tuple[np.ndarray, np.ndarray]:
    """Linearly fill bounded gaps no longer than `max_gap`; report filled samples."""
    result = np.array(coords, dtype=float, copy=True)
    interpolated = np.zeros(result.shape[:-1], dtype=bool)
    if max_gap <= 0:
        return result, interpolated
    frames, landmarks, _ = result.shape
    for j in range(landmarks):
        valid = np.isfinite(result[:, j]).all(axis=-1)
        i = 0
        while i < frames:
            if valid[i]:
                i += 1
                continue
            start = i
            while i < frames and not valid[i]:
                i += 1
            end = i
            gap = end - start
            if start > 0 and end < frames and gap <= max_gap:
                alpha = np.arange(1, gap + 1, dtype=float) / (gap + 1)
                left, right = result[start - 1, j], result[end, j]
                result[start:end, j] = left + alpha[:, None] * (right - left)
                interpolated[start:end, j] = True
    return result, interpolated

