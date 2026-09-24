# Coach app redesign (Part 2) — design

Date: 2026-09-24. Status: direction approved by the user in chat ("good direction … redesign the
app, organize the buttons, delete unnecessary items, Apple design rules, proper data visualisation
for athletes, coaches and sport scientists"). References/Compare removal approved implicitly
("delete unnecessary items").

## 1. Goal and success criteria

Upload a video → the coach and athlete see, on one page, what happened on that throw, what went
right, what to fix, and the biomechanics behind it — with honest numbers. Across throws, the same
athlete's throws are compared in one table and a few plots. The Launch Lab teaches the release
physics. Every screen follows the macOS Human Interface Guidelines.

Success means:
1. Sidebar has **one list of athletes plus Launch Lab**; no "Research tools", Overview, References,
   Compare, Throw Replay or Throws destinations remain.
2. After an analysis finishes, the app shows the **Throw report** for that throw with a verdict
   sentence at the top.
3. A single throw shows ≤ 8 headline numbers, each with a range bar (athlete's own spread and, for
   release speed/angle, the physics hole window). Everything else is behind one disclosure.
4. Correction tools (landmark drag, bag seed, events, trim) live in one **Fix Tracking** sheet.
5. Every chart has axis titles with units, event markers, and works in light and dark mode.
6. No composite scores; values that failed reliability rules are shown as "—" with the reason.
7. Verdict text is produced in Python from tested math (not written in Swift views).

## 2. Information architecture (Apple three-column NavigationSplitView)

```
Sidebar                 Content column                 Detail
─────────               ───────────────                ──────
ATHLETES           +    Player 1                        Throw report  (a throw selected)
 Player 1  9            ┌ Summary · all throws ┐        Athlete summary (Summary selected)
 Player 2  6            Throw 1   Hole   7.9 m/s 38°
 Player 3 11            Throw 2   —      8.1 m/s 44°
TOOLS                   …                        [+]
 Launch Lab                                              Launch Lab (content column hidden)
```

* Sidebar: section "Athletes" (row = name + throw count; context menu Edit / Reveal / Delete;
  "+" in the section header adds an athlete) and section "Tools" with Launch Lab.
* Content column: the selected athlete's throws, newest last, with a pinned "Summary" row. Row =
  name, result badge (Hole / Board / Miss / none), release speed and angle, a warning glyph when a
  quality grade is WARNING/POOR, a spinner while analysing. Toolbar: **Import Videos** (primary,
  ⇧⌘I). Empty state explains the recording setup and offers Import.
* Detail: Throw report, Athlete summary or Launch Lab.
* Settings (⌘,) window: appearance, analysis settings (confidence threshold, filter), library
  location (Choose / New / Reveal / Import legacy). Help menu: "Recording Guide".
* Removed UI: OverviewView, ReferenceView, CompareView, ResultsView scatter, TrialsView tab bar,
  MeasurementsView "research data" tab, SwingExplorerPanel, "Import Reference Video", session
  management page. Data model fields for references and sessions are kept so old libraries decode.

## 3. Throw report (detail, one scrolling page, max width 1120, 24 pt margins, 24 pt between cards)

1. **Header**: "Throw 6" + "Player 1 · 17 Sep 2026 · side view · 60 fps". Right: result picker
   (segmented: Hole 3 · Board 1 · Miss 0, one click saves). Toolbar: Fix Tracking…, Re-analyze,
   More menu (Trim/Crop…, Edit Throw…, Reveal Video, Export Package…, Delete…).
2. **Verdict card** (`insights.verdict`, §6): one headline sentence and up to three rows marked
   ✓ went well / ↗ to work on / ⓘ data note. Shows "Analysis out of date — Re-analyze" instead when
   `needs_reanalysis`.
3. **Replay card**: segmented View = Video (existing overlay: skeleton, measured bag path, dashed
   drag-free model) | Animation (stick figure from pose landmarks + bag path on a clean canvas,
   same timeline). Controls: play/pause (space), ¼×/½×/1×, frame step, event chips (Backswing,
   Peak wrist speed, Release, Apex, First contact). Overlay toggles move into a small "Show" menu.
4. **Key numbers** — two rows of `MetricTile`s:
   * Release: speed (m/s), angle (°), height (m).
   * Body: elbow angle at release, trunk lean at release, peak wrist speed, backswing angle, tempo.
   Tile = label, value, ± standard error or noise floor, a range bar (athlete's throws: min–max
   line, IQR box, this throw's marker; for speed and angle also the hole window band), a status
   glyph only when caution/unreliable, ⓘ popover with the definition and reasons. Clicking a tile
   seeks the replay to the tile's event.
5. **Plots** (Swift Charts, 2-up grid, 1-up below 900 pt):
   * Joint angles vs time from release (elbow angle, trunk inclination; degrees) with event rules.
   * Speeds vs time from release (wrist speed; arm lengths/s) with peak and release markers.
   * Bag flight, side view in metres when scaled (measured points, drag-free fit dashed, board drawn
     at the measured or assumed distance), pixels otherwise.
   * Timing strip: backswing → peak wrist speed → release → first contact on one time axis (ms).
   Clicking any time chart seeks the replay.
6. **Scientific details** (one DisclosureGroup, closed by default): full metrics table (SwiftUI
   `Table`: metric, value, unit, SE/noise floor, status, definition), data-quality grades with
   their rules, bag launch fit (method, RMSE, SE), measurement warnings, provenance (engine, model
   hash, method version, filter), Export.

## 4. Athlete summary (detail)

1. Header: name, throws analysed, throws with a result. Toolbar: Refresh.
2. **Scoring tiles**: PPR, In %, On %, Off %, bags recorded; a call to action when no results.
3. **Coach focus**: dashboard headline + priorities (existing five-check gate) + "observed
   differences, not yet advice" disclosure.
4. **Throw comparison table** (SwiftUI `Table`, sortable): Throw, Result, Release speed, angle,
   height, elbow at release, peak wrist speed, tempo, quality. Median and SD footer row. Double-click
   opens the throw.
5. **Consistency plots**: elbow-angle curves over normalised time (each throw faint, mean ± 1 SD
   band); release profile dot strips (existing, restyled: scored blue, miss orange, none grey) with
   SD vs noise floor.
6. **Release map**: throws on the speed × angle success map (shared view with Launch Lab).
7. **Research details** disclosure: evidence chain (Spearman ρ, bootstrap CI, n), data trust grade
   counts, compensation estimate.

## 5. Launch Lab

One screen, no modes:
* **Scene** (Canvas + TimelineView, to scale, metres grid): floor, regulation board (48 in deck,
  3 in front, 12 in back, 6 in hole 9 in from the back), stick-figure thrower whose arm swings
  through the release angle, bag flight animated with a fading trail, apex and landing markers,
  ghost arcs of the last three throws. "Throw" button (⏎) replays the animation.
* **Controls** (Form, grouped): release speed, angle, height, release-to-board distance; "Start from"
  menu listing the selected athlete's measured throws; "Solve for the hole" button.
* **Readouts**: outcome (hole window / on board / short / long), distance from hole centre, flight
  time, apex height, speed needed for the hole at this angle and height.
* **Success map**: heat map over angle 10–70° × speed 3–11 m/s coloured by predicted first
  contact (hole window / board / off), current parameters as a crosshair, the athlete's measured
  throws as points. Clicking the map sets speed and angle.
* **Sensitivity**: ∂x/∂v, ∂x/∂θ, ∂x/∂h (cm per 0.1 m/s, per 1°, per 1 cm), central differences.
* Model and assumptions disclosure (drag-free point mass; equations).

## 6. Engine change: per-throw verdict (python, `verdict.py`, called from `insights.py`)

Inputs: this throw's coach metrics, the athlete's other analysed throws (same data insights already
loads), `release_to_board_front_m` for this throw (from the chain/board engine) and zone settings.

1. **Physics check** (needs release speed, angle, height with status ≠ unreliable):
   distance `d` = this throw's measured release-to-board-front distance when available, else the
   settings value (7.7 m) and the text says "assumed regulation distance". Drag-free first contact
   `x(v, θ, h)` with the board profile (zones.landing). Required speed `v*` = speed_to_hole(θ, h).
   Report landing class, signed distance to the hole centre along the board, `Δv = v − v*`, and the
   linear sensitivity `∂x/∂v`. If the scale is WARNING the numbers carry "≈".
2. **Personal comparison** (needs ≥ 5 other throws with the metric): median and IQR of the other
   throws; flag when `|value − median| > max(noise_floor, 1.5 × IQR/1.349)` (≈ 1.5 robust SD).
   Direction words come from a per-metric table (e.g. elbow: "more extended" / "more bent").
3. **Selection**: headline = physics result if available, else personal outliers, else "measured;
   need more throws to compare". "To work on" = the release variable with the largest share of the
   predicted landing error (|∂x/∂q · Δq|, Δq relative to the value that reaches the hole), plus at
   most one body metric flagged by step 2 that the dashboard evidence chain links to that release
   variable (or any flagged body metric, labelled "unusual for this athlete"). "Went well" = release
   variables within the hole window or within the athlete's IQR. Data notes = WARNING/POOR grades.
4. Output `insights.verdict = {headline, items:[{kind: good|fix|note, text, metric_key?}],
   physics:{distance_m, distance_source, landing, from_hole_m, required_speed_m_s, delta_speed_m_s,
   sensitivity_m_per_m_s}, method}`. Unit-tested.

Zones (athlete level) use the median measured release-to-board distance of the athlete's throws
when ≥ 3 are measured; otherwise the setting, labelled as assumed.

## 7. Visual system (DesignSystem.swift)

* Spacing scale 4/8/12/16/24/32; card padding 16; corner radius 12; page margins 24.
* Type: largeTitle page title, title2 card titles, headline tile labels, `.title.monospacedDigit()`
  tile values, caption notes. SF Symbols only.
* Colour: semantic system colours for chrome; data colours fixed and reused everywhere — scored
  `scoredInk` blue, miss `missInk` orange, no result grey, measured bag `measuredInk`, model dashed
  secondary, athlete `athleteInk` teal; status green/orange/red always paired with a glyph.
* Components: `Card`, `CardHeader`, `MetricTile`, `RangeBar`, `ResultBadge`, `EmptyState`.

## 8. Testing

* Python: `tests/test_verdict.py` (physics check against zones.landing; personal flags; selection;
  missing inputs).
* Swift: existing unit tests keep passing (tests for removed views deleted with them); new
  `DesignSystemTests` for RangeBar domain maths; VisualQATests renders Throw report, Athlete summary
  and Launch Lab in light and dark from a scratch copy of the re-analysed pilot library.
* Manual: build with `verify.sh`, open the app on the pilot library.

## 9. Out of scope

Changing tracking models (pose/bag), new sensors, cloud features, iOS. Reference-similarity
analysis stays in the engine but has no UI.
