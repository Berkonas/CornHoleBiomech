import json
from pathlib import Path

import cv2
import numpy as np

from cornhole_biomech.auto_bag import Candidate
from cornhole_biomech.scene import person_masks, tag_people


def test_missing_binary_is_unavailable(tmp_path):
    out = person_masks("x.mov", tmp_path, (1920, 1080), binary=None)
    assert out["status"] == "unavailable" and "scene-vision" in out["reason"]
    assert out["masks"] == {}


def _fake_cache(tmp_path: Path, w, h):
    cache = tmp_path / "scene_vision"
    cache.mkdir()
    m = np.zeros((h, w), np.uint8); m[10:20, 10:20] = 255
    cv2.imwrite(str(cache / "mask_000000.png"), m)
    (cache / "index.json").write_text(json.dumps({"fps": 60, "width": 2 * w, "height": 2 * h, "mask_width": w,
                                                   "mask_height": h, "step": 2, "frames": [0]}))
    return cache


def test_cached_masks_are_loaded_at_full_resolution(tmp_path):
    _fake_cache(tmp_path, 40, 30)
    out = person_masks("x.mov", tmp_path, (80, 60), binary=None)
    assert out["status"] == "measured"
    assert out["masks"][0].shape == (60, 80) and out["masks"][0][30, 30] == 255


def test_mask_size_mismatch_is_rejected(tmp_path):
    _fake_cache(tmp_path, 40, 30)
    out = person_masks("x.mov", tmp_path, (1080, 1920), binary=None)   # rotated video
    assert out["status"] == "unavailable" and "size" in out["reason"]


def test_tag_people_marks_candidates_inside_masks():
    m = np.zeros((60, 80), np.uint8); m[20:40, 20:40] = 255
    tagged = tag_people([Candidate(0, 30.0, 30.0, 5.0), Candidate(0, 70.0, 5.0, 5.0), Candidate(1, 30.0, 30.0, 5.0)],
                        {0: m})
    assert [c.in_person for c in tagged] == [True, False, True]   # frame 1 uses nearest mask (frame 0)
