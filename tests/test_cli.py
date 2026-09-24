import argparse
import json

import numpy as np
import pytest

from cornhole_biomech.board import order_corners
from cornhole_biomech.cli import handle_set_board_corners


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
