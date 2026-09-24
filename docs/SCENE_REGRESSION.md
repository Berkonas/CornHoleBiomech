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
