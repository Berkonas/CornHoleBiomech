"""Numerically stable planar geometry for projected 2D biomechanics."""

from __future__ import annotations

import numpy as np


def vector_angle_degrees(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    """Return unsigned planar angle ABC in [0, 180] degrees.

    Uses atan2(abs(cross(u, v)), dot(u, v)) with u=A-B and v=C-B.
    Degenerate or non-finite vectors produce NaN. This is a projected 2D angle,
    not a three-dimensional anatomical joint rotation.
    """
    a, b, c = np.asarray(a, float), np.asarray(b, float), np.asarray(c, float)
    u, v = a - b, c - b
    cross = u[..., 0] * v[..., 1] - u[..., 1] * v[..., 0]
    dot = np.sum(u * v, axis=-1)
    lengths = np.linalg.norm(u, axis=-1) * np.linalg.norm(v, axis=-1)
    result = np.degrees(np.arctan2(np.abs(cross), dot))
    return np.where(np.isfinite(lengths) & (lengths > 1e-12), result, np.nan)


def unsigned_vector_angle_degrees(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Return the unsigned angle between vectors, with NaN for degenerate input."""
    zeros = np.zeros_like(np.asarray(u, float))
    return vector_angle_degrees(np.asarray(u, float), zeros, np.asarray(v, float))


def signed_orientation_degrees(vector: np.ndarray) -> np.ndarray:
    """Return atan2 orientation in degrees in mathematical x-right/y-up axes."""
    vector = np.asarray(vector, float)
    valid = np.isfinite(vector).all(axis=-1) & (np.linalg.norm(vector, axis=-1) > 1e-12)
    angle = np.degrees(np.arctan2(vector[..., 1], vector[..., 0]))
    return np.where(valid, angle, np.nan)


def robust_segment_length(a: np.ndarray, b: np.ndarray) -> float:
    """Median finite Euclidean segment length across frames."""
    lengths = np.linalg.norm(np.asarray(a, float) - np.asarray(b, float), axis=-1)
    finite = lengths[np.isfinite(lengths) & (lengths > 1e-9)]
    return float(np.median(finite)) if finite.size else float("nan")


def throw_centered_points(
    points: np.ndarray,
    origin: np.ndarray,
    arm_length: float,
    target_direction: str,
) -> np.ndarray:
    """Translate, reflect into target-forward x, flip image y upward, and scale.

    Output is dimensionless in arm lengths. This removes 2D translation and
    uniform image scale but cannot remove perspective or out-of-plane error.
    """
    if not np.isfinite(arm_length) or arm_length <= 0:
        return np.full_like(np.asarray(points, float), np.nan)
    relative = np.asarray(points, float) - np.asarray(origin, float)
    x_sign = 1.0 if target_direction == "left_to_right" else -1.0
    return np.stack((x_sign * relative[..., 0], -relative[..., 1]), axis=-1) / arm_length

