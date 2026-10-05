"""Combine the side and front cameras for one throw: where it ended in 2D, and why.

The side analysis (pipeline.analyze_trial) has already measured the release (speed, angle, height,
distance to the board), the body chain and, on the board, touchdown and rest *along* the deck. This step
adds the front camera (front_view.py) and writes ``two_view.json`` next to ``results.json``:

* ``landing`` — first contact and rest as (x across, y along) board inches. Across comes from the front
  camera's deck homography (≈ 0.1 in per pixel); along from the side camera when it measured it (the front
  camera sees the deck edge-on, ≈ 1 in per pixel), else from the front camera.
* ``result`` — hole / board / off, decided from the front camera (it looks straight at the hole) and
  cross-checked with the side camera's suggestion.
* ``miss`` — the signed miss in the thrower's frame: short(−)/long(+) and left(−)/right(+) inches from the
  hole centre, measured at rest (where points are scored).
* ``heading`` — sideways launch direction (front_view.heading) and how much of the sideways miss comes
  from aim versus from where the hand released the bag.
* ``frontal`` — frontal-plane body measures at release (front_view.frontal_metrics).
* ``explanation`` — one plain sentence for the coach, built only from measured parts: distance (from the
  side physics) and direction (from the front camera), each with the measured body or release value that
  went with it. Associations, not causes: words like "came with" are used, never "because".

Methods: docs/METHODS_AND_MATH.md §5.3 ("Combined result: where it ended and why").
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Callable

import numpy as np

from . import front_view as fv
from .regulation import INCH_M, Board
from .serialization import json_ready, write_json

TWO_VIEW_VERSION = "two_view_v3_front_lag"   # bump when the front landing / tracking logic changes
TAKE_LINK_FILENAME = "take_link.json"
LATERAL_ON_LINE_IN = 3.0          # within ±3 in of the hole centre line sideways = "on line" (the hole radius)
DISTANCE_ON_TARGET_IN = 3.0
MAX_CORNER_RESIDUAL_PX = 2.5      # front deck-corner PnP residual above which the corners are suspect (good: ≤ 1.3)
MAX_HFOV_DEVIATION_DEG = 8.0      # deck-shape field of view this far from the pooled one: suspect corners (±2.5° noise)
SIDE_OFF_ENDS = ("left_deck", "never_on_deck")   # side board-phase endings that mean "not on the board"
SYNC_FRAME_TOLERANCE = 2          # front frames: the two views' first-contact times must agree this closely

Progress = Callable[[str, float, str], None]


def _no_progress(stage: str, fraction: float, message: str) -> None:
    return None


def load_take_link(analysis_dir: str | Path) -> dict[str, Any] | None:
    """The throw's link to its take: ``take_record`` (take.json) and ``throw_number``, paths relative to the
    analysis folder. The take record holds the clips, the sync, the front deck and its reference frame."""
    path = Path(analysis_dir) / TAKE_LINK_FILENAME
    if not path.exists():
        return None
    link = json.loads(path.read_text())
    record_path = (Path(analysis_dir) / link["take_record"]).resolve()
    if not record_path.exists():
        return {**link, "error": f"Take record not found: {link['take_record']}"}
    take = json.loads(record_path.read_text())
    throw = next((t for t in take.get("throws", []) if t.get("number") == link.get("throw_number")), None)
    if throw is None:
        return {**link, "error": f"Throw {link.get('throw_number')} is not in the take record."}
    folder = record_path.parent

    def local(p: str | None) -> str | None:
        if not p:
            return None
        candidate = Path(p)
        return str(candidate if candidate.is_absolute() and candidate.exists() else folder / candidate.name)

    board = take.get("front_board") or {}
    if link.get("front_board_corners_override"):
        board = {**board, "status": "found", "corners_px": link["front_board_corners_override"], "source": "clicked"}
    return {**link, "take": take.get("take"), "sync": take.get("sync"), "throw": throw,
            "front_clip_path": local((throw.get("front_clip") or {}).get("path")),
            "side_clip_path": local((throw.get("side_clip") or {}).get("path")),
            "front_clip": throw.get("front_clip"), "side_clip": throw.get("side_clip"),
            "front_board": board, "front_reference_path": local(board.get("reference_image")),
            "front_hfov_pooled": take.get("front_hfov_pooled"), "front_lag_s": take.get("front_lag_s")}


def ensure_side_board_corners(analysis_dir: str | Path) -> bool:
    """Write board_corners.json (the side-view deck, carried from the take's empty-board frame into this
    clip's first frame) unless one exists already. A person's clicked corners are never replaced."""
    out = Path(analysis_dir)
    target = out / "board_corners.json"
    link = load_take_link(out)
    if link is None or link.get("error"):
        return False
    corners = (link.get("throw") or {}).get("side_board_corners_frame0")
    if not corners:
        return False
    if target.exists():
        existing = json.loads(target.read_text())
        if existing.get("source") != "take_reference":
            return False
    write_json(target, {"corners_px": corners["corners_px"], "source": "take_reference",
                        "reference_frame": int(corners.get("reference_frame", 0))})
    return True


SHARED_BOARD_MIN_CONFIDENCE = 0.75   # the side detector's own "found" gate (board.detect_board)


def _found_side_boards(analysis_dirs: list[Path]) -> list[dict[str, Any]]:
    """Throws whose own side-camera analysis found the deck, with the plate it was found on."""
    found = []
    for folder in analysis_dirs:
        flight = folder / "auto_flight.json"
        plate = folder / "plate.jpg"
        corners_file = folder / "board_corners.json"
        if not flight.exists() or not plate.exists():
            continue
        try:
            board = json.loads(flight.read_text()).get("board") or {}
            source = json.loads(corners_file.read_text()).get("source") if corners_file.exists() else None
        except (OSError, ValueError):
            continue
        # Only the detector's own finds count (not corners that were themselves shared or carried).
        if (board.get("status") == "found" and source is None and board.get("corners_px")
                and float(board.get("confidence") or 0) >= SHARED_BOARD_MIN_CONFIDENCE):
            link = load_take_link(folder) or {}
            found.append({"folder": folder, "corners_px": board["corners_px"], "plate": plate,
                          "confidence": float(board["confidence"]), "take_record": link.get("take_record")})
    return found


def share_side_board(analysis_dir: str | Path, siblings: list[str | Path] | None = None) -> dict[str, Any] | None:
    """Give a throw whose side camera could not find the deck the deck another throw of the athlete found.

    Called after the throw's own analysis failed to find the deck (a throw whose own detection succeeded keeps
    it); the throw is then analysed again with the shared corners.

    The side phone stands still for a whole session, but later bags on the deck and people near it make the
    automatic deck search fail on some clips (Final Data Collection: 3 of 5 Player 1 clips). The deck found on
    a sibling throw (same take first, then the athlete's other takes; highest detector confidence) is carried
    from that throw's background plate into this clip's first frame by ECC alignment of the board area; the
    alignment must converge with correlation ≥ 0.6 (otherwise nothing is written). Writes board_corners.json
    (source ``sibling_throw``). Clicked corners and a take-start deck are never replaced.
    """
    import cv2
    from .front_view import align_to_reference, board_window, warp_points
    out = Path(analysis_dir)
    target = out / "board_corners.json"
    if target.exists():
        try:
            if json.loads(target.read_text()).get("source") != "sibling_throw":   # clicked or take-start: keep
                return None
        except (OSError, ValueError):
            return None
    if _found_side_boards([out]):
        return None                       # this throw's own detection found the deck: keep it
    link = load_take_link(out)
    if link is None or link.get("error") or not link.get("side_clip_path"):
        return None
    folders = [Path(p) for p in siblings] if siblings is not None else [p for p in out.parent.iterdir() if p.is_dir()]
    candidates = [c for c in _found_side_boards([f for f in folders if f.resolve() != out.resolve()])]
    if not candidates:
        return None
    candidates.sort(key=lambda c: (c["take_record"] != link.get("take_record"), -c["confidence"]))
    capture = cv2.VideoCapture(str(link["side_clip_path"]))
    ok, frame = capture.read()
    capture.release()
    if not ok:
        return None
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    for candidate in candidates[:3]:
        reference = cv2.imread(str(candidate["plate"]))
        if reference is None or reference.shape[:2] != frame.shape[:2]:
            continue
        corners = np.asarray(candidate["corners_px"], float)
        window = board_window(corners, (reference.shape[1], reference.shape[0]))
        aligned = align_to_reference(cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY), gray, window)
        if not aligned["ok"]:
            continue
        record = {"corners_px": warp_points(aligned["warp"], corners).round(2).tolist(), "reference_frame": 0,
                  "source": "sibling_throw", "from_throw": candidate["folder"].name,
                  "same_take": candidate["take_record"] == link.get("take_record"),
                  "detector_confidence": candidate["confidence"], "alignment_correlation": aligned["correlation"]}
        write_json(target, record)
        return record
    return None


SIDE_SETUP_TOLERANCE_PX = 25.0     # deck centre shift that still means "the side phone did not move"


def side_camera_setups(analysis_dirs: list[Path]) -> dict[str, list[Path]]:
    """Two-camera throws grouped by side camera set-up: the same phone (device model and frame size), the same
    recording date, and the deck at the same place in the picture (centre within 25 px, so the tripod did not
    move). Such throws share one lens field of view whoever threw, so their gravity calibrations are pooled
    together (Final Data Collection: Player 1 and Player 4 decks 11 px apart; per-throw values 51–65°)."""
    groups: dict[str, list[Path]] = {}
    centres: dict[str, list[np.ndarray]] = {}
    for folder in analysis_dirs:
        folder = Path(folder)
        link = load_take_link(folder)
        if link is None or link.get("error"):
            continue
        try:
            take = json.loads((folder / link["take_record"]).resolve().read_text())
            board = json.loads((folder / "auto_flight.json").read_text()).get("board") or {}
        except (OSError, ValueError):
            continue
        side = take.get("side") or {}
        base = f"{side.get('model') or 'unknown camera'} {'x'.join(map(str, side.get('size') or []))} {side.get('recorded') or 'unknown date'}"
        corners = board.get("corners_px") if board.get("status") == "found" else None
        if corners is None and (folder / "board_corners.json").exists():
            try:     # a deck shared or clicked since this throw was analysed (used on its next analysis)
                corners = json.loads((folder / "board_corners.json").read_text()).get("corners_px")
            except (OSError, ValueError):
                corners = None
        if not corners:
            key = f"{base} · deck not found"
        else:
            centre = np.asarray(corners, float).mean(axis=0)
            key = next((k for k, cs in centres.items() if k.startswith(base)
                        and np.linalg.norm(np.mean(cs, axis=0) - centre) <= SIDE_SETUP_TOLERANCE_PX), None)
            if key is None:
                key = f"{base} · position {sum(1 for k in centres if k.startswith(base)) + 1}"
                centres[key] = []
            centres[key].append(centre)
        groups.setdefault(key, []).append(folder)
    return groups


def athlete_release_distance(analysis_dir: str | Path, minimum: int = 3) -> float | None:
    """Median measured release → board-front distance over the athlete's other analysed throws
    (sibling analysis folders), when at least ``minimum`` have one."""
    values = []
    for results_path in Path(analysis_dir).parent.glob("*/results.json"):
        if results_path.parent == Path(analysis_dir):
            continue
        try:
            value = (json.loads(results_path.read_text()).get("summaries") or {}).get("release_to_board_front_m")
        except (OSError, ValueError):
            continue
        if value is not None and np.isfinite(value):
            values.append(float(value))
    return float(np.median(values)) if len(values) >= minimum else None


def _summary(results: dict[str, Any], key: str) -> float | None:
    value = (results.get("summaries") or {}).get(key)
    return None if value is None or not np.isfinite(value) else float(value)


def side_to_front_frame(side_frame: int | None, side_fps: float, link: dict[str, Any]) -> int | None:
    """Front-clip frame showing the same instant as a side-clip frame (container timestamps, sound sync, then
    the set-up's measured picture lag ``front_lag_s``, see ``pool_front_lag``)."""
    if side_frame is None:
        return None
    front = link.get("front_clip") or {}
    t0 = front.get("side_frame0_front_time_s")
    if t0 is None:
        return None
    side_times = (link.get("side_clip") or {}).get("frame_times_s")
    t_side = side_times[side_frame] if side_times and 0 <= side_frame < len(side_times) else side_frame / side_fps
    t_front = t_side + float(t0) + float(link.get("front_lag_s") or 0.0)
    times = front.get("frame_times_s")
    if times:
        times = np.asarray(times, float)
        step = float(np.median(np.diff(times))) if len(times) > 1 else 1.0 / float(front.get("fps") or 30.0)
        if t_front < times[0] - step or t_front > times[-1] + step:
            return None                     # that instant is outside the front clip
        return int(np.argmin(np.abs(times - t_front)))
    return int(round(t_front * float(front.get("fps") or 30.0)))


def _unavailable(out: Path, record: dict[str, Any], reason: str) -> dict[str, Any]:
    record.update(status="unavailable", reason=reason)
    write_json(out / "two_view.json", json_ready(record))
    return record


def analyze_two_view(analysis_dir: str | Path, *, throwing_side: str, progress: Progress = _no_progress,
                     front_pose=None, run_pose: bool = True, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Front-camera analysis of one throw + fusion with its side analysis. Writes two_view.json."""
    import cv2
    out = Path(analysis_dir)
    link = load_take_link(out)
    if link is None:
        return {"status": "unavailable", "reason": "This throw has no front-camera clip."}
    record: dict[str, Any] = {"schema_version": 1, "method_version": TWO_VIEW_VERSION, "take": link.get("take"),
                              "throw_in_take": link.get("throw_number"), "status": "measured", "notes": []}
    if link.get("error"):
        return _unavailable(out, record, link["error"])
    record["sync"] = {k: (link.get("sync") or {}).get(k) for k in ("status", "offset_s", "correlation", "margin",
                                                                   "uncertainty_s", "reason")}
    results = json.loads((out / "results.json").read_text())
    front_path = link.get("front_clip_path")
    board = link.get("front_board") or {}
    if not front_path or not Path(front_path).exists():
        return _unavailable(out, record, (link.get("throw") or {}).get("front_clip_reason")
                            or "The front clip for this throw is missing.")
    if board.get("status") != "found" or not board.get("corners_px"):
        return _unavailable(out, record, board.get("reason")
                            or "The board was not found in the front camera; click its four corners.")
    reference_path = link.get("front_reference_path")
    reference_img = cv2.imread(reference_path) if reference_path and Path(reference_path).exists() else None
    if reference_img is None:
        return _unavailable(out, record, "The front camera's reference frame is missing; prepare the take again.")
    reference = {"image": reference_img, "corners_px": np.asarray(board["corners_px"], float)}
    progress("front_camera", 0.05, "Reading the front camera")
    frames, front_fps = fv.read_clip_frames(front_path)
    if len(frames) < 10:
        return _unavailable(out, record, "The front clip could not be read.")
    h, w = frames[0].shape[:2]
    aligned = fv.frame_corners(reference, frames)
    record["alignment"] = {k: v for k, v in aligned.items() if k != "corners"}
    if aligned["status"] != "measured":
        return _unavailable(out, record, aligned["reason"])
    corners = aligned["corners"]
    side_fps = float((results.get("quality") or {}).get("frame_rate_fps") or 60.0)
    events = results.get("event_frames") or {}
    release_side = events.get("release")
    contact = results.get("contact") if isinstance(results.get("contact"), dict) else {}
    contact_side = contact.get("frame")
    phase = results.get("board_phase") or {}
    if contact_side is None and isinstance(phase.get("touchdown"), dict):
        contact_side = phase["touchdown"].get("frame")
    release_front = side_to_front_frame(release_side, side_fps, link)
    contact_front = side_to_front_frame(contact_side, side_fps, link)
    contact_front_from_side = contact_front
    record["frames"] = {"front_fps": front_fps, "side_fps": side_fps, "release_side": release_side,
                        "release_front": release_front, "contact_side": contact_side, "contact_front": contact_front,
                        "front_frame_count": len(frames), "front_lag_s": float(link.get("front_lag_s") or 0.0)}
    # 1. Where it ended, across the board.
    progress("front_camera", 0.15, "Finding where the bag ended on the front camera")
    landing = fv.landing_from_front(frames, front_fps, corners, release_front, contact_front, reference,
                                    hfov_deg=link.get("front_hfov_pooled"))
    landing = resolve_knocked_bag(landing, phase)
    record["front_landing"] = landing
    if contact_front is None and (landing.get("contact") or {}).get("frame") is not None:
        # First contact found by the front camera only: express it in side frames for the replay too.
        contact_front = int(landing["contact"]["frame"])
        side_count = int((link.get("side_clip") or {}).get("frame_count") or 0)
        mapped = [(abs(m - contact_front), k) for k in range(side_count)
                  if (m := side_to_front_frame(k, side_fps, link)) is not None]
        record["frames"].update(contact_front=contact_front, contact_side=min(mapped)[1] if mapped else None,
                                contact_source=landing.get("contact_source"))
    # 2. Front pose → frontal-plane measures (and the release hand for the camera cross-check).
    pose_frames = None
    if front_pose is not None:
        pose_frames = fv.pose_frames_from_sequence(front_pose)
    elif run_pose:
        progress("front_camera", 0.3, "Tracking the body in the front camera")
        try:
            pose_frames = _front_pose(front_path, out, settings or {}, progress)
        except Exception as error:  # noqa: BLE001 - body measures stay unavailable, landing still counts
            record["notes"].append(f"Front-camera body tracking failed: {error}")
    release_distance = _summary(results, "release_to_board_front_m")
    release_height = _summary(results, "bag_release_height_m")
    if release_distance is None:
        pooled = athlete_release_distance(out)
        if pooled is not None:
            release_distance = pooled
            record["notes"].append(f"This throw's release distance was not measured; the athlete's median of the other "
                                   f"throws ({pooled:.2f} m) is used for the aim, which is therefore estimated.")
            record["release_distance_source"] = "athlete_median"
    release_px = None
    if pose_frames and release_front is not None:
        release_px = fv._mean_joint(pose_frames, release_front, f"{throwing_side}_wrist")
    at_release = corners[release_front] if release_front is not None and 0 <= release_front < len(corners) else corners[0]
    camera = fv.calibrate_front_camera(at_release, (w, h), None if release_px is None else release_px.tolist(),
                                       release_distance, release_height, link.get("front_hfov_pooled"))
    record["camera"] = {"hfov_deg": camera["hfov_deg"], "status": camera["status"], "source": camera.get("source"),
                        "deck_shape_hfov": camera.get("deck_shape"), "cross_check": camera.get("cross_check"),
                        "position_m": None if camera.get("pose") is None else camera["pose"]["centre_m"].tolist(),
                        "corner_residual_px": None if camera.get("pose") is None else camera["pose"]["residual_px"],
                        "reason": camera.get("reason")}
    # Deck-corner quality: with the field of view fixed, true corners leave ≤ 1.3 px of PnP residual on this
    # collection; a misplaced corner shows as a large residual and as a deck-shape field of view far from the
    # pooled one (Player 1 take 5: 6.5 px and 90.9° vs 66.1°). Then metric positions from the camera (stance,
    # release-hand offset, aim) are withheld; positions on the deck stay, with a note.
    residual = None if camera.get("pose") is None else float(camera["pose"]["residual_px"])
    shape_hfov = (camera.get("deck_shape") or {}).get("hfov_deg")
    pooled = link.get("front_hfov_pooled")
    suspect = (residual is not None and residual > MAX_CORNER_RESIDUAL_PX) or (
        shape_hfov is not None and pooled is not None and abs(float(shape_hfov) - float(pooled)) > MAX_HFOV_DEVIATION_DEG)
    record["camera"]["corners_suspect"] = bool(suspect)
    if suspect:
        camera = {**camera, "status": "estimated", "pose": None}
        record["camera"]["status"] = "estimated"
        record["notes"].append("The board's corners in the front camera look misplaced (the camera fit is poor), so "
                               "where the athlete stood and the aim are not measured on this take; left/right on the "
                               "board is approximate. Click the four deck corners to fix it.")
    if pose_frames and release_front is not None:
        record["frontal"] = fv.frontal_metrics(pose_frames, release_front, front_fps, throwing_side, camera, release_distance,
                                               roll_deg=fv.camera_roll_deg(at_release))
    else:
        record["frontal"] = {}
        record["notes"].append("Frontal-plane body measures need the front camera's body tracking at release.")
    # 3. Fuse the landing; 4. heading; 5. result and miss; 6. sync check; 7. replay path.
    final_camera = camera
    if landing.get("where") == "off" and not suspect:
        final_camera = fv.calibrate_front_camera(corners[-1], (w, h), None, None, None, camera["hfov_deg"])
    record["landing"] = fuse_landing(landing, phase, results, final_camera)
    offset = (record["frontal"].get("release_point_offset_m") or {}).get("value")
    # Heading from first contact; the resting place only for a bag that stayed on the board (a bag that slid
    # or bounced off ends far from where the flight was aimed).
    rest = record["landing"].get("rest") or {}
    touch = record["landing"].get("contact") or (rest if rest.get("on") == "board" else None)
    record["heading"] = fv.heading(offset, (touch or {}).get("x_in"), release_distance, (touch or {}).get("y_in"))
    if suspect:
        record["heading"] = {"status": "unavailable", "deg": None,
                             "reason": "The front camera's board corners look misplaced on this take."}
    if record.get("release_distance_source") == "athlete_median" and record["heading"].get("deg") is not None:
        record["heading"]["status"] = "estimated"
        for key in ("release_point_offset_m",):
            if (record["frontal"].get(key) or {}).get("value") is not None:
                record["frontal"][key]["status"] = "estimated"
    record["result"] = decide_result(record["landing"], results)
    if suspect:
        # Hole / board / off and the board positions come from the same misplaced corners: shown, not recorded.
        record["landing"]["status"] = "estimated"
        for key in ("contact", "rest"):
            if isinstance(record["landing"].get(key), dict):
                record["landing"][key]["status"] = "estimated"
        if record["result"].get("category") is not None:
            record["result"]["status"] = "needs_confirmation"
    record["miss"] = miss_vector(record["landing"])
    record["sync_check"] = sync_check(landing, contact_front_from_side)
    record["front_path"] = front_flight_path(frames, release_front, contact_front, release_px, corners, front_fps,
                                             hfov_deg=camera.get("hfov_deg"))
    record["deck_corners_px"] = corners[release_front if release_front is not None and 0 <= release_front < len(corners) else 0].tolist()
    record["deck_corners_by_frame_px"] = corners.round(1).tolist()
    record["front_size"] = [w, h]
    record["explanation"] = explain(record, results)
    record["board_phase"] = board_phase_with_front(record, results)
    record["auto_outcome"] = outcome_from_two_view(record)
    side_count = int((link.get("side_clip") or {}).get("frame_count")
                     or len((link.get("side_clip") or {}).get("frame_times_s") or []))
    record["side_to_front_frames"] = [side_to_front_frame(k, side_fps, link) for k in range(side_count)]
    write_json(out / "two_view.json", json_ready(record))
    progress("front_camera", 1.0, "Front camera done")
    return record


def _front_pose(front_path: str, out: Path, settings: dict[str, Any], progress: Progress):
    """Run the same Sports2D pose model on the front clip (cached in the analysis folder)."""
    from .models import PoseSequence
    from .serialization import canonical_hash
    from .sports2d_adapter import Sports2DAdapter
    from .video import read_video_metadata
    from .config import merged_config
    video = read_video_metadata(front_path)
    cache = out / "front_pose_raw.json"
    key_file = out / "front_pose_cache.json"
    key = canonical_hash({"video": video.sha256, "model": (settings or {}).get("sports2d")})
    if cache.exists() and key_file.exists() and json.loads(key_file.read_text()).get("key") == key:
        sequence = PoseSequence.load(cache)
    else:
        sequence = Sports2DAdapter().analyze(video, out / "front_sports2d", merged_config(settings or None),
                                             lambda s, f, m: progress("front_camera", 0.3 + 0.4 * f, m), "cpu")
        sequence.save(cache)
        key_file.write_text(json.dumps({"key": key}))
    return fv.pose_frames_from_sequence(sequence)


def resolve_knocked_bag(front: dict[str, Any], phase: dict[str, Any]) -> dict[str, Any]:
    """A throw that knocked another bag changes two places on the front camera (a bag on the deck and one
    under the board) and the front camera cannot tell which is the thrown one. The side camera follows the
    thrown bag from release to rest, so its ending decides: "rest" → the bag on the deck, "fell_in_hole" →
    the hole (Player 1: five such throws, the thrown bag stopping at the hole lip while it pushed the bag
    already there into the hole). Without a side ending the throw stays ambiguous (needs confirmation)."""
    candidates = front.get("ambiguous_candidates")
    if not front.get("ambiguous") or not candidates or phase.get("status") != "measured":
        return front
    kind = ((phase.get("end") or {}) if isinstance(phase.get("end"), dict) else {}).get("kind")
    choice = {"rest": "board", "fell_in_hole": "hole"}.get(kind or "")
    if choice is None:
        return front
    out = {**front, "where": choice, "rest": candidates[choice], "ambiguous_resolved_by": "side camera"}
    out["notes"] = list(front.get("notes") or []) + [
        "The side camera followed the thrown bag: it " + ("stopped on the board" if choice == "board" else
                                                          "went into the hole") + "; the other bag that moved was knocked."]
    return out


def fuse_landing(front: dict[str, Any], phase: dict[str, Any], results: dict[str, Any], camera: dict[str, Any]
                 ) -> dict[str, Any]:
    """Contact and rest in board inches (x across from the front camera, y along preferably from the side)."""
    out: dict[str, Any] = {"where": front.get("where"), "contact": None, "rest": None,
                           "deck_clear": bool(front.get("deck_clear")),
                           "x_source": "front camera deck homography",
                           "precision": front.get("precision")}
    touch = phase.get("touchdown") if isinstance(phase.get("touchdown"), dict) else None
    end = phase.get("end") if isinstance(phase.get("end"), dict) else None
    side_measured = phase.get("status") == "measured"
    if front.get("contact"):
        c = front["contact"]
        y_side = touch.get("v_in") if (side_measured and touch) else None
        out["contact"] = {"x_in": c["x_in"], "y_in": y_side if y_side is not None else c["y_in_front"],
                          "y_source": "side camera" if y_side is not None else "front camera"}
    rest = front.get("rest")
    if front.get("where") == "board" and rest:
        y_side = end.get("v_in") if (side_measured and end and end.get("kind") == "rest") else None
        out["rest"] = {"x_in": rest["x_in"], "y_in": y_side if y_side is not None else rest["y_in_front"],
                       "y_source": "side camera" if y_side is not None else "front camera", "on": "board"}
    elif front.get("where") == "hole":
        out["rest"] = {"x_in": fv.HOLE_X_IN, "y_in": fv.HOLE_Y_IN, "on": "hole", "y_source": "hole"}
    elif front.get("where") == "off" and rest:
        pose = camera.get("pose")
        floor = fv.ray_to_floor(pose, rest["bottom_px"], height_m=0.0) if pose is not None else None
        if floor is not None:
            # Floor (X, Y) in the throw frame → board-inch coordinates extended beyond the deck.
            x_in = floor[0] / INCH_M + fv.HOLE_X_IN
            y_in = floor[1] / (INCH_M * math.cos(Board().angle))
            out["rest"] = {"x_in": float(x_in), "y_in": float(y_in), "on": "floor", "y_source": "front camera floor plane",
                           "status": "measured" if camera.get("status") == "measured" else "estimated"}
        else:
            out["rest"] = {"x_in": rest.get("x_in_deck_plane"), "y_in": None, "on": "floor",
                           "status": "estimated", "y_source": None}
    return out


def board_phase_with_front(record: dict[str, Any], results: dict[str, Any]) -> dict[str, Any] | None:
    """The side camera's board phase (results.json → board_phase) with the front camera's measurements in:
    left/right (``right_of_centre_in``) at touchdown and at the end, how it ended (hole / rest / off the
    board), and the front camera's suggested result. Same shape the app already draws, so every board view
    shows the measured left/right. Side-camera values (along the deck, the slide physics) are kept."""
    landing = record.get("landing") or {}
    front = record.get("front_landing") or {}
    if front.get("status") != "measured":
        return None
    side = results.get("board_phase") if isinstance(results.get("board_phase"), dict) else {}
    phase: dict[str, Any] = {k: v for k, v in (side or {}).items()}
    phase["status"] = "measured"
    precision = ((front.get("precision") or {}).get("across_in_per_px"))
    phase["lateral"] = {"state": "front_camera", "precision_in": None if precision is None else max(0.25, 2 * precision),
                        "note": "Left/right measured by the front camera on the deck "
                                f"(about ±{max(0.25, 2 * (precision or 0.25)):.1f} in)."}
    contact = landing.get("contact") or {}
    touch = dict(phase.get("touchdown") or {})
    if touch and contact.get("x_in") is not None:
        touch["right_of_centre_in"] = contact["x_in"] - fv.HOLE_X_IN
        phase["touchdown"] = touch
    elif not touch and contact.get("x_in") is not None and contact.get("y_in") is not None:
        frame = (record.get("frames") or {}).get("contact_side")
        if frame is not None:
            phase["touchdown"] = {"frame": int(frame), "u_in": contact["x_in"], "v_in": contact["y_in"],
                                  "from_hole_in": contact["y_in"] - fv.HOLE_Y_IN, "on_deck": True,
                                  "basis": "front camera", "right_of_centre_in": contact["x_in"] - fv.HOLE_X_IN}
    rest = landing.get("rest") or {}
    end = dict(phase.get("end") or {})
    where = landing.get("where")
    end_frame = end.get("frame") or (record.get("frames") or {}).get("contact_side")
    if where == "hole":
        end.update(kind="fell_in_hole", v_in=fv.HOLE_Y_IN, from_hole_in=0.0, right_of_centre_in=0.0, frame=end_frame)
    elif where == "board" and rest.get("x_in") is not None and rest.get("y_in") is not None:
        end.update(kind="rest", v_in=rest["y_in"], from_hole_in=rest["y_in"] - fv.HOLE_Y_IN,
                   right_of_centre_in=rest["x_in"] - fv.HOLE_X_IN, frame=end_frame)
    elif where == "off":
        end.update(kind="left_deck", frame=end_frame,
                   v_in=rest.get("y_in") if rest.get("y_in") is not None else end.get("v_in"),
                   right_of_centre_in=None if rest.get("x_in") is None else rest["x_in"] - fv.HOLE_X_IN,
                   note="Ended off the board (front camera).")
        if end.get("v_in") is not None:
            end["from_hole_in"] = end["v_in"] - fv.HOLE_Y_IN
    if end.get("kind"):
        phase["end"] = end
    result = record.get("result") or {}
    if result.get("points") is not None:
        phase["suggested_outcome"] = {"score": result["points"], "basis": "front camera (looking straight at the hole)",
                                      "confidence": ("medium" if front.get("ambiguous_resolved_by") else "high")
                                      if result.get("views_agree") is not False
                                      and (not front.get("ambiguous") or front.get("ambiguous_resolved_by")) else "low"}
    if "touchdown" not in phase and "end" not in phase:
        return None
    return phase


def decide_result(landing: dict[str, Any], results: dict[str, Any]) -> dict[str, Any]:
    """Hole (3) / board (1) / off (0) from the front camera; the side camera's suggestion is a cross-check."""
    where = landing.get("where")
    category = {"hole": "throughHole", "board": "onBoard", "off": "offBoard"}.get(where or "")
    side = (results.get("suggested_outcome") or {}).get("category") if isinstance(results.get("suggested_outcome"), dict) else None
    phase_end = ((results.get("board_phase") or {}).get("end") or {}).get("kind")
    side_cat = ("throughHole" if phase_end == "fell_in_hole" else "onBoard" if phase_end == "rest"
                else "offBoard" if phase_end in SIDE_OFF_ENDS else side)
    source = "front camera" if category else None
    if category is None and landing.get("deck_clear"):
        # No new bag on the deck or in the hole (the front camera sees the whole deck): off the board. It is
        # only "suggested" when the side camera also saw the bag leave the deck or never land on it.
        category, source = "offBoard", "front camera (no new bag on the board or in the hole)"
        agree = True if side_cat == "offBoard" else (None if side_cat is None else False)
        return {"category": category, "points": 0, "source": source, "side_suggestion": side_cat, "views_agree": agree,
                "status": "suggested" if agree else "needs_confirmation"}
    agree = None if category is None or side_cat is None else category == side_cat
    if landing.get("ambiguous_resolved_by"):
        # The side ending chose between the front camera's two candidates, so it cannot also confirm the choice.
        agree = None
    return {"category": category, "points": {"throughHole": 3, "onBoard": 1, "offBoard": 0}.get(category or ""),
            "source": source, "side_suggestion": side_cat, "views_agree": agree,
            "status": "needs_confirmation" if category is None or agree is False else "suggested"}


def miss_vector(landing: dict[str, Any]) -> dict[str, Any]:
    """Signed miss at rest from the hole centre in the thrower's frame (inches): long +, right +."""
    rest = landing.get("rest")
    if not rest or rest.get("x_in") is None:
        return {"status": "unavailable", "reason": "Where the bag stopped is not known in both directions."}
    if rest.get("on") == "hole":
        return {"status": "measured", "short_long_in": 0.0, "left_right_in": 0.0, "distance_in": 0.0}
    right = float(rest["x_in"]) - fv.HOLE_X_IN          # x grows to the thrower's right
    long = None if rest.get("y_in") is None else float(rest["y_in"]) - fv.HOLE_Y_IN
    return {"status": rest.get("status", "measured") if long is not None else "partial",
            "short_long_in": long, "left_right_in": right,
            "distance_in": None if long is None else math.hypot(long, right)}


def sync_check(front_landing: dict[str, Any], contact_front: int | None) -> dict[str, Any]:
    """Do both cameras see first contact at the same moment? (A direct check of the sound sync.)"""
    path = front_landing.get("path") or []
    if contact_front is None or not path:
        return {"status": "unavailable"}
    first_on_deck = next((p for p in path if fv.point_in_deck(p["deck_in"], 0.0)), None)
    if first_on_deck is None:
        return {"status": "unavailable"}
    gap = first_on_deck["frame"] - contact_front
    return {"status": "measured", "front_frames_difference": int(gap),
            "agrees": abs(gap) <= SYNC_FRAME_TOLERANCE + 2}


FRONT_LAG_MIN_THROWS = 8       # throws with both contacts seen before a set-up's picture lag is estimated
FRONT_LAG_MAX_S = 0.10         # 3 front frames: beyond that it is not exposure/readout lag but a sync or tracking fault
FRONT_LAG_MAX_IQR_S = 0.07     # about 2 front frames of spread between throws
LAG_COMPATIBLE_VERSIONS = {"two_view_v2", "two_view_v3_front_lag"}   # same front tracker (front_track.py)


def pool_front_lag(analysis_dirs: list[Path]) -> dict[str, Any]:
    """Constant picture lag of the front camera relative to the sound sync, per front camera set-up.

    The sound sync aligns the two soundtracks (±17.5 ms), but what each phone *shows* at a timestamp also
    depends on its exposure and rolling-shutter readout (the deck sits low in the front picture, read out late)
    and on audio-path latency. The tracking audit found the front camera showing first contact and release one
    front frame after the sound-mapped frame on all six audited throws. The lag is measured on every throw where
    both views saw first contact: (first on-deck frame in the front camera − side contact mapped to the front)
    / front fps, plus the lag that mapping already used, minus the expected frame quantisation. The set-up's
    interquartile mean (≥ FRONT_LAG_MIN_THROWS throws, gated on size and spread) is written into each take record
    as ``front_lag_s`` and used by ``side_to_front_frame``; one throw's value is ±1–2 frames (a 30 fps camera,
    a bag landing within a frame), the pooled value is steadier.
    """
    from .takes import front_setups
    per_take: dict[Path, list[float]] = {}
    for folder in analysis_dirs:
        folder = Path(folder)
        link_path = folder / TAKE_LINK_FILENAME
        record_path = folder / "two_view.json"
        if not link_path.exists() or not record_path.exists():
            continue
        try:
            link = json.loads(link_path.read_text())
            record = json.loads(record_path.read_text())
        except (OSError, ValueError):
            continue
        if record.get("method_version") not in LAG_COMPATIBLE_VERSIONS:
            continue                        # older front tracking: its first on-deck frame is not comparable
        check = record.get("sync_check") or {}
        frames = record.get("frames") or {}
        fps = frames.get("front_fps")
        if check.get("status") != "measured" or check.get("front_frames_difference") is None or not fps:
            continue
        # Both "first on the deck" frames come after the true contact by half a frame on average (front: half a
        # front frame, side: half a side frame), while the mapping rounds to the nearest frame; remove that
        # expected quantisation so a camera pair with no picture lag gives zero.
        side_fps = float(frames.get("side_fps") or 60.0)
        quantisation = 0.5 / float(fps) - 0.5 / side_fps
        lag = (float(frames.get("front_lag_s") or 0.0) + float(check["front_frames_difference"]) / float(fps)
               - quantisation)
        take = (folder / link["take_record"]).resolve()
        per_take.setdefault(take, []).append(lag)
    out: dict[str, Any] = {}
    for key, takes in front_setups(list(per_take)).items():
        values = [v for t in takes for v in per_take.get(t, [])]
        if len(values) < FRONT_LAG_MIN_THROWS:
            out[key] = {"status": "unavailable", "throws": len(values),
                        "reason": f"Fewer than {FRONT_LAG_MIN_THROWS} throws with first contact seen by both cameras."}
            continue
        # Interquartile mean: robust to a mistracked throw like the median, but not stuck on whole frames
        # (each throw's difference is a whole number of frames).
        q1, q3 = np.percentile(values, [25, 75])
        middle = [v for v in values if q1 <= v <= q3]
        median = float(np.mean(middle)) if middle else float(np.median(values))
        summary = {"status": "measured", "lag_s": median, "throws": len(values), "iqr_s": float(q3 - q1)}
        if abs(median) > FRONT_LAG_MAX_S or q3 - q1 > FRONT_LAG_MAX_IQR_S:
            # Not a constant picture lag (tracking or sync trouble): leave the mapping as the sound gives it.
            summary.update(status="rejected", reason=f"Median {median * 1000:.0f} ms, spread (IQR) "
                           f"{(q3 - q1) * 1000:.0f} ms: outside ±{FRONT_LAG_MAX_S * 1000:.0f} ms / "
                           f"{FRONT_LAG_MAX_IQR_S * 1000:.0f} ms.")
            median = 0.0
        summary["applied_s"] = median
        for take in takes:
            data = json.loads(take.read_text())
            data["front_lag_s"] = median
            data["front_lag_pool"] = summary
            take.write_text(json.dumps(json_ready(data), indent=2))
        out[key] = summary
    return out


def front_flight_path(frames: list[np.ndarray], release_front: int | None, contact_front: int | None,
                      release_px: np.ndarray | None = None, corners: np.ndarray | None = None,
                      fps: float = 30.0, hfov_deg: float | None = None) -> list[dict[str, Any]]:
    """The bag's path in the front image between release and first contact (for the replay overlay).

    Moving bag-red blobs in every frame; the bag is the set that follows one projectile through the camera
    (``front_track.flight_path``, METHODS_AND_MATH §5.2), fitted to all frames at once. Frames where the bag
    was not seen on that path are left out; with no consistent path the list is empty. ``corners`` (deck
    corners per frame) remove the camera's drift and say where first contact must be. Display only: no
    number is computed from this path.
    """
    from .front_track import flight_path
    result = flight_path(frames, release_front, contact_front, release_px=release_px,
                         corners_per_frame=corners, fps=fps, hfov_deg=hfov_deg)
    return [{"frame": p["frame"], "px": p["px"]} for p in result["path"]]


# ------------------------------------------------------------------------------------------------
# The coach sentence


def _side(value_in: float) -> str:
    return "right" if value_in > 0 else "left"


def explain(record: dict[str, Any], results: dict[str, Any]) -> dict[str, Any]:
    """One plain sentence (plus the parts it was built from).

    Made throws get no correction (outcome first). For a miss or a board bag:
    * distance part: ``N in short/long`` at rest, with the measured release speed;
    * direction part: ``N in left/right`` with the measured aim (heading) and, only when they point the same
      way as the miss, the frontal measures that go with it: the hand finishing across the body (sends the bag
      towards the non-throwing side) or swinging out (towards the throwing side), at least 0.25 shoulder widths
      (about twice their noise); or standing at least 15 cm off the centre line on the side of the miss.
      Trunk side lean is a steady personal trait for most athletes, so it is compared across throws on the
      athlete summary, not named per throw. Associations, not causes: never "because".
    """
    result = record.get("result") or {}
    miss = record.get("miss") or {}
    heading = record.get("heading") or {}
    frontal = record.get("frontal") or {}
    side = results.get("throwing_side") or "right"
    throwing_sign = 1.0 if side == "right" else -1.0      # + = the thrower's right
    parts: list[dict[str, Any]] = []
    if result.get("category") == "throughHole":
        return {"sentence": "In the hole — nothing to correct on this throw.", "parts": [], "kind": "made"}
    sentence_bits: list[str] = []
    long = miss.get("short_long_in")
    right = miss.get("left_right_in")
    if long is not None and abs(long) >= DISTANCE_ON_TARGET_IN:
        word = "long" if long > 0 else "short"
        bit = f"{abs(long):.0f} in {word}"
        v = _summary(results, "bag_release_speed_m_s")
        parts.append({"axis": "distance", "inches": long, "word": word})
        if v is not None:
            bit += f" (release {v:.1f} m/s)"
        sentence_bits.append(bit)
    if right is not None and abs(right) >= LATERAL_ON_LINE_IN:
        word = _side(right)
        bit = f"{abs(right):.0f} in {word}"
        detail = []
        if heading.get("deg") is not None and abs(heading["deg"]) >= 0.3:
            detail.append(f"aimed {abs(heading['deg']):.1f}° {_side(heading['deg'])}")
        arm = (frontal.get("arm_across_body_sw") or {}).get("value")
        if arm is not None and abs(arm) >= 0.25:
            pushes = -throwing_sign if arm > 0 else throwing_sign      # across → non-throwing side
            if np.sign(pushes) == np.sign(right):
                detail.append("hand finished across the body" if arm > 0 else "hand swung out away from the body")
        stance = (frontal.get("stance_offset_m") or {}).get("value")
        if stance is not None and abs(stance) >= 0.15 and np.sign(stance) == np.sign(right):
            detail.append(f"stood {abs(stance) * 100:.0f} cm {_side(stance)} of the centre line")
        if detail:
            bit += " — " + ", ".join(detail)
        parts.append({"axis": "direction", "inches": right, "word": word, "details": detail})
        sentence_bits.append(bit)
    if not sentence_bits:
        if result.get("category") == "offBoard":
            aim = (f" — aimed {abs(heading['deg']):.1f}° {_side(heading['deg'])}"
                   if heading.get("deg") is not None and abs(heading["deg"]) >= 0.3 else "")
            return {"sentence": f"Off the board{aim}; where it stopped was out of the front camera's view.",
                    "parts": parts, "kind": "miss"}
        if result.get("category") == "onBoard":
            return {"sentence": "On the board close to the hole — distance and line were both within 3 in.",
                    "parts": parts, "kind": "close"}
        return {"sentence": "Where the bag ended could not be measured in both directions.", "parts": parts,
                "kind": "unknown"}
    lead = {"onBoard": "On the board", "offBoard": "Off the board"}.get(result.get("category") or "", "Ended")
    return {"sentence": f"{lead}: " + "; ".join(sentence_bits) + ".", "parts": parts, "kind": "miss"}

AUTO_OUTCOME_NOTE = "Recorded automatically from the front camera; check the video and change it if it is wrong."


def outcome_from_two_view(record: dict[str, Any]) -> dict[str, Any] | None:
    """A TrialOutcome (project.json shape) from the front camera, or None when it is not confident.

    Only a confident result is recorded: the front camera decided hole / board / off and, when the side
    camera also saw the board, both agreed; the throw did not move another bag (ambiguous). First
    contact and rest are stored as board points (inches, the board-camera precision label) when they lie
    on the deck.
    """
    result = record.get("result") or {}
    if record.get("status") != "measured" or result.get("points") is None or result.get("status") != "suggested":
        return None
    front = record.get("front_landing") or {}
    if front.get("ambiguous") and not front.get("ambiguous_resolved_by"):
        return None
    landing = record.get("landing") or {}

    def point(p: dict[str, Any] | None) -> dict[str, Any] | None:
        if not p or p.get("x_in") is None or p.get("y_in") is None:
            return None
        if not (0 <= p["x_in"] <= 24 and 0 <= p["y_in"] <= 48):
            return None
        return {"x_inches": round(float(p["x_in"]), 2), "y_inches": round(float(p["y_in"]), 2),
                "precision": "board_camera_homography"}

    rest = landing.get("rest") if (landing.get("rest") or {}).get("on") in ("board", "hole") else None
    return {"intended_target": "Hole center", "score_category": int(result["points"]), "throw_type": "Standard",
            "notes": AUTO_OUTCOME_NOTE, "intended_point": None,
            "first_contact_point": point(landing.get("contact")), "final_resting_point": point(rest)}
