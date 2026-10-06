"""Automatic bag flight: physics-constrained trajectory selection and events."""
import numpy as np
import pytest

from cornhole_biomech.auto_bag import (
    Candidate,
    detect_moving_blobs_in_frames,
    find_flight,
    release_from_wrist,
)

FPS = 60.0
PPM = 180.0
G = 9.80665


def true_flight(t0=40, n=45, x0=500.0, y0=500.0, vx=5.5, vy=3.5, sign=1):
    pts = {}
    for k in range(n):
        t = k / FPS
        pts[t0 + k] = (x0 + sign * PPM * vx * t, y0 - PPM * (vy * t - 0.5 * G * t * t))
    return pts


def candidates_with_clutter(flight, seed=0, clutter_per_frame=4, drop=0.15, noise=1.5):
    rng = np.random.default_rng(seed)
    out = []
    for f in range(0, 120):
        for _ in range(clutter_per_frame):
            out.append(Candidate(f, float(rng.uniform(0, 1900)), float(rng.uniform(0, 1000)), 20))
        if f in flight and rng.random() > drop:
            x, y = flight[f]
            out.append(Candidate(f, x + rng.normal(0, noise), y + rng.normal(0, noise), 25))
    return out


def test_finds_projectile_among_clutter_and_rejects_clutter():
    flight = true_flight()
    result = find_flight(candidates_with_clutter(flight), FPS, "left_to_right", arm_length_px=PPM * 0.62)
    assert result["status"] == "accepted"
    frames = {p["frame"] for p in result["points"]}
    assert len(frames) >= 30
    assert all(40 <= f < 85 for f in frames)
    fit = result["fit"]
    assert fit["vertical_acceleration_px_s2"] == pytest.approx(G * PPM, rel=0.1)


def test_wrong_direction_or_upward_curvature_is_not_a_flight():
    flight = true_flight(sign=-1)                 # moves away from the target
    result = find_flight(candidates_with_clutter(flight), FPS, "left_to_right", arm_length_px=PPM * 0.62)
    assert result["status"] != "accepted"


def test_implausible_gravity_for_body_scale_is_rejected():
    flight = true_flight()
    # Arm length implies ~5x smaller scale: the arc would need 5x gravity to be real.
    result = find_flight(candidates_with_clutter(flight), FPS, "left_to_right", arm_length_px=PPM * 0.62 / 5)
    assert result["status"] != "accepted"


def test_too_few_detections_is_never_accepted():
    flight = true_flight(n=6)
    result = find_flight(candidates_with_clutter(flight, drop=0), FPS, "left_to_right", arm_length_px=PPM * 0.62)
    assert result["status"] in ("needs_review", "not_found")


def test_release_is_where_backward_parabola_meets_the_wrist():
    flight = true_flight(t0=40)
    result = find_flight(candidates_with_clutter(flight, drop=0), FPS, "left_to_right", arm_length_px=PPM * 0.62)
    # Wrist carries the bag along the same path until frame 40, then falls away.
    wrist = np.full((120, 2), np.nan)
    for f in range(20, 60):
        t = (f - 40) / FPS
        on_path = (500 + PPM * 5.5 * t, 500 - PPM * (3.5 * t - 0.5 * G * t * t))
        wrist[f] = on_path if f <= 40 else (on_path[0] - 25 * (f - 40), on_path[1] + 20 * (f - 40))
    frame, distance = release_from_wrist(result["fit"], wrist, FPS, search_seconds=0.35)
    assert abs(frame - 40) <= 1
    assert distance < 5


def test_moving_blob_detector_finds_small_mover_on_static_background():
    rng = np.random.default_rng(1)
    background = (rng.uniform(80, 160, (240, 320))).astype(np.uint8)
    frames = []
    for f in range(12):
        img = background.copy()
        cx, cy = 40 + 20 * f, 60 + 5 * f
        img[cy - 3:cy + 3, cx - 3:cx + 3] = 250
        frames.append(np.dstack([img] * 3))
    blobs, _ = detect_moving_blobs_in_frames(frames, scale=1.0)
    hits = [b for b in blobs if b.frame == 6]
    assert any(abs(b.x - 160) < 4 and abs(b.y - 90) < 4 for b in hits)


def test_two_throws_in_one_clip_are_both_found_in_order():
    from cornhole_biomech.auto_bag import find_flights
    first, second = true_flight(t0=10, n=40), true_flight(t0=70, n=40, x0=450, y0=520, vx=6.0, vy=3.0)
    cands = candidates_with_clutter({**first, **second}, drop=0.1, clutter_per_frame=3)
    flights = [f for f in find_flights(cands, FPS, "left_to_right", PPM * 0.62) if f["status"] == "accepted"]
    assert len(flights) == 2
    assert flights[0]["fit"]["first_frame"] < 20 and 65 <= flights[1]["fit"]["first_frame"] < 80


def test_reference_transform_removes_camera_translation():
    from cornhole_biomech.auto_bag import camera_motion_px, to_reference
    # Camera pans 3 px right per frame: scene content moves 3 px left per frame,
    # so frame t -> t-1 maps x to x + 3.
    to_prev = [np.float32([[1, 0, 0], [0, 1, 0]])] + [np.float32([[1, 0, 3], [0, 1, 0]]) for _ in range(9)]
    static_world_point = [Candidate(f, 100.0 - 3 * f, 50.0, 1) for f in range(10)]
    mapped = to_reference(static_world_point, to_prev, reference=4)
    assert all(abs(c.x - (100 - 12)) < 1e-6 for c in mapped)
    assert camera_motion_px(to_prev, 0, 9, (100.0, 50.0)) == pytest.approx(27.0)


def test_short_hand_motion_is_not_accepted_as_a_throw():
    # A small upward toss and catch: plausible gravity, but it barely travels toward the target.
    flight = true_flight(n=30, vx=0.3, vy=2.5)
    result = find_flight(candidates_with_clutter(flight, drop=0), FPS, "left_to_right", arm_length_px=PPM * 0.62)
    assert result["status"] != "accepted"
    assert any("arm lengths toward the target" in r for r in result["reasons"])


def test_slide_after_landing_is_trimmed_so_contact_is_the_last_flight_frame():
    flight = true_flight(t0=40, n=40)
    last_x, last_y = flight[79]
    for k in range(1, 20):                        # bag slides along the board after first contact
        flight[79 + k] = (last_x + 6 * k, last_y - 1.5 * k)
    result = find_flight(candidates_with_clutter(flight, drop=0.05), FPS, "left_to_right", arm_length_px=PPM * 0.62)
    assert result["status"] == "accepted"
    assert 77 <= result["fit"]["last_frame"] <= 81


def test_blur_fragments_of_one_bag_are_merged_into_one_candidate():
    from cornhole_biomech.auto_bag import _merge_fragments
    merged = _merge_fragments([(100.0, 100.0, 10), (108.0, 104.0, 10), (300.0, 300.0, 5)], merge_px=16)
    assert len(merged) == 2
    assert any(abs(x - 104) < 1e-9 and abs(y - 102) < 1e-9 and a == 20 for x, y, a in merged)


def test_acceptance_rms_is_measured_with_camera_motion_removed():
    # Hand-held sway (camera offset c(f)) moves every raw detection by −c(f). Raw pixels then
    # deviate from one parabola by more than the RMS limit although the bag flies a clean arc.
    flight = true_flight()
    sway = {f: np.array([16 * np.sin(2 * np.pi * f / 30), 9.6 * np.cos(2 * np.pi * f / 30)]) for f in range(121)}
    raw = [Candidate(c.frame, c.x - sway[c.frame][0], c.y - sway[c.frame][1], c.area)
           for c in candidates_with_clutter(flight)]
    # to_prev[f] maps frame-f pixels to frame f−1: raw_{f−1} = raw_f + c(f) − c(f−1).
    to_prev = [np.float32([[1, 0, 0], [0, 1, 0]])] + [
        np.float32([[1, 0, sway[f][0] - sway[f - 1][0]], [0, 1, sway[f][1] - sway[f - 1][1]]]) for f in range(1, 121)]
    arm = PPM * 0.62
    old = find_flight(raw, FPS, "left_to_right", arm_length_px=arm)
    assert old["status"] == "needs_review"
    assert any("px RMS" in r for r in old["reasons"])
    new = find_flight(raw, FPS, "left_to_right", arm_length_px=arm, to_prev=to_prev)
    assert new["status"] == "accepted", new["reasons"]
    assert new["fit"]["rms_residual_px"] < 0.08 * arm
    # points stay in raw video pixels
    by_frame = {c.frame: c for c in raw if np.hypot(c.x + sway[c.frame][0] - flight.get(c.frame, (1e9, 0))[0],
                                                     c.y + sway[c.frame][1] - flight.get(c.frame, (0, 1e9))[1]) < 6}
    p = new["points"][len(new["points"]) // 2]
    assert (p["x"], p["y"]) == pytest.approx((by_frame[p["frame"]].x, by_frame[p["frame"]].y))


from cornhole_biomech.auto_bag import find_flight as _find_flight


def test_person_candidates_cannot_seed_a_flight():
    flight = true_flight()
    cands = [Candidate(c.frame, c.x, c.y, c.area, in_person=True)
             for c in candidates_with_clutter(flight, clutter_per_frame=0, drop=0.0)]
    result = _find_flight(cands, FPS, "left_to_right", arm_length_px=PPM * 0.62)
    assert result["status"] == "not_found"


def test_auto_track_does_not_report_mid_air_contact(monkeypatch):
    import cornhole_biomech.auto_bag as ab
    # A flight that ends high in the air: the classifier says lost_in_flight.
    monkeypatch.setattr(ab, "classify_flight_end", lambda p, m: {"kind": "lost_in_flight", "plane_xy_m": [0.0, 1.0]})
    monkeypatch.setattr(ab, "predict_contact", lambda *a, **k: None)
    out = ab._contact_from_board({"status": "found", "model": _StubModel()}, (500.0, 300.0), fit={
        "coef_x": [0, 1, 0], "coef_y": [0, 0, 1], "reference_frame": 0}, fps=FPS, last_frame=80,
        frame_count=200, chain={f: np.eye(3) for f in range(200)})
    assert out["first_contact_frame"] is None
    assert out["contact"]["kind"] == "lost_in_flight" and out["contact"]["state"] == "unavailable"


class _StubModel:
    def as_dict(self):
        return {"phi_deg": 5.0}


def test_flight_ending_on_the_deck_is_an_observed_contact(monkeypatch):
    import cornhole_biomech.auto_bag as ab
    monkeypatch.setattr(ab, "classify_flight_end", lambda p, m: {"kind": "deck", "plane_xy_m": [0.5, 0.2]})
    out = ab._contact_from_board({"status": "found", "model": _StubModel()}, (500.0, 300.0), fit={
        "coef_x": [0, 1, 0], "coef_y": [0, 0, 1], "reference_frame": 0}, fps=FPS, last_frame=80,
        frame_count=200, chain={f: np.eye(3) for f in range(200)})
    assert out["first_contact_frame"] == 80 and out["predicted_contact"] is None
    assert out["contact"] == {"kind": "deck", "state": "measured", "plane_xy_m": [0.5, 0.2], "reason": None}


def test_without_a_board_contact_is_not_checked():
    import cornhole_biomech.auto_bag as ab
    out = ab._contact_from_board({"status": "not_found", "model": None}, (500.0, 300.0), fit={}, fps=FPS,
                                 last_frame=80, frame_count=200, chain={})
    assert out["first_contact_frame"] is None and out["contact"]["state"] == "unavailable"


def _near_contact(monkeypatch, coef_y, predicted_frame):
    import cornhole_biomech.auto_bag as ab
    monkeypatch.setattr(ab, "classify_flight_end", lambda p, m: {"kind": "lost_in_flight", "plane_xy_m": [-0.8, 0.14]})
    monkeypatch.setattr(ab, "predict_contact", lambda *a, **k: {
        "frame": predicted_frame, "x_px": 1.0, "y_px": 2.0, "kind": "floor", "state": "estimated", "reason": "r"})
    return ab._contact_from_board({"status": "found", "model": _StubModel()}, (500.0, 300.0), fit={
        "coef_x": [0, 100, 0], "coef_y": coef_y, "reference_frame": 0}, fps=FPS, last_frame=80,
        frame_count=200, chain={f: np.eye(3) for f in range(200)})


def test_descending_track_ending_just_before_predicted_contact_is_observed(monkeypatch):
    from cornhole_biomech.auto_bag import NEAR_CONTACT_FRAMES
    out = _near_contact(monkeypatch, [0, 0, 500.0], 80 + NEAR_CONTACT_FRAMES)   # dy/dt > 0: falling
    assert out["first_contact_frame"] == 80 and out["predicted_contact"] is None
    assert out["contact"]["kind"] == "floor" and out["contact"]["state"] == "measured"
    assert out["contact"]["plane_xy_m"] == [-0.8, 0.14]
    assert f"within {NEAR_CONTACT_FRAMES} frame(s) of the predicted floor contact" in out["contact"]["reason"]


def test_rising_track_near_predicted_contact_stays_lost(monkeypatch):
    out = _near_contact(monkeypatch, [0, -2000.0, 500.0], 81)   # dy/dt < 0 at t = 80/60 s: still rising
    assert out["first_contact_frame"] is None and out["contact"]["kind"] == "lost_in_flight"
    assert out["predicted_contact"]["frame"] == 81


def test_track_ending_well_before_predicted_contact_stays_lost(monkeypatch):
    from cornhole_biomech.auto_bag import NEAR_CONTACT_FRAMES
    out = _near_contact(monkeypatch, [0, 0, 500.0], 80 + NEAR_CONTACT_FRAMES + 1)
    assert out["first_contact_frame"] is None and out["contact"]["state"] == "unavailable"


def test_after_contact_seeds_from_predicted_contact_when_lost_in_flight(monkeypatch):
    # A bag lost mid-air with a predicted (estimated) contact must still get an
    # after-contact track, seeded from the PREDICTED frame/position converted back
    # to that frame's raw pixels, not from the (nonexistent) observed contact frame.
    # The chain is a genuine translation (not identity) so that dropping the inverse
    # (or applying it backwards) would move the seed point and fail this test.
    import cornhole_biomech.auto_bag as ab
    translate = np.array([[1.0, 0.0, 50.0], [0.0, 1.0, 50.0], [0.0, 0.0, 1.0]])  # raw + 50 = release-frame
    chain = {f: translate for f in range(200)}
    decided = {"predicted_contact": {"frame": 85, "x_px": 12.0, "y_px": 34.0, "kind": "floor",
                                     "state": "estimated", "reason": "predicted"},
              "contact": {"kind": "lost_in_flight", "state": "unavailable"}}
    refined = {f: {"x": 100.0 + f, "y": 200.0 + f} for f in range(75, 81)}
    calls = {}

    def fake_track_after_contact(frames, chains, contact, start, release, fps, typical_area, v0, **kw):
        calls["contact"] = contact
        calls["start"] = start
        calls["v0"] = v0
        return {"status": "rest_found", "path": [], "rest": {"x_release_frame": 5.0, "y_release_frame": 5.0}}

    monkeypatch.setattr(ab, "track_after_contact", fake_track_after_contact)
    after_contact, from_predicted = ab._after_contact(decided, 80, False, refined, chain,
                                                       frames=[None] * 200, release=0, fps=FPS, typical_area=100.0)
    assert from_predicted is True
    assert calls["contact"] == 85
    # raw = inverse(translate) @ (12.0, 34.0, 1) = (12.0 - 50.0, 34.0 - 50.0)
    assert calls["start"] == pytest.approx((-38.0, -16.0))
    assert after_contact["status"] == "rest_found"


def test_after_contact_seeds_from_observed_contact_when_known(monkeypatch):
    import cornhole_biomech.auto_bag as ab
    chain = {f: np.eye(3) for f in range(200)}
    decided = {"predicted_contact": None, "contact": {"kind": "deck", "state": "measured"}}
    refined = {f: {"x": 100.0 + f, "y": 200.0} for f in range(75, 81)}
    calls = {}

    def fake_track_after_contact(frames, chains, contact, start, release, fps, typical_area, v0, **kw):
        calls["contact"] = contact
        calls["start"] = start
        return {"status": "rest_found", "path": [], "rest": None}

    monkeypatch.setattr(ab, "track_after_contact", fake_track_after_contact)
    after_contact, from_predicted = ab._after_contact(decided, 80, True, refined, chain,
                                                       frames=[None] * 200, release=70, fps=FPS, typical_area=None)
    assert from_predicted is False
    assert calls["contact"] == 80
    assert calls["start"] == pytest.approx((180.0, 200.0))
    assert after_contact["status"] == "rest_found"


def test_after_contact_none_without_observed_or_predicted_contact():
    import cornhole_biomech.auto_bag as ab
    chain = {f: np.eye(3) for f in range(200)}
    decided = {"predicted_contact": None, "contact": {"kind": "lost_in_flight", "state": "unavailable"}}
    refined = {f: {"x": 100.0 + f, "y": 200.0} for f in range(75, 81)}
    after_contact, from_predicted = ab._after_contact(decided, 80, False, refined, chain,
                                                       frames=[None] * 200, release=0, fps=FPS, typical_area=100.0)
    assert after_contact is None and from_predicted is False


def test_mark_predicted_basis_appends_marker_only_when_predicted():
    import cornhole_biomech.auto_bag as ab
    suggested = {"needs_confirmation": True, "score": 1, "basis": "Bag came to rest on the deck."}
    marked = ab._mark_predicted_basis(suggested, True)
    assert marked["basis"] == "Bag came to rest on the deck. (from predicted contact)"
    unmarked = ab._mark_predicted_basis(suggested, False)
    assert unmarked is suggested
    assert ab._mark_predicted_basis(None, True) is None


def test_no_board_fallback_contact_is_unverified_and_said_so():
    import cornhole_biomech.auto_bag as ab
    decided = ab._contact_from_board({"status": "not_found", "model": None}, (0, 0), {}, FPS, 80, 200, {})
    fit = {"coef_x": [0, 100, 0], "coef_y": [0, 0, 500.0], "reference_frame": 0}
    known, warning = ab._no_board_fallback(decided, fit, FPS, {"x": 900.0, "y": 500.0}, 80, 1920, 1080)
    assert known and decided["first_contact_frame"] == 80 and decided["contact"]["state"] == "unverified"
    assert "unverified" in warning
    decided = ab._contact_from_board({"status": "not_found", "model": None}, (0, 0), {}, FPS, 80, 200, {})
    known, warning = ab._no_board_fallback(decided, fit, FPS, {"x": 5.0, "y": 500.0}, 80, 1920, 1080)  # at edge
    assert not known and decided["first_contact_frame"] is None and decided["contact"]["state"] == "unavailable"
    assert warning is None


def _no_flight_clip(monkeypatch, frame_count=9):
    """A clip whose frames show a pilot-look board and in which no flight is found."""
    import cornhole_biomech.auto_bag as ab
    from test_board import pilot_like_corners, render_pilot_board
    frame = render_pilot_board(pilot_like_corners())
    monkeypatch.setattr(ab, "read_frames", lambda path, scale=1.0: ([frame.copy() for _ in range(frame_count)], FPS))
    monkeypatch.setattr(ab, "detect_moving_blobs_in_frames",
                        lambda frames: ([], [np.eye(3)[:2] for _ in range(len(frames))]))
    monkeypatch.setattr(ab, "find_flights", lambda *a, **k: [])
    return ab


def test_board_is_detected_on_a_middle_frame_plate_when_no_flight_is_found(monkeypatch):
    from test_board import pilot_like_corners
    from cornhole_biomech.board import order_corners
    ab = _no_flight_clip(monkeypatch)
    out = ab.auto_track_bag("clip.mov", None, None, "left_to_right")
    assert out["status"] == "not_found"
    board = out["board"]
    assert board["status"] == "found"
    assert board["reference_frame"] == 4 and board["reference"] == "middle_frame"
    assert np.abs(np.array(board["corners_px"]) - order_corners(pilot_like_corners(), "left_to_right")).max() < 12
    assert "phi_deg" in board and "model" not in board        # the pose is reported, the model object is not


def test_clicked_corners_in_the_current_plate_frame_are_used_as_is(monkeypatch):
    ab = _no_flight_clip(monkeypatch)
    from test_board import pilot_like_corners
    from cornhole_biomech.board import order_corners
    clicked = order_corners(pilot_like_corners(), "left_to_right").tolist()
    out = ab.auto_track_bag("clip.mov", None, None, "left_to_right", board_corners_px=clicked,
                            board_corners_frame=4)          # the middle frame, this plate's reference
    assert out["board"]["status"] == "found" and out["board"]["reasons"] == ["clicked corners"]
    assert out["board"]["corners_px"] == clicked and out["board"]["clicked_in_frame"] == 4


def test_clicked_corners_from_another_plate_frame_are_remapped(monkeypatch):
    # the scene drifts +3 px in x per frame: to_prev[t] (frame t → t−1) is x − 3, so a static
    # point at x in frame 1's pixels is at x + 9 in frame 4's (the middle-frame plate).
    ab = _no_flight_clip(monkeypatch)
    step = np.array([[1.0, 0.0, -3.0], [0.0, 1.0, 0.0]])
    monkeypatch.setattr(ab, "detect_moving_blobs_in_frames",
                        lambda frames: ([], [np.eye(3)[:2]] + [step] * (len(frames) - 1)))
    clicked = [[700.0, 500.0], [720.0, 540.0], [1300.0, 520.0], [1290.0, 480.0]]
    out = ab.auto_track_bag("clip.mov", None, None, "left_to_right", board_corners_px=clicked,
                            board_corners_frame=1)
    assert out["board"]["reference_frame"] == 4 and out["board"]["clicked_in_frame"] == 1
    expected = (np.array(clicked) + [9.0, 0.0])
    assert np.allclose(out["board"]["corners_px"], expected)


def test_corners_in_reference_maps_through_the_chain_both_ways():
    from cornhole_biomech.auto_bag import corners_in_reference, reference_chain
    step = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, -2.0]])     # frame t is 2 px lower than t−1
    chain = reference_chain([np.eye(3)[:2]] + [step] * 5, 3)
    corners = [[10.0, 10.0], [20.0, 12.0], [30.0, 14.0], [40.0, 16.0]]
    later, _ = corners_in_reference(corners, 5, chain, 3)
    earlier, _ = corners_in_reference(corners, 1, chain, 3)
    assert np.allclose(np.array(later) - corners, [0.0, -4.0])
    assert np.allclose(np.array(earlier) - corners, [0.0, 4.0])


def test_clicked_corners_without_a_frame_are_dropped_with_a_reason(monkeypatch):
    ab = _no_flight_clip(monkeypatch)
    clicked = [[700.0, 500.0], [720.0, 540.0], [1300.0, 520.0], [1290.0, 480.0]]
    out = ab.auto_track_bag("clip.mov", None, None, "left_to_right", board_corners_px=clicked)
    assert out["board"]["reasons"] != ["clicked corners"]            # automatic detection ran instead
    assert "which plate frame" in out["board"]["clicked_corners_ignored"]
    assert out["board"]["corners_px"] != clicked


def test_clicked_corners_from_a_frame_outside_the_clip_are_dropped(monkeypatch):
    ab = _no_flight_clip(monkeypatch)
    clicked = [[700.0, 500.0], [720.0, 540.0], [1300.0, 520.0], [1290.0, 480.0]]
    out = ab.auto_track_bag("clip.mov", None, None, "left_to_right", board_corners_px=clicked,
                            board_corners_frame=250)
    assert "frame 250" in out["board"]["clicked_corners_ignored"]


def test_near_contact_landing_uses_the_predicted_surface_point(monkeypatch):
    import cornhole_biomech.auto_bag as ab
    from cornhole_biomech.auto_bag import AUTO_BAG_REVISION, NEAR_CONTACT_FRAMES
    assert AUTO_BAG_REVISION == "auto_motion_parabola_v18_hand_to_touchdown"
    decided = _near_contact(monkeypatch, [0, 0, 500.0], 80 + NEAR_CONTACT_FRAMES)
    assert decided["contact"]["surface_point_px"] == [1.0, 2.0]
    assert decided["contact"]["surface_frame"] == 80 + NEAR_CONTACT_FRAMES
    seen = []
    monkeypatch.setattr(ab, "landing_summary", lambda p, m: seen.append(tuple(p)) or {"along_error_m": 0.1})
    refined = {80: {"x": 500.0, "y": 300.0}}                       # the last tracked point, still in the air
    landing = ab._landing(decided, True, 80, refined, {80: np.eye(3)}, _StubModel())
    assert seen == [(1.0, 2.0)] and decided["first_contact_frame"] == 80
    assert landing["state"] == "measured" and landing["position_basis"] == "predicted_surface_point"
    assert f"frame {80 + NEAR_CONTACT_FRAMES}" in landing["reason"]
    # A contact seen on the surface itself still uses the tracked point.
    seen.clear()
    observed = {"first_contact_frame": 80, "predicted_contact": None,
                "contact": {"kind": "deck", "state": "measured", "plane_xy_m": [0.5, 0.2], "reason": None}}
    landing = ab._landing(observed, True, 80, refined, {80: np.eye(3)}, _StubModel())
    assert seen == [(500.0, 300.0)] and landing["position_basis"] == "observed_contact_point"


def test_slide_after_touchdown_is_cut_from_the_flight():
    """Pilot P3 take 1 throw 4: six slide frames after touchdown stayed in the flight (32 px RMS, rejected)."""
    flight = true_flight(t0=40, n=45)
    last = flight[84]
    for k in range(1, 8):                       # touchdown at frame 84, then a slow slide along the deck
        flight[84 + k] = (last[0] + 6.0 * k, last[1] - 1.0 * k)
    result = find_flight(candidates_with_clutter(flight, drop=0, clutter_per_frame=2), FPS, "left_to_right",
                         arm_length_px=PPM * 0.62)
    assert result["status"] == "accepted"
    assert 82 <= result["fit"]["last_frame"] <= 85
    assert result["fit"]["rms_residual_px"] < 5.0


def test_near_static_flight_cannot_stand_for_the_throw():
    from cornhole_biomech.auto_bag import travels_toward_target
    static = {"points": [{"frame": f, "x": 249.0 - 1.3 * (f - 221), "y": 367.0} for f in range(221, 233)]}
    throw = {"points": [{"frame": f, "x": 420.0 + 19.0 * (f - 150), "y": 400.0} for f in range(150, 220)]}
    arm = 106.0
    assert not travels_toward_target(static, "left_to_right", arm)
    assert travels_toward_target(throw, "left_to_right", arm)
    assert not travels_toward_target(throw, "right_to_left", arm)
