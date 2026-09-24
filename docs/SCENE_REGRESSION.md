# Scene regression: board detection and camera field of view on the pilot library

Measured on the 26 pilot throws (Players 1–3, `testsep17 - 1..26.mov`) with
`scripts/regression_check.py` (two-pass analysis in scratch copies; the library is never
modified) and `scripts/board_coverage.py` (one row per throw + counts). Task 11 extends this file.

Reproduce:

    MPLCONFIGDIR=$TMPDIR/mpl PYTHONPATH=python .venv/bin/python scripts/regression_check.py \
        --library "~/Documents/Cornhole Pilot Library" --scratch "$TMPDIR/scene" --output "$TMPDIR/scene.json"
    PYTHONPATH=python .venv/bin/python scripts/board_coverage.py --analyses "$TMPDIR/scene" \
        --qa-dir "$TMPDIR/board-qa" --output "$TMPDIR/coverage.json"

## Task 8c, Part A — before (commit 5848869, Task 8b scratch run)

Spec criterion 1 is that the board is found automatically on at least 22 of 26 clips.

| | count |
|---|---|
| flights accepted | 21 / 26 (the other 5 are needs_review; no clip has zero flights) |
| boards found | **16 / 26** (Player 1: 7/9, Player 2: 6/6, Player 3: 3/11) |
| boards found among accepted flights | 13 / 21 |
| per-throw HFOV measured | 10 |

Board detection ran on all 26 clips, because a needs_review flight also sets the plate's
reference frame. Player 3's gap is therefore **board not found (8/11)**, not a missing flight. The
5 non-accepted throws were also checked on a middle-frame plate, and each gave the same answer as
its release-frame plate (3 found, 2 not found).

All 10 misses have the same cause: the **detector threshold is too high for a pale deck.** Every
board is fully in frame and not occluded. The plates are soft, but none is doubled. Bags lie on
the floor near the board, never on the deck. Measured over the red-hue pixels inside the deck:

| group | red-hue px in deck | median S | px with S ≥ 40 | px with S ≥ 30 |
|---|---|---|---|---|
| 16 found | 4 058–5 749 | 30–50 | 1 425–3 282 | 2 174–3 789 |
| 10 missed | 3 154–4 241 | 26–34 | 680–1 764 | 1 212–2 428 |

At `RED_MIN_SAT = 40` the red on these decks breaks up. The apron path's "red above the band" and
far-edge fit then fail, so no candidate passes the regulation-PnP gate.

Per throw, before. "no candidate passed PnP" stands for "No red deck with a dark rim or apron large
enough to be a regulation board was found."

| trial | athlete | clip | flight | release | board | conf | hole (in) | board reasons | phi (°) | contact kind/state | per-throw HFOV (°) | miss class |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 19A9640F | P1 | testsep17 - 1.mov | accepted | 227 | found | 0.89 | 0.9 | — | 2.4 | deck/measured | 55.0 estimated | — |
| 44CA1279 | P1 | testsep17 - 2.mov | accepted | 168 | found | 0.88 | 1.1 | — | 3.2 | deck/measured | 61.7 measured | — |
| 80823323 | P1 | testsep17 - 3.mov | accepted | 206 | found | 0.90 | 0.8 | — | 2.0 | deck/measured | 58.7 measured | — |
| 3B3DC0EC | P1 | testsep17 - 4.mov | accepted | 200 | found | 0.90 | 1.3 | — | 3.5 | deck/measured | 56.6 measured | — |
| 3D93058B | P1 | testsep17 - 5.mov | needs_review | 13 | found | 0.89 | 1.0 | — | 3.1 | lost_in_flight/unavailable | — | — |
| 41A04DAC | P1 | testsep17 - 6.mov | accepted | 156 | found | 0.89 | 0.8 | — | 3.3 | deck/measured | 58.8 measured | — |
| 1500778E | P1 | testsep17 - 7.mov | accepted | 205 | found | 0.83 | 1.5 | — | 6.2 | floor/measured | 55.0 estimated | — |
| F0E77C58 | P1 | testsep17 - 8.mov | accepted | 178 | not_found | 0.00 | — | no candidate passed PnP | — | unknown/unverified | — | pale deck (threshold) |
| D7FAAA60 | P1 | testsep17 - 9.mov | needs_review | 294 | not_found | 0.31 | 6.2 | conf 0.31 < 0.75 | — | unknown/unverified | — | pale deck (threshold) |
| D4FF5A49 | P2 | testsep17 - 10.mov | accepted | 194 | found | 0.89 | 1.4 | — | 2.0 | floor/measured | 69.2 measured | — |
| 126CCAD1 | P2 | testsep17 - 11.mov | accepted | 118 | found | 0.91 | 1.8 | — | 2.8 | floor/measured | 62.3 measured | — |
| 105B9972 | P2 | testsep17 - 12.mov | accepted | 159 | found | 0.91 | 1.5 | — | 1.7 | floor/measured | 55.5 measured | — |
| DB5A8186 | P2 | testsep17 - 13.mov | accepted | 106 | found | 0.90 | 1.5 | — | 0.6 | lost_in_flight/unavailable | 59.8 measured | — |
| EFFA8D86 | P2 | testsep17 - 14.mov | needs_review | 83 | found | 0.91 | 1.6 | — | 0.8 | lost_in_flight/unavailable | — | — |
| 5B5C77D7 | P2 | testsep17 - 15.mov | accepted | 628 | found | 0.91 | 1.9 | — | 1.0 | floor/measured | 60.3 measured | — |
| 6BD2EE8F | P3 | testsep17 - 16.mov | accepted | 133 | found | 0.90 | 1.1 | — | 5.1 | lost_in_flight/unavailable | 55.3 measured | — |
| 14A6C444 | P3 | testsep17 - 17.mov | needs_review | 192 | found | 0.90 | 2.5 | — | 4.4 | floor/measured | — | — |
| 3B1EF3CA | P3 | testsep17 - 18.mov | accepted | 190 | found | 0.90 | 2.4 | — | 5.8 | deck/measured | 55.0 estimated | — |
| 08541449 | P3 | testsep17 - 19.mov | accepted | 50 | not_found | 0.00 | — | no candidate passed PnP | — | unknown/unverified | — | pale deck (threshold) |
| DE7F5B7D | P3 | testsep17 - 20.mov | accepted | 246 | not_found | 0.00 | — | no candidate passed PnP | — | unknown/unverified | — | pale deck (threshold) |
| AA7AC4A3 | P3 | testsep17 - 21.mov | accepted | 39 | not_found | 0.00 | — | no candidate passed PnP | — | unknown/unverified | — | pale deck (threshold) |
| A21B263C | P3 | testsep17 - 22.mov | accepted | 93 | not_found | 0.00 | — | no candidate passed PnP | — | unknown/unverified | — | pale deck (threshold) |
| E0D8F3B9 | P3 | testsep17 - 23.mov | accepted | 40 | not_found | 0.00 | — | no candidate passed PnP | — | unknown/unverified | — | pale deck (threshold) |
| BE2292C2 | P3 | testsep17 - 24.mov | needs_review | 28 | not_found | 0.00 | — | no candidate passed PnP | — | unknown/unavailable | — | pale deck (threshold) |
| 8D96BCAF | P3 | testsep17 - 25.mov | accepted | 83 | not_found | 0.00 | — | no candidate passed PnP | — | unknown/unverified | — | pale deck (threshold) |
| 62AA318D | P3 | testsep17 - 26.mov | accepted | 103 | not_found | 0.00 | — | no candidate passed PnP | — | unknown/unverified | — | pale deck (threshold) |

### Threshold sweep (evidence for the fix)

`detect_board` was run on the 26 stored plates at S ≥ 40/35/30/25/20/15:

- With both candidate paths:
  - The missed boards appear at S ≥ 30 or 25.
  - At **S ≥ 20 a rim candidate on a pink TV-screen banner** scored 1.0 and beat the real board on
    3D93058B, giving a wrong "found" 810 px away. S ≥ 15 did the same on D7FAAA60.
- With the apron path only, no wrong "found" appeared on any plate down to S ≥ 10. At the cascade's
  thresholds (S ≥ 30, 25) every found quad lay within 5 px of the same board's quad at S ≥ 40 (within
  7 px down to S ≥ 10).
- The result is not monotonic in S. For example, BE2292C2 is found at 30, rejected at 25 by the
  hole/PnP gates and found again at 20. This is why the fix is a cascade and not one lower
  threshold.

## Task 8c, Part B — after (commits 8954b09 + 30d755c, fresh two-pass run)

The fix is a relaxed pass. `detect_board` keeps the standard pass (S ≥ 40, rim and apron paths).
Only if that finds nothing does it retry the **apron path only** at S ≥ 30, then at S ≥ 25
(`RELAXED_RED_MIN_SATS`). The retries use the same PnP, hole and observed-front-corner gates, and
the result reports `red_min_sat`.

| | before | after |
|---|---|---|
| boards found | 16 / 26 | **26 / 26** (10 by the relaxed pass) |
| boards found among accepted flights | 13 / 21 | **21 / 21** |
| Player 3 boards found | 3 / 11 | **11 / 11** |
| per-throw HFOV measured | 10 | 14 |
| scale status "measured" (pass 2): P1 / P2 / P3 | 6 / 5 / 0 | 7 / 5 / 9 |

Every final quad was checked by eye and lies on the deck. The QA montage is
`/private/tmp/claude-501/board-qa/8c/after_all26.png` (ephemeral scratch outside the repo; it may
no longer exist).

| trial | athlete | clip | flight | release | board | min S | conf | hole (in) | board reasons | phi (°) | contact kind/state | per-throw HFOV (°) | HFOV used (°), scale |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 19A9640F | P1 | testsep17 - 1.mov | accepted | 227 | found | 40 | 0.89 | 0.9 | — | 2.4 | deck/measured | 55.0 estimated | 58.8 measured |
| 44CA1279 | P1 | testsep17 - 2.mov | accepted | 168 | found | 40 | 0.88 | 1.1 | — | 3.2 | deck/measured | 61.7 measured | 58.8 measured |
| 80823323 | P1 | testsep17 - 3.mov | accepted | 206 | found | 40 | 0.90 | 0.8 | — | 2.0 | deck/measured | 58.7 measured | 58.8 measured |
| 3B3DC0EC | P1 | testsep17 - 4.mov | accepted | 200 | found | 40 | 0.90 | 1.3 | — | 3.5 | deck/measured | 56.6 measured | 58.8 measured |
| 3D93058B | P1 | testsep17 - 5.mov | needs_review | 13 | found | 40 | 0.89 | 1.0 | — | 3.1 | lost_in_flight/unavailable | —  | — unavailable |
| 41A04DAC | P1 | testsep17 - 6.mov | accepted | 156 | found | 40 | 0.89 | 0.8 | — | 3.3 | deck/measured | 58.8 measured | 58.8 measured |
| 1500778E | P1 | testsep17 - 7.mov | accepted | 205 | found | 40 | 0.83 | 1.5 | — | 6.2 | floor/measured | 55.0 estimated | 58.8 measured |
| F0E77C58 | P1 | testsep17 - 8.mov | accepted | 178 | found | 30 | 0.86 | 1.6 | — | 3.4 | floor/measured | 55.0 estimated | 58.8 measured |
| D7FAAA60 | P1 | testsep17 - 9.mov | needs_review | 294 | found | 30 | 0.90 | 1.8 | — | 0.8 | floor/measured | —  | — unavailable |
| D4FF5A49 | P2 | testsep17 - 10.mov | accepted | 194 | found | 40 | 0.89 | 1.4 | — | 2.0 | floor/measured | 69.2 measured | 60.3 measured |
| 126CCAD1 | P2 | testsep17 - 11.mov | accepted | 118 | found | 40 | 0.91 | 1.8 | — | 2.8 | floor/measured | 62.3 measured | 60.3 measured |
| 105B9972 | P2 | testsep17 - 12.mov | accepted | 159 | found | 40 | 0.91 | 1.5 | — | 1.7 | floor/measured | 55.5 measured | 60.3 measured |
| DB5A8186 | P2 | testsep17 - 13.mov | accepted | 106 | found | 40 | 0.90 | 1.5 | — | 0.6 | lost_in_flight/unavailable | 59.8 measured | 60.3 measured |
| EFFA8D86 | P2 | testsep17 - 14.mov | needs_review | 83 | found | 40 | 0.91 | 1.6 | — | 0.8 | lost_in_flight/unavailable | —  | — unavailable |
| 5B5C77D7 | P2 | testsep17 - 15.mov | accepted | 628 | found | 40 | 0.91 | 1.9 | — | 1.0 | floor/measured | 60.3 measured | 60.3 measured |
| 6BD2EE8F | P3 | testsep17 - 16.mov | accepted | 133 | found | 40 | 0.90 | 1.1 | — | 5.1 | lost_in_flight/unavailable | 55.3 measured | 56.6 measured |
| 14A6C444 | P3 | testsep17 - 17.mov | needs_review | 192 | found | 40 | 0.90 | 2.5 | — | 4.4 | floor/measured | —  | — unavailable |
| 3B1EF3CA | P3 | testsep17 - 18.mov | accepted | 190 | found | 40 | 0.90 | 2.4 | — | 5.8 | deck/measured | 55.0 estimated | 56.6 measured |
| 08541449 | P3 | testsep17 - 19.mov | accepted | 50 | found | 25 | 0.89 | 1.5 | — | 6.0 | deck/measured | 56.6 measured | 56.6 measured |
| DE7F5B7D | P3 | testsep17 - 20.mov | accepted | 246 | found | 30 | 0.82 | 2.3 | — | 6.1 | floor/measured | 55.0 estimated | 56.6 measured |
| AA7AC4A3 | P3 | testsep17 - 21.mov | accepted | 39 | found | 25 | 0.91 | 1.2 | — | 6.8 | deck/measured | 57.6 measured | 56.6 measured |
| A21B263C | P3 | testsep17 - 22.mov | accepted | 93 | found | 30 | 0.87 | 1.5 | — | 7.4 | lost_in_flight/unavailable | 55.1 measured | 56.6 measured |
| E0D8F3B9 | P3 | testsep17 - 23.mov | accepted | 40 | found | 30 | 0.85 | 1.9 | — | 5.7 | deck/measured | 55.0 estimated | 56.6 measured |
| BE2292C2 | P3 | testsep17 - 24.mov | needs_review | 28 | found | 30 | 0.84 | 1.9 | — | 7.9 | lost_in_flight/unavailable | —  | — unavailable |
| 8D96BCAF | P3 | testsep17 - 25.mov | accepted | 83 | found | 30 | 0.85 | 2.5 | — | 6.0 | lost_in_flight/unavailable | 55.0 estimated | 56.6 measured |
| 62AA318D | P3 | testsep17 - 26.mov | accepted | 103 | found | 30 | 0.85 | 2.1 | — | 6.1 | floor/measured | 57.2 measured | 56.6 measured |

The 16 boards found before are unchanged: the standard pass still returns them, within 2 px of
their earlier quads.

Borderline cases:
- The relaxed threshold that succeeds can differ between the in-memory plate and its JPEG copy
  (AA7AC4A3: 25 vs 30; DE7F5B7D: 30 vs 25). The quads agree within a few px either way.
- The 5 "unavailable" scales are needs_review flights (no accepted flight to calibrate from), not
  board misses.

## Task 8c, Part C — library-wide field-of-view fallback

A session can have fewer than `MIN_SESSION_THROWS` measured per-throw calibrations. Its
`camera.json` then comes from the pool of every measured throw in the same library run
(`source: "library_median_gravity_fov"`). It counts as "measured" only when that pool meets the
n ≥ 3 and IQR ≤ 6° rules. The reason states that it assumes the same camera and zoom in every
session.

| pool | n | median HFOV | IQR | status |
|---|---|---|---|---|
| Player 1 session | 4 | 58.78° | 1.34° | measured |
| Player 2 session | 5 | 60.30° | 2.54° | measured |
| Player 3 session | 5 | 56.58° | 1.95° | measured |
| **library (all 14 measured throws)** | 14 | **58.19°** | **3.57°** | measured (outlier D4FF5A49, 69.2°) |
| library, Task-8b state (10 measured) | 10 | 59.29° | 4.19° | measured |

After Part B every session has at least 3 measured throws, so the fallback is not triggered on the
pilot data. Under the Task-8b detection it would have given Player 3 59.3° ("measured") instead of
an "estimated" single-throw 55.3°.


## Release onset audit (Task 9b)

Every body timing (shoulder, elbow and wrist peaks) and the release-timing sensitivity are measured relative to the detected release frame. Task 9 raised a concern. On most throws, the hand-point direction matched the bag's release angle 3–5 frames *before* the detected release, which suggested release was being detected late.

This audit checks the detected release against the video itself, frame by frame.

**Tool.** `scripts/release_audit.py` reads a `regression_check.py` scratch directory. For every accepted flight it writes:
- a contact sheet of frames release−8 … release+3, as 2× crops centred on the hand point. Each crop marks:
  - the wrist landmark;
  - the hand point (wrist + 0.34 arm along the forearm);
  - the bag detection, or the flight traced backwards before the first detection;
- the per-throw table below.

It is also given visually judged release frames, passed as `--visual visual.json`. With these it reports method − visual for each method.

```
PYTHONPATH=python .venv/bin/python scripts/release_audit.py --analyses /tmp/regression \
    --sheets /tmp/release-audit/sheets --visual docs/release_audit_visual.json --output audit.json
```

**Visual release** (`docs/release_audit_visual.json`). For each throw I recorded the first frame where the bag has visibly separated from the fingers. This was done by looking at all 21 sheets of accepted pilot throws (Task 8c state, detector v11c).
- Every judgement is a 2-frame range, [last frame the fingertips still touch, first frame with a clear gap].
- Motion blur at the fingertips makes it impossible to tell which of the two adjacent frames is the separation.
- Errors count as 0 inside the range; otherwise they are the signed distance to the nearest end.

**Methods compared.**
- R: detected release, i.e. the first frame of the flight fit.
- C: the backward-flight/wrist cue (`release_check`).
- A: the hand-angle match, i.e. the frame in R−8 … R where the hand-point velocity direction (board plane) is closest to the bag's fitted release angle.

| throw | R | C | A | visual | R−V | C−V | A−V |
|---|---|---|---|---|---|---|---|
| 08541449 | 50 | 46 | 45 | 48–49 | +1 | -2 | -3 |
| 105B9972 | 159 | 156 | 155 | 158–159 | +0 | -2 | -3 |
| 126CCAD1 | 118 | 118 | 118 | 121–122 | -3 | -3 | -3 |
| 1500778E | 205 | 202 | 201 | 203–204 | +1 | -1 | -2 |
| 19A9640F | 227 | 224 | 223 | 226–227 | +0 | -2 | -3 |
| 3B1EF3CA | 190 | 190 | 189 | 192–193 | -2 | -2 | -3 |
| 3B3DC0EC | 200 | 196 | 196 | 199–200 | +0 | -3 | -3 |
| 41A04DAC | 156 | 154 | 153 | 156–157 | +0 | -2 | -3 |
| 44CA1279 | 168 | 166 | 165 | 168–169 | +0 | -2 | -3 |
| 5B5C77D7 | 628 | 628 | 628 | 631–632 | -3 | -3 | -3 |
| 62AA318D | 103 | 99 | 97 | 102–103 | +0 | -3 | -5 |
| 6BD2EE8F | 133 | 132 | 130 | 133–134 | +0 | -1 | -3 |
| 80823323 | 206 | 202 | 202 | 205–206 | +0 | -3 | -3 |
| 8D96BCAF | 83 | 81 | 79 | 83–84 | +0 | -2 | -4 |
| A21B263C | 93 | 93 | 92 | 96–97 | -3 | -3 | -4 |
| AA7AC4A3 | 39 | 35 | 35 | 38–39 | +0 | -3 | -3 |
| D4FF5A49 | 194 | 194 | 194 | 197–198 | -3 | -3 | -3 |
| DB5A8186 | 106 | 104 | 104 | 107–108 | -1 | -3 | -3 |
| DE7F5B7D | 246 | 244 | 243 | 246–247 | +0 | -2 | -3 |
| E0D8F3B9 | 40 | 37 | 37 | 39–40 | +0 | -2 | -2 |
| F0E77C58 | 178 | 175 | 174 | 177–178 | +0 | -2 | -3 |

| method | mean (frames) | SD | within ±1 of the visual range | vs the clear-gap frame: mean, within ±1 |
|---|---|---|---|---|
| R: first flight frame (v11c) | −0.62 | 1.32 | 16/21 | −1.14, 15/21 |
| C: backward flight meets wrist | −2.33 | 0.66 | 2/21 | −3.33, 0/21 |
| A: hand-angle match | −3.10 | 0.62 | 0/21 | −4.10, 0/21 |

**Findings.**

1. **Release is not detected late.**
   - It is never later than the visual range by more than 1 frame (+1 on 2 throws, and both of those are ambiguous by a single frame).
   - It is **early by 2–3 frames on 5 of 21 throws**: 126CCAD1, 3B1EF3CA, 5B5C77D7, A21B263C and D4FF5A49.
   - On those 5, the sheets show the bag still wrapped in the fingers at R.
   - The cause: the bag's last in-hand frames lie on nearly the same arc as its free flight, so the flight fit accepted them. The in-hand gate (bag within 0.45 arm lengths of the wrist) was applied only while extending the flight backwards, never to the fit's own first points.
2. **The hand-point model is wrong near release (Task 9's alternative explanation).**
   - At the visually judged release frame (the clear-gap frame), the hand-point direction is **27–47° steeper than the bag's fitted angle on all 21 throws** (median 38°).
   - The hand-angle match A lies 3–5 frames *before* the visual release on every throw.
   - So the bag does not leave along the rigid hand point's path. In the last ~50–80 ms the bag leaves along a shallower line, while the tracked hand point is already turning upward into the follow-through.
   - Two causes cannot be separated with body-only landmarks:
     - finger and wrist action, which the model does not capture;
     - lag of the 6 Hz-filtered wrist in these motion-blurred frames. On the sheets, the wrist ring visibly trails the real wrist after release.
   - The rigid-offset hand point cannot stand in for the bag's path at release.
3. **Conclusion: (b), the hand-point model is wrong near release, not (a).**
   - In addition there is an early-release failure on 5/21 throws, which is the opposite of the suspected late bias.
   - The 4/21 throws where Task 9's timing sensitivity was "available" are 4 of those 5 early throws. Their hand rates were read 2–3 frames before the bag actually left the hand.

### Correction (Task 9b, part B): release = first flight centroid beyond the hand

**Rule.** Release is the first refined bag centroid in the chosen flight that lies more than `IN_HAND_ARM_LENGTHS` (0.45 arm lengths) from the wrist. Frames the segmentation re-acquired between detections are included.
- This is the same in-hand radius the backward extension already used. The constant is not re-tuned: 0.40 and 0.45 score the same, and 0.50 scores 21/21 within ±1 but with only 17 exact.
- Earlier flight points were still in the hand, so they are dropped, and the parabola and its RMS are refitted on the remaining detections.
- The detector revision is `auto_motion_parabola_v12b_release_onset_status`.
- `auto_flight.json` → `release_onset` records the dropped frames and a `status`:
  - `applied`: frames were dropped.
  - `no_in_hand_points`: the flight already starts beyond the hand.
  - `no_wrist`: the check could not run.
  - `capped_min_inliers`: the bag was still in the hand, but dropping more frames would leave fewer than 12 detections.
- An accepted automatic release whose check is `no_wrist` or `capped_min_inliers` is graded at most WARNING and carries a release warning.
- The raw detection blob, which marks the bag's leading edge, would have scored 20/21. The centroid is used instead.

**Fresh two-pass run with the final code** (Task 9b fix round 1). 21 flights are accepted, as before. On the pilot data the in-hand check reports:
- `applied` on 8 flights: 7 accepted, plus 3D93058B, which needs review;
- `no_in_hand_points` on 16;
- `capped_min_inliers` on 2 flights, BE2292C2 and EFFA8D86, both short needs-review flights with 12 and 9 detections;
- `no_wrist` on none.

| method | mean vs visual range | SD | within ±1 |
|---|---|---|---|
| R before | −0.62 | 1.32 | 16/21 |
| **R after** | **+0.10** | **0.30** | **21/21** (19 exact) |
| C (backward flight meets the wrist), after | −2.19 | 0.60 | 2/21 |

Before → after, per accepted throw.
- "Window" is the release window, from cue C to release R.
- Grades use the final rules on both sides: GOOD requires a window of 4 frames or fewer (see below).
- Chain timings are in ms relative to release. "—" means unavailable.

| throw | release b→a | onset check | window b→a | release grade b→a | shoulder pk ms | elbow pk ms | wrist pk ms | hand angle ° | TS in/10ms |
|---|---|---|---|---|---|---|---|---|---|
| 08541449 | 50 → 50 (acc) | no_in_hand_points | 46–50 → 46–50 | WARNING → GOOD | -83 → -83 | -100 → -100 | -50 → -50 | 74 → 74 | — → — |
| 105B9972 | 159 → 159 (acc) | no_in_hand_points | 156–159 → 156–159 | GOOD → GOOD | 67 → 67 | -133 → -133 | -83 → -83 | 68 → 68 | — → — |
| 126CCAD1 | 118 → 122 (acc) | applied | 118–118 → 119–122 | GOOD → GOOD | 83 → 17 | -83 → -150 | 0 → -67 | 39 → 81 | — → — |
| 1500778E | 205 → 205 (acc) | no_in_hand_points | 202–205 → 202–205 | GOOD → GOOD | 33 → 33 | 0 → 0 | -67 → -67 | 94 → 94 | — → — |
| 19A9640F | 227 → 227 (acc) | no_in_hand_points | 224–227 → 224–227 | GOOD → GOOD | 17 → 17 | 100 → — | -67 → -67 | 75 → 75 | — → — |
| 3B1EF3CA | 190 → 193 (acc) | applied | 190–190 → 190–193 | GOOD → GOOD | -50 → -100 | -117 → -167 | 0 → -50 | 48 → 73 | 7.6 (est) → — |
| 3B3DC0EC | 200 → 200 (acc) | no_in_hand_points | 196–200 → 196–200 | WARNING → GOOD | -33 → -33 | -33 → -33 | -67 → -67 | 81 → 81 | — → — |
| 41A04DAC | 156 → 156 (acc) | no_in_hand_points | 154–156 → 154–156 | GOOD → GOOD | -17 → -17 | -167 → -167 | -50 → -50 | 71 → 71 | — → — |
| 44CA1279 | 168 → 168 (acc) | no_in_hand_points | 166–168 → 166–168 | GOOD → GOOD | -17 → -17 | -150 → -150 | -50 → -50 | 72 → 72 | — → — |
| 5B5C77D7 | 628 → 632 (acc) | applied | 628–628 → 629–632 | GOOD → GOOD | -17 → -83 | -150 → — | -33 → -100 | 63 → 103 | -33.0 (est) → — |
| 62AA318D | 103 → 103 (acc) | no_in_hand_points | 99–103 → 99–103 | WARNING → GOOD | -117 → -117 | -183 → -183 | -100 → -100 | 95 → 95 | — → — |
| 6BD2EE8F | 133 → 133 (acc) | no_in_hand_points | 132–133 → 132–133 | GOOD → GOOD | -83 → -83 | -133 → -133 | -33 → -33 | 68 → 68 | — → — |
| 80823323 | 206 → 206 (acc) | no_in_hand_points | 202–206 → 202–206 | WARNING → GOOD | 17 → 17 | -150 → -150 | -67 → -67 | 82 → 82 | — → — |
| 8D96BCAF | 83 → 83 (acc) | no_in_hand_points | 81–83 → 81–83 | GOOD → GOOD | 0 → 0 | -234 → -234 | -50 → -50 | 82 → 82 | — → — |
| A21B263C | 93 → 96 (acc) | applied | 93–93 → 93–96 | GOOD → GOOD | -50 → -100 | -50 → -100 | -33 → -83 | 47 → 76 | -4.7 (est) → — |
| AA7AC4A3 | 39 → 39 (acc) | no_in_hand_points | 35–39 → 35–39 | WARNING → GOOD | -67 → -67 | -83 → -83 | -50 → -50 | 71 → 71 | — → — |
| D4FF5A49 | 194 → 198 (acc) | applied | 194–194 → 195–198 | GOOD → GOOD | -17 → -83 | -83 → -150 | -50 → -117 | 43 → 79 | -23.9 (est) → — |
| DB5A8186 | 106 → 107 (acc) | applied | 104–106 → 104–107 | GOOD → GOOD | -67 → -83 | -133 → — | -67 → -83 | 64 → 75 | — → — |
| DE7F5B7D | 246 → 247 (acc) | applied | 244–246 → 244–247 | GOOD → GOOD | -67 → -83 | -50 → -67 | -33 → -50 | 52 → 59 | — → — |
| E0D8F3B9 | 40 → 40 (acc) | no_in_hand_points | 37–40 → 37–40 | GOOD → GOOD | -33 → -33 | -100 → -100 | -50 → -50 | 51 → 51 | — → — |
| F0E77C58 | 178 → 178 (acc) | no_in_hand_points | 175–178 → 175–178 | GOOD → GOOD | 33 → 33 | 83 → 83 | -83 → -83 | 104 → 104 | — → — |

**Effects of the correction.**
- **Release moved on 7 throws:**
  - by +3 to +4 frames on the 5 early throws: 126CCAD1, 3B1EF3CA, 5B5C77D7, A21B263C and D4FF5A49;
  - by +1 frame on DB5A8186 and DE7F5B7D.
- **Body timings moved only on those throws.**
  - Shoulder and wrist peaks shift 17–67 ms earlier relative to release.
  - Elbow peaks that stay inside the window shift 17–67 ms earlier as well.
- **Elbow peaks on the window edge are now unavailable.**
  - With the later release, the elbow maximum on 5B5C77D7 and DB5A8186 fell exactly on the end of the search window (release + 0.1 s).
  - The same was already true of 19A9640F before the correction.
  - A maximum on either edge of the search window is not a peak. `chain.py` and `timing.py` now report it as unavailable, with the reason "peak at the edge of the search window", and leave it out of the peak sequence.
- **Release window grade.**
  - The backward-flight/wrist cue is early by construction. After the correction it is 1–4 frames before release on every throw, 4 frames on five of them.
  - So GOOD is now a window of 4 frames or fewer (was 3), and WARNING is 5–6 frames.
  - This regrades five correct releases from WARNING to GOOD: 08541449, 3B3DC0EC, 62AA318D, 80823323 and AA7AC4A3.
- **Timing sensitivity is available on 0 of 21 throws (was 4).**
  - The 4 earlier values were read 2–3 frames before the bag had actually left the hand.
  - At the true release, the hand path is 27–47° steeper than the bag on every throw, so the existing 10° gate withholds the value.
  - This is finding (b). The rigid hand point cannot provide the bag's release-rate derivatives, and this has not been fixed here. Using the bag's own post-release path would give ballistic rates, not the rates of a later release.
  - Timing sensitivity therefore needs a direct measure of the hand/bag path in the last frames of contact, for example a hand keypoint model or bag tracking while in hand.
