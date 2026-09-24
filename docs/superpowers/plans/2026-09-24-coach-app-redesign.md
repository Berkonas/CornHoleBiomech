# Coach App Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the eight-section research UI with a three-column coach app (athletes → throws → Throw report / Athlete summary) plus a rebuilt Launch Lab, driven by a tested per-throw verdict from the Python engine.

**Architecture:** SwiftUI `NavigationSplitView` with three columns; detail views are built from one shared design-system file (cards, metric tiles, range bars). The Python `insights` step gains a `verdict` block (drag-free physics check + within-athlete comparison) that the Throw report displays verbatim. Launch Lab reuses the Swift `LaunchModel` and adds a zone classifier that mirrors `zones.py`.

**Tech Stack:** Swift 6.2 tools (Swift 5 language mode), SwiftUI + Swift Charts, macOS 15; Python 3 engine (`python/cornhole_biomech`), pytest.

**Spec:** `docs/superpowers/specs/2026-09-24-coach-app-redesign-design.md`

## Global Constraints

- macOS 15 minimum; no new Swift packages or Python dependencies.
- Old libraries must still decode: keep every Codable field in `Models.swift` (references, sessions) even where UI is removed.
- No composite or "overall" scores. A value that failed reliability shows "—" plus its reason.
- Data colours: `scoredInk` (blue) scored, `missInk` (orange) miss, grey no result, `measuredInk` bag path, `athleteInk` athlete, model dashed secondary. Status colours always paired with an SF Symbol.
- Spacing scale 4/8/12/16/24/32; card padding 16; card corner radius 12; page margin 24; page max width 1120.
- Every chart: axis titles with units; time axes are "Time from release (ms)".
- Coach-facing copy is plain English; equations and statistics live in the Scientific/Research details disclosures.
- Python tests: `MPLCONFIGDIR=$TMPDIR/mpl PYTHONPATH=python .venv/bin/python -m pytest tests -q`.
- Swift build/tests: `./verify.sh` or `cd app/CornholeBiomechanics && DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer swift test --disable-sandbox` with `CLANG_MODULE_CACHE_PATH`/`SWIFTPM_MODULECACHE_OVERRIDE` pointed at a temp dir.
- Commit after each task with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. A throw with no scale (release speed/height unreliable or missing) — verdict must fall back to personal comparison, never print physics numbers (Task 1 test `test_no_scale_skips_physics`).
2. An athlete with fewer than 5 other throws — no personal "unusual" flags, headline says more throws are needed (Task 1 test `test_few_throws_no_personal_flags`).
3. A throw whose analysis is stale (`needs_reanalysis`) or still running — Throw report shows the re-analyze banner / progress instead of numbers (Task 4 manual check + VisualQA).
4. A library with zero athletes or an athlete with zero throws — every column shows an empty state with the one action that unblocks it (Task 2).
5. A release speed outside every hole solution (e.g. 2 m/s) — `speed_to_hole` returns None; verdict must say "no speed reaches the hole at this angle" rather than crash (Task 1 test `test_unreachable_hole`).

---

### Task 1: Python per-throw verdict

**Files:**
- Create: `python/cornhole_biomech/verdict.py`
- Modify: `python/cornhole_biomech/insights.py` (inside `generate_insights`, after `performance["zones"]` is set)
- Test: `tests/test_verdict.py`

**Interfaces:**
- Consumes: `zones.ZoneSettings`, `zones.predicted_zone(speed, angle_deg, height, settings)`, `zones.speed_to_hole(angle_deg, height, settings)`, `zones.landing(...)`.
- Produces: `throw_verdict(metrics: dict, others: list[dict], grades: dict, release_to_board_m: float | None, settings: ZoneSettings) -> dict` returning
  `{"headline": str, "items": [{"kind": "good"|"fix"|"note", "text": str, "metric_key": str|None}], "physics": dict|None, "personal": [dict], "method": str}`;
  and `insights.json["verdict"]` with that dict. `metrics`/`others` are `results.json["coach_metrics"]` dicts (key → `{"value", "status", "noise_floor", "label", "unit"}`).

- [ ] **Step 1: Write the failing tests** — `tests/test_verdict.py`:

```python
from cornhole_biomech.verdict import throw_verdict, personal_flags, physics_check
from cornhole_biomech.zones import ZoneSettings, speed_to_hole


def metric(value, status="reliable", noise=0.1, label="m", unit=""):
    return {"value": value, "status": status, "noise_floor": noise, "label": label, "unit": unit}


def release(speed, angle=40.0, height=0.9, status="reliable"):
    return {"bag_release_speed_m_s": metric(speed, status, 0.15, "Release speed", "m/s"),
            "bag_release_angle_deg": metric(angle, "reliable", 3.0, "Release angle", "°"),
            "bag_release_height_m": metric(height, status, 0.03, "Release height", "m")}


def test_physics_uses_measured_distance_and_required_speed():
    settings = ZoneSettings()
    p = physics_check(release(7.0), 6.0, settings)
    assert p["distance_source"] == "measured" and p["distance_m"] == 6.0
    need = speed_to_hole(40.0, 0.9, ZoneSettings(release_to_board_m=6.0))
    assert abs(p["required_speed_m_s"] - need) < 1e-6
    assert abs(p["delta_speed_m_s"] - (7.0 - need)) < 1e-6
    assert p["sensitivity_m_per_m_s"] > 0


def test_physics_falls_back_to_assumed_distance():
    p = physics_check(release(8.0), None, ZoneSettings())
    assert p["distance_source"] == "assumed" and p["distance_m"] == 7.7


def test_no_scale_skips_physics():
    v = throw_verdict(release(7.0, status="unreliable"), [], {}, 6.0, ZoneSettings())
    assert v["physics"] is None
    assert "m/s" not in v["headline"]


def test_unreachable_hole():
    p = physics_check(release(2.0, angle=5.0, height=0.3), 6.0, ZoneSettings())
    assert p["required_speed_m_s"] is None or p["landing"] in ("short", "front")
    v = throw_verdict(release(2.0, angle=5.0, height=0.3), [], {}, 6.0, ZoneSettings())
    assert v["headline"]


def test_few_throws_no_personal_flags():
    others = [{"elbow_angle_deg_at_release": metric(150.0, noise=10.0)} for _ in range(4)]
    assert personal_flags({"elbow_angle_deg_at_release": metric(190.0, noise=10.0)}, others) == []


def test_personal_flag_needs_noise_and_spread():
    others = [{"elbow_angle_deg_at_release": metric(v, noise=10.0)} for v in (148, 150, 151, 152, 150, 149)]
    flags = personal_flags({"elbow_angle_deg_at_release": metric(175.0, noise=10.0)}, others)
    assert flags and flags[0]["key"] == "elbow_angle_deg_at_release" and flags[0]["direction"] == "high"
    assert personal_flags({"elbow_angle_deg_at_release": metric(156.0, noise=10.0)}, others) == []


def test_fix_item_names_speed_when_speed_is_off():
    settings = ZoneSettings()
    need = speed_to_hole(40.0, 0.9, ZoneSettings(release_to_board_m=6.0))
    v = throw_verdict(release(need + 0.8), [], {"calibration": "WARNING"}, 6.0, settings)
    fixes = [i for i in v["items"] if i["kind"] == "fix"]
    assert fixes and fixes[0]["metric_key"] == "bag_release_speed_m_s"
    assert any(i["kind"] == "note" for i in v["items"])      # WARNING grade becomes a data note
    assert "long" in v["headline"] or "past" in v["headline"]
```

- [ ] **Step 2: Run to verify failure** — `PYTHONPATH=python .venv/bin/python -m pytest tests/test_verdict.py -q` → ImportError (no module `verdict`).

- [ ] **Step 3: Implement `verdict.py`:**

```python
"""Per-throw coaching verdict: what happened, what went well, what to work on.

Two independent checks, both stated in plain words and both reproducible:

1. Physics (drag-free point mass, zones.landing): with this throw's measured release speed v,
   angle θ and height h, and the measured release-to-board distance d (regulation 7.7 m when the
   board was not measured), where would the bag first land? The speed that reaches the hole
   centre at the same θ and h is v*; Δv = v − v*. ∂x/∂v (central difference, ±0.05 m/s) converts
   a speed error into metres of landing error.
2. Personal (within-athlete): the throw's value against the athlete's other throws, flagged only
   when |value − median| > max(noise floor, 1.5 · IQR/1.349) and at least 5 other throws exist.

Associations only; the text never claims a body variable caused the landing.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

import numpy as np

from .zones import ZoneSettings, landing, predicted_zone, speed_to_hole

MINIMUM_OTHERS = 5
RELEASE = ("bag_release_speed_m_s", "bag_release_angle_deg", "bag_release_height_m")
BODY_WORDS = {  # key: (word when higher than usual, word when lower)
    "elbow_angle_deg_at_release": ("straighter elbow", "more bent elbow"),
    "trunk_inclination_deg_at_release": ("more forward trunk lean", "more upright trunk"),
    "wrist_peak_speed_arm_lengths_s": ("faster peak hand speed", "slower peak hand speed"),
    "swing_backswing_angle_deg": ("shorter backswing", "bigger backswing"),
    "swing_forward_duration_s": ("slower forward swing", "quicker forward swing"),
    "swing_tempo_ratio": ("longer backswing relative to the forward swing", "shorter backswing relative to the forward swing"),
    "wrist_direction_at_release_deg": ("hand moving more upward at release", "hand moving flatter at release"),
    "wrist_peak_speed_time_rel_release_ms": ("peak hand speed closer to release", "peak hand speed earlier before release"),
    "bag_release_angle_deg": ("higher release angle", "lower release angle"),
    "bag_release_speed_m_s": ("faster release", "slower release"),
    "bag_release_height_m": ("higher release point", "lower release point"),
}


def _usable(metrics: dict, key: str) -> float | None:
    row = metrics.get(key) or {}
    value = row.get("value")
    if value is None or row.get("status") in ("unreliable", "unavailable", None) or not np.isfinite(value):
        return None
    return float(value)


def physics_check(metrics: dict, release_to_board_m: float | None, settings: ZoneSettings) -> dict[str, Any] | None:
    v, a, h = (_usable(metrics, k) for k in RELEASE)
    if v is None or a is None or h is None:
        return None
    measured = release_to_board_m is not None and np.isfinite(release_to_board_m) and release_to_board_m > 0
    s = replace(settings, release_to_board_m=float(release_to_board_m)) if measured else settings
    hit = predicted_zone(v, a, h, s)
    need = speed_to_hole(a, h, s)
    dv = 0.05
    x_hi = landing(v + dv, a, h, s.release_to_board_m, s.board)["horizontal_m"]
    x_lo = landing(v - dv, a, h, s.release_to_board_m, s.board)["horizontal_m"]
    hole_x = s.release_to_board_m + s.board.hole_along * np.cos(s.board.angle)
    return {"distance_m": s.release_to_board_m, "distance_source": "measured" if measured else "assumed",
            "speed_m_s": v, "angle_deg": a, "height_m": h,
            "landing": hit["kind"], "zone": hit["zone"], "from_hole_m": hit["from_hole_m"],
            "landing_x_m": hit["horizontal_m"], "hole_x_m": float(hole_x),
            "required_speed_m_s": need, "delta_speed_m_s": None if need is None else v - need,
            "sensitivity_m_per_m_s": (x_hi - x_lo) / (2 * dv)}


def personal_flags(metrics: dict, others: list[dict]) -> list[dict[str, Any]]:
    flags = []
    for key, row in metrics.items():
        value = _usable(metrics, key)
        history = [x for x in (_usable(o, key) for o in others) if x is not None]
        if value is None or len(history) < MINIMUM_OTHERS:
            continue
        median = float(np.median(history))
        q25, q75 = np.percentile(history, [25, 75])
        threshold = max(float(row.get("noise_floor") or 0.0), 1.5 * (q75 - q25) / 1.349)
        if abs(value - median) > threshold and threshold > 0:
            flags.append({"key": key, "label": row.get("label", key), "unit": row.get("unit", ""), "value": value,
                          "median": median, "q25": float(q25), "q75": float(q75),
                          "direction": "high" if value > median else "low",
                          "size": abs(value - median) / threshold})
    return sorted(flags, key=lambda f: -f["size"])


def _fmt(value: float, unit: str) -> str:
    digits = 0 if unit in ("°", "ms", "°/s") else 2 if unit in ("m", "s") else 1
    return f"{value:.{digits}f}{'' if unit == '°' else ' '}{unit}".strip()


def throw_verdict(metrics: dict, others: list[dict], grades: dict, release_to_board_m: float | None,
                  settings: ZoneSettings) -> dict[str, Any]:
    physics = physics_check(metrics, release_to_board_m, settings)
    flags = personal_flags(metrics, others)
    approx = "≈" if grades.get("calibration") != "GOOD" else ""
    items: list[dict[str, Any]] = []
    if physics:
        where = {"short": "short of the board", "front": "into the front of the board", "long": "past the board"}
        if physics["landing"] == "board":
            off = physics["from_hole_m"]
            place = "at the hole" if abs(off) < 0.08 else f"{approx}{abs(off):.2f} m {'past' if off > 0 else 'short of'} the hole"
            headline = f"Released at {physics['angle_deg']:.0f}° and {approx}{physics['speed_m_s']:.1f} m/s: the flight model puts first contact on the board, {place}."
        else:
            headline = f"Released at {physics['angle_deg']:.0f}° and {approx}{physics['speed_m_s']:.1f} m/s: the flight model puts first contact {where[physics['landing']]}."
        need = physics["required_speed_m_s"]
        if need is None:
            items.append({"kind": "fix", "metric_key": "bag_release_angle_deg",
                          "text": f"No release speed reaches the hole from {physics['height_m']:.2f} m at {physics['angle_deg']:.0f}°; the release angle is the limit."})
        elif abs(physics["delta_speed_m_s"]) * abs(physics["sensitivity_m_per_m_s"]) > 0.15:
            more = "less" if physics["delta_speed_m_s"] > 0 else "more"
            items.append({"kind": "fix", "metric_key": "bag_release_speed_m_s",
                          "text": f"Release speed: {approx}{need:.1f} m/s reaches the hole at this angle and height; this throw was {approx}{abs(physics['delta_speed_m_s']):.1f} m/s {'faster' if more == 'less' else 'slower'}. "
                                  f"Each 0.1 m/s moves first contact about {abs(physics['sensitivity_m_per_m_s']) * 0.1:.2f} m."})
        else:
            items.append({"kind": "good", "metric_key": "bag_release_speed_m_s",
                          "text": f"Release speed matched the hole ({approx}{physics['speed_m_s']:.1f} m/s vs {approx}{need:.1f} m/s needed)."})
    elif flags:
        headline = f"This throw differed from the athlete's usual pattern in {len(flags)} measured variable{'s' if len(flags) != 1 else ''}."
    elif len(others) < MINIMUM_OTHERS:
        headline = f"Measured. {MINIMUM_OTHERS - len(others)} more analysed throw{'s' if MINIMUM_OTHERS - len(others) != 1 else ''} are needed to compare it with this athlete's usual pattern."
    else:
        headline = "Every reliable measurement was within this athlete's usual range."
    for flag in flags[:2]:
        words = BODY_WORDS.get(flag["key"])
        if not words:
            continue
        word = words[0] if flag["direction"] == "high" else words[1]
        items.append({"kind": "fix" if physics is None or flag["key"] not in RELEASE else "note", "metric_key": flag["key"],
                      "text": f"Unusual for this athlete: {word} ({_fmt(flag['value'], flag['unit'])}; usual {_fmt(flag['q25'], flag['unit'])}–{_fmt(flag['q75'], flag['unit'])})."})
    steady = [k for k in ("elbow_angle_deg_at_release", "trunk_inclination_deg_at_release", "wrist_peak_speed_arm_lengths_s")
              if _usable(metrics, k) is not None and k not in {f["key"] for f in flags}
              and sum(_usable(o, k) is not None for o in others) >= MINIMUM_OTHERS]
    if steady:
        labels = [str((metrics[k] or {}).get("label", k)).lower() for k in steady]
        items.append({"kind": "good", "metric_key": steady[0], "text": f"Within the usual range: {', '.join(labels)}."})
    for stage, name in (("pose", "Body tracking"), ("bag", "Bag tracking"), ("release", "Release timing"), ("calibration", "Scale")):
        grade = grades.get(stage)
        if grade in ("WARNING", "POOR"):
            text = ("Scale comes from the bag's fall under gravity only; metres are approximate." if stage == "calibration" and grade == "WARNING"
                    else f"{name} quality is {grade.lower()}; treat related numbers with care.")
            items.append({"kind": "note", "metric_key": None, "text": text})
    order = {"fix": 0, "good": 1, "note": 2}
    items.sort(key=lambda i: order[i["kind"]])
    return {"headline": headline, "items": items[:5], "physics": physics, "personal": flags,
            "method": "Drag-free point-mass flight to first contact (zones.landing); personal flags when "
                      "|value − median| > max(noise floor, 1.5·IQR/1.349) with ≥ 5 other throws."}
```

- [ ] **Step 4: Wire into `insights.py`** — after `performance["zones"]=zone_report(rows,zone_settings)` add:

```python
    from .verdict import throw_verdict
    other_metrics=[read(d/'results.json',{}).get('coach_metrics') or {} for d in eligible_dirs if d!=directory]
    grades={k:v.get('grade') for k,v in (results.get('quality',{}).get('grades') or {}).items() if isinstance(v,dict)}
    verdict=throw_verdict(results.get('coach_metrics') or {},other_metrics,grades,
                          (results.get('summaries') or {}).get('release_to_board_front_m'),zone_settings)
```
and add `'verdict':verdict,` to `payload`. Zones: replace the `zone_settings=` line with the median measured distance when ≥ 3 throws have one:

```python
    measured=[x for x in ((read(d/'results.json',{}).get('summaries') or {}).get('release_to_board_front_m') for d in eligible_dirs) if isinstance(x,(int,float))]
    default_distance=float(settings.get('releaseToBoardMeters') or 7.7)
    zone_settings=ZoneSettings(release_to_board_m=float(np.median(measured)) if len(measured)>=3 else default_distance)
```
(import numpy as np at the top of insights.py if missing) and record `performance["zones"]["settings"]["distance_source"]="measured_median" if len(measured)>=3 else "assumed"` after `zone_report`.

- [ ] **Step 5: Run** the new tests and the full Python suite; all pass.
- [ ] **Step 6: Commit** `verdict.py`, `insights.py`, `tests/test_verdict.py`.

---

### Task 2: Design system + three-column shell + removals

**Files:**
- Create: `Sources/CornholeBiomechanics/DesignSystem.swift`, `SidebarView.swift`, `ThrowListView.swift`, `ThrowReportView.swift` (stub), `AthleteSummaryView.swift` (stub), `LaunchLabView.swift` (stub), `SettingsView.swift`
- Modify: `ContentView.swift` (rewrite), `CornholeBiomechanicsApp.swift` (commands + `Settings` scene), `Models.swift` (`AppSection` → `Destination`), `InsightsModels.swift` (add `Verdict` decoding), `ProjectStore.swift` (selection defaults only)
- Delete: `OverviewView.swift`, `ReferenceView.swift`, `CompareView.swift`, `ResultsView.swift`, `ThrowComparisonPanel.swift`, `SwingExplorerPanel.swift`, `LaunchExplorerView.swift`, `AthleteDashboardView.swift` (DashboardContent moves to AthleteSummaryView in Task 5; keep the file until then if Task 5 runs later — see Interfaces), `SessionsView.swift` (SessionForm only if unused after AthletesView change), tests `ThrowComparisonTests.swift`.
- Test: `Tests/CornholeBiomechanicsTests/DesignSystemTests.swift`

**Interfaces (produced, used by Tasks 3–5):**

```swift
enum Space { static let xs: CGFloat = 4, s: CGFloat = 8, m: CGFloat = 12, l: CGFloat = 16, xl: CGFloat = 24, xxl: CGFloat = 32 }
struct Card<Content: View>: View { init(_ title: String? = nil, symbol: String? = nil, subtitle: String? = nil, @ViewBuilder content: () -> Content) }
struct Page<Content: View>: View { init(@ViewBuilder content: () -> Content) }   // ScrollView, margins 24, max width 1120, spacing 24
struct RangeBarModel { let values: [Double]; let current: Double?; let target: ClosedRange<Double>?
                       var domain: ClosedRange<Double>; var quartiles: (Double, Double)? }   // domain padded 10 %, includes target and current
struct RangeBar: View { init(model: RangeBarModel) }                               // 22 pt tall Canvas
struct MetricTile: View { init(row: CoachMetricRow, history: [Double], target: ClosedRange<Double>? = nil, seek: ((Int) -> Void)? = nil) }
struct ResultBadge: View { init(score: ScoreCategory?) }                            // Hole / Board / Miss / —, colored capsule with symbol
struct EmptyState: View { init(_ title: String, symbol: String, message: String, action: (label: String, run: () -> Void)? = nil) }
enum Destination: Hashable { case summary(UUID); case throwReport(UUID); case launchLab }
// ThrowReportView(trial: Trial), AthleteSummaryView(athleteID: UUID), LaunchLabView() — stubs until Tasks 3–5.
struct Verdict: Decodable { struct Item: Decodable, Identifiable { var kind: String; var text: String; var metric_key: String?; var id: String { kind + text } }
                            struct Physics: Decodable { var distance_m: Double; var distance_source: String; var landing: String; var zone: String; var from_hole_m: Double?; var required_speed_m_s: Double?; var delta_speed_m_s: Double?; var sensitivity_m_per_m_s: Double?; var landing_x_m: Double?; var hole_x_m: Double? }
                            var headline: String; var items: [Item]; var physics: Physics? }
// TrialInsights gains `var verdict: Verdict?`
```

- [ ] **Step 1: Failing test** `DesignSystemTests`:

```swift
import XCTest
@testable import CornholeBiomechanics
final class DesignSystemTests: XCTestCase {
    func testDomainIncludesTargetAndCurrent() {
        let m = RangeBarModel(values: [7.5, 7.8, 8.0], current: 9.0, target: 6.9...7.2)
        XCTAssertLessThanOrEqual(m.domain.lowerBound, 6.9); XCTAssertGreaterThanOrEqual(m.domain.upperBound, 9.0)
    }
    func testQuartilesNeedThreeValues() {
        XCTAssertNil(RangeBarModel(values: [1, 2], current: nil, target: nil).quartiles)
        let q = RangeBarModel(values: [1, 2, 3, 4, 5], current: nil, target: nil).quartiles!
        XCTAssertEqual(q.0, 2, accuracy: 1e-9); XCTAssertEqual(q.1, 4, accuracy: 1e-9)
    }
    func testDegenerateDomainIsWidened() {
        let m = RangeBarModel(values: [5, 5, 5], current: 5, target: nil)
        XCTAssertGreaterThan(m.domain.upperBound - m.domain.lowerBound, 0)
    }
}
```
- [ ] **Step 2:** run → fails (types missing).
- [ ] **Step 3: Implement DesignSystem.swift** (quartiles by linear interpolation, same as numpy default; domain = min/max of values ∪ current ∪ target, padded 10 % of span, min span 1e-6·|x|+1e-3).
- [ ] **Step 4: Rewrite ContentView** as `NavigationSplitView(columnVisibility:) { SidebarView } content: { ThrowListView or nothing } detail: { destination }`; sidebar sections "Athletes" (rows with count, `.contextMenu` Edit…/Reveal in Finder/Delete…, header "+" → AthleteForm) and "Tools" (Launch Lab). When Launch Lab is selected set `columnVisibility = .doubleColumn`-equivalent by hiding content (`.navigationSplitViewColumnWidth(0)` is not allowed — instead show `ThrowListView` only when an athlete is selected; for Launch Lab render `LaunchLabView` in content+detail by using `NavigationSplitView` with detail = LaunchLab and content = an `EmptyView` with `.navigationSplitViewColumnWidth(min: 0, ideal: 0, max: 0)`; verify visually and fall back to a two-column split if needed). Toolbar on the throw list: `Button("Import Videos", systemImage: "plus")` primary. Keep analysis progress inset, error alert, import sheet, notifications (`importTrialVideo`, `analyzeSelectedTrial`, `addTrialOutcome`, `exportSelectedTrial`, `addAthlete`, library commands). After `AnalysisService.analyze` completes for a trial, select `.throwReport(trial.id)`.
- [ ] **Step 5: ThrowListView** — `List(selection:)` with pinned `Label("Summary", systemImage: "chart.bar.xaxis")` row then throws: title, `ResultBadge`, "7.8 m/s · 41°" secondary (from results.json coach metrics, cached per trial in a small `@State` dictionary loaded off the main thread), `exclamationmark.triangle` when any grade is WARNING/POOR (`replay.json` grades), `ProgressView` when `analysis.activeTrialID == trial.id`, "Not analyzed" + "Analyze" button when `analysisRelativePath == nil`. Context menu: Analyze / Re-analyze, Reveal Video, Delete Throw…. Empty state: recording guide text (from CameraGuideCard) + Import button.
- [ ] **Step 6: SettingsView** (`Settings { SettingsView() }` scene, tabs General (appearance) / Analysis (embed existing `AnalysisSettingsView` content) / Library (Choose, New, Reveal, Import legacy)). Remove the "Appearance" command menu (moved to Settings); keep File commands; add Help → "Recording Guide" (opens a sheet with the guide).
- [ ] **Step 7: Delete the removed files**, fix compile errors by deleting now-unused references (not by stubbing them back). Keep model types.
- [ ] **Step 8:** build + run all Swift tests; commit.

---

### Task 3: Launch Lab

**Files:** Modify `LaunchModel.swift` (add zone classification); replace `LaunchLabView.swift`; create `LaunchScene.swift`, `SuccessMap.swift`; test `LaunchModelTests.swift` (extend).

**Interfaces:** Consumes `Card`, `Page`, `Space`, `LaunchModel`, `LaunchParameters`, `ProjectStore.selectedAthleteID`, `CoachMetricsDocument.load(_:)`. Produces `enum LandingZone { case hole, board, off }`, `LaunchModel.zone(slideAllowance: Double = 0.45, slideUp: Double = 0.30) -> LandingZone`, `SuccessMap(params: Binding<LaunchParameters>, throws: [MeasuredRelease])`, `struct MeasuredRelease: Identifiable { id: UUID; label: String; speed: Double; angle: Double; height: Double; score: ScoreCategory? }` (Athlete summary reuses SuccessMap).

- [ ] **Step 1: Failing tests** mirroring `zones.py` rules: board landing within `[holeAlong − 0.45, holeAlong + holeRadius]` → `.hole`; board elsewhere → `.board`; short by ≤ 0.30 m → `.board`; short further, front face, long → `.off`. Use `LaunchModel.speedToHitHole()` to build a hole case, +2 m/s for long, −2 m/s for off-short.
- [ ] **Step 2:** run → fail. **Step 3:** implement `zone(...)` from `landing()`; tests pass.
- [ ] **Step 4: LaunchScene** — `TimelineView(.animation)` + `Canvas`, world→screen transform fitting x ∈ [−0.8, distance + 1.6] m and y ∈ [0, max(apex, 1.9) + 0.2] m with equal scale; draws 1 m grid (quaternary), floor line, board profile polygon with hole gap, stick figure (head circle, trunk, legs in a stride, throwing arm rotating from −60° to the release direction during the first 0.35 s of the animation, releasing at the hand = release point), bag (12 cm rounded square, `measuredInk`) along the model path with a 0.25 s fading trail, apex marker, landing marker coloured by zone with label, ghost arcs (last 3 parameter sets, 25 % opacity). Animation time 0 → flight time + 0.6 s; "Throw" button restarts; respects Reduce Motion (draw final state).
- [ ] **Step 5: SuccessMap** — Canvas heat map over angle 10–70° (x) × speed 3–11 m/s (y), 0.5°×0.05 m/s cells at current height and distance, fill = zone colour (ZoneStyle) at 55 % opacity, axes with ticks every 10° / 1 m/s, crosshair at current params, athlete throws as points (filled circle scored, diamond board, ✕ miss, hollow unknown), click/drag sets angle+speed. Recompute in a `Task.detached` when height/distance change (≤ 7,000 model evaluations).
- [ ] **Step 6: LaunchLabView** — Page: header ("Launch Lab" + one-line purpose), row [LaunchScene card (flex) | controls Form card 300 pt: 4 sliders with value text fields, "Start from" Menu (selected athlete's analysed throws with scaled release speed/angle/height), "Solve speed for the hole" button, readouts grid: Outcome, From hole, Flight time, Apex, Speed for the hole], SuccessMap card, Sensitivity card (three numbers with units per 0.1 m/s, 1°, 1 cm), "Model and assumptions" disclosure with equations x = v cosθ t, y = h + v sinθ t − ½gt², g = 9.80665 m/s².
- [ ] **Step 7:** build, tests, commit.

---

### Task 4: Throw report

**Files:** replace `ThrowReportView.swift`; create `VerdictCard.swift`, `ThrowCharts.swift`, `StickFigureReplay.swift`, `FixTrackingSheet.swift`; modify `ThrowReplayView.swift` (Video/Animation picker, "Show" menu replaces three checkboxes), `TrialsView.swift` (keep `VideoPoseEditor`, `QualityEventsView`, bag editors, overlays; delete `TrialsView`, `TrialDetailView`, `MeasurementsView` tab host), `TrialResultsView.swift` (delete `ResultsView`; keep reusable pieces still used: `BoardMap`, `QuickOutcomeBar` only if reused, else delete).

**Interfaces:** Consumes Task 2 components and `Verdict`; `ReplayDocument`, `CoachMetricsDocument`, `TrialDataController` (`load(analysisURL:)`, `normalized`, `results`, `pose`), `AnalysisService.refreshInsights`-equivalent currently used by `ResultsView.refresh()` (move that function verbatim into ThrowReportView), `KinematicsCSV` if present or `normalized` series for angle charts. Produces nothing for other tasks.

- [ ] **Step 1: Layout** per spec §3: header with `Picker` (segmented, Hole/Board/Miss/None → `store.setScore`), toolbar (`Fix Tracking…` `wrench.and.screwdriver`, `Re-analyze` `arrow.clockwise`, More `ellipsis.circle` menu: Trim/Crop…, Edit Throw…, Reveal Video, Export Package…, Delete Throw…).
- [ ] **Step 2: VerdictCard** — headline `.title3.weight(.semibold)`; items as rows with symbols `checkmark.circle.fill` (green, "Went well"), `arrow.up.forward.circle.fill` (orange, "Work on"), `info.circle` (secondary, "Data note"); tapping a row with `metric_key` seeks to that metric's frame. Stale banner when `needs_reanalysis`.
- [ ] **Step 3: Key numbers** — two `Card`s ("Release", "Body") with `LazyVGrid(.adaptive(minimum: 180))` of `MetricTile`; history = same metric from the athlete's other analysed throws (load their results.json once per athlete); target for speed = the contiguous range of speeds (0.01 m/s steps) whose `LaunchModel(...).zone() == .hole` at this throw's angle, height and `verdict.physics.distance_m`; target for angle = the same scan over angle (0.1° steps) at this throw's speed. No target when `verdict.physics` is nil.
- [ ] **Step 4: ThrowCharts** — `JointAngleChart` (elbow angle + trunk inclination vs ms from release from `kinematics.csv` columns `time_seconds`, `elbow_angle_deg`, `trunk_inclination_deg`; two series with legend, event RuleMarks), existing `WristSpeedChart` restyled, `FlightChart` (metres when `pixels_per_meter` exists: x forward, y up, measured points `measuredInk`, drag-free fit dashed, board profile at `verdict.physics.distance_m`), `TimingStrip` (horizontal event timeline in ms). 2-up `Grid` ≥ 900 pt, 1-up below (ViewThatFits).
- [ ] **Step 5: StickFigureReplay** — Canvas drawing pose landmarks for `frame` scaled to fit (throwing arm `athleteInk` 4 pt, other bones secondary 2.5 pt, joints dots, head circle from nose/ears), bag path in the same pixel space (`ReplayDocument.toFrame`), floor line at the lowest ankle; shares `currentFrame` with the video.
- [ ] **Step 6: FixTrackingSheet** — 1100×760 sheet; `TabView` (Body landmarks: `VideoPoseEditor`; Events & quality: `QualityEventsView`), footer "Re-analyze with corrections" primary + Close.
- [ ] **Step 7: Scientific details** disclosure: `Table` of all coach metrics (Metric, Value, Uncertainty, Status, Definition), TrustStrip + grade rules, bag launch fit summary, warnings, provenance grid, Export button.
- [ ] **Step 8:** build, tests, commit.

---

### Task 5: Athlete summary

**Files:** replace `AthleteSummaryView.swift`; create `ThrowComparisonTable.swift`, `ConsistencyCharts.swift`; delete `AthleteDashboardView.swift` after moving `DashboardContent` pieces; update `VisualQATests.swift` to render `AthleteSummaryContent`.

**Interfaces:** Consumes `AthleteDashboard` (dashboards/<id>.json; refresh via `analysis.refreshDashboard(athleteID:store:)`), `TrialInsights.consistency` (traces, tau), `CoachMetricsDocument`, `SuccessMap`/`MeasuredRelease` from Task 3 (if Task 3 is not merged yet, leave a `// SuccessMap` slot and add it at integration). Produces `AthleteSummaryContent(dashboard:rows:consistency:open:)` (pure view for QA).

- [ ] **Step 1:** Scoring tiles (PPR, In, On, Off, Bags) with the no-results call to action.
- [ ] **Step 2:** Coach focus card (headline, priorities with the five-check chips, observed differences disclosure).
- [ ] **Step 3:** `ThrowComparisonTable` — SwiftUI `Table` with sortable columns (Throw, Result badge, Speed, Angle, Height, Elbow at release, Peak wrist speed, Tempo, Quality glyph); values "—" when unreliable; footer text row "Median · SD" computed in Swift; double-click (`contextMenu(forSelectionType:primaryAction:)`) opens the throw.
- [ ] **Step 4:** Consistency: elbow curves over normalised time (faint per-throw lines coloured by result, mean line, ±1 SD `AreaMark`), release-profile dot strips (restyled from DashboardContent).
- [ ] **Step 5:** Release map card with `SuccessMap` at the athlete's median height and distance (read-only, no drag).
- [ ] **Step 6:** Research details disclosure: evidence chain table, trust grade counts, compensation.
- [ ] **Step 7:** build, tests, commit.

---

### Task 6: Integration, visual QA and review

- [ ] Merge task branches; resolve `ContentView`/project conflicts.
- [ ] Extend `VisualQATests` to render ThrowReport content, Athlete summary content and Launch Lab (light + dark) from `CORNHOLE_VISUAL_QA`; build the QA folder from the scratch re-analysed library; inspect every PNG; fix spacing/overlap issues.
- [ ] Run Python and Swift suites; `./build_app.sh`; commit.
- [ ] Whole-branch code review (pr-review-toolkit:code-reviewer); fix findings.
- [ ] Write `docs/METHODS_AND_MATH.md` (System Design & Methodology; Application & Feedback Framework; equations).
