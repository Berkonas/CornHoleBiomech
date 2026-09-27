"""Coaching gate: a real driver becomes a priority; noise, unreliable or unmodifiable variables do not."""
import numpy as np
import pytest

from cornhole_biomech.coaching import (
    athlete_dashboard,
    coaching_priorities,
    evidence_chain,
    release_compensation,
    release_profile,
)
from cornhole_biomech.performance import performance_summary
from cornhole_biomech.zones import ZoneSettings


def athlete(driver_effect=6.0, n=40, seed=3):
    """Release angle drives scoring (misses 6° higher); speed is pure noise."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        scored = i % 2 == 0
        rows.append({"trial_id": f"T{i}", "score_category": (3 if i % 4 == 0 else 1) if scored else 0,
                     "bag_release_angle_deg": 40 + rng.normal(0, 1.5) + (0 if scored else driver_effect),
                     "bag_release_speed_m_s": 7.5 + rng.normal(0, 0.1),
                     "bag_release_height_m": 0.9 + rng.normal(0, 0.01),
                     "bag_release_angle_se_deg": 0.5})
    return rows


def test_true_driver_becomes_priority_and_noise_does_not():
    rows = athlete()
    summary = performance_summary(rows, {})
    gate = coaching_priorities(rows, summary, {}, {})
    keys = [p["key"] for p in gate["priorities"]]
    assert keys == ["bag_release_angle_deg"]
    p = gate["priorities"][0]
    assert all(p["checks"].values())
    assert p["ci_95"][0] > 0                       # misses higher, CI excludes 0
    assert p["example_throws"]
    assert "bag_release_speed_m_s" not in keys


def test_unreliable_measurement_is_only_an_observed_difference():
    rows = athlete()
    summary = performance_summary(rows, {})
    gate = coaching_priorities(rows, summary, {}, {"bag_release_angle_deg": 0.5})
    assert gate["priorities"] == []
    observed = gate["observed_differences"][0]
    assert observed["key"] == "bag_release_angle_deg"
    assert "measured reliably" in observed["why_not_a_priority"]


def test_small_or_absent_effect_gives_no_priority():
    rows = athlete(driver_effect=0.0)
    gate = coaching_priorities(rows, performance_summary(rows, {}), {}, {})
    assert gate["priorities"] == []


def test_profile_consistency_against_noise():
    rows = athlete()
    profile = {p["key"]: p for p in release_profile(rows)}
    assert profile["bag_release_speed_m_s"]["consistency"] == "within measurement noise"
    assert profile["bag_release_angle_deg"]["consistency"] in ("moderate", "variable")
    assert profile["bag_release_speed_m_s"]["cv_percent"] == pytest.approx(
        100 * np.std([r["bag_release_speed_m_s"] for r in rows], ddof=1) / np.mean([r["bag_release_speed_m_s"] for r in rows]))


def test_compensation_detects_covarying_speed_and_angle():
    rng = np.random.default_rng(5)
    rows = []
    for i in range(20):
        angle = 40 + rng.normal(0, 4)
        # Speed chosen to keep the drag-free range constant: errors cancel.
        from cornhole_biomech.zones import speed_to_hole
        speed = speed_to_hole(angle, 0.9, ZoneSettings()) or 7.0
        rows.append({"trial_id": f"T{i}", "bag_release_speed_m_s": speed, "bag_release_angle_deg": angle,
                     "bag_release_height_m": 0.9})
    out = release_compensation(rows, ZoneSettings(), permutations=100)
    assert out["status"] == "estimated" and out["ratio"] > 2
    assert "compensate" in out["message"]


def test_evidence_chain_and_dashboard_without_outcomes():
    rows = [{"trial_id": f"T{i}", "score_category": None, "wrist_speed_at_release_arm_lengths_s": 8 + 0.1 * i,
             "bag_release_speed_m_s": 6 + 0.05 * i} for i in range(12)]
    chain = evidence_chain(rows)
    link = next(c for c in chain if c["from"] == "wrist_speed_at_release_arm_lengths_s")
    assert link["supported"] and link["rho"] == pytest.approx(1.0)
    dash = athlete_dashboard(rows, performance_summary(rows, {}), {"bags": 0}, {}, {"status": "needs_scale"},
                             ZoneSettings(), {}, [{"pose": "GOOD", "bag": "POOR", "calibration": "WARNING",
                                                   "release": "GOOD"}], [])
    assert dash["priorities"] == [] and "Record hole" in dash["headline"]
    assert dash["trust"]["overall"]["bag"] == "POOR"


def test_compensation_message_names_chance_when_tighter_but_not_significant():
    rng = np.random.default_rng(0)
    rows = []
    for i in range(8):
        from cornhole_biomech.zones import speed_to_hole
        angle = 40 + rng.normal(0, 4)
        speed = (speed_to_hole(angle, 0.9, ZoneSettings()) or 7.0) + rng.normal(0, 0.35)
        rows.append({"trial_id": f"T{i}", "bag_release_speed_m_s": speed, "bag_release_angle_deg": angle,
                     "bag_release_height_m": 0.9})
    out = release_compensation(rows, ZoneSettings(), permutations=200)
    assert out["ratio"] > 1.1 and out["chance_as_tight"] >= 0.05
    # Not "spread close to random pairing": the spreads differ, chance just cannot be ruled out.
    assert "close to random" not in out["message"] and "rule out chance" in out["message"]
