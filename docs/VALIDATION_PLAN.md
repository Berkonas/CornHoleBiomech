# Real-video validation plan

The engine and app are development-complete for this stage, and all 92 throws were re-analysed on 2026-10-12
(`scripts/analyze_library.py --athlete all`). Nothing below has been validated yet; this plan says how to do it
before any result is presented as accurate. It uses the existing blinded tools (`tools/annotator.html`,
`annotation-frames`, `bag-annotation-frames`, `validate-tracking`, `bag-benchmark`).

## Sample

Stratified, not convenient: 20 throws, 5 per athlete, chosen before looking at the results, covering hole, board and
miss outcomes, at least 4 knocked-bag throws (including the 4 flagged `tracked_slide_turned`), the 15 throws without a
3D flight, and Player 3 (whose hand passes behind the body in the front view). One annotator per throw, blinded to the
engine's values; a second annotator on 5 throws for inter-rater agreement.

## What is compared

| Quantity | Reference | Acceptance (to agree before looking) |
|---|---|---|
| Release frame (side) | manual first frame the bag is free | median \|error\| ≤ 1 frame, 90 % ≤ 2 |
| First contact frame (side and front) | manual first frame on the deck | ≤ 1 frame on 90 % |
| Camera sync | clap and impact frames in both views | \|offset error\| ≤ 17 ms |
| Contact and rest on the board | manual points on the front deck | ≤ 2 in across, ≤ 3 in along |
| Outcome (hole / board / off) | the recorded result | ≥ 95 % agreement; every disagreement explained |
| Bag identity on knocked throws | manual | no silent wrong bag (flagged is acceptable) |
| Release speed and angle | manual bag centroids over the first 0.12 s, fitted the same way | speed within 0.15 m/s, angle within 3° |
| Joint landmarks at release (side and front) | manual landmarks | median error ≤ 4 px; elbow angle reported only where error ≤ its 10° floor |

Report bias (mean error), spread (SD), and limits of agreement (Bland–Altman) for each continuous quantity, per
athlete as well as pooled, because throws are nested in athletes.

## Decisions it feeds

- Noise floors in `docs/METRICS.md` that are still provisional are replaced by the measured spreads.
- `reliability.METRIC_TIERS` is re-checked: a per-throw metric whose measured error is larger than its throw-to-throw
  spread moves to *profile* or *advanced*.
- The knocked-bag turn threshold (45°) and the front contact rule are kept or changed according to the false-flag
  and miss rates.
- Only after these pass are the coaching associations (scored vs missed) reported to the client, with the sample
  sizes stated.

## Preliminary visual check (2026-10-12)

Not the blinded validation above: one reviewer (Claude, looking at the saved front-clip frames), no hand-marked
coordinates, no second rater. It is a sanity check that decided one rule change.

- **Knocked-bag flags (all 4 `tracked_slide_turned` throws).** 1 was a real knock (Player 1 take 3 throw 3: the bag
  landed on the pile by the hole and a bag ended under the board). 3 were false: the bag landed and slid off the
  side (Player 2 take 4 throw 4, Player 3 take 4 throw 2, Player 3 take 3 throw 4). The turn came from the landing
  itself and from the bag dropping off the edge, so the rule now only counts turns whose heading window lies wholly
  after first contact and whose next three points are still on the deck (`front_view.slide_turned_on_deck`); on the
  stored tracks this keeps the real knock and clears the three false flags.
- **Random sample of 8 throws (seeded shuffle).** The hole / board / off result matched what the frames show on 8 of 8
  (2 board, 1 hole, 5 off; one off throw left the front camera's view and was correctly not placed). On the 7 throws
  with a front contact frame, the bag was on or touching the deck in that frame and in the air one frame earlier on
  every throw (±1 frame at 30 fps; the exact touching frame is hard to call at this resolution).

## Known limits that validation cannot remove

Two 2D cameras without a shared calibration: side measures are in the throw plane, front measures are image-plane
2D, and the 3D flight is a physics-constrained fit, not a stereo reconstruction. The side field of view on the first
camera position is estimated (session spread 7.1° IQR), so on 45 of 92 throws release speed comes from the flight's
own gravity scale rather than the board-plane fit. Four athletes and 20–28 throws each support within-athlete
descriptions, not general claims.
