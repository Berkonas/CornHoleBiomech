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


def projectile_frames(n=50):
    """A red bag on a projectile path (image gravity 0.24 px/frame^2) over a white/grey wall."""
    rng = np.random.default_rng(1)
    base = np.zeros((H, W, 3), np.uint8)
    base[: H // 2] = (235, 235, 235)
    base[H // 2:] = (120, 120, 120)
    base = cv2.add(base, rng.integers(0, 6, base.shape, dtype=np.uint8))
    frames, centres = [], []
    for k in range(n):
        cx, cy = 40.0 + 11.0 * k, 180.0 - 6.0 * k + 0.12 * k * k
        frame = base.copy()
        cv2.ellipse(frame, (int(round(cx)), int(round(cy))), (12, 8), 20, 0, 360, (60, 60, 200), -1)
        frames.append(frame)
        centres.append((cx, cy))
    return frames, centres, {k: np.eye(3) for k in range(n)}


def test_backfill_reaches_the_hand_past_a_long_detector_gap():
    """Detections start 25 frames after release (pilot: 10-22 frames missed against the slat wall); the first
    one has no mask (detector edge bias). The gravity-constrained walk fills every frame back to the hand."""
    from cornhole_biomech.bag_segment import BACKFILL_MAX_SECONDS, backfill_to_hand
    frames, centres, chains = projectile_frames()
    rows = refine_flight(frames, chains, [{"frame": k, "x": centres[k][0], "y": centres[k][1] - 6.0}
                                          for k in range(30, 50)])
    rows[0].update(source="detection", x=rows[0]["detection_x"], y=rows[0]["detection_y"] + 12.0, area_px=None)
    release = 5
    wrist = np.array([[centres[release][0] - 4.0 * (f - release), centres[release][1] + 3.0 * (f - release)]
                      for f in range(50)])
    found = backfill_to_hand(frames, chains, rows, wrist, in_hand_px=30.0,
                             max_frames=int(round(BACKFILL_MAX_SECONDS * 60)), gravity_px_per_frame2=0.24)
    frames_found = [r["frame"] for r in found]
    assert frames_found == list(range(frames_found[0], 31))     # contiguous up to the detections
    assert frames_found[0] <= release + 3                        # reached the hand (old 15-frame cap: 15)
    assert len(frames_found) > 15
    replaced = next(r for r in found if r["frame"] == 30)        # the mask-less detection was re-measured
    assert replaced["source"] == "backfilled_mask" and replaced["detection_y"] is not None
    assert all(np.hypot(r["x"] - centres[r["frame"]][0], r["y"] - centres[r["frame"]][1]) < 2.0 for r in found)
