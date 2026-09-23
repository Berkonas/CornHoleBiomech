# Light engineering validation

Written 23 September 2026. This replaces a full frame-annotation study as the project's
working validation. The full workflow (`docs/BAG_TRACKING_VALIDATION.md`) stays available if
a real problem needs measuring.

The question is not "what is the tracker's error to the pixel?" but "is the tracking good
enough that coaching conclusions don't depend on tracking errors?" Three kinds of
evidence answer it, each with stated limits.

## 1. Internal consistency (all 26 pilot clips, automatic)

| Evidence | Result | What it shows | What it cannot show |
|---|---|---|---|
| Flight frames with a bag position | median 100% (worst 96%) of accepted flights | tracking rarely drops out | whether the position is right |
| Frame-to-frame jitter (third-difference σ) | median 0.49 px, bag ≈ 25 px across | positions are smooth relative to bag size | a smooth path can still be offset |
| Flight-filter noise model | mean normalised innovation ≈ 2.0 | the noise model matches the data | — |
| Outlier rejections | 0–10 per flight, kept in raw data | jumps are caught, not hidden | — |
| Drag-free model residual | 3–17 px in-sample | detections follow one smooth arc | perspective vs drag (not separable) |
| Two release cues (first free-flight frame; backward flight meets wrist) | 0–3 frames apart on 17/20 accepted flights (4–6 on the other 3); 5–12 on flights already needing review | release is bracketed; disagreement flags bad flights | which cue is exactly right |
| Physical plausibility | apparent gravity scale gives release speeds 5.4–10.7 m/s, heights 0.5–1.4 m | values are in the expected range for underhand throws | exact metres (single camera) |

## 2. Visual spot check (6 clips, 2 per player, key events only)

`scripts/spot_check.py` draws the automatic markers on the video. It shows a release filmstrip
(−3 … +3 frames) plus the apex, first-contact and final-rest frames. Reviewing one clip takes
about a minute. This first pass was reviewed by the engineering assistant, not a blinded
human rater; a team member should look over the same sheets.

| Clip | Release frame | Apex | First contact | Final rest |
|---|---|---|---|---|
| 1 | correct (±1) | bag too small to confirm | bag too small to confirm | correct (floor, beside board leg) |
| 2 | correct (±1) | on bag | bag not visible in crop | **wrong**: marker on the board edge, bag on the floor |
| 10 | correct (±1) | on bag | on bag (floor, short) | correct |
| 11 | correct (±1) | on bag | on bag | not found (reported as not found) |
| 18 | correct (±1) | on bag | on bag (board) | correct (board) |
| 26 | correct (±1) | on bag | on bag (floor) | **wrong**: slid next to an earlier bag; marker between them |

**Reading:**
- **Release:** judged correct within ±1 frame (±17 ms) on 6/6 clips. At 60 fps the "true" release
  frame is itself ambiguous by about a frame.
- **Flight events (apex, first contact):** on the bag wherever the bag is visible at crop scale.
- **Final rest:** correct on 3 of 5 detected rests. It fails when another bag or a board edge
  is nearby. The app therefore labels final rest as an automatic estimate to confirm in the
  video. Scoring (hole / board / miss) stays a one-click human entry.

## 3. Sensitivity of release measurements to tracking choices

The regression check (`scripts/regression_check.py`) shows how much release values move when
only the bag-centre method changes (blob → silhouette):

| Release value | Median change | Largest change |
|---|---|---|
| Angle | 0.8° | 3.5° |
| Speed | 0.08 m/s | 0.27 m/s |
| Height | 1.6 cm | 9.5 cm |

These are of the same order as the noise floors used by the analysis (3°, 0.15 m/s, 3 cm).
Differences between an athlete's throws smaller than that are never reported as meaningful.

## Conclusion and limits

- **Good enough to coach from:**
  - release timing (±1 frame);
  - release angle and speed differences above the noise floors;
  - flight events;
  - body angles that pass the per-throw reliability rules.
- **Not claimed:**
  - absolute metres to better than a few percent (gravity scale only, WARNING-level calibration);
  - pixel-level centroid accuracy;
  - final rest without a glance at the video;
  - anything about the hole (a bag lost after contact is "not found", never "in the hole").
- **Upgrade path if a problem appears:** the annotation benchmark (`bag-annotation-frames` /
  `bag-benchmark`) can measure exactly the failing phase, and heavier trackers (SAM 2,
  CoTracker3) would be compared only on that phase.
