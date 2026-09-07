"""Filtering and derivatives for biomechanical trajectories."""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfiltfilt


def _finite_runs(mask: np.ndarray) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for i, valid in enumerate(mask):
        if valid and start is None:
            start = i
        elif not valid and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(mask)))
    return runs


def lowpass_zero_phase(
    values: np.ndarray,
    fps: float,
    cutoff_hz: float = 6.0,
    order: int = 4,
) -> tuple[np.ndarray, float, list[str]]:
    """Filter finite runs with a zero-phase Butterworth SOS filter.

    `cutoff_hz` is capped at 45% of sampling frequency to stay below Nyquist.
    Short runs remain unfiltered and produce a warning. Forward/backward
    application avoids phase lag but introduces edge sensitivity.
    """
    if fps <= 0:
        raise ValueError("fps must be positive")
    effective_cutoff = min(float(cutoff_hz), 0.45 * float(fps))
    if effective_cutoff <= 0:
        raise ValueError("cutoff_hz must be positive")
    sos = butter(order, effective_cutoff, btype="lowpass", fs=fps, output="sos")
    result = np.array(values, dtype=float, copy=True)
    warnings: list[str] = []
    flat = result.reshape(result.shape[0], -1)
    for column in range(flat.shape[1]):
        series = flat[:, column]
        for start, end in _finite_runs(np.isfinite(series)):
            segment = series[start:end]
            try:
                if len(segment) < max(9, 3 * (2 * len(sos) + 1)):
                    raise ValueError("finite run is too short")
                series[start:end] = sosfiltfilt(sos, segment)
            except ValueError:
                warnings.append(
                    f"Series {column}, frames {start}-{end - 1}: too short for zero-phase filtering; left unfiltered."
                )
    return result, effective_cutoff, sorted(set(warnings))


def derivative(values: np.ndarray, fps: float) -> np.ndarray:
    """Differentiate only contiguous finite runs using time-aware gradients."""
    result = np.full_like(np.asarray(values, float), np.nan)
    source = np.asarray(values, float)
    flat_source = source.reshape(source.shape[0], -1)
    flat_result = result.reshape(result.shape[0], -1)
    for column in range(flat_source.shape[1]):
        for start, end in _finite_runs(np.isfinite(flat_source[:, column])):
            if end - start >= 3:
                flat_result[start:end, column] = np.gradient(
                    flat_source[start:end, column], 1.0 / fps, edge_order=2
                )
    return result

