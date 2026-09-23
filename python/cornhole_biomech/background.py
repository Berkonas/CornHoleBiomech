"""Clean background plate in reference-frame pixels (hand-held camera motion removed).

Median over up to `max_samples` evenly spaced frames, each warped into the
reference frame; person-mask pixels are treated as missing. Computed at `scale`
per channel to bound memory, then resized to full resolution.
"""
from __future__ import annotations

import warnings
from typing import Any, Sequence

import cv2
import numpy as np


def build_plate(frames: Sequence[np.ndarray], chain: dict[int, np.ndarray],
                person_masks: dict[int, np.ndarray] | None = None, max_samples: int = 60,
                scale: float = 0.5) -> dict[str, Any]:
    h, w = frames[0].shape[:2]
    sh, sw = max(1, int(round(h * scale))), max(1, int(round(w * scale)))
    S = np.diag([scale, scale, 1.0])
    usable = [f for f in range(len(frames)) if f in chain]
    picks = usable if len(usable) <= max_samples else [usable[i] for i in np.linspace(0, len(usable) - 1, max_samples).astype(int)]
    stack = np.full((len(picks), sh, sw, 3), np.nan, np.float32)
    for i, f in enumerate(picks):
        M = (S @ chain[f] @ np.linalg.inv(S))[:2]
        small = cv2.resize(frames[f], (sw, sh), interpolation=cv2.INTER_AREA) if scale != 1 else frames[f]
        warped = cv2.warpAffine(small, M, (sw, sh), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0))
        valid = cv2.warpAffine(np.full((sh, sw), 255, np.uint8), M, (sw, sh), flags=cv2.INTER_NEAREST) > 0
        if person_masks is not None:
            mask = _nearest_mask(person_masks, f)
            if mask is not None:
                mask = cv2.resize(mask, (sw, sh), interpolation=cv2.INTER_NEAREST)
                valid &= cv2.warpAffine(mask, M, (sw, sh), flags=cv2.INTER_NEAREST) == 0
        layer = warped.astype(np.float32)
        layer[~valid] = np.nan
        stack[i] = layer
    coverage = np.mean(np.isfinite(stack[..., 0]), axis=0).astype(np.float32)
    plate = np.zeros((sh, sw, 3), np.uint8)
    for c in range(3):
        with np.errstate(all="ignore"), warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="All-NaN slice encountered", category=RuntimeWarning)
            med = np.nanmedian(stack[..., c], axis=0)
        plate[..., c] = np.nan_to_num(med, nan=0.0).clip(0, 255).astype(np.uint8)
    if scale != 1:
        plate = cv2.resize(plate, (w, h), interpolation=cv2.INTER_LINEAR)
        coverage = cv2.resize(coverage, (w, h), interpolation=cv2.INTER_NEAREST)
    return {"plate": plate, "coverage": coverage, "samples": len(picks)}


def _nearest_mask(masks: dict[int, np.ndarray], frame: int) -> np.ndarray | None:
    if frame in masks:
        return masks[frame]
    if not masks:
        return None
    nearest = min(masks, key=lambda k: abs(k - frame))
    return masks[nearest] if abs(nearest - frame) <= 2 else None
