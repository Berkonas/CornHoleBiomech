"""Fast regression version of scripts/stress_test.py."""
import numpy as np

from cornhole_biomech import stress
from cornhole_biomech.performance import performance_summary
from cornhole_biomech.zones import ZoneSettings, zone_report


def claim_rate(athlete, n, reps=40, seed=3):
    rng = np.random.default_rng(seed)
    hits = 0
    for _ in range(reps):
        s = performance_summary(stress.simulate_session(athlete, n, rng), {})
        hits += any(v["distinguishes"] or v["spread_distinguishes"] for v in s["variables"].values())
    return hits / reps


def test_null_and_pro_athletes_rarely_get_false_claims():
    null, pro = stress.SCENARIOS[3], stress.SCENARIOS[2]
    assert claim_rate(null, 20) <= 0.10
    assert claim_rate(pro, 20) <= 0.10


def test_speed_driven_misses_are_detected_with_forty_throws():
    assert claim_rate(stress.SCENARIOS[0], 40) >= 0.7


def test_physics_priority_names_the_true_cause_with_ten_throws():
    rng = np.random.default_rng(5)
    for athlete, truth in ((stress.SCENARIOS[0], "speed"), (stress.SCENARIOS[1], "angle")):
        tops = [zone_report(stress.simulate_session(athlete, 10, rng), ZoneSettings())["priority"]["variable"] for _ in range(20)]
        assert tops.count(truth) / len(tops) >= 0.8
