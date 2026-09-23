"""Physics-informed state estimation for the bag's free flight (raw data is never replaced).

Model (per image axis, independent x and y):

    state s = [p, v, a]ᵀ           position (px), velocity (px/s), acceleration (px/s²)
    p(k+1) = p + v Δt + ½ a Δt²
    v(k+1) = v + a Δt
    a(k+1) = a + w                  w: white jerk noise, spectral density q (px²/s⁵)

In free flight a is approximately constant: ≈ g·(px per m) downward and ≈ 0
horizontally. The model does not impose those values. It estimates a from the
data and lets it drift by q, so perspective, drag and residual camera motion are
absorbed instead of forcing the path onto a perfect parabola.

Measurement: z = p + e, e ~ N(0, σ²) in each axis (σ in px).

Procedure (Bar-Shalom, Li & Kirubarajan 2001, ch. 5–6; Rauch, Tung & Striebel 1965):
1. σ is initialised from the third differences of consecutive centroids
   (for white noise Var(Δ³z) = 20σ²), a robust MAD estimate.
2. Outliers (a jump to the wrong blob) are found by leave-one-out: each point
   is compared with a quadratic through its neighbours within ±5 frames. A
   point more than max(5σ, 4 px) away is labelled `rejected_outlier`; it stays
   in the raw data and is not used by the filter. (A sequential innovation gate
   was tried first; on real clips one rejection let the prediction drift and
   then rejected good points too.)
3. σ and q are chosen by maximising the innovation log-likelihood over a
   grid, using the remaining measurements.
4. Forward Kalman filter + Rauch–Tung–Striebel smoother give the filtered
   position, velocity and a 1-SD position uncertainty for every frame between
   the first and last measurement. Frames without a measurement are labelled
   `predicted_gap`; gaps longer than `max_gap_frames` are left empty.

Nothing is extrapolated before the first or after the last measurement: the
filter never invents release or landing positions.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

FILTER_REVISION = "ca_kalman_rts_v1"
OUTLIER_SIGMAS = 5.0
OUTLIER_MIN_PX = 4.0
OUTLIER_HALF_WINDOW = 5
SIGMA_GRID_PX = (0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0)
Q_GRID = tuple(10.0 ** e for e in np.arange(3.0, 10.01, 0.5))  # px²/s⁵


def _transition(dt: float) -> tuple[np.ndarray, np.ndarray]:
    F1 = np.array([[1.0, dt, 0.5 * dt * dt], [0.0, 1.0, dt], [0.0, 0.0, 1.0]])
    Q1 = np.array([[dt**5 / 20, dt**4 / 8, dt**3 / 6],
                   [dt**4 / 8, dt**3 / 3, dt**2 / 2],
                   [dt**3 / 6, dt**2 / 2, dt]])
    F = np.zeros((6, 6)); Q = np.zeros((6, 6))
    F[:3, :3] = F[3:, 3:] = F1
    Q[:3, :3] = Q[3:, 3:] = Q1
    return F, Q


H = np.zeros((2, 6)); H[0, 0] = 1.0; H[1, 3] = 1.0


def third_difference_sigma(frames: np.ndarray, z: np.ndarray) -> float | None:
    """Robust measurement-noise SD (px) from third differences of consecutive frames."""
    values = []
    for i in range(len(frames) - 3):
        if frames[i + 3] - frames[i] == 3:
            values.extend(z[i + 3] - 3 * z[i + 2] + 3 * z[i + 1] - z[i])
    if len(values) < 6:
        return None
    d = np.asarray(values)
    return float(1.4826 * np.median(np.abs(d - np.median(d))) / math.sqrt(20.0))


def leave_one_out_outliers(frames: np.ndarray, z: np.ndarray, sigma: float) -> np.ndarray:
    """True where a point sits far from a quadratic through its neighbours (itself excluded)."""
    limit = max(OUTLIER_SIGMAS * sigma, OUTLIER_MIN_PX)
    out = np.zeros(len(frames), bool)
    for i, f in enumerate(frames):
        near = np.flatnonzero((np.abs(frames - f) <= OUTLIER_HALF_WINDOW) & (np.arange(len(frames)) != i))
        if len(near) < 5:
            continue
        t = (frames[near] - f).astype(float)
        predicted = [np.polyval(np.polyfit(t, z[near, axis], 2), 0.0) for axis in (0, 1)]
        out[i] = math.hypot(z[i, 0] - predicted[0], z[i, 1] - predicted[1]) > limit
    # A neighbour that is itself an outlier can make a good point look bad: re-test
    # flagged points against the unflagged neighbours only.
    for i in np.flatnonzero(out):
        near = np.flatnonzero((np.abs(frames - frames[i]) <= OUTLIER_HALF_WINDOW) & ~out)
        if len(near) < 5:
            continue
        t = (frames[near] - frames[i]).astype(float)
        predicted = [np.polyval(np.polyfit(t, z[near, axis], 2), 0.0) for axis in (0, 1)]
        out[i] = math.hypot(z[i, 0] - predicted[0], z[i, 1] - predicted[1]) > limit
    return out


def _initial_state(t: np.ndarray, z: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """State from a quadratic through the first measurements; wide covariance."""
    use = slice(0, min(len(t), 8))
    s = np.zeros(6)
    for axis, offset in ((0, 0), (1, 3)):
        degree = 2 if len(t[use]) >= 4 else 1
        c = np.polyfit(t[use] - t[0], z[use, axis], degree)[::-1]
        c = np.pad(c, (0, 3 - len(c)))
        s[offset:offset + 3] = [c[0], c[1], 2 * c[2]]
    P = np.diag([25.0, 1e6, 1e8] * 2)   # px², (px/s)², (px/s²)²: effectively uninformative
    return s, P


def _forward(frames, z, use, fps, sigma, q):
    """Kalman filter over consecutive frames first..last. Returns arrays for smoothing."""
    first, last = int(frames[0]), int(frames[-1])
    n = last - first + 1
    lookup = {int(f): i for i, f in enumerate(frames)}
    dt = 1.0 / fps
    F, Q1 = _transition(dt)
    Q = q * Q1
    R = np.eye(2) * sigma * sigma
    s, P = _initial_state((frames - first) / fps, z)
    xs_pred = np.zeros((n, 6)); Ps_pred = np.zeros((n, 6, 6))
    xs = np.zeros((n, 6)); Ps = np.zeros((n, 6, 6))
    loglik, used, nis = 0.0, 0, []
    for k in range(n):
        if k > 0:
            s = F @ s
            P = F @ P @ F.T + Q
        xs_pred[k], Ps_pred[k] = s, P
        i = lookup.get(first + k)
        if i is not None and use[i]:
            innovation = z[i] - H @ s
            S = H @ P @ H.T + R
            Sinv = np.linalg.inv(S)
            d2 = float(innovation @ Sinv @ innovation)
            K = P @ H.T @ Sinv
            s = s + K @ innovation
            P = (np.eye(6) - K @ H) @ P
            if k > 3:   # the first updates only initialise the state
                loglik += -0.5 * (d2 + math.log(np.linalg.det(S)) + 2 * math.log(2 * math.pi))
                used += 1
                nis.append(d2)
        xs[k], Ps[k] = s, P
    return dict(first=first, F=F, xs=xs, Ps=Ps, xs_pred=xs_pred, Ps_pred=Ps_pred,
                loglik=loglik, used=used, nis=nis)


def _rts(run) -> tuple[np.ndarray, np.ndarray]:
    xs, Ps, xp, Pp, F = run["xs"], run["Ps"], run["xs_pred"], run["Ps_pred"], run["F"]
    xsm, Psm = xs.copy(), Ps.copy()
    for k in range(len(xs) - 2, -1, -1):
        C = Ps[k] @ F.T @ np.linalg.pinv(Pp[k + 1])
        xsm[k] = xs[k] + C @ (xsm[k + 1] - xp[k + 1])
        Psm[k] = Ps[k] + C @ (Psm[k + 1] - Pp[k + 1]) @ C.T
    return xsm, Psm


def smooth_flight(points: list[dict[str, Any]], fps: float, max_gap_frames: int = 6,
                  sigma_px: float | None = None, q: float | None = None) -> dict[str, Any]:
    """Filter a free-flight track given as [{"frame", "x", "y"}] in one fixed pixel frame.

    Pass `sigma_px`/`q` to fix the noise model (e.g. for tests); otherwise both are
    estimated from the clip. Returns per-frame raw and filtered values; the raw
    values are copied unchanged.
    """
    empty = {"status": "insufficient_data", "revision": FILTER_REVISION, "frames": []}
    clean = sorted((int(p["frame"]), float(p["x"]), float(p["y"])) for p in points
                   if p.get("x") is not None and p.get("y") is not None
                   and math.isfinite(p["x"]) and math.isfinite(p["y"]))
    if len(clean) < 8 or fps <= 0:
        empty["reason"] = "At least 8 flight measurements are needed for the flight filter."
        return empty
    frames = np.array([c[0] for c in clean])
    z = np.array([[c[1], c[2]] for c in clean])
    use = np.ones(len(frames), bool)
    sigma0 = sigma_px or third_difference_sigma(frames, z) or 1.5
    sigma0 = float(np.clip(sigma0, 0.3, 10.0))
    q0 = q or 1e6
    use = ~leave_one_out_outliers(frames, z, sigma0)
    # Pass 2: maximum-likelihood noise model on the retained measurements.
    if sigma_px is None or q is None:
        best = None
        for s_try in ([sigma_px] if sigma_px else SIGMA_GRID_PX):
            for q_try in ([q] if q else Q_GRID):
                run = _forward(frames, z, use, fps, s_try, q_try)
                if run["used"] and (best is None or run["loglik"] > best[0]):
                    best = (run["loglik"], s_try, q_try)
        _, sigma, q_used = best if best else (None, sigma0, q0)
    else:
        sigma, q_used = sigma_px, q
    final = _forward(frames, z, use, fps, sigma, q_used)
    xsm, Psm = _rts(final)
    first = final["first"]
    by_frame = {int(f): (zz, bool(u)) for f, zz, u in zip(frames, z, use)}
    measured = sorted(int(f) for f, u in zip(frames, use) if u)
    out, gap_lengths = [], []
    gap_start = None
    for k in range(len(xsm)):
        f = first + k
        raw = by_frame.get(f)
        if raw is None:
            status = "predicted_gap"
        elif raw[1]:
            status = "measured"
        else:
            status = "rejected_outlier"
        if status != "measured":
            gap_start = f if gap_start is None else gap_start
        elif gap_start is not None:
            gap_lengths.append(f - gap_start); gap_start = None
        out.append({"frame": f, "raw_x": None if raw is None else float(raw[0][0]),
                    "raw_y": None if raw is None else float(raw[0][1]), "status": status,
                    "x": float(xsm[k, 0]), "y": float(xsm[k, 3]),
                    "vx": float(xsm[k, 1]), "vy": float(xsm[k, 4]),
                    "sd_x": float(math.sqrt(max(Psm[k, 0, 0], 0))), "sd_y": float(math.sqrt(max(Psm[k, 3, 3], 0)))})
    # Blank long unobserved stretches: a smoother across 0.1 s+ of nothing is a guess.
    run_start = None
    for idx, row in enumerate(out + [{"status": "measured"}]):
        if row["status"] != "measured":
            run_start = idx if run_start is None else run_start
        elif run_start is not None:
            if idx - run_start > max_gap_frames:
                for r in out[run_start:idx]:
                    r.update(x=None, y=None, vx=None, vy=None, sd_x=None, sd_y=None, status=r["status"] + "_too_long")
            run_start = None
    residuals = [math.hypot(r["raw_x"] - r["x"], r["raw_y"] - r["y"]) for r in out
                 if r["status"] == "measured" and r["x"] is not None]
    nis = np.asarray(final["nis"])
    return {
        "status": "filtered",
        "revision": FILTER_REVISION,
        "model": "constant_acceleration_white_jerk_per_axis",
        "measurement_sigma_px": float(sigma),
        "jerk_spectral_density_px2_s5": float(q_used),
        "noise_selection": "maximum_innovation_likelihood" if (sigma_px is None or q is None) else "fixed",
        "measurement_count": int(len(frames)),
        "rejected_outlier_frames": sorted(int(f) for f, u in zip(frames, use) if not u),
        "predicted_gap_frames": int(sum(1 for r in out if r["status"].startswith("predicted_gap"))),
        "longest_gap_frames": int(max(gap_lengths, default=0)),
        "first_frame": first, "last_frame": first + len(out) - 1,
        "raw_minus_filtered_rms_px": float(np.sqrt(np.mean(np.square(residuals)))) if residuals else None,
        # Mean normalised innovation squared: ≈ 2 when the noise model matches the data.
        "mean_nis": float(nis.mean()) if nis.size else None,
        "measured_frames": measured,
        "frames": out,
        "assumptions": ("Single fixed pixel frame (camera motion removed); free flight between the first and last "
                        "measurement; acceleration approximately constant but allowed to drift. Not extrapolated "
                        "beyond the measured flight."),
    }


def filtered_to_raw(filtered: dict[str, Any], camera_to_release: dict[str, list[list[float]]] | None) -> dict[int, tuple[float, float]]:
    """Map filtered release-frame coordinates back onto each raw video frame for display."""
    out: dict[int, tuple[float, float]] = {}
    for row in filtered.get("frames", []):
        if row.get("x") is None:
            continue
        f = int(row["frame"])
        if camera_to_release and str(f) in camera_to_release:
            M = np.vstack([np.asarray(camera_to_release[str(f)], float), [0, 0, 1]])
            x, y, _ = np.linalg.inv(M) @ np.array([row["x"], row["y"], 1.0])
            out[f] = (float(x), float(y))
        elif not camera_to_release:
            out[f] = (float(row["x"]), float(row["y"]))
    return out


def stabilize_points(points: np.ndarray, camera_to_release: dict[str, list[list[float]]] | None) -> np.ndarray:
    """Raw per-frame pixels → release-frame pixels. Frames without a transform are left as NaN
    when transforms exist (their camera motion is unknown), or unchanged for a fixed camera."""
    p = np.array(points, float, copy=True)
    if not camera_to_release:
        return p
    out = np.full_like(p, np.nan)
    for key, matrix in camera_to_release.items():
        f = int(key)
        if 0 <= f < len(p) and np.isfinite(p[f]).all():
            M = np.asarray(matrix, float)
            out[f] = M[:, :2] @ p[f] + M[:, 2]
    return out
