# Second-pass engineering and scientific audit

Written 23 September 2026 on branch `codex/second-pass-lab`. Evidence comes from the code and from running
it on the 26 pilot clips (17 Sep, hand-held iPhone, 1080p, ~60 fps). No hand-labelled ground truth exists
yet, so every accuracy statement below is either internal consistency or a visual check. Numbers marked
"pilot" are not validation results.

Guiding question: *which measurable features of an athlete's throwing mechanics and release are associated
with better or worse cornhole outcomes, within that athlete?*

## 1. How the pipeline works today

| Stage | Implementation | File |
|---|---|---|
| Pose | Sports2D 0.8.34 (RTMPose, HALPE-26), 2D image landmarks, confidence mask, gaps ≤ 3 frames interpolated, 4th-order zero-phase Butterworth at 6 Hz (Winter residual analysis in `scripts/residual_analysis.py`) | `sports2d_adapter.py`, `filtering.py` |
| Bag detection | Camera-compensated three-frame differencing (ORB + RANSAC similarity per frame pair), small blobs, blur fragments merged | `auto_bag.py` |
| Bag tracking | Constant-velocity tracklets → sub-window quadratic seeds + RANSAC → physics plausibility (image gravity range from the athlete's arm length, motion toward target) → local extension → local-parabola trimming. Manual fallback: seed + CSRT/colour tracker | `auto_bag.py`, `bag.py` |
| Release | First free-flight frame of the accepted flight (backward extension stops within 0.45 arm lengths of the wrist). Fallback: persistent bag–wrist divergence, then peak wrist speed | `auto_bag.py`, `bag.py`, `events.py` |
| Launch | Huber-weighted quadratic over ~0.12 s after release; with a scale, a gravity-constrained linear fit. Delta-method standard errors | `bag.py` |
| Scale | Flight's own vertical acceleration = g gives px/m in the flight plane; optional measured in-plane scale | `flight.py` |
| Landing | Manual first-contact / rest points on a board map; optional board-camera homography | `outcomes.py`, `BoardHomography.swift` |
| "Simulation" | Launch Explorer: drag-free point mass from slider values or athlete averages; animated stick-figure pendulum | `LaunchModel.swift`, `SwingExplorerPanel.swift` |
| Body metrics | 2D projected elbow angle, segment orientations, arm-to-trunk, trunk inclination, normalised wrist path, angular velocities, swing (pendulum) metrics | `kinematics.py`, `swing.py` |
| Outcome analysis | Within-athlete scored (1/3) vs miss (0): 12 pre-registered variables, Cliff's δ, noise floors, Holm-type family-wise control, 3-level plain-language feedback; physics "zones" | `performance.py`, `zones.py`, `stress.py` |

## 2. What is working (keep)

- **Measurement discipline.** Raw, effective, filtered and manual data are stored separately, with provenance.
  Unreviewed data is withheld, not guessed. Wording says "projected 2D" and never claims causation. Method
  versions gate compatibility.
- **Bag flight detection design.** A classical moving-object + projectile-constraint approach is the right
  choice for a ~20–30 px bag with no training data. 20/26 pilot clips were accepted with no clicks. The 6
  rejections are honest (two clips contain no complete throw).
- **Launch estimation.** Launch comes from a robust multi-sample fit, not a two-frame difference, and reports
  standard errors. This is already what the brief asks for in §5.
- **Within-athlete statistics.** The analysis is built around the athlete compared with themselves, not an "ideal
  throw". It uses rank effect sizes and noise floors, and a stress test shows false claims stay ≤ 5% for a null athlete.
- **Metric documentation.** `docs/METRICS.md` gives the definition, equation, units and limits of every body metric.

## 3. Scientifically weak

1. **No ground truth anywhere.** Bag centroid error, release-frame error, landing error and joint-angle error
   have never been measured. The noise floors in `performance.py` are simulated. *This is the largest gap.*
2. **Bag centroid was biased, not just noisy.** The detector reports the centroid of the frame-difference blob,
   which is where the bag contrasts most with the background, not the bag's centre. Visual check on clip 10:
   the point sat on the bag's top edge while it crossed a white wall. The mask refinement moved it a median 3.1 px
   and a 90th percentile 6.9 px (pilot, 20 clips). The bag is only ~25 px across.
3. **The drag-free model does not predict the second half of a flight.** Fitting the first half and predicting the
   second misses by a median 31 px (pilot, 20 flights). The bag decelerates horizontally in the image by ~7% of its
   vertical acceleration. Perspective (the bag moving away from the camera toward the board) and drag both produce
   this, and one camera cannot separate them. A fitted quadratic-drag model did not help consistently (median 24.5 px
   vs 24.9 px for a free quadratic). **Decision: no drag coefficient.** The ballistic model is used for description
   (apex, residuals) and very short-range prediction only.
4. **The gravity scale assumes the flight plane is square to the camera.** In the pilot framing the board is visibly
   farther from the camera than the athlete, so px/m changes along the flight. Release speed in m/s inherits this
   bias (sign unknown without a measured scale). Metres are therefore GOOD only when a measured in-plane scale
   agrees with the gravity scale.
5. **Segment orientations are unstable when a segment is foreshortened.** Clip 10 reports a forearm-orientation
   ROM of 350° over the throw. That is not a wrap-around bug (angles are unwrapped). The projected forearm is a few
   pixels long when it points at the camera, so its direction is noise. Orientation ROM and peak velocity should
   not be shown to coaches. None of the 12 outcome variables use them.
6. **Release timing is not validated.** The one manual comparison (clip 10) differs by 4 frames (67 ms). Release-
   referenced body values (elbow angle at release, arm angle at release) move with this error.
7. **The "simulation" is not the trial.** The Launch Explorer is a slider-driven teaching model. Nothing replays
   the measured path, the fitted model and the landing for one throw.

## 4. Technically weak

1. **Overlay drew stabilised coordinates on unstabilised video (fixed).** Automatic flight points were stored in
   the release frame's pixels with camera motion removed, then drawn on the raw hand-held video. The marker slid off
   the bag by the camera motion: median 13 px, up to 49 px during a flight (pilot). This is most of the visible
   "jitter / jumping / losing the bag". Manual corrections (raw pixels) were also mixed with these stabilised points.
2. **Coverage gaps.** Median 11% of flight frames had no detection (worst clip 24%), from motion blur and low contrast.
3. **Display smoothing was a 6 Hz Butterworth on the bag,** which rounds the release kink and does not know about
   gaps or outliers.
4. **No per-trial quality grade.** There were warnings, but no GOOD / WARNING / POOR per measurement stage.
5. **Whole clip held in memory** (`read_frames`: ~2.5 GB for a 7 s 1080p clip). Acceptable on the 16 GB
   development Mac. Should stream if longer clips are used.

## 5. Tracking approaches researched

| Candidate | What it offers | Fit for a ~25 px, blurred, single bag with no training labels | Verdict |
|---|---|---|---|
| Ultralytics YOLO + ByteTrack / BoT-SORT / OC-SORT ([docs](https://docs.ultralytics.com/modes/track)) | Detector + multi-object association with Kalman motion; BoT-SORT adds re-ID | Needs a trained bag detector: hundreds of labelled frames. Solves association between many objects, which we don't have. | Not now. Revisit once the annotation study produces labelled bag frames. |
| CoTracker3 ([repo](https://github.com/facebookresearch/co-tracker), [paper](https://arxiv.org/abs/2410.11831)) | Tracks arbitrary points through occlusion | A 25 px blurred bag has almost no stable texture to hold several points. PyTorch dependency; "GPU strongly recommended". | Not now. Benchmark candidate only if the bag becomes larger in frame (tripod, closer camera). |
| SAM 2 video predictor ([paper](https://arxiv.org/abs/2408.00714)) | Mask propagation from one click, giving centroid, area and orientation | Known weakness on fast, blurred, small objects: errors propagate through memory, and trackers drop frames after strong blur ([FMOX benchmark](https://arxiv.org/abs/2512.09633); [SAMURAI](https://arxiv.org/abs/2411.11922) adds motion-aware memory for this reason). Multi-GB install; 15 GB disk free. | Not now. Its useful product (a mask centroid, area and orientation) is reproduced classically below. |
| Norfair ([repo](https://github.com/tryolabs/norfair)) | Detector-agnostic Kalman tracker with custom distance | Designed for many objects. For one bag, the association problem is already solved by the physics-constrained search. | Not needed. The Kalman idea is implemented directly for the single flight. |
| TrackNet family ([TrackNetV3](https://github.com/qaz812345/TrackNetV3)) | Heat-map ball tracker + trajectory rectification | The closest problem (tiny fast shuttlecock), but trained on thousands of labelled frames. | Future option if a labelled bag dataset is built. Its background-subtraction and rectification ideas are already in our pipeline. |

**Recommendation.** Keep the classical detector. Add (a) a silhouette refinement for an unbiased centroid,
(b) a physics-informed Kalman/RTS smoother that keeps raw data, and (c) a ground-truth benchmark that can score any
future tracker, including SAM 2 or CoTracker, on the same frames. Test first the refinement that fixes the measured
bias. Do not add a deep model before the benchmark can show that it helps.

## 6. Implemented in this pass

| Change | Evidence (pilot, 20 accepted flights unless stated) |
|---|---|
| **Raw vs stabilised coordinates separated** (`auto_bag.py` v9). Points are stored in raw pixels, the same system as the video, pose and manual clicks. `stabilized_points` and per-frame `camera_to_release` transforms are stored alongside. Fits (launch, gravity scale, model check) stabilise via `bag_filter.stabilize_points`. | Launch values unchanged to 4 significant figures on clip 10 before the mask change. The overlay now stays on the bag in hand-held clips. |
| **Bag silhouette centroid** (`bag_segment.py`). Local median background from camera-aligned neighbour frames → colour-difference mask → moments give centroid, area and orientation. Short gaps are re-acquired. The detection centroid is kept next to the refined one. | Flight coverage median 89% → 100% (worst 76% → 96%). Jitter σ (third-difference estimate) 1.12 → 0.49 px, lower on 20/20 clips. Release frames unchanged on all clips. Visual check of 9 frames on clip 10: the mask centroid is at the bag's centre, including edge cases where the detector sat on the rim. |
| **Physics-informed flight filter** (`bag_filter.py`). Constant-acceleration Kalman + RTS smoother per axis; acceleration estimated, allowed to drift (not forced to g); noise chosen by maximum likelihood; leave-one-out outlier rejection; raw data copied unchanged; gaps > 3 frames left empty; no extrapolation before release or after contact. Written to `bag_flight_filtered.json` and used for the overlay's filtered centroid. | Mean normalised innovation ≈ 2.0 across clips (the value for a correctly specified 2D noise model). A sequential χ² gate was tried first and rejected: on real clips it cascaded and rejected up to 59 good points. |
| **Trajectory model check** (`trajectory_model.py`). In-sample and half-split out-of-sample RMSE, horizontal/vertical acceleration ratio, apex inside the observed flight, plain-language interpretation. | Clip 10: 16 px in-sample, 47 px out-of-sample, horizontal deceleration 14% of vertical: reported, not hidden. |
| **Bag-tracking validation workflow** (`bag_validation.py`, CLI `bag-annotation-frames` / `bag-benchmark`, annotator bag-only mode). Phase-stratified blinded frames; MAE, RMSE, success rate, per-phase errors, lost-track events, longest gap, release/contact frame error, landing position error, runtime, and cm only with an in-plane scale. Scores the detection, mask, filtered and effective tracks side by side. | Ready. **Needs a person to mark frames** (see `docs/BAG_TRACKING_VALIDATION.md`). |
| **Per-trial quality grades** (`quality.quality_grades`). GOOD / WARNING / POOR for pose, bag, calibration and release, each with its deciding numbers and written rules. | Clip 10: pose GOOD, bag GOOD, calibration WARNING (gravity scale only), release GOOD. |

New outputs: `bag_flight_filtered.json`; `results.flight.model_check`; `results.bag.flight_filter`;
`results.quality.grades`; summaries `bag_trajectory_model_rmse_arm_lengths` and `bag_trajectory_apex_rise_m`.
The tracker revision bump (`auto_motion_parabola_v9_mask`) makes old automatic tracks recompute on the next
analysis. Tracks with manual corrections are never discarded.

## 6b. Regression check before the checkpoint

`scripts/regression_check.py` re-analysed all 26 pilot throws in scratch copies. Pose was cached and the library was
not modified. Results compared with the stored results:

- 26/26 analyses completed. **Release frames are identical on all 26.** Body values at release (elbow angle,
  trunk, arm angle) are identical, because they depend only on pose and the release frame.
- Release values changed only through the new bag centre (20 throws with launch values):
  - angle: median |Δ| 0.8°, max 3.5°, mean Δ +0.01°;
  - speed (17): median |Δ| 0.08 m/s, max 0.27 m/s;
  - height (17): median |Δ| 1.6 cm, max 9.5 cm.

  These shifts are of the same order as the centroid bias that was removed. Whether they move values *toward*
  the truth is exactly what the annotation benchmark must show.
- Two throws that previously had no speed or height (gravity scale failed on sparse coverage) now have them.
- Release grades: 8 GOOD, 12 WARNING, 6 POOR (no accepted flight). **Every WARNING is from one rule**: the first
  flight point is 0.51–0.63 arm lengths from the wrist, just over the provisional 0.5 limit. That limit has no
  evidence behind it. It is deliberately left unchanged until the release-timing validation (Phase 5) shows what
  distance separates correct from late release detections.

## 7. Staged plan (next phases)

| Phase | Work | Needs from the team |
|---|---|---|
| 2b. Ground truth | Export ~14 frames per clip (`bag-annotation-frames`) and mark the bag centre; a second rater on a subset. Run `bag-benchmark`. Replace provisional noise floors and grade thresholds with measured values. | ~1–2 h of clicking for 26 clips |
| 3b. Tracker candidates | Only if the benchmark shows residual error at release or near the board: try SAM 2.1-tiny or CoTracker3 on those phases, scored on the same frames. | Approval for a ~1 GB PyTorch install |
| 4. Calibration | Tripod + meter stick in the throwing plane (already in `RECORDING_PROTOCOL.md`); board-corner homography for the landing plane only. Report the gravity-vs-measured scale ratio per clip. | New recordings |
| 5. Release | Validate against marked release frames. Add a bag–wrist separation-velocity check across several frames as a second, independent estimate; flag disagreement > 2 frames. | Ground truth from 2b |
| 7. Trial replay | Replace slider-first Launch Explorer with a per-trial replay: measured path (solid), fitted model (dashed), release, apex, first contact and rest markers, outcome. Level 1 (playback) and Level 2 (ballistic) only; model residual shown. | — |
| 8. Body metrics | Hide orientation ROM/peak velocity when the segment is foreshortened (projected length < 50% of median); add wrist speed at release, timing of peak wrist speed and peak elbow extension velocity relative to release, wrist-path repeatability. | — |
| 9–10. Outcome analysis + UI | Progressive layout (Outcome → Release → Flight → Mechanics → Consistency → Comparison → Scientific). Normalised curves with successful/unsuccessful means and bands. Graph click → video seek. Quality grades on every panel. | — |
| 11–12. Validation + docs | Validation section per stage (pose, bag, release, trajectory, landing, repeatability) filled from the annotation study. | — |
