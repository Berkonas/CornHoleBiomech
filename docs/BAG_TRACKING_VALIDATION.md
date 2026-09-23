# Bag-tracking validation

This turns "the path looks right" into measured error. Code: `python/cornhole_biomech/bag_validation.py`.
Tests: `tests/test_bag_validation.py`.

## 1. Export frames (≈16 per clip)

Analyse the clips first, so each has an `auto_flight.json`. Then:

```
PYTHONPATH=python .venv/bin/python -m cornhole_biomech bag-annotation-frames \
    --library "~/Documents/Cornhole Pilot Library" --output ~/Desktop/bag-frames
```

Frames come from seven phases of each automatic flight, two per phase:

- **in_hand:** up to 0.3 s before release.
- **release:** release ±1 frame. The automatic release frame is always included.
- **early_flight:** high velocity, most motion blur.
- **apex**
- **descent**
- **near_board**
- **landing:** first contact to +3 frames. The automatic first-contact frame is always included.

The choice is deterministic (fixed seed), so a second rater gets the same frames. PNGs are full resolution with no
overlays. Each clip folder also has `bag_validation_plan.json` with the phase labels. **Raters should not open it.**
Full-resolution PNGs take ~40 MB per clip.

## 2. Mark the bag

1. Open `tools/annotator.html` in a browser.
2. Load all PNGs of one clip plus its `annotation_manifest.json`. The manifest puts the tool in bag-only mode.
3. Click the **centre of the bag's visible outline**, not the brightest spot or the leading edge. If the bag is hidden
   by the hand or out of frame, press **N** (not visible).
4. Step through the original video to find the **release** frame (first frame the bag is clearly out of the hand) and
   the **first-contact** frame (bag first touches board or ground). Type both in. Do this before looking at any
   automatic event.
5. Download the JSON and save it **into that clip's folder** (the file name starts with `annotation_`).

A second rater on at least 5 clips gives the rater-vs-rater floor: automatic error below that floor cannot be
demonstrated.

## 3. Score

```
PYTHONPATH=python .venv/bin/python -m cornhole_biomech bag-benchmark \
    --frames ~/Desktop/bag-frames --output ~/Desktop/bag-benchmark.json [--rater AB]
```

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
