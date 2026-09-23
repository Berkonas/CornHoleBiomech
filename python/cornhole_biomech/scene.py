# python/cornhole_biomech/scene.py
"""Person masks from the `scene-vision` helper (Apple Vision), cached per trial.

Masks only ever REMOVE evidence (people cannot seed a bag flight, and are left out
of the background plate). If the helper is missing or its output does not match
the video, tracking runs exactly as before and the reason is recorded.
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .auto_bag import Candidate

SCENE_REVISION = "scene_vision_v1"
_REPO = Path(__file__).resolve().parents[2]
_DEFAULT = object()


def find_binary() -> Path | None:
    env = os.environ.get("CORNHOLE_SCENE_VISION")
    candidates = [Path(env)] if env else []
    candidates += [_REPO / "app/CornholeBiomechanics/.build/release/SceneVision",
                   _REPO / "app/CornholeBiomechanics/.build/debug/SceneVision"]
    return next((p for p in candidates if p.is_file() and os.access(p, os.X_OK)), None)


def person_masks(video_path: str, cache_dir: Path, frame_size: tuple[int, int], binary: Any = _DEFAULT) -> dict[str, Any]:
    cache = Path(cache_dir) / "scene_vision"
    index_path = cache / "index.json"
    if not index_path.exists():
        exe = find_binary() if binary is _DEFAULT else binary
        if exe is None:
            return {"status": "unavailable", "reason": "scene-vision helper not found; person masks skipped.",
                    "masks": {}, "step": None}
        done = subprocess.run([str(exe), "--input", str(video_path), "--output", str(cache)],
                              capture_output=True, text=True, timeout=900)
        if done.returncode != 0 or not index_path.exists():
            return {"status": "unavailable", "reason": f"scene-vision failed: {done.stderr.strip()[:300]}",
                    "masks": {}, "step": None}
    index = json.loads(index_path.read_text())
    width, height = frame_size
    if abs(index["mask_width"] / index["mask_height"] - width / height) > 0.01:
        return {"status": "unavailable", "masks": {}, "step": index.get("step"),
                "reason": f"Mask size {index['mask_width']}×{index['mask_height']} does not match the video "
                          f"{width}×{height} (orientation?); person masks skipped."}
    masks = {}
    for f in index["frames"]:
        m = cv2.imread(str(cache / f"mask_{f:06d}.png"), cv2.IMREAD_GRAYSCALE)
        if m is not None:
            masks[int(f)] = (cv2.resize(m, (width, height), interpolation=cv2.INTER_NEAREST) >= 128).astype(np.uint8) * 255
    return {"status": "measured", "reason": None, "masks": masks, "step": index["step"], "revision": SCENE_REVISION}


def tag_people(candidates: list[Candidate], masks: dict[int, np.ndarray]) -> list[Candidate]:
    if not masks:
        return list(candidates)
    keys = sorted(masks)
    out = []
    for c in candidates:
        nearest = min(keys, key=lambda k: abs(k - c.frame))
        m = masks[nearest]
        x, y = int(round(c.x)), int(round(c.y))
        inside = abs(nearest - c.frame) <= 2 and 0 <= y < m.shape[0] and 0 <= x < m.shape[1] and m[y, x] > 0
        out.append(replace(c, in_person=bool(inside)))
    return out
