"""Hand-held camera registration: the composed frame→reference chain must be sub-pixel.

The pilot clips drift slowly (well under 1 px per frame at half resolution). A
feature-only (ORB keypoint) similarity under-estimates such sub-pixel steps, and
the error accumulates over hundreds of frames when the steps are composed.
"""
import cv2
import numpy as np
import pytest

from cornhole_biomech.auto_bag import detect_moving_blobs_in_frames, reference_chain

N_FRAMES = 120
FRAME_W, FRAME_H = 960, 540
DRIFT = (0.35, -0.20)          # px per frame, camera position in scene pixels
ROTATION_DEG = 0.01            # per frame
BLOB_START, BLOB_STEP, BLOB_RADIUS = (80.0, 300.0), 7.0, 4


def _scene(seed=3):
    rng = np.random.default_rng(seed)
    scene = cv2.GaussianBlur(rng.uniform(0, 255, (900, 1400)).astype(np.float32), (0, 0), 2)
    scene = cv2.normalize(scene, None, 0, 255, cv2.NORM_MINMAX)
    for _ in range(40):
        x, y = int(rng.integers(0, 1350)), int(rng.integers(0, 850))
        w, h = int(rng.integers(15, 120)), int(rng.integers(15, 120))
        cv2.rectangle(scene, (x, y), (x + w, y + h), float(rng.uniform(0, 255)), -1)
    return cv2.cvtColor(scene.astype(np.uint8), cv2.COLOR_GRAY2BGR)


def _frame_to_scene(k):
    """3×3 map from frame-k pixels to scene pixels (the camera pose of frame k)."""
    a = np.deg2rad(ROTATION_DEG * k)
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 200 + DRIFT[0] * k], [s, c, 180 + DRIFT[1] * k], [0, 0, 1]])


def _blob(k):
    return BLOB_START[0] + BLOB_STEP * k, BLOB_START[1]


@pytest.fixture(scope="module")
def drifting_clip():
    scene = _scene()
    frames = []
    for k in range(N_FRAMES):
        frame = cv2.warpAffine(scene, _frame_to_scene(k)[:2], (FRAME_W, FRAME_H),
                               flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)
        x, y = _blob(k)
        cv2.circle(frame, (int(round(x)), int(round(y))), BLOB_RADIUS, (255, 255, 255), -1)
        frames.append(frame)
    return frames, detect_moving_blobs_in_frames(frames)


def test_composed_chain_is_subpixel_over_120_frames_of_slow_drift(drifting_clip):
    _, (_, to_prev) = drifting_clip
    chain = reference_chain(to_prev, 0)
    last = N_FRAMES - 1
    errors = []
    for p_last in ([480.0, 270.0], [150.0, 100.0], [800.0, 450.0]):
        scene_point = _frame_to_scene(last) @ np.array([*p_last, 1.0])
        truth = np.linalg.inv(_frame_to_scene(0)) @ scene_point
        mapped = chain[last] @ np.array([*p_last, 1.0])
        errors.append(float(np.hypot(*(mapped[:2] - truth[:2]))))
    # True accumulated motion here is ~48 px; ORB-only steps missed a large share of it.
    assert max(errors) < 1.0, errors


def test_registration_does_not_suppress_a_real_moving_blob(drifting_clip):
    _, (candidates, _) = drifting_clip
    hits = 0
    frames = range(2, N_FRAMES - 2)
    for k in frames:
        x, y = _blob(k)
        if any(c.frame == k and np.hypot(c.x - x, c.y - y) < 6 for c in candidates):
            hits += 1
    assert hits >= 0.9 * len(frames)


def _chain_error(frames, to_prev):
    chain = reference_chain(to_prev, 0)
    last = len(frames) - 1
    p_last = np.array([480.0, 270.0, 1.0])
    truth = np.linalg.inv(_frame_to_scene(0)) @ (_frame_to_scene(last) @ p_last)
    return float(np.hypot(*((chain[last] @ p_last)[:2] - truth[:2])))


def test_keyframe_switch_path_still_registers_each_step(drifting_clip, monkeypatch):
    import cornhole_biomech.auto_bag as auto_bag
    frames, _ = drifting_clip
    monkeypatch.setattr(auto_bag, "KEYFRAME_MIN_CC", 1.01)   # every frame starts a new keyframe
    _, to_prev = detect_moving_blobs_in_frames(frames[:40])
    assert _chain_error(frames[:40], to_prev) < 1.0


def test_ecc_failure_falls_back_to_the_orb_step(drifting_clip, monkeypatch):
    import cornhole_biomech.auto_bag as auto_bag
    frames, _ = drifting_clip
    monkeypatch.setattr(auto_bag, "_register_to_keyframes", lambda gray, steps, factor: steps)
    _, expected = detect_moving_blobs_in_frames(frames[:10])
    monkeypatch.undo()

    def fail(*args, **kwargs):
        raise cv2.error("no convergence")
    monkeypatch.setattr(auto_bag.cv2, "findTransformECC", fail)
    _, to_prev = detect_moving_blobs_in_frames(frames[:10])
    for got, want in zip(to_prev, expected):
        np.testing.assert_allclose(got, want, atol=1e-5)
