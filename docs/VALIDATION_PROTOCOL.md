# Stage 1 Validation Protocol

This protocol turns a working software instrument into an evidence-generating course project. Public videos can exercise software paths, but the course question requires real task performance from consented participants.

## 1. Freeze the pilot configuration

Record the app/package versions, pose backend/model hash, confidence threshold, gap policy, filter type/order/cutoff, camera model, resolution, nominal and measured frame rate, distance, height, lens, and view. Mark the camera/tripod and board positions. Do not tune settings separately for successful and unsuccessful throws.

## 2. Verify board and recording geometry

Confirm the board is 24 by 48 inches with the hole center 12 inches across and 39 inches from the pitcher end. Measure the applicable pitching distance using current course-approved ACL rules. Record a scale object or board dimensions for diagnostic perspective checks even though scale is not required for angle/path comparison.

Use a fixed side/sagittal-like camera, perpendicular to the intended movement plane, with the participant's upper body and throwing arm fully visible. Prefer at least 60 fps, short exposure, fixed zoom, stable lighting, and the same setup for every repeated trial.

## 3. Collect real repeated trials

- Follow instructor/institution requirements for participant permission, privacy, and data handling.
- Use participant codes rather than unnecessary identifying information.
- Record enough repeated throws per athlete to span ordinary performance variation; at least eight complete movement–outcome pairs are needed before the software reports correlation, and more are preferable.
- Randomize or balance conditions if different target/throw types are studied.
- Record intended target, 3/1/0 score, throw type, and approximate first contact/final rest immediately after each throw.
- Do not discard poor outcomes or tracking failures without recording the exclusion reason.

## 4. Tracking reliability audit

Select frames across backswing, forward swing, visible release, and follow-through. Have a trained reviewer manually digitize the eight primary landmarks while blinded to automatic points where practical. Repeat a subset after a delay and, if possible, use a second reviewer.

Report image-space landmark error, corrected-frame proportion, missingness, and intra/inter-rater differences. Stratify by landmark and movement phase. Pose confidence should be evaluated as a ranking/gating signal, not assumed to be calibrated distance uncertainty.

### How to run it

1. Analyze the clip in the app or with `cornhole-biomech analyze`.
2. Export blinded frames. Event frames are chosen first, with release ±2 frames, then evenly spread frames up to the count:
   `cornhole-biomech annotation-frames VIDEO --analysis ANALYSIS_DIR --output FRAMES_DIR --count 12`
   The frame choice is deterministic, so a second rater gets the same frames.
3. Each rater opens `tools/annotator.html` in a browser, loads every PNG plus `annotation_manifest.json`, and marks the throwing shoulder, elbow and wrist, the other shoulder, both hips and the bag, using "not visible" where needed. They then download the JSON.
   Release and first-contact frames are entered as video frame numbers. Step through the original video to find them before looking at any automatic event.
4. Compute agreement:
   `cornhole-biomech validate-tracking --annotation RATER_A.json --second-annotation RATER_B.json --analysis ANALYSIS_DIR --throwing-side right --output report.json`

The report gives, per landmark, mean/median/RMSE/95th-percentile error in pixels and arm lengths, bias, and detection-failure rate. It also gives projected elbow-angle error (raw and filtered points), release-frame error, and rater-versus-rater agreement. Rater disagreement is the floor below which automatic error cannot be demonstrated.

## 5. Kinematic validity audit

Compare projected angles against a defensible criterion measured in the same image plane (manual digitization or validated motion capture projected into the camera plane). Use paired traces, mean absolute error, RMSE, bias, limits-of-agreement plots, and phase-specific error. Do not compare a 2D projection directly with an unmatched 3D anatomical angle and call the difference model error.

Repeat controlled recordings with small camera-angle and distance changes to quantify sensitivity. Test arm occlusion, clothing, and illumination deliberately. The goal is to define when the system is usable, not to hide failure conditions.

## 6. Processing sensitivity

On the same trials, vary reasonable confidence thresholds, interpolation gaps, and filter cutoffs. Plot position and velocity traces. Confirm scientific conclusions do not hinge on one arbitrary setting. Choose the cutoff using signal/noise evidence and expected movement content; document the final decision before outcome analysis.

## 7. Repeatability

For each athlete and feature, report `n`, mean, median, standard deviation, range, and repeated-session context. For full normalized trajectories, inspect pointwise variability and key-phase variability. When sample size supports it, add ICC and typical/standard error with the exact model and confidence interval. A repeatable biased measure is not necessarily valid, so report validity and repeatability separately.

## 8. Reference assessment

Ask a coach to select references using a rule written before viewing test comparisons. Prefer several high-quality repetitions rather than one “perfect” throw. Report reference-set `n`, mean curve, variability envelope, and recording compatibility. Evaluate whether distance from the reference is actually associated with outcome instead of assuming it.

## 9. Movement–performance analysis

Analyze within athlete first. Preselect a small number of interpretable features: elbow angle at release, elbow range, trunk inclination, movement duration, release timing, wrist-path deviation, and reference similarity where available. Show raw points and sample size. Use Spearman association when justified, effect estimates and uncertainty rather than thresholded p-values, and cautious language: “associated with,” not “causes.”

Compare three distinct candidate explanations:

1. closeness to the coach-selected reference;
2. consistency of the athlete's own technique;
3. individual kinematic features.

Treat exploratory findings as hypotheses for a larger follow-up, especially with small pilot samples or multiple comparisons.

## 10. Reproducibility audit

For randomly selected trials, rebuild results from the saved source video, corrections, events, configuration, and manifest. Confirm hashes, high-level summaries, CSV row counts, normalized sample count, and plot generation. Archive the exact repository commit used in the report. Keep original recordings unchanged and retain exclusion/correction logs.

## Completion evidence

Stage 1 scientific validation is complete only when the report includes real participant data, the fixed camera protocol, tracking/kinematic error evidence, repeatability, movement–outcome observations, quality/exclusion reporting, and limitations. Passing automated tests proves software behavior; it does not prove biomechanical validity.
