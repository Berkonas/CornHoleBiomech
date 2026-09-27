# python/cornhole_biomech/scene.py
"""Person masks from the `scene-vision` helper (Apple Vision), cached per trial.

Masks only ever REMOVE evidence (people cannot seed a bag flight, and are left out
of the background plate). If the helper is missing, times out, its output does not
match the video, or the cache belongs to a different video, tracking runs exactly
as before and the reason is recorded -- this module never raises out of
`person_masks`.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .auto_bag import Candidate
from .video import file_sha256

SCENE_REVISION = "scene_vision_v1"
_REPO = Path(__file__).resolve().parents[2]
_DEFAULT = object()

DEFAULT_HELPER_TIMEOUT_SECONDS = 900.0
# A mask with fewer person pixels than this fraction of the frame is treated as a
# missed detection rather than "no one is here": VNGeneratePersonSegmentationRequest
# occasionally returns a near-empty, low-confidence mask instead of no result at all
# (observed on ~40% of frames of the P1 pilot clip), and letting that win the
# nearest-mask lookup in tag_people would wrongly clear a real in-person candidate.
MIN_PERSON_PIXEL_FRACTION = 0.0005


def find_binary() -> Path | None:
    env = os.environ.get("CORNHOLE_SCENE_VISION")
    candidates = [Path(env)] if env else []
    candidates += [_REPO / "app/CornholeBiomechanics/.build/release/SceneVision",
                   _REPO / "app/CornholeBiomechanics/.build/debug/SceneVision"]
    return next((p for p in candidates if p.is_file() and os.access(p, os.X_OK)), None)


def _video_identity(video_path: str) -> str | None:
    """The source video's content hash, or None if it cannot be read (never raises)."""
    try:
        return file_sha256(video_path)
    except OSError:
        return None


def _stamp_identity(index_path: Path, identity: str) -> bool:
    """Record the source video's identity in an on-disk index.json. Returns False
    (never raises) if the file cannot be read back or rewritten."""
    try:
        index = json.loads(index_path.read_text())
        index["video_sha256"] = identity
        index_path.write_text(json.dumps(index))
        return True
    except (json.JSONDecodeError, OSError, KeyError):
        return False


def _regenerate(video_path: str, cache: Path, timeout: float, binary: Any) -> dict[str, Any] | None:
    """(Re)build `cache` from scratch by running the helper. Returns an 'unavailable'
    result dict on any failure (missing binary, non-zero exit, timeout, OS error, or
    an unwritable/corrupt result), always leaving `cache` removed rather than
    partially written; returns None on success, with `cache` populated and stamped
    with the source video's identity."""
    shutil.rmtree(cache, ignore_errors=True)
    exe = find_binary() if binary is _DEFAULT else binary
    if exe is None:
        return {"status": "unavailable", "reason": "scene-vision helper not found; person masks skipped.",
                "masks": {}, "step": None}
    try:
        done = subprocess.run([str(exe), "--input", str(video_path), "--output", str(cache)],
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        shutil.rmtree(cache, ignore_errors=True)
        return {"status": "unavailable",
                "reason": f"scene-vision timed out after {timeout:.0f}s; person masks skipped.",
                "masks": {}, "step": None}
    except OSError as exc:
        shutil.rmtree(cache, ignore_errors=True)
        return {"status": "unavailable", "reason": f"scene-vision could not be run ({exc}); person masks skipped.",
                "masks": {}, "step": None}
    index_path = cache / "index.json"
    if done.returncode != 0 or not index_path.exists():
        shutil.rmtree(cache, ignore_errors=True)
        return {"status": "unavailable", "reason": f"scene-vision failed: {done.stderr.strip()[:300]}",
                "masks": {}, "step": None}
    identity = _video_identity(video_path)
    if identity is not None and not _stamp_identity(index_path, identity):
        shutil.rmtree(cache, ignore_errors=True)
        return {"status": "unavailable",
                "reason": "scene-vision wrote an unreadable index.json; person masks skipped.",
                "masks": {}, "step": None}
    return None


def person_masks(video_path: str, cache_dir: Path, frame_size: tuple[int, int], binary: Any = _DEFAULT,
                  timeout: float = DEFAULT_HELPER_TIMEOUT_SECONDS) -> dict[str, Any]:
    cache = Path(cache_dir) / "scene_vision"
    index_path = cache / "index.json"

    index: dict[str, Any] | None = None
    if index_path.exists():
        try:
            index = json.loads(index_path.read_text())
        except (json.JSONDecodeError, OSError):
            index = None
        else:
            recorded = index.get("video_sha256")
            if recorded is not None:
                identity = _video_identity(video_path)
                if identity is not None and identity != recorded:
                    index = None   # a different video is reusing this cache directory

    if index is None:
        failure = _regenerate(video_path, cache, timeout, binary)
        if failure is not None:
            return failure
        try:
            index = json.loads(index_path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            shutil.rmtree(cache, ignore_errors=True)
            return {"status": "unavailable",
                    "reason": f"scene-vision cache is corrupt ({exc}); person masks skipped.",
                    "masks": {}, "step": None}

    try:
        mask_width, mask_height, step, frames = (index["mask_width"], index["mask_height"],
                                                  index["step"], index["frames"])
    except KeyError as exc:
        shutil.rmtree(cache, ignore_errors=True)
        return {"status": "unavailable",
                "reason": f"scene-vision cache is missing {exc}; person masks skipped.",
                "masks": {}, "step": None}

    width, height = frame_size
    try:
        sizes_ok = min(float(mask_width), float(mask_height), float(width), float(height)) > 0
    except (TypeError, ValueError):
        sizes_ok = False
    if not sizes_ok:
        shutil.rmtree(cache, ignore_errors=True)
        return {"status": "unavailable", "masks": {}, "step": step,
                "reason": f"scene-vision cache has an invalid mask size {mask_width}×{mask_height} "
                          f"(video {width}×{height}); person masks skipped."}
    if abs(mask_width / mask_height - width / height) > 0.01:
        return {"status": "unavailable", "masks": {}, "step": step,
                "reason": f"Mask size {mask_width}×{mask_height} does not match the video "
                          f"{width}×{height} (orientation?); person masks skipped."}

    masks: dict[int, np.ndarray] = {}
    empty_frames = 0
    min_pixels = MIN_PERSON_PIXEL_FRACTION * width * height
    for f in frames:
        m = cv2.imread(str(cache / f"mask_{f:06d}.png"), cv2.IMREAD_GRAYSCALE)
        if m is None:
            continue
        resized = (cv2.resize(m, (width, height), interpolation=cv2.INTER_NEAREST) >= 128).astype(np.uint8) * 255
        if int(np.count_nonzero(resized)) < min_pixels:
            empty_frames += 1
            continue
        masks[int(f)] = resized
    return {"status": "measured", "reason": None, "masks": masks, "step": step, "revision": SCENE_REVISION,
            "empty_frames": empty_frames}


def _mask_is_empty(mask: np.ndarray) -> bool:
    return not np.any(mask)


def tag_people(candidates: list[Candidate], masks: dict[int, np.ndarray]) -> list[Candidate]:
    if not masks:
        return list(candidates)
    keys = sorted(masks)
    out = []
    for c in candidates:
        # Break nearest-frame ties toward a non-empty mask: an empty mask at an
        # equal distance is a dropout, not a "no person here" reading, and should
        # not out-vote a real detection the same number of frames away.
        nearest = min(keys, key=lambda k: (abs(k - c.frame), _mask_is_empty(masks[k])))
        m = masks[nearest]
        x, y = int(round(c.x)), int(round(c.y))
        inside = abs(nearest - c.frame) <= 2 and 0 <= y < m.shape[0] and 0 <= x < m.shape[1] and m[y, x] > 0
        out.append(replace(c, in_person=bool(inside)))
    return out


def tag_bystanders(candidates: list[Candidate], boxes: dict[int, list[list[float]]] | None) -> list[Candidate]:
    """Mark candidates inside a pose-tracked bystander's box (same frame) as in a person.

    Complements the Vision masks, which miss small background people: like a masked
    candidate, a tagged one cannot seed a flight but can still extend one (the bag
    may fly in front of a bystander).
    """
    if not boxes:
        return list(candidates)
    return [replace(c, in_person=True) if any(x0 <= c.x <= x1 and y0 <= c.y <= y1
                                              for x0, y0, x1, y1 in boxes.get(c.frame, ()))
            else c for c in candidates]
