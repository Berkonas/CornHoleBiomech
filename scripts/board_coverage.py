"""Board-detection coverage over a library run (Task 8c): one row per throw, plus counts.

Reads each analysed throw folder under `--analyses` (a `regression_check.py` scratch directory)
and reports what the automatic tracking and the board
detector found: flight status, release frame, board status/confidence/hole offset/reasons, the
out-of-plane angle phi, the contact kind/state and the per-throw field-of-view calibration.

Board detection runs on a plate built in the chosen flight's release frame. For a throw whose
flight was not accepted, `--reference-plates` also detects the board on a plate built in the
clip's middle frame, to separate "no board in this clip" from "no accepted flight". With
`--qa-dir`, every throw whose board was not found gets a QA image there (its plate with the
best-guess quad drawn), for a person to classify the miss.

    PYTHONPATH=python .venv/bin/python scripts/board_coverage.py --analyses /tmp/regression \
        --qa-dir /tmp/board-qa --output coverage.json --reference-plates

Point it at scratch copies, never at a library: it only reads the analysed folders, except that
`--reference-plates` may (re)build a folder's person-mask cache (`scene_vision/`). Prints a
Markdown table and the counts (throws, flights accepted, boards found, found among accepted
flights, found by the relaxed pale-deck pass, per-throw HFOV measured).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np


def _load(path: Path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def reference_plate_board(video_path: str, target_direction: str, cache_dir: Path) -> dict:
    """Board on a plate in the clip's middle frame (independent of any flight)."""
    from cornhole_biomech.auto_bag import (_scene_and_board, detect_moving_blobs_in_frames, read_frames,
                                           reference_chain)
    from cornhole_biomech.scene import person_masks
    frames, _ = read_frames(video_path)
    _, to_prev = detect_moving_blobs_in_frames(frames)
    reference = len(frames) // 2
    height, width = frames[0].shape[:2]
    masks = person_masks(video_path, cache_dir, (width, height))["masks"]
    _, board = _scene_and_board(frames, reference_chain(to_prev, reference), target_direction, masks)
    board = {k: v for k, v in board.items() if k != "model"}
    return {**board, "reference_frame": reference}


def row_for(directory: Path, reference_plates: bool) -> dict:
    manifest = _load(directory / "manifest.json", {})
    context = manifest.get("trial_context") or {}
    auto = _load(directory / "auto_flight.json", {}) or {}
    results = _load(directory / "results.json", {}) or {}
    board = auto.get("board") or {}
    scale = results.get("scale") or {}
    contact = auto.get("contact") or {}
    row = {
        "trial_id": context.get("trial_id") or directory.name,
        "folder": directory.name,
        "athlete_id": context.get("athlete_id"),
        "clip": Path(context.get("source_video") or "").name,
        "flight_status": auto.get("status"),
        "release_frame": auto.get("release_frame"),
        "board_reference_frame": board.get("reference_frame", auto.get("release_frame")),
        "board_status": board.get("status"),
        "board_red_min_sat": board.get("red_min_sat"),
        "board_confidence": board.get("confidence"),
        "hole_offset_in": board.get("hole_offset_in"),
        "board_reasons": board.get("reasons") or [],
        "corners_px": board.get("corners_px"),
        "phi_deg": board.get("phi_deg"),
        "contact_kind": contact.get("kind"),
        "contact_state": contact.get("state"),
        "per_throw_hfov_deg": scale.get("per_throw_hfov_deg"),
        "per_throw_hfov_status": scale.get("per_throw_hfov_status"),
        "scale_status": scale.get("status"),
        "hfov_deg": scale.get("hfov_deg"),
        "hfov_source": scale.get("hfov_source"),
    }
    if reference_plates and auto.get("status") != "accepted":
        direction = context.get("target_direction")
        if not context.get("source_video") or direction not in ("left_to_right", "right_to_left"):
            row["reference_plate_board"] = {"status": "skipped",
                                            "reasons": ["manifest has no source_video or target_direction"]}
        else:
            row["reference_plate_board"] = reference_plate_board(context["source_video"], direction, directory)
    return row


def save_qa(directory: Path, row: dict, qa_dir: Path) -> Path | None:
    plate = cv2.imread(str(directory / "plate.jpg"))
    if plate is None:
        return None
    if row["corners_px"]:
        quad = np.round(np.asarray(row["corners_px"], float)).astype(np.int32)
        cv2.polylines(plate, [quad], True, (0, 0, 255), 2)
        cv2.circle(plate, tuple(int(v) for v in quad[0]), 5, (0, 255, 255), -1)   # front-far corner
    label = f"{row['trial_id']} {row['board_status']} conf={row['board_confidence'] or 0:.2f}"
    cv2.putText(plate, label, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
    qa_dir.mkdir(parents=True, exist_ok=True)
    out = qa_dir / f"miss_{row['trial_id']}.jpg"
    cv2.imwrite(str(out), plate)
    return out


def counts(rows: list[dict]) -> dict:
    accepted = [r for r in rows if r["flight_status"] == "accepted"]
    found = [r for r in rows if r["board_status"] == "found"]
    ref_found = [r for r in rows if r["board_status"] != "found"
                 and (r.get("reference_plate_board") or {}).get("status") == "found"]
    from cornhole_biomech.board import RED_MIN_SAT
    return {"throws": len(rows), "flights_accepted": len(accepted), "boards_found": len(found),
            "boards_found_by_relaxed_pass": sum(1 for r in found if (r.get("board_red_min_sat") or RED_MIN_SAT) < RED_MIN_SAT),
            "boards_found_among_accepted": sum(1 for r in accepted if r["board_status"] == "found"),
            "boards_found_only_on_reference_plate": len(ref_found),
            "per_throw_hfov_measured": sum(1 for r in rows if r["per_throw_hfov_status"] == "measured")}


def markdown(rows: list[dict]) -> str:
    def f(v, digits=2):
        return "—" if v is None else (f"{v:.{digits}f}" if isinstance(v, float) else str(v))
    lines = ["| trial | athlete | clip | flight | release | board | min S | conf | hole (in) | reasons | phi (°) "
             "| contact | per-throw HFOV (°) | HFOV used (°) |", "|" + "---|" * 14]
    for r in rows:
        reason = "; ".join(r["board_reasons"])[:70] or "—"
        ref = r.get("reference_plate_board")
        board = r["board_status"] + (f" (mid-frame plate: {ref['status']})" if ref else "")
        lines.append(f"| {r['trial_id'][:8]} | {(r['athlete_id'] or '')[:8]} | {r['clip']} | {r['flight_status']} "
                     f"| {f(r['release_frame'])} | {board} | {f(r.get('board_red_min_sat'))} "
                     f"| {f(r['board_confidence'])} | {f(r['hole_offset_in'], 1)} "
                     f"| {reason} | {f(r['phi_deg'], 1)} | {r['contact_kind']}/{r['contact_state']} "
                     f"| {f(r['per_throw_hfov_deg'], 1)} {r['per_throw_hfov_status'] or ''} "
                     f"| {f(r['hfov_deg'], 1)} {r['scale_status'] or ''} ({r['hfov_source'] or '—'}) |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analyses", required=True, help="Folder holding one analysed folder per throw")
    parser.add_argument("--output", help="JSON file for the rows and counts")
    parser.add_argument("--qa-dir", help="Save a QA image for every throw whose board was not found")
    parser.add_argument("--reference-plates", action="store_true",
                        help="Also detect the board on a middle-frame plate for throws without an accepted flight")
    args = parser.parse_args()
    root = Path(args.analyses).expanduser()
    dirs = sorted(p.parent for p in root.glob("*/manifest.json"))
    rows = []
    for directory in dirs:
        row = row_for(directory, args.reference_plates)
        if args.qa_dir and row["board_status"] != "found":
            row["qa_image"] = str(save_qa(directory, row, Path(args.qa_dir)))
        rows.append(row)
    summary = counts(rows)
    print(markdown(rows))
    print(json.dumps(summary, indent=2))
    if args.output:
        Path(args.output).write_text(json.dumps({"rows": rows, "counts": summary}, indent=2))


if __name__ == "__main__":
    main()
