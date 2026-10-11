"""Front camera: following the bag through the air (release → first contact) and across the deck.

The front camera looks back along the throw line, so the bag starts small near the thrower and grows as
it flies towards the lens. Two cues pick it out of a busy hall:

* **colour** — the bags are red/maroon (OpenCV hue ≤ 12 or ≥ 150, saturation ≥ 60; measured in flight, 727
  detections on 21 throws, 2nd–98th percentile: hue 165–180 and 0–8, saturation 63–145). Floor glare (low
  saturation), the wooden wall slats (hue 15–28) and people's clothing do not pass;
* **motion** — a bag pixel differs from the empty scene before release (median of the frames before the
  throw, shifted for the camera's slow drift, which the per-frame deck corners measure) *and* from the same
  frame two frames earlier and two frames later. Static red things (the deck, the board's legs, spare bags)
  fail this.

Among the moving red blobs, the bag is the one set that follows **one projectile seen through a pinhole
camera**. A drag-free bag moves linearly across (X), linearly towards the camera (Z) and parabolically up
and down (Y); seen through a fixed pinhole camera its image position is therefore a ratio of polynomials in
time with a *shared* denominator (the depth):

    u(t) = (a0 + a1·t + a2·t²) / D(t),   v(t) = (c0 + c1·t + c2·t²) / D(t),   D(t) = 1 + d1·t + d2·t²

(a2 and d2 are only non-zero when the camera is pitched; for a level camera the model has 6 numbers). The
model is fitted to the candidate blobs of all frames at once with RANSAC (three blobs from three different
frames give a level-camera model; the frame with most agreement wins), then refined on its inliers. The
bag must also approach the camera (D falls) and grow accordingly. One set of numbers for the whole flight
makes the choice global: a person, a reflection or a spare bag cannot fit a projectile that comes from the
release and ends on the deck. Frames whose nearest blob is not close to the fitted path are left out.

Methods and thresholds: docs/METHODS_AND_MATH.md §5.2 ("Bag path in the front camera").
"""
from __future__ import annotations

import math
from typing import Any, Sequence

import cv2
import numpy as np

# Colour: the bag-red gate shared with front_view (hue ≤ 12 or ≥ 150 on OpenCV's 0–180 scale, S ≥ 60).
BAG_HUE_LOW, BAG_HUE_HIGH = 12, 150
BAG_MIN_SAT = 60                  # bags in flight: S 63–145 (2nd–98th pct); deck paint S 25–60
BAG_MIN_VAL = 35                  # below this the hue is noise (shadow)
# Motion, on the 8-bit channel with the largest difference (half-resolution frames).
SEARCH_SCALE = 0.5
BACKGROUND_DIFF = 30              # bag vs empty scene: 50–173 in flight (2nd–98th pct); still scene: median 2–4
TEMPORAL_DIFF = 20                # bag vs the same pixel two frames before and after; still scene: 99th pct ≤ 8
TEMPORAL_GAP = 2                  # frames; a far bag moves 3–10 half-res px per frame, about its own size
MIN_BLOB_PX = 2                   # half-res pixels: the far bag is 3–6 px across at half resolution
MAX_CANDIDATES = 15               # per frame, largest first
# Trajectory model.
RANSAC_ITERATIONS = 1500
MIN_SAMPLE_GAP = 3                # frames between the three blobs of a RANSAC sample
INLIER_BASE_PX = 4.0              # half-res px: tolerance = base + share × blob size
INLIER_SIZE_SHARE = 0.75          # bag-to-model residuals: median 0.6 px, 98th pct 2.9 px (0.35 × tolerance)
MIN_GROWTH, MAX_GROWTH = 1.3, 8.0  # depth at the first / last searched frame: measured 2.2–3.3 (21 throws)
CONTACT_SYNC_FRAMES = 1           # the front camera sees the bag reach the deck 0–2 frames (median 1) after the
                                  # side camera's first contact (11 Final Data Collection throws): one more frame
MIN_INLIER_FRAMES = 6             # fewer frames on one projectile: no path
MIN_INLIER_SHARE = 0.3            # of the frames between release and contact
AREA_RATIO_MAX = 6.0              # blob area vs the size the fitted depth predicts (a tumbling bag changes its
                                  # area up to 2.5× between frames, Player 4 take 1: 1500 → 616 px²)
# Gravity: the t² term of the vertical model is f·g / (2·Z0), so it gives the bag's starting distance from the
# camera Z0. Measured on 21 throws (two libraries): 7.4–9.4 m. A non-falling object (a person walking, a
# rolling bag) has no such term. Accepted: 3–30 m (with the pooled field of view, 66°, if none is given).
GRAVITY_M_S2 = 9.81
DEFAULT_HFOV_DEG = 66.0
MIN_RELEASE_DEPTH_M, MAX_RELEASE_DEPTH_M = 3.0, 30.0


def _red_mask(hsv: np.ndarray) -> np.ndarray:
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    return ((h <= BAG_HUE_LOW) | (h >= BAG_HUE_HIGH)) & (s >= BAG_MIN_SAT) & (v >= BAG_MIN_VAL)


def _maxdiff(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return cv2.absdiff(a, b).max(axis=2)


def _shift(image: np.ndarray, dxy: np.ndarray) -> np.ndarray:
    if not np.any(np.abs(dxy) > 0.25):
        return image
    m = np.float32([[1, 0, dxy[0]], [0, 1, dxy[1]]])
    return cv2.warpAffine(image, m, (image.shape[1], image.shape[0]), borderMode=cv2.BORDER_REPLICATE)


def scene_shift(corners_per_frame: np.ndarray | None, frame: int, reference: int) -> np.ndarray:
    """Image translation of the scene from ``reference`` to ``frame`` (full-res px), from the deck corners."""
    if corners_per_frame is None:
        return np.zeros(2)
    c = np.asarray(corners_per_frame, float)
    frame, reference = min(max(frame, 0), len(c) - 1), min(max(reference, 0), len(c) - 1)
    return (c[frame] - c[reference]).reshape(-1, 2).mean(axis=0)


def moving_red_blobs(small: Sequence[np.ndarray], background: np.ndarray, k: int, shift_px: np.ndarray
                     ) -> list[dict[str, Any]]:
    """Bag-coloured blobs in (half-resolution) frame ``k`` that are not in the empty scene and are moving."""
    im = small[k]
    bg = _shift(background, shift_px)
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
    mask = _red_mask(hsv) & (_maxdiff(im, bg) > BACKGROUND_DIFF)
    prev, nxt = small[max(0, k - TEMPORAL_GAP)], small[min(len(small) - 1, k + TEMPORAL_GAP)]
    mask &= np.minimum(_maxdiff(im, prev), _maxdiff(im, nxt)) > TEMPORAL_DIFF
    mask = mask.astype(np.uint8)
    # Join the pieces of one motion-blurred bag before labelling; statistics use the original pixels.
    joined = cv2.dilate(mask, np.ones((3, 3), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(joined, 8)
    blobs = []
    for j in range(1, count):
        ys, xs = np.nonzero((labels == j) & (mask > 0))
        if len(xs) < MIN_BLOB_PX:
            continue
        blobs.append({"x": float(xs.mean()), "y": float(ys.mean()), "area": float(len(xs))})
    blobs.sort(key=lambda b: -b["area"])
    return blobs[:MAX_CANDIDATES]


# ------------------------------------------------------------------------------------------------
# The projectile model: u, v = polynomial / shared depth polynomial.

def fit_level(t: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray | None:
    """Level-camera model (a0, a1, c0, c1, c2, d1) by linear least squares (exact for three points)."""
    n = len(t)
    A = np.zeros((2 * n, 6))
    b = np.concatenate([u, v])
    A[:n, 0], A[:n, 1], A[:n, 5] = 1, t, -t * u
    A[n:, 2], A[n:, 3], A[n:, 4], A[n:, 5] = 1, t, t * t, -t * v
    try:
        p, *_ = np.linalg.lstsq(A, b, rcond=None)
    except np.linalg.LinAlgError:
        return None
    a0, a1, c0, c1, c2, d1 = p
    return np.array([a0, a1, 0.0, c0, c1, c2, d1, 0.0])


def fit_full(t: np.ndarray, u: np.ndarray, v: np.ndarray, w: np.ndarray | None = None,
             start: np.ndarray | None = None) -> np.ndarray | None:
    """Full model (pitched camera) by robust least squares on image residuals, from ``start``."""
    from scipy.optimize import least_squares
    if len(t) < 5:
        return start
    w = np.ones(len(t)) if w is None else w
    x0 = start if start is not None else fit_level(t, u, v)
    if x0 is None:
        return None

    def residual(p):
        pu, pv, _ = predict(p, t)
        return np.concatenate([(pu - u) * w, (pv - v) * w])
    # d2 and a2 are small (a few degrees of pitch); a weak prior keeps them so with few points.
    def regularised(p):
        return np.concatenate([residual(p), [p[2] * 50.0, p[7] * 2000.0]])
    try:
        sol = least_squares(regularised, x0, loss="soft_l1", f_scale=2.0, max_nfev=200)
    except Exception:  # noqa: BLE001 - keep the linear fit
        return x0
    return sol.x


def predict(p: np.ndarray, t: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    a0, a1, a2, c0, c1, c2, d1, d2 = p
    t = np.asarray(t, float)
    D = 1.0 + d1 * t + d2 * t * t
    Ds = np.where(np.abs(D) < 1e-6, 1e-6, D)
    return (a0 + a1 * t + a2 * t * t) / Ds, (c0 + c1 * t + c2 * t * t) / Ds, D


def release_depth_m(p: np.ndarray, focal_px: float, fps: float) -> float | None:
    """Distance of the bag from the camera at t = 0 implied by the model's gravity term (None if it does not fall)."""
    c2 = float(p[5])
    if c2 <= 0:
        return None
    return focal_px * GRAVITY_M_S2 / fps ** 2 / (2.0 * c2)


def _plausible(p: np.ndarray, t0: float, t1: float, gravity: tuple[float, float] | None = None) -> bool:
    if gravity is not None:
        depth = release_depth_m(p, *gravity)
        if depth is None or not MIN_RELEASE_DEPTH_M <= depth <= MAX_RELEASE_DEPTH_M:
            return False
    ts = np.linspace(t0, t1, 12)
    _, _, D = predict(p, ts)
    if not np.all(np.isfinite(D)) or D.min() <= 0.05:
        return False
    if not np.all(np.diff(D) < 0):            # the bag comes towards the camera the whole way
        return False
    growth = D[0] / D[-1]
    return MIN_GROWTH <= growth <= MAX_GROWTH


def _tolerance(area: np.ndarray) -> np.ndarray:
    return INLIER_BASE_PX + INLIER_SIZE_SHARE * np.sqrt(area)


def _associate(p: np.ndarray, frames_t: np.ndarray, cand: list[np.ndarray]) -> tuple[float, list[int | None]]:
    """For each frame: the blob nearest the model (if within tolerance); MSAC score."""
    pu, pv, _ = predict(p, frames_t)
    score, chosen = 0.0, []
    for k, c in enumerate(cand):
        if len(c) == 0:
            chosen.append(None)
            continue
        d = np.hypot(c[:, 0] - pu[k], c[:, 1] - pv[k])
        tol = _tolerance(c[:, 2])
        ok = d < tol
        if not ok.any():
            chosen.append(None)
            continue
        quality = np.where(ok, 1.0 - (d / tol) ** 2, -1.0)
        j = int(np.argmax(quality))
        score += float(quality[j])
        chosen.append(j)
    return score, chosen


def fit_projectile(frames_t: np.ndarray, cand: list[np.ndarray], *, gravity: tuple[float, float] | None = None,
                   end_check=None, rng_seed: int = 0) -> dict[str, Any] | None:
    """RANSAC over per-frame candidates (``cand[k]`` = array of [x, y, area] at time ``frames_t[k]``)."""
    rng = np.random.default_rng(rng_seed)
    pool = [(k, j) for k, c in enumerate(cand) for j in range(len(c))]
    if len({k for k, _ in pool}) < 3:
        return None
    weights = np.array([math.sqrt(cand[k][j, 2]) for k, j in pool])
    weights = weights / weights.sum()
    t0, t1 = float(frames_t[0]), float(frames_t[-1])
    best: tuple[float, np.ndarray] | None = None
    for _ in range(RANSAC_ITERATIONS):
        idx = rng.choice(len(pool), size=3, replace=False, p=weights)
        picks = sorted((pool[i] for i in idx), key=lambda kj: kj[0])
        ks = [k for k, _ in picks]
        if min(np.diff(ks)) < MIN_SAMPLE_GAP:
            continue
        pts = np.array([cand[k][j] for k, j in picks])
        p = fit_level(frames_t[ks], pts[:, 0], pts[:, 1])
        if p is None or not _plausible(p, t0, t1, gravity):
            continue
        if end_check is not None and not end_check(p):
            continue
        score, _ = _associate(p, frames_t, cand)
        if best is None or score > best[0]:
            best = (score, p)
    if best is None:
        return None
    p = best[1]
    chosen: list[int | None] = []
    for _ in range(3):                       # refine on the inliers, re-associate
        _, chosen = _associate(p, frames_t, cand)
        ks = [k for k, j in enumerate(chosen) if j is not None]
        if len(ks) < 3:
            return None
        pts = np.array([cand[k][chosen[k]] for k in ks])
        q = fit_full(frames_t[ks], pts[:, 0], pts[:, 1], start=p) if len(ks) >= 6 else fit_level(frames_t[ks], pts[:, 0], pts[:, 1])
        if q is None or not _plausible(q, t0, t1, gravity) or (end_check is not None and not end_check(q)):
            break
        p = q
    score, chosen = _associate(p, frames_t, cand)
    return {"params": p, "chosen": chosen, "score": score}


def _size_consistent(p: np.ndarray, frames_t: np.ndarray, cand: list[np.ndarray], chosen: list[int | None]
                     ) -> list[int | None]:
    """Drop inliers whose area disagrees with the depth the model gives (area ∝ 1 / depth²)."""
    ks = [k for k, j in enumerate(chosen) if j is not None]
    if len(ks) < 4:
        return chosen
    _, _, D = predict(p, frames_t)
    norm = np.array([cand[k][chosen[k], 2] * D[k] ** 2 for k in ks])
    ref = float(np.median(norm))
    out = list(chosen)
    for k, value in zip(ks, norm):
        if not 1.0 / AREA_RATIO_MAX <= value / ref <= AREA_RATIO_MAX:
            out[k] = None
    return out


def flight_path(frames: Sequence[np.ndarray], release_frame: int | None, contact_frame: int | None, *,
                release_px: Sequence[float] | None = None, corners_per_frame: np.ndarray | None = None,
                contact_px: Sequence[float] | None = None, fps: float = 30.0,
                hfov_deg: float | None = None) -> dict[str, Any]:
    """The bag's image path from release to first contact. Returns {"status", "path", ...}; the path is a list
    of {"frame", "px", "area_px"} in full-resolution pixels, only for frames where the bag was seen on the
    fitted trajectory."""
    n = len(frames)
    if release_frame is None or n < 10 or not 0 <= release_frame < n:
        return {"status": "unavailable", "reason": "No release frame in the front clip.", "path": []}
    stop = contact_frame if contact_frame is not None and contact_frame > release_frame else None
    last = min(n - 1, (stop + CONTACT_SYNC_FRAMES) if stop is not None else release_frame + int(round(1.6 * fps)))
    first = max(0, release_frame - 2)
    if last - first < 8:
        return {"status": "unavailable", "reason": "Too few frames between release and contact.", "path": []}
    s = SEARCH_SCALE
    lo, hi = max(0, first - TEMPORAL_GAP), min(n, last + TEMPORAL_GAP + 1)
    small = {k: cv2.resize(frames[k], None, fx=s, fy=s, interpolation=cv2.INTER_AREA) for k in range(lo, hi)}
    # Empty scene: median of frames before release (every 3rd of up to 2.5 s), each shifted to the release
    # frame's camera position. The bag is in the hand then and moves, so the median does not keep it.
    bg_frames = list(range(max(0, release_frame - int(2.5 * fps)), max(1, release_frame - int(0.2 * fps)), 3))
    if len(bg_frames) < 5:
        bg_frames = list(range(0, max(1, release_frame - 2)))
    stack = []
    for k in bg_frames:
        im = cv2.resize(frames[k], None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        stack.append(_shift(im, -scene_shift(corners_per_frame, k, release_frame) * s))
    background = np.median(np.stack(stack), axis=0).astype(np.uint8)
    seq = [small[k] for k in range(lo, hi)]
    ks = list(range(first, last + 1))
    cand = []
    for k in ks:
        blobs = moving_red_blobs(seq, background, k - lo, scene_shift(corners_per_frame, k, release_frame) * s)
        cand.append(np.array([[b["x"], b["y"], b["area"]] for b in blobs]).reshape(-1, 3))
    frames_t = np.array(ks, float) - release_frame

    end_check = None
    if stop is not None and corners_per_frame is not None:
        quad = np.asarray(corners_per_frame, float)[min(stop, len(corners_per_frame) - 1)] * s
        width = float(np.ptp(quad[:, 0]))
        target = np.asarray(contact_px, float) * s if contact_px is not None else quad.mean(axis=0)
        reach = width * (1.0 if contact_px is not None else 1.5)

        def end_check(p):                    # at first contact the bag is at the deck
            pu, pv, _ = predict(p, np.array([stop - release_frame], float))
            return math.hypot(pu[0] - target[0], pv[0] - target[1]) <= reach
    width_px = frames[0].shape[1] * s
    focal = (width_px / 2) / math.tan(math.radians(hfov_deg or DEFAULT_HFOV_DEG) / 2)
    gravity = (focal, float(fps))
    fit = fit_projectile(frames_t, cand, gravity=gravity, end_check=end_check)
    if fit is None and end_check is not None:
        # A bag that ends far from the deck (well off the board) still follows one projectile.
        fit = fit_projectile(frames_t, cand, gravity=gravity)
    if fit is None:
        return {"status": "unavailable", "reason": "No bag-coloured object followed a throw's path.", "path": []}
    chosen = _size_consistent(fit["params"], frames_t, cand, fit["chosen"])
    inliers = [k for k, j in enumerate(chosen) if j is not None]
    span = max(1, (stop if stop is not None else last) - release_frame)
    if len(inliers) < max(MIN_INLIER_FRAMES, MIN_INLIER_SHARE * span):
        return {"status": "unavailable", "path": [], "inlier_frames": len(inliers),
                "reason": "The bag was seen in too few frames to trust its path."}
    path = []
    for k in inliers:
        if ks[k] < release_frame or (stop is not None and ks[k] > stop + CONTACT_SYNC_FRAMES):
            continue                         # the path runs from release to first contact
        x, y, area = cand[k][chosen[k]]
        path.append({"frame": int(ks[k]), "px": [float(x / s), float(y / s)], "area_px": float(area / s / s)})
    p = fit["params"]
    pu, pv, D = predict(p, frames_t)
    result = {"status": "measured", "path": path, "inlier_frames": len(inliers), "frames_searched": len(ks),
              "model": {"params": [float(v) for v in p], "release_frame": int(release_frame), "scale": s},
              "growth": float(D[0] / D[-1]), "release_depth_m": release_depth_m(p, *gravity)}
    if release_px is not None:
        result["release_gap_px"] = float(math.hypot(pu[ks.index(release_frame)] / s - release_px[0],
                                                    pv[ks.index(release_frame)] / s - release_px[1]))
    return result


# ------------------------------------------------------------------------------------------------
# Near and on the deck: the last frames of the flight, first contact and the slide.

DECK_STEP_PX = 90.0               # full-res px per frame: the bag's last flight steps before contact are 32–73
DECK_MIN_MOVING_SHARE = 0.15      # share of a blob's pixels that changed against two frames before/after
DECK_MAX_GAP = 3                  # frames a track may skip (bag hidden behind the hole's rim, blur)
DECK_SKIP_COST = 0.5              # per skipped frame, against a reward of 1 per tracked frame
DECK_HOLE_INTERIOR_SHARE = 0.8    # a blob this much inside the hole's outline is the hole interior, not a bag


def _scene_background(frames: Sequence[np.ndarray], before: int, scale: float) -> tuple[np.ndarray, int]:
    """Median of up to 15 frames ending one second (30 frames) before ``before``: the scene near the deck
    without the thrown bag. Returns the image and the frame its camera position is taken from."""
    end = max(1, before - 30)
    idx = np.unique(np.linspace(0, end - 1, num=min(15, end)).round().astype(int))
    stack = [cv2.resize(frames[k], None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) for k in idx]
    return np.median(np.stack(stack), axis=0).astype(np.uint8), int(idx[len(idx) // 2])


def track_on_deck(frames: Sequence[np.ndarray], anchors_px: np.ndarray, start: int, stop: int, roi_mask: np.ndarray,
                  min_area: float, max_area: float, scale: float = SEARCH_SCALE,
                  hole_px: Sequence[np.ndarray] | None = None) -> list[dict[str, Any]]:
    """The moving bag near/on the deck from ``start`` to ``stop`` (front-clip frames).

    ``anchors_px[f]`` is a fixed deck point in frame f's image (it gives the camera's drift). A candidate is a
    bag-red blob (S ≥ 60: the deck paint is S 25–60) that differs from the empty scene and of which at least
    15 % of the pixels changed against two frames before and after (a bag at rest is left out, as before). The
    track is the best chain through all frames (dynamic programming: +1 per tracked frame, minus the squared
    step relative to 90 px per frame, minus 0.5 per skipped frame), not a greedy nearest-neighbour link. Each
    point is the bag *in that frame* (frame-pair differencing put it one frame early or late, 44–71 px off).
    ``hole_px[f]`` (optional) is the hole's outline in frame f: a blob lying almost wholly inside it (≥ 80 % of
    its pixels) is the hole's dark-red interior, which flickers and passes the motion test while nothing moves
    (Player 3 take 2 throw 1: it was "tracked" for 12 frames after the bag had left the view); it is left out.
    Returns [{"frame", "px", "bottom_px", "area_px"}] in full-resolution pixels."""
    n = len(frames)
    lo, hi = max(1, start), min(n - 1, stop)
    if hi - lo < 1:
        return []
    s = scale
    roi_small = cv2.resize(np.asarray(roi_mask, np.uint8), None, fx=s, fy=s, interpolation=cv2.INTER_NEAREST) > 0
    background, ref = _scene_background(frames, lo, s)
    a = np.asarray(anchors_px, float)
    small = {k: cv2.resize(frames[k], None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
             for k in range(max(0, lo - TEMPORAL_GAP), min(n, hi + TEMPORAL_GAP + 1))}
    min_px, max_px = 0.5 * min_area * s * s, 1.5 * max_area * s * s
    nodes: list[list[dict[str, Any]]] = []
    ks = list(range(lo, hi))
    for k in ks:
        im = small[k]
        shift = (a[min(k, len(a) - 1)] - a[min(ref, len(a) - 1)]) * s
        colour = _red_mask(cv2.cvtColor(im, cv2.COLOR_BGR2HSV)) & (_maxdiff(im, _shift(background, shift)) > BACKGROUND_DIFF)
        colour &= roi_small
        prev, nxt = small[max(min(small), k - TEMPORAL_GAP)], small[min(max(small), k + TEMPORAL_GAP)]
        moving = np.minimum(_maxdiff(im, prev), _maxdiff(im, nxt)) > TEMPORAL_DIFF
        mask = cv2.morphologyEx(colour.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        count, labels, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
        hole_mask = None
        if hole_px is not None and k < len(hole_px) and hole_px[k] is not None:
            hole_mask = np.zeros(mask.shape, np.uint8)
            cv2.fillPoly(hole_mask, [np.round(np.asarray(hole_px[k], float) * s).astype(np.int32)], 1)
        frame_nodes = []
        for j in range(1, count):
            area = float(stats[j, cv2.CC_STAT_AREA])
            if not min_px <= area <= max_px:
                continue
            ys, xs = np.nonzero(labels == j)
            if float(np.mean(moving[ys, xs])) < DECK_MIN_MOVING_SHARE:
                continue
            if hole_mask is not None and float(np.mean(hole_mask[ys, xs])) >= DECK_HOLE_INTERIOR_SHARE:
                continue
            low = ys >= np.percentile(ys, 85)
            frame_nodes.append({"frame": k, "px": [float(cents[j][0] / s), float(cents[j][1] / s)],
                                "bottom_px": [float(np.median(xs[low]) / s), float(ys.max() / s)],
                                "area_px": area / s / s})
        nodes.append(frame_nodes)
    # Best chain: maximise (tracked frames) − Σ (step / allowed step)² − skip costs; any start and end.
    best: list[list[tuple[float, tuple[int, int] | None]]] = []
    for i, frame_nodes in enumerate(nodes):
        row = []
        for node in frame_nodes:
            value, back = 1.0, None
            p = np.asarray(node["px"])
            for gap in range(1, DECK_MAX_GAP + 1):
                if i - gap < 0:
                    break
                for j, other in enumerate(nodes[i - gap]):
                    d = float(np.linalg.norm(p - np.asarray(other["px"])))
                    allowed = DECK_STEP_PX * gap
                    if d > allowed:
                        continue
                    v = best[i - gap][j][0] + 1.0 - (d / allowed) ** 2 - DECK_SKIP_COST * (gap - 1)
                    if v > value:
                        value, back = v, (i - gap, j)
            row.append((value, back))
        best.append(row)
    end = max(((best[i][j][0], (i, j)) for i in range(len(best)) for j in range(len(best[i]))), default=None)
    if end is None:
        return []
    chain = []
    at: tuple[int, int] | None = end[1]
    while at is not None:
        i, j = at
        chain.append(nodes[i][j])
        at = best[i][j][1]
    return chain[::-1]
