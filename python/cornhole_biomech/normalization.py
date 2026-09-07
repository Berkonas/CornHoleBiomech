"""Anthropometric and movement-time normalization."""

from __future__ import annotations

import numpy as np


def resample_curve(
    values: np.ndarray,
    start_frame: int,
    end_frame: int,
    samples: int = 101,
) -> tuple[np.ndarray, np.ndarray]:
    """Resample a selected movement to equally spaced 0-100% cycle samples.

    Interpolation occurs only inside the first-to-last finite support of each
    signal; leading/trailing unsupported samples remain NaN.
    """
    source = np.asarray(values, float)
    if not 0 <= start_frame < end_frame < source.shape[0]:
        raise ValueError("start_frame and end_frame must define a valid non-empty interval")
    if samples < 3:
        raise ValueError("samples must be at least 3")
    selected = source[start_frame : end_frame + 1]
    source_tau = np.linspace(0.0, 1.0, len(selected))
    target_tau = np.linspace(0.0, 1.0, samples)
    flat = selected.reshape(len(selected), -1)
    output = np.full((samples, flat.shape[1]), np.nan)
    for column in range(flat.shape[1]):
        valid = np.isfinite(flat[:, column])
        if np.count_nonzero(valid) < 2:
            continue
        lo, hi = source_tau[valid][0], source_tau[valid][-1]
        supported = (target_tau >= lo) & (target_tau <= hi)
        output[supported, column] = np.interp(
            target_tau[supported], source_tau[valid], flat[valid, column]
        )
    return target_tau, output.reshape((samples,) + selected.shape[1:])


def normalized_event_timing(frame: int | None, start_frame: int, end_frame: int) -> float | None:
    """Map an integer event frame to a movement-cycle fraction without sub-frame claims."""
    if frame is None or end_frame <= start_frame:
        return None
    return float((frame - start_frame) / (end_frame - start_frame))

