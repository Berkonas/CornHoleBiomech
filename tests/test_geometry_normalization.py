import numpy as np
import pytest

from cornhole_biomech.geometry import throw_centered_points, vector_angle_degrees
from cornhole_biomech.normalization import resample_curve


@pytest.mark.parametrize("expected", [0, 45, 90, 135, 180])
def test_known_planar_angles(expected):
    radians = np.radians(expected)
    a = np.array([np.cos(radians), np.sin(radians)])
    b = np.array([0.0, 0.0])
    c = np.array([1.0, 0.0])
    assert vector_angle_degrees(a, b, c) == pytest.approx(expected)


def test_degenerate_angle_is_missing():
    value = vector_angle_degrees(np.array([0.0, 0.0]), np.zeros(2), np.ones(2))
    assert np.isnan(value)


def test_throw_centering_is_scale_and_translation_invariant():
    origin = np.array([[100.0, 200.0], [110.0, 195.0]])
    wrist = origin + np.array([[30.0, -10.0], [50.0, -20.0]])
    base = throw_centered_points(wrist, origin, 100.0, "left_to_right")
    for scale in (0.5, 2.0):
        translated_origin = origin * scale + np.array([320.0, -75.0])
        translated_wrist = wrist * scale + np.array([320.0, -75.0])
        result = throw_centered_points(
            translated_wrist, translated_origin, 100.0 * scale, "left_to_right"
        )
        np.testing.assert_allclose(result, base)


def test_target_direction_reflection_is_removed():
    origin = np.array([[100.0, 200.0]])
    wrist = np.array([[150.0, 180.0]])
    mirrored_origin = np.array([[400.0, 200.0]])
    mirrored_wrist = np.array([[350.0, 180.0]])
    left_to_right = throw_centered_points(wrist, origin, 100.0, "left_to_right")
    right_to_left = throw_centered_points(
        mirrored_wrist, mirrored_origin, 100.0, "right_to_left"
    )
    np.testing.assert_allclose(left_to_right, right_to_left)


def test_time_resampling_matches_same_analytic_motion():
    outputs = []
    for frames in (31, 121):
        source_t = np.linspace(0, 1, frames)
        source = np.sin(np.pi * source_t)
        tau, result = resample_curve(source, 0, frames - 1, 101)
        outputs.append(result)
    np.testing.assert_allclose(outputs[0], outputs[1], atol=0.002)
    assert tau[0] == 0 and tau[-1] == 1

