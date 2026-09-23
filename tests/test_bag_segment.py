"""Bag silhouette refinement: unbiased centroid where the bag crosses a background edge."""
import cv2
import numpy as np

from cornhole_biomech.bag_segment import refine_flight, segment_bag

N, H, W = 40, 240, 640


def synthetic(camera_shift=(0.0, 0.0)):
    """White wall over grey wall; a red ellipse bag moving right, crossing the boundary."""
    rng = np.random.default_rng(0)
    base = np.zeros((H + 40, W + 40, 3), np.uint8)
    base[: (H + 40) // 2] = (235, 235, 235)
    base[(H + 40) // 2 :] = (120, 120, 120)
    base = cv2.add(base, rng.integers(0, 6, base.shape, dtype=np.uint8))
    frames, centres, chains = [], [], {}
    for k in range(N):
        dx, dy = camera_shift[0] * k, camera_shift[1] * k
        frame = base[20 + int(dy):20 + int(dy) + H, 20 + int(dx):20 + int(dx) + W].copy()
        cx, cy = 60 + 13.0 * k - dx, 118 + 0.0 * k - dy   # bag centre in this frame's pixels
        cv2.ellipse(frame, (int(round(cx)), int(round(cy))), (14, 9), 30, 0, 360, (60, 60, 200), -1)
        frames.append(frame)
        centres.append((round(cx), round(cy)))
        # frame k pixels → reference (frame 0) pixels
        chains[k] = np.array([[1, 0, int(dx)], [0, 1, int(dy)], [0, 0, 1]], float)
    return frames, centres, chains


def test_mask_centroid_is_at_bag_centre_across_background_edge():
    frames, centres, chains = synthetic()
    seg = segment_bag(frames, chains, 20, (centres[20][0], centres[20][1] - 7))  # detector-like edge bias
    assert seg is not None
    assert abs(seg["x"] - centres[20][0]) < 1.0 and abs(seg["y"] - centres[20][1]) < 1.0
    assert 300 < seg["area_px"] < 500          # π·14·9 ≈ 396
    assert abs(abs(seg["orientation_deg"]) - 30) < 5


def test_refine_handles_camera_motion_and_reacquires_gaps():
    frames, centres, chains = synthetic(camera_shift=(1.0, 0.5))
    detections = [{"frame": k, "x": centres[k][0] + 1.0, "y": centres[k][1] - 6.0}
                  for k in range(10, 30) if k not in (18, 19)]
    rows = {r["frame"]: r for r in refine_flight(frames, chains, detections)}
    assert rows[18]["source"] == "reacquired_mask" and rows[19]["source"] == "reacquired_mask"
    errors = [np.hypot(r["x"] - centres[f][0], r["y"] - centres[f][1]) for f, r in rows.items()]
    assert max(errors) < 1.5
    assert rows[12]["detection_y"] == centres[12][1] - 6.0   # detector value retained


def test_no_mask_keeps_detection():
    frames, centres, chains = synthetic()
    blank = [np.full_like(f, 128) for f in frames]
    rows = refine_flight(blank, chains, [{"frame": k, "x": 100.0, "y": 100.0} for k in range(10, 20)])
    assert all(r["source"] == "detection" and r["x"] == 100.0 for r in rows)
