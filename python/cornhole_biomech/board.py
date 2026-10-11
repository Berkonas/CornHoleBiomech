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
# Where the gravity calibration may FIND the field of view. Wider than the band above (which still
# sets the reported scale uncertainty): the Final Data Collection side phone (iPhone 15 Pro Max,
# 1080p 60 fps, 1×, stabilisation on) solved at 55.0° exactly — on the old search edge, which
# flagged every throw's metre values although gravity matched within 0.003 m/s².
SEARCH_HFOV_RANGE_DEG = (45.0, 85.0)
MIN_VALID_HFOV_SAMPLES = 3          # fewer PnP-solvable field-of-view grid points cannot bracket a root
MIN_SESSION_THROWS = 3              # fewer measured per-throw HFOVs cannot pool a "measured" session estimate
MAX_SESSION_IQR_DEG = 6.0           # wider per-throw HFOV spread cannot pool a "measured" session estimate
MAX_SESSION_DEVIATION_DEG = 8.0     # a member farther than this from the session median is reported as an outlier
SESSION_HFOV_SOURCE = "session_median_gravity_fov"
LIBRARY_HFOV_SOURCE = "library_median_gravity_fov"   # fallback for a session with too few measured throws
MIDPOINT_PROBE_FRACTIONS = (0.05, -0.05, 0.1, -0.1, 0.2, -0.2)   # of the current bracket span, tried in order
HFOV_ACCEL_TOLERANCE_M_S2 = 0.5     # |a_y - (-g)| at most this close still counts as "measured" when bisection stalls
MAX_PHI_DEG = 20.0
MIN_DECK_AREA_FRACTION = 0.0015     # red deck + dark rim, of the image; a lone bag is ~0.0002
MIN_RED_AREA_FRACTION = 0.0004      # red part alone (pilot decks: 0.0006–0.0012; white stripe covers the rest)
MIN_CONFIDENCE = 0.75                # shape evidence alone (max 0.5) is not enough: the hole must agree
MAX_PNP_RESIDUAL_FRACTION = 0.03    # of the quad's width; pilot apron quads 0.8–2.2 %, wrong quads 5–10 %
RED_HUE_MAX, RED_HUE_MIN = 10, 150  # OpenCV hue (0–180): red wraps, h <= 10 or h >= 150
RED_MIN_SAT = 40                    # pilot decks: median S 55–84, 10th percentile ≈ 44
# Retried in order, apron path only, when the standard pass finds no board. Task 8c: 10 of 26
# pilot plates (8 of 11 for Player 3) show a paler, smaller deck — median S 26–34 and only
# 680–1 764 deck px with S >= 40, against 1 425–3 282 on the 16 found — so no quad survived at
# 40. With this cascade all 10 are found, some at 30 and some at 25; which of the two wins can
# differ between the in-memory plate and its JPEG copy. Apron-only quads at S >= 30 or 25 lie
# within 5 px of the same board's quad at S >= 40 (within 7 px all the way down to S >= 10).
# Rim candidates stay at the standard threshold: at S >= 20 a rim candidate on a pink TV-screen
# banner scored 1.0 and beat the real board, whereas apron-only detection gave no wrong "found"
# on any pilot plate down to S >= 10.
RELAXED_RED_MIN_SATS = (30, 25)
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

    def deck_inches_lifted(self, points_px: np.ndarray, lift_m: float) -> np.ndarray:
        """(u, v) deck inches of image points that lie `lift_m` above the deck surface (e.g. a bag's centre).

        Each pixel's viewing ray (camera pose from the board corners) is intersected with the plane parallel to the
        deck at that height, then expressed as u across (0 = far side, 24 = camera side) and v up the deck from the
        front edge. From a side camera the across direction runs nearly along the line of sight, so treating a bag's
        centre as if it lay ON the deck shifts u by several inches; this removes that bias. Rows whose ray does not
        meet the plane in front of the camera are NaN.
        """
        pts = np.asarray(points_px, float).reshape(-1, 2)
        R = cv2.Rodrigues(np.asarray(self.rvec, float))[0]
        t = np.asarray(self.tvec, float).ravel()
        centre = -R.T @ t
        b = self.board
        alpha, half_width = b.angle, b.width_m / 2
        origin = np.array([0.0, b.front_height_m, -half_width])           # front-far corner (u = 0, v = 0)
        normal = np.array([-math.sin(alpha), math.cos(alpha), 0.0])
        along = np.array([math.cos(alpha), math.sin(alpha), 0.0])
        rays = (R.T @ np.linalg.inv(self.K) @ np.column_stack([pts, np.ones(len(pts))]).T).T
        denom = rays @ normal
        out = np.full((len(pts), 2), np.nan)
        ok = np.abs(denom) > 1e-9
        s = np.where(ok, (lift_m - (centre - origin) @ normal) / np.where(ok, denom, 1.0), np.nan)
        ok &= s > 0
        world = centre + s[:, None] * rays
        out[ok, 0] = (world[ok, 2] + half_width) / INCH_M
        out[ok, 1] = ((world[ok] - origin) @ along) / INCH_M
        return out

    def as_dict(self) -> dict[str, Any]:
        return {"corners_px": self.corners_px.tolist(), "hfov_deg": self.hfov_deg, "phi_deg": self.phi_deg,
                "phi_status": "measured" if self.phi_deg <= MAX_PHI_DEG else "estimated",
                "phi_reason": None if self.phi_deg <= MAX_PHI_DEG else
                f"Throw line is {self.phi_deg:.0f}° out of the image plane (> {MAX_PHI_DEG:.0f}°); plane distances "
                "depend strongly on the assumed field of view.",
                "plane_H": self.plane_H.tolist(), "deck_H": self.deck_H.tolist(),
                "front_height_in": self.board.front_height_m / INCH_M}


def _physical_pose(object_points: np.ndarray, corners: np.ndarray, K: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Board pose from four coplanar corners, choosing the physically possible one of IPPE's two solutions.

    A planar target seen at a grazing angle has two poses that reproject almost equally well: the real one and
    its mirror, which puts the camera on the FAR side of the board, metres up, with the throw line tilted
    ~40° out of the image. Taking the smaller reprojection error alone picked the mirror on some tripod clips
    (tilting the throw plane, so distance and scale were wrong, and flipping left/right on the deck). The
    corners are ordered so the near side (lower in the image) is +z, so the camera must be at z > 0 and above
    the floor; among such poses the best-fitting one wins, and the best overall is used only if none is.
    """
    try:
        count, rvecs, tvecs, errors = cv2.solvePnPGeneric(object_points, corners, K, None, flags=cv2.SOLVEPNP_IPPE)
    except cv2.error:
        count = 0
    if not count:
        ok, rvec, tvec = cv2.solvePnP(object_points, corners, K, None, flags=cv2.SOLVEPNP_IPPE)
        if not ok:
            raise ValueError("Board pose could not be solved from these corners.")
        return rvec, tvec
    candidates = []
    for rvec, tvec, error in zip(rvecs, tvecs, np.asarray(errors, float).reshape(-1)):
        R = cv2.Rodrigues(rvec)[0]
        centre = -R.T @ np.asarray(tvec, float).ravel()
        physical = centre[2] > 0 and centre[1] > 0.05
        candidates.append((not physical, float(error), rvec, tvec))
    candidates.sort(key=lambda c: (c[0], c[1]))
    return candidates[0][2], candidates[0][3]


def camera_height_m(model: "BoardModel") -> float:
    """Height of the camera above the floor implied by the board pose (metres)."""
    R = cv2.Rodrigues(np.asarray(model.rvec, float))[0]
    return float((-R.T @ np.asarray(model.tvec, float).ravel())[1])


# A real side-view setup has the camera on a tripod or in a hand: 0.1-4 m above the floor. A "board" implying
# a camera 7 m up is something else red and rectangular (a screen, a sign) seen high in the picture.
CAMERA_HEIGHT_RANGE_M = (0.1, 4.0)


def solve_board(corners_px: np.ndarray, image_size: tuple[int, int], board: Board = Board(),
                hfov_deg: float = NOMINAL_HFOV_DEG) -> BoardModel:
    corners = np.asarray(corners_px, float).reshape(4, 2)
    K = camera_matrix(image_size[0], image_size[1], hfov_deg)
    rvec, tvec = _physical_pose(_deck_object_points(board), corners, K)
    R = cv2.Rodrigues(rvec)[0]
    phi = math.degrees(math.asin(min(1.0, abs(R[2, 0]))))
    plane_H = K @ np.column_stack([R[:, 0], R[:, 1], tvec.ravel()])
    deck_uv = np.array([[0, 0], [24, 0], [24, 48], [0, 48]], np.float32)
    deck_H = cv2.getPerspectiveTransform(corners.astype(np.float32), deck_uv)
    return BoardModel(corners, hfov_deg, K, rvec, tvec, phi, plane_H, deck_H, board)


def calibrate_hfov_from_flight(corners_px, image_size: tuple[int, int], points_px, frames, fps: float,
                               board: Board = Board(), hfov_range: tuple[float, float] = HFOV_RANGE_DEG,
                               grid_deg: float = 0.25, min_points: int = 6,
                               search_range: tuple[float, float] | None = None) -> dict[str, Any]:
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

    `solve_board`'s PnP can fail at some HFOVs even when it succeeds at others (a degenerate pose
    for that particular assumed focal length); every candidate HFOV is solved defensively, a
    failure just drops that one grid point, and fewer than `MIN_VALID_HFOV_SAMPLES` solvable
    points in the whole band falls back to the nominal HFOV (status "estimated") rather than
    raising. A failure exactly at a bisection midpoint is not simply skipped (that would recompute
    the same failing point every remaining iteration): nearby points are probed
    (`MIDPOINT_PROBE_FRACTIONS` of the current bracket span, alternating sides) and the first one
    that solves takes the midpoint's place in the bisection; if none of them solve either,
    bisection stops and falls back to whichever already-solved bracket endpoint is nearer, with
    status "measured" only if its own vertical acceleration is within `HFOV_ACCEL_TOLERANCE_M_S2`
    of gravity, otherwise "estimated". `gravity_fit_used` in the result is true only when the
    returned HFOV came from comparing the flight's own acceleration against gravity (the
    "measured" case, the real "never crosses -g" edge case, and the stalled-bisection fallback,
    all of which use an actually-solved point's own acceleration); it is false only for a nominal
    fallback (too few flight points, too few solvable HFOVs, or a non-finite fit).
    """
    from .bag import GRAVITY_M_S2
    lo, hi = hfov_range                     # reported scale band (uncertainty)
    s_lo, s_hi = search_range or hfov_range  # where the root may be found
    pts = np.asarray(points_px, float).reshape(-1, 2) if len(points_px) else np.zeros((0, 2))
    fr = np.asarray(frames, float)
    release_px = (float(pts[0, 0]), float(pts[0, 1])) if len(pts) else None

    def try_solve(hfov: float) -> BoardModel | None:
        try:
            return solve_board(corners_px, image_size, board, hfov_deg=hfov)
        except ValueError:
            return None

    def ppm_labeled() -> dict[str, float | None]:
        out: dict[str, float | None] = {}
        for h, key in ((lo, "pixels_per_meter_at_55_deg"), (hi, "pixels_per_meter_at_75_deg")):
            model = try_solve(h) if release_px is not None else None
            value = model.pixels_per_meter_at(release_px) if model is not None else None
            out[key] = float(value) if value is not None and math.isfinite(value) else None
        return out

    def package(hfov: float, status: str, reason: str | None, a_y_band_edges: list[float] | None,
               horizontal: float | None, gravity_fit_used: bool) -> dict[str, Any]:
        model = try_solve(hfov)
        if model is None:
            # The chosen HFOV itself cannot be solved: report it unmeasurable rather than raising.
            status, gravity_fit_used = "estimated", False
            solve_failure = f"The board's pose could not be solved at {hfov:.1f}°."
            reason = f"{solve_failure} {reason}" if reason else solve_failure
        ppm = model.pixels_per_meter_at(release_px) if model is not None and release_px is not None else None
        if ppm is not None and not math.isfinite(ppm):
            ppm = None
        return {"status": status, "hfov_deg": float(hfov), "phi_deg": model.phi_deg if model is not None else None,
                "pixels_per_meter": ppm, **ppm_labeled(),
                "a_y_band_edges_m_s2": a_y_band_edges, "horizontal_acceleration_m_s2": horizontal,
                "reason": reason, "gravity_fit_used": gravity_fit_used, "model": model}

    if len(pts) < min_points or len(pts) != len(fr):
        return package(NOMINAL_HFOV_DEG, "estimated",
                       f"Only {len(pts)} flight point(s); {min_points} are needed to calibrate the field of "
                       f"view from gravity. Using the nominal {NOMINAL_HFOV_DEG:.0f}°.", None, None, False)

    t = (fr - fr[0]) / fps
    target = -GRAVITY_M_S2

    def vertical_accel(hfov: float) -> float | None:
        model = try_solve(hfov)
        if model is None:
            return None
        xy = model.to_plane(pts)
        return float(2 * np.polyfit(t, xy[:, 1], 2)[0])

    def horizontal_accel(hfov: float) -> float | None:
        model = try_solve(hfov)
        if model is None:
            return None
        xy = model.to_plane(pts)
        return float(2 * np.polyfit(t, xy[:, 0], 2)[0])

    def probe_near(mid: float, span: float, lo_bound: float, hi_bound: float) -> tuple[float, float] | None:
        """A bisection midpoint failed to solve (a degenerate pose there): try nearby points
        within the current bracket, and return the first (hfov, vertical_accel) that solves."""
        for frac in MIDPOINT_PROBE_FRACTIONS:
            candidate = mid + frac * span
            if not (lo_bound < candidate < hi_bound):
                continue
            value = vertical_accel(candidate)
            if value is not None:
                return candidate, value
        return None

    steps = max(2, int(round((s_hi - s_lo) / grid_deg)))
    grid = np.linspace(s_lo, s_hi, steps + 1)
    scanned = [(float(h), vertical_accel(float(h))) for h in grid]
    valid = [(h, a) for h, a in scanned if a is not None]
    if len(valid) < MIN_VALID_HFOV_SAMPLES:
        return package(NOMINAL_HFOV_DEG, "estimated",
                       f"The board's pose could only be solved at {len(valid)} of {len(scanned)} field-of-view "
                       f"values tried in the {s_lo:.0f}-{s_hi:.0f}° band ({MIN_VALID_HFOV_SAMPLES} are needed to "
                       f"calibrate from gravity). Using the nominal {NOMINAL_HFOV_DEG:.0f}°.", None, None, False)
    a_y_band_edges = [valid[0][1], valid[-1][1]]
    diffs = [a - target for _, a in valid]
    bracket = None
    fa = fb = None
    for i in range(len(valid) - 1):
        if diffs[i] == 0:
            bracket, fa, fb = (valid[i][0], valid[i][0]), diffs[i], diffs[i]
            break
        if (diffs[i] > 0) != (diffs[i + 1] > 0):
            bracket, fa, fb = (valid[i][0], valid[i + 1][0]), diffs[i], diffs[i + 1]
            break
    if bracket is None:
        hfov = valid[0][0] if abs(diffs[0]) <= abs(diffs[-1]) else valid[-1][0]
        reason = (f"The flight's vertical acceleration ({valid[0][1]:.2f} to {valid[-1][1]:.2f} m/s^2 across the "
                 f"band) never matches gravity ({-target:.2f} m/s^2) in the {s_lo:.0f}-{s_hi:.0f}° HFOV band; "
                 f"using the {'lower' if hfov == valid[0][0] else 'upper'} edge. The scale is flagged.")
        horiz = horizontal_accel(hfov)
        if horiz is None or not (math.isfinite(hfov) and math.isfinite(horiz)):
            return package(NOMINAL_HFOV_DEG, "estimated",
                           "The gravity fit did not converge to a finite result; using the nominal "
                           f"{NOMINAL_HFOV_DEG:.0f}°.", a_y_band_edges, None, False)
        return package(hfov, "estimated", reason, a_y_band_edges, horiz, True)
    a, b = bracket
    mid = 0.5 * (a + b)
    stalled = False
    for _ in range(40):
        if b - a < 1e-4:
            break
        span = b - a
        mid = 0.5 * (a + b)
        fm = vertical_accel(mid)
        used = mid
        if fm is None:
            probe = probe_near(mid, span, a, b)
            if probe is None:
                stalled = True     # neither the midpoint nor nearby probes solve: stop bisecting
                break
            used, fm = probe
        fm -= target
        if fm == 0:
            a, fa, b, fb = used, fm, used, fm
            break
        if (fm > 0) == (fa > 0):
            a, fa = used, fm
        else:
            b, fb = used, fm
    if stalled:
        # Both bracket endpoints are already-solved points by construction (from the grid scan,
        # or from an earlier successful bisection/probe step): use whichever is nearer to where
        # the search stalled, rather than discarding it for the nominal HFOV.
        hfov, residual = (a, fa) if abs(mid - a) <= abs(mid - b) else (b, fb)
        status = "measured" if abs(residual) <= HFOV_ACCEL_TOLERANCE_M_S2 else "estimated"
        reason = None if status == "measured" else (
            f"Bisection could not refine the field of view near {mid:.2f}° (the board's pose could "
            f"not be solved there or nearby); using the closer already-solved {hfov:.2f}°, whose "
            f"vertical acceleration is {residual + target:.2f} m/s^2 (target {-target:.2f} m/s^2).")
        horiz = horizontal_accel(hfov)
        if horiz is None or not (math.isfinite(hfov) and math.isfinite(horiz)):
            return package(NOMINAL_HFOV_DEG, "estimated",
                           "The gravity fit did not converge to a finite result; using the nominal "
                           f"{NOMINAL_HFOV_DEG:.0f}°.", a_y_band_edges, None, False)
        return package(hfov, status, reason, a_y_band_edges, horiz, True)
    hfov = 0.5 * (a + b)
    horiz = horizontal_accel(hfov)
    if horiz is None or not (math.isfinite(hfov) and math.isfinite(horiz)):
        return package(NOMINAL_HFOV_DEG, "estimated",
                       "The gravity fit did not converge to a finite result; using the nominal "
                       f"{NOMINAL_HFOV_DEG:.0f}°.", a_y_band_edges, None, False)
    return package(hfov, "measured", None, a_y_band_edges, horiz, True)


def pool_session_hfov(calibrations: list[dict[str, Any]], scope: str = "session") -> dict[str, Any]:
    """Pool one recording session's per-throw gravity HFOV calibrations into one session estimate.

    A single throw's ~0.4 s free flight gives a noisy vertical-acceleration fit, so its
    gravity-calibrated HFOV (`calibrate_hfov_from_flight`) can vary by ten-plus degrees between
    throws filmed on the same phone from the same spot in one sitting; the true camera HFOV does
    not change throw to throw. Pooling the session's own measured (gravity-fit) per-throw HFOVs
    with a median removes most of that per-throw noise from every throw's metric scale.

    `calibrations` is a list of `{"trial_id": ..., "hfov_deg": ..., "status": ...}` (or superset
    dicts, e.g. a throw's persisted `results.json["scale"]` fields); only items with
    `status == "measured"` count. Status "measured" requires at least `MIN_SESSION_THROWS`
    measured throws whose HFOVs' IQR is at most `MAX_SESSION_IQR_DEG`; otherwise "estimated" with
    a reason. No measured throw at all gives "unavailable". `scope` names the pool in the reasons.
    """
    measured = [c for c in calibrations if c.get("status") == "measured" and c.get("hfov_deg") is not None]
    n = len(measured)
    if n == 0:
        return {"hfov_deg": None, "status": "unavailable", "n": 0, "iqr_deg": None, "spread_deg": None,
                "members": [], "outliers": [],
                "reason": f"No throw in this {scope} had a field of view measured from gravity.",
                "source": SESSION_HFOV_SOURCE}
    values = np.array([float(c["hfov_deg"]) for c in measured], float)
    members = [c.get("trial_id") for c in measured]
    median = float(np.median(values))
    spread = float(values.max() - values.min())
    iqr = float(np.percentile(values, 75) - np.percentile(values, 25)) if n >= 2 else None
    outliers = [tid for tid, v in zip(members, values) if abs(v - median) > MAX_SESSION_DEVIATION_DEG]
    base = {"hfov_deg": median, "n": n, "iqr_deg": iqr, "spread_deg": spread,
            "members": members, "outliers": outliers, "source": SESSION_HFOV_SOURCE}
    if n < MIN_SESSION_THROWS:
        return {**base, "status": "estimated",
                "reason": f"Only {n} throw(s) in this {scope} had a field of view measured from gravity; at "
                          f"least {MIN_SESSION_THROWS} are needed to pool a {scope} estimate confidently."}
    if iqr is not None and iqr > MAX_SESSION_IQR_DEG:
        return {**base, "status": "estimated",
                "reason": f"This {scope}'s {n} measured field-of-view calibrations spread over an IQR of "
                          f"{iqr:.1f}° (> {MAX_SESSION_IQR_DEG:.1f}°); the per-throw values disagree too much "
                          f"to pool as one measured {scope} field of view."}
    return {**base, "status": "measured", "reason": None}


def pool_library_hfov(calibrations: list[dict[str, Any]], session: dict[str, Any] | None = None) -> dict[str, Any]:
    """Library-wide fallback for a session with fewer than `MIN_SESSION_THROWS` measured throws.

    Pools every measured per-throw calibration of the library run (all sessions) with the same
    median/n/IQR rules as `pool_session_hfov`. It rests on an unverified assumption -- every
    session was filmed with the same camera and zoom -- so its status is at most "estimated"
    (spec §8: nothing "measured" depends on an assumed input), with that assumption as the reason;
    `pool_status` keeps what the pool's own median/n/IQR rules gave. `session` (that session's
    own pool) is kept for reference.
    """
    pooled = pool_session_hfov(calibrations, scope="library run")
    note = (f"This session had fewer than {MIN_SESSION_THROWS} throws with a field of view measured from gravity, "
            f"so the median of all {pooled['n']} measured throws in this library run is used; this assumes the "
            "same camera and zoom in every session, which is not verified, so the field of view is estimated.")
    reason = note if pooled["status"] == "measured" else f"{note} {pooled['reason']}"
    status = "estimated" if pooled["status"] == "measured" else pooled["status"]
    return {**pooled, "status": status, "pool_status": pooled["status"], "source": LIBRARY_HFOV_SOURCE,
            "reason": reason, "session_pool": session}


def _red_and_rim(plate: np.ndarray, min_sat: int = RED_MIN_SAT) -> tuple[np.ndarray, np.ndarray]:
    hsv = cv2.cvtColor(plate, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    red = (((h <= RED_HUE_MAX) | (h >= RED_HUE_MIN)) & (s >= min_sat) & (v >= RED_MIN_VAL)).astype(np.uint8)
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
    boards' look) a dark near-side apron with red deck showing along its top. When nothing is
    found at the standard red saturation, the apron path is retried at each of
    `RELAXED_RED_MIN_SATS` (pale decks); every retry passes the same PnP, hole and
    observed-corner gates. `red_min_sat` reports the threshold of the returned result; with no
    board found, the most confident candidate of all passes is kept for pre-filling clicks.
    """
    result = _detect_board_at(plate, target_direction, board, RED_MIN_SAT, use_rims=True)
    for min_sat in RELAXED_RED_MIN_SATS:
        if result["status"] == "found":
            break
        retry = _detect_board_at(plate, target_direction, board, min_sat, use_rims=False)
        if retry["status"] == "found" or retry["confidence"] > result["confidence"]:
            result = retry
    return result


def _detect_board_at(plate: np.ndarray, target_direction: str, board: Board, min_sat: int,
                     use_rims: bool) -> dict[str, Any]:
    red, dark = _red_and_rim(plate, min_sat)
    # A rim grown into an apron (or a visible end face) puts corners at the apron's floor edge
    # instead of the deck edge, so a rim quad is dropped where an apron quad covers the same
    # deck (synthetic pilot-look boards: such rim quads were 25–37 px off yet passed the hole
    # check). Conservative: an apron quad later rejected by PnP still suppresses the rim quad.
    aprons = _apron_candidates(red, dark, target_direction, board)
    rims = [(q, s, True) for q, s in (_rim_candidates(red, dark, target_direction) if use_rims else [])
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
                "red_min_sat": min_sat,
                "reasons": ["No red deck with a dark rim or apron large enough to be a regulation board was found."]}
    observed = best.pop("corners_observed")
    best["red_min_sat"] = min_sat
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
