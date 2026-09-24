"""Release-onset audit (Task 9b): contact sheets around the detected release and a per-throw table.

For every analysed throw folder under `--analyses` (a `regression_check.py` scratch directory)
whose automatic flight was accepted, this writes a contact sheet of frames release−8 … release+3
into `--sheets`: 2× crops centred on the hand point, with

* the wrist landmark (blue ring),
* the hand point, wrist + 0.34 arm length along the forearm (green cross; chain.py's bag point),
* the bag detection used by the flight (red ring), or, before the first detection, the flight
  traced backwards with a local quadratic of its first 8 detections (orange ring),

and the frame number, with tags R (detected release = first free-flight frame), C (the
backward-flight/wrist cue, `release_check`), A (hand-angle match: the frame in release−8 …
release where the hand-point velocity direction in the board plane is closest to the bag's
fitted release angle) and V (the visual frame, when given).

A person (or reviewer) looks at each sheet and records the visual release = the first frame
where the bag has visibly separated from the fingers, in a JSON file
`{"Throw-XXXX": 123 | [lo, hi] | null, ...}` passed as `--visual`. The table then reports
method − visual for each method (a range counts as 0 inside it, else the distance to its nearest
end) and how many are within ±1 frame.

    PYTHONPATH=python .venv/bin/python scripts/release_audit.py --analyses /tmp/regression \
        --sheets /tmp/release-audit/sheets --visual visual.json --output audit.json

Only reads the analysed folders and the source videos; never point `--analyses` at a library.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import cv2
import numpy as np

HAND_OFFSET_ARM_LENGTHS = 0.34
BEFORE, AFTER = 8, 3
SCALE = 2
COLUMNS = 4


def _load(path: Path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def arm_points(directory: Path, side: str, frame_count: int) -> dict[str, np.ndarray]:
    """Filtered shoulder/elbow/wrist pixels per frame from keypoints.csv (NaN where missing)."""
    names = {f"{side}_{j}": j for j in ("shoulder", "elbow", "wrist")}
    out = {j: np.full((frame_count, 2), np.nan) for j in names.values()}
    with open(directory / "keypoints.csv", newline="") as handle:
        for row in csv.DictReader(handle):
            joint = names.get(row["landmark"])
            f = int(row["frame"])
            if joint and f < frame_count and row["filtered_x_px"] not in ("", "nan"):
                out[joint][f] = (float(row["filtered_x_px"]), float(row["filtered_y_px"]))
    return out


def hand_point(arm: dict[str, np.ndarray]) -> tuple[np.ndarray, float]:
    """chain.py's bag point in pixels: wrist + 0.34 arm length along the forearm."""
    upper = np.linalg.norm(arm["elbow"] - arm["shoulder"], axis=1)
    fore = np.linalg.norm(arm["wrist"] - arm["elbow"], axis=1)
    length = float(np.nanmedian(upper) + np.nanmedian(fore))
    unit = (arm["wrist"] - arm["elbow"]) / fore[:, None]
    return arm["wrist"] + HAND_OFFSET_ARM_LENGTHS * length * unit, length


def backward_flight(points: list[dict], fps: float):
    """Bag position per frame: the detection when there is one, else a local quadratic of the first 8."""
    early = points[:8]
    first = early[0]["frame"]
    t = np.array([(p["frame"] - first) / fps for p in early])
    degree = 2 if len(early) >= 5 else 1
    cx = np.polyfit(t, [p["x"] for p in early], degree)
    cy = np.polyfit(t, [p["y"] for p in early], degree)
    by_frame = {p["frame"]: (p["x"], p["y"]) for p in points}

    def at(f: int) -> tuple[tuple[float, float], bool]:
        if f in by_frame:
            return by_frame[f], True
        s = (f - first) / fps
        return (float(np.polyval(cx, s)), float(np.polyval(cy, s))), False
    return at


def angle_match_frame(results: dict, release: int, before: int = BEFORE) -> tuple[int | None, list[dict]]:
    """Frame in release−8 … release where the hand-point direction (board plane) is closest to the bag's angle."""
    chain = results.get("chain") or {}
    series = chain.get("series") or {}
    bag_angle = ((chain.get("quantities") or {}).get("release_angle_deg") or {}).get("value")
    velocity, start = series.get("velocity_m_s"), series.get("start_frame")
    if bag_angle is None or not velocity or start is None:
        return None, []
    rows = []
    for f in range(release - before, release + 1):
        i = f - start
        if 0 <= i < len(velocity) and velocity[i] and all(v is not None for v in velocity[i]):
            vx, vy = velocity[i]
            angle = math.degrees(math.atan2(vy, vx))
            rows.append({"frame": f, "hand_angle_deg": angle, "diff_deg": angle - bag_angle,
                         "hand_speed_m_s": math.hypot(vx, vy)})
    if not rows:
        return None, rows
    best = min(rows, key=lambda r: abs(r["diff_deg"]))
    return best["frame"], rows


def read_frames(video: str, first: int, last: int) -> dict[int, np.ndarray]:
    capture = cv2.VideoCapture(video)
    out, f = {}, 0
    while f <= last:
        ok, image = capture.read()
        if not ok:
            break
        if f >= first:
            out[f] = image
        f += 1
    capture.release()
    return out


def contact_sheet(path: Path, images: dict[int, np.ndarray], hand: np.ndarray, wrist: np.ndarray, bag_at,
                  half: int, tags: dict[int, str], scale: int = SCALE) -> None:
    panels = []
    for f in sorted(images):
        image = images[f]
        centre = hand[f] if np.isfinite(hand[f]).all() else wrist[f]
        if not np.isfinite(centre).all():
            centre = np.array([image.shape[1] / 2, image.shape[0] / 2])
        x0, y0 = int(round(centre[0])) - half, int(round(centre[1])) - half
        pad = cv2.copyMakeBorder(image, half, half, half, half, cv2.BORDER_CONSTANT, value=(40, 40, 40))
        crop = pad[y0 + half:y0 + 3 * half, x0 + half:x0 + 3 * half]
        crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

        def to_panel(p):
            return int(round((p[0] - x0) * scale)), int(round((p[1] - y0) * scale))
        if np.isfinite(wrist[f]).all():
            cv2.circle(crop, to_panel(wrist[f]), 5, (255, 140, 0), 1, cv2.LINE_AA)
        if np.isfinite(hand[f]).all():
            cv2.drawMarker(crop, to_panel(hand[f]), (0, 220, 0), cv2.MARKER_CROSS, 12, 1, cv2.LINE_AA)
        (bx, by), detected = bag_at(f)
        cv2.circle(crop, to_panel((bx, by)), 22, (0, 0, 255) if detected else (0, 165, 255), 1, cv2.LINE_AA)
        label = f"{f} {tags.get(f, '')}".strip()
        cv2.rectangle(crop, (0, 0), (len(label) * 13 + 8, 26), (0, 0, 0), -1)
        cv2.putText(crop, label, (4, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
        panels.append(crop)
    while len(panels) % COLUMNS:
        panels.append(np.zeros_like(panels[0]))
    rows = [np.hstack(panels[i:i + COLUMNS]) for i in range(0, len(panels), COLUMNS)]
    cv2.imwrite(str(path), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 92])


def error_to_visual(frame: int | None, visual) -> float | None:
    """method − visual; a visual range counts 0 inside it, else the signed distance to its nearest end."""
    if frame is None or visual is None:
        return None
    lo, hi = (visual, visual) if isinstance(visual, (int, float)) else visual
    return 0.0 if lo <= frame <= hi else float(frame - (lo if frame < lo else hi))


def audit_throw(directory: Path, sheets: Path | None, visual, before: int = BEFORE, after: int = AFTER,
                scale: int = SCALE) -> dict | None:
    auto = _load(directory / "auto_flight.json", {}) or {}
    if auto.get("status") != "accepted":
        return None
    results = _load(directory / "results.json", {}) or {}
    context = (_load(directory / "manifest.json", {}) or {}).get("trial_context") or {}
    fps = float(auto["fps"])
    release = int(auto["release_frame"])
    count = int(auto.get("frames_processed") or release + AFTER + 1)
    arm = arm_points(directory, context["throwing_side"], count)
    hand, arm_px = hand_point(arm)
    bag_at = backward_flight(auto["points"], fps)
    check = (auto.get("release_check") or {}).get("frame")
    match, angle_rows = angle_match_frame(results, release)
    first_fit = int(auto["fit"]["first_frame"])

    def distance(f):
        if f is None or not 0 <= f < count or not np.isfinite(hand[f]).all():
            return None
        (bx, by), _ = bag_at(f)
        d = float(np.hypot(bx - hand[f][0], by - hand[f][1]))
        return {"px": round(d, 1), "arm_lengths": round(d / arm_px, 3)}
    lo_visual = None if visual is None else (visual if isinstance(visual, (int, float)) else visual[0])
    per_frame = {f: distance(f) for f in range(release - BEFORE, release + AFTER + 1)}
    row = {
        "throw": directory.name, "fps": fps, "arm_px": round(arm_px, 1),
        "release": release, "release_check": check, "angle_match": match, "fit_first_frame": first_fit,
        "visual": visual,
        "distance_hand_to_bag": {"release": distance(release), "release_check": distance(check),
                                 "angle_match": distance(match), "visual": distance(lo_visual)},
        "distance_by_frame": {str(f): d for f, d in per_frame.items()},
        "angle_rows": angle_rows,
        "errors": {k: error_to_visual(v, visual) for k, v in
                   (("release", release), ("release_check", check), ("angle_match", match))},
        # Against the last frame of a range alone (the first frame with a clear gap).
        "errors_vs_clear_gap": {k: error_to_visual(v, None if visual is None else
                                                   (visual if isinstance(visual, (int, float)) else visual[-1]))
                                for k, v in (("release", release), ("release_check", check), ("angle_match", match))},
    }
    if sheets is not None:
        tags: dict[int, list[str]] = {}
        for tag, f in (("R", release), ("C", check), ("A", match)):
            if f is not None:
                tags.setdefault(f, []).append(tag)
        if visual is not None:
            lo, hi = (visual, visual) if isinstance(visual, (int, float)) else visual
            for f in range(int(lo), int(hi) + 1):
                tags.setdefault(f, []).append("V")
        images = read_frames(context["source_video"], release - before, release + after)
        half = int(np.clip(0.8 * arm_px, 70, 140))
        contact_sheet(sheets / f"{directory.name}.jpg", images, hand, arm["wrist"], bag_at, half,
                      {f: "".join(t) for f, t in tags.items()}, scale)
    return row


def summarise(rows: list[dict], field: str = "errors") -> dict:
    out = {}
    for key in ("release", "release_check", "angle_match"):
        errors = [r[field][key] for r in rows if r[field][key] is not None]
        if errors:
            out[key] = {"n": len(errors), "mean": float(np.mean(errors)), "sd": float(np.std(errors, ddof=1))
                        if len(errors) > 1 else 0.0, "within_1": sum(abs(e) <= 1 for e in errors)}
    return out


def markdown(rows: list[dict]) -> str:
    def d(x):
        return "—" if x is None else f"{x['px']:.0f} px / {x['arm_lengths']:.2f}"
    lines = ["| throw | release R | cue C | angle match A | visual V | fit first | R−V | C−V | A−V | "
             "hand–bag at R | at C | at A | at V |", "|" + "---|" * 13]
    for r in rows:
        v = r["visual"]
        vs = "—" if v is None else (str(v) if isinstance(v, (int, float)) else f"{v[0]}–{v[1]}")
        e = r["errors"]
        dist = r["distance_hand_to_bag"]
        fmt = lambda x: "—" if x is None else f"{x:+.0f}"
        lines.append(f"| {r['throw']} | {r['release']} | {r['release_check']} | {r['angle_match']} | {vs} | "
                     f"{r['fit_first_frame']} | {fmt(e['release'])} | {fmt(e['release_check'])} | "
                     f"{fmt(e['angle_match'])} | {d(dist['release'])} | {d(dist['release_check'])} | "
                     f"{d(dist['angle_match'])} | {d(dist['visual'])} |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--analyses", required=True)
    parser.add_argument("--sheets", help="Directory for the contact sheets (omit to skip them).")
    parser.add_argument("--visual", help="JSON {throw: frame | [lo, hi] | null} of visually judged release frames.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--throw", action="append", help="Only this throw folder name (repeatable).")
    parser.add_argument("--before", type=int, default=BEFORE, help="Sheet frames before release (default 8).")
    parser.add_argument("--after", type=int, default=AFTER, help="Sheet frames after release (default 3).")
    parser.add_argument("--scale", type=int, default=SCALE, help="Crop magnification (default 2).")
    args = parser.parse_args()
    visual = _load(Path(args.visual), {}) if args.visual else {}
    sheets = Path(args.sheets) if args.sheets else None
    if sheets:
        sheets.mkdir(parents=True, exist_ok=True)
    rows = []
    for directory in sorted(Path(args.analyses).glob("Throw-*")):
        if args.throw and directory.name not in args.throw:
            continue
        row = audit_throw(directory, sheets, visual.get(directory.name), args.before, args.after, args.scale)
        if row is not None:
            rows.append(row)
    summary = {"vs_visual_range": summarise(rows), "vs_clear_gap_frame": summarise(rows, "errors_vs_clear_gap")}
    Path(args.output).write_text(json.dumps({"rows": rows, "summary": summary}, indent=2))
    print(markdown(rows))
    for basis, block in summary.items():
        print(f"\n{basis}:")
        for key, s in block.items():
            print(f"  {key}: n={s['n']} mean {s['mean']:+.2f} SD {s['sd']:.2f} frames; "
                  f"within ±1: {s['within_1']}/{s['n']}")


if __name__ == "__main__":
    main()
