# Validation plan

**Protocol version: 8 September 2026**

Cornhole Biomechanics Lab is a research prototype. Passing tests verifies code behavior; it does not prove that a camera-based value is accurate, repeatable, or useful for coaching. This plan keeps four questions separate.

| Evidence class | Question | Example evidence | What it cannot establish alone |
|---|---|---|---|
| Software verification | Does the code implement its stated equation, data rule, and workflow? | Synthetic trajectories, schema tests, relaunch tests, build, end-to-end UI checks | Accuracy of pose or bag measurements on people |
| Measurement repeatability | Does the same setup give sufficiently similar estimates when the movement/setup is repeated or re-annotated? | Within-session/between-session variation, repeat annotation, ICC with specified model | Agreement with truth; usefulness for performance |
| Criterion/task validity | Does the estimate agree with a stronger reference for the same quantity and task? | Manual image digitization; synchronized calibrated motion capture projected into the image plane | That the measure predicts cornhole outcomes or causes improvement |
| Performance validity | Do changes in the measured feature meaningfully accompany changes in cornhole performance for the athlete? | Repeated real throws, outcomes, raw scatter, effect/uncertainty, held-out confirmation | Causality without an appropriate intervention/design |

No document or UI may shorten these four categories to “validated” without naming which one has evidence.

## 1. Freeze the pilot configuration

Before evaluating results, record:

- app commit/build and Python package revision;
- Sports2D, Pose2Sim, RTMLib/ONNX Runtime, pose model identity and model hash;
- bag tracker method/version and seed procedure;
- confidence thresholds and person-selection method;
- interpolation rule and maximum gap;
- filter type, order, cutoff, and finite-run behavior;
- release-candidate method, thresholds, persistence window, and fallback;
- camera/phone model, lens, resolution, nominal and measured fps, exposure mode, orientation, distance, height, and view;
- target direction and throwing side;
- board dimensions and pitching distance actually measured;
- physical calibration object, dimension, position/plane, and uncertainty, if m/s will be reported.

Mark tripod, throwing area, and board locations. Do not tune processing separately for scored and missed throws. If a method changes, start a new configuration cohort and do not pool it silently with the old one.

## 2. Software verification

Synthetic and file-workflow tests must cover at least:

- included angles of 0°, 45°, 90°, 135°, and 180°, plus a degenerate zero-length vector;
- target-direction reflection and left/right handling;
- translation and uniform-scale invariance of normalized paths;
- time normalization without bridging a long missing interval;
- signed-angle unwrap across ±180°;
- Nyquist rejection and too-short filter runs;
- confidence masking, short-gap provenance, and long-gap preservation;
- immutable raw points, manual correction priority, reset, undo, and redo;
- event ordering, valid frame bounds, and manual-over-automatic priority;
- straight path approximately 1 and a curved path below 1;
- known constant-velocity and polynomial trajectories;
- bag–wrist co-movement followed by persistent separation;
- local-fit release velocity/angle and missing/invalid calibration units;
- shoulder/wrist global-relative decomposition;
- shoulder-to-wrist and shoulder-to-bag radius;
- incompatible view rejection;
- raw reference errors and composite arithmetic;
- missing/deleted files, locate/relink, deletion semantics, migration idempotence, and library relaunch persistence.

Run Python tests, Swift tests, the release build, and the non-mutating verification command. Record exact commands, commit, environment, counts, warnings, and failures in [VERIFICATION.md](VERIFICATION.md). A failing check stays visible until rerun; do not replace a failure with an earlier passing result.

## 3. Data and participant protocol

- Follow instructor and institutional requirements for consent, privacy, retention, and access.
- Use participant codes unless identifying information is necessary and approved.
- Record whether supplied/reference video is consented participant data, user-owned QA media, public demonstration media, or synthetic data.
- Never infer course-participant provenance from a filename or folder.
- Preserve originals; perform imports through the app and analyze copies/managed references.
- Record exclusions and tracker failures rather than deleting poor throws.
- Collect repeated throws spanning ordinary performance variation. Determine sample size from the planned analysis and feasible pilot precision; do not treat an app display gate as a power calculation.

For each throw, record athlete, session, timestamp, target, throwing side, view, throw type, per-bag value, foul/dead state, intended board target, first contact if observed, final rest if observed, and notes. Keep contact and rest distinct.

## 4. Camera and board setup

Primary Stage 1 setup is a fixed side view with the optical axis approximately perpendicular to the main throwing plane. Keep the throwing arm, both shoulders, and both hips visible throughout the reviewed interval. Use stable zoom, landscape orientation, strong lighting, short exposure, uncluttered clothing/background, and one dominant person. Prefer 60 fps or higher for fast release motion, but record actual timestamps/fps rather than trusting a label.

Measure the study board. The nominal ACL default is 24 by 48 in with a 6 in hole centered at `(12,39)` in from the pitcher/front origin, but permitted manufacturing tolerances mean the physical board may differ. Board geometry is not an athlete-plane scale. If physical release velocity is required, place a known object in approximately the athlete/release plane and quantify calibration repeatability.

## 5. Pose landmark validation

Select frames before motion, at backswing, during forward swing, at visible release, and during follow-through, including difficult blur/occlusion frames. A trained reviewer manually marks at minimum throwing shoulder, elbow, wrist, bilateral shoulders/hips used for trunk, and the bag when visible.

Where practical:

1. keep the reviewer blinded to automatic points during the first pass;
2. repeat a randomized subset after a delay;
3. use a second reviewer for another subset;
4. preserve every annotation set rather than averaging it away.

Report per-landmark and per-phase:

- Euclidean pixel error versus manual label;
- error divided by `L_arm`;
- horizontal and vertical bias;
- median, interquartile range, mean, SD, RMSE, and selected quantiles;
- missing and false-track rate;
- correction rate and failure frames;
- within-rater and between-rater disagreement.

Manual disagreement estimates annotation repeatability; it is not automatically ground truth. Pose confidence should be tested as a ranking/gating signal and must not be presented as calibrated physical error.

## 6. Bag-track validation

Use supplied QA recordings only after confirming they can be copied without modifying originals. For a stratified frame subset—held, early release, clear flight, blur, overlap with hand/body, near board, and tracker failure—manually mark bag centroid.

Compare automatic and final corrected tracks with the independent labels. Report:

- pixel and arm-normalized centroid error;
- horizontal/vertical bias;
- missing-track rate;
- wrong-object/identity-switch count;
- fraction manually corrected or interpolated;
- longest unsupported gap;
- named failure frames and visual examples;
- tracker seed time and reviewer effort.

Do not compute an aggregate only on frames where the algorithm succeeded; that would hide failures. Report all eligible frames and the denominator.

## 7. Release-event validation

Define a written manual release rule before comparison—for example, first frame of persistent visible bag–hand separation, acknowledging ambiguous frames. Have reviewers label release independently and repeat a subset.

For the automatic candidate versus the reviewed manual frame, report:

- signed and absolute difference in frames;
- difference in milliseconds using `1000/fps`;
- median, spread, and worst observed differences;
- missing candidate rate;
- whether bag evidence or wrist-only fallback was used;
- failure videos/conditions.

Also report reviewer-to-reviewer and repeat-review differences. Frame conversion is not sub-frame precision. A 60 fps video has a 16.7 ms sample interval; blur can make actual uncertainty larger.

## 8. Kinematic criterion validity

For projected elbow, trunk, path, and velocity variables, compare the app with a defensible criterion measuring the same definition in the same plane:

- manual digitization using the equations in [BIOMECHANICS_METHODS.md](BIOMECHANICS_METHODS.md); or
- synchronized, calibrated motion capture projected into the camera plane; or
- for bag velocity, a higher-frame-rate calibrated video with synchronized events.

Do not compare an image-plane included angle with an unmatched 3D anatomical angle and call the difference model error. Report paired traces, bias, MAE, RMSE, limits of agreement, phase-specific errors, missingness, and the effect of manual corrections. Correlation describes waveform similarity, not absolute agreement.

Predefine acceptable error for the intended coaching decision using manual repeatability, expected within-athlete changes, and criterion uncertainty. Do not borrow an error threshold from gait, darts, another pose model, or a different frame rate.

## 9. Measurement repeatability

Use repeated throws within a fixed session and, when possible, repeat the setup on another day. Report every metric with `n`, mean, median, SD, robust spread, and missingness. Separate:

- repeated manual annotation of the same frames;
- reanalysis of the same video/configuration;
- repeated throws in one setup;
- repeated sessions after camera replacement.

For waveforms, inspect pointwise SD and phase-specific variability. If sample size/design supports an ICC, name the exact ICC model, unit of analysis, confidence interval, and rationale; also report typical/standard error in the original units. A biased measurement can be repeatable, so do not substitute repeatability for criterion validity.

## 10. Camera sensitivity

Repeat controlled throws or a calibration movement while varying one factor at a time:

- small yaw away from perpendicular;
- camera height and distance;
- left versus right side;
- front/rear versus side view;
- landscape framing/resolution;
- zoom/cropping;
- lighting, clothing contrast, motion blur, and arm–torso occlusion.

Report changes in landmarks, projected angles, event timing, path metrics, and bag velocity. Use the results to define supported views and warning conditions. Do not convert a sensitivity test into an out-of-plane correction unless depth/camera information supports that correction.

## 11. Filter and interpolation sensitivity

On representative real trials, analyze the same immutable inputs at plausible cutoffs such as 4, 6, and 8 Hz, plus an unfiltered diagnostic when safe. Hold all other settings constant. Compare:

- coordinate and elbow/trunk waveforms;
- release angle and local-fit speed;
- angular velocity and optional acceleration;
- automatic event frames;
- path length/straightness/radius variability;
- conclusions of the movement–performance analysis.

Inspect residuals and spectral content where the record length permits. Test alternative short-gap limits separately. Choose and document the final setting before evaluating outcome groups. Conclusions that reverse with a plausible cutoff are unstable and must be reported as such.

## 12. Frame-rate sensitivity

If a high-frame-rate original exists, retain it and create analysis copies through a non-destructive workflow at lower rates. Analyze original and downsampled copies with appropriately documented filters. Compare release frame/time, elbow/trunk at release, bag velocity/angle, angular velocity, and path metrics.

This experiment supports statements about this task and camera setup. It does not justify a universal minimum frame rate. Preserve the mapping between downsampled and original frames and report temporal quantization.

## 13. Reference-set assessment

Ask a coach to define reference-selection criteria before seeing similarity/outcome results. Prefer several compatible, quality-reviewed throws over one supposedly exemplary trial. Report reference-set `n`, provenance, mean waveform, sample-SD band, view/settings, and selection rule.

Test whether raw distance from the reference is associated with outcome. Compare that explanation with the athlete's own consistency and individual kinematic features. If similarity is unrelated to performance, report that result; do not redefine the reference after the fact without labeling a new exploratory analysis.

## 14. Participant performance validity

Analyze within athlete first. Preselect a small group of interpretable features and one named outcome at a time. Show all raw points, `n`, missing/excluded observations, units, and session structure. Use Spearman association only when both variables vary and the complete-pair gate is met. Report estimates and uncertainty without treating a thresholded p-value as proof.

Confounding factors include learning, fatigue, target choice, session order, camera changes, and multiple feature testing. Exploratory findings generate a hypothesis. A later pre-registered session or intervention should test whether the association repeats before coach-facing prescriptive language is considered.

## 15. Reproducibility and persistence audit

For randomly selected trials, rebuild derived results from source video, immutable automatic tracks, corrections, event overrides, outcome, configuration, and manifest. Confirm source/model/engine hashes, row counts, normalized sample count, units, warnings, figures, and report. Reopening the app must restore the same athletes, sessions, trials, references, file links, settings, and selected data root.

Exercise legacy migration twice to confirm it is idempotent. Move a test copy of a video and confirm the record becomes **Missing file** with working **Locate / Relink**, not silently deleted. Verify deletion rules on disposable copies: deleting analysis retains video; removing a reference assignment retains its source throw; athlete/session/throw deletion reports the affected items and uses a recoverable mechanism where practical.

## 16. Current supplied-video status

The repository contains five unique MP4 files under the literal path `Participant/Reference /Cornhole Study.cornholeproject/videos` (the `Reference ` directory has a trailing space). They are user-owned inputs and were inventoried without modification on 2026-09-08. Their names and location alone do not establish consent or course-participant provenance.

Use normal app import/copy behavior for QA. Record each filename, hash, duration/fps/resolution, tracker result, bag failures, manual corrections, and release review in [VERIFICATION.md](VERIFICATION.md). Until that evidence is recorded, these files count as **available QA material**, not completed bag/pose validation and not participant science.

## 17. Completion and reporting

Before calling a measurement protocol supported, define its intended use and acceptance criteria, then evaluate a held-out or frozen dataset. Report failures and uncertainty, not only averages. At minimum the course report should include:

- participant/data provenance and fixed camera protocol;
- exact software/model/configuration versions;
- software-verification results;
- pose and bag tracking error including missing/failure frames;
- manual annotation repeatability;
- release-event agreement;
- filter, camera, and frame-rate sensitivity;
- within/between-session repeatability;
- criterion agreement where available;
- raw movement–outcome observations and uncertainty;
- exclusions, limitations, and unresolved risks.

Real participant task/performance validity remains incomplete until those data are collected and analyzed. Passing tests, a successful build, or an attractive report does not change that status.
