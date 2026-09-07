import numpy as np
import pytest

from cornhole_biomech.corrections import apply_corrections, interpolate_short_gaps
from cornhole_biomech.filtering import derivative, lowpass_zero_phase
from cornhole_biomech.models import CorrectionSet, PointCorrection
from cornhole_biomech.quality import quality_summary


def test_low_confidence_is_missing_but_manual_correction_is_effective():
    raw = np.array([[[1.0, 2.0]], [[3.0, 4.0]]])
    original = raw.copy()
    confidence = np.array([[0.1], [0.9]])
    corrections = CorrectionSet(corrections=[PointCorrection(0, "right_wrist", 8.0, 9.0)])
    effective, manual, low = apply_corrections(
        raw, confidence, ("right_wrist",), corrections, 0.35
    )
    np.testing.assert_array_equal(raw, original)
    np.testing.assert_allclose(effective[0, 0], [8.0, 9.0])
    assert manual[0, 0]
    assert low[0, 0]


def test_short_bounded_gap_interpolates_and_long_gap_does_not():
    values = np.array([[[0.0, 0.0]], [[np.nan, np.nan]], [[2.0, 4.0]],
                       [[np.nan, np.nan]], [[np.nan, np.nan]], [[np.nan, np.nan]], [[6.0, 12.0]]])
    result, mask = interpolate_short_gaps(values, max_gap=2)
    np.testing.assert_allclose(result[1, 0], [1.0, 2.0])
    assert mask[1, 0]
    assert np.isnan(result[3:6, 0]).all()


def test_zero_phase_filter_preserves_low_frequency_timing_and_reduces_noise():
    fps = 100.0
    t = np.arange(500) / fps
    low = np.sin(2 * np.pi * 1.2 * t)
    noisy = low + 0.25 * np.sin(2 * np.pi * 25 * t)
    filtered, cutoff, warnings = lowpass_zero_phase(noisy, fps, 6.0, 4)
    assert cutoff == 6.0
    assert not warnings
    assert np.sqrt(np.mean((filtered - low) ** 2)) < np.sqrt(np.mean((noisy - low) ** 2)) * 0.2
    assert np.argmax(filtered[:100]) == pytest.approx(np.argmax(low[:100]), abs=1)


def test_derivative_does_not_bridge_missing_gap():
    values = np.arange(10, dtype=float)
    values[4:6] = np.nan
    result = derivative(values, fps=10)
    assert np.isnan(result[4:6]).all()
    np.testing.assert_allclose(result[[1, 2, 7, 8]], 10.0)


def test_quality_warns_when_required_points_are_cropped_and_confidence_is_poor():
    landmarks = ("right_shoulder", "right_elbow", "right_wrist", "left_hip", "right_hip")
    raw = np.full((20, len(landmarks), 2), [50.0, 50.0])
    raw[:, 2, 0] = 1.0
    confidence = np.full((20, len(landmarks)), 0.2)
    effective = np.full_like(raw, np.nan)
    mask = np.zeros((20, len(landmarks)), bool)
    result = quality_summary(
        raw, confidence, effective, mask, mask, landmarks,
        fps=24, width=100, height=100, camera_view="other",
        confidence_threshold=0.35, throwing_side="right",
    )
    warnings = " ".join(result["warnings"])
    assert "confidence" in warnings
    assert "cropped" in warnings
    assert "below 30 fps" in warnings
    assert "not a Side view" in warnings
