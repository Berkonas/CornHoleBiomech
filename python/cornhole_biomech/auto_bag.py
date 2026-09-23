"""Automatic bag flight detection: motion candidates + projectile-constrained selection.

Method (classical sports-ball tracking, cf. TrackNetV3's background-subtraction
and trajectory-rectification stages, without a trained network):

1. Candidates: camera-compensated three-frame differencing. Each frame is
   compared with its neighbours after aligning them, so hand-held drift is not
   "motion". Alignment: an ORB + RANSAC similarity per step initialises an
   intensity-based (ECC) affine registration of every frame against a keyframe,
   so composed transforms stay sub-pixel instead of accumulating drift.
2. Selection: RANSAC over candidates from different frames for a free-flight
   path x(t) ≈ linear, y(t) = quadratic with downward (image +y) curvature,
   moving toward the target. The fitted image gravity must be plausible for the
   athlete's scale (projected arm length ≈ 0.45–0.9 m), which rejects clutter.
3. Events: release is where the fitted parabola, traced backwards, meets the
   throwing wrist. First contact is OBSERVED only when the last
   parabola-consistent detection lies on the detected board's deck/front face or
   the floor (contact.py); a flight that ends in the air is `lost_in_flight`,
   and its parabola is extended to an ESTIMATED (predicted) contact instead.
   Candidates inside person masks (scene.py) cannot seed a flight.
4. Acceptance: enough inliers over enough of the flight with small residuals.
   Otherwise the result is "needs_review" with the reason, never silently used.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import cv2
import numpy as np

from .background import build_plate
from .bag import GRAVITY_M_S2, _robust_polynomial
from .bag_segment import SEGMENT_REVISION, refine_flight, track_after_contact
from .board import detect_board, solve_board
from .contact import classify_flight_end, landing_summary, predict_contact, suggest_outcome

AUTO_BAG_REVISION = "auto_motion_parabola_v11_scene"
ARM_LENGTH_RANGE_M = (0.45, 0.90)   # projected shoulder–wrist length; generous for foreshortening
MIN_INLIERS = 12
MIN_SPAN_SECONDS = 0.25
MIN_COVERAGE = 0.6
MIN_TRAVEL_ARM_LENGTHS = 4.0   # a throw carries the bag metres toward the board; hand/catch motion does not
# A held bag sits at the fingertips, about one hand length (~0.34 arm lengths) beyond the
# wrist landmark, so anything within 0.45 arm lengths of the wrist is still treated as held.
IN_HAND_ARM_LENGTHS = 0.45
MAX_RMS_ARM_LENGTHS = 0.08  # whole-flight parabola residual limit (drag/perspective allowance)
RELEASE_AT_HAND_ARM_LENGTHS = 0.8  # the first free-flight point must be this close to the wrist
# A descending track that ends this close (frames) before its own predicted surface
# contact is an observed contact: the last detection is the touchdown, whose
# throw-plane height reads high when the bag lands off the board centreline
# (pilot P2: on the floor at 0.14 m "height", predicted floor contact 1 frame later).
NEAR_CONTACT_FRAMES = 2


# Registration (hand-held camera). ORB keypoint steps alone captured only ~66 % of the
# sub-pixel inter-frame motion on the pilot clips, so their composition drifted 15–40 px
# over 200–350 frames. Each frame is instead registered directly to a keyframe with ECC
# (enhanced correlation coefficient), initialised from the previous frame's registration
# composed with the ORB step; per-step transforms are derived from those, so the chain
# telescopes and error does not accumulate. Measured on P1/P2/P3 (task-4b report):
# residual vs frame 0 fell from up to 51 px to ≤ 4.6 px (44 of 52 patch checks ≤ 3 px).
# Affine rather than Euclidean: with hand-held translation the floor/board and the far
# walls move differently (parallax); an affine fit of the whole frame kept the board
# within ~3.5 px where a Euclidean fit left 9 px on P1.
REGISTRATION_SCALE = 0.25          # ECC image scale vs full resolution (half-scale gave no gain at 3× the time)
REGISTRATION_CRITERIA = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 50, 1e-5)
KEYFRAME_MIN_CC = 0.8              # below this correlation a new keyframe starts (pilot clips: min 0.93)
MAX_ECC_CORRECTION_PX = 3.0        # at REGISTRATION_SCALE; a larger jump from the ORB prediction is distrusted


@dataclass(frozen=True)
class Candidate:
    frame: int
    x: float        # full-resolution pixels, x right
    y: float        # full-resolution pixels, y down
    area: float
    in_person: bool = False   # inside an Apple Vision person mask (athlete or bystander)


# ---------------------------------------------------------------- detection
def _similarity(orb, matcher, a, b) -> np.ndarray:
    """2×3 transform mapping image a coordinates onto image b (identity if unsure)."""
    identity = np.float32([[1, 0, 0], [0, 1, 0]])
    ka, da = a
    kb, db = b
    if da is None or db is None or len(ka) < 12 or len(kb) < 12:
        return identity
    matches = matcher.match(da, db)
    if len(matches) < 12:
        return identity
    pa = np.float32([ka[m.queryIdx].pt for m in matches])
    pb = np.float32([kb[m.trainIdx].pt for m in matches])
    M, inliers = cv2.estimateAffinePartial2D(pa, pb, method=cv2.RANSAC, ransacReprojThreshold=2.0)
    if M is None or inliers is None or int(inliers.sum()) < 10:
        return identity
    return M.astype(np.float32)


def detect_moving_blobs_in_frames(frames: Sequence[np.ndarray], scale: float = 0.5,
                                  min_area: int = 3, max_area: int = 400, merge_px: float = 16.0
                                  ) -> tuple[list[Candidate], list[np.ndarray]]:
    """Small moving blobs per frame and per-frame transforms (frame t → t−1, full-res).

    Three-frame differencing keeps only pixels that differ from BOTH aligned
    neighbours, which suppresses ghosts left by the previous position.
    """
    gray = []
    for f in frames:
        small = cv2.resize(f, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale != 1 else f
        gray.append(cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (3, 3), 0))
    orb = cv2.ORB_create(1500)
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    features = [orb.detectAndCompute(g, None) for g in gray]
    h, w = gray[0].shape
    orb_steps = [np.float32([[1, 0, 0], [0, 1, 0]])]
    for t in range(1, len(gray)):
        orb_steps.append(_similarity(orb, matcher, features[t], features[t - 1]))
    to_prev = _register_to_keyframes(gray, orb_steps, min(1.0, REGISTRATION_SCALE / scale))
    candidates: list[Candidate] = []
    for t in range(1, len(gray) - 1):
        prev_to_t = cv2.invertAffineTransform(to_prev[t])
        next_to_t = to_prev[t + 1]
        prev = cv2.warpAffine(gray[t - 1], prev_to_t, (w, h), borderMode=cv2.BORDER_REPLICATE)
        nxt = cv2.warpAffine(gray[t + 1], next_to_t, (w, h), borderMode=cv2.BORDER_REPLICATE)
        diff = np.minimum(cv2.absdiff(gray[t], prev), cv2.absdiff(gray[t], nxt))
        med = float(np.median(diff))
        mad = float(np.median(np.abs(diff - med)))
        mask = (diff > max(18.0, med + 6 * 1.4826 * mad)).astype(np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        count, _, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
        blobs = [(float(centroids[i][0] / scale), float(centroids[i][1] / scale), int(stats[i, cv2.CC_STAT_AREA]))
                 for i in range(1, count) if int(stats[i, cv2.CC_STAT_AREA]) >= min_area]
        for x, y, area in _merge_fragments(blobs, merge_px):
            if area <= max_area:
                candidates.append(Candidate(t, x, y, area / scale**2))
    full = []
    for M in to_prev:   # rescale translation to full resolution
        F = M.copy()
        F[:, 2] /= scale
        full.append(F)
    return candidates, full


def _ecc(template: np.ndarray, image: np.ndarray, init: np.ndarray) -> tuple[float, np.ndarray] | None:
    """Affine warp W with image(W·x) ≈ template(x), refined from `init`; None if unreliable."""
    try:
        cc, warp = cv2.findTransformECC(template, image, init.astype(np.float32), cv2.MOTION_AFFINE,
                                        REGISTRATION_CRITERIA, None, 5)
    except cv2.error:    # raised when the iteration diverges or the images are degenerate
        return None
    if not np.isfinite(warp).all() or not np.isfinite(cc):
        return None
    h, w = template.shape
    corners = np.array([[0, 0, 1], [w, 0, 1], [0, h, 1], [w, h, 1]], dtype=np.float64).T
    if np.abs((warp.astype(np.float64) - init) @ corners).max() > MAX_ECC_CORRECTION_PX:
        return None
    return float(cc), warp.astype(np.float64)


def _register_to_keyframes(gray: list[np.ndarray], orb_steps: list[np.ndarray], factor: float) -> list[np.ndarray]:
    """Per-step transforms (frame t → t−1, in `gray` pixels) from keyframe registration.

    Frame t is registered to the current keyframe k with ECC, giving A_t (t → k); then
    to_prev[t] = A_{t−1}⁻¹ · A_t, so composing steps back to k reproduces A_t exactly and
    errors do not accumulate. If ECC fails or correlates below KEYFRAME_MIN_CC, the step is
    registered pairwise (ECC t → t−1, else the ORB step) and t becomes the new keyframe.
    ECC runs on images resized by `factor`; translations are rescaled back.
    """
    def lift(m):
        return np.vstack([m, [0, 0, 1]]).astype(np.float64)

    def rescale(m, k):
        m = m.astype(np.float64).copy()
        m[:2, 2] *= k
        return m

    small = [cv2.resize(g, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA) if factor != 1 else g
             for g in gray]
    key, a_prev = 0, np.eye(3)
    steps = [np.float32([[1, 0, 0], [0, 1, 0]])]
    for t in range(1, len(small)):
        orb_step = lift(rescale(orb_steps[t], factor))
        fit = _ecc(small[t], small[key], (a_prev @ orb_step)[:2])
        if fit is not None and fit[0] >= KEYFRAME_MIN_CC:
            a_t = lift(fit[1])
            step = np.linalg.inv(a_prev) @ a_t
        else:
            pair = _ecc(small[t], small[t - 1], orb_step[:2])
            step = lift(pair[1]) if pair is not None else orb_step
            key, a_t = t, np.eye(3)
        steps.append(rescale(step[:2], 1 / factor).astype(np.float32))
        a_prev = a_t
    return steps


def _merge_fragments(blobs: list[tuple[float, float, int]], merge_px: float) -> list[tuple[float, float, int]]:
    """Join fragments of one object split by motion blur (area-weighted centroid).

    Greedy single-linkage within `merge_px` full-resolution pixels. Small enough that
    the bag is not merged with the hand or a second bag in normal framing.
    """
    groups: list[list[tuple[float, float, int]]] = []
    for blob in sorted(blobs, key=lambda b: -b[2]):
        for group in groups:
            if any(np.hypot(blob[0] - g[0], blob[1] - g[1]) <= merge_px for g in group):
                group.append(blob)
                break
        else:
            groups.append([blob])
    merged = []
    for group in groups:
        area = sum(b[2] for b in group)
        merged.append((sum(b[0] * b[2] for b in group) / area, sum(b[1] * b[2] for b in group) / area, area))
    return merged


def read_frames(video_path: str) -> tuple[list[np.ndarray], float]:
    capture = cv2.VideoCapture(str(video_path))
    fps = float(capture.get(cv2.CAP_PROP_FPS)) or 30.0
    frames = []
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        frames.append(frame)
    capture.release()
    return frames, fps


def reference_chain(to_prev: list[np.ndarray], reference: int) -> dict[int, np.ndarray]:
    """3×3 transforms mapping each frame's pixels into the pixel frame of `reference`."""
    n = len(to_prev)
    chain: dict[int, np.ndarray] = {reference: np.eye(3)}
    for t in range(reference + 1, n):      # t → t−1 → … → reference
        chain[t] = chain[t - 1] @ np.vstack([to_prev[t], [0, 0, 1]])
    for t in range(reference - 1, -1, -1):  # t → t+1 → … → reference
        chain[t] = chain[t + 1] @ np.linalg.inv(np.vstack([to_prev[t + 1], [0, 0, 1]]))
    return chain


def to_reference(candidates: list[Candidate], to_prev: list[np.ndarray], reference: int) -> list[Candidate]:
    """Express every candidate in the pixel frame of `reference` using chained transforms."""
    chain = reference_chain(to_prev, reference)
    out = []
    for c in candidates:
        m = chain[c.frame]
        x, y, _ = m @ np.array([c.x, c.y, 1.0])
        out.append(Candidate(c.frame, float(x), float(y), c.area))
    return out


# ---------------------------------------------------------------- selection
def _gravity_range(arm_length_px: float | None) -> tuple[float, float]:
    if not arm_length_px or arm_length_px <= 0:
        return 100.0, 1e5
    lo_ppm, hi_ppm = arm_length_px / ARM_LENGTH_RANGE_M[1], arm_length_px / ARM_LENGTH_RANGE_M[0]
    return 0.75 * GRAVITY_M_S2 * lo_ppm, 1.25 * GRAVITY_M_S2 * hi_ppm


def _predict(coef_x, coef_y, t):
    return (coef_x[0] + coef_x[1] * t + coef_x[2] * t * t, coef_y[0] + coef_y[1] * t + coef_y[2] * t * t)


def _inliers(by_frame, frames, t_ref, fps, coef_x, coef_y, tol):
    chosen = {}
    for f in frames:
        px, py = _predict(coef_x, coef_y, (f - t_ref) / fps)
        best = min(by_frame[f], key=lambda c: (c.x - px) ** 2 + (c.y - py) ** 2)
        d = float(np.hypot(best.x - px, best.y - py))
        if d < tol:
            chosen[f] = (best, d)
    return chosen


def _longest_run(frames: list[int], max_gap: int) -> list[int]:
    if not frames:
        return []
    runs, run = [], [frames[0]]
    for f in frames[1:]:
        if f - run[-1] <= max_gap:
            run.append(f)
        else:
            runs.append(run); run = [f]
    runs.append(run)
    return max(runs, key=len)


def _extend(by_frame, chosen, fps, gate, local=6, max_missed=3, wrist=None, in_hand_px=None):
    """Grow the flight at both ends using a local quadratic of the nearest detections.

    A global parabola extrapolated to the ends of a real (drag, perspective,
    residual camera motion) flight drifts by tens of pixels; a local fit does not.
    """
    chosen = dict(chosen)
    for direction in (-1, 1):
        missed = 0
        while missed <= max_missed and len(chosen) >= 4:
            ends = sorted(chosen)[:local] if direction < 0 else sorted(chosen)[-local:]
            edge = ends[0] if direction < 0 else ends[-1]
            f = edge + direction * (missed + 1)
            t = np.array([(g - edge) / fps for g in ends])
            degree = 2 if len(ends) >= 5 else 1
            px = np.polyval(np.polyfit(t, [chosen[g][0].x for g in ends], degree), (f - edge) / fps)
            py = np.polyval(np.polyfit(t, [chosen[g][0].y for g in ends], degree), (f - edge) / fps)
            options = by_frame.get(f, [])
            best = min(options, key=lambda c: (c.x - px) ** 2 + (c.y - py) ** 2) if options else None
            if (direction < 0 and best is not None and wrist is not None and in_hand_px
                    and f < len(wrist) and np.isfinite(wrist[f]).all()
                    and np.hypot(best.x - wrist[f][0], best.y - wrist[f][1]) < in_hand_px):
                break   # the bag is still in the hand: free flight starts after this frame
            if best is not None and np.hypot(best.x - px, best.y - py) < gate * (1 + missed):
                chosen[f] = (best, float(np.hypot(best.x - px, best.y - py)))
                missed = 0
            else:
                missed += 1
    return chosen


def _trim_to_projectile(chosen, f_ref, fps, limit, min_points=6):
    """Drop end points that no longer follow one parabola (bag still in hand, or sliding/bouncing after contact).

    The end whose residual is worst is removed and the parabola refitted until both
    ends lie within `limit` pixels. The first remaining frame is free flight; the
    last is the final frame on the projectile path (first contact happens here).
    """
    run = sorted(chosen)
    while True:
        t = np.array([(f - f_ref) / fps for f in run])
        coef_x, _, _ = _robust_polynomial(t, np.array([chosen[f][0].x for f in run]), 2)
        coef_y, _, _ = _robust_polynomial(t, np.array([chosen[f][0].y for f in run]), 2)
        if len(run) <= min_points:
            return run, coef_x, coef_y
        px, py = _predict(coef_x, coef_y, t)
        residual = np.hypot(np.array([chosen[f][0].x for f in run]) - px, np.array([chosen[f][0].y for f in run]) - py)
        # The start was already stopped at the hand by the backward extension, so only a
        # grossly deviating start is removed. The end is judged against a LOCAL parabola of
        # the preceding frames: late free flight drifts from one whole-flight parabola
        # (perspective, drag) but a slide or bounce breaks sharply from the local one.
        if _end_breaks_locally(chosen, run, fps, limit):
            run = run[:-1]
        elif residual[0] > 2 * limit:
            run = run[1:]
        else:
            return run, coef_x, coef_y


def _end_breaks_locally(chosen, run, fps, limit, window=15) -> bool:
    if len(run) < 8:
        return False
    before = run[-1 - min(window, len(run) - 1):-1]
    t = np.array([(f - run[-1]) / fps for f in before])
    degree = 2 if len(before) >= 5 else 1
    px = np.polyval(np.polyfit(t, [chosen[f][0].x for f in before], degree), 0.0)
    py = np.polyval(np.polyfit(t, [chosen[f][0].y for f in before], degree), 0.0)
    end = chosen[run[-1]][0]
    return float(np.hypot(end.x - px, end.y - py)) > limit


def _plausible(coef_x, coef_y, sign, g_range) -> bool:
    ay = 2 * coef_y[2]
    ax = 2 * coef_x[2]
    return (sign * coef_x[1] > 0 and g_range[0] <= ay <= g_range[1] and abs(ax) <= 0.35 * ay)


def build_tracklets(candidates: list[Candidate], gate_px: float, first_step_px: float,
                    max_missed: int = 3) -> list[list[Candidate]]:
    """Link candidates frame to frame with a constant-velocity prediction (greedy nearest match).

    Standard first stage of multi-candidate ball tracking: short consistent
    chains are far likelier to be one object than random triples of blobs.
    """
    by_frame: dict[int, list[Candidate]] = {}
    for c in candidates:
        by_frame.setdefault(c.frame, []).append(c)
    active: list[dict[str, Any]] = []
    finished: list[list[Candidate]] = []
    for f in sorted(by_frame):
        pool = list(by_frame[f])
        pairs = []
        for i, track in enumerate(active):
            gap = f - track["points"][-1].frame
            px = track["points"][-1].x + track["vx"] * gap
            py = track["points"][-1].y + track["vy"] * gap
            # A one-point track has no velocity yet: allow any plausible bag step.
            gate = (first_step_px * gap if len(track["points"]) == 1
                    else gate_px + 0.5 * np.hypot(track["vx"], track["vy"]) * gap)
            for j, c in enumerate(pool):
                d = np.hypot(c.x - px, c.y - py)
                if d < gate:
                    pairs.append((d, i, j))
        used_t, used_c = set(), set()
        for d, i, j in sorted(pairs):
            if i in used_t or j in used_c:
                continue
            track, c = active[i], pool[j]
            last = track["points"][-1]
            gap = c.frame - last.frame
            track["vx"], track["vy"] = (c.x - last.x) / gap, (c.y - last.y) / gap
            track["points"].append(c)
            used_t.add(i); used_c.add(j)
        still = []
        for i, track in enumerate(active):
            if i in used_t or f - track["points"][-1].frame <= max_missed:
                still.append(track)
            else:
                finished.append(track["points"])
        active = still + [{"points": [c], "vx": 0.0, "vy": 0.0} for j, c in enumerate(pool) if j not in used_c]
    finished += [t["points"] for t in active]
    return [t for t in finished if len(t) >= 5]


def find_flight(candidates: list[Candidate], fps: float, target_direction: str,
                arm_length_px: float | None = None, iterations: int = 1500, seed: int = 7,
                wrist: np.ndarray | None = None, to_prev: list[np.ndarray] | None = None) -> dict[str, Any]:
    """Choose the candidate subset that behaves like a thrown bag (see module docstring).

    With `to_prev` (per-frame camera transforms), the whole-flight residual used for
    acceptance is measured on the detections expressed in the first flight frame's pixels,
    so hand-held camera motion during the flight does not count as deviation from one arc.
    """
    sign = 1.0 if target_direction == "left_to_right" else -1.0
    g_range = _gravity_range(arm_length_px)
    tol = max(6.0, 0.05 * arm_length_px) if arm_length_px else 8.0
    by_frame: dict[int, list[Candidate]] = {}
    for c in candidates:
        by_frame.setdefault(c.frame, []).append(c)
    frames = sorted(by_frame)
    # People (athlete, bystanders) cannot SEED a flight: their limbs and clothing
    # move like a bag. Inliers, extension and trimming still use every candidate,
    # since a bag right at the hand may sit inside the person mask.
    seedable = [c for c in candidates if not c.in_person]
    seed_by_frame: dict[int, list[Candidate]] = {}
    for c in seedable:
        seed_by_frame.setdefault(c.frame, []).append(c)
    seed_frames = sorted(seed_by_frame)
    result: dict[str, Any] = {"status": "not_found", "revision": AUTO_BAG_REVISION, "points": [], "fit": None,
                              "reasons": ["No moving object followed a plausible projectile path."],
                              "gravity_range_px_s2": list(g_range), "tolerance_px": tol}
    if len(frames) < 3 or len(seed_frames) < 3:
        return result
    rng = np.random.default_rng(seed)
    max_span = int(1.5 * fps)
    best: tuple[int, float, Any] | None = None

    def consider(f1: int, coef_x, coef_y) -> None:
        nonlocal best
        if not _plausible(coef_x, coef_y, sign, g_range):
            return
        near = [f for f in frames if f1 - max_span <= f <= f1 + 2 * max_span]
        chosen = _inliers(by_frame, near, f1, fps, coef_x, coef_y, tol)
        score, error = len(chosen), sum(d for _, d in chosen.values())
        if best is None or score > best[0] or (score == best[0] and error < best[1]):
            best = (score, error, (f1, coef_x, coef_y))

    # Stage 1: tracklet seeds (fast, finds the flight when it is well detected).
    # Fastest plausible bag ≈ 12 m/s; pixels per metre from the arm-length prior.
    ppm_hi = arm_length_px / ARM_LENGTH_RANGE_M[0] if arm_length_px else 250.0
    first_step = 12.0 * ppm_hi / fps
    # Tracklets often join free flight to the hand before release or the slide after
    # landing, so seeds come from overlapping sub-windows; one lies inside the flight.
    window = max(8, int(0.2 * fps))
    for track in build_tracklets(seedable, gate_px=2 * tol, first_step_px=first_step):
        starts = range(0, max(1, len(track) - window + 1), max(1, window // 2))
        for start in starts:
            piece = track[start:start + window]
            if len(piece) < 5 or piece[-1].frame - piece[0].frame < 4:
                continue
            f1 = piece[0].frame
            t = np.array([(c.frame - f1) / fps for c in piece])
            coef_x, _, _ = _robust_polynomial(t, np.array([c.x for c in piece]), 2)
            coef_y, _, _ = _robust_polynomial(t, np.array([c.y for c in piece]), 2)
            consider(f1, coef_x, coef_y)
    # Stage 2: RANSAC fallback for fragmented detections.
    for _ in range(iterations):
        # Guided sampling: flight detections are close in time, so draw the
        # three frames within `step` of each other rather than across the clip.
        f1 = seed_frames[rng.integers(len(seed_frames))]
        step = max(3, int(0.25 * fps))
        later = [f for f in seed_frames if f1 < f <= f1 + step]
        if not later:
            continue
        f2 = later[rng.integers(len(later))]
        latest = [f for f in seed_frames if f2 < f <= f2 + step]
        if not latest:
            continue
        f3 = latest[rng.integers(len(latest))]
        if f3 - f1 < 4:
            continue
        picks = [seed_by_frame[f][rng.integers(len(seed_by_frame[f]))] for f in (f1, f2, f3)]
        t = np.array([(c.frame - f1) / fps for c in picks])
        design = np.column_stack([np.ones(3), t, t * t])
        coef_y = np.linalg.solve(design, [c.y for c in picks]) if abs(np.linalg.det(design)) > 1e-12 else None
        if coef_y is None:
            continue
        coef_x = np.append(np.polyfit(t, [c.x for c in picks], 1)[::-1], 0.0)
        consider(f1, coef_x, coef_y)
    if best is None or best[0] < 4:
        return result
    f_ref, coef_x, coef_y = best[2]
    chosen: dict[int, tuple[Candidate, float]] = {}
    for _ in range(4):   # refine: robust refit on inliers, re-collect, keep the contiguous flight
        chosen = _inliers(by_frame, frames, f_ref, fps, coef_x, coef_y, tol)
        run = _longest_run(sorted(chosen), max_gap=4)
        if len(run) < 4:
            break
        t = np.array([(f - f_ref) / fps for f in run])
        coef_x, _, _ = _robust_polynomial(t, np.array([chosen[f][0].x for f in run]), 2)
        coef_y, _, _ = _robust_polynomial(t, np.array([chosen[f][0].y for f in run]), 2)
        chosen = {f: chosen[f] for f in run}
    chosen = _extend(by_frame, chosen, fps, gate=2.5 * tol, wrist=wrist,
                     in_hand_px=IN_HAND_ARM_LENGTHS * arm_length_px if arm_length_px else None)
    run, coef_x, coef_y = _trim_to_projectile(chosen, f_ref, fps, 3.0 * tol)
    if not run:
        return result
    chosen = {f: chosen[f] for f in run}
    t = np.array([(f - f_ref) / fps for f in run])
    residual = np.hypot(np.array([chosen[f][0].x for f in run]) - _predict(coef_x, coef_y, t)[0],
                        np.array([chosen[f][0].y for f in run]) - _predict(coef_x, coef_y, t)[1])
    span = (run[-1] - run[0]) / fps
    coverage = len(run) / (run[-1] - run[0] + 1)
    reasons = []
    if len(run) < MIN_INLIERS:
        reasons.append(f"Only {len(run)} frames follow the projectile path; {MIN_INLIERS} are needed.")
    if span < MIN_SPAN_SECONDS:
        reasons.append(f"The detected flight lasts {span:.2f} s; at least {MIN_SPAN_SECONDS} s are needed.")
    if coverage < MIN_COVERAGE:
        reasons.append(f"The bag was found in {coverage:.0%} of flight frames; {MIN_COVERAGE:.0%} are needed.")
    if not _plausible(coef_x, coef_y, sign, g_range):
        reasons.append("The refined path is not a plausible throw toward the target for this body scale.")
    travel = sign * (chosen[run[-1]][0].x - chosen[run[0]][0].x)
    if arm_length_px and travel < MIN_TRAVEL_ARM_LENGTHS * arm_length_px:
        reasons.append(f"The path moves only {travel / arm_length_px:.1f} arm lengths toward the target; "
                       f"a throw needs at least {MIN_TRAVEL_ARM_LENGTHS:.0f}.")
    if to_prev is not None:
        residual = _stabilized_residual([chosen[f][0] for f in run], to_prev, fps)
    rms = float(np.sqrt(np.mean(residual**2)))
    rms_limit = MAX_RMS_ARM_LENGTHS * arm_length_px if arm_length_px else 8.0
    if rms > rms_limit:
        reasons.append(f"Detections deviate from one smooth flight by {rms:.1f} px RMS (limit {rms_limit:.1f} px).")
    result.update(
        status="accepted" if not reasons else "needs_review",
        reasons=reasons,
        points=[{"frame": f, "x": chosen[f][0].x, "y": chosen[f][0].y, "area": chosen[f][0].area} for f in run],
        fit={"reference_frame": f_ref, "coef_x": list(map(float, coef_x)), "coef_y": list(map(float, coef_y)),
             "vertical_acceleration_px_s2": float(2 * coef_y[2]), "horizontal_acceleration_px_s2": float(2 * coef_x[2]),
             "rms_residual_px": rms, "rms_coordinates": "first_flight_frame_pixels_camera_motion_removed"
             if to_prev is not None else "raw_video_pixels", "first_frame": run[0], "last_frame": run[-1],
             "span_seconds": span, "coverage": coverage, "inliers": len(run),
             "early_points": [{"frame": f, "x": chosen[f][0].x, "y": chosen[f][0].y} for f in run[:8]]},
    )
    return result


def _stabilized_residual(points: list[Candidate], to_prev: list[np.ndarray], fps: float) -> np.ndarray:
    """Distances from one parabola of detections expressed in the first detection's frame pixels."""
    first = points[0].frame
    m, at = np.eye(3), first
    xs, ys = [], []
    for c in points:                       # compose frame c.frame → first (frames increase)
        while at < c.frame:
            at += 1
            m = m @ np.vstack([to_prev[at], [0, 0, 1]])
        x, y, _ = m @ np.array([c.x, c.y, 1.0])
        xs.append(x)
        ys.append(y)
    t = np.array([(c.frame - first) / fps for c in points])
    xs, ys = np.array(xs), np.array(ys)
    coef_x, _, _ = _robust_polynomial(t, xs, 2)
    coef_y, _, _ = _robust_polynomial(t, ys, 2)
    px, py = _predict(coef_x, coef_y, t)
    return np.hypot(xs - px, ys - py)


def release_from_wrist(fit: dict[str, Any], wrist: np.ndarray, fps: float,
                       search_seconds: float = 0.4) -> tuple[int | None, float | None]:
    """Release = latest frame (up to the first detection) where the backward parabola meets the wrist.

    Before release the bag moves with the hand on a curved swing, so the ballistic
    extrapolation diverges from the wrist; after release the hand falls away.
    The minimum wrist–parabola distance therefore marks separation. Ties go to the
    latest frame, since the hand carries the bag up to the moment it leaves.
    """
    first = int(fit["first_frame"])
    start = max(0, first - int(round(search_seconds * fps)))
    early = fit.get("early_points")  # local fit near release is far more accurate than the whole arc
    if early and len(early) >= 5:
        te = np.array([(q["frame"] - first) / fps for q in early])
        cx = np.polyfit(te, [q["x"] for q in early], 2)
        cy = np.polyfit(te, [q["y"] for q in early], 2)
        predict = lambda f: (np.polyval(cx, (f - first) / fps), np.polyval(cy, (f - first) / fps))
    else:
        predict = lambda f: _predict(fit["coef_x"], fit["coef_y"], (f - fit["reference_frame"]) / fps)
    frames, distances = [], []
    for f in range(start, min(first, len(wrist) - 1) + 1):
        if not np.isfinite(wrist[f]).all():
            continue
        px, py = predict(f)
        frames.append(f)
        distances.append(float(np.hypot(wrist[f][0] - px, wrist[f][1] - py)))
    if not frames:
        return None, None
    d = np.asarray(distances)
    close = np.flatnonzero(d <= d.min() + 2.0)
    i = int(close[-1])
    return frames[i], float(d[i])


# ---------------------------------------------------------------- orchestration
def find_flights(candidates: list[Candidate], fps: float, target_direction: str,
                 arm_length_px: float | None, wrist: np.ndarray | None = None, max_flights: int = 8,
                 to_prev: list[np.ndarray] | None = None) -> list[dict[str, Any]]:
    """All projectile flights in a clip (a clip may contain several throws), in time order."""
    remaining = list(candidates)
    flights: list[dict[str, Any]] = []
    for _ in range(max_flights):
        found = find_flight(remaining, fps, target_direction, arm_length_px=arm_length_px, wrist=wrist,
                            to_prev=to_prev)
        if found["fit"] is None or found["fit"]["inliers"] < 6:
            break
        flights.append(found)
        used = {(p["frame"], round(p["x"], 3), round(p["y"], 3)) for p in found["points"]}
        first, last = found["fit"]["first_frame"], found["fit"]["last_frame"]
        # Drop this flight's detections and anything else in its time span that lies on it.
        remaining = [c for c in remaining if (c.frame, round(c.x, 3), round(c.y, 3)) not in used
                     and not (first <= c.frame <= last and _near_path(found["fit"], c, fps))]
        if found["status"] != "accepted":
            continue
    return sorted(flights, key=lambda r: r["fit"]["first_frame"])


def _near_path(fit, c, fps, tol=12.0):
    px, py = _predict(fit["coef_x"], fit["coef_y"], (c.frame - fit["reference_frame"]) / fps)
    return np.hypot(c.x - px, c.y - py) < tol


def camera_motion_px(to_prev: list[np.ndarray], first: int, last: int, point: tuple[float, float]) -> float:
    """Largest displacement of a scene point between `first` and any frame up to `last`."""
    x, y = point
    worst = 0.0
    M = np.eye(3)
    for t in range(first + 1, min(last, len(to_prev) - 1) + 1):
        # to_prev[t] maps t → t−1; its inverse moves a first-frame point forward in time.
        M = np.linalg.inv(np.vstack([to_prev[t], [0, 0, 1]])) @ M
        nx, ny, _ = M @ np.array([x, y, 1.0])
        worst = max(worst, float(np.hypot(nx - x, ny - y)))
    return worst


def _scene_and_board(frames, chain, target_direction, masks, board_corners_px=None, cache_dir=None):
    """Background plate + board in release-frame pixels (the reference of `chain`).

    Returns (scene_info, board) where board carries `model` (BoardModel) only when
    the board was found (or corners were clicked); `not_found` may still carry
    best-guess corners, which are never used.
    """
    plate = build_plate(frames, chain, person_masks=masks or None)
    if cache_dir is not None:   # kept for `set-board-corners --apply-to` (plate-to-plate corner transfer)
        cv2.imwrite(str(Path(cache_dir) / "plate.jpg"), plate["plate"])
    height, width = frames[0].shape[:2]
    scene_info = {"plate_samples": plate["samples"]}
    if board_corners_px is not None:
        found = {"status": "found", "corners_px": board_corners_px, "confidence": 1.0, "hole_offset_in": None,
                 "reasons": ["clicked corners"]}
    else:
        found = detect_board(plate["plate"], target_direction)
    if found["status"] != "found":
        return scene_info, {**found, "model": None}
    try:
        model = solve_board(np.asarray(found["corners_px"], float), (width, height))
    except ValueError as exc:
        return scene_info, {**found, "status": "not_found", "reasons": [*found.get("reasons", []), str(exc)],
                            "model": None}
    return scene_info, {**found, "model": model}


def _contact_from_board(board, end_point_ref, fit, fps, last_frame, frame_count, chain):
    """Observed contact only when the flight ends at the deck/front/floor; otherwise predicted.

    `end_point_ref` is the last tracked point in the board model's (release-frame)
    pixels; `fit` is in raw video pixels, so predictions go through `chain`.
    """
    if board.get("model") is None:
        return {"first_contact_frame": None, "predicted_contact": None,
                "contact": {"kind": "unknown", "state": "unavailable", "plane_xy_m": None,
                            "reason": "Board not located, so contact cannot be checked against the deck or floor."}}
    model = board["model"]
    end = classify_flight_end(end_point_ref, model)
    if end["kind"] != "lost_in_flight":
        return {"first_contact_frame": last_frame, "predicted_contact": None,
                "contact": {"kind": end["kind"], "state": "measured", "plane_xy_m": end["plane_xy_m"], "reason": None}}
    to_ref = lambda f, p: (chain[f] @ np.array([p[0], p[1], 1.0]))[:2] if f in chain else np.asarray(p, float)
    predicted = predict_contact(fit["coef_x"], fit["coef_y"], fit["reference_frame"], fps, last_frame, frame_count,
                                to_ref, model)
    t_last = (last_frame - fit["reference_frame"]) / fps
    descending = fit["coef_y"][1] + 2 * fit["coef_y"][2] * t_last > 0          # image y grows downward
    if predicted is not None and descending and predicted["frame"] - last_frame <= NEAR_CONTACT_FRAMES:
        gap = predicted["frame"] - last_frame
        return {"first_contact_frame": last_frame, "predicted_contact": None,
                "contact": {"kind": predicted["kind"], "state": "measured", "plane_xy_m": end["plane_xy_m"],
                            "reason": f"Descending track ended within {gap} frame(s) of the predicted "
                                      f"{predicted['kind']} contact."}}
    return {"first_contact_frame": None, "predicted_contact": predicted,
            "contact": {"kind": "lost_in_flight", "state": "unavailable", "plane_xy_m": end["plane_xy_m"],
                        "reason": "The bag was lost while still in the air; first contact was not observed."}}


def _no_board_fallback(decided, fit, fps, last, contact, width, height) -> tuple[bool, str | None]:
    """No board: the previous geometric rule (descending, away from the image edge), labelled unverified.

    Mutates `decided`. Returns (contact_known, warning for the top-level reasons or None).
    """
    t_last = (contact - fit["reference_frame"]) / fps
    descending = fit["coef_y"][1] + 2 * fit["coef_y"][2] * t_last > 0          # image y grows downward
    at_edge = min(last["x"], width - last["x"], last["y"], height - last["y"]) < 0.02 * width
    rule = (" Using the older end-of-track rule (last tracked frame of a descending flight away from the image "
            "edge), unverified.")
    decided["contact"]["reason"] += rule
    if not (descending and not at_edge):
        return False, None
    decided["first_contact_frame"] = contact
    decided["contact"]["state"] = "unverified"
    return True, (f"First contact (frame {contact}) was taken as the end of the tracked flight: the board was not "
                  "located, so it is unverified against the deck or floor. Confirm it in Flight & scale.")


def auto_track_bag(video_path: str, wrist: np.ndarray | None, arm_length_px: float | None,
                   target_direction: str, preferred_release: int | None = None,
                   cache_dir: Path | None = None, board_corners_px: list | None = None) -> dict[str, Any]:
    """Detect every flight in a clip and pick the one for this trial.

    `points` are raw video pixels, the same system as the pose landmarks, manual
    bag corrections and the video on screen. `stabilized_points` hold the same
    detections in the release frame's pixels with camera motion removed, and
    `camera_to_release` stores the per-frame 2×3 transforms that produce them,
    so launch fits and the gravity scale can behave as if the camera were fixed.
    (Revision 8 stored only stabilized points; drawn over a hand-held video they
    drifted off the bag by the camera motion, up to ~50 px in the pilot clips.)

    With `cache_dir`, person masks are computed/cached there (scene.py) and the
    background plate is written as `plate.jpg`. `board_corners_px` (clicked deck
    corners in release-frame pixels) bypass board detection. `board`, `landing`
    and `predicted_contact` are in release-frame pixels.
    """
    started = time.perf_counter()
    frames, fps = read_frames(video_path)
    if len(frames) < 5:
        return {"status": "not_found", "revision": AUTO_BAG_REVISION, "reasons": ["The clip is too short."], "flights": []}
    candidates, to_prev = detect_moving_blobs_in_frames(frames)
    from .scene import person_masks, tag_people   # scene imports Candidate from here
    height, width = frames[0].shape[:2]
    masks_info = (person_masks(video_path, cache_dir, (width, height)) if cache_dir is not None
                  else {"status": "unavailable", "reason": "No cache directory for person masks.", "masks": {}})
    candidates = tag_people(candidates, masks_info["masks"])
    flights = find_flights(candidates, fps, target_direction, arm_length_px, wrist, to_prev=to_prev)
    summary = [{"status": f["status"], "first_frame": f["fit"]["first_frame"], "last_frame": f["fit"]["last_frame"],
                "inliers": f["fit"]["inliers"], "reasons": f["reasons"]} for f in flights]
    accepted = [f for f in flights if f["status"] == "accepted"]
    pool = accepted or flights
    if not pool:
        return {"status": "not_found", "revision": AUTO_BAG_REVISION, "fps": fps, "flights": summary,
                "reasons": ["No moving object followed a plausible projectile path. Check that the bag stays in view."]}
    def gap_to_wrist(f: dict[str, Any]) -> float:
        start = f["points"][0]
        w = wrist[start["frame"]] if wrist is not None and start["frame"] < len(wrist) else None
        return float(np.hypot(start["x"] - w[0], start["y"] - w[1])) if w is not None and np.isfinite(w).all() else np.inf
    if preferred_release is not None:
        chosen = min(pool, key=lambda f: abs(f["fit"]["first_frame"] - preferred_release))
    else:
        # The trial's throw is the flight that starts at this athlete's throwing hand.
        chosen = min(pool, key=lambda f: (gap_to_wrist(f), f["fit"]["first_frame"]))
    fit = chosen["fit"]
    release, contact = int(fit["first_frame"]), int(fit["last_frame"])
    last = next(p for p in chosen["points"] if p["frame"] == contact)
    chain = reference_chain(to_prev, release)
    scene_info, board = _scene_and_board(frames, chain, target_direction, masks_info["masks"], board_corners_px,
                                         cache_dir)
    end_ref = (chain[contact] @ np.array([last["x"], last["y"], 1.0]))[:2]
    decided = _contact_from_board(board, end_ref, fit, fps, contact, len(frames), chain)
    fallback_warning = None
    if board.get("model") is None:
        contact_known, fallback_warning = _no_board_fallback(decided, fit, fps, last, contact, width, height)
    else:
        contact_known = decided["first_contact_frame"] is not None
    # Detection blobs mark where the bag differs most from the background, not its
    # centre; a local background mask gives the silhouette centroid (bag_segment.py).
    refined = {r["frame"]: r for r in refine_flight(frames, chain, chosen["points"])}
    raw = [Candidate(f, refined[f]["x"], refined[f]["y"], refined[f].get("area_px") or 0.0) for f in sorted(refined)]
    stabilized = to_reference(raw, to_prev, release)
    # Transforms for every frame of the clip: fits use the flight frames; the replay
    # uses the rest to draw the whole throw on a moving (hand-held) picture.
    camera_to_release = {str(f): np.round(chain[f][:2], 6).tolist() for f in range(len(frames))}
    areas = [r["area_px"] for r in refined.values() if r.get("area_px")]
    typical_area = float(np.median(areas)) if areas else None
    after_contact = None
    if contact_known and contact in refined:
        before = [f for f in sorted(refined) if f < contact][-3:]
        v0 = ((refined[contact]["x"] - refined[before[0]]["x"]) / (contact - before[0]),
              (refined[contact]["y"] - refined[before[0]]["y"]) / (contact - before[0])) if before else (0.0, 0.0)
        after_contact = track_after_contact(frames, chain, contact, (refined[contact]["x"], refined[contact]["y"]),
                                            release, fps, typical_area, v0,
                                            flight={f: (r["x"], r["y"]) for f, r in refined.items()})
    # Second, independent release cue: where the flight traced backwards meets the
    # wrist (geometry of bag path vs hand), versus the first free-flight detection.
    release_check = None
    if wrist is not None:
        early = [{"frame": c.frame, "x": c.x, "y": c.y} for c in raw[:8]]
        cue_frame, cue_distance = release_from_wrist({**fit, "first_frame": release, "early_points": early}, wrist, fps)
        if cue_frame is not None:
            release_check = {"method": "backward_flight_meets_wrist", "frame": int(cue_frame),
                             "wrist_distance_px": cue_distance, "difference_frames": int(release - cue_frame),
                             "agrees_within_2_frames": abs(release - cue_frame) <= 2}
    motion = camera_motion_px(to_prev, release, contact, (raw[0].x, raw[0].y))
    wrist_gap = None
    if wrist is not None and release < len(wrist) and np.isfinite(wrist[release]).all():
        wrist_gap = float(np.hypot(raw[0].x - wrist[release][0], raw[0].y - wrist[release][1]))
    reasons = list(chosen["reasons"])
    status = chosen["status"]
    if (wrist_gap is not None and arm_length_px and wrist_gap > RELEASE_AT_HAND_ARM_LENGTHS * arm_length_px):
        status = "needs_review"
        reasons.append(f"The detected flight starts {wrist_gap / arm_length_px:.1f} arm lengths from the wrist; a throw "
                       "leaves from the hand, so the start of the flight was probably missed.")
    if fallback_warning:
        reasons.append(fallback_warning)
    if not contact_known:
        predicted = decided["predicted_contact"]
        reasons.append(decided["contact"]["reason"] + " Flight time is unknown"
                       + (f"; contact is estimated at frame {predicted['frame']} ({predicted['kind']})" if predicted else "")
                       + ". Mark contact in Flight & scale if it is visible.")
    landing = suggested = None
    if board.get("model") is not None:
        model = board["model"]
        if contact_known and contact in refined:
            p = chain[contact] @ np.array([refined[contact]["x"], refined[contact]["y"], 1.0])
            landing = {**landing_summary(p[:2], model), "state": "measured"}
        elif decided["predicted_contact"] is not None:
            pc = decided["predicted_contact"]
            landing = {**landing_summary((pc["x_px"], pc["y_px"]), model), "state": "estimated",
                       "reason": pc["reason"]}
        suggested = suggest_outcome(after_contact, model)
    board_payload = {k: v for k, v in board.items() if k != "model"}
    if board.get("model") is not None:
        board_payload.update(board["model"].as_dict())
    if len(accepted) > 1:
        reasons.append(f"{len(accepted)} flights were found in this clip; the one starting at the throwing hand was used.")
    return {
        "status": status, "revision": AUTO_BAG_REVISION, "fps": fps, "reasons": reasons,
        "release_frame": release, "first_contact_frame": contact if contact_known else None,
        "last_tracked_frame": contact,
        "contact": decided["contact"], "predicted_contact": decided["predicted_contact"],
        "board": board_payload, "landing": landing, "suggested_outcome": suggested,
        "scene": {"masks_status": masks_info["status"], "masks_reason": masks_info.get("reason"),
                  "masks_empty_frames": masks_info.get("empty_frames"),
                  "plate_samples": scene_info["plate_samples"]},
        "width": width, "height": height,
        "event_precision_frames": 1,
        "release_wrist_distance_px": wrist_gap,
        "camera_motion_during_flight_px": motion,
        "coordinates": "raw_video_pixels",
        "points": [{"frame": c.frame, "x": c.x, "y": c.y, "source": refined[c.frame]["source"],
                    "area_px": refined[c.frame].get("area_px"), "orientation_deg": refined[c.frame].get("orientation_deg"),
                    "detection_x": refined[c.frame]["detection_x"], "detection_y": refined[c.frame]["detection_y"]}
                   for c in raw],
        "centroid_method": SEGMENT_REVISION,
        "centroid_sources": {src: sum(1 for r in refined.values() if r["source"] == src)
                             for src in ("mask", "detection", "reacquired_mask")},
        "stabilized_coordinates": "release_frame_pixels_camera_motion_removed",
        "stabilized_points": [{"frame": c.frame, "x": c.x, "y": c.y} for c in stabilized],
        "camera_to_release": camera_to_release,
        "after_contact": after_contact,
        "release_check": release_check,
        "typical_bag_area_px": typical_area,
        "runtime_seconds": time.perf_counter() - started,
        "frames_processed": len(frames),
        "fit": {k: v for k, v in fit.items() if k != "early_points"},
        "flights": summary,
    }
