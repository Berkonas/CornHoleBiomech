"""Front camera: the camera on a tripod behind the board, looking back along the throw line at the athlete.

It sees what the side camera cannot: **left/right**. From it the engine measures

* the deck (four corners) and therefore a deck homography: any point on the deck in board inches;
* where the bag first touched and where it came to rest **across** the board (x, 0–24 in), and whether
  it went through the hole, stayed on the deck or ended off the board;
* the bag's sideways path in flight, and from it the **heading** (left/right aim) of the throw;
* frontal-plane body measures from pose (trunk side lean, shoulder tilt, arm path across the body,
  where the athlete stands and steps relative to the board's centre line).

Board coordinates follow the app: x 0–24 in left→right *as seen by the thrower*, y 0–48 in from the
front (thrower) edge to the back edge, hole centre (12, 39). The front camera faces the thrower, so the
thrower's left appears on the right of its image: front-left (0, 0) is the far-right deck corner in the
image, back-left (0, 48) the near-right one. Signed lateral values are reported in the thrower's frame:
negative = to the thrower's left, positive = to the thrower's right.

Methods and thresholds: docs/METHODS_AND_MATH.md §5.2 ("Front camera").
"""
from __future__ import annotations

import math
from typing import Any, Sequence

import cv2
import numpy as np

from .regulation import INCH_M, Board

DECK_W_IN, DECK_L_IN = 24.0, 48.0
HOLE_X_IN, HOLE_Y_IN, HOLE_R_IN = 12.0, 39.0, 3.0
# Image corner order used everywhere below: thrower's front-left, front-right, back-right, back-left.
DECK_CORNERS_IN = np.array([[0.0, 0.0], [24.0, 0.0], [24.0, 48.0], [0.0, 48.0]])

RED_HUE_LOW, RED_HUE_HIGH = 12, 150      # red = hue <= 12 or >= 150 (OpenCV 0–180)
RED_MIN_SAT, RED_MIN_VAL = 25, 60        # the Final Data Collection deck: S 30–60 under hall lighting
DARK_MAX_VAL = 75                        # black end apron: V 25–45
MIN_APRON_WIDTH_FRACTION = 0.06          # of the image width (Final Data Collection: 0.15–0.17)
MIN_APRON_ASPECT = 2.5
HOLE_SEARCH_TOLERANCE_IN = 4.0
MAX_SIDE_LINE_RMS_PX = 3.0
FLOOR_B_STEP = 2.5                       # CIELAB b* units below the floor beside the deck (deck 3–6 below)


# ------------------------------------------------------------------------------------------------
# Geometry helpers


def deck_homography(corners_px: np.ndarray) -> np.ndarray:
    """Image → deck inches. ``corners_px`` in the order front-left, front-right, back-right, back-left (thrower's view)."""
    return cv2.getPerspectiveTransform(np.asarray(corners_px, np.float32).reshape(4, 2),
                                       DECK_CORNERS_IN.astype(np.float32))


def to_deck(H: np.ndarray, points_px: np.ndarray) -> np.ndarray:
    pts = np.asarray(points_px, float).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(pts, np.asarray(H, float)).reshape(-1, 2)


def to_image(H: np.ndarray, points_in: np.ndarray) -> np.ndarray:
    pts = np.asarray(points_in, float).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(pts, np.linalg.inv(np.asarray(H, float))).reshape(-1, 2)


def lateral_precision_in_per_px(H: np.ndarray, point_in: Sequence[float]) -> dict[str, float]:
    """How many board inches one image pixel is worth at a deck point, across (x) and along (y) the board."""
    c = to_image(H, np.array([point_in]))[0]
    dx = to_deck(H, np.array([c + [0.5, 0], c - [0.5, 0]]))
    dy = to_deck(H, np.array([c + [0, 0.5], c - [0, 0.5]]))
    return {"across_in_per_px": float(max(abs(dx[0, 0] - dx[1, 0]), abs(dy[0, 0] - dy[1, 0]))),
            "along_in_per_px": float(max(abs(dx[0, 1] - dx[1, 1]), abs(dy[0, 1] - dy[1, 1])))}


def _fit_line(xs: np.ndarray, ys: np.ndarray, iterations: int = 200, tol: float = 2.0, seed: int = 0
              ) -> tuple[np.ndarray, float] | None:
    """Robust line (a, b, c) with a x + b y + c = 0, |(a, b)| = 1, by RANSAC + least squares on inliers."""
    pts = np.column_stack([xs, ys]).astype(float)
    if len(pts) < 5:
        return None
    rng = np.random.default_rng(seed)
    best = None
    for _ in range(iterations):
        i, j = rng.choice(len(pts), 2, replace=False)
        d = pts[j] - pts[i]
        n = np.array([-d[1], d[0]])
        norm = np.linalg.norm(n)
        if norm < 1e-9:
            continue
        n /= norm
        c = -n @ pts[i]
        inliers = np.abs(pts @ n + c) < tol
        if best is None or inliers.sum() > best.sum():
            best = inliers
    if best is None or best.sum() < 5:
        return None
    sel = pts[best]
    mean = sel.mean(axis=0)
    _, _, vt = np.linalg.svd(sel - mean)
    direction = vt[0]
    n = np.array([-direction[1], direction[0]])
    c = -n @ mean
    rms = float(np.sqrt(np.mean((sel @ n + c) ** 2)))
    return np.array([n[0], n[1], c]), rms


def _intersect(l1: np.ndarray, l2: np.ndarray) -> np.ndarray | None:
    p = np.cross(l1, l2)
    if abs(p[2]) < 1e-9:
        return None
    return p[:2] / p[2]


# ------------------------------------------------------------------------------------------------
# Board detection


def plate_from_frames(frames: Sequence[np.ndarray]) -> np.ndarray:
    """Per-pixel median of a handful of frames: moving people and flying bags disappear."""
    return np.median(np.stack(frames), axis=0).astype(np.uint8)


def read_plate(video_path: str, start_s: float = 0.0, span_s: float = 1.5, count: int = 9) -> np.ndarray:
    capture = cv2.VideoCapture(str(video_path))
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    wanted = sorted({min(total - 1, int(round((start_s + span_s * k / max(1, count - 1)) * fps))) for k in range(count)})
    frames, index = [], 0
    try:
        while wanted and index <= wanted[-1]:
            ok, frame = capture.read()
            if not ok:
                break
            if index in wanted:
                frames.append(frame)
            index += 1
    finally:
        capture.release()
    if not frames:
        raise ValueError(f"Could not read frames from {video_path}")
    return plate_from_frames(frames)


def detect_front_board(plate: np.ndarray) -> dict[str, Any]:
    """Find the deck in a front-camera plate.

    1. The board's black end apron (the end nearest the camera) is the widest dark, wide-and-short
       component in the lower two thirds of the image; its top edge is the deck's back edge.
    2. The deck's red paint lies above it. The outer boundary of the red region on each side gives the
       two side edges (robust line fits); the top of the red region next to each side edge gives the
       front (far) edge.
    3. The four edge lines intersect in the four corners. The detection is accepted when the deck is
       wider at the back than at the front (perspective), the side lines fit within 3 px RMS, and a dark
       hole is found within 4 in of (12, 39) in.
    """
    h, w = plate.shape[:2]
    hsv = cv2.cvtColor(plate, cv2.COLOR_BGR2HSV)
    H, S, V = (hsv[..., i].astype(int) for i in range(3))
    red = (((H >= RED_HUE_HIGH) | (H <= RED_HUE_LOW)) & (S >= RED_MIN_SAT) & (V >= RED_MIN_VAL)).astype(np.uint8)
    red = cv2.morphologyEx(red, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))     # isolated reddish floor speckle out
    dark = (V < DARK_MAX_VAL).astype(np.uint8)
    dark[: h // 3] = 0
    dark = cv2.morphologyEx(dark, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(dark, 8)
    candidates = []
    for k in range(1, count):
        x, y, bw, bh, area = stats[k]
        if bw < MIN_APRON_WIDTH_FRACTION * w or bw / max(1, bh) < MIN_APRON_ASPECT * 0.5:
            continue
        # Red deck paint must sit directly above it.
        band = red[max(0, y - max(6, bh)): y, x: x + bw]
        red_share = float(band.mean()) if band.size else 0.0
        candidates.append((bw * (0.2 + red_share), k, x, y, bw, bh, red_share))
    if not candidates:
        return {"status": "not_found", "reason": "No dark end apron with red paint above it was found."}
    failures = []
    for candidate in sorted(candidates, reverse=True)[:4]:
        found = _deck_from_apron(plate, red, labels, candidate, h, w)
        if found["status"] == "found":
            return found
        failures.append(found)
    return failures[0]


def _deck_from_apron(plate: np.ndarray, red: np.ndarray, labels: np.ndarray, best: tuple, h: int, w: int
                     ) -> dict[str, Any]:
    _, k, ax, ay, aw, ah, red_share = best
    comp = labels == k
    cols = np.arange(ax, ax + aw)
    tops = np.array([np.argmax(comp[:, c]) if comp[:, c].any() else -1 for c in cols])
    keep = tops >= 0
    inner = (cols > ax + 0.1 * aw) & (cols < ax + 0.9 * aw) & keep
    back = _fit_line(cols[inner].astype(float), tops[inner].astype(float), tol=1.5)
    if back is None:
        return {"status": "not_found", "reason": "The top edge of the end apron could not be fitted."}
    back_line, back_rms = back
    # Deck rows: from well above the apron down to the back edge. The deck is at most ~1.2 apron widths
    # tall in this view (grazing angle), so search up to that height.
    y_back = int(np.median(tops[inner]))
    y_top_search = max(0, y_back - int(1.2 * aw))
    # Only red paint connected to the apron's top edge belongs to the deck (a red bag in the athlete's
    # hand or a red sign higher up does not).
    grown = cv2.dilate(red, np.ones((5, 5), np.uint8))
    n_red, red_labels = cv2.connectedComponents(grown, connectivity=8)
    band = red_labels[max(0, y_back - 4): y_back + 1, ax: ax + aw]
    touching = [lab for lab in np.unique(band) if lab != 0]
    deck_red = (np.isin(red_labels, touching) & (red > 0)).astype(np.uint8) if touching else np.zeros_like(red)
    deck_red[y_back + 1:] = 0
    red = deck_red
    region = red[y_top_search: y_back, max(0, ax - aw // 3): min(w, ax + aw + aw // 3)]
    x_off = max(0, ax - aw // 3)
    rows = np.arange(region.shape[0])
    lefts, rights, ys = [], [], []
    for r in rows:
        on = np.flatnonzero(region[r])
        if len(on) < 3:
            continue
        lefts.append(on[0] + x_off)
        rights.append(on[-1] + x_off)
        ys.append(r + y_top_search)
    if len(ys) < 8:
        return {"status": "not_found", "reason": "Too little red deck paint above the apron."}
    ys_a, lefts_a, rights_a = np.array(ys, float), np.array(lefts, float), np.array(rights, float)
    # Side lines: x as a function of y (near-vertical), fitted as general lines.
    left_fit = _fit_line(lefts_a, ys_a, tol=2.0, seed=1)
    right_fit = _fit_line(rights_a, ys_a, tol=2.0, seed=2)
    if left_fit is None or right_fit is None:
        return {"status": "not_found", "reason": "The deck's side edges could not be fitted."}
    (left_line, left_rms), (right_line, right_rms) = left_fit, right_fit
    # Front (far) edge. Candidate lines parallel to the back edge are scored by the mean vertical colour
    # gradient along them, between the two side edges (CIELAB, all three channels). The deck's far edge
    # is the only straight boundary that spans the whole deck width (the white stripes run diagonally and
    # the centre graphic covers only the middle third). The best three candidates are kept; the hole
    # check below chooses among them.
    lab = cv2.GaussianBlur(cv2.cvtColor(plate, cv2.COLOR_BGR2LAB).astype(np.float32), (3, 3), 0)
    grad = np.sqrt(sum(cv2.Sobel(lab[..., i], cv2.CV_32F, 0, 1, ksize=3) ** 2 for i in range(3)))
    y_first = int(ys_a.min())
    a_b, b_b, c_b = back_line
    slope = -a_b / b_b if abs(b_b) > 1e-9 else 0.0          # dy/dx of the back edge
    x_mid = (_x_at(left_line, y_back) + _x_at(right_line, y_back)) / 2 if _x_at(left_line, y_back) is not None else ax + aw / 2
    lo = max(0, y_back - int(1.2 * aw))
    hi = y_back - 4
    scores = []
    for y0 in range(lo, hi):
        xl, xr = _x_at(left_line, y0), _x_at(right_line, y0)
        if xl is None or xr is None or xr - xl < 10:
            continue
        xs = np.linspace(xl + 0.1 * (xr - xl), xr - 0.1 * (xr - xl), 40)
        ys = y0 + slope * (xs - x_mid)
        inside = (ys >= 1) & (ys < h - 1) & (xs >= 0) & (xs < w)
        if inside.sum() < 30:
            continue
        g = grad[ys[inside].round().astype(int), xs[inside].round().astype(int)]
        # Reward a boundary that is strong everywhere along the line, not just in a few places.
        scores.append((float(np.median(g)) + 0.5 * float(np.mean(g)), y0))
    # Local maxima of the score that stand out (above the 70th percentile) are candidate far edges; the
    # one whose deck homography puts the hole closest to (12, 39) in is kept.
    candidates = []
    if scores:
        values = np.array([sc for sc, _ in scores])
        cut = float(np.percentile(values, 70))
        for i, (score, y0) in enumerate(scores):
            left_ok = i == 0 or score >= scores[i - 1][0]
            right_ok = i == len(scores) - 1 or score >= scores[i + 1][0]
            if left_ok and right_ok and score >= cut:
                candidates.append((score, y0))
    front = None
    best_hole = None
    for score, y0 in candidates:
        line = np.array([-slope, 1.0, -(y0 - slope * x_mid)])
        line /= np.linalg.norm(line[:2])
        trial = [_intersect(line, left_line), _intersect(line, right_line),
                 _intersect(back_line, right_line), _intersect(back_line, left_line)]
        if any(c is None for c in trial):
            continue
        far_l, far_r, near_r, near_l = trial
        if np.linalg.norm(far_r - far_l) >= np.linalg.norm(near_r - near_l):
            continue                          # perspective: the far edge must look shorter
        quad = np.array([far_r, far_l, near_l, near_r], float)
        hole = find_hole(plate, deck_homography(quad))
        offset = hole["offset_in"] if hole else 99.0
        if best_hole is None or offset < best_hole[0]:
            best_hole = (offset, line, score)
    if best_hole is not None:
        front = (best_hole[1], 0.0)
    if front is None:
        return {"status": "not_found", "reason": "The deck's front edge could not be fitted."}
    front_line, front_rms = front
    checks_extra = {"front_edge_candidates": [c[1] for c in candidates]}
    corners_img = [_intersect(front_line, left_line), _intersect(front_line, right_line),
                   _intersect(back_line, right_line), _intersect(back_line, left_line)]
    if any(c is None for c in corners_img):
        return {"status": "not_found", "reason": "Deck edges are parallel."}
    far_left_img, far_right_img, near_right_img, near_left_img = corners_img
    # Thrower's view is mirrored: front-left (0,0) = far-right in the image, etc.
    corners = np.array([far_right_img, far_left_img, near_left_img, near_right_img], float)
    near_w = np.linalg.norm(corners[2] - corners[3])
    far_w = np.linalg.norm(corners[0] - corners[1])
    checks = {"apron_width_px": int(aw), "back_edge_rms_px": back_rms, "left_edge_rms_px": left_rms,
              "right_edge_rms_px": right_rms, "front_edge_rms_px": front_rms,
              "near_width_px": float(near_w), "far_width_px": float(far_w), "red_above_apron": red_share,
              **checks_extra}
    problems = []
    if not far_w < near_w:
        problems.append("the deck is not narrower at the far end")
    if max(left_rms, right_rms) > MAX_SIDE_LINE_RMS_PX:
        problems.append("the side edges are ragged")
    if not np.all(np.isfinite(corners)) or np.any(corners < -0.2 * max(h, w)) or np.any(corners > 1.2 * max(h, w)):
        problems.append("corners fall outside the image")
    hole = None
    if not problems:
        Hm = deck_homography(corners)
        hole = find_hole(plate, Hm)
        checks["hole"] = hole
        if hole is None or hole["offset_in"] > HOLE_SEARCH_TOLERANCE_IN:
            problems.append("no hole near (12, 39) in")
    status = "found" if not problems else "not_found"
    return {"status": status, "corners_px": corners.tolist(),
            "corner_order": "front-left, front-right, back-right, back-left (thrower's view)",
            "checks": checks,
            "reason": None if not problems else "Deck detection failed checks: " + "; ".join(problems)
            + ". Click the four deck corners on the board camera instead.",
            "method": "end apron top edge + red deck side and front edges (RANSAC lines), hole check"}


def _x_at(line: np.ndarray, y: float) -> float | None:
    a, b, c = line
    if abs(a) < 1e-9:
        return None
    return float(-(b * y + c) / a)


def find_hole(plate: np.ndarray, H: np.ndarray, px_per_in: int = 8) -> dict[str, Any] | None:
    """Rectify the deck and look for the dark hole near (12, 39) in; return its centre and offset."""
    size = (int(DECK_W_IN * px_per_in), int(DECK_L_IN * px_per_in))
    scale = np.diag([px_per_in, px_per_in, 1.0])
    rect = cv2.warpPerspective(plate, scale @ np.asarray(H, float), size)
    gray = cv2.cvtColor(rect, cv2.COLOR_BGR2GRAY).astype(float)
    y0, y1 = int((HOLE_Y_IN - 8) * px_per_in), int(min(DECK_L_IN, HOLE_Y_IN + 7) * px_per_in)
    x0, x1 = int((HOLE_X_IN - 8) * px_per_in), int((HOLE_X_IN + 8) * px_per_in)
    window = gray[y0:y1, x0:x1]
    if window.size == 0:
        return None
    deck_median = float(np.median(gray))
    threshold = min(deck_median * 0.7, np.percentile(window, 12))
    mask = (window <= threshold).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
    expected_area = math.pi * (HOLE_R_IN * px_per_in) ** 2
    best = None
    for k in range(1, count):
        area = stats[k, cv2.CC_STAT_AREA]
        if area < 0.15 * expected_area or area > 2.5 * expected_area:
            continue
        cx = (centroids[k][0] + x0) / px_per_in
        cy = (centroids[k][1] + y0) / px_per_in
        offset = math.hypot(cx - HOLE_X_IN, cy - HOLE_Y_IN)
        if best is None or offset < best["offset_in"]:
            best = {"x_in": float(cx), "y_in": float(cy), "offset_in": float(offset), "area_fraction": float(area / expected_area)}
    return best


# ------------------------------------------------------------------------------------------------
# Camera model: the deck corners fix the front camera's pose once its field of view is known.

NOMINAL_FRONT_HFOV_DEG = 68.0            # iPhone 1× camera in 16:9 video, after stabilisation crop
FRONT_HFOV_RANGE_DEG = (50.0, 82.0)


def deck_object_points(board: Board = Board()) -> np.ndarray:
    """3D deck corners (m) in the throw frame: X to the thrower's right, Y along the throw from the
    board's front edge, Z up from the floor. Order: front-left, front-right, back-right, back-left."""
    half = board.width_m / 2
    run = board.horizontal_length_m
    return np.array([[-half, 0.0, board.front_height_m], [half, 0.0, board.front_height_m],
                     [half, run, board.back_height_m], [-half, run, board.back_height_m]], float)


def front_camera_pose(corners_px: np.ndarray, image_size: tuple[int, int], hfov_deg: float,
                      board: Board = Board()) -> dict[str, Any] | None:
    """solvePnP (IPPE) of the four deck corners under an assumed horizontal field of view."""
    w, h = image_size
    f = (w / 2) / math.tan(math.radians(hfov_deg) / 2)
    K = np.array([[f, 0, w / 2], [0, f, h / 2], [0, 0, 1]], float)
    obj = deck_object_points(board)
    img = np.asarray(corners_px, float).reshape(4, 2)
    best = None
    for flag in (cv2.SOLVEPNP_IPPE, cv2.SOLVEPNP_ITERATIVE):
        try:
            ok, rvec, tvec = cv2.solvePnP(obj, img, K, None, flags=flag)
        except cv2.error:
            continue
        if not ok:
            continue
        R = cv2.Rodrigues(rvec)[0]
        centre = (-R.T @ tvec).ravel()
        # Physically: the camera is behind the board (Y beyond the back edge) and above the floor.
        if centre[1] <= board.horizontal_length_m * 0.5 or centre[2] <= 0:
            continue
        projected = cv2.projectPoints(obj, rvec, tvec, K, None)[0].reshape(-1, 2)
        residual = float(np.sqrt(np.mean(np.sum((projected - img) ** 2, axis=1))))
        if best is None or residual < best["residual_px"]:
            best = {"K": K, "rvec": rvec, "tvec": tvec, "R": R, "centre_m": centre, "residual_px": residual,
                    "hfov_deg": hfov_deg}
    return best


def ray_to_plane_y(pose: dict[str, Any], pixel: Sequence[float], y_plane_m: float) -> np.ndarray | None:
    """World point where the pixel's viewing ray crosses the vertical plane Y = y_plane_m."""
    R, K, centre = pose["R"], pose["K"], pose["centre_m"]
    ray = R.T @ np.linalg.inv(K) @ np.array([pixel[0], pixel[1], 1.0])
    if abs(ray[1]) < 1e-9:
        return None
    s = (y_plane_m - centre[1]) / ray[1]
    if s <= 0:
        return None
    return centre + s * ray


def ray_to_floor(pose: dict[str, Any], pixel: Sequence[float], height_m: float = 0.0) -> np.ndarray | None:
    """World point where the pixel's viewing ray meets the horizontal plane Z = height_m (the floor by default)."""
    R, K, centre = pose["R"], pose["K"], pose["centre_m"]
    ray = R.T @ np.linalg.inv(K) @ np.array([pixel[0], pixel[1], 1.0])
    if abs(ray[2]) < 1e-9:
        return None
    s = (height_m - centre[2]) / ray[2]
    if s <= 0:
        return None
    return centre + s * ray


def deck_shape_hfov(corners_px: np.ndarray, image_size: tuple[int, int]) -> dict[str, Any]:
    """Field of view that makes the four deck corners a true 24 × 48 in deck with the regulation slope.

    With the field of view fixed, a pose from four points has 6 unknowns and 8 equations, so a wrong
    field of view leaves a reprojection residual. Scanning 40–95° gives a sharp V-shaped minimum
    (Final Data Collection: 61–66°, residual < 0.3 px at the minimum, about 0.28 px per degree either side),
    refined by a parabola through the three best grid points.
    """
    grid = np.arange(40.0, 95.01, 1.0)
    residuals = []
    for hfov in grid:
        pose = front_camera_pose(corners_px, image_size, float(hfov))
        residuals.append(np.inf if pose is None else pose["residual_px"])
    residuals = np.asarray(residuals)
    i = int(np.argmin(residuals))
    if not np.isfinite(residuals[i]) or i in (0, len(grid) - 1):
        return {"status": "unavailable", "hfov_deg": None, "residual_px": None,
                "reason": "The deck's shape does not fix the field of view (minimum at the edge of 40–95°)."}
    y0, y1, y2 = residuals[i - 1], residuals[i], residuals[i + 1]
    denom = y0 - 2 * y1 + y2
    hfov = float(grid[i] + (0.5 * (y0 - y2) / denom if denom > 0 else 0.0))
    pose = front_camera_pose(corners_px, image_size, hfov)
    slope = float(0.5 * (abs(y0 - y1) + abs(y2 - y1)))       # px per degree near the minimum
    return {"status": "measured" if pose is not None and pose["residual_px"] < 1.0 else "estimated",
            "hfov_deg": hfov, "residual_px": None if pose is None else pose["residual_px"],
            "uncertainty_deg": float(0.5 / max(slope, 1e-3)),   # half a pixel of corner error
            "reason": None}


def calibrate_front_camera(corners_px: np.ndarray, image_size: tuple[int, int], release_px: Sequence[float] | None,
                           release_distance_m: float | None, release_height_m: float | None,
                           pooled_hfov_deg: float | None = None) -> dict[str, Any]:
    """Front camera model: field of view from the deck's shape, pose from the deck corners.

    Priority: a session-pooled field of view (median over the takes, steadier than one take), then this
    take's deck-shape value, then the nominal 68°. When the bag at release is seen by both cameras, the
    front camera's ray through the release hand is intersected with the side camera's release distance and
    the height it implies is compared with the side camera's measured release height (``cross_check``).
    """
    shape = deck_shape_hfov(corners_px, image_size)
    if pooled_hfov_deg is not None:
        hfov, status, source = float(pooled_hfov_deg), "measured", "session median of the deck-shape field of view"
    elif shape["status"] == "measured":
        hfov, status, source = shape["hfov_deg"], "measured", "deck shape"
    else:
        hfov, status, source = NOMINAL_FRONT_HFOV_DEG, "estimated", "nominal iPhone field of view"
    pose = front_camera_pose(corners_px, image_size, hfov)
    out: dict[str, Any] = {"hfov_deg": hfov, "status": status if pose is not None else "unavailable",
                           "source": source, "pose": pose, "deck_shape": shape, "reason": None,
                           "cross_check": None}
    if pose is None:
        out["reason"] = "The deck corners do not give a physically possible camera position."
        return out
    if release_px is not None and release_distance_m is not None and release_height_m is not None:
        point = ray_to_plane_y(pose, release_px, -release_distance_m)
        if point is not None:
            out["cross_check"] = {"front_release_height_m": float(point[2]), "side_release_height_m": release_height_m,
                                  "difference_m": float(point[2] - release_height_m)}
    return out


# ------------------------------------------------------------------------------------------------
# Keeping the deck registered: the front phone drifts slowly on its tripod (Final Data Collection: the
# board moved ~40 px down the image over a 30 s take, and exposure changed). Every frame is aligned to
# the take's reference frame, in which the deck corners were found, by ECC image alignment (affine,
# invariant to brightness and contrast changes) on a window around the board, its end apron and legs.

ECC_ITERATIONS = 80
ECC_EPSILON = 1e-5


def board_window(corners_px: np.ndarray, size: tuple[int, int]) -> tuple[int, int, int, int]:
    """x, y, w, h of the alignment window: the deck plus its apron and legs, with a margin."""
    c = np.asarray(corners_px, float)
    width = float(c[:, 0].max() - c[:, 0].min())
    height = float(c[:, 1].max() - c[:, 1].min())
    x0 = int(max(0, c[:, 0].min() - 0.35 * width))
    x1 = int(min(size[0], c[:, 0].max() + 0.35 * width))
    y0 = int(max(0, c[:, 1].min() - 1.2 * height))
    y1 = int(min(size[1], c[:, 1].max() + 0.75 * width))
    return x0, y0, x1 - x0, y1 - y0


def align_to_reference(reference_gray: np.ndarray, gray: np.ndarray, window: tuple[int, int, int, int],
                       initial: np.ndarray | None = None, ignore_mask: np.ndarray | None = None) -> dict[str, Any]:
    """Affine warp W (2×3) mapping reference pixels to this frame's pixels, by ECC on the board window.

    Phase correlation gives the starting translation; ECC refines a full affine. ``ok`` is False when
    ECC does not converge or its correlation is below 0.6 (the board is hidden or the scene changed).
    ``ignore_mask`` (frame-sized, non-zero = leave out) removes pixels of this frame from the fit, e.g. bags.
    """
    x, y, w, h = window
    ref = reference_gray[y:y + h, x:x + w].astype(np.float32)
    # Search a wider window in the frame so a drifted board is still inside it.
    pad = int(0.25 * max(w, h))
    X0, Y0 = max(0, x - pad), max(0, y - pad)
    X1, Y1 = min(gray.shape[1], x + w + pad), min(gray.shape[0], y + h + pad)
    cur = gray[Y0:Y1, X0:X1].astype(np.float32)
    input_mask = None
    if ignore_mask is not None:
        keep = (np.asarray(ignore_mask)[Y0:Y1, X0:X1] == 0).astype(np.uint8)
        if keep.mean() >= 0.5:               # most of the window must still be usable
            input_mask = keep
    if initial is None:
        big = np.zeros_like(cur)
        oy, ox = y - Y0, x - X0
        big[oy:oy + h, ox:ox + w] = ref
        win = cv2.createHanningWindow((cur.shape[1], cur.shape[0]), cv2.CV_32F)
        (dx, dy), response = cv2.phaseCorrelate(big, cur, win)
        shift = np.array([dx, dy])
        warp = np.array([[1, 0, ox + shift[0]], [0, 1, oy + shift[1]]], np.float32)
    else:
        # ``initial`` maps full reference pixels → full frame pixels; express it window → search window.
        A0 = np.asarray(initial, float)[:, :2]
        t0 = np.asarray(initial, float)[:, 2]
        warp = np.zeros((2, 3), np.float32)
        warp[:, :2] = A0
        warp[:, 2] = A0 @ np.array([x, y], float) + t0 - np.array([X0, Y0], float)
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, ECC_ITERATIONS, ECC_EPSILON)
    try:
        cc, warp = cv2.findTransformECC(ref, cur, warp, cv2.MOTION_AFFINE, criteria, input_mask, 5)
    except cv2.error:
        return {"ok": False, "warp": None, "correlation": None}
    # window→search warp  →  full reference → full frame:  p_frame = A (p_ref - [x,y]) + t + [X0,Y0]
    A = warp[:, :2].astype(float)
    t = warp[:, 2].astype(float)
    full = np.zeros((2, 3))
    full[:, :2] = A
    full[:, 2] = t + np.array([X0, Y0]) - A @ np.array([x, y], float)
    return {"ok": bool(cc >= 0.6), "warp": full, "correlation": float(cc)}


ALIGN_BAG_DILATE_PX = 9          # bag mask grown by about a third of a near bag's size (blur, shadow at its edge)
ALIGN_SHAPE_TOLERANCE_PX = 3.0   # deck shape change (translation removed) beyond which a key frame is not trusted
ALIGN_MAX_LINEAR = 0.02          # affine scale/shear a drifting tripod camera can show (real: ≤ 0.3 %, 1 px on the deck)


def bag_red_mask(image: np.ndarray) -> np.ndarray:
    """Bag-coloured pixels (hue ≤ 12 or ≥ 150, S ≥ 60, V ≥ 35: the bags, not the deck paint at S 25–60), grown."""
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    red = (((h <= RED_HUE_LOW) | (h >= RED_HUE_HIGH)) & (s >= BAG_MIN_SATURATION) & (v >= 35)).astype(np.uint8)
    return cv2.dilate(red, np.ones((ALIGN_BAG_DILATE_PX, ALIGN_BAG_DILATE_PX), np.uint8)) > 0


def warp_points(warp: np.ndarray, points: np.ndarray) -> np.ndarray:
    p = np.asarray(points, float).reshape(-1, 2)
    return p @ np.asarray(warp, float)[:, :2].T + np.asarray(warp, float)[:, 2]


def frame_corners(reference: dict[str, Any], frames: Sequence[np.ndarray], step: int = 5) -> dict[str, Any]:
    """Deck corners in every frame of a clip, from the take's reference frame and per-frame alignment.

    Alignment runs on every ``step``-th frame (and the last); corners in between are interpolated
    (the drift is slow: a few pixels per second).
    """
    ref_img = reference["image"]
    ref_gray = cv2.cvtColor(ref_img, cv2.COLOR_BGR2GRAY)
    corners = np.asarray(reference["corners_px"], float)
    size = (ref_img.shape[1], ref_img.shape[0])
    window = board_window(corners, size)
    keys = sorted(set(list(range(0, len(frames), step)) + [len(frames) - 1]))
    solved: dict[int, np.ndarray] = {}
    scores: list[float] = []
    previous = None
    ref_bags = bag_red_mask(ref_img)

    def solve(gray: np.ndarray, frame_bags: np.ndarray, seed: np.ndarray | None) -> dict[str, Any]:
        result = align_to_reference(ref_gray, gray, window, seed, frame_bags)
        if result["ok"]:
            carried = cv2.warpAffine(ref_bags.astype(np.uint8), result["warp"], (gray.shape[1], gray.shape[0]),
                                     flags=cv2.INTER_NEAREST) > 0
            refined = align_to_reference(ref_gray, gray, window, result["warp"], frame_bags | carried)
            if refined["ok"]:
                result = refined
        return result

    def rigid(result: dict[str, Any]) -> bool:
        return bool(result["ok"]) and float(np.max(np.abs(result["warp"][:, :2] - np.eye(2)))) <= ALIGN_MAX_LINEAR

    for k in keys:
        gray = cv2.cvtColor(frames[k], cv2.COLOR_BGR2GRAY)
        # Bags pull the fit towards themselves where this frame and the reference differ (Player 2 take 4
        # throw 2: the far corners rose 27 px when a bag landed by the far edge, the camera still). Bag-red
        # pixels of this frame, and those of the reference carried into this frame, are left out of the fit.
        # With less texture left the fit can settle on a stretched warp, so it is solved from the previous
        # frame's warp and from a fresh phase-correlation start, and the better plausible one is kept.
        frame_bags = bag_red_mask(frames[k])
        tries = [solve(gray, frame_bags, previous)]
        if previous is not None and not rigid(tries[0]):
            tries.append(solve(gray, frame_bags, None))
        ok = [t for t in tries if t["ok"]]
        result = max(ok, key=lambda t: (rigid(t), t["correlation"])) if ok else tries[0]
        if result["ok"]:
            solved[k] = warp_points(result["warp"], corners)
            previous = result["warp"]
            scores.append(result["correlation"])
    if not solved:
        return {"status": "unavailable", "reason": "The board could not be aligned with the take's reference frame.",
                "corners": None}
    # Guard: the phone drifts as a whole, so the deck keeps its shape in the picture (translation removed, the
    # far and near edges move together: ≤ 1.2 px on all 92 library throws once bags are masked). A key frame
    # whose deck shape departs from the clip's median shape by more than ALIGN_SHAPE_TOLERANCE_PX was pulled
    # by something in the scene; it is dropped and its corners interpolated from the good key frames.
    shapes = {k: c - c.mean(axis=0) for k, c in solved.items()}
    median_shape = np.median(np.stack(list(shapes.values())), axis=0)
    deviation = {k: float(np.max(np.linalg.norm(s - median_shape, axis=1))) for k, s in shapes.items()}
    good = {k: c for k, c in solved.items() if deviation[k] <= ALIGN_SHAPE_TOLERANCE_PX}
    rejected = len(solved) - len(good)
    if good:
        solved = good
    known = np.array(sorted(solved))
    stack = np.stack([solved[k] for k in known])                 # (n, 4, 2)
    per_frame = np.empty((len(frames), 4, 2))
    for i in range(4):
        for j in range(2):
            per_frame[:, i, j] = np.interp(np.arange(len(frames)), known, stack[:, i, j])
    drift = float(np.max(np.linalg.norm(per_frame - per_frame[0], axis=2)))
    return {"status": "measured", "corners": per_frame, "aligned_frames": int(len(known)),
            "attempted_frames": len(keys), "median_correlation": float(np.median(scores)),
            "max_drift_px": drift, "max_shape_change_px": float(max(deviation.values())),
            "shape_rejected_frames": int(rejected)}


# ------------------------------------------------------------------------------------------------
# Where the bag ended: deck change between before the throw and after it settles.

CHANGE_LAB_THRESHOLD = 18.0              # ΔE (CIELAB, 8-bit scale) for "this pixel changed"
MIN_BAG_AREA_FRACTION = 0.25             # of the expected bag footprint in pixels
MAX_BAG_AREA_FRACTION = 5.0
DECK_MARGIN_IN = 0.75                    # a bag's centre within this of the deck edge still counts as on the deck
FLOOR_BAND_DECK_HEIGHTS = 2.5            # floor search band above the deck's far edge, in deck image heights
FLOOR_SEARCH_HALF_WIDTH_M = 2.0          # an off-board bag is looked for within ±2 m of the centre line ...
FLOOR_SEARCH_SHORT_M = 2.5               # ... from 2.5 m short of the board to the camera
FLOOR_SEARCH_DECK_WIDTHS = 1.5           # without a camera pose: within 1.5 deck widths either side of the deck
CONTACT_DECK_MARGIN_IN = 6.0             # first contact: a tracked point within one bag width of the deck
MIN_OFF_DECK_AREA_FRACTION = 0.6         # a whole bag on the floor (under the board or beside it), of the deck bag area
BAG_MIN_SATURATION = 60                  # the Final Data Collection bags are red: hue as the deck paint, S 88-166
MIN_BAG_COLOUR_FRACTION = 0.4            # off the deck, at least this share of a blob's pixels must be bag red
MIN_ON_DECK_AREA_FRACTION = 1.0          # a bag at rest on the deck: at least one bag top face at that place (rests 1.3–11×)
MIN_ON_DECK_VS_EMPTY = CHANGE_LAB_THRESHOLD   # ... and differing from the empty board like a changed pixel (rests ≥ 22)
PATH_START_MAX_FRAMES = 3                # the deck track must start within this many frames after the mapped contact
PATH_OFF_DECK_POINTS = 3                 # last tracked points more than a bag width off the deck: the bag left it


def read_clip_frames(video_path: str, scale: float = 1.0) -> tuple[list[np.ndarray], float]:
    capture = cv2.VideoCapture(str(video_path))
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    frames = []
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if scale != 1.0:
                frame = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            frames.append(frame)
    finally:
        capture.release()
    return frames, float(fps)


def _deck_polygon(H: np.ndarray, margin_in: float = 0.0) -> np.ndarray:
    m = margin_in
    return to_image(H, np.array([[-m, -m], [DECK_W_IN + m, -m], [DECK_W_IN + m, DECK_L_IN + m], [-m, DECK_L_IN + m]]))


def expected_bag_area_px(H: np.ndarray, at_in: Sequence[float] = (12.0, 24.0)) -> float:
    """Image area of a 6 × 6 in bag lying on the deck at a deck point (its top face; the visible
    side adds to this, so the accepted range is wide)."""
    x, y = at_in
    square = to_image(H, np.array([[x - 3, y - 3], [x + 3, y - 3], [x + 3, y + 3], [x - 3, y + 3]]))
    return float(abs(cv2.contourArea(square.astype(np.float32))))


def floor_bag_area_px(pose: dict[str, Any] | None, floor_point: Sequence[float] | None) -> float | None:
    """Image area of a 6 × 6 in bag lying on the floor at a floor point (X, Y in m), from the camera pose."""
    if pose is None or floor_point is None:
        return None
    half = 3.0 * INCH_M
    x, y = float(floor_point[0]), float(floor_point[1])
    square = np.array([[x - half, y - half, 0.0], [x + half, y - half, 0.0], [x + half, y + half, 0.0],
                       [x - half, y + half, 0.0]])
    projected = cv2.projectPoints(square, pose["rvec"], pose["tvec"], pose["K"], None)[0].reshape(-1, 2)
    if not np.isfinite(projected).all():
        return None
    return float(abs(cv2.contourArea(projected.astype(np.float32))))


def local_bag_area_px(blob: dict[str, Any], H: np.ndarray, pose: dict[str, Any] | None, fallback: float) -> float:
    """Expected image area of a bag where this blob lies: on the deck from the deck homography at its centre,
    elsewhere on the floor from the camera pose at its lowest point; without a pose the deck-centre value."""
    deck = to_deck(H, np.array([blob["centroid_px"]]))[0]
    if -DECK_MARGIN_IN <= deck[0] <= DECK_W_IN + DECK_MARGIN_IN and -3.0 <= deck[1] <= DECK_L_IN + 6.0:
        at = (float(np.clip(deck[0], 3.0, DECK_W_IN - 3.0)), float(np.clip(deck[1], 3.0, DECK_L_IN - 3.0)))
        return expected_bag_area_px(H, at)
    if pose is not None:
        area = floor_bag_area_px(pose, ray_to_floor(pose, blob["bottom_px"], height_m=0.0))
        if area is not None:
            return max(area, fallback)       # never below the deck-centre bag (the old, fixed reference)
    return fallback


def change_blobs(before: np.ndarray, after: np.ndarray, roi_mask: np.ndarray, min_area: float, max_area: float
                 ) -> list[dict[str, Any]]:
    a = cv2.cvtColor(before, cv2.COLOR_BGR2LAB).astype(np.float32)
    b = cv2.cvtColor(after, cv2.COLOR_BGR2LAB).astype(np.float32)
    delta = np.sqrt(np.sum((a - b) ** 2, axis=2))
    mask = ((delta > CHANGE_LAB_THRESHOLD) & (roi_mask > 0)).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
    blobs = []
    for k in range(1, count):
        area = float(stats[k, cv2.CC_STAT_AREA])
        if not min_area <= area <= max_area:
            continue
        ys, xs = np.nonzero(labels == k)
        hsv = cv2.cvtColor(after[ys, xs].reshape(-1, 1, 3), cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(float)
        hue, sat = hsv[:, 0], hsv[:, 1]
        bag_coloured = float(np.mean(((hue <= RED_HUE_LOW) | (hue >= RED_HUE_HIGH)) & (sat >= BAG_MIN_SATURATION)))
        blobs.append({"centroid_px": [float(centroids[k][0]), float(centroids[k][1])], "area_px": area,
                      "bag_colour_fraction": bag_coloured,
                      "bottom_px": [float(np.median(xs[ys >= np.percentile(ys, 85)])), float(ys.max())],
                      "bbox": [int(v) for v in stats[k, :4]], "mean_delta": float(delta[labels == k].mean())})
    return sorted(blobs, key=lambda b: -b["area_px"] * b["mean_delta"])


def point_in_deck(point_in: Sequence[float], margin_in: float = DECK_MARGIN_IN) -> bool:
    x, y = point_in
    return -margin_in <= x <= DECK_W_IN + margin_in and -margin_in <= y <= DECK_L_IN + margin_in


def in_hole(point_in: Sequence[float], extra_in: float = 1.0) -> bool:
    return math.hypot(point_in[0] - HOLE_X_IN, point_in[1] - HOLE_Y_IN) <= HOLE_R_IN + extra_in


def track_bag_on_deck(frames: Sequence[np.ndarray], homographies: Sequence[np.ndarray], start: int, stop: int,
                      roi_mask: np.ndarray, min_area: float, max_area: float) -> list[dict[str, Any]]:
    """The moving bag near/on the deck from ``start`` to ``stop`` (front-clip frames).

    Used for the slide path, for the lateral position at first contact and for a bag that drops into the
    hole. Candidates are moving bag-red blobs; the track is the best chain through all frames
    (``front_track.track_on_deck``, METHODS_AND_MATH §5.2). Each frame's own deck homography maps the
    blob's lowest point to board inches.
    """
    from .front_track import track_on_deck
    anchors = np.array([to_image(H, np.array([[12.0, 24.0]]))[0] for H in homographies])
    ring = np.array([[HOLE_X_IN + HOLE_R_IN * math.cos(a), HOLE_Y_IN + HOLE_R_IN * math.sin(a)]
                     for a in np.linspace(0, 2 * math.pi, 24, endpoint=False)])
    holes = [to_image(H, ring) for H in homographies]
    path = []
    for point in track_on_deck(frames, anchors, start, stop, roi_mask, min_area, max_area, hole_px=holes):
        f = point["frame"]
        deck = to_deck(homographies[f], np.array([point["bottom_px"]]))[0]
        path.append({"frame": f, "px": point["px"], "bottom_px": point["bottom_px"],
                     "deck_in": [float(deck[0]), float(deck[1])]})
    return path


UNDER_BOARD_FROM_M = 0.45      # floor under the deck from 0.45 m behind the front edge ...
UNDER_BOARD_TO_BACK_M = 0.03   # ... to 3 cm short of the back edge (the hole's centre is 23 cm short of it)


def under_board_region(corners_px: np.ndarray, pose: dict[str, Any] | None = None,
                       board: Board = Board()) -> np.ndarray:
    """Image polygon of the floor under the board's back end (between the legs), where a bag that went
    through the hole comes to rest in the front camera's view.

    With the camera pose it is the floor rectangle under the deck, ±12 in across, from 0.45 m behind the
    front edge to 3 cm short of the back edge, projected into the image (a bag dropping through the hole,
    whose centre is 23 cm short of the back edge, lands inside it); a bag that slid off the back end lands
    on the floor nearer the camera, beyond the back edge and below this region (Player 4 takes 1 and 4: such bags were taken for
    bags in the hole by the earlier, image-proportion region). Without a pose, the image proportions are used:
    from 10 % to 55 % of the back edge's width below it (the back legs' feet in this collection)."""
    c = np.asarray(corners_px, float)
    if pose is not None:
        half = board.width_m / 2
        far = board.horizontal_length_m - UNDER_BOARD_TO_BACK_M
        floor = np.array([[-half, UNDER_BOARD_FROM_M, 0.0], [half, UNDER_BOARD_FROM_M, 0.0],
                          [half, far, 0.0], [-half, far, 0.0]])
        projected = cv2.projectPoints(floor, pose["rvec"], pose["tvec"], pose["K"], None)[0].reshape(-1, 2)
        if np.isfinite(projected).all():
            return projected
    back_right_img, back_left_img = c[2], c[3]        # thrower's back-right is image left
    width = float(np.linalg.norm(back_left_img - back_right_img))
    down = np.array([0.0, 1.0])
    return np.array([back_right_img + 0.10 * width * down, back_left_img + 0.10 * width * down,
                     back_left_img + 0.55 * width * down, back_right_img + 0.55 * width * down])


def _normalised_lab(image: np.ndarray, roi: np.ndarray) -> np.ndarray:
    """CIELAB with the lightness scaled so its median inside ``roi`` is 128 (removes exposure drift)."""
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB).astype(np.float32)
    median = float(np.median(lab[..., 0][roi > 0])) if roi.any() else float(np.median(lab[..., 0]))
    lab[..., 0] *= 128.0 / max(1.0, median)
    return lab


def _appeared(blob: dict[str, Any], before_lab: np.ndarray, after_lab: np.ndarray, empty_lab: np.ndarray | None
              ) -> bool:
    """Did a bag appear here (present after, not before) rather than leave (present before, not after)?

    Compared with the empty board at the start of the take: where a bag now lies, the after image differs
    from the empty board more than the before image does.
    """
    if empty_lab is None:
        return True
    x, y, w, h = blob["bbox"]
    sl = (slice(y, y + h), slice(x, x + w))
    d_after = float(np.mean(np.linalg.norm(after_lab[sl] - empty_lab[sl], axis=2)))
    d_before = float(np.mean(np.linalg.norm(before_lab[sl] - empty_lab[sl], axis=2)))
    blob["vs_empty_after"], blob["vs_empty_before"] = d_after, d_before
    return d_after >= d_before


def _deck_pose(corners: np.ndarray, size: tuple[int, int], hfov_deg: float | None) -> dict[str, Any] | None:
    """The front camera's pose from the deck corners (pooled field of view, else this deck's shape)."""
    if hfov_deg is None:
        shape = deck_shape_hfov(corners, size)
        hfov_deg = shape["hfov_deg"] if shape["status"] == "measured" else None
    return front_camera_pose(corners, size, hfov_deg) if hfov_deg is not None else None


def _floor_gate(c_after: np.ndarray, size: tuple[int, int], hfov_deg: float | None):
    """Function telling whether an image point lies on the floor near the board (|X| ≤ 2 m, from 2.5 m short
    of the board to just before the camera), from the front camera's pose; None without a pose."""
    pose = _deck_pose(c_after, size, hfov_deg)
    if pose is None:
        return None
    camera_y = float(pose["centre_m"][1])

    def gate(point_px) -> tuple[bool, list[float] | None]:
        floor = ray_to_floor(pose, point_px, height_m=0.0)
        if floor is None:
            return False, None
        inside = abs(floor[0]) <= FLOOR_SEARCH_HALF_WIDTH_M and -FLOOR_SEARCH_SHORT_M <= floor[1] <= camera_y - 0.3
        return bool(inside), [float(floor[0]), float(floor[1])]
    return gate


def landing_from_front(frames: Sequence[np.ndarray], fps: float, corners_per_frame: np.ndarray,
                       release_frame: int | None, contact_frame: int | None,
                       empty_reference: dict[str, Any] | None = None, hfov_deg: float | None = None) -> dict[str, Any]:
    """Where the bag ended across the board, seen by the front camera.

    * before = per-pixel median of the last 12 frames up to 0.25 s before release (the bag is in the hand),
      warped onto the final frame's board position (the camera drifts slowly);
    * after = median of the clip's last 0.3 s (the bag has stopped);
    * a changed blob of bag size is the new bag. On the deck (centre within 0.75 in of the edge) → *board*;
      on the floor under the board's back end, between the legs → *hole* (that is where a bag that drops
      through the hole lies); anywhere else near the board → *off the board*. With no new bag but a moving
      bag that reached the hole → *hole*.
    """
    n = len(frames)
    if n < 10:
        return {"status": "unavailable", "reason": "Front clip too short."}
    h, w = frames[0].shape[:2]
    Hs = [deck_homography(c) for c in corners_per_frame]
    pre_end = max(3, int((release_frame if release_frame is not None else n // 3) - 0.25 * fps))
    pre_idx = list(range(max(0, min(pre_end, n) - 12), min(pre_end, n)))
    post_idx = list(range(n - max(3, int(0.3 * fps)), n))
    before = np.median(np.stack([frames[i] for i in pre_idx]), axis=0).astype(np.uint8)
    after = np.median(np.stack([frames[i] for i in post_idx]), axis=0).astype(np.uint8)
    c_before = np.median(corners_per_frame[pre_idx], axis=0)
    c_after = np.median(corners_per_frame[post_idx], axis=0)
    shift = cv2.getPerspectiveTransform(c_before.astype(np.float32), c_after.astype(np.float32))
    before = cv2.warpPerspective(before, shift, (w, h), borderMode=cv2.BORDER_REPLICATE)
    H_after = deck_homography(c_after)
    bag_area = expected_bag_area_px(H_after)
    region_poly = to_image(H_after, np.array([[-24.0, -30.0], [48.0, -30.0], [48.0, 60.0], [-24.0, 60.0]]))
    roi = np.zeros((h, w), np.uint8)
    cv2.fillPoly(roi, [np.clip(region_poly, -10 * w, 10 * w).astype(np.int32)], 1)
    after_pose = _deck_pose(c_after, (w, h), hfov_deg)
    under = under_board_region(c_after, after_pose)
    cv2.fillPoly(roi, [under.astype(np.int32)], 1)
    # The floor around the board, out to the frame's bottom edge: a bag that slides off the back end comes
    # towards the camera, and a short bag lies on the floor in front of the board, below the deck plane the
    # polygon above follows. The band starts FLOOR_BAND_DECK_HEIGHTS deck-heights above the deck's far
    # edge (≈ 2–2.5 m short of the board at this camera height), below where the thrower stands.
    deck_top, deck_bottom = float(c_after[:, 1].min()), float(c_after[:, 1].max())
    band_top = int(max(0, deck_top - FLOOR_BAND_DECK_HEIGHTS * max(1.0, deck_bottom - deck_top)))
    roi[band_top:, :] = 1
    min_area, max_area = MIN_BAG_AREA_FRACTION * bag_area, MAX_BAG_AREA_FRACTION * bag_area * 3
    # A bag's image size depends on where it lies: one on the floor near the camera is many times the deck-centre
    # bag (Player 1 take 5 throw 4: a bag that slid off the back end was 3069 px² against 176 px² at the deck
    # centre, beyond the old fixed limit of 15 × 176). Blobs are found up to the largest size a bag can have in
    # the searched area, then each is held to the size a bag has at its own place (``local_bag_area_px``).
    nearest_floor = floor_bag_area_px(after_pose, ray_to_floor(after_pose, (w / 2, h - 1))) if after_pose else None
    blob_cap = MAX_BAG_AREA_FRACTION * 3 * max(bag_area, nearest_floor or 0.0)
    blobs = []
    for blob in change_blobs(before, after, roi, min_area, blob_cap):
        blob["expected_area_px"] = local_bag_area_px(blob, H_after, after_pose, bag_area)
        if blob["area_px"] <= MAX_BAG_AREA_FRACTION * 3 * blob["expected_area_px"]:
            blobs.append(blob)
    empty_lab = None
    if empty_reference is not None:
        to_after = cv2.getPerspectiveTransform(np.asarray(empty_reference["corners_px"], np.float32),
                                               c_after.astype(np.float32))
        empty = cv2.warpPerspective(empty_reference["image"], to_after, (w, h), borderMode=cv2.BORDER_REPLICATE)
        empty_lab = _normalised_lab(empty, roi)
    before_lab, after_lab = _normalised_lab(before, roi), _normalised_lab(after, roi)
    removed = [b for b in blobs if not _appeared(b, before_lab, after_lab, empty_lab)]
    blobs = [b for b in blobs if b not in removed]
    path = []
    contact_source = "side camera"
    if contact_frame is not None:
        path = track_bag_on_deck(frames, Hs, max(1, contact_frame - int(0.15 * fps)), n - 1, roi, min_area, max_area)
    elif release_frame is not None:
        # No first contact from the side camera: the first moment the moving bag's lowest point sits on the
        # deck for three frames running (a bag still in the air projects beyond the deck's far edge here).
        path = track_bag_on_deck(frames, Hs, release_frame + int(0.25 * fps), n - 1, roi, min_area, max_area)
        for k in range(len(path) - 2):
            if all(point_in_deck(p["deck_in"], 0.0) for p in path[k:k + 3]):
                contact_frame = path[k]["frame"]
                contact_source = "front camera (bag reaching the deck)"
                break
    result: dict[str, Any] = {"status": "measured", "expected_bag_area_px": bag_area, "path": path,
                              "deck_polygon_px": c_after.tolist(), "contact_source": contact_source,
                              "precision": lateral_precision_in_per_px(H_after, (12.0, 30.0))}
    contact = None
    # Only tracked points at the deck count: earlier ones are the bag still in the air, whose deck-plane
    # mapping runs far off (Player 4 take 5 throw 1: −190 in sideways two frames before touchdown).
    at_deck = [p for p in path if point_in_deck(p["deck_in"], CONTACT_DECK_MARGIN_IN)]
    if contact_frame is not None and at_deck:
        window = max(2, int(0.1 * fps))
        # First choice: the first tracked point ON the deck from one frame before the side camera's contact (the
        # front camera sees the bag reach the deck 0–2 frames after the mapped contact). A point in the air just
        # in front of the deck is only used when the bag is never seen on the deck itself.
        on_deck = [p for p in at_deck if point_in_deck(p["deck_in"], 0.0)
                   and contact_frame - 1 <= p["frame"] <= contact_frame + window]
        near = min(on_deck, key=lambda p: p["frame"]) if on_deck else \
            min(at_deck, key=lambda p: abs(p["frame"] - contact_frame))
        if abs(near["frame"] - contact_frame) <= window:
            contact = near
    result["contact"] = None if contact is None else {"frame": contact["frame"], "x_in": contact["deck_in"][0],
                                                      "y_in_front": contact["deck_in"][1], "px": contact["px"]}
    under_path = under.reshape(-1, 1, 2).astype(np.float32)
    floor_gate = _floor_gate(c_after, (w, h), hfov_deg)
    deck_cx = float(c_after[:, 0].mean())
    deck_half_w = float(c_after[:, 0].max() - c_after[:, 0].min()) / 2
    on_deck, in_under, elsewhere, small_on_deck = [], [], [], []
    for blob in blobs:
        # The blob's centre (the bag's top) maps to the deck; at this grazing view the bag's own thickness
        # pushes its lowest pixels past the deck's back edge, so the along range is generous (−3 to 54 in).
        deck = to_deck(H_after, np.array([blob["centroid_px"]]))[0]
        blob["deck_in"] = [float(deck[0]), float(deck[1])]
        blob["area_fraction"] = blob["area_px"] / max(1.0, blob["expected_area_px"])
        if -DECK_MARGIN_IN <= deck[0] <= DECK_W_IN + DECK_MARGIN_IN and -3.0 <= deck[1] <= DECK_L_IN + 6.0:
            # A bag at rest on the deck is a whole bag that the empty board does not have. On a red deck the
            # colour test says little (paint and bag share the hue), so size and difference decide: smaller
            # changes are specks, shadows or a nudged bag's edge, not a bag (library: 0.24–0.76 of a bag's top
            # face, against 1.3–11 for every bag at rest; the top face plus the visible side).
            if blob["area_fraction"] >= MIN_ON_DECK_AREA_FRACTION and \
                    blob.get("vs_empty_after", MIN_ON_DECK_VS_EMPTY) >= MIN_ON_DECK_VS_EMPTY:
                on_deck.append(blob)
            else:
                small_on_deck.append(blob)
        elif cv2.pointPolygonTest(under_path, tuple(map(float, blob["centroid_px"])), False) >= 0:
            # A bag through the hole lies on the floor nearer the camera than the deck centre, so it is at least
            # this big; shadow specks under the board are much smaller (Player 1 take 3: bag 996 px², specks ~70).
            if blob["area_px"] >= MIN_OFF_DECK_AREA_FRACTION * bag_area and \
                    blob["bag_colour_fraction"] >= MIN_BAG_COLOUR_FRACTION:
                in_under.append(blob)
        elif blob["area_px"] < MIN_OFF_DECK_AREA_FRACTION * bag_area or \
                blob["bag_colour_fraction"] < MIN_BAG_COLOUR_FRACTION:
            continue                       # off the deck only a whole, bag-coloured blob is a bag
        elif floor_gate is not None:
            # Off the board: only where a bag can lie (the floor near the board). Reflections on a shiny floor
            # and changes far to the side are not bags.
            near, floor_m = floor_gate(blob["bottom_px"])
            if near:
                blob["floor_m"] = floor_m
                elsewhere.append(blob)
        elif abs(blob["centroid_px"][0] - deck_cx) <= deck_half_w * (1 + 2 * FLOOR_SEARCH_DECK_WIDTHS):
            elsewhere.append(blob)
    result["changes"] = {"new_on_deck": len(on_deck), "new_under_board": len(in_under), "new_elsewhere": len(elsewhere),
                         "bags_moved_or_knocked": len(removed), "small_on_deck": len(small_on_deck)}
    result["candidates"] = [
        {"kind": kind, "px": [round(b["centroid_px"][0], 1), round(b["centroid_px"][1], 1)],
         "area_px": b["area_px"], "area_fraction": round(b["area_fraction"], 2),
         "bag_colour_fraction": round(b["bag_colour_fraction"], 2),
         "vs_empty": None if b.get("vs_empty_after") is None else round(b["vs_empty_after"], 1)}
        for kind, group in (("deck", on_deck), ("small_on_deck", small_on_deck), ("under_board", in_under),
                            ("elsewhere", elsewhere)) for b in group]
    end_px = np.asarray(path[-1]["px"]) if path else None
    # The tracked path is only evidence about this throw when it starts at the bag's first contact: a track
    # that begins later followed something else (Player 3 take 2 throw 1: it began 36 frames after contact, on
    # the flickering hole, after the bag had sailed off the back of the board and out of view).
    path_starts_at_contact = bool(path) and contact_frame is not None and \
        path[0]["frame"] <= contact_frame + PATH_START_MAX_FRAMES
    result["path_starts_at_contact"] = path_starts_at_contact

    def nearest(candidates: list[dict[str, Any]]) -> dict[str, Any]:
        if end_px is None or not path_starts_at_contact:
            return candidates[0]
        return min(candidates, key=lambda c: float(np.linalg.norm(np.asarray(c["centroid_px"]) - end_px)))

    def image_gap(blob: dict[str, Any]) -> float:
        return float(np.linalg.norm(np.asarray(blob["centroid_px"]) - end_px))

    # A bag tracked from first contact to well off the deck (its last PATH_OFF_DECK_POINTS points more than a
    # bag width outside it) that ends next to a new bag on the floor slid or bounced off: a change on the deck
    # is then something else, a knocked bag or a small disturbance (Player 1 take 5 throw 4: the bag slid off
    # the back end and lay on the floor 6 px from the track's end, while a 95 px² speck changed on the deck).
    left_deck = path_starts_at_contact and len(path) >= PATH_OFF_DECK_POINTS and all(
        not point_in_deck(p["deck_in"], CONTACT_DECK_MARGIN_IN) for p in path[-PATH_OFF_DECK_POINTS:])
    result["path_left_deck"] = bool(left_deck)
    if left_deck and elsewhere and (on_deck or in_under):
        floor_end = min(elsewhere, key=image_gap)
        if image_gap(floor_end) < min(image_gap(b) for b in on_deck + in_under):
            result["notes"] = ["The bag was followed off the board to the floor; the other change on the board or "
                               "under it is another bag that moved."]
            result["other_changes_not_thrown_bag"] = len(on_deck) + len(in_under)
            on_deck, in_under = [], []
    ambiguous = bool(on_deck and in_under)
    if ambiguous:
        # Two bags changed place: the thrown one and one it knocked. The thrown bag is the one at the end
        # of the tracked slide; without a slide, the hole is not claimed (needs confirmation).
        result["notes"] = ["This throw moved a bag that was already on the board."]
        deck_end = nearest(on_deck)
        under_end = nearest(in_under)
        # Both readings are kept: the side camera, which follows the thrown bag the whole way, can settle it.
        result["ambiguous_candidates"] = {
            "board": {"x_in": deck_end["deck_in"][0], "y_in_front": deck_end["deck_in"][1], "px": deck_end["centroid_px"]},
            "hole": {"x_in": HOLE_X_IN, "y_in_front": HOLE_Y_IN, "px": under_end["centroid_px"]}}
        if end_px is not None and path_starts_at_contact and image_gap(under_end) < image_gap(deck_end):
            on_deck = []
        else:
            in_under = []
        result["ambiguous"] = True
    # With no bag seen under the board, the hole is still the answer when the bag was tracked from its first
    # contact on the deck into the hole and nothing new lies elsewhere.
    tracked_into_hole = path_starts_at_contact and result["contact"] is not None and \
        in_hole(path[-1]["deck_in"], extra_in=2.0) and \
        any(not in_hole(p["deck_in"], extra_in=2.0) and point_in_deck(p["deck_in"], 0.0) for p in path[:-1])
    if on_deck:
        bag = nearest(on_deck)
        result.update(where="board", rest={"x_in": bag["deck_in"][0], "y_in_front": bag["deck_in"][1],
                                           "px": bag["centroid_px"], "area_fraction": round(bag["area_fraction"], 2)},
                      rest_basis="new bag on the deck")
    elif in_under or (tracked_into_hole and not elsewhere):
        result.update(where="hole", rest={"x_in": HOLE_X_IN, "y_in_front": HOLE_Y_IN,
                                          "px": (in_under[0]["centroid_px"] if in_under else path[-1]["px"])},
                      rest_basis="new bag under the board" if in_under else "tracked path into the hole")
    elif elsewhere:
        bag = nearest(elsewhere)
        result.update(where="off", rest={"x_in_deck_plane": bag["deck_in"][0], "px": bag["centroid_px"],
                                         "bottom_px": bag["bottom_px"]}, rest_basis="new bag on the floor")
    else:
        # Nothing new on the deck, under the board or on the floor in view. The deck is fully visible, so the
        # bag is not on the board and not in the hole; where it went is unknown (hidden in front of the board
        # or out of view). `deck_clear` lets the side camera's board phase settle "off the board".
        result.update(status="unavailable", where=None, rest=None, deck_clear=True,
                      reason="No new bag was found on the board, in the hole or on the floor in view after the throw.")
    return result


# ------------------------------------------------------------------------------------------------
# Frontal-plane body measures (front-camera pose).

FRONT_POSE_MIN_CONFIDENCE = 0.3


def _joint(pose_frames: Sequence[dict[str, Any]], frame: int, name: str) -> np.ndarray | None:
    if not 0 <= frame < len(pose_frames):
        return None
    point = (pose_frames[frame] or {}).get(name)
    if point is None:
        return None
    x, y, c = point
    if x is None or y is None or not np.isfinite([x, y]).all() or (c is not None and c < FRONT_POSE_MIN_CONFIDENCE):
        return None
    return np.array([x, y], float)


def _mean_joint(pose_frames, frame: int, name: str, half_window: int = 1) -> np.ndarray | None:
    points = [p for f in range(frame - half_window, frame + half_window + 1) if (p := _joint(pose_frames, f, name)) is not None]
    return np.mean(points, axis=0) if points else None


def camera_roll_deg(corners_px: np.ndarray) -> float:
    """The front camera's roll: the board's back edge is level, so its slope in the image is the roll."""
    c = np.asarray(corners_px, float)
    back_right_img, back_left_img = c[2], c[3]       # image left → image right along the back edge
    return float(math.degrees(math.atan2(back_left_img[1] - back_right_img[1], back_left_img[0] - back_right_img[0])))


def frontal_metrics(pose_frames: Sequence[dict[str, Any]], release_frame: int, fps: float, throwing_side: str,
                    camera: dict[str, Any] | None, release_distance_m: float | None, roll_deg: float = 0.0
                    ) -> dict[str, Any]:
    """Frontal-plane measures at release from the front camera's 2D pose.

    The front camera looks straight down the throw line, so its image plane is the athlete's frontal
    plane (within the camera's small offset). All angles are image angles; signs are in the thrower's
    frame (the image is mirrored: the thrower's right is the image's left).

    * ``trunk_side_lean_deg`` — hip centre → shoulder centre against vertical; + = towards the throwing arm.
    * ``shoulder_tilt_deg`` — shoulder line against horizontal; + = throwing shoulder lower.
    * ``arm_across_body_sw`` — throwing wrist's sideways position relative to the throwing shoulder at
      release, in shoulder widths; + = towards the body's midline (across the body), − = away from it. A
      straight pendulum swing in the throw plane gives ≈ 0.
    * ``follow_through_across_sw`` — the same 0.15 s after release (where the hand finishes).
    * ``release_point_offset_m`` — the throwing wrist's sideways distance from the board's centre line
      at release (needs the calibrated camera and the side camera's release distance).
    * ``stance_offset_m`` / ``stance_width_m`` — feet midpoint and spacing on the floor 1 s before release.

    Image angles are corrected for the camera's roll (``roll_deg``, from the board's level back edge).
    """
    sign_side = 1.0 if throwing_side == "right" else -1.0
    t_side = throwing_side
    o_side = "left" if throwing_side == "right" else "right"
    out: dict[str, Any] = {"camera_roll_deg": {"value": float(roll_deg), "unit": "°", "label": "Front camera roll (corrected)",
                                               "status": "measured", "reason": None}}

    def put(key: str, value: float | None, unit: str, label: str, reason: str | None = None, status: str = "measured"):
        out[key] = {"value": None if value is None or not np.isfinite(value) else float(value), "unit": unit,
                    "label": label, "status": status if value is not None and np.isfinite(value) else "unavailable",
                    "reason": reason if value is None or not np.isfinite(value) else None}

    f = int(release_frame)
    ls, rs = _mean_joint(pose_frames, f, "left_shoulder"), _mean_joint(pose_frames, f, "right_shoulder")
    lh, rh = _mean_joint(pose_frames, f, "left_hip"), _mean_joint(pose_frames, f, "right_hip")
    wrist = _mean_joint(pose_frames, f, f"{t_side}_wrist")
    shoulder = _mean_joint(pose_frames, f, f"{t_side}_shoulder")
    missing = "The front camera did not see these joints clearly at release."
    # Image x grows to the thrower's LEFT (mirror), so thrower-frame sideways = -image x.
    if ls is not None and rs is not None and lh is not None and rh is not None:
        sc, hc = (ls + rs) / 2, (lh + rh) / 2
        trunk = sc - hc                        # image vector, y down
        lean_image = math.degrees(math.atan2(trunk[0], -trunk[1])) - roll_deg  # + = top of trunk towards image right (roll removed)
        # Image right = thrower's left. Towards the throwing arm (right-hander: thrower's right = image left) is −image.
        put("trunk_side_lean_deg", -sign_side * lean_image, "°", "Trunk side lean at release (+ towards throwing arm)")
        t_sh, o_sh = (rs, ls) if throwing_side == "right" else (ls, rs)
        tilt = math.degrees(math.atan2(t_sh[1] - o_sh[1], abs(t_sh[0] - o_sh[0]) + 1e-9))   # + = throwing shoulder lower
        # Roll: a camera rolled clockwise (+ roll, back edge sloping down to the image right) makes the image-right
        # shoulder look lower; the throwing shoulder is image-left for a right-hander.
        tilt += roll_deg if throwing_side == "right" else -roll_deg
        put("shoulder_tilt_deg", tilt, "°", "Shoulder tilt at release (+ throwing shoulder lower)")
    else:
        put("trunk_side_lean_deg", None, "°", "Trunk side lean at release", missing)
        put("shoulder_tilt_deg", None, "°", "Shoulder tilt at release", missing)
    shoulder_width = float(np.linalg.norm(ls - rs)) if ls is not None and rs is not None else None
    if wrist is not None and shoulder is not None and shoulder_width and shoulder_width > 3:
        # Midline direction in the image: from the throwing shoulder towards the other shoulder.
        other = _mean_joint(pose_frames, f, f"{o_side}_shoulder")
        towards_mid = np.sign((other - shoulder)[0]) if other is not None else (1.0 if throwing_side == "right" else -1.0)
        put("arm_across_body_sw", towards_mid * (wrist[0] - shoulder[0]) / shoulder_width, "shoulder widths",
            "Hand across the body at release (+ towards the midline)")
        f2 = f + int(round(0.15 * fps))
        w2, s2 = _mean_joint(pose_frames, f2, f"{t_side}_wrist"), _mean_joint(pose_frames, f2, f"{t_side}_shoulder")
        if w2 is not None and s2 is not None:
            put("follow_through_across_sw", towards_mid * (w2[0] - s2[0]) / shoulder_width, "shoulder widths",
                "Hand across the body 0.15 s after release (+ towards the midline)")
        else:
            put("follow_through_across_sw", None, "shoulder widths", "Hand across the body after release", missing)
    else:
        put("arm_across_body_sw", None, "shoulder widths", "Hand across the body at release", missing)
        put("follow_through_across_sw", None, "shoulder widths", "Hand across the body after release", missing)
    # Metric positions need the camera model. When it is withheld (misplaced deck corners) that is the reason
    # given, not a missing joint.
    pose = (camera or {}).get("pose")
    status = "measured" if (camera or {}).get("status") == "measured" else "estimated"
    no_camera = (camera or {}).get("pose_withheld") or (camera or {}).get("reason") \
        or "The front camera's position could not be worked out from the board."
    if pose is not None and wrist is not None and release_distance_m is not None:
        point = ray_to_plane_y(pose, wrist, -release_distance_m)
        put("release_point_offset_m", None if point is None else point[0], "m",
            "Release hand's distance from the board's centre line (+ thrower's right)", status=status)
    elif pose is None:
        put("release_point_offset_m", None, "m", "Release hand's distance from the board's centre line", no_camera)
    elif wrist is None:
        put("release_point_offset_m", None, "m", "Release hand's distance from the board's centre line",
            "The front camera did not see the release hand clearly.")
    else:
        put("release_point_offset_m", None, "m", "Release hand's distance from the board's centre line",
            "Needs the side camera's release distance.")
    setup = max(0, f - int(round(1.0 * fps)))
    feet = []
    for side in ("left", "right"):
        p = _mean_joint(pose_frames, setup, f"{side}_ankle", half_window=2)
        feet.append(None if p is None or pose is None else ray_to_floor(pose, p, height_m=0.07))
    if pose is not None and all(p is not None for p in feet):
        put("stance_offset_m", float((feet[0][0] + feet[1][0]) / 2), "m",
            "Feet midpoint from the board's centre line 1 s before release (+ thrower's right)", status=status)
        put("stance_width_m", float(abs(feet[0][0] - feet[1][0])), "m", "Sideways distance between the ankles", status=status)
    else:
        why = no_camera if pose is None else "Ankles not seen clearly."
        put("stance_offset_m", None, "m", "Feet midpoint from the board's centre line", why)
        put("stance_width_m", None, "m", "Sideways distance between the ankles", why)
    return out


def pose_frames_from_sequence(sequence) -> list[dict[str, tuple[float | None, float | None, float | None]]]:
    """Canonical PoseSequence → per-frame {joint: (x, y, confidence)}."""
    frames = []
    for frame in sequence.frames:
        frames.append({name: (p.x, p.y, p.confidence) for name, p in frame.landmarks.items()})
    return frames


# ------------------------------------------------------------------------------------------------
# Heading: the bag's sideways direction from release to the board.


def heading(release_offset_m: float | None, contact_x_in: float | None, release_distance_m: float | None,
            contact_along_in: float | None, board: Board = Board()) -> dict[str, Any]:
    """Sideways launch direction, from where the hand released the bag to where it first touched.

    heading = atan((X_contact − X_release) / (distance from release to the board front + horizontal
    distance up the deck to contact)). + = to the thrower's right. The sideways miss it implies at the
    hole's distance is reported too, so "aim" and "standing off-centre" can be told apart.
    """
    if contact_x_in is None or release_distance_m is None:
        return {"status": "unavailable", "deg": None,
                "reason": "Needs the bag's first contact across the board and the release distance."}
    x_contact = (contact_x_in - HOLE_X_IN) * INCH_M
    along = (contact_along_in if contact_along_in is not None else HOLE_Y_IN) * INCH_M * math.cos(board.angle)
    run = release_distance_m + along
    x_release = release_offset_m if release_offset_m is not None else 0.0
    deg = math.degrees(math.atan2(x_contact - x_release, run))
    hole_run = release_distance_m + board.hole_along * math.cos(board.angle)
    at_hole = x_release + math.tan(math.radians(deg)) * hole_run
    return {"status": "measured" if release_offset_m is not None else "estimated", "deg": deg,
            "release_offset_m": release_offset_m, "contact_offset_m": x_contact,
            "sideways_at_hole_in": at_hole / INCH_M,
            # Without the release hand the split into aim and standing position is unknown (missing stays missing).
            "from_aim_in": (at_hole - x_release) / INCH_M if release_offset_m is not None else None,
            "from_release_position_in": x_release / INCH_M if release_offset_m is not None else None,
            "reason": None if release_offset_m is not None else
            "Release hand not located in the front view; heading assumes a release on the centre line."}
