"""Regulation board → metric throw plane.

Detection: red deck + dark rim, or red deck above a dark near-side apron, on the
background plate → deck quadrilateral, confirmed by the hole.
Pose: solvePnP (IPPE, 4 coplanar deck corners with the regulation slope) under an
assumed horizontal field of view; the FOV range gives the scale uncertainty.
Throw plane: the vertical plane through the board centreline (athlete and bag are
assumed to move in it; out-of-plane angle φ is reported, > 20° is flagged).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from .regulation import INCH_M, Board

NOMINAL_HFOV_DEG = 65.0
HFOV_RANGE_DEG = (55.0, 75.0)
MAX_PHI_DEG = 20.0
MIN_DECK_AREA_FRACTION = 0.0015     # red deck + dark rim, of the image; a lone bag is ~0.0002
MIN_RED_AREA_FRACTION = 0.0004      # red part alone (pilot decks: 0.0006–0.0012; white stripe covers the rest)
MIN_CONFIDENCE = 0.75                # shape evidence alone (max 0.5) is not enough: the hole must agree
MAX_PNP_RESIDUAL_FRACTION = 0.03    # of the quad's width; pilot apron quads 0.8–2.2 %, wrong quads 5–10 %
RED_HUE_MAX, RED_HUE_MIN = 10, 150  # OpenCV hue (0–180): red wraps, h <= 10 or h >= 150
RED_MIN_SAT = 40                    # pilot decks: median S 55–84, 10th percentile ≈ 44
RED_MIN_VAL = 50
DARK_MAX_VAL = 70
RIM_GROW_FRACTION = 0.08            # rim growth limit as a fraction of the red component's width
MIN_APRON_AREA_FRACTION = 0.0005    # pilot aprons: 5 000–8 000 px of 2 073 600
APRON_MIN_ASPECT = 4.0              # pilot aprons: length / thickness 5.8–7.2
APRON_MIN_RED_FRACTION = 0.5        # pilot aprons: 0.71–0.90 of columns show red deck just above
HOLE_LOCAL_CONTRAST = 0.2           # black-hat depth / deck median; pilot hole blobs at 0.2: 690–880 px of ~1 000
HOLE_KERNEL_IN = 8                  # black-hat kernel diameter, larger than the 6 in hole
HOLE_TOLERANCE_IN = 4.0             # hole centroid within this of (12, 39) in; pilot plates measured 0.9–1.5 in
HOLE_MIN_AREA_FRACTION = 0.1        # of the 3 in radius hole's area in the rectified deck
EDGE_TOL_PX = 2.0                   # edge-line inlier tolerance (blurred plate edges scatter ~1 px)
HIDDEN_FRONT_CORNER_REASON = "The board's front corner is hidden; click the four deck corners."
END_FACE_MIN_PX = 3                 # band end this far beyond the near edge's end = a visible end face


def camera_matrix(width: int, height: int, hfov_deg: float) -> np.ndarray:
    f = (width / 2) / math.tan(math.radians(hfov_deg) / 2)
    return np.array([[f, 0, width / 2], [0, f, height / 2], [0, 0, 1]], float)


def _deck_object_points(board: Board) -> np.ndarray:
    Lh, fh, w = board.horizontal_length_m, board.front_height_m, board.width_m
    bh = fh + board.length_m * math.sin(board.angle)
    return np.array([[0, fh, -w / 2], [0, fh, w / 2], [Lh, bh, w / 2], [Lh, bh, -w / 2]], float)


def order_corners(quad: np.ndarray, target_direction: str) -> np.ndarray:
    """front-far, front-near, back-near, back-far. Front = end nearer the thrower; near = lower in image."""
    q = np.asarray(quad, float).reshape(4, 2)
    sign = 1.0 if target_direction == "left_to_right" else -1.0
    by_along = q[np.argsort(sign * q[:, 0])]
    front, back = by_along[:2], by_along[2:]
    front = front[np.argsort(front[:, 1])]   # smaller y (higher in image) = far side
    back = back[np.argsort(back[:, 1])]
    return np.array([front[0], front[1], back[1], back[0]])


@dataclass
class BoardModel:
    corners_px: np.ndarray
    hfov_deg: float
    K: np.ndarray
    rvec: np.ndarray
    tvec: np.ndarray
    phi_deg: float
    plane_H: np.ndarray
    deck_H: np.ndarray
    board: Board = field(default_factory=Board)

    def to_plane(self, points_px: np.ndarray) -> np.ndarray:
        p = cv2.perspectiveTransform(np.asarray(points_px, float).reshape(-1, 1, 2), np.linalg.inv(self.plane_H))
        return p.reshape(-1, 2)

    def to_deck_inches(self, points_px: np.ndarray) -> np.ndarray:
        return cv2.perspectiveTransform(np.asarray(points_px, float).reshape(-1, 1, 2), self.deck_H).reshape(-1, 2)

    def pixels_per_meter_at(self, point_px) -> float:
        p = np.asarray(point_px, float)
        a, b = self.to_plane(np.array([p, p + [1.0, 0.0]]))
        return 1.0 / max(1e-9, float(np.hypot(*(b - a))))

    def along_precision_in_per_px(self, point_px) -> float:
        p = np.asarray(point_px, float)
        a, b = self.to_plane(np.array([p, p + [1.0, 0.0]]))
        return abs(float(b[0] - a[0])) / INCH_M

    def across_precision_in_per_px(self, point_px) -> float:
        p = np.asarray(point_px, float)
        a, b = self.to_deck_inches(np.array([p, p + [0.0, 1.0]]))
        return abs(float(b[0] - a[0]))

    def as_dict(self) -> dict[str, Any]:
        return {"corners_px": self.corners_px.tolist(), "hfov_deg": self.hfov_deg, "phi_deg": self.phi_deg,
                "phi_status": "measured" if self.phi_deg <= MAX_PHI_DEG else "estimated",
                "phi_reason": None if self.phi_deg <= MAX_PHI_DEG else
                f"Throw line is {self.phi_deg:.0f}° out of the image plane (> {MAX_PHI_DEG:.0f}°); plane distances "
                "depend strongly on the assumed field of view.",
                "plane_H": self.plane_H.tolist(), "deck_H": self.deck_H.tolist(),
                "front_height_in": self.board.front_height_m / INCH_M}


def solve_board(corners_px: np.ndarray, image_size: tuple[int, int], board: Board = Board(),
                hfov_deg: float = NOMINAL_HFOV_DEG) -> BoardModel:
    corners = np.asarray(corners_px, float).reshape(4, 2)
    K = camera_matrix(image_size[0], image_size[1], hfov_deg)
    ok, rvec, tvec = cv2.solvePnP(_deck_object_points(board), corners, K, None, flags=cv2.SOLVEPNP_IPPE)
    if not ok:
        raise ValueError("Board pose could not be solved from these corners.")
    R = cv2.Rodrigues(rvec)[0]
    phi = math.degrees(math.asin(min(1.0, abs(R[2, 0]))))
    plane_H = K @ np.column_stack([R[:, 0], R[:, 1], tvec.ravel()])
    deck_uv = np.array([[0, 0], [24, 0], [24, 48], [0, 48]], np.float32)
    deck_H = cv2.getPerspectiveTransform(corners.astype(np.float32), deck_uv)
    return BoardModel(corners, hfov_deg, K, rvec, tvec, phi, plane_H, deck_H, board)


def calibrate_hfov_from_flight(corners_px, image_size: tuple[int, int], points_px, frames, fps: float,
                               board: Board = Board(), hfov_range: tuple[float, float] = HFOV_RANGE_DEG,
                               grid_deg: float = 0.25, min_points: int = 6) -> dict[str, Any]:
    """Find the HFOV in `hfov_range` whose board-plane vertical acceleration matches gravity.

    A single still image cannot separate a wide lens seen from close up from a narrow lens seen
    from far away: both project the same board corners for a suitable camera distance, but they
    disagree about the metric scale of everything else in the frame. The bag's own free flight
    does not have that ambiguity — it obeys -9.80665 m/s^2 regardless of the lens — so matching
    it pins down the otherwise-free HFOV parameter and, with it, the whole plane's metric scale.

    `points_px`/`frames` are one accepted flight's release-frame (camera-motion-removed) pixel
    points and their frame indices, in flight order; `points_px[0]` is taken as the release
    point, at which the returned pixels-per-metre scale (and its 55-75 deg band) is evaluated.
    Each candidate HFOV re-solves the board's PnP pose from the same corners and image size, and
    maps the flight through that pose's plane homography (`BoardModel.to_plane`) into the
    board's own metres; the vertical (height) coordinate's quadratic-fit acceleration a_y(HFOV)
    is compared with gravity.

    A root of a_y(HFOV) = -g strictly inside `hfov_range` (bracketed by a `grid_deg` grid search,
    then refined by bisection) gives status "measured". If a_y never crosses -g in the band, the
    closer edge is used with status "estimated" and a reason (`a_y_band_edges_m_s2` reports both
    ends). Fewer than `min_points` flight points cannot be fit at all; the nominal HFOV is used,
    status "estimated".
    """
    from .bag import GRAVITY_M_S2
    lo, hi = hfov_range
    pts = np.asarray(points_px, float).reshape(-1, 2) if len(points_px) else np.zeros((0, 2))
    fr = np.asarray(frames, float)
    release_px = (float(pts[0, 0]), float(pts[0, 1])) if len(pts) else None

    def solve_at(hfov: float) -> BoardModel:
        return solve_board(corners_px, image_size, board, hfov_deg=hfov)

    def ppm_band() -> list[float] | None:
        if release_px is None:
            return None
        values = [solve_at(h).pixels_per_meter_at(release_px) for h in (lo, hi)]
        return sorted(values) if all(math.isfinite(v) for v in values) else None

    def package(hfov: float, status: str, reason: str | None,
               a_y_band_edges: list[float] | None, horizontal: float | None) -> dict[str, Any]:
        model = solve_at(hfov)
        ppm = model.pixels_per_meter_at(release_px) if release_px is not None else None
        if ppm is not None and not math.isfinite(ppm):
            ppm = None
        return {"status": status, "hfov_deg": float(hfov), "phi_deg": model.phi_deg,
                "pixels_per_meter": ppm, "pixels_per_meter_band": ppm_band(),
                "a_y_band_edges_m_s2": a_y_band_edges, "horizontal_acceleration_m_s2": horizontal,
                "reason": reason, "model": model}

    if len(pts) < min_points or len(pts) != len(fr):
        return package(NOMINAL_HFOV_DEG, "estimated",
                       f"Only {len(pts)} flight point(s); {min_points} are needed to calibrate the field of "
                       f"view from gravity. Using the nominal {NOMINAL_HFOV_DEG:.0f}°.", None, None)

    t = (fr - fr[0]) / fps
    target = -GRAVITY_M_S2

    def vertical_accel(hfov: float) -> float:
        xy = solve_at(hfov).to_plane(pts)
        return float(2 * np.polyfit(t, xy[:, 1], 2)[0])

    def horizontal_accel(hfov: float) -> float:
        xy = solve_at(hfov).to_plane(pts)
        return float(2 * np.polyfit(t, xy[:, 0], 2)[0])

    steps = max(2, int(round((hi - lo) / grid_deg)))
    grid = np.linspace(lo, hi, steps + 1)
    accel = [vertical_accel(h) for h in grid]
    a_y_band_edges = [accel[0], accel[-1]]
    diffs = [a - target for a in accel]
    bracket = None
    for i in range(len(grid) - 1):
        if diffs[i] == 0:
            bracket = (float(grid[i]), float(grid[i]))
            break
        if (diffs[i] > 0) != (diffs[i + 1] > 0):
            bracket = (float(grid[i]), float(grid[i + 1]))
            break
    if bracket is None:
        hfov = lo if abs(diffs[0]) <= abs(diffs[-1]) else hi
        reason = (f"The flight's vertical acceleration ({accel[0]:.2f} to {accel[-1]:.2f} m/s^2 across the "
                 f"band) never matches gravity ({-target:.2f} m/s^2) in the {lo:.0f}-{hi:.0f}° HFOV band; "
                 f"using the {'lower' if hfov == lo else 'upper'} edge. The scale is flagged.")
        horiz = horizontal_accel(hfov)
        if not (math.isfinite(hfov) and math.isfinite(horiz)):
            return package(NOMINAL_HFOV_DEG, "estimated",
                           "The gravity fit did not converge to a finite result; using the nominal "
                           f"{NOMINAL_HFOV_DEG:.0f}°.", a_y_band_edges, None)
        return package(hfov, "estimated", reason, a_y_band_edges, horiz)
    a, b = bracket
    fa = vertical_accel(a) - target
    for _ in range(40):
        if b - a < 1e-4:
            break
        mid = 0.5 * (a + b)
        fm = vertical_accel(mid) - target
        if fm == 0:
            a = b = mid
            break
        if (fm > 0) == (fa > 0):
            a, fa = mid, fm
        else:
            b = mid
    hfov = 0.5 * (a + b)
    horiz = horizontal_accel(hfov)
    if not (math.isfinite(hfov) and math.isfinite(horiz)):
        return package(NOMINAL_HFOV_DEG, "estimated",
                       "The gravity fit did not converge to a finite result; using the nominal "
                       f"{NOMINAL_HFOV_DEG:.0f}°.", a_y_band_edges, None)
    return package(hfov, "measured", None, a_y_band_edges, horiz)


def _red_and_rim(plate: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    hsv = cv2.cvtColor(plate, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    red = (((h <= RED_HUE_MAX) | (h >= RED_HUE_MIN)) & (s >= RED_MIN_SAT) & (v >= RED_MIN_VAL)).astype(np.uint8)
    dark = (v <= DARK_MAX_VAL).astype(np.uint8)
    return red, dark


def _grow_into_rim(component: np.ndarray, dark: np.ndarray, radius: int) -> np.ndarray:
    """Geodesic growth of the red component through connected dark (rim) pixels, at most `radius` steps."""
    allowed = dark | component
    region = component.copy()
    kernel = np.ones((3, 3), np.uint8)
    for _ in range(radius):
        grown = cv2.dilate(region, kernel) & allowed
        if np.array_equal(grown, region):
            break
        region = grown
    return region


def detect_board(plate: np.ndarray, target_direction: str, board: Board = Board()) -> dict[str, Any]:
    """Find the deck quad on a clean plate; `found` needs the shape evidence and the hole to agree.

    Two candidate sources: a red deck grown into a dark rim that frames it, and (the pilot
    boards' look) a dark near-side apron with red deck showing along its top.
    """
    red, dark = _red_and_rim(plate)
    # A rim grown into an apron (or a visible end face) puts corners at the apron's floor edge
    # instead of the deck edge, so a rim quad is dropped where an apron quad covers the same
    # deck (synthetic pilot-look boards: such rim quads were 25–37 px off yet passed the hole
    # check). Conservative: an apron quad later rejected by PnP still suppresses the rim quad.
    aprons = _apron_candidates(red, dark, target_direction, board)
    rims = [(q, s, True) for q, s in _rim_candidates(red, dark, target_direction)
            if not any(_quads_overlap(q, a) for a, _, _ in aprons)]
    candidates = aprons + rims
    height, width = plate.shape[:2]
    best = None
    for quad, shape_score, corners_observed in candidates:
        if _pnp_residual_px(quad, (width, height), board) > MAX_PNP_RESIDUAL_FRACTION * np.ptp(quad[:, 0]):
            continue      # not a projected regulation deck
        hole_offset = _hole_offset_in(plate, quad)
        confidence = 0.5 * shape_score + (0.5 if hole_offset is not None and hole_offset <= HOLE_TOLERANCE_IN else 0.0)
        if best is None or confidence > best["confidence"]:
            best = {"corners_px": quad.tolist(), "confidence": confidence, "hole_offset_in": hole_offset,
                    "corners_observed": corners_observed}
    if best is None:
        return {"status": "not_found", "corners_px": None, "confidence": 0.0, "hole_offset_in": None,
                "reasons": ["No red deck with a dark rim or apron large enough to be a regulation board was found."]}
    observed = best.pop("corners_observed")
    if best["confidence"] < MIN_CONFIDENCE:
        return {**best, "status": "not_found",
                "reasons": [f"Best board candidate has confidence {best['confidence']:.2f} (< {MIN_CONFIDENCE}); "
                            "click the four deck corners instead."]}
    if not observed:
        # The front-far corner came from the PnP scan at the nominal FOV, not from the image:
        # synthetic boards showed it 15–21 px (3–4 in) off while the hole still agreed.
        return {**best, "status": "not_found", "reasons": [HIDDEN_FRONT_CORNER_REASON]}
    return {**best, "status": "found", "reasons": []}


def _quads_overlap(a: np.ndarray, b: np.ndarray) -> bool:
    inter, _ = cv2.intersectConvexConvex(np.float32(a), np.float32(b))
    return inter > 0


def _rim_candidates(red: np.ndarray, dark: np.ndarray, target_direction: str) -> list[tuple[np.ndarray, float]]:
    height, width = red.shape
    red = cv2.morphologyEx(red, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(red, 8)
    out = []
    for i in range(1, count):
        if stats[i, cv2.CC_STAT_AREA] < MIN_RED_AREA_FRACTION * width * height:
            continue
        x, y, w, h = (int(v) for v in stats[i, :4])
        radius = max(4, int(round(RIM_GROW_FRACTION * w)))
        x0, y0 = max(0, x - radius - 2), max(0, y - radius - 2)
        x1, y1 = min(width, x + w + radius + 2), min(height, y + h + radius + 2)
        component = (labels[y0:y1, x0:x1] == i).astype(np.uint8)
        region = _grow_into_rim(component, dark[y0:y1, x0:x1], radius)
        if region.sum() < MIN_DECK_AREA_FRACTION * width * height:
            continue
        contours, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        hull = cv2.convexHull(max(contours, key=cv2.contourArea)) + np.array([x0, y0])
        quad = _four_corners(hull)
        if quad is None:
            continue
        ordered = order_corners(quad, target_direction)
        if np.ptp(ordered[:, 0]) < np.ptp(ordered[:, 1]):     # a side-view deck is wider than tall in the image
            continue
        fill = float(region.sum()) / max(1.0, cv2.contourArea(ordered.astype(np.float32)))
        out.append((ordered, min(1.0, fill / 0.6)))
    return out


def _apron_candidates(red: np.ndarray, dark: np.ndarray, target_direction: str,
                      board: Board = Board()) -> list[tuple[np.ndarray, float, bool]]:
    """Dark band much longer (in x) than thick — the near-side apron — with red deck along its top edge.

    Near edge = top of the band; far edge = top of the red directly above it. Near corners
    end where the band's top leaves the near-edge line, back-far where the red along the far
    edge ends. If the band continues past the front-near corner (a visible front face), its
    front column is the observed front-far corner. Otherwise front-far is inferred: searched
    along the far edge from a little ahead of the band's front end to the first red, keeping
    the position whose regulation-deck PnP fit has the smallest residual. Each candidate is
    (quad, shape score, front-far corner observed).
    """
    height, width = dark.shape
    band = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    band = cv2.morphologyEx(band, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(band, 8)
    out = []
    for i in range(1, count):
        if stats[i, cv2.CC_STAT_AREA] < MIN_APRON_AREA_FRACTION * width * height:
            continue
        x, y, w, h = (int(v) for v in stats[i, :4])
        if w < APRON_MIN_ASPECT * h * 0.5:       # cheap reject before the per-column scan
            continue
        mask = labels[y:y + h, x:x + w] == i
        present = mask.any(axis=0)
        top = np.where(present, mask.argmax(axis=0), -1) + y
        bottom = np.where(present, h - 1 - mask[::-1].argmax(axis=0), -1) + y
        thick = float(np.median((bottom - top)[present] + 1))
        if present.sum() < APRON_MIN_ASPECT * thick:
            continue
        cols = np.arange(x, x + w)
        far = np.full(w, -1)
        reach = int(math.ceil(2 * thick))
        for j in np.nonzero(present)[0]:
            y0 = max(0, top[j] - reach)
            hits = np.nonzero(red[y0:top[j], cols[j]])[0]
            if len(hits):
                far[j] = y0 + hits[0]
        red_fraction = float(np.mean(far[present] >= 0))
        if red_fraction < APRON_MIN_RED_FRACTION:
            continue
        lo, hi = cols[present].min(), cols[present].max()
        inner = present & (cols > lo + 0.05 * (hi - lo)) & (cols < hi - 0.05 * (hi - lo))
        near_line, _ = _robust_line(cols[inner], top[inner])
        has_far = far >= 0
        far_line, far_inliers = _robust_line(cols[has_far], far[has_far])
        if near_line is None or far_line is None:
            continue
        far_cols = cols[has_far][far_inliers]
        # The band can include an end face of the board (pilot boards: the front face, seen
        # because the camera stands ahead of the board's side). Its top edge climbs toward
        # the far corner, above the near line, so the near corners are where the band's
        # top leaves the near-edge line, not the band's extreme columns.
        near_lo, near_hi = _line_extent(cols, top, present, near_line, inner, max(2.0, 0.25 * thick))
        front_x, back_x = (near_lo, near_hi) if target_direction == "left_to_right" else (near_hi, near_lo)
        band_front = lo if target_direction == "left_to_right" else hi
        front_far_x, back_far_x = ((far_cols.min(), far_cols.max()) if target_direction == "left_to_right"
                                   else (far_cols.max(), far_cols.min()))
        on = lambda line, xv: [xv, line[0] * xv + line[1]]   # noqa: E731
        size = (red.shape[1], red.shape[0])
        best_quad, best_residual = None, math.inf
        step = 1 if target_direction == "left_to_right" else -1
        observed_front_far = abs(front_x - band_front) >= END_FACE_MIN_PX
        if observed_front_far:
            # A visible front face ends at the front-far corner: the band's front column.
            front_far_candidates = [band_front]
        else:
            start = front_x - step * int(0.15 * (hi - lo))   # the front-far corner can sit ahead of the band's end
            front_far_candidates = np.arange(start, front_far_x + step, step)
        for x_ff in front_far_candidates:
            quad = order_corners(np.array([on(far_line, x_ff), on(near_line, front_x),
                                           on(near_line, back_x), on(far_line, back_far_x)], float), target_direction)
            front_depth, back_depth = quad[1, 1] - quad[0, 1], quad[2, 1] - quad[3, 1]
            if back_depth <= 0 or front_depth < 0.25 * back_depth:    # far edge must stay above the near edge
                continue
            residual = _pnp_residual_px(quad, size, board)
            if residual < best_residual:
                best_quad, best_residual = quad, residual
        if best_quad is None:
            continue
        out.append((best_quad, red_fraction, observed_front_far))
    return out


def _line_extent(cols: np.ndarray, top: np.ndarray, present: np.ndarray, line: tuple[float, float],
                 inner: np.ndarray, tol: float, run: int = 3) -> tuple[int, int]:
    """Columns where the band's top edge stops following `line`, walking out from its fitted span.

    Walking from the middle of the fitted (inner) columns toward each band end, the edge ends
    at the first run of `run` present columns whose top lies more than `tol` px above the line
    (an end face rising toward the far side); otherwise it reaches the band's end.
    """
    above = present & (top < line[0] * cols + line[1] - tol)
    idx = np.nonzero(inner)[0]
    middle = int(idx[len(idx) // 2])

    def walk(start: int, stop: int, step: int) -> int:
        last, streak = start, 0
        for j in range(start, stop, step):
            if not present[j]:
                continue
            if above[j]:
                streak += 1
                if streak >= run:
                    return last
            else:
                streak, last = 0, j
        return last

    return int(cols[walk(middle, -1, -1)]), int(cols[walk(middle, len(cols), 1)])


def _pnp_residual_px(corners: np.ndarray, image_size: tuple[int, int], board: Board) -> float:
    """Largest corner reprojection error of the regulation deck posed on these corners (nominal FOV)."""
    K = camera_matrix(image_size[0], image_size[1], NOMINAL_HFOV_DEG)
    obj = _deck_object_points(board)
    try:
        ok, rvec, tvec = cv2.solvePnP(obj, corners.astype(float), K, None, flags=cv2.SOLVEPNP_IPPE)
        if not ok:
            return math.inf
        projected, _ = cv2.projectPoints(obj, rvec, tvec, K, None)
    except cv2.error:
        return math.inf
    return float(np.abs(projected.reshape(-1, 2) - corners).max())


def _robust_line(xs: np.ndarray, ys: np.ndarray,
                 tol: float = EDGE_TOL_PX) -> tuple[tuple[float, float] | None, np.ndarray]:
    """y = a·x + b followed by the most columns within `tol` px; returns (a, b), inlier mask.

    Consensus over point pairs (deterministic sample), then two least-squares refits on the
    inliers. Residual clipping alone failed on the pilot far edges, where about a third of the
    columns are other edges (the deck graphic behind a stripe, the back edge): it kept them
    all, tilted the line and put P1's back-far corner ~45 px beyond the deck.
    """
    xs, ys = np.asarray(xs, float), np.asarray(ys, float)
    keep = np.ones(len(xs), bool)
    if len(xs) < 5:
        return None, keep
    sample = np.unique(np.linspace(0, len(xs) - 1, min(len(xs), 40)).astype(int))
    best = None
    for k, i in enumerate(sample):
        for j in sample[k + 1:]:
            if xs[j] == xs[i]:
                continue
            a = (ys[j] - ys[i]) / (xs[j] - xs[i])
            inliers = np.abs(ys - (a * xs + ys[i] - a * xs[i])) <= tol
            if best is None or inliers.sum() > best.sum():
                best = inliers
    keep = best if best is not None else keep
    for _ in range(2):
        if keep.sum() < 5:
            return None, keep
        a, b = np.polyfit(xs[keep], ys[keep], 1)
        keep = np.abs(ys - (a * xs + b)) <= tol
    if keep.sum() < 5:
        return None, keep
    return (float(a), float(b)), keep


def _four_corners(hull: np.ndarray) -> np.ndarray | None:
    perimeter = cv2.arcLength(hull, True)
    for eps in np.linspace(0.01, 0.1, 19):
        approx = cv2.approxPolyDP(hull, eps * perimeter, True)
        if len(approx) == 4:
            return approx.reshape(4, 2).astype(float)
    return None


def _hole_offset_in(plate: np.ndarray, corners: np.ndarray, px_per_in: int = 6) -> float | None:
    """Rectify the deck and return the distance (in) from (12 in, 39 in from the front) to the
    nearest hole-like dark blob, or None if there is none.

    Dark = locally darker than the surrounding deck (black-hat with a kernel larger than the
    hole) by HOLE_LOCAL_CONTRAST of the deck's median brightness. On the pilot plates the hole
    is only a faint shadowed crescent (0.58–0.62 of the median, no darker than the deck's pink
    stripe), but it stands out locally; broad stripes do not. Blobs touching the rectified
    border are rim or apron slivers from imperfect corners. Deck graphics (a logo near the
    front on the pilot boards) can be larger than the hole, so the blob nearest the expected
    position is used; `found` still needs it within HOLE_TOLERANCE_IN on a regulation-shaped quad.
    """
    dst = np.array([[0, 0], [24, 0], [24, 48], [0, 48]], np.float32) * px_per_in
    M = cv2.getPerspectiveTransform(corners.astype(np.float32), dst)
    deck = cv2.warpPerspective(plate, M, (24 * px_per_in, 48 * px_per_in))
    gray = cv2.cvtColor(deck, cv2.COLOR_BGR2GRAY)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (HOLE_KERNEL_IN * px_per_in + 1,) * 2)
    local = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, kernel).astype(float)
    margin = 2 * px_per_in
    inner = local[margin:-margin, margin:-margin]
    dark = (inner > HOLE_LOCAL_CONTRAST * max(1.0, float(np.median(gray[margin:-margin, margin:-margin])))
            ).astype(np.uint8)
    count, _, stats, centroids = cv2.connectedComponentsWithStats(dark, 8)
    ih, iw = inner.shape
    x, y, w, h, area = (stats[1:, k] for k in range(5))
    interior = (x > 0) & (y > 0) & (x + w < iw) & (y + h < ih)    # rim/apron slivers touch the border
    holelike = interior & (area >= HOLE_MIN_AREA_FRACTION * math.pi * (3 * px_per_in) ** 2)
    if not holelike.any():
        return None
    uv = (centroids[1:] + margin) / px_per_in
    offsets = np.hypot(uv[:, 0] - 12.0, uv[:, 1] - 39.0)
    return float(offsets[holelike].min())


def transfer_corners(src_plate: np.ndarray, dst_plate: np.ndarray, corners_px) -> np.ndarray | None:
    """Carry clicked corners from one clip's plate to another shot from the same position."""
    orb = cv2.ORB_create(3000)
    a = orb.detectAndCompute(cv2.cvtColor(src_plate, cv2.COLOR_BGR2GRAY), None)
    b = orb.detectAndCompute(cv2.cvtColor(dst_plate, cv2.COLOR_BGR2GRAY), None)
    if a[1] is None or b[1] is None:
        return None
    matches = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(a[1], b[1])
    if len(matches) < 30:
        return None
    src = np.float32([a[0][m.queryIdx].pt for m in matches])
    dst = np.float32([b[0][m.trainIdx].pt for m in matches])
    M, inliers = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=3.0)
    if M is None or int(inliers.sum()) < 20:
        return None
    c = np.asarray(corners_px, float).reshape(4, 2)
    return (M[:, :2] @ c.T).T + M[:, 2]
