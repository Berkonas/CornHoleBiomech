"""Automatic bag flight detection: motion candidates + projectile-constrained selection.

Method (classical sports-ball tracking, cf. TrackNetV3's background-subtraction
and trajectory-rectification stages, without a trained network):

1. Candidates: camera-compensated three-frame differencing. Each frame is
   compared with its neighbours after aligning them with a feature-based
   similarity transform (ORB + RANSAC), so hand-held drift is not "motion".
2. Selection: RANSAC over candidates from different frames for a free-flight
   path x(t) ≈ linear, y(t) = quadratic with downward (image +y) curvature,
   moving toward the target. The fitted image gravity must be plausible for the
   athlete's scale (projected arm length ≈ 0.45–0.9 m), which rejects clutter.
3. Events: release is where the fitted parabola, traced backwards, meets the
   throwing wrist; first contact is the first frame after the last
   parabola-consistent detection.
4. Acceptance: enough inliers over enough of the flight with small residuals.
   Otherwise the result is "needs_review" with the reason, never silently used.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import cv2
import numpy as np

from .bag import GRAVITY_M_S2, _robust_polynomial

AUTO_BAG_REVISION = "auto_motion_parabola_v1"
ARM_LENGTH_RANGE_M = (0.45, 0.90)   # projected shoulder–wrist length; generous for foreshortening
MIN_INLIERS = 12
MIN_SPAN_SECONDS = 0.25
MIN_COVERAGE = 0.6
IN_HAND_ARM_LENGTHS = 0.3   # bag within this distance of the wrist is treated as held
MAX_RMS_ARM_LENGTHS = 0.08  # whole-flight parabola residual limit (drag/perspective allowance)


@dataclass(frozen=True)
class Candidate:
    frame: int
    x: float        # full-resolution pixels, x right
    y: float        # full-resolution pixels, y down
    area: float


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
                                  min_area: int = 3, max_area: int = 400
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
    to_prev = [np.float32([[1, 0, 0], [0, 1, 0]])]
    for t in range(1, len(gray)):
        to_prev.append(_similarity(orb, matcher, features[t], features[t - 1]))
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
        for i in range(1, count):
            area = int(stats[i, cv2.CC_STAT_AREA])
            if min_area <= area <= max_area:
                candidates.append(Candidate(t, float(centroids[i][0] / scale), float(centroids[i][1] / scale), area / scale**2))
    full = []
    for M in to_prev:   # rescale translation to full resolution
        F = M.copy()
        F[:, 2] /= scale
        full.append(F)
    return candidates, full


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


def to_reference(candidates: list[Candidate], to_prev: list[np.ndarray], reference: int) -> list[Candidate]:
    """Express every candidate in the pixel frame of `reference` using chained transforms."""
    n = len(to_prev)
    chain: dict[int, np.ndarray] = {reference: np.eye(3)}
    for t in range(reference + 1, n):      # t → t−1 → … → reference
        chain[t] = chain[t - 1] @ np.vstack([to_prev[t], [0, 0, 1]])
    for t in range(reference - 1, -1, -1):  # t → t+1 → … → reference
        chain[t] = chain[t + 1] @ np.linalg.inv(np.vstack([to_prev[t + 1], [0, 0, 1]]))
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
                wrist: np.ndarray | None = None) -> dict[str, Any]:
    """Choose the candidate subset that behaves like a thrown bag (see module docstring)."""
    sign = 1.0 if target_direction == "left_to_right" else -1.0
    g_range = _gravity_range(arm_length_px)
    tol = max(6.0, 0.05 * arm_length_px) if arm_length_px else 8.0
    by_frame: dict[int, list[Candidate]] = {}
    for c in candidates:
        by_frame.setdefault(c.frame, []).append(c)
    frames = sorted(by_frame)
    result: dict[str, Any] = {"status": "not_found", "revision": AUTO_BAG_REVISION, "points": [], "fit": None,
                              "reasons": ["No moving object followed a plausible projectile path."],
                              "gravity_range_px_s2": list(g_range), "tolerance_px": tol}
    if len(frames) < 3:
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
    for track in build_tracklets(candidates, gate_px=2 * tol, first_step_px=first_step):
        f1 = track[0].frame
        t = np.array([(c.frame - f1) / fps for c in track])
        if t[-1] - t[0] < 4 / fps:
            continue
        coef_x, _, _ = _robust_polynomial(t, np.array([c.x for c in track]), 2)
        coef_y, _, _ = _robust_polynomial(t, np.array([c.y for c in track]), 2)
        consider(f1, coef_x, coef_y)
    # Stage 2: RANSAC fallback for fragmented detections.
    for _ in range(iterations):
        # Guided sampling: flight detections are close in time, so draw the
        # three frames within `step` of each other rather than across the clip.
        f1 = frames[rng.integers(len(frames))]
        step = max(3, int(0.25 * fps))
        later = [f for f in frames if f1 < f <= f1 + step]
        if not later:
            continue
        f2 = later[rng.integers(len(later))]
        latest = [f for f in frames if f2 < f <= f2 + step]
        if not latest:
            continue
        f3 = latest[rng.integers(len(latest))]
        if f3 - f1 < 4:
            continue
        picks = [by_frame[f][rng.integers(len(by_frame[f]))] for f in (f1, f2, f3)]
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
    run = sorted(chosen)
    if not run:
        return result
    t = np.array([(f - f_ref) / fps for f in run])
    coef_x, _, _ = _robust_polynomial(t, np.array([chosen[f][0].x for f in run]), 2)
    coef_y, _, _ = _robust_polynomial(t, np.array([chosen[f][0].y for f in run]), 2)
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
             "rms_residual_px": float(np.sqrt(np.mean(residual**2))), "first_frame": run[0], "last_frame": run[-1],
             "span_seconds": span, "coverage": coverage, "inliers": len(run),
             "early_points": [{"frame": f, "x": chosen[f][0].x, "y": chosen[f][0].y} for f in run[:8]]},
    )
    return result


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
                 arm_length_px: float | None, wrist: np.ndarray | None = None, max_flights: int = 8) -> list[dict[str, Any]]:
    """All projectile flights in a clip (a clip may contain several throws), in time order."""
    remaining = list(candidates)
    flights: list[dict[str, Any]] = []
    for _ in range(max_flights):
        found = find_flight(remaining, fps, target_direction, arm_length_px=arm_length_px, wrist=wrist)
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


def auto_track_bag(video_path: str, wrist: np.ndarray | None, arm_length_px: float | None,
                   target_direction: str, preferred_release: int | None = None) -> dict[str, Any]:
    """Detect every flight in a clip and pick the one for this trial.

    Coordinates of the chosen flight are expressed in the release frame's pixels
    (camera motion removed), so launch fits and the gravity scale behave as if
    the camera were fixed; at the release frame they equal raw pixels, keeping
    release position consistent with the pose landmarks.
    """
    frames, fps = read_frames(video_path)
    if len(frames) < 5:
        return {"status": "not_found", "revision": AUTO_BAG_REVISION, "reasons": ["The clip is too short."], "flights": []}
    candidates, to_prev = detect_moving_blobs_in_frames(frames)
    flights = find_flights(candidates, fps, target_direction, arm_length_px, wrist)
    summary = [{"status": f["status"], "first_frame": f["fit"]["first_frame"], "last_frame": f["fit"]["last_frame"],
                "inliers": f["fit"]["inliers"], "reasons": f["reasons"]} for f in flights]
    accepted = [f for f in flights if f["status"] == "accepted"]
    pool = accepted or flights
    if not pool:
        return {"status": "not_found", "revision": AUTO_BAG_REVISION, "fps": fps, "flights": summary,
                "reasons": ["No moving object followed a plausible projectile path. Check that the bag stays in view."]}
    if preferred_release is not None:
        chosen = min(pool, key=lambda f: abs(f["fit"]["first_frame"] - preferred_release))
    else:
        chosen = pool[0]
    fit = chosen["fit"]
    release, contact = int(fit["first_frame"]), int(fit["last_frame"])
    ids = {p["frame"]: p for p in chosen["points"]}
    raw = [Candidate(f, ids[f]["x"], ids[f]["y"], ids[f]["area"]) for f in sorted(ids)]
    stabilized = to_reference(raw, to_prev, release)
    motion = camera_motion_px(to_prev, release, contact, (raw[0].x, raw[0].y))
    wrist_gap = None
    if wrist is not None and release < len(wrist) and np.isfinite(wrist[release]).all():
        wrist_gap = float(np.hypot(raw[0].x - wrist[release][0], raw[0].y - wrist[release][1]))
    reasons = list(chosen["reasons"])
    if len(accepted) > 1:
        reasons.append(f"{len(accepted)} throws were found in this clip; the one nearest the wrist-speed release was used.")
    return {
        "status": chosen["status"], "revision": AUTO_BAG_REVISION, "fps": fps, "reasons": reasons,
        "release_frame": release, "first_contact_frame": contact,
        "event_precision_frames": 1,
        "release_wrist_distance_px": wrist_gap,
        "camera_motion_during_flight_px": motion,
        "coordinates": "release_frame_pixels_camera_motion_removed",
        "points": [{"frame": c.frame, "x": c.x, "y": c.y} for c in stabilized],
        "fit": {k: v for k, v in fit.items() if k != "early_points"},
        "flights": summary,
    }
