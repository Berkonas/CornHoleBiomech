"""The bag's flight in 3D from the two cameras (side + front).

Each camera alone sees the flight badly in one direction. The side camera sees the throw plane well — along
the throw and height, metric through the board and the gravity-calibrated field of view (§1.7–§1.8) — but not
left/right. The front camera, behind the board looking back at the thrower, sees left/right but the bag flies
almost straight at it: it moves little in the picture, grows, and crosses a busy background, so tracking it
there on its own (``front_track.flight_path``) is fragile.

This module joins the two with physics. The bag is one drag-free projectile in the board's world frame
(front_view: X to the thrower's right, Y along the throw from the board's front edge, Z up, metres):

    Y(τ) = a0 + a1·τ + a2·τ²          along the throw   } from the side camera (its measured flight, the
    Z(τ) = b0 + b1·τ + b2·τ²          height            }  side rays put at the bag's lateral position)
    X(τ) = X0 + Vx·τ                  left/right: no sideways force on a drag-free bag

with τ the time since release on the side clock. Only X0 and Vx (plus a small timing offset δ within the
sound sync's tolerance) are unknown. The side flight fixes, for every front frame, where the bag must be
along the throw and how high, so a candidate blob in the front image gives one lateral position by
intersecting its viewing ray with the plane Y = Y(τ), and its height and size must agree with the side
camera's. A straight line in time through those lateral positions (RANSAC, then robust least squares of the
image residuals) is the bag; clutter (the thrower, bystanders, the wall) does not follow it. The front
camera's first contact on the deck, when measured, is a check and an end constraint.

Outputs (``flight_3d`` in two_view.json and flight3d.json): lateral release position, lateral velocity and
launch angle, the predicted lateral landing against the measured one, the 3D path samples for an animation
and the projected image path for the replay. Missing stays missing: without an accepted side flight, a metric
side scale, a calibrated front camera or enough front frames on the line, nothing is reported.

Methods and thresholds: docs/METHODS_AND_MATH.md §5.4 ("3D flight from two views").
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Sequence

import cv2
import numpy as np

from .regulation import BAG_SIDE_M, INCH_M, Board

FLIGHT3D_VERSION = "flight3d_v1"
FLIGHT3D_FILENAME = "flight3d.json"

# --- Front-camera candidates (front_track's colour + motion test, half resolution) -------------------------
SEARCH_SCALE = 0.5
# --- Association gates (full-resolution pixels) ------------------------------------------------------------
VERTICAL_GATE_PX = 30.0           # candidate height vs the side camera's height at that instant, first pass
VERTICAL_GATE_SIZE_SHARE = 0.5    # ... plus this share of the expected bag size (px)
LATERAL_TOL_PX = 6.0              # RANSAC / refinement inlier tolerance on the image, plus a share of bag size
LATERAL_TOL_SIZE_SHARE = 0.5
AREA_RATIO_MIN, AREA_RATIO_MAX = 0.05, 2.5   # blob area / face-on bag area at the predicted depth
RANSAC_ITERATIONS = 400
MIN_SAMPLE_GAP = 3                # front frames between the two candidates of a RANSAC sample
TIMING_LIMIT_FRAMES = 4.0         # δ within ±4 front frames: the sync check's agreement limit (two_view.sync_check)
GRID_TIMING_STEP_FRAMES = 0.5
GRID_HFOV_STEP_DEG = 1.0
FRONT_HFOV_BAND_DEG = 8.0         # the bag may re-estimate the front field of view this far from the pooled one
                                  # (two_view.MAX_HFOV_DEVIATION_DEG: beyond it the deck corners are suspect)
# --- Acceptance -------------------------------------------------------------------------------------------
MIN_INLIER_FRAMES = 6
MIN_INLIER_SHARE = 0.3            # of the front frames from release to first contact
MIN_END_COVERAGE = 0.5            # share of frames with the bag in the first and in the last third of the flight
MAX_RMS_TOLERANCE_SHARE = 0.5    # RMS of (residual / inlier tolerance) over the inlier frames
MAX_RELEASE_LATERAL_M = 1.5       # pitcher's box: 3 ft each side of the board's 2 ft width
MAX_LAUNCH_ANGLE_DEG = 15.0
CONTACT_AGREE_IN = 6.0            # front first contact used as an end constraint only within one bag width
CONTACT_SIGMA_IN = 1.0            # its weight: ±0.5 in homography precision + the bag's own size on the deck
PIXEL_SIGMA_PX = 3.0              # typical front detection noise; the contact residual is scaled to it
PATH_SAMPLE_HZ = 60.0
BAG_CENTRE_HEIGHT_M = 0.6 * INCH_M   # a bag's centre above the surface it lands on (board_phase.BAG_CENTRE_HEIGHT_IN)
MAX_FLIGHT_S = 3.0                # search limit for the arc's landing (library flights last 1.0–1.4 s)


# ------------------------------------------------------------------------------------------------
# Side camera: rays in the board's frame and the along/height model.


def side_rays(corners_px: Sequence[Sequence[float]], image_size: tuple[int, int], hfov_deg: float,
              points_px: np.ndarray) -> tuple[np.ndarray, np.ndarray, Any]:
    """Camera centre and ray directions (side-board frame: x along, y up, z across, +z the camera side) for
    release-frame pixels, with the board pose solved at ``hfov_deg`` (board.solve_board)."""
    from .board import solve_board
    model = solve_board(np.asarray(corners_px, float), image_size, hfov_deg=float(hfov_deg))
    R = cv2.Rodrigues(np.asarray(model.rvec, float))[0]
    t = np.asarray(model.tvec, float).ravel()
    centre = -R.T @ t
    pts = np.asarray(points_px, float).reshape(-1, 2)
    rays = (R.T @ np.linalg.inv(model.K) @ np.column_stack([pts, np.ones(len(pts))]).T).T
    return centre, rays, model


def rays_at_lateral(centre: np.ndarray, rays: np.ndarray, lateral_z: np.ndarray) -> np.ndarray:
    """Points (x along, y up) where each ray meets the vertical plane z = lateral_z (side-board frame)."""
    z = np.broadcast_to(np.asarray(lateral_z, float), (len(rays),))
    s = (z - centre[2]) / np.where(np.abs(rays[:, 2]) < 1e-12, 1e-12, rays[:, 2])
    pts = centre[None, :] + s[:, None] * rays
    return pts[:, :2]


def _quad_fit(tau: np.ndarray, values: np.ndarray, weights: np.ndarray) -> np.ndarray:
    A = np.column_stack([np.ones_like(tau), tau, tau * tau]) * weights[:, None]
    coef, *_ = np.linalg.lstsq(A, values * weights, rcond=None)
    return coef


def side_flight(results: dict[str, Any], auto_flight: dict[str, Any], side_times: np.ndarray,
                release_side: int) -> dict[str, Any]:
    """The side camera's accepted flight as one viewing ray per measured frame, ready to be put at any lateral
    position. Returns {"status", "reason", ...}; "measured"/"estimated" carries the side scale's status.

    Only the tracked flight centres are used. The board phase's touchdown point is not: on the library it sat
    3–13 cm off the flight's own arc one frame after the last flight point (a bag centre measured on the deck by
    another method) and 1–4.6 m off on five throws whose touchdown frame came 9–28 frames later."""
    if (auto_flight or {}).get("status") != "accepted":
        return {"status": "unavailable", "reason": "The side camera's bag flight was not accepted, so the flight "
                                                   "along the throw and its height are not known."}
    scale = results.get("scale") or {}
    hfov = scale.get("hfov_deg")
    if hfov is None or scale.get("status") not in ("measured", "estimated"):
        return {"status": "unavailable", "reason": "The side camera has no metric scale for this throw ("
                + (scale.get("reason") or "field of view not calibrated") + ")."}
    board = auto_flight.get("board") or {}
    if board.get("status") != "found" or board.get("reference_frame") != auto_flight.get("release_frame"):
        return {"status": "unavailable", "reason": "The side camera's board is not in the flight's pixel frame."}
    rejected = set(((results.get("bag") or {}).get("flight_filter") or {}).get("rejected_outlier_frames") or [])
    pts = [p for p in auto_flight.get("stabilized_points") or [] if p.get("frame") not in rejected
           and p.get("x") is not None and p.get("y") is not None and 0 <= int(p["frame"]) < len(side_times)]
    if len(pts) < 6:
        return {"status": "unavailable", "reason": "Too few side-camera flight points."}
    size = (int(auto_flight.get("width") or 1920), int(auto_flight.get("height") or 1080))
    px = np.array([[p["x"], p["y"]] for p in pts], float)
    frames = np.array([int(p["frame"]) for p in pts])
    weights = np.ones(len(pts))
    try:
        centre, rays, model = side_rays(board["corners_px"], size, float(hfov), px)
    except (ValueError, cv2.error) as error:
        return {"status": "unavailable", "reason": f"The side camera's board pose could not be solved ({error})."}
    tau = np.asarray(side_times, float)[frames] - float(side_times[release_side])
    sign = 1.0 if (results.get("target_direction") or "left_to_right") == "left_to_right" else -1.0
    return {"status": scale["status"], "reason": scale.get("reason") if scale["status"] != "measured" else None,
            "hfov_deg": float(hfov), "centre": centre, "rays": rays, "tau": tau, "frames": frames,
            "weights": weights, "lateral_sign": sign,
            "release_side": int(release_side), "board": model.board}


def fit_side_model(side: dict[str, Any], lateral_x: np.ndarray | float = 0.0) -> dict[str, Any]:
    """Quadratics along(τ), height(τ) through the side rays put at lateral X (front frame, + thrower's right)."""
    z = np.broadcast_to(np.asarray(lateral_x, float), side["tau"].shape) * side["lateral_sign"]
    pts = rays_at_lateral(side["centre"], side["rays"], z)
    tau, w = side["tau"], side["weights"]
    a = _quad_fit(tau, pts[:, 0], w)
    b = _quad_fit(tau, pts[:, 1], w)
    resid = np.hypot(np.polyval(a[::-1], tau) - pts[:, 0], np.polyval(b[::-1], tau) - pts[:, 1])
    return {"along": a, "height": b, "rms_m": float(np.sqrt(np.mean(resid[w == 1] ** 2))) if np.any(w == 1) else None,
            "apparent_gravity_m_s2": float(-2 * b[2])}


def surface_time(side_model: dict[str, Any], x0: float, vx: float, t_max: float,
                 board: Board = Board()) -> tuple[float, str] | None:
    """First time (≤ t_max) the bag's centre comes down to the surface under it: the deck where the path is over
    the board's footprint, else the floor; the centre is taken BAG_CENTRE_HEIGHT_M above it (half a bag's
    thickness, board_phase). Returns (τ, "deck" | "floor") or None if it does not come down by t_max."""
    a, b = side_model["along"], side_model["height"]
    apex = -b[1] / (2 * b[2]) if b[2] < 0 else 0.0
    ts = np.arange(max(0.0, apex), t_max + 1e-9, 0.001)
    if len(ts) == 0:
        return None
    pts = model_points(side_model, x0, vx, ts)
    on_deck = (np.abs(pts[:, 0]) <= board.width_m / 2) & (pts[:, 1] >= 0) & (pts[:, 1] <= board.horizontal_length_m)
    surface = np.where(on_deck, board.front_height_m + pts[:, 1] * math.tan(board.angle), 0.0) + BAG_CENTRE_HEIGHT_M
    hit = np.nonzero(pts[:, 2] <= surface)[0]
    if len(hit) == 0:
        return None
    i = int(hit[0])
    return float(ts[i]), ("deck" if on_deck[i] else "floor")


def model_points(side_model: dict[str, Any], x0: float, vx: float, tau: np.ndarray) -> np.ndarray:
    """World points (front frame X right, Y along, Z up) at side-clock times τ."""
    tau = np.asarray(tau, float)
    a, b = side_model["along"], side_model["height"]
    return np.column_stack([x0 + vx * tau, a[0] + a[1] * tau + a[2] * tau ** 2, b[0] + b[1] * tau + b[2] * tau ** 2])


# ------------------------------------------------------------------------------------------------
# Front camera: projection with drift, candidates.


class FrontProjector:
    """Pinhole projection of world points into front frames. The pose comes from the deck corners in the
    reference frame (front_view.front_camera_pose); the phone's slow drift is the deck corners' mean shift."""

    def __init__(self, pose: dict[str, Any], corners_per_frame: np.ndarray, reference_frame: int):
        self.K = np.asarray(pose["K"], float)
        self.R = np.asarray(pose["R"], float)
        self.t = np.asarray(pose["tvec"], float).ravel()
        self.centre = np.asarray(pose["centre_m"], float)
        self.corners = np.asarray(corners_per_frame, float)
        self.reference = int(reference_frame)
        self.focal = float(self.K[0, 0])

    def shift(self, frame: int) -> np.ndarray:
        c = self.corners
        f = min(max(int(frame), 0), len(c) - 1)
        r = min(max(self.reference, 0), len(c) - 1)
        return (c[f] - c[r]).reshape(-1, 2).mean(axis=0)

    def depth(self, points: np.ndarray) -> np.ndarray:
        cam = (self.R @ np.asarray(points, float).reshape(-1, 3).T).T + self.t
        return cam[:, 2]

    def project(self, points: np.ndarray, frames: Sequence[int]) -> np.ndarray:
        pts = np.asarray(points, float).reshape(-1, 3)
        cam = (self.R @ pts.T).T + self.t
        z = np.where(cam[:, 2] < 1e-6, 1e-6, cam[:, 2])
        u = self.K[0, 0] * cam[:, 0] / z + self.K[0, 2]
        v = self.K[1, 1] * cam[:, 1] / z + self.K[1, 2]
        shifts = np.array([self.shift(f) for f in frames]).reshape(-1, 2)
        return np.column_stack([u, v]) + shifts

    def ray_to_along(self, pixel: Sequence[float], frame: int, along_m: float) -> np.ndarray | None:
        """World point on the pixel's viewing ray (drift removed) at Y = along_m."""
        p = np.asarray(pixel, float) - self.shift(frame)
        ray = self.R.T @ np.linalg.inv(self.K) @ np.array([p[0], p[1], 1.0])
        if abs(ray[1]) < 1e-9:
            return None
        s = (along_m - self.centre[1]) / ray[1]
        if s <= 0:
            return None
        return self.centre + s * ray

    def bag_area_px(self, depth_m: np.ndarray) -> np.ndarray:
        """Face-on 6 × 6 in bag area (full-res px²) at a depth."""
        return (self.focal * BAG_SIDE_M / np.maximum(np.asarray(depth_m, float), 0.3)) ** 2


def flight_candidates(frames: Sequence[np.ndarray], release_front: int, first: int, last: int,
                      corners_per_frame: np.ndarray | None, fps: float = 30.0) -> dict[int, np.ndarray]:
    """Moving bag-red blobs per front frame (front_track's colour + empty-scene + two-frame motion test), as
    arrays of [x, y, area] in full-resolution pixels."""
    from .front_track import TEMPORAL_GAP, _shift, moving_red_blobs, scene_shift
    n = len(frames)
    s = SEARCH_SCALE
    lo, hi = max(0, first - TEMPORAL_GAP), min(n, last + TEMPORAL_GAP + 1)
    small = [cv2.resize(frames[k], None, fx=s, fy=s, interpolation=cv2.INTER_AREA) for k in range(lo, hi)]
    # Empty scene as in front_track.flight_path: every 3rd frame from 2.5 s to 0.2 s before release, drift removed.
    bg_frames = list(range(max(0, release_front - int(2.5 * fps)), max(1, release_front - int(0.2 * fps)), 3))
    if len(bg_frames) < 5:
        bg_frames = list(range(0, max(1, release_front - 2)))
    stack = [_shift(cv2.resize(frames[k], None, fx=s, fy=s, interpolation=cv2.INTER_AREA),
                    -scene_shift(corners_per_frame, k, release_front) * s) for k in bg_frames]
    background = np.median(np.stack(stack), axis=0).astype(np.uint8)
    out: dict[int, np.ndarray] = {}
    for k in range(max(first, 0), min(last, n - 1) + 1):
        blobs = moving_red_blobs(small, background, k - lo, scene_shift(corners_per_frame, k, release_front) * s)
        out[k] = np.array([[b["x"] / s, b["y"] / s, b["area"] / (s * s)] for b in blobs], float).reshape(-1, 3)
    return out


# ------------------------------------------------------------------------------------------------
# The fit.


def _times(front_times: np.ndarray, frames: Sequence[int], to_side: float) -> np.ndarray:
    """Side-clock τ (since release) of front frames: τ = t_front − (side→front offset) − t_side(release)."""
    return np.asarray(front_times, float)[np.asarray(frames, int)] - to_side


def _tolerance(size_px: np.ndarray, base: float, share: float) -> np.ndarray:
    return base + share * np.asarray(size_px, float)


def _associate(side_model: dict[str, Any], projector: FrontProjector, candidates: dict[int, np.ndarray],
               ks: list[int], tau: np.ndarray, x0: float, vx: float, gate: float) -> list[dict[str, Any]]:
    """Per front frame, the candidate nearest the model's image position within ``gate`` × the inlier
    tolerance and of a plausible size for the model's depth."""
    pts = model_points(side_model, x0, vx, tau)
    pred = projector.project(pts, ks)
    size = np.sqrt(projector.bag_area_px(projector.depth(pts)))
    chosen = []
    for i, k in enumerate(ks):
        cand = candidates.get(k)
        if cand is None or len(cand) == 0:
            continue
        d = np.hypot(cand[:, 0] - pred[i, 0], cand[:, 1] - pred[i, 1])
        ratio = cand[:, 2] / (size[i] ** 2)
        tol = float(_tolerance(size[i], LATERAL_TOL_PX, LATERAL_TOL_SIZE_SHARE))
        ok = (d < gate * tol) & (ratio >= AREA_RATIO_MIN) & (ratio <= AREA_RATIO_MAX)
        if not ok.any():
            continue
        j = int(np.argmin(np.where(ok, d, np.inf)))
        chosen.append({"i": i, "frame": int(k), "px": [float(cand[j, 0]), float(cand[j, 1])],
                       "area_px": float(cand[j, 2]), "residual_px": float(d[j]),
                       "residual_uv_px": [float(cand[j, 0] - pred[i, 0]), float(cand[j, 1] - pred[i, 1])],
                       "expected_area_px": float(size[i] ** 2), "tolerance_px": tol})
    return chosen


def _ransac_lateral(side_model: dict[str, Any], projector: FrontProjector, candidates: dict[int, np.ndarray],
                    ks: list[int], tau_k: np.ndarray, rng_seed: int = 0) -> tuple[float, float] | None:
    """First guess of (X0, Vx): every candidate gives a lateral position on its viewing ray at the side
    camera's along position; candidates at the wrong height or size are dropped; RANSAC over pairs of
    candidates from different frames picks the straight line in time most candidates agree with."""
    obs = []                                  # frame index, lateral m, expected size px, depth m
    for i, k in enumerate(ks):
        cand = candidates.get(k)
        if cand is None or len(cand) == 0:
            continue
        centre_pt = model_points(side_model, 0.0, 0.0, tau_k[i:i + 1])[0]
        depth = float(projector.depth(centre_pt[None])[0])
        size = math.sqrt(float(projector.bag_area_px(depth)))
        for x, y, area in cand:
            if not AREA_RATIO_MIN <= area / (size * size) <= AREA_RATIO_MAX:
                continue
            world = projector.ray_to_along((x, y), k, centre_pt[1])
            if world is None:
                continue
            dv = (world[2] - centre_pt[2]) * projector.focal / depth
            if abs(dv) > VERTICAL_GATE_PX + VERTICAL_GATE_SIZE_SHARE * size:
                continue
            obs.append((i, float(world[0]), size, depth))
    if len({o[0] for o in obs}) < 2:
        return None
    arr = np.array(obs, float)
    idx = arr[:, 0].astype(int)
    tol = _tolerance(arr[:, 2], LATERAL_TOL_PX, LATERAL_TOL_SIZE_SHARE)
    rng = np.random.default_rng(rng_seed)
    along_v = float(side_model["along"][1])
    best = None
    for _ in range(RANSAC_ITERATIONS):
        a, b = rng.choice(len(arr), size=2, replace=False)
        if abs(ks[idx[a]] - ks[idx[b]]) < MIN_SAMPLE_GAP:
            continue
        vx = (arr[b, 1] - arr[a, 1]) / (tau_k[idx[b]] - tau_k[idx[a]])
        x0 = arr[a, 1] - vx * tau_k[idx[a]]
        if abs(x0) > 1.5 * MAX_RELEASE_LATERAL_M or abs(math.degrees(math.atan2(vx, along_v))) > 1.5 * MAX_LAUNCH_ANGLE_DEG:
            continue
        err = np.abs(arr[:, 1] - (x0 + vx * tau_k[idx])) * projector.focal / arr[:, 3]
        quality = np.where(err < tol, 1.0 - (err / tol) ** 2, 0.0)
        per_frame: dict[int, float] = {}
        for i, q in zip(idx, quality):
            per_frame[i] = max(per_frame.get(i, 0.0), q)
        score = sum(per_frame.values())
        if best is None or score > best[0]:
            best = (score, x0, vx)
    return None if best is None else (best[1], best[2])


def fit_lateral(side: dict[str, Any], make_projector, hfov0: float, candidates: dict[int, np.ndarray],
                front_times: np.ndarray, to_side: float, frame_dt: float, contact: dict[str, Any] | None = None,
                hfov_band: float = 0.0, rng_seed: int = 0) -> dict[str, Any]:
    """Lateral release position X0 and velocity Vx, the timing offset δ and the front camera's field of view.

    ``make_projector(hfov)`` gives the front camera posed from the deck corners at that field of view;
    ``to_side``: front time − to_side = side-clock τ; ``hfov_band``: the field of view may move this far from
    ``hfov0`` (0 = fixed); ``contact`` (optional): {"tau", "x_m"}, the front camera's first contact across the
    deck, used as an end constraint only when the flight alone lands within a bag width of it.
    Returns the flight-only fit and, when the contact was used, the constrained one."""
    from scipy.optimize import least_squares
    ks = sorted(candidates)
    if not ks:
        return {"status": "unavailable", "reason": "No front frames to search."}
    tau_k = _times(front_times, ks, to_side)
    side_model = fit_side_model(side, 0.0)
    projector0 = make_projector(hfov0)
    if projector0 is None:
        return {"status": "unavailable", "reason": "The front camera could not be posed from the deck corners."}
    start = _ransac_lateral(side_model, projector0, candidates, ks, tau_k, rng_seed)
    if start is None:
        return {"status": "unavailable", "reason": "The bag was not seen in the front camera where the side camera "
                                                   "puts it."}
    lo = np.array([-3.0, -5.0, -TIMING_LIMIT_FRAMES, hfov0 - hfov_band - 1e-6])
    hi = np.array([3.0, 5.0, TIMING_LIMIT_FRAMES, hfov0 + hfov_band + 1e-6])
    cache: dict[float, FrontProjector | None] = {}

    def projector_at(h: float) -> FrontProjector | None:
        key = round(float(h), 9)
        if key not in cache:
            cache[key] = make_projector(float(h))
        return cache[key]

    # Timing offset and field of view move the bag up and down in the picture (the lateral line does not depend
    # on them): a coarse grid over both, scored by how many frames have a candidate on the path, starts the
    # local refinement in the right valley.
    model0 = fit_side_model(side, start[0] + start[1] * side["tau"])
    best_grid = None
    for d_frames in np.arange(-TIMING_LIMIT_FRAMES, TIMING_LIMIT_FRAMES + 1e-9, GRID_TIMING_STEP_FRAMES):
        for h in np.arange(hfov0 - hfov_band, hfov0 + hfov_band + 1e-9, GRID_HFOV_STEP_DEG) if hfov_band else [hfov0]:
            proj = projector_at(h)
            if proj is None:
                continue
            chosen = _associate(model0, proj, candidates, ks, tau_k + d_frames * frame_dt, start[0], start[1], 1.0)
            score = sum(1.0 - (c["residual_px"] / c["tolerance_px"]) ** 2 for c in chosen)
            # Ties (flat score) go to the smallest correction from the sync and the pooled field of view.
            key = (round(score, 6), -abs(d_frames) - abs(h - hfov0) / max(hfov_band, 1.0))
            if best_grid is None or key > best_grid[0]:
                best_grid = (key, d_frames, h)
    params = np.array([start[0], start[1], best_grid[1] if best_grid else 0.0, best_grid[2] if best_grid else hfov0])

    def solve(params: np.ndarray, chosen: list[dict[str, Any]], side_model: dict[str, Any],
              with_contact: bool) -> np.ndarray:
        idx = np.array([c["i"] for c in chosen])
        obs = np.array([c["px"] for c in chosen])
        frames_sel = [ks[i] for i in idx]

        def residuals(p):
            proj = projector_at(p[3])
            if proj is None:
                return np.full(2 * len(idx) + int(with_contact), 1e3)
            pts = model_points(side_model, p[0], p[1], tau_k[idx] + p[2] * frame_dt)
            res = (proj.project(pts, frames_sel) - obs).ravel()
            if with_contact:
                x_c = p[0] + p[1] * (contact["tau"] + p[2] * frame_dt)
                res = np.append(res, (x_c - contact["x_m"]) / (CONTACT_SIGMA_IN * INCH_M) * PIXEL_SIGMA_PX)
            return res
        sol = least_squares(residuals, np.clip(params, lo, hi), bounds=(lo, hi), loss="soft_l1", f_scale=PIXEL_SIGMA_PX,
                            x_scale=np.array([0.05, 0.1, 0.3, 1.0]), diff_step=1e-4)
        return sol.x

    def run(with_contact: bool, params: np.ndarray) -> tuple[np.ndarray, dict[str, Any], list[dict[str, Any]]]:
        model = fit_side_model(side, params[0] + params[1] * side["tau"])
        for gate in (2.0, 1.5, 1.0, 1.0):
            proj = projector_at(params[3])
            chosen = _associate(model, proj, candidates, ks, tau_k + params[2] * frame_dt, params[0], params[1], gate)
            if len(chosen) < 3:
                break
            params = solve(params, chosen, model, with_contact)
            # The side rays are put at the bag's lateral position (its distance from the side camera).
            model = fit_side_model(side, params[0] + params[1] * side["tau"])
        proj = projector_at(params[3])
        chosen = _associate(model, proj, candidates, ks, tau_k + params[2] * frame_dt, params[0], params[1], 1.0)
        return params, model, chosen

    free, free_model, free_chosen = run(False, params)
    out = {"status": "fitted", "free": {"x0": float(free[0]), "vx": float(free[1]), "delta_s": float(free[2] * frame_dt),
                                        "hfov_deg": float(free[3])},
           "frames": ks, "tau": tau_k, "contact_used": False}
    final, model, chosen = free, free_model, free_chosen
    if contact is not None and contact.get("x_m") is not None:
        x_c = free[0] + free[1] * (contact["tau"] + free[2] * frame_dt)
        out["free"]["contact_x_m"] = float(x_c)
        if abs(x_c - contact["x_m"]) <= CONTACT_AGREE_IN * INCH_M:
            final, model, chosen = run(True, free)
            out["contact_used"] = True
    out.update(x0=float(final[0]), vx=float(final[1]), delta_s=float(final[2] * frame_dt), hfov_deg=float(final[3]),
               side_model=model, detections=[{k: v for k, v in c.items() if k != "i"} for c in chosen],
               projector=projector_at(final[3]))
    return out


# ------------------------------------------------------------------------------------------------
# One throw.


def reconstruct_flight(*, frames: Sequence[np.ndarray], results: dict[str, Any], auto_flight: dict[str, Any],
                       link: dict[str, Any], corners_per_frame: np.ndarray, front_hfov_deg: float | None,
                       camera_status: str | None, release_side: int | None, contact_side: int | None,
                       release_front: int | None, contact_front: int | None,
                       front_contact: dict[str, Any] | None = None, corners_suspect: bool = False,
                       frontal_release_offset_m: float | None = None, heading_deg: float | None = None,
                       candidates: dict[int, np.ndarray] | None = None, debug: bool = False) -> dict[str, Any]:
    """3D bag flight for one throw. Returns the ``flight_3d`` record (status measured / estimated / unavailable).

    ``corners_per_frame``: front deck corners per front frame (front_view.frame_corners); ``front_hfov_deg``: the
    front camera's field of view (session pool); ``release_*`` / ``contact_*``: release and first-contact frames in
    each clip (two_view ``frames``); ``front_contact``: front_view's first contact across the deck."""
    from .front_view import front_camera_pose
    out: dict[str, Any] = {"method_version": FLIGHT3D_VERSION, "status": "unavailable",
                           "frame": "x along the throw from the release point (m), y sideways from the board's centre "
                                    "line (m, + thrower's right), z height above the floor (m); t from release (s, side "
                                    "camera clock)"}

    def unavailable(reason: str) -> dict[str, Any]:
        out.update(status="unavailable", reason=reason)
        return out

    if corners_suspect:
        return unavailable("The front camera's board corners look misplaced on this take, so its position is not "
                           "known well enough to place the bag sideways.")
    if front_hfov_deg is None:
        return unavailable("The front camera's field of view is not known.")
    if release_side is None or release_front is None or not 0 <= release_front < len(frames):
        return unavailable("No release frame in both cameras.")
    side_clip = link.get("side_clip") or {}
    front_clip = link.get("front_clip") or {}
    side_fps = float((results.get("quality") or {}).get("frame_rate_fps") or side_clip.get("fps") or 60.0)
    side_times = np.asarray(side_clip.get("frame_times_s") or [], float)
    if len(side_times) == 0:
        side_times = np.arange(int(side_clip.get("frame_count") or 2000)) / side_fps
    front_fps = float(front_clip.get("fps") or 30.0)
    front_times = np.asarray(front_clip.get("frame_times_s") or [], float)
    if len(front_times) != len(frames):
        front_times = np.arange(len(frames)) / front_fps
    t0 = front_clip.get("side_frame0_front_time_s")
    if t0 is None:
        return unavailable("The two cameras are not synchronised.")
    if not 0 <= release_side < len(side_times):
        return unavailable("The release frame is outside the side clip.")
    # Front time of a side-clock instant: t_front = t_side + sound offset + picture lag (two_view.side_to_front_frame).
    to_side = float(t0) + float(link.get("front_lag_s") or 0.0) + float(side_times[release_side])
    side = side_flight(results, auto_flight, side_times, release_side)
    if side["status"] == "unavailable":
        return unavailable(side["reason"])
    # The flight ends at first contact: the side camera's contact time, or where the arc comes down to the deck or
    # the floor if that is earlier (a contact seen late, e.g. a bag that flew past the board) or there is no contact
    # time (a bag that dropped short). The search runs to the later of the two along the centre line.
    tau_contact = None
    if contact_side is not None and 0 <= contact_side < len(side_times) and contact_front is not None \
            and contact_front > release_front:
        tau_contact = float(side_times[contact_side] - side_times[release_side])
    floor = surface_time(fit_side_model(side, 0.0), 2.0, 0.0, MAX_FLIGHT_S)   # 2 m aside: the floor, never the deck
    if tau_contact is None and floor is None:
        return unavailable("No first-contact time in both cameras, so the end of the flight is not known.")
    tau_end = min(t for t in (tau_contact, floor[0] if floor else None) if t is not None)
    end_front = int(np.searchsorted(front_times, tau_end + to_side + 0.5 / front_fps, side="right")) - 1
    # From the first front frame at or after release (before it the bag is still in the hand).
    first = int(np.searchsorted(front_times, to_side - 1e-9, side="left"))
    first, last = max(first, release_front - 1, 0), min(len(frames) - 1, end_front)
    if last - first < MIN_INLIER_FRAMES:
        return unavailable("Too few front frames between release and first contact.")
    size = (int(frames[0].shape[1]), int(frames[0].shape[0]))
    corners = np.asarray(corners_per_frame, float)

    def make_projector(hfov: float) -> FrontProjector | None:
        pose = front_camera_pose(corners[release_front], size, hfov)
        return None if pose is None else FrontProjector(pose, corners, release_front)

    if candidates is None:
        candidates = flight_candidates(frames, release_front, first, last, corners, front_fps)
    contact = None
    if front_contact and front_contact.get("x_in") is not None:
        # The front camera's first contact across the deck, at the time the arc comes down to the deck (lateral
        # motion is slow: ~0.3 cm per front frame, so the exact instant matters little).
        land0 = surface_time(fit_side_model(side, 0.0), (float(front_contact["x_in"]) - 12.0) * INCH_M, 0.0, tau_end + 0.2)
        t_c = min(t for t in (tau_contact, land0[0] if land0 else None) if t is not None) if (tau_contact or land0) else None
        if t_c is not None:
            contact = {"tau": t_c, "x_m": (float(front_contact["x_in"]) - 12.0) * INCH_M}
    fit = fit_lateral(side, make_projector, float(front_hfov_deg),
                      {k: candidates.get(k, np.zeros((0, 3))) for k in range(first, last + 1)},
                      front_times, to_side, 1.0 / front_fps, contact, hfov_band=FRONT_HFOV_BAND_DEG)
    if fit["status"] != "fitted":
        return unavailable(fit["reason"])
    det = fit["detections"]
    span = last - first + 1
    x0, vx, delta = fit["x0"], fit["vx"], fit["delta_s"]
    side_model, projector = fit["side_model"], fit["projector"]
    rel = [d["residual_px"] / d["tolerance_px"] for d in det]
    out["fit"] = {"inlier_frames": len(det), "frames_searched": span,
                  "rms_px": float(np.sqrt(np.mean([d["residual_px"] ** 2 for d in det]))) if det else None,
                  "median_px": float(np.median([d["residual_px"] for d in det])) if det else None,
                  "rms_lateral_px": float(np.sqrt(np.mean([d["residual_uv_px"][0] ** 2 for d in det]))) if det else None,
                  "rms_vertical_px": float(np.sqrt(np.mean([d["residual_uv_px"][1] ** 2 for d in det]))) if det else None,
                  "rms_tolerance_share": float(np.sqrt(np.mean(np.square(rel)))) if det else None,
                  "timing_offset_s": delta, "front_hfov_deg": fit["hfov_deg"], "front_hfov_pooled_deg": float(front_hfov_deg),
                  "contact_constraint_used": fit["contact_used"], "flight_only": fit["free"],
                  "side_rms_m": side_model["rms_m"], "side_apparent_gravity_m_s2": side_model["apparent_gravity_m_s2"],
                  "side_scale_status": side["status"]}
    reasons = []
    if len(det) < max(MIN_INLIER_FRAMES, MIN_INLIER_SHARE * span):
        reasons.append(f"The bag was found on the 3D path in only {len(det)} of {span} front frames.")
    # Both ends of the flight must be seen: near the thrower (where clutter is worst) and near the board (where
    # the bag is large and alone). The middle may leave the picture on a high arc.
    thirds = np.array_split(np.arange(first, last + 1), 3)
    seen = {d["frame"] for d in det}
    coverage = [float(np.mean([k in seen for k in part])) if len(part) else 0.0 for part in thirds]
    out["fit"]["coverage_by_third"] = [round(c, 3) for c in coverage]
    if min(coverage[0], coverage[2]) < MIN_END_COVERAGE:
        reasons.append("The bag was not seen on the 3D path at both ends of its flight.")
    if det and out["fit"]["rms_tolerance_share"] > MAX_RMS_TOLERANCE_SHARE:
        reasons.append(f"The front detections sit {out['fit']['rms_px']:.1f} px (RMS) off the 3D path, too far for "
                       "the bag's size.")
    along_v = float(side_model["along"][1])
    angle = math.degrees(math.atan2(vx, along_v))
    if abs(x0) > MAX_RELEASE_LATERAL_M:
        reasons.append(f"The release would be {x0:.2f} m off the centre line, outside the pitcher's box.")
    if abs(angle) > MAX_LAUNCH_ANGLE_DEG:
        reasons.append(f"A sideways launch of {angle:.0f}° is not a throw at the board.")
    out["detections"] = [{"frame": d["frame"], "px": [round(d["px"][0], 1), round(d["px"][1], 1)],
                          "area_px": round(d["area_px"], 1), "expected_area_px": round(d["expected_area_px"], 1),
                          "residual_px": round(d["residual_px"], 2),
                          "residual_uv_px": [round(d["residual_uv_px"][0], 2), round(d["residual_uv_px"][1], 2)],
                          "tolerance_px": round(d["tolerance_px"], 2)} for d in det]
    a, b = side_model["along"], side_model["height"]
    release_along = float(a[0])
    out["release"] = {"lateral_m": x0, "height_m": float(b[0]), "to_board_front_m": -release_along}
    out["velocity_m_s"] = {"along": along_v, "lateral": vx, "vertical": float(b[1]),
                           "speed": float(math.sqrt(along_v ** 2 + vx ** 2 + b[1] ** 2))}
    out["lateral_launch_angle_deg"] = angle
    # First contact: the side camera's contact time or, if earlier, where the fitted arc meets the deck or floor.
    down = surface_time(side_model, x0, vx, tau_end + 0.2)
    if tau_contact is not None and (down is None or tau_contact <= down[0]):
        tau_land, end_kind = tau_contact, "side camera's first contact"
    elif down is not None:
        tau_land, end_kind = down[0], f"arc meets the {down[1]}"
        if tau_contact is not None:
            out.setdefault("notes", []).append(f"The side camera's first contact came {tau_contact - down[0]:.2f} s after "
                                               f"the arc reached the {down[1]}; the arc is used.")
    else:
        tau_land, end_kind = tau_end, "end of search"
    pt = model_points(side_model, x0, vx, np.array([tau_land]))[0]
    landing = {"t_s": tau_land, "at": end_kind, "side_contact_t_s": tau_contact, "predicted_x_in": float(pt[0] / INCH_M + 12.0),
               "predicted_along_m": float(pt[1]), "predicted_height_m": float(pt[2])}
    if fit["free"].get("contact_x_m") is not None:
        landing["flight_only_x_in"] = float(fit["free"]["contact_x_m"] / INCH_M + 12.0)
    if contact is not None:
        landing["measured_x_in"] = float(front_contact["x_in"])
        landing["difference_in"] = landing["predicted_x_in"] - landing["measured_x_in"]
        if landing.get("flight_only_x_in") is not None:
            landing["flight_only_difference_in"] = landing["flight_only_x_in"] - landing["measured_x_in"]
    out["landing"] = landing
    if frontal_release_offset_m is not None:
        out["release_check"] = {"front_pose_hand_lateral_m": float(frontal_release_offset_m),
                                "difference_m": x0 - float(frontal_release_offset_m)}
    if heading_deg is not None:
        out["heading_check"] = {"two_view_heading_deg": float(heading_deg), "difference_deg": angle - float(heading_deg)}
    # Path samples (60 Hz) from release to first contact, and the image path per front frame.
    ts = np.arange(0.0, tau_land + 1e-9, 1.0 / PATH_SAMPLE_HZ)
    pts = model_points(side_model, x0, vx, ts)
    out["path_m"] = [{"t_s": round(float(t), 4), "x_m": round(float(p[1] - release_along), 4),
                      "y_m": round(float(p[0]), 4), "z_m": round(float(p[2]), 4)} for t, p in zip(ts, pts)]
    ks = list(range(first, last + 1))
    tau_k = _times(front_times, ks, to_side) + delta
    keep = [(k, t) for k, t in zip(ks, tau_k) if 0.0 <= t <= tau_land + 0.5 / front_fps]
    if keep:
        kk = [k for k, _ in keep]
        pix = projector.project(model_points(side_model, x0, vx, np.array([t for _, t in keep])), kk)
        out["front_path"] = [{"frame": int(k), "px": [round(float(p[0]), 1), round(float(p[1]), 1)]}
                             for k, p in zip(kk, pix)]
    if reasons:
        # Missing stays missing: a rejected fit says why and how well it fitted, never its numbers.
        numbers = ("release", "velocity_m_s", "lateral_launch_angle_deg", "landing", "release_check",
                   "heading_check", "path_m", "front_path")
        rejected = {k: out.pop(k) for k in numbers if k in out}
        if debug:
            out["rejected_fit"] = rejected
        return unavailable(" ".join(reasons))
    status = "measured" if side["status"] == "measured" and camera_status == "measured" else "estimated"
    out.update(status=status, reason=None if status == "measured" else
               "The side camera's scale or the front camera's field of view is estimated on this throw.")
    return out


def write_flight3d(analysis_dir: str | Path, record: dict[str, Any]) -> None:
    from .serialization import json_ready, write_json
    write_json(Path(analysis_dir) / FLIGHT3D_FILENAME, json_ready(record))


def analyze_flight3d(analysis_dir: str | Path, frames: Sequence[np.ndarray] | None = None,
                     write: bool = True, debug: bool = False) -> dict[str, Any]:
    """Re-run the 3D flight on an analysed two-camera throw from its stored outputs (two_view.json for the
    per-frame deck corners, frames and the front camera; results.json and auto_flight.json for the side
    flight) and the front clip. Used for library re-runs; analyze_two_view calls ``reconstruct_flight``."""
    from . import front_view as fv
    from .two_view import load_take_link
    out = Path(analysis_dir)
    link = load_take_link(out)
    if link is None or link.get("error"):
        return {"method_version": FLIGHT3D_VERSION, "status": "unavailable", "reason": "No front-camera clip."}
    record = json.loads((out / "two_view.json").read_text())
    results = json.loads((out / "results.json").read_text())
    auto_flight = json.loads((out / "auto_flight.json").read_text()) if (out / "auto_flight.json").exists() else {}
    if record.get("status") != "measured":
        return {"method_version": FLIGHT3D_VERSION, "status": "unavailable",
                "reason": record.get("reason") or "The front camera was not analysed."}
    if frames is None:
        frames, _ = fv.read_clip_frames(link["front_clip_path"])
    corners = np.asarray(record["deck_corners_by_frame_px"], float)
    fr = record.get("frames") or {}
    cam = record.get("camera") or {}
    release_front = fr.get("release_front")
    heading = (record.get("heading") or {}).get("deg")
    offset = ((record.get("frontal") or {}).get("release_point_offset_m") or {}).get("value")
    flight = reconstruct_flight(frames=frames, results=results, auto_flight=auto_flight, link=link,
                                corners_per_frame=corners, front_hfov_deg=cam.get("hfov_deg"),
                                camera_status=cam.get("status"),
                                release_side=fr.get("release_side"), contact_side=fr.get("contact_side"),
                                release_front=release_front, contact_front=fr.get("contact_front"),
                                front_contact=(record.get("landing") or {}).get("contact"),
                                corners_suspect=bool(cam.get("corners_suspect")),
                                frontal_release_offset_m=offset, heading_deg=heading, debug=debug)
    if write:
        write_flight3d(out, flight)
    return flight
