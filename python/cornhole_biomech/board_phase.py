"""What the bag does ON the board: touchdown, slide, stop or drop into the hole.

Why a separate stage: the flight tracker follows a free projectile and deliberately stops
where the path leaves the parabola (touchdown, slide, bounce). Where the throw ENDS is a
different question: a bag can land short and slide in (a valid technique), hang on the lip
and drop a moment later, or stop on the deck. The earlier "rest" rule took the first quiet
0.2 s as the final rest, so a bag pausing on the lip of the hole was scored as a board bag.

Method (side camera, board located by `board.py`):

1. Region: the deck quadrilateral in release-frame pixels, grown upward by about one bag
   length (a bag lying on the deck projects above the deck surface in the image).
2. Empty-board background: the per-pixel median (Lab colour) of camera-aligned frames in
   which the bag is still far from the board (in the hand or early in flight). Previous bags
   already lying still are part of this background.
3. Every later frame is camera-aligned into the release frame and compared with that
   background; the bag is the connected change region of plausible bag size (0.25-4x the
   bag's in-flight area) nearest its predicted position.
4. Positions are mapped onto the deck with the deck homography: v = inches up the deck from
   the front edge (0-48, hole centre at 39), u = inches across (0-24, hole at 12).
5. Events:
   - touchdown: first sample whose throw-plane height is on the deck surface (plane model);
   - stop: the bag's along-deck position stays within a small band for 0.2 s;
   - the bag is followed to the END of the clip, so a pause is not mistaken for the end:
     a bag that stops and later vanishes at the hole (often shrinking as it tips in) fell
     in; a bag still present when the clip ends rests there.
6. Slide kinematics by finite differences / least squares on the along-deck position:
   distance, duration, entry speed, deceleration a, and an effective sliding friction
   coefficient for a bag sliding UP the slope (angle alpha):  a = g (sin alpha + mu cos alpha).

Lateral position: from a side camera the deck's across direction runs nearly along the
optical axis, so a few pixels of height move u by several inches. The bag's centre sits
about half its thickness above the deck, so u is found by intersecting the centre's viewing
ray (camera pose from the board corners) with the plane 0.6 in above the deck, not with the
deck itself (which put every bag several inches toward the far side). It is reported as
approximate (about +/-3 in), drawn on the board, and signed from the thrower's point of view
(`right_of_centre_in`, + = thrower's right); it is not used to decide the outcome, which uses
the along-deck coordinate v. The board camera measures left/right precisely.

The suggested score always needs a coach's confirmation (one click).
"""
from __future__ import annotations

import math
from typing import Any, Sequence

import cv2
import numpy as np

from .bag import GRAVITY_M_S2
from .bag_segment import _local_align, _warp_to
from .regulation import INCH_M

BOARD_PHASE_REVISION = "board_phase_v3_deck_footprint_touchdown"
HOLE_U_IN, HOLE_V_IN, HOLE_RADIUS_IN = 12.0, 39.0, 3.0
BAG_HALF_IN = 3.0
# A bag whose centre vanishes within the hole radius + half a bag (along the deck) fell in.
HOLE_ALONG_WINDOW_IN = HOLE_RADIUS_IN + BAG_HALF_IN + 0.5
STOP_WINDOW_S = 0.20           # quiet this long = stopped
STOP_BAND_IN = 1.0             # along-deck range allowed while "stopped"
VANISH_S = 0.12                # absent this long = gone
DRAIN_AREA_DROP = 0.35         # visible area falling by this fraction before vanishing = tipping into the hole
MIN_SLIDE_FOR_FRICTION_IN = 4.0
LATERAL_UNRELIABLE_IN = 0.5    # inches across per pixel above which u is only approximate
BAG_CENTRE_HEIGHT_IN = 0.6     # a resting/sliding bag's centre above the deck (about half its thickness)
DECK_TOLERANCE_M = 0.07        # bag half-thickness + plane-mapping noise
DECK_WIDTH_IN = 24.0
# A moving bag whose centre was last seen within half a bag of a side edge already overhangs it; when it
# then vanishes it went off that side (Player 2 take 5 throw 4: last seen 21.6 in across, on the floor next).
SIDE_EDGE_IN = BAG_HALF_IN
# The same half-bag rule for the front and back edges. Along the deck (v) is measured to about an inch,
# across (u) only to about +-3 in, so a bag within half a bag of the front or back edge is judged off
# that edge first (Player 4 take 5 throw 3: last seen 1.5-1.7 in up the deck and 2.7 in across; the
# front camera shows it falling off the front edge, which the side-edge rule had reported).
END_EDGE_IN = BAG_HALF_IN
DECK_LENGTH_IN = 48.0
# Touchdown (see `_on_deck`): a single side view cannot tell "high above the deck" from "on the deck
# but further across" -- both move the bag up in the picture. The bag's centre is therefore mapped onto
# the plane BAG_CENTRE_HEIGHT_IN above the deck; it can be ON the deck only if that point lies on the
# deck, allowing the bag's overhang (half a bag) plus the across precision (+-3 in) at the side edges
# and the overhang at the front/back. Pilot evidence (14 audited side throws, frame by frame): the
# frame-checked touchdown samples mapped -4.0 to +15.7 in across and 2.6-36.6 in along; airborne samples
# mapped 6.2-28 in beyond the far side edge, or past the back edge for the bag that sailed long (Player 3
# take 2 throw 1: 3.9-11.6 in past it). The older throw-plane height test (within 7 cm of the deck)
# rejected a bag landing at the far front corner (9-12 cm "height", Player 2 take 3 throw 3, which then
# fell back to the first airborne sample), was 1 frame late on Player 3 take 1 throw 4 (7.2 cm at the
# visible touchdown), and could not say "never landed" (Player 3 take 2 throw 1 got an airborne touchdown).
# Airborne samples can still map onto the deck footprint (5 pilot throws, -0.5 to -5.6 in across, one
# frame before touchdown), so a second test is needed: in the air the bag still falls quickly in the
# picture, at impact the centre's drop collapses. Centre drop to the next sample, in bag lengths: -0.03
# to 0.33 from the 13 frame-checked touchdown frames (0.31-0.33 when a corner lands first: Player 3
# take 1 throw 4, Player 4 take 5 throw 2, Player 4 take 1 throw 1); 0.42-0.64 from the airborne
# samples on or next to the footprint (Player 1 take 3 throw 2, Player 1 take 5 throw 1, Player 2 take 1
# throw 2, Player 2 take 5 throw 4, Player 3 take 2 throw 1, Player 4 take 5 throw 3). The cut-off is
# midway, 0.38 bag lengths; the margin is small (0.33 vs 0.42), so a touchdown can still be one frame off.
TOUCHDOWN_FALL_BAG_LENGTHS = 0.38


def _bag_length_px(typical_area: float | None) -> float:
    return 2.0 * math.sqrt(typical_area / math.pi) if typical_area and typical_area > 0 else 20.0


def _region(corners_ref: np.ndarray, bag_length: float, width: int, height: int
            ) -> tuple[tuple[int, int, int, int], np.ndarray]:
    """Bounding box (x0, y0, x1, y1) and hull mask (in box pixels) of the deck grown upward."""
    c = np.asarray(corners_ref, float).reshape(4, 2)
    up = c - [0.0, 1.2 * bag_length]
    pts = np.vstack([c, up])
    x0 = int(max(0, math.floor(pts[:, 0].min() - 0.6 * bag_length)))
    x1 = int(min(width, math.ceil(pts[:, 0].max() + 0.6 * bag_length)))
    y0 = int(max(0, math.floor(pts[:, 1].min() - 0.3 * bag_length)))
    y1 = int(min(height, math.ceil(pts[:, 1].max() + 0.3 * bag_length)))
    mask = np.zeros((max(1, y1 - y0), max(1, x1 - x0)), np.uint8)
    hull = cv2.convexHull((pts - [x0, y0]).astype(np.int32))
    cv2.fillPoly(mask, [hull], 1)
    return (x0, y0, x1, y1), mask


def _aligned_lab(frames: Sequence[np.ndarray], chains: dict[int, np.ndarray], f: int,
                 box: tuple[int, int, int, int]) -> np.ndarray:
    """Frame f warped into the release frame's pixels over `box`, in Lab (float32)."""
    patch = _warp_to(frames[f], chains.get(f, np.eye(3)), box)
    return cv2.cvtColor(patch, cv2.COLOR_BGR2LAB).astype(np.float32)


def _background_frames(release: int, entry: int, fps: float, n_frames: int, count: int = 11) -> list[int]:
    """Frames before the bag reaches the board: up to 1 s before release through 2 frames before entry."""
    start = max(0, release - int(round(fps)))
    stop = max(start, min(entry - 2, n_frames - 1))
    if stop - start < 3:
        start = max(0, stop - 30)
    return sorted({int(round(v)) for v in np.linspace(start, stop, min(count, stop - start + 1))})


def _entry_frame(flight_ref: dict[int, tuple[float, float]], box: tuple[int, int, int, int], bag_length: float,
                 last_flight: int) -> int:
    """First flight frame whose bag is within one bag length of the board region."""
    x0, y0, x1, y1 = box
    for f in sorted(flight_ref):
        x, y = flight_ref[f]
        if x0 - bag_length <= x <= x1 + bag_length and y0 - bag_length <= y <= y1 + bag_length:
            return f
    return last_flight + 1


def _components(diff: np.ndarray, roi: np.ndarray, area_bounds: tuple[float, float]) -> list[dict[str, float]]:
    values = diff[roi > 0]
    if values.size == 0:
        return []
    med = float(np.median(values))
    mad = float(np.median(np.abs(values - med)))
    threshold = max(18.0, med + 6 * 1.4826 * mad)
    mask = ((diff > threshold) & (roi > 0)).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
    out = []
    for i in range(1, count):
        area = float(stats[i, cv2.CC_STAT_AREA])
        if not area_bounds[0] <= area <= area_bounds[1]:
            continue
        out.append({"x": float(centroids[i][0]), "y": float(centroids[i][1]), "area": area,
                    "bottom": float(stats[i, cv2.CC_STAT_TOP] + stats[i, cv2.CC_STAT_HEIGHT])})
    return out


def _stop_index(v: np.ndarray, frames: np.ndarray, fps: float, band: float) -> int | None:
    """First sample index from which v stays within `band` inches for STOP_WINDOW_S."""
    need = max(3, int(round(STOP_WINDOW_S * fps)))
    for i in range(len(v)):
        j = i
        while j + 1 < len(v) and frames[j + 1] - frames[i] < need:
            j += 1
        if frames[j] - frames[i] < need - 1 or j - i + 1 < 0.6 * need:
            continue
        window = v[i:j + 1]
        if float(np.max(window) - np.min(window)) <= band:
            return i
    return None


def slide_kinematics(times_s: np.ndarray, along_in: np.ndarray, deck_angle_rad: float) -> dict[str, Any]:
    """Least-squares s(t) = s0 + v0 t - a t^2 / 2 over the slide; effective friction for an up-slope slide.

    Up the slope the bag decelerates by gravity's along-slope part plus kinetic friction:
    a = g (sin alpha + mu cos alpha)  =>  mu = (a / g - sin alpha) / cos alpha.
    Returned in SI units; values are unavailable (None, with a reason) when the slide is too short.
    """
    out: dict[str, Any] = {"entry_speed_m_s": None, "deceleration_m_s2": None, "mu_effective": None,
                           "fit_rmse_in": None, "state": "unavailable", "reason": None}
    t = np.asarray(times_s, float)
    s = np.asarray(along_in, float) * INCH_M
    ok = np.isfinite(t) & np.isfinite(s)
    t, s = t[ok], s[ok]
    distance_in = float((s[-1] - s[0]) / INCH_M) if len(s) >= 2 else 0.0
    if len(t) < 5 or abs(distance_in) < MIN_SLIDE_FOR_FRICTION_IN:
        out["reason"] = "Slide too short or too few samples for a friction estimate."
        if len(t) >= 3 and t[-1] > t[0]:
            out["entry_speed_m_s"] = float((s[min(2, len(s) - 1)] - s[0]) / (t[min(2, len(t) - 1)] - t[0]))
        return out
    t0 = t - t[0]
    A = np.column_stack([np.ones_like(t0), t0, -0.5 * t0 ** 2])
    coef, *_ = np.linalg.lstsq(A, s, rcond=None)
    residual = s - A @ coef
    v0, a = float(coef[1]), float(coef[2])
    out.update(entry_speed_m_s=v0, deceleration_m_s2=a, fit_rmse_in=float(np.sqrt(np.mean(residual ** 2)) / INCH_M))
    if v0 <= 0 or a <= 0:
        out["reason"] = "The slide did not decelerate steadily up the deck (bounce or tumble)."
        return out
    mu = (a / GRAVITY_M_S2 - math.sin(deck_angle_rad)) / math.cos(deck_angle_rad)
    out.update(mu_effective=float(mu), state="estimated",
               reason="Effective kinetic friction for a bag sliding up the deck, from a constant-deceleration fit.")
    return out


def analyze_board_phase(frames: Sequence[np.ndarray], chains: dict[int, np.ndarray], model, release: int,
                        last_flight: int, flight_ref: dict[int, tuple[float, float]], fps: float,
                        typical_area: float | None, touchdown_hint: int | None = None,
                        target_direction: str = "left_to_right") -> dict[str, Any]:
    """Follow the bag on the deck from touchdown to the end of the clip.

    `chains[f]` maps raw pixels of frame f into the release frame's pixels; the board model and
    `flight_ref` (bag centres by frame) are in release-frame pixels. `touchdown_hint` is the
    flight tracker's first-contact frame when it was observed.
    """
    n = len(frames)
    height, width = frames[0].shape[:2]
    bag_length = _bag_length_px(typical_area)
    area = typical_area if typical_area and typical_area > 0 else math.pi * (bag_length / 2) ** 2
    box, roi = _region(model.corners_px, bag_length, width, height)
    if box[2] - box[0] < 8 or box[3] - box[1] < 8:
        return {"revision": BOARD_PHASE_REVISION, "status": "not_found", "reason": "The board is outside the picture."}
    entry = _entry_frame(flight_ref, box, bag_length, last_flight)
    background_frames = _background_frames(release, entry, fps, n)
    if len(background_frames) < 3:
        return {"revision": BOARD_PHASE_REVISION, "status": "not_found",
                "reason": "Too few frames with an empty board to build its background."}
    stack = [_aligned_lab(frames, chains, f, box) for f in background_frames]
    background = np.median(np.stack(stack), axis=0)
    del stack
    bounds = (0.25 * area, 4.0 * area)
    start = max(release + 1, min(entry, last_flight) - 2)
    samples: list[dict[str, Any]] = []
    position: tuple[float, float] | None = None
    velocity = (0.0, 0.0)
    known = sorted(f for f in flight_ref if f < start)
    if len(known) >= 2:
        # Enter the board region with the flight's last velocity (release-frame pixels per frame).
        a, b = known[-2], known[-1]
        position = flight_ref[b]
        velocity = ((flight_ref[b][0] - flight_ref[a][0]) / (b - a), (flight_ref[b][1] - flight_ref[a][1]) / (b - a))
        missed = start - b - 1
    else:
        missed = 0
    for f in range(start, n):
        lab = _aligned_lab(frames, chains, f, box)
        diff = np.linalg.norm(lab - background, axis=2)
        found = _components(diff, roi, bounds)
        chosen = None
        if found:
            for c in found:
                c["x"] += box[0]
                c["y"] += box[1]
            if position is None:
                chosen = max(found, key=lambda c: c["area"])
            else:
                guess = (position[0] + velocity[0] * (missed + 1), position[1] + velocity[1] * (missed + 1))
                near = min(found, key=lambda c: math.hypot(c["x"] - guess[0], c["y"] - guess[1]))
                if math.hypot(near["x"] - guess[0], near["y"] - guess[1]) <= 1.5 * bag_length + 0.5 * bag_length * missed:
                    chosen = near
                elif missed >= 2:
                    # Lost for a few frames (impact, blur): re-acquire the most bag-like change on the board.
                    chosen = max(found, key=lambda c: c["area"])
        if chosen is None:
            missed += 1
            samples.append({"frame": f, "present": False})
            continue
        x, y = chosen["x"], chosen["y"]
        if position is not None:
            gap = missed + 1
            step = ((x - position[0]) / gap, (y - position[1]) / gap)
            # On the deck the bag decelerates; follow the measured step closely (friction, impact).
            velocity = (0.3 * velocity[0] + 0.7 * step[0], 0.3 * velocity[1] + 0.7 * step[1])
        position, missed = (x, y), 0
        samples.append({"frame": f, "present": True, "x_release_frame": x, "y_release_frame": y, "area_px": chosen["area"]})
    return summarize_board_phase(samples, model, fps, n, typical_area=area, chains=chains,
                                 touchdown_hint=touchdown_hint, background_frames=background_frames,
                                 target_direction=target_direction)


def summarize_board_phase(samples: list[dict[str, Any]], model, fps: float, frame_count: int,
                          typical_area: float | None = None, chains: dict[int, np.ndarray] | None = None,
                          touchdown_hint: int | None = None, background_frames: list[int] | None = None,
                          target_direction: str = "left_to_right") -> dict[str, Any]:
    """Events, outcome and slide kinematics from per-frame deck samples (release-frame pixels).

    Split from the image work so the decision rules can be tested directly.
    """
    board = model.board
    present = [s for s in samples if s.get("present")]
    base: dict[str, Any] = {"revision": BOARD_PHASE_REVISION, "background_frames": background_frames or []}
    lateral_precision = None
    if present:
        pts = np.array([[s["x_release_frame"], s["y_release_frame"]] for s in present], float)
        uv = model.to_deck_inches(pts)
        plane = model.to_plane(pts)
        lifted = _lifted_u(model, pts)
        side = 1.0 if target_direction == "left_to_right" else -1.0
        for s, (u, v), (px, py), u_lift in zip(present, uv, plane, lifted):
            s["u_in_deck_plane"] = float(u)
            s["u_in"], s["v_in"] = (float(u_lift) if math.isfinite(u_lift) else float(u)), float(v)
            # Thrower's right is the camera side for a left-to-right throw (the far side right-to-left).
            s["right_of_centre_in"] = side * (s["u_in"] - HOLE_U_IN)
            s["plane_x_m"], s["plane_y_m"] = float(px), float(py)
            deck_y = board.deck_height_at(min(max(float(px), 0.0), board.horizontal_length_m))
            s["lifted_u"] = bool(math.isfinite(u_lift))
            s["plane_on_deck"] = bool(-0.5 * 6 * INCH_M <= px <= board.horizontal_length_m + 3 * INCH_M
                                      and abs(py - deck_y) <= DECK_TOLERANCE_M)
            if chains is not None and s["frame"] in chains:
                raw = np.linalg.inv(chains[s["frame"]]) @ np.array([s["x_release_frame"], s["y_release_frame"], 1.0])
                s["x"], s["y"] = float(raw[0]), float(raw[1])
            else:
                s["x"], s["y"] = s["x_release_frame"], s["y_release_frame"]
        mid = pts[len(pts) // 2]
        lateral_precision = model.across_precision_in_per_px(mid)
        across_tol = BAG_HALF_IN + max(3.0, 3.0 * lateral_precision)
        bag_length = _bag_length_px(typical_area)
        for i, s in enumerate(present):
            nxt = present[i + 1] if i + 1 < len(present) else None
            s["on_deck_surface"] = _on_deck(s, nxt, across_tol, bag_length)
    lateral = {"state": "approximate" if lateral_precision is None or lateral_precision > LATERAL_UNRELIABLE_IN else "estimated",
               "inches_per_pixel": lateral_precision,
               "precision_in": None if lateral_precision is None else float(max(3.0, 3.0 * lateral_precision)),
               "note": "Left/right on the board is approximate from a side camera (about ±3 in): the across "
                       "direction runs along the camera's line of sight. The result is decided from the "
                       "along-board position; the board camera measures left/right precisely."}
    base["lateral"] = lateral
    if not present:
        return {**base, "status": "not_found", "path": [],
                "reason": "The bag was not seen on the board (it may have landed off the board or been hidden).",
                "end": {"kind": "never_on_deck"},
                "suggested_outcome": None}
    # Touchdown: the first sample that can lie on the deck (or the flight tracker's observed contact, if
    # earlier). A bag seen only in the air over the board never touched down: it is not given a touchdown.
    on_surface = [s for s in present if s["on_deck_surface"]]
    if not on_surface:
        return {**base, "status": "not_found", "path": [],
                "reason": "The bag was seen over the board only in the air; it did not land on the deck.",
                "end": {"kind": "never_on_deck"}, "suggested_outcome": None,
                "samples_present": len(present), "samples_total": len(samples)}
    touch = on_surface[0]
    if touchdown_hint is not None:
        hinted = [s for s in present if s["frame"] >= touchdown_hint]
        if hinted and hinted[0]["frame"] < touch["frame"] and hinted[0]["on_deck_surface"]:
            touch = hinted[0]
    deck = [s for s in present if s["frame"] >= touch["frame"]]
    frames_arr = np.array([s["frame"] for s in deck], float)
    v_arr = np.array([s["v_in"] for s in deck], float)
    # 3-sample running median against single-frame segmentation jitter.
    if len(v_arr) >= 3:
        smooth = np.array([np.median(v_arr[max(0, i - 1):i + 2]) for i in range(len(v_arr))])
    else:
        smooth = v_arr.copy()
    precision = max(STOP_BAND_IN, 3.0 * model.along_precision_in_per_px(
        (touch["x_release_frame"], touch["y_release_frame"])))
    stop_i = _stop_index(smooth, frames_arr, fps, precision)
    last_seen = deck[-1]
    vanish_frames = max(3, int(round(VANISH_S * fps)))
    gone = frame_count - 1 - last_seen["frame"] >= vanish_frames
    in_hole_window = lambda s: abs(s["v_in"] - HOLE_V_IN) <= HOLE_ALONG_WINDOW_IN
    on_deck_area = lambda s: -1.0 <= s["v_in"] <= 49.0 and -8.0 <= s["u_in"] <= 32.0

    # Area trend in the last 0.3 s before the bag disappeared (a bag tipping into the hole shrinks).
    tail = [s for s in deck if s["frame"] >= last_seen["frame"] - int(round(0.3 * fps))]
    reference_areas = [s["area_px"] for s in deck[: max(3, len(deck) // 2)]]
    drained = bool(gone and tail and reference_areas
                   and np.median([s["area_px"] for s in tail[-3:]]) <= (1 - DRAIN_AREA_DROP) * np.median(reference_areas))

    stop = deck[stop_i] if stop_i is not None else None
    end: dict[str, Any]
    hang = None
    if gone and in_hole_window(last_seen):
        if stop is not None and last_seen["frame"] - stop["frame"] > int(round(0.1 * fps)):
            hang = {"from_frame": stop["frame"], "to_frame": last_seen["frame"],
                    "seconds": (last_seen["frame"] - stop["frame"]) / fps}
        end = {"kind": "fell_in_hole", "frame": last_seen["frame"] + 1,
               "note": ("The bag hung on the lip for {:.2f} s, then dropped through the hole.".format(hang["seconds"])
                        if hang else "The bag slid into the hole." if len(deck) > 3 else "The bag went into the hole.")
               + (" It shrank from view as it tipped in." if drained else "")}
        end_sample = last_seen
    elif gone and not on_deck_area(last_seen):
        end = {"kind": "left_deck", "frame": last_seen["frame"] + 1,
               "note": "The bag left the board surface (slid or bounced off)."}
        end_sample = last_seen
    elif gone and stop is None and (last_seen["v_in"] > DECK_LENGTH_IN - END_EDGE_IN or last_seen["v_in"] < END_EDGE_IN):
        edge = "back" if last_seen["v_in"] > DECK_LENGTH_IN / 2 else "front"
        end = {"kind": "left_deck", "frame": last_seen["frame"] + 1, "edge": edge,
               "note": f"The bag was last seen at the {edge} edge of the board and then disappeared (probably slid off)."}
        end_sample = last_seen
    elif gone and stop is None and (last_seen["u_in"] >= DECK_WIDTH_IN - SIDE_EDGE_IN or last_seen["u_in"] <= SIDE_EDGE_IN):
        end = {"kind": "left_deck", "frame": last_seen["frame"] + 1, "edge": "side",
               "note": "The bag was last seen moving at the side edge of the board and then disappeared "
                       "(probably slid or tipped off the side)."}
        end_sample = last_seen
    elif gone:
        end = {"kind": "lost", "frame": last_seen["frame"] + 1,
               "note": "The bag disappeared away from the hole (hidden or picked up); confirm the result in the video."}
        end_sample = last_seen
    elif stop is not None:
        quiet = [s for s in deck[stop_i:]]
        rest_v = float(np.median([s["v_in"] for s in quiet]))
        end = {"kind": "rest", "frame": stop["frame"],
               "note": ("The bag stopped on the board and was still there when the clip ended"
                        + (" (resting at the lip of the hole)." if abs(rest_v - HOLE_V_IN) <= HOLE_RADIUS_IN + BAG_HALF_IN
                           else "."))}
        end_sample = {**stop, "u_in": float(np.median([s["u_in"] for s in quiet])),
                      "right_of_centre_in": float(np.median([s["right_of_centre_in"] for s in quiet])),
                      "v_in": float(np.median([s["v_in"] for s in quiet])),
                      "x_release_frame": float(np.median([s["x_release_frame"] for s in quiet])),
                      "y_release_frame": float(np.median([s["y_release_frame"] for s in quiet]))}
        if frame_count - 1 - stop["frame"] < int(round(0.5 * fps)):
            end["note"] += " The clip ends soon after it stopped, so a late drop cannot be ruled out."
            end["short_after_stop"] = True
    else:
        end = {"kind": "moving_at_clip_end", "frame": last_seen["frame"],
               "note": "The bag was still moving when the clip ended."}
        end_sample = last_seen
    end.update(u_in=float(end_sample["u_in"]), v_in=float(end_sample["v_in"]),
               right_of_centre_in=float(end_sample["right_of_centre_in"]),
               from_hole_in=float(end_sample["v_in"] - HOLE_V_IN),
               x_release_frame=float(end_sample["x_release_frame"]), y_release_frame=float(end_sample["y_release_frame"]))
    if "x" in end_sample:
        end.update(x=float(end_sample["x"]), y=float(end_sample["y"]))
    if end["kind"] == "fell_in_hole":
        end["from_hole_in"] = 0.0 if abs(end["from_hole_in"]) <= HOLE_RADIUS_IN else end["from_hole_in"]

    touchdown = {"frame": touch["frame"], "u_in": touch["u_in"], "v_in": touch["v_in"],
                 "right_of_centre_in": touch["right_of_centre_in"],
                 "from_hole_in": touch["v_in"] - HOLE_V_IN,
                 "x_release_frame": touch["x_release_frame"], "y_release_frame": touch["y_release_frame"],
                 "on_deck": bool(0.0 <= touch["v_in"] <= 48.0),
                 "basis": "on_deck_surface" if touch["on_deck_surface"] else "first_seen_over_board"}
    if "x" in touch:
        touchdown.update(x=touch["x"], y=touch["y"])
    # Slide: touchdown to the stop (or to the last sample before the bag vanished/fell).
    slide_end = stop_i if stop_i is not None else len(deck) - 1
    slide = deck[: slide_end + 1]
    # Friction only from the part of the slide on plain deck: over the hole the bag bridges the
    # opening or tips in, which is not sliding friction.
    plain = [s for s in slide if s["v_in"] < HOLE_V_IN - HOLE_ALONG_WINDOW_IN or s["v_in"] > HOLE_V_IN + HOLE_ALONG_WINDOW_IN]
    plain = plain if len(plain) >= 5 and plain[-1]["frame"] - plain[0]["frame"] == len(plain) - 1 else \
        [s for s in slide if s["v_in"] < HOLE_V_IN - HOLE_ALONG_WINDOW_IN]
    kin = slide_kinematics(np.array([(s["frame"] - touch["frame"]) / fps for s in plain]),
                           np.array([s["v_in"] for s in plain]), board.angle)
    if plain and len(plain) < len(slide):
        kin["reason"] = (kin.get("reason") or "") + " Fitted on the plain deck before the hole."
    slide_summary = {"distance_in": float(slide[-1]["v_in"] - touch["v_in"]) if slide else 0.0,
                     "duration_s": float((slide[-1]["frame"] - touch["frame"]) / fps) if slide else 0.0,
                     "samples": len(slide), **kin}
    score, basis, confidence = None, end["note"], "low"
    if end["kind"] == "fell_in_hole":
        score, confidence = 3, "high" if (drained or hang or abs(last_seen["v_in"] - HOLE_V_IN) <= HOLE_RADIUS_IN + 1) else "medium"
    elif end["kind"] == "rest":
        on = -0.5 <= end["v_in"] <= 48.5 and (lateral["state"] == "approximate" or -2.0 <= end["u_in"] <= 26.0)
        score, confidence = (1, "high" if not end.get("short_after_stop") else "medium") if on else (0, "medium")
        basis = f"{end['note']} It stopped {_where(end['from_hole_in'])}."
    elif end["kind"] == "left_deck":
        # Off a side edge is judged from the approximate (±3 in) across position: low confidence.
        score, confidence = 0, "low" if end.get("edge") == "side" else "medium"
    suggested = None if score is None else {
        "score": score, "basis": basis, "confidence": confidence, "needs_confirmation": True,
        "source": "board_phase"}
    path = [{k: s[k] for k in ("frame", "x", "y", "x_release_frame", "y_release_frame", "u_in", "v_in",
                               "right_of_centre_in", "area_px")
             if k in s} for s in deck]
    return {**base, "status": "measured", "touchdown": touchdown, "end": end, "hang": hang, "drained": drained,
            "slide": slide_summary, "path": path, "suggested_outcome": suggested,
            "samples_present": len(present), "samples_total": len(samples)}


def _on_deck(sample: dict[str, Any], following: dict[str, Any] | None, across_tol_in: float,
             bag_length_px: float) -> bool:
    """Can this sample be the bag lying on the deck? (touchdown test; constants above)

    Its centre, mapped onto the plane half a bag-thickness above the deck, lies on the deck (u within
    `across_tol_in` of the side edges, v within half a bag of the front/back edge), and it is not still
    falling: its image centre drops by at most TOUCHDOWN_FALL_BAG_LENGTHS bag lengths per frame to the
    next sample. Without the camera pose (no lifted mapping) the older throw-plane height test is used.
    """
    if not sample.get("lifted_u"):
        on = bool(sample.get("plane_on_deck"))
    else:
        on = (-across_tol_in <= sample["u_in"] <= DECK_WIDTH_IN + across_tol_in
              and -END_EDGE_IN <= sample["v_in"] <= DECK_LENGTH_IN + END_EDGE_IN)
    if on and following is not None:
        gap = max(1, following["frame"] - sample["frame"])
        if (following["y_release_frame"] - sample["y_release_frame"]) / gap > TOUCHDOWN_FALL_BAG_LENGTHS * bag_length_px:
            on = False
    return on


def _lifted_u(model, pts: np.ndarray) -> np.ndarray:
    """Across-deck inches of bag centres (BAG_CENTRE_HEIGHT_IN above the deck); NaN where unavailable."""
    if not hasattr(model, "deck_inches_lifted") or getattr(model, "rvec", None) is None:
        return np.full(len(pts), np.nan)
    try:
        return model.deck_inches_lifted(pts, BAG_CENTRE_HEIGHT_IN * INCH_M)[:, 0]
    except Exception:  # a degenerate pose never costs the along-deck result
        return np.full(len(pts), np.nan)


def _where(from_hole_in: float) -> str:
    if abs(from_hole_in) <= HOLE_RADIUS_IN:
        return "at the hole"
    return f"{abs(from_hole_in):.0f} in {'past' if from_hole_in > 0 else 'short of'} the hole"


def as_after_contact(phase: dict[str, Any]) -> dict[str, Any] | None:
    """The older `after_contact` shape (replay, suggested outcome) from a board-phase result."""
    if not phase or phase.get("status") != "measured":
        return None
    end = phase["end"]
    status = {"rest": "rest_found", "fell_in_hole": "fell_in_hole", "left_deck": "left_deck",
              "moving_at_clip_end": "moving_at_clip_end"}.get(end["kind"], "lost_after_contact")
    rest = None
    if end["kind"] == "rest":
        rest = {"frame": end["frame"], "x": end.get("x", end["x_release_frame"]), "y": end.get("y", end["y_release_frame"]),
                "x_release_frame": end["x_release_frame"], "y_release_frame": end["y_release_frame"],
                "u_in": end["u_in"], "v_in": end["v_in"]}
    stop_frame = end["frame"] if end["kind"] == "rest" else None
    path = [p for p in phase["path"] if stop_frame is None or p["frame"] <= stop_frame]
    return {"status": status, "path": path, "rest": rest, "note": end.get("note"),
            "source": BOARD_PHASE_REVISION}
