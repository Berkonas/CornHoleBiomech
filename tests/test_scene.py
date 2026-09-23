import json
from pathlib import Path

import cv2
import numpy as np

from cornhole_biomech.auto_bag import Candidate
from cornhole_biomech.scene import person_masks, tag_people
from cornhole_biomech.video import file_sha256


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


# ---------------------------------------------------------------- fix round 1


def _write_script(path: Path, body: str) -> Path:
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(0o755)
    return path


def test_helper_nonzero_exit_is_unavailable_with_stderr(tmp_path):
    script = _write_script(tmp_path / "fake_sv.sh", 'echo "boom: bad input" >&2\nexit 1')
    out = person_masks("x.mov", tmp_path, (80, 60), binary=script)
    assert out["status"] == "unavailable"
    assert "boom" in out["reason"]
    assert out["masks"] == {}


def test_helper_timeout_is_unavailable(tmp_path):
    script = _write_script(tmp_path / "fake_sv.sh", "sleep 5")
    out = person_masks("x.mov", tmp_path, (80, 60), binary=script, timeout=1.0)
    assert out["status"] == "unavailable"
    assert "timed out" in out["reason"].lower()
    assert out["masks"] == {}
    # no partial cache directory left behind for a later call to wrongly trust
    assert not (tmp_path / "scene_vision" / "index.json").exists()


def test_corrupt_index_json_is_unavailable_not_an_exception(tmp_path):
    cache = tmp_path / "scene_vision"
    cache.mkdir()
    (cache / "index.json").write_text("{not valid json")
    out = person_masks("x.mov", tmp_path, (80, 60), binary=None)
    assert out["status"] == "unavailable"
    assert out["masks"] == {}


def test_cache_from_a_different_video_is_not_reused(tmp_path):
    video_a = tmp_path / "a.mov"; video_a.write_bytes(b"video A content, some bytes")
    video_b = tmp_path / "b.mov"; video_b.write_bytes(b"video B content, totally different")
    cache_root = tmp_path / "cache"; cache_root.mkdir()
    cache = _fake_cache(cache_root, 40, 30)
    index = json.loads((cache / "index.json").read_text())
    index["video_sha256"] = file_sha256(video_a)
    (cache / "index.json").write_text(json.dumps(index))

    out = person_masks(str(video_b), cache_root, (80, 60), binary=None)
    assert out["status"] == "unavailable"   # video B's masks are not video A's cached masks
    assert out["masks"] == {}


def test_person_masks_drops_near_empty_masks_and_counts_them(tmp_path):
    cache = tmp_path / "scene_vision"
    cache.mkdir()
    empty = np.zeros((30, 40), np.uint8)
    person = np.zeros((30, 40), np.uint8); person[10:20, 10:20] = 255
    cv2.imwrite(str(cache / "mask_000000.png"), empty)
    cv2.imwrite(str(cache / "mask_000002.png"), person)
    (cache / "index.json").write_text(json.dumps({"fps": 60, "width": 80, "height": 60, "mask_width": 40,
                                                   "mask_height": 30, "step": 2, "frames": [0, 2]}))
    out = person_masks("x.mov", tmp_path, (80, 60), binary=None)
    assert out["status"] == "measured"
    assert 0 not in out["masks"]
    assert 2 in out["masks"]
    assert out["empty_frames"] == 1


def test_tag_people_prefers_nearest_nonempty_mask_on_tie():
    empty = np.zeros((60, 80), np.uint8)
    person = np.zeros((60, 80), np.uint8); person[20:40, 20:40] = 255
    tagged = tag_people([Candidate(1, 30.0, 30.0, 5.0)], {0: empty, 2: person})
    assert tagged[0].in_person is True
