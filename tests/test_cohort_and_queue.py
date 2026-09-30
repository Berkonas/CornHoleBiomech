"""The summary pools the largest comparable group and says why throws are left out; analyses run one at a time."""
import json
import threading
import time

from cornhole_biomech.cli import analysis_slot, dashboard_base_trial
from cornhole_biomech.insights import incompatibility_reason


def write_trial(root, tid, created, method="m1", stale=False):
    d = root / f"a/{tid}"
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps({"method_version": method, "pose_backend": "sports2d"}))
    if stale:
        (d / "needs_reanalysis.json").write_text("{}")
    return {"id": tid, "createdAt": created, "analysisRelativePath": f"a/{tid}", "cameraView": "side",
            "throwingSide": "right"}


def test_base_trial_is_from_the_largest_comparable_group(tmp_path):
    trials = [write_trial(tmp_path, f"t{i}", f"2026-09-2{i}", "old") for i in range(5)]
    trials.append(write_trial(tmp_path, "new", "2026-09-29", "new"))   # one throw re-analyzed with a newer version
    assert dashboard_base_trial(tmp_path, trials)["id"] == "t4"


def test_ties_go_to_the_newest_and_stale_throws_do_not_count(tmp_path):
    trials = [write_trial(tmp_path, "a", "2026-09-20"), write_trial(tmp_path, "b", "2026-09-21"),
              write_trial(tmp_path, "c", "2026-09-22", stale=True)]
    assert dashboard_base_trial(tmp_path, trials)["id"] == "b"


def test_incompatibility_reason_names_the_app_version():
    trial = {"cameraView": "side", "throwingSide": "right"}
    reason = incompatibility_reason(trial, {"method_version": "a"}, dict(trial), {"method_version": "b"})
    assert "re-analyze" in reason
    assert incompatibility_reason({**trial, "cameraView": "front"}, {}, trial, {}) == "different camera view"


def test_analysis_slot_runs_one_analysis_at_a_time(tmp_path, monkeypatch):
    monkeypatch.setenv("CORNHOLE_ANALYSIS_LOCK", str(tmp_path / "lock"))
    events, messages = [], []

    def work(name):
        with analysis_slot(lambda stage, fraction, message: messages.append(stage)):
            events.append(("start", name))
            time.sleep(0.3)
            events.append(("end", name))

    first = threading.Thread(target=work, args=("a",))
    first.start()
    time.sleep(0.05)
    second = threading.Thread(target=work, args=("b",))
    second.start()
    first.join(); second.join()
    assert [e[0] for e in events] == ["start", "end", "start", "end"]
    assert "queued" in messages
