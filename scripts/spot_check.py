"""Light engineering validation: one contact sheet per throw for a quick visual check.

Row 1: release filmstrip (release −3 … +3 frames) with the automatic bag centre and
       wrist, so the release frame can be judged in seconds.
Row 2: apex, first contact and final rest, each cropped around the automatic marker.
Markers: magenta = bag centre (release-frame path mapped onto that frame),
cyan = throwing wrist. A reviewer notes per event: correct / off by n frames /
marker off the bag. See docs/LIGHT_VALIDATION.md for the protocol and results.

    PYTHONPATH=python .venv/bin/python scripts/spot_check.py --library ~/Documents/"Cornhole Pilot Library" \
        --output spot-check --throws Throw-D4FF5A49 Throw-19A9640F
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

CROP = 160


def _frames(video: str, wanted: set[int]) -> dict[int, np.ndarray]:
    capture, out, index = cv2.VideoCapture(video), {}, 0
    while wanted - set(out):
        ok, frame = capture.read()
        if not ok:
            break
        if index in wanted:
            out[index] = frame
        index += 1
    capture.release()
    return out


def _to_frame(replay: dict, frame: int, point: dict | None) -> tuple[float, float] | None:
    if point is None:
        return None
    transforms = replay.get("release_to_frame")
    if transforms and str(frame) in transforms:
        m = np.asarray(transforms[str(frame)], float)
        x, y = m[:, :2] @ [point["x"], point["y"]] + m[:, 2]
        return float(x), float(y)
    return point["x"], point["y"]


def _crop(image, centre, label, marks):
    pad = cv2.copyMakeBorder(image, CROP, CROP, CROP, CROP, cv2.BORDER_CONSTANT)
    cx, cy = (int(centre[0]), int(centre[1])) if centre else (image.shape[1] // 2, image.shape[0] // 2)
    tile = pad[cy:cy + 2 * CROP, cx:cx + 2 * CROP].copy()
    for point, colour in marks:
        if point is not None:
            cv2.circle(tile, (int(point[0] - cx + CROP), int(point[1] - cy + CROP)), 9, colour, 2)
    cv2.putText(tile, label, (6, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    return tile


def sheet(analysis: Path, output: Path) -> Path | None:
    replay = json.loads((analysis / "replay.json").read_text())
    manifest = json.loads((analysis / "manifest.json").read_text())
    events = replay["events"]
    if "release" not in events:
        return None
    side = manifest["trial_context"]["throwing_side"]
    table = pd.read_csv(analysis / "keypoints.csv")
    wrist = table[table["landmark"] == f"{side}_wrist"].set_index("frame")[["filtered_x_px", "filtered_y_px"]]
    release = events["release"]["frame"]
    measured = {r["frame"]: r for r in replay["measured"]}
    strip = list(range(release - 3, release + 4))
    later = [(name, events[name]["frame"], events[name].get("position")) for name in ("apex", "first_contact", "final_rest")
             if name in events]
    images = _frames(manifest["trial_context"]["source_video"], set(strip) | {f for _, f, _ in later})
    row1 = []
    anchor = _to_frame(replay, release, events["release"].get("position"))
    for f in strip:
        if f not in images:
            continue
        bag = _to_frame(replay, f, measured.get(f))
        w = tuple(wrist.loc[f]) if f in wrist.index and np.isfinite(wrist.loc[f]).all() else None
        tag = "REL" if f == release else f"{f - release:+d}"
        row1.append(_crop(images[f], anchor or w, f"{f} {tag}", [(bag, (255, 0, 255)), (w, (255, 255, 0))]))
    row2 = []
    for name, f, position in later:
        if f in images:
            point = _to_frame(replay, f, position)
            row2.append(_crop(images[f], point, f"{name} {f}", [(point, (255, 0, 255))]))
    width = max(len(row1), len(row2))
    blank = np.zeros((2 * CROP, 2 * CROP, 3), np.uint8)
    grid = np.vstack([np.hstack(row + [blank] * (width - len(row))) for row in (row1, row2) if row])
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"{analysis.name}.jpg"
    cv2.imwrite(str(path), grid)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--throws", nargs="*", help="Analysis folder names (default: all)")
    args = parser.parse_args()
    folders = sorted(p.parent for p in Path(args.library).expanduser().glob("Athletes/*/analyses/*/replay.json"))
    for folder in folders:
        if args.throws and folder.name not in args.throws:
            continue
        print(sheet(folder, Path(args.output).expanduser()))


if __name__ == "__main__":
    main()
