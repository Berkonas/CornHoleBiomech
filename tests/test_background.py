import numpy as np

from cornhole_biomech.background import build_plate


def test_plate_removes_moving_object_and_undoes_camera_shift():
    h, w = 120, 160
    scene = np.zeros((h, w, 3), np.uint8)
    scene[40:80, 60:100] = (0, 0, 200)            # static red "board"
    frames, chain = [], {}
    for f in range(30):
        dx = f % 5                                  # hand-held drift, known transform
        img = np.roll(scene, dx, axis=1).copy()
        img[10:20, 5 * f % w:5 * f % w + 6] = 255   # moving white "bag"
        frames.append(img)
        chain[f] = np.array([[1, 0, -dx], [0, 1, 0], [0, 0, 1]], float)   # frame → reference
    out = build_plate(frames, chain, scale=1.0)
    plate = out["plate"]
    assert plate.shape == scene.shape
    assert np.abs(plate[45:75, 65:95].astype(int) - scene[45:75, 65:95]).max() <= 2
    assert plate[10:20, 20:140].max() < 60        # moving object gone


def test_person_mask_pixels_are_excluded():
    h, w = 60, 80
    frames = [np.full((h, w, 3), 100, np.uint8) for _ in range(10)]
    masks = {}
    for f in range(0, 10):
        frames[f][20:40, 20:40] = 250               # a person standing still in every frame
        m = np.zeros((h, w), np.uint8); m[20:40, 20:40] = 255
        masks[f] = m
    chain = {f: np.eye(3) for f in range(10)}
    out = build_plate(frames, chain, person_masks=masks, scale=1.0)
    assert out["coverage"][30, 30] == 0.0           # never visible → no plate evidence
    assert out["coverage"][5, 5] == 1.0
