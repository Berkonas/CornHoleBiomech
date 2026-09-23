"""Bag-tracking validation metrics: phase selection, errors, lost-track counts, events, pooling."""
import json

import numpy as np
import pytest

from cornhole_biomech.bag_validation import (
    bag_benchmark,
    bag_phase_frames,
    pooled,
    select_bag_frames,
    tracker_report,
)


def test_phase_frames_cover_flight_and_selection_is_deterministic():
    phases = bag_phase_frames(release=100, contact=160, last_tracked=160, apex=128, fps=60, frame_count=400)
    assert phases["release"] == [99, 100, 101]
    assert all(f < 100 for f in phases["in_hand"])
    assert all(f >= 160 for f in phases["landing"])
    assert 128 in phases["apex"]
    a, b = select_bag_frames(phases, 2), select_bag_frames(phases, 2)
    forced = select_bag_frames(phases, 1, always={100: "release", 160: "landing"})
    assert {100, 160} <= {r["frame"] for r in forced}
    assert a == b and {r["phase"] for r in a} == set(phases)
    assert len({r["frame"] for r in a}) == len(a)


def test_tracker_report_errors_success_and_lost_track():
    reference = {10: (100.0, 100.0), 11: (110.0, 100.0), 12: (120.0, 100.0), 13: (130.0, 100.0)}
    track = {10: (103.0, 104.0), 11: (110.0, 100.0), 12: None, 13: (160.0, 100.0), 14: (140.0, 100.0)}
    phase_of = {10: "release", 11: "release", 13: "apex"}
    out = tracker_report(reference, {15}, phase_of, track, (10, 16), success_radius_px=10.0, pixels_per_meter=200.0)
    assert out["n_compared"] == 3 and out["n_no_estimate"] == 1
    assert out["mae_px"] == pytest.approx((5 + 0 + 30) / 3)
    assert out["rmse_px"] == pytest.approx(np.sqrt((25 + 0 + 900) / 3))
    assert out["success_rate"] == pytest.approx(2 / 4)       # a missing estimate is a failure
    assert out["success_rate_in_flight"] == pytest.approx(2 / 4)
    assert out["lost_track_events"] == 2 and out["longest_missing_frames"] == 2   # frame 12; frames 15–16
    assert out["by_phase"]["apex"]["mae_px"] == pytest.approx(30.0)
    assert out["mae_cm_flight_plane"] == pytest.approx(100 * out["mae_px"] / 200.0)


def test_bag_benchmark_reads_analysis_and_annotation(tmp_path):
    analysis = tmp_path / "analysis"; analysis.mkdir()
    points = [{"frame": f, "x": 100.0 + 10 * (f - 50), "y": 300.0, "detection_x": 100.0 + 10 * (f - 50),
               "detection_y": 294.0, "source": "mask", "area_px": 314.0} for f in range(50, 80)]
    (analysis / "auto_flight.json").write_text(json.dumps({
        "points": points, "release_frame": 50, "first_contact_frame": 79, "last_tracked_frame": 79,
        "fps": 60.0, "runtime_seconds": 2.0, "frames_processed": 400}))
    marks = [{"frame_index": f, "landmark": "bag", "x": 100.0 + 10 * (f - 50), "y": 300.0, "visible": True}
             for f in (50, 60, 79)] + [{"frame_index": 45, "landmark": "bag", "visible": False}]
    annotation = tmp_path / "annotation_AB.json"
    annotation.write_text(json.dumps({"rater": "AB", "annotations": marks,
                                      "events": {"release": 51, "first_contact": 79}}))
    report = bag_benchmark(annotation, analysis)
    assert report["success_radius_px"] == pytest.approx(10.0, rel=1e-3)   # √(314/π)
    assert report["trackers"]["mask"]["mae_px"] == pytest.approx(0.0)
    assert report["trackers"]["detection"]["mae_px"] == pytest.approx(6.0)
    assert report["events"]["release"]["signed_frames"] == -1
    assert report["landing_position_error_px"]["detection"] == pytest.approx(6.0)
    assert report["processing_fps"] == pytest.approx(200.0)
    pool = pooled([report, report])
    assert pool["detection"]["n_compared"] == 6 and pool["detection"]["mae_px"] == pytest.approx(6.0)
