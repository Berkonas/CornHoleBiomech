"""Anthropometric and movement-time normalization."""

from __future__ import annotations

from .filtering import _finite_runs

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
        # Only adjacent supported samples may be interpolated. Long gaps that
        # survived confidence/gap handling must remain missing in comparisons.
        for first, last in _finite_runs(np.isfinite(flat[:, column])):
            if last - first < 2:
                continue
            supported = (target_tau >= source_tau[first]) & (target_tau <= source_tau[last - 1])
            output[supported, column] = np.interp(
                target_tau[supported], source_tau[first:last], flat[first:last, column]
            )
    return target_tau, output.reshape((samples,) + selected.shape[1:])


def normalized_event_timing(frame: int | None, start_frame: int, end_frame: int) -> float | None:
    """Map an integer event frame to a movement-cycle fraction without sub-frame claims."""
    if frame is None or end_frame <= start_frame:
        return None
    return float((frame - start_frame) / (end_frame - start_frame))

