import argparse
import json

import numpy as np
import pytest

from cornhole_biomech.board import order_corners
from cornhole_biomech.cli import handle_calibrate_session, handle_set_board_corners


def test_set_board_corners_orders_shuffled_clicks(tmp_path):
    trial_dir = tmp_path / "trial"
    trial_dir.mkdir()
    (trial_dir / "manifest.json").write_text(json.dumps(
        {"trial_context": {"target_direction": "left_to_right"}}))
    quad = [[700.0, 300.0], [1200.0, 300.0], [1500.0, 900.0], [420.0, 900.0]]
    shuffled = [quad[2], quad[0], quad[3], quad[1]]
    flat = ",".join(str(v) for pt in shuffled for v in pt)
    args = argparse.Namespace(trial_dir=str(trial_dir), corners=flat, apply_to=[])

    result = handle_set_board_corners(args)

    written = json.loads((trial_dir / "board_corners.json").read_text())
    expected = order_corners(np.asarray(shuffled, float), "left_to_right")
    assert np.allclose(written["corners_px"], expected)
    assert written["source"] == "clicked"
    assert result["written"] == str(trial_dir / "board_corners.json")
    assert result["applied"] == [] and result["failed"] == []


def test_set_board_corners_requires_an_analyzed_trial(tmp_path):
    trial_dir = tmp_path / "trial"
    trial_dir.mkdir()
    args = argparse.Namespace(trial_dir=str(trial_dir), corners="0,0,1,0,1,1,0,1", apply_to=[])
    with pytest.raises(ValueError):
        handle_set_board_corners(args)


def test_set_board_corners_rejects_wrong_corner_count(tmp_path):
    trial_dir = tmp_path / "trial"
    trial_dir.mkdir()
    (trial_dir / "manifest.json").write_text(json.dumps(
        {"trial_context": {"target_direction": "left_to_right"}}))
    args = argparse.Namespace(trial_dir=str(trial_dir), corners="0,0,1,0,1,1", apply_to=[])
    with pytest.raises(ValueError):
        handle_set_board_corners(args)


def _throw_dir(tmp_path, name, trial_id, hfov_deg, status):
    d = tmp_path / name
    d.mkdir()
    (d / "manifest.json").write_text(json.dumps({"trial_context": {"trial_id": trial_id}}))
    (d / "results.json").write_text(json.dumps(
        {"scale": {"per_throw_hfov_deg": hfov_deg, "per_throw_hfov_status": status}}))
    return d


def test_calibrate_session_pools_and_writes_camera_json_to_every_dir(tmp_path):
    dirs = [_throw_dir(tmp_path, f"throw{i}", f"trial-{i}", hfov, "measured")
            for i, hfov in enumerate([60.0, 61.0, 59.5])]
    args = argparse.Namespace(analyses=[str(d) for d in dirs], session_key=None)

    result = handle_calibrate_session(args)

    assert result["status"] == "measured"
    assert result["n"] == 3
    assert sorted(result["members"]) == ["trial-0", "trial-1", "trial-2"]
    for d in dirs:
        written = json.loads((d / "camera.json").read_text())
        assert written == result


def test_calibrate_session_uses_a_given_session_key(tmp_path):
    d = _throw_dir(tmp_path, "throw0", "trial-0", 60.0, "measured")
    args = argparse.Namespace(analyses=[str(d)], session_key="my-session")

    result = handle_calibrate_session(args)

    assert result["session_key"] == "my-session"
    assert json.loads((d / "camera.json").read_text())["session_key"] == "my-session"


def test_calibrate_session_defaults_key_deterministically_from_folder_paths(tmp_path):
    d = _throw_dir(tmp_path, "throw0", "trial-0", 60.0, "measured")
    args = argparse.Namespace(analyses=[str(d)], session_key=None)

    first = handle_calibrate_session(args)
    second = handle_calibrate_session(args)

    assert first["session_key"] == second["session_key"]
