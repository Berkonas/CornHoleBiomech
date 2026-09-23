# Bag-tracking validation

This turns "the path looks right" into measured error. Code: `python/cornhole_biomech/bag_validation.py`.
Tests: `tests/test_bag_validation.py`.

## 1. Export frames (≈19 per clip)

Analyse the clips first, so each has an `auto_flight.json`. Then:

```
PYTHONPATH=python .venv/bin/python -m cornhole_biomech bag-annotation-frames \
    --library "~/Documents/Cornhole Pilot Library" --output ~/Desktop/"Cornhole Bag Validation"
```

Frames come from seven phases of each automatic flight, two per phase:

- **in_hand:** up to 0.3 s before release.
- **release:** release ±1 frame. The automatic release frame is always included.
- **early_flight:** high velocity, most motion blur.
- **apex**
- **descent**
- **near_board**
- **landing:** first contact to +3 frames. The automatic first-contact frame is always included.
- **final_rest:** last 0.25 s of the clip, at least 0.5 s after contact (where the bag ends up).
- **weak_detection:** flight frames where the tracker was least sure: no mask found, re-acquired in a gap, or
  rejected by the flight filter.

The pilot set (26 clips, 505 frames, 1.3 GB) is already exported to `~/Desktop/Cornhole Bag Validation`, with a
`README.txt` listing each clip's folder and the 5 clips for the second rater (clips 1, 8, 10, 18, 22: all three
players, easy and hard throws).

The choice is deterministic (fixed seed), so a second rater gets the same frames. PNGs are full resolution with no
overlays. Each clip folder also has `bag_validation_plan.json` with the phase labels. **Raters should not open it.**
Full-resolution PNGs take ~40 MB per clip.

## 2. Mark the bag

1. Open `tools/annotator.html` in a browser.
2. Load all PNGs of one clip plus its `annotation_manifest.json`. The manifest puts the tool in bag-only mode.
3. Click the **centre of the bag's visible outline**, not the brightest spot or the leading edge. If the bag is hidden
   by the hand or out of frame, press **N** (not visible).
4. Step through the original video to find the **release** frame and the **first-contact** frame (bag first touches
   board or ground), and type both in. Do this before looking at any automatic event.

   **Definition of release:** the first frame where the bag has clearly separated from the hand and is in
   independent flight. When that is ambiguous (blur, hand overlapping the bag), also enter the earliest and latest
   plausible frames. The automatic release is then also judged against that window, not only against one frame.
5. Download the JSON and save it **into that clip's folder** (the file name starts with `annotation_`).

A second rater on at least 5 clips gives the rater-vs-rater floor: automatic error below that floor cannot be
demonstrated.

## 3. Score

```
PYTHONPATH=python .venv/bin/python -m cornhole_biomech bag-benchmark \
    --frames ~/Desktop/"Cornhole Bag Validation" --output ~/Desktop/bag-benchmark.json [--rater AB]
```

The alphabetically first rater (or `--rater`) is the reference. Every other rater on the same clip is scored
against the reference exactly like a tracker: this is the **human floor**. The output puts them side by side:

- `trackers`: pooled over all clips from every individual frame error: mean, median, RMSE, 95th percentile,
  worst case, success rates, lost-track events, longest gap, and the same statistics per phase.
- `human_floor`: the same statistics for rater vs rater, plus release/contact frame differences between raters and
  the number of frames where the raters disagreed on visibility.
- `release_timing`, `first_contact_timing`: automatic − reference frames: mean signed, median and max absolute,
  number within ±1 frame, and number inside the rater's plausible window.
- `landing_position_error_px` per tracker, and `per_clip` detail.

The numbers are never combined into one accuracy score.

**Reading rule.** Tracker error can only be demonstrated down to the human floor. If raters disagree by ~3 px and the
tracker is 2 px from the reference, the data cannot say the tracker is accurate to 2 px, only that it is within human
labelling uncertainty. A tracker is worth replacing only in a phase where its error is clearly *above* the floor.

For each tracker output, it reports:

- **detection:** the raw motion-blob centroid.
- **mask:** the silhouette centroid from `bag_segment.py`.
- **filtered:** the Kalman/RTS path from `bag_filter.py`.
- **effective:** what the analysis used, including manual corrections.

| Metric | Definition |
|---|---|
| Centroid error | e_i = √((x_auto − x_manual)² + (y_auto − y_manual)²), px |
| MAE / RMSE | (1/N) Σ e_i  /  √((1/N) Σ e_i²), px; also median, 95th percentile, max, x/y bias |
| Success rate | share of visible marks with an estimate within one bag radius (√(median mask area / π)); overall and inside the tracker's flight span |
| Per-phase MAE / RMSE | the same errors split by phase |
| Lost-track events / longest gap | runs of frames with no estimate between automatic release and contact |
| Release / contact error | automatic − rater frame, in frames and ms |
| Landing position error | error at the marked frame nearest (±2) the rater's first contact |
| Runtime | tracker seconds per clip and frames per second |

Errors in cm are added only when a measured in-plane scale is given, and they hold only in the flight plane.

## 4. What to do with the result

- Replace the provisional thresholds in `quality.GRADE_RULES` and the noise floors in `performance.VARIABLES` with
  measured values: for example, the bag noise floor is about 2 × pooled RMSE.
- If a phase stays poor (typically release or near_board), that phase is where a heavier tracker (SAM 2, CoTracker3)
  is worth testing. Score it on these same frames.
- Report the pooled table in the course write-up's validation section, with the rater floor next to it.
