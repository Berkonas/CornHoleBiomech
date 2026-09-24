# Coaching system: measured replay, coach metrics, reliability and priorities

Written 23 September 2026. This covers what a coach sees: **Coach Dashboard** (athlete) and **Throw Replay**
(one throw). Evidence for the measurements is in `docs/LIGHT_VALIDATION.md`; the tracking design is in
`docs/AUTOMATIC_TRACKING.md`.

Analysis hierarchy (a hypothesis structure, not a causal claim):

```
body movement → release mechanics → bag flight → first contact / rest → points
```

## 1. Throw Replay (replay.py → replay.json; ThrowReplayView.swift)

The video plays with:
- **Measured bag path:** solid orange. Bold up to the current frame, faint afterwards. Drawn through the
  Kalman/RTS estimate, which follows the measured centres and leaves gaps where nothing was measured.
- **Drag-free model:** thin, dashed and white. A reference only, never styled like the measured path.
- **After first contact:** a yellow path to the automatically found rest point.
- **Skeleton:** the throwing arm is highlighted.
- **Event pins:**
  - release;
  - apex (from the fitted arc, only when inside the measured flight);
  - first contact (last frame on the flight arc);
  - final rest (an automatic estimate: confirm it in the video);
  - body events: top of backswing, peak wrist speed, fastest elbow extension.

Every path is stored once, in the release frame's pixels, and mapped onto each frame with the
camera transform. A hand-held clip therefore shows the whole throw in place. Clicking an event chip,
a metric's ▶ button or the wrist-speed chart seeks the video to that frame. The panel under the video
shows the values measured at the nearest event.

## 2. Coach metrics (reliability.py)

All are projected 2D. "Arm lengths" = median shoulder–elbow + elbow–wrist length in the clip.

| Metric | Definition / equation | Units | Input | Noise floor | Main limitation |
|---|---|---|---|---|---|
| Release speed | \|v₀\| from a gravity-constrained linear fit of the first ~0.12 s of flight | m/s | bag centres, scale | 0.15 | metres from the fall-based scale (WARNING) |
| Release angle | atan2(v₀y, v₀x) | ° | bag centres | 3 (or 2 × fit SE) | camera must be roughly side-on |
| Release height | bag centre above the lowest foot point at release | m | bag, feet, scale | 0.03 | scale; foot landmark noise |
| Release point | (bag − throwing shoulder) along the target axis ÷ arm length | arm lengths | bag, shoulder | 0.05 | — |
| Wrist speed at release | \|d p_wrist/dt\| at release; camera-steadied, 6 Hz filtered | arm lengths/s | wrist | 0.3 | filter smooths peaks |
| Peak wrist speed | max \|v_wrist\| from top of backswing to release + 0.1 s | arm lengths/s | wrist | 0.3 | same |
| Peak wrist speed timing | t(peak) − t(release) | ms | wrist, release | 35 | ±1 frame each (16.7 ms) |
| Hand direction at release | atan2(v_wy, v_wx) | ° | wrist | 5 | — |
| Arm angle at release | shoulder→wrist line from straight down (0°) toward the board (90°) | ° | shoulder, wrist | 5 | release-frame sensitivity |
| Backswing | minimum arm angle before release | ° | shoulder, wrist | 5 | plausible range −170…10° |
| Elbow angle at release | acos((S−E)·(W−E) / (\|S−E\|\|W−E\|)); 180° = straight | ° | shoulder, elbow, wrist | 10 | hidden if a segment is foreshortened |
| Peak elbow extension speed | max dθ_elbow/dt in the forward swing | °/s | same | 150 | **exploratory** (derivative of a noisy 2D angle) |
| Elbow extension timing | t(peak extension) − t(release) | ms | same | 50 | exploratory |
| Forward swing time | top of backswing → release | s | wrist, release | 0.035 | plausible range 0.15–1.5 s |
| Tempo | backswing time ÷ forward-swing time; backswing starts at the last rest before the fastest backward swing | ratio | shoulder, wrist | 0.15 | plausible range 0.3–4 |
| Trunk lean at release | hip-midpoint → shoulder-midpoint line from vertical, + toward the board | ° | shoulders, hips | 5 | camera roll |

Noise floors are the smallest difference the analysis will interpret. Most are provisional estimates
(documented in `performance.py`/`reliability.py`) pending a measured error study.

**Never shown to coaches:** upper-arm and forearm orientation ranges and velocities. A segment pointing at
the camera has an undefined 2D direction; one pilot clip showed a "350° forearm range".

## 3. Per-throw reliability rules

Each coach metric is checked on every throw:

1. **Visible:** landmark confidence ≥ threshold in release ± 2 frames.
2. **In plane:** each segment ≥ 70% of its usual projected length.
3. **Stable:** filtered stays within 0.1 arm lengths of raw.
4. **Plausible:** inside physiological bounds.
5. **Release-window sensitivity:** "at release" values that change by more than their noise floor between
   the two release cues get a caution.
6. **Upstream grades:** bag metrics inherit the bag, release and scale grades.

Result per metric:
- **Reliable** or **Use with caution:** the value is shown, with the reason for any caution.
- **Insufficient tracking quality:** the value is withheld.
- **Not measured.**

Withheld values never enter the athlete analysis.

**Release window.** Two automatic cues bracket release:
- the first free-flight frame (used as release);
- the frame where the flight, traced backwards, meets the wrist (earlier by construction).

Release grade:
- **GOOD:** within 4 frames (the wrist cue is 2–3 frames early by construction; Task 9b audit), or labelled by a person;
- **WARNING:** 5–6 frames;
- **POOR:** more than 6 frames.

## 4. Athlete analysis and coaching priorities (performance.py, coaching.py)

- **Performance:**
  - points per bag and PPR (ACL definition);
  - hole / board / miss %;
  - landing grouping (RMS radius of first contacts);
  - target error.
- **Release profile:** for each metric:
  - median and middle half;
  - SD, and CV for ratio-scale metrics;
  - consistency judged against the noise floor: *within measurement noise* (SD ≤ floor), *moderate*,
    *variable* (SD > 2 × floor);
  - Hopkins' smallest worthwhile change (0.2 × SD) is recorded as the smallest difference worth discussing.
- **Release compensation** (after Müller & Sternad 2004):
  - predicted landing spread with the athlete's own speed–angle pairing, versus random pairing;
  - ratio > 1 means the athlete compensates.
  - Needs ≥ 8 throws with metres; model-based.
- **Evidence chain:** within-athlete Spearman ρ with a bootstrap 95% CI for body → release, release → flight,
  release → points and body → points. "Supported" = the CI excludes 0 with ≥ 8 throws.
- **Coaching priority gate.** A feature becomes a priority only if it passes all five checks:
  1. associated with scoring (Cliff's δ above the chance level for the number of tests, ≥ 5 throws per group);
  2. median difference larger than the noise floor;
  3. repeatable (bootstrap CI of the difference excludes 0);
  4. reliably measured on ≥ 80% of throws;
  5. interpretable and modifiable (not an exploratory derivative).

  A difference that is larger than the noise floor and has at least a medium effect, but fails a check, is
  listed as an **observed difference, not advice**, with the failed checks named.

  A priority names typical scored throws of the same athlete to review in the replay.

The pilot library has no recorded results yet, so its dashboards show profiles, consistency and the evidence
chain, but no priorities. For Player 3, release angle → apex height is supported (ρ = 0.78, n = 10), as physics expects.
Recording hole / board / miss (one click per throw in Throw Replay) is the step that unlocks priorities.

## 5. Limits

- The camera is single and hand-held. All angles are projected.
- Metres come from the bag's fall (WARNING) until a meter stick is filmed in the throwing plane.
- With ~10 throws per athlete only large effects can be detected. The stress test (`docs/STRESS_TEST.md`)
  suggests 20–40 throws per athlete for reliable outcome comparisons.
- Associations are not causes. A priority is a hypothesis for the coach to test in practice.
