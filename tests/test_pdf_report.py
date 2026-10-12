"""Printable athlete report (pdf_report.py): built from saved outputs only, missing values never crash it."""
import json
import re
from pathlib import Path

import pytest

from cornhole_biomech.cli import main
from cornhole_biomech.pdf_report import _miss_rows, athlete_report_pdf, collect

ATHLETE = "11111111-2222-3333-4444-555555555555"
SESSION = "99999999-8888-7777-6666-555555555555"
REAL_LIBRARY = Path(__file__).resolve().parents[1] / "data" / "libraries" / "Cornhole Biomechanics Lab Data"


def _page_count(path: Path) -> int:
    return len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", path.read_bytes()))


def _metric(value, unit="m/s", status="reliable"):
    return {"value": value, "unit": unit, "status": status, "label": "x", "reasons": []}


def _trial(root: Path, number: int, score, *, two_view: dict | None, speed, angle, height, scale="measured"):
    trial_id = f"0000000{number}-0000-0000-0000-000000000000"
    rel = f"Athletes/Player-9-11111111/analyses/Throw-{number}"
    d = root / rel
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps({
        "method_version": "test-method", "pose_backend": "sports2d", "pose_model": "body_with_feet-balanced",
        "pose_model_version": "0.8.34", "pose_model_sha256": "abc", "analysis_configuration": {"x": 1},
        "python_package_version": "0.6.2"}))
    coach = {"bag_release_speed_m_s": _metric(speed), "bag_release_angle_deg": _metric(angle, "°"),
             "bag_release_height_m": _metric(height, "m"),
             "swing_tempo_ratio": _metric(None if speed is None else 1.8, "back ÷ forward", "not_measured")}
    (d / "results.json").write_text(json.dumps({
        "trial_id": trial_id, "athlete_id": ATHLETE, "quality": {"usable_frame_percentage": 95.0},
        "scale": {"status": scale}, "chain": {},
        "summaries": {"bag_release_speed_m_s": speed, "bag_release_angle_deg": angle, "bag_release_height_m": height,
                      "bag_release_angle_se_deg": 0.3, "board_slide_in": 12.0 if two_view else None},
        "coach_metrics": coach}))
    if two_view is not None:
        (d / "two_view.json").write_text(json.dumps(two_view))
    outcome = None if score is None else {"score_category": score, "intended_target": "Hole center",
                                          "throw_type": "Standard", "notes": ""}
    return {"id": trial_id, "athleteID": ATHLETE, "createdAt": f"2026-10-0{number}T10:00:00Z",
            "recordingDate": f"2026-10-0{number}", "cameraView": "side", "throwingSide": "right",
            "targetDirection": "left_to_right", "sessionID": SESSION, "name": f"Take 1 · Throw {number}",
            "originalFilename": f"throw_{number}.mov", "analysisRelativePath": rel, "analysisStatus": "Analyzed",
            "takeNumber": 1, "throwInTake": number, "outcome": outcome}


def _library(tmp_path: Path) -> Path:
    root = tmp_path / "Library"
    root.mkdir()
    with_attribution = {
        "status": "measured", "method_version": "two_view_v7_front_contact",
        "landing": {"contact": {"x_in": 14.0, "y_in": 20.0}, "rest": {"x_in": 18.0, "y_in": 47.0, "on": "board"}},
        "miss": {"status": "measured", "short_long_in": 8.0, "left_right_in": 6.0},
        "result": {"category": "onBoard"},
        "heading": {"deg": 0.8, "status": "measured"},
        "frontal": {"trunk_side_lean_deg": {"value": 9.0, "status": "measured"},
                    "release_point_offset_m": {"value": None, "status": "unavailable"}},
        "explanation": {"sentence": "On the board: 8 in long, 6 in right.", "kind": "miss"},
        "attribution": {
            "lateral": {"components": [{"key": "aim", "label": "Aim (launch direction)", "named": True,
                                        "share": 0.7}]},
            "depth": {"components": [{"key": "carry", "label": "Carry (where it landed)", "named": False}]},
            "drivers": [],
            "explanation": {"observed": "On the board, 8 in long and 6 in right.", "phase": "flight",
                            "evidence": ["Aim: 4 in right of usual (2× its noise)."],
                            "possible_explanation": "The bag left the hand on a line 0.6° right of the usual one.",
                            "suggestion": "Review release alignment in the front view."}}}
    older = {"status": "measured", "method_version": "two_view_v5_knocked_confirm",
             "landing": {"contact": {"x_in": None, "y_in": 10.0}, "rest": None},
             "miss": {"status": "unavailable"}, "result": {"category": "offBoard"},
             "explanation": {"sentence": "Off the board; where it stopped was out of the front camera's view."}}
    trials = [
        _trial(root, 1, 1, two_view=with_attribution, speed=7.4, angle=38.0, height=0.98),
        _trial(root, 2, 0, two_view=older, speed=7.9, angle=None, height=1.02, scale="estimated"),
        _trial(root, 3, None, two_view=None, speed=None, angle=None, height=None),   # side only, nothing measured
    ]
    project = {"schemaVersion": 4, "athletes": [{"id": ATHLETE, "participantCode": "Player 9"}],
               "trials": trials, "sessions": [], "referenceSets": [], "analysisSettings": {}}
    (root / "project.json").write_text(json.dumps(project))
    return root


def test_synthetic_library_gives_a_six_page_pdf(tmp_path):
    root = _library(tmp_path)
    out = tmp_path / "reports" / "Player-9.pdf"
    result = athlete_report_pdf(root, ATHLETE, out)
    assert out.exists() and out.read_bytes().startswith(b"%PDF")
    # cover, board, release, consistency, one miss-table page, scored vs missed + limitations
    assert result["pages"] == 6 and _page_count(out) == 6
    assert result["throws"] == 3
    assert not out.with_name(out.name + ".partial").exists()


def test_missing_values_stay_missing(tmp_path):
    data = collect(_library(tmp_path), ATHLETE)
    by_number = {th["number"]: th for th in data["throws"]}
    assert by_number[3]["landing"]["rest"] is None and by_number[3]["row"]["bag_release_speed_m_s"] is None
    assert by_number[2]["state"]["bag_release_speed_m_s"] == "estimated"
    assert data["performance"]["counts"] == {"hole": 0, "board": 1, "miss": 1, "unknown": 1}
    rows = {r["number"]: r for r in _miss_rows(data)}
    assert rows[1]["phase"] == "flight"
    assert any("Review release alignment" in body for _, body in rows[1]["lines"])
    assert rows[2]["short_long"] is None and rows[2]["left_right"] is None       # unavailable, not 0
    assert "No front camera" in rows[3]["lines"][0][1]
    assert set(data["two_view_versions"]) == {"two_view_v7_front_contact", "two_view_v5_knocked_confirm"}


def test_cli_prints_one_json_result_line(tmp_path, capsys):
    root = _library(tmp_path)
    out = tmp_path / "r.pdf"
    assert main(["athlete-report-pdf", "--library", str(root), "--athlete-id", ATHLETE, "--output", str(out)]) == 0
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["type"] == "result" and line["data"]["output"] == str(out.resolve()) and out.exists()


def test_unknown_athlete_is_an_error_line(tmp_path, capsys):
    root = _library(tmp_path)
    assert main(["athlete-report-pdf", "--library", str(root), "--athlete-id", "nobody",
                 "--output", str(tmp_path / "x.pdf")]) == 1
    assert json.loads(capsys.readouterr().out.strip())["type"] == "error"


@pytest.mark.skipif(not (REAL_LIBRARY / "project.json").exists(), reason="cached athlete library not present")
def test_real_library_report(tmp_path):
    project = json.loads((REAL_LIBRARY / "project.json").read_text())
    analysed = {t["athleteID"] for t in project["trials"] if t.get("analysisRelativePath")}
    athlete = next(a["id"] for a in project["athletes"] if a["id"] in analysed)
    out = tmp_path / "real.pdf"
    result = athlete_report_pdf(REAL_LIBRARY, athlete, out)
    assert result["pages"] >= 6 and _page_count(out) == result["pages"]
