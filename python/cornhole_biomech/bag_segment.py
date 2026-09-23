"""Per-frame bag silhouette: local background model → mask → centroid, area, orientation.

Why: the flight detector finds the bag from three-frame differencing. The
difference blob is where the bag CONTRASTS most with the background, not the
bag itself, so its centroid is pulled toward one edge (on the pilot clips, the
top edge of a red bag against a white wall: up to half a bag, ~10–15 px).

Method, for each flight frame t with a predicted position p:
1. Background patch: the pixel-wise median of neighbouring frames
   (t ± 4…8, `BACKGROUND_OFFSETS`) warped into frame t with the camera
   similarity transforms. The bag moves ≥ ~1 bag length in 4 frames in
   flight, so it is absent from most of them and the median removes it.
2. Mask: colour distance |I_t − B| (Lab, Euclidean) above a threshold set
   from the patch's own noise (median + 6·MAD, at least 18), cleaned with a
   morphological open/close.
3. The connected component that contains or lies nearest p, with a plausible
   area, is the bag. Its image moments give the centroid (m10/m00, m01/m00),
   visible area (px²) and principal-axis orientation (° from image x).

The detection centroid is replaced only when a mask is found within
`MAX_SHIFT_BAG_LENGTHS` of it; otherwise the detection is kept and marked.
Frames where the detector found nothing are re-tried at the position
interpolated from neighbouring detections (re-acquisition); success is labelled
`reacquired_mask`, never silently mixed with detections.

Limits: needs the bag to differ in colour from the background it passes
(a red bag over a red board fails); motion blur widens the mask along the
motion direction, which moves the centroid little but inflates area.
"""
from __future__ import annotations

import math
from typing import Any, Sequence

import cv2
import numpy as np

SEGMENT_REVISION = "local_median_background_mask_v1"
BACKGROUND_OFFSETS = (-8, -6, -4, 4, 6, 8)
HALF_WINDOW_PX = 48
MIN_AREA_PX = 12
MAX_AREA_PX = 4000
MAX_SHIFT_BAG_LENGTHS = 0.75


def _warp_to(frame: np.ndarray, src_to_dst: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
    """Warp the region of `frame` that lands on box (x0, y0, x1, y1) of the destination frame."""
    x0, y0, x1, y1 = box
    shift = np.array([[1, 0, -x0], [0, 1, -y0], [0, 0, 1]], float)
    M = (shift @ src_to_dst)[:2]
    return cv2.warpAffine(frame, M, (x1 - x0, y1 - y0), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def _local_align(target: np.ndarray, moving: np.ndarray, max_shift: float = 12.0) -> np.ndarray:
    """Translate `moving` onto `target` (same-size BGR patches) by phase correlation."""
    a = cv2.cvtColor(target, cv2.COLOR_BGR2GRAY).astype(np.float32)
    b = cv2.cvtColor(moving, cv2.COLOR_BGR2GRAY).astype(np.float32)
    window = cv2.createHanningWindow(a.shape[::-1], cv2.CV_32F)
    (dx, dy), response = cv2.phaseCorrelate(b, a, window)
    if response < 0.05 or math.hypot(dx, dy) > max_shift:
        return moving
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(moving, M, (moving.shape[1], moving.shape[0]), borderMode=cv2.BORDER_REPLICATE)


def _pair_transform(chains: dict[int, np.ndarray], src: int, dst: int) -> np.ndarray:
    """3×3 mapping frame src pixels → frame dst pixels via a common reference."""
    return np.linalg.inv(chains[dst]) @ chains[src]


def segment_bag(frames: Sequence[np.ndarray], chains: dict[int, np.ndarray], frame: int,
                predicted: tuple[float, float], expected_area: float | None = None,
                background_frames: Sequence[int] | None = None,
                area_bounds: tuple[float, float] | None = None) -> dict[str, Any] | None:
    """Bag mask near `predicted` in `frame`. Returns centroid/area/orientation or None.

    `background_frames` overrides the neighbouring frames used for the background
    median (needed once the bag has stopped: its neighbours then contain it too).
    """
    h, w = frames[frame].shape[:2]
    px, py = predicted
    if not (math.isfinite(px) and math.isfinite(py)):
        return None
    x0, y0 = max(0, int(px) - HALF_WINDOW_PX), max(0, int(py) - HALF_WINDOW_PX)
    x1, y1 = min(w, int(px) + HALF_WINDOW_PX), min(h, int(py) + HALF_WINDOW_PX)
    if x1 - x0 < 16 or y1 - y0 < 16:
        return None
    candidates = background_frames if background_frames is not None else [frame + o for o in BACKGROUND_OFFSETS]
    neighbours = [n for n in candidates if 0 <= n < len(frames) and n in chains and n != frame]
    if len(neighbours) < 3 or frame not in chains:
        return None
    patch = cv2.cvtColor(frames[frame][y0:y1, x0:x1], cv2.COLOR_BGR2LAB).astype(np.float32)
    warped = [_warp_to(frames[n], _pair_transform(chains, n, frame), (x0, y0, x1, y1)) for n in neighbours]
    if background_frames is not None:
        # Distant background frames: chained camera transforms drift by a few pixels,
        # which lights up every edge. Re-align each patch by phase correlation.
        warped = [_local_align(frames[frame][y0:y1, x0:x1], w) for w in warped]
    stack = [cv2.cvtColor(w, cv2.COLOR_BGR2LAB).astype(np.float32) for w in warped]
    background = np.median(np.stack(stack), axis=0)
    distance = np.linalg.norm(patch - background, axis=2)
    med = float(np.median(distance))
    mad = float(np.median(np.abs(distance - med)))
    mask = (distance > max(18.0, med + 6 * 1.4826 * mad)).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
    if count <= 1:
        return None
    lo, hi = MIN_AREA_PX, MAX_AREA_PX
    if expected_area:
        lo, hi = max(lo, 0.25 * expected_area), min(hi, 4.0 * expected_area)
    if area_bounds:
        lo, hi = max(MIN_AREA_PX, area_bounds[0]), min(MAX_AREA_PX, area_bounds[1])
    local = (px - x0, py - y0)
    best, best_d = None, None
    for i in range(1, count):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if not lo <= area <= hi:
            continue
        inside = 0 <= int(local[1]) < labels.shape[0] and 0 <= int(local[0]) < labels.shape[1] \
            and labels[int(local[1]), int(local[0])] == i
        d = 0.0 if inside else math.hypot(centroids[i][0] - local[0], centroids[i][1] - local[1])
        if best_d is None or d < best_d:
            best, best_d = i, d
    if best is None:
        return None
    component = (labels == best).astype(np.uint8)
    m = cv2.moments(component, binaryImage=True)
    cx, cy = m["m10"] / m["m00"], m["m01"] / m["m00"]
    mu20, mu02, mu11 = m["mu20"] / m["m00"], m["mu02"] / m["m00"], m["mu11"] / m["m00"]
    orientation = 0.5 * math.degrees(math.atan2(2 * mu11, mu20 - mu02))
    spread = math.sqrt(max(mu20 + mu02, 0.0))
    touches_edge = bool(stats[best, cv2.CC_STAT_LEFT] == 0 or stats[best, cv2.CC_STAT_TOP] == 0
                        or stats[best, cv2.CC_STAT_LEFT] + stats[best, cv2.CC_STAT_WIDTH] >= component.shape[1]
                        or stats[best, cv2.CC_STAT_TOP] + stats[best, cv2.CC_STAT_HEIGHT] >= component.shape[0])
    return {"x": float(x0 + cx), "y": float(y0 + cy), "area_px": float(m["m00"]),
            "orientation_deg": float(orientation), "radius_px": 2.0 * spread,
            "distance_from_prediction_px": float(best_d), "touches_window_edge": touches_edge}


def refine_flight(frames: Sequence[np.ndarray], chains: dict[int, np.ndarray],
                  detections: list[dict[str, Any]], max_fill_gap: int = 4) -> list[dict[str, Any]]:
    """Mask-refined centroids for detected frames, plus re-acquisition in short gaps.

    `detections` are raw-pixel points [{"frame","x","y"}] of one flight, sorted.
    Each output row keeps the detector centroid (`detection_x/y`) next to the
    refined one and a `source`: `mask`, `detection` (mask not found or rejected)
    or `reacquired_mask` (no detection; found by segmentation).
    """
    by_frame = {int(p["frame"]): p for p in detections}
    ordered = sorted(by_frame)
    if len(ordered) < 3:
        return [dict(p, source="detection", detection_x=p["x"], detection_y=p["y"]) for p in detections]
    first_pass = {}
    for f in ordered:
        seg = segment_bag(frames, chains, f, (by_frame[f]["x"], by_frame[f]["y"]))
        first_pass[f] = seg
    areas = [s["area_px"] for s in first_pass.values() if s and not s["touches_window_edge"]]
    typical_area = float(np.median(areas)) if areas else None
    bag_length = 2.0 * math.sqrt(typical_area / math.pi) if typical_area else 20.0
    out: list[dict[str, Any]] = []
    for f in range(ordered[0], ordered[-1] + 1):
        if f in by_frame:
            det = by_frame[f]
            seg = first_pass[f]
            if seg and typical_area and not 0.25 * typical_area <= seg["area_px"] <= 4 * typical_area:
                seg = segment_bag(frames, chains, f, (det["x"], det["y"]), typical_area)
            row = {"frame": f, "detection_x": det["x"], "detection_y": det["y"]}
            if seg and not seg["touches_window_edge"] and math.hypot(seg["x"] - det["x"], seg["y"] - det["y"]) \
                    <= MAX_SHIFT_BAG_LENGTHS * bag_length:
                row.update(x=seg["x"], y=seg["y"], area_px=seg["area_px"], orientation_deg=seg["orientation_deg"],
                           source="mask")
            else:
                row.update(x=det["x"], y=det["y"], area_px=None, orientation_deg=None, source="detection")
            out.append(row)
            continue
        before = [g for g in ordered if g < f][-3:]
        after = [g for g in ordered if g > f][:3]
        if not before or not after or after[0] - before[-1] - 1 > max_fill_gap:
            continue
        support = before + after
        t = np.array(support, float) - f
        degree = 2 if len(support) >= 4 else 1
        guess = (float(np.polyval(np.polyfit(t, [by_frame[g]["x"] for g in support], degree), 0.0)),
                 float(np.polyval(np.polyfit(t, [by_frame[g]["y"] for g in support], degree), 0.0)))
        seg = segment_bag(frames, chains, f, guess, typical_area)
        if seg and not seg["touches_window_edge"] and seg["distance_from_prediction_px"] <= 0.5 * bag_length:
            out.append({"frame": f, "x": seg["x"], "y": seg["y"], "area_px": seg["area_px"],
                        "orientation_deg": seg["orientation_deg"], "source": "reacquired_mask",
                        "detection_x": None, "detection_y": None})
    return out


def track_after_contact(frames: Sequence[np.ndarray], chains: dict[int, np.ndarray], contact: int,
                        start: tuple[float, float], release: int, fps: float, typical_area: float | None,
                        start_velocity: tuple[float, float] = (0.0, 0.0), max_missed: int = 8,
                        flight: dict[int, tuple[float, float]] | None = None) -> dict[str, Any]:
    """Follow the bag from first contact until it stops (slide) and report where it rests.

    Background: the latest flight frames in which the bag was still in the air more
    than ~2 search windows from the landing point (`flight` = raw positions by
    frame). They are only a few frames old, so camera drift is small; each is
    camera-aligned and then locally re-aligned. Without flight positions, frames
    just before release are used.
    Motion model: the last flight velocity, damped each frame (friction stops a
    sliding bag); the blob must keep a size consistent with its recent frames, so
    the tracker cannot jump to a board edge. Rest is judged in camera-steadied
    (release-frame) pixels, because a hand-held camera makes a resting bag move in
    raw pixels: rest = the first 0.2 s window whose points stay within
    max(3 px, 0.15 bag lengths) of their median. Rest position is reported in raw
    pixels of the rest frame and in release-frame pixels.

    A bag that disappears (hole, off the board, out of view) or is still moving at
    the end of the clip is reported as such; the bag is never assumed to be in the hole.
    """
    far = [f for f in sorted(flight or {}, reverse=True)
           if f < contact and math.hypot(flight[f][0] - start[0], flight[f][1] - start[1]) > 2 * HALF_WINDOW_PX]
    step = max(1, int(round(0.08 * fps)))
    background = far[:6] if len(far) >= 3 else [release - k * step for k in range(2, 8) if release - k * step >= 0]
    bag_length = 2.0 * math.sqrt(typical_area / math.pi) if typical_area else 20.0
    path: list[dict[str, Any]] = []
    position, velocity, missed = start, start_velocity, 0
    areas: list[float] = []
    for f in range(contact + 1, len(frames)):
        velocity = (0.7 * velocity[0], 0.7 * velocity[1])   # friction: damp before predicting
        guess = (position[0] + velocity[0] * (missed + 1), position[1] + velocity[1] * (missed + 1))
        recent = float(np.median(areas[-5:])) if len(areas) >= 3 else None
        bounds = (0.4 * recent, 2.5 * recent) if recent else \
            ((0.15 * typical_area, 3.0 * typical_area) if typical_area else None)
        seg = segment_bag(frames, chains, f, guess, None, background, bounds) if len(background) >= 3 else None
        if seg and not seg["touches_window_edge"] and seg["distance_from_prediction_px"] <= 1.2 * bag_length:
            new = (seg["x"], seg["y"])
            gap = missed + 1
            velocity = ((new[0] - position[0]) / gap, (new[1] - position[1]) / gap)
            position, missed = new, 0
            areas.append(seg["area_px"])
            steady = chains[f] @ np.array([new[0], new[1], 1.0])
            path.append({"frame": f, "x": new[0], "y": new[1], "area_px": seg["area_px"],
                         "x_release_frame": float(steady[0]), "y_release_frame": float(steady[1])})
        else:
            missed += 1
            if missed > max_missed:
                break
    result: dict[str, Any] = {"status": "lost_after_contact", "path": path, "rest": None,
                              "background_frames": background,
                              "note": "The bag could not be followed after first contact (hole, off the board, "
                                      "out of view or too little contrast). Final rest must come from the video."}
    run = max(3, int(round(0.2 * fps)))
    tolerance = max(3.0, 0.15 * bag_length)
    for i in range(len(path) - run + 1):
        window = path[i:i + run]
        if window[-1]["frame"] - window[0]["frame"] > 1.5 * run:
            continue
        mx = float(np.median([p["x_release_frame"] for p in window]))
        my = float(np.median([p["y_release_frame"] for p in window]))
        if max(math.hypot(p["x_release_frame"] - mx, p["y_release_frame"] - my) for p in window) <= tolerance:
            stationary = [p for p in path[i:]
                          if math.hypot(p["x_release_frame"] - mx, p["y_release_frame"] - my) <= 2 * tolerance]
            first = stationary[0]
            result.update(status="rest_found", rest={
                "frame": first["frame"], "x": first["x"], "y": first["y"],
                "x_release_frame": float(np.median([p["x_release_frame"] for p in stationary])),
                "y_release_frame": float(np.median([p["y_release_frame"] for p in stationary])),
                "stationary_frames": len(stationary)},
                note="Bag followed from first contact until it stopped; rest = median of the stationary frames "
                     "in camera-steadied pixels.")
            # Keep the slide only up to the stop; later samples are the same resting bag.
            result["path"] = [p for p in path if p["frame"] <= first["frame"] + run]
            break
    else:
        if path and path[-1]["frame"] >= len(frames) - 3:
            result.update(status="moving_at_clip_end", note="The bag was still moving when the clip ended.")
    return result
