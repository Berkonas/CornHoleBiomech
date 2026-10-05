"""Forward growth of a flight to first contact (bag_segment.extend_to_contact, auto_bag._grow_to_contact).

Synthetic clip: a red bag on a parabola over a textured grey background, a flickering clutter
patch just below its path, a 4-frame occlusion shortly before it lands, then the bag rests where
it touched down. The motion track is cut early (as when the detector lost the bag in clutter or
another candidate flight claimed its last frames); growth must carry it to the landing.
"""
import math

import numpy as np
import pytest

from cornhole_biomech.auto_bag import Candidate
from cornhole_biomech.bag_segment import extend_to_contact

FPS = 60.0
W, H = 640, 360
RADIUS = 7
OCCLUDED = range(52, 56)        # bag hidden (pillar) in these frames
GROUND_Y = 290.0                # bag centre at/below this image row = on the surface
N_FRAMES = 72


def path(k: float) -> tuple[float, float]:
    """Bag centre in frame k: x linear, y quadratic (image y down), 1080 px/s² image gravity."""
    return 40.0 + 8.0 * k, 300.0 - 9.0 * k + 0.15 * k * k


TOUCHDOWN = next(k for k in range(31, N_FRAMES) if path(k)[1] >= GROUND_Y)   # first frame on the surface (descending)


def render(decoy: str | None = None, bag_after_occlusion: bool = True, seed: int = 3) -> list[np.ndarray]:
    rng = np.random.default_rng(seed)
    background = np.clip(110 + 25 * rng.standard_normal((H, W, 1)), 0, 255).repeat(3, axis=2).astype(np.uint8)
    background = cv2_blur(background)
    frames = []
    for k in range(N_FRAMES):
        img = background.copy()
        patch = rng.integers(60, 200, (56, 80, 1)).repeat(3, axis=2).astype(np.uint8)   # grey flicker clutter
        img[235:291, 370:450] = patch
        visible = k not in OCCLUDED and (bag_after_occlusion or k < OCCLUDED[0])
        x, y = path(min(k, TOUCHDOWN))           # the bag stops where it touched down
        if visible:
            draw_disc(img, x, y, (40, 40, 200))
        if decoy and k > OCCLUDED[-1]:
            dx, dy = path(min(k, TOUCHDOWN))
            draw_disc(img, dx + 5, dy + 4, (40, 40, 200) if decoy == "red" else (128, 128, 128))
        frames.append(img)
    return frames


def cv2_blur(img):
    import cv2
    return cv2.GaussianBlur(img, (5, 5), 0)


def draw_disc(img, x, y, colour):
    import cv2
    cv2.circle(img, (int(round(x)), int(round(y))), RADIUS, colour, -1, cv2.LINE_AA)


def chains():
    return {f: np.eye(3) for f in range(N_FRAMES)}


def track_rows(last: int = 45) -> list[dict]:
    return [{"frame": k, "x": path(k)[0], "y": path(k)[1], "area_px": math.pi * RADIUS ** 2, "source": "mask"}
            for k in range(5, last + 1)]


def on_surface(f, p):
    return "deck" if p[1] >= GROUND_Y else "air"


def test_growth_crosses_clutter_and_a_four_frame_occlusion_to_the_landing():
    out = extend_to_contact(render(), chains(), track_rows(), max_frames=40, surface=on_surface)
    frames = [r["frame"] for r in out["rows"]]
    assert frames[0] == 46 and frames[-1] == TOUCHDOWN
    assert out["stop"] == "surface_contact_deck"
    assert not set(frames) & set(OCCLUDED)                     # never invents the hidden frames
    assert out["bridged_frames"] >= len(OCCLUDED)
    visible = [k for k in range(46, TOUCHDOWN + 1) if k not in OCCLUDED]
    assert len(frames) >= 0.8 * len(visible)
    for r in out["rows"]:                                      # on the bag, not on the clutter patch
        assert math.hypot(r["x"] - path(r["frame"])[0], r["y"] - path(r["frame"])[1]) < 2.0
        assert r["source"] == "extended_mask"


def test_without_a_board_the_walk_still_reaches_the_landing_and_stops_on_the_resting_bag():
    out = extend_to_contact(render(), chains(), track_rows(), max_frames=40, surface=None)
    frames = [r["frame"] for r in out["rows"]]
    assert TOUCHDOWN in frames
    # The resting bag is off the falling path: it is not followed far past touchdown.
    assert frames[-1] <= TOUCHDOWN + 2


def test_a_person_region_blocks_reacquisition_after_misses():
    # The bag never reappears after the occlusion; a red blob moves near its predicted path inside a
    # person (e.g. a bystander's red clothing). It must not be taken as the bag.
    frames = render(decoy="red", bag_after_occlusion=False)
    person = lambda f, x, y: True
    guarded = extend_to_contact(frames, chains(), track_rows(), max_frames=40, surface=on_surface, in_person=person)
    assert max(r["frame"] for r in guarded["rows"]) < OCCLUDED[0]
    # Control: without the person region the same red blob WOULD be re-acquired, so the guard matters.
    unguarded = extend_to_contact(frames, chains(), track_rows(), max_frames=40, surface=on_surface)
    assert max(r["frame"] for r in unguarded["rows"]) > OCCLUDED[-1]


def test_a_differently_coloured_object_on_the_path_is_not_the_bag():
    frames = render(decoy="grey", bag_after_occlusion=False)
    out = extend_to_contact(frames, chains(), track_rows(), max_frames=40, surface=on_surface)
    assert max(r["frame"] for r in out["rows"]) < OCCLUDED[0]
    assert out["stop"] in ("lost", "predicted_surface_not_seen")


def test_predicted_surface_without_a_detection_is_reported_for_the_contact_rule():
    # Bag hidden from the frame it would touch down: the walk stops where its local path reaches the surface.
    frames = render()
    empty = frames[OCCLUDED[0]]                      # a frame without the bag (it is behind the pillar)
    for k in range(TOUCHDOWN, N_FRAMES):
        clutter = frames[k][235:291, 370:450].copy()
        frames[k] = empty.copy()
        frames[k][235:291, 370:450] = clutter
    out = extend_to_contact(frames, chains(), track_rows(), max_frames=40, surface=on_surface)
    assert out["stop"] == "predicted_surface_not_seen"
    assert out["surface_reached"]["frame"] == TOUCHDOWN and out["surface_reached"]["kind"] == "deck"
    assert out["rows"][-1]["frame"] == TOUCHDOWN - 1


# ------------------------------------------------------------------ auto_bag integration
def _chosen_flight(last=45):
    from cornhole_biomech.bag import _robust_polynomial
    pts = [{"frame": k, "x": path(k)[0], "y": path(k)[1], "area": 150.0} for k in range(5, last + 1)]
    t = np.array([(p["frame"] - 5) / FPS for p in pts])
    cx, _, _ = _robust_polynomial(t, np.array([p["x"] for p in pts]), 2)
    cy, _, _ = _robust_polynomial(t, np.array([p["y"] for p in pts]), 2)
    fit = {"reference_frame": 5, "first_frame": 5, "last_frame": last, "coef_x": list(cx), "coef_y": list(cy),
           "vertical_acceleration_px_s2": 2 * cy[2], "horizontal_acceleration_px_s2": 2 * cx[2],
           "rms_residual_px": 0.5, "inliers": len(pts), "coverage": 1.0, "span_seconds": (last - 5) / FPS}
    return {"status": "accepted", "reasons": [], "points": pts, "fit": fit}


class _Board:
    pass


def test_grown_flight_is_refit_and_ends_at_the_landing(monkeypatch):
    import cornhole_biomech.auto_bag as ab
    monkeypatch.setattr(ab, "surface_at", lambda p, model: "deck" if p[1] >= GROUND_Y else "air")
    frames = render()
    chosen = _chosen_flight()
    refined = {r["frame"]: {**r, "detection_x": r["x"], "detection_y": r["y"]} for r in track_rows()}
    to_prev = [np.float32([[1, 0, 0], [0, 1, 0]]) for _ in range(N_FRAMES)]
    # Motion candidates of the late flight exist (claimed by another candidate flight in the real case).
    cands = [Candidate(k, *path(k), 150.0) for k in range(46, TOUCHDOWN + 1) if k not in OCCLUDED]
    grown, refined2, info = ab._grow_to_contact(chosen, refined, frames, chains(), to_prev, cands, _Board(),
                                                lambda f, x, y: False, FPS, 60.0, "left_to_right")
    assert info["status"] == "extended" and info["last_frame"] == TOUCHDOWN
    assert grown["fit"]["last_frame"] == TOUCHDOWN
    assert grown["fit"]["vertical_acceleration_px_s2"] == pytest.approx(2 * 0.15 * FPS ** 2, rel=0.05)
    assert grown["fit"]["inliers"] == len(chosen["points"]) + info["frames_added"]
    assert all(refined2[f]["source"] == "extended_mask" for f in info["added_frames"])


def test_growth_that_breaks_the_gravity_arc_is_discarded(monkeypatch):
    # Whatever the image search returns, the grown flight must stay one gravity arc: a continuation
    # without gravity (straight line) or curving upward is discarded and the flight kept as detected.
    import cornhole_biomech.auto_bag as ab
    monkeypatch.setattr(ab, "surface_at", lambda p, model: "air")
    x45, y45 = path(45)
    to_prev = [np.float32([[1, 0, 0], [0, 1, 0]]) for _ in range(N_FRAMES)]
    for bend in (0.0, -0.6):
        chosen = _chosen_flight()
        refined = {r["frame"]: dict(r) for r in track_rows()}
        fake = {"rows": [{"frame": k, "x": x45 + 8.0 * (k - 45), "y": y45 + 4.5 * (k - 45) + bend * (k - 45) ** 2,
                          "area_px": 150.0, "source": "extended_mask"} for k in range(46, 70)],
                "stop": "lost", "bridged_frames": 0, "surface_reached": None}
        monkeypatch.setattr(ab, "extend_to_contact", lambda *a, **k: fake)
        grown, refined2, info = ab._grow_to_contact(chosen, refined, [None] * N_FRAMES, chains(), to_prev, [],
                                                    _Board(), None, FPS, 60.0, "left_to_right")
        assert info["status"] == "rejected_by_physics_gate", info
        assert grown is chosen and refined2 is refined


def test_track_already_on_a_surface_is_not_grown(monkeypatch):
    import cornhole_biomech.auto_bag as ab
    monkeypatch.setattr(ab, "surface_at", lambda p, model: "deck")
    chosen = _chosen_flight()
    grown, _, info = ab._grow_to_contact(chosen, {}, [], chains(), [], [], _Board(), None, FPS, 60.0, "left_to_right")
    assert info["status"] == "not_needed" and grown is chosen


def test_local_path_on_the_surface_next_frame_makes_the_last_frame_the_contact(monkeypatch):
    import cornhole_biomech.auto_bag as ab
    monkeypatch.setattr(ab, "classify_flight_end", lambda p, m: {"kind": "lost_in_flight", "plane_xy_m": [0.3, 0.2]})
    lost = {"first_contact_frame": None, "predicted_contact": {"frame": 99},
            "contact": {"kind": "lost_in_flight", "state": "unavailable"}}
    fit = {"reference_frame": 0, "coef_y": [0.0, 0.0, 500.0]}     # descending
    local = {"frame": 81, "kind": "deck", "x_px": 1.0, "y_px": 2.0}
    out = ab._local_surface_contact(lost, local, object(), (0.0, 0.0), fit, FPS, 80)
    assert out["first_contact_frame"] == 80 and out["predicted_contact"] is None
    assert out["contact"]["kind"] == "deck" and out["contact"]["state"] == "measured"
    assert "surface_point_px" not in out["contact"]       # landing = observed centre at the contact frame
    # Not the next frame, rising, or already measured on a surface: unchanged.
    assert ab._local_surface_contact(lost, {**local, "frame": 83}, object(), (0, 0), fit, FPS, 80) is lost
    rising = {"reference_frame": 0, "coef_y": [0.0, -2000.0, 500.0]}
    assert ab._local_surface_contact(lost, local, object(), (0, 0), rising, FPS, 80) is lost
    measured = {"first_contact_frame": 80, "contact": {"kind": "deck", "state": "measured"}}
    assert ab._local_surface_contact(measured, local, object(), (0, 0), fit, FPS, 80) is measured


def test_candidate_flight_inside_the_chosen_flight_is_not_counted_as_another_throw():
    from cornhole_biomech.auto_bag import _same_throw
    chosen = {"first_frame": 166, "last_frame": 225}
    assert _same_throw({"fit": {"first_frame": 187, "last_frame": 225}}, chosen)
    assert not _same_throw({"fit": {"first_frame": 300, "last_frame": 340}}, chosen)
