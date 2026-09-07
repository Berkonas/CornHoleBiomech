"""Small-sample, within-athlete movement-versus-outcome summaries."""

from __future__ import annotations

from typing import Any
import numpy as np
from scipy.stats import spearmanr

INSUFFICIENT_MESSAGE = "Not enough trials to estimate this relationship reliably."


def _bootstrap_spearman_ci(
    x: np.ndarray, y: np.ndarray, resamples: int = 2000, seed: int = 20260906
) -> tuple[float | None, float | None]:
    rng = np.random.default_rng(seed)
    values: list[float] = []
    n = len(x)
    for _ in range(resamples):
        indices = rng.integers(0, n, n)
        if np.unique(x[indices]).size < 2 or np.unique(y[indices]).size < 2:
            continue
        rho = float(spearmanr(x[indices], y[indices]).statistic)
        if np.isfinite(rho):
            values.append(rho)
    if len(values) < max(100, resamples // 4):
        return None, None
    low, high = np.percentile(values, [2.5, 97.5])
    return float(low), float(high)


def relationship(
    feature: list[float | None] | np.ndarray,
    outcome: list[float | None] | np.ndarray,
    minimum_trials: int = 8,
) -> dict[str, Any]:
    """Report paired data and Spearman association without causal language."""
    x, y = np.asarray(feature, float), np.asarray(outcome, float)
    valid = np.isfinite(x) & np.isfinite(y)
    x, y = x[valid], y[valid]
    base: dict[str, Any] = {
        "n": int(len(x)),
        "feature_mean": float(np.mean(x)) if len(x) else None,
        "feature_sd": float(np.std(x, ddof=1)) if len(x) > 1 else None,
        "outcome_mean": float(np.mean(y)) if len(y) else None,
        "outcome_sd": float(np.std(y, ddof=1)) if len(y) > 1 else None,
        "claim_scope": "within_athlete_observational_association_not_causation",
    }
    if len(x) < minimum_trials or np.unique(x).size < 2 or np.unique(y).size < 2:
        return {**base, "status": "insufficient_data", "message": INSUFFICIENT_MESSAGE}
    result = spearmanr(x, y)
    ci_low, ci_high = _bootstrap_spearman_ci(x, y)
    return {
        **base,
        "status": "estimated",
        "spearman_rho": float(result.statistic),
        "spearman_p_value_exploratory": float(result.pvalue),
        "spearman_bootstrap_95_ci": [ci_low, ci_high],
        "message": (
            "This exploratory within-athlete association may guide hypotheses; it does not show that the movement feature causes the outcome."
        ),
    }


def grouped_summary(values: list[float | None], scores: list[int | None]) -> dict[str, Any]:
    """Describe a feature by 0/1/3 outcome without inferential overreach."""
    groups: dict[str, Any] = {}
    for category in (0, 1, 3):
        data = np.asarray(
            [v for v, score in zip(values, scores, strict=True) if score == category and v is not None],
            float,
        )
        data = data[np.isfinite(data)]
        groups[str(category)] = {
            "n": int(len(data)),
            "mean": float(np.mean(data)) if len(data) else None,
            "median": float(np.median(data)) if len(data) else None,
            "sd": float(np.std(data, ddof=1)) if len(data) > 1 else None,
        }
    return groups

