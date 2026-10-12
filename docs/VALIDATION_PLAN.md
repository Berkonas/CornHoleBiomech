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

## Known limits that validation cannot remove

Two 2D cameras without a shared calibration: side measures are in the throw plane, front measures are image-plane
2D, and the 3D flight is a physics-constrained fit, not a stereo reconstruction. The side field of view on the first
camera position is estimated (session spread 7.1° IQR), so on 45 of 92 throws release speed comes from the flight's
own gravity scale rather than the board-plane fit. Four athletes and 20–28 throws each support within-athlete
descriptions, not general claims.
