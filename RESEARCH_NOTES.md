# Research Notes

Updated 2026-09-07. This document separates published evidence from decisions made for this application. Software checks are complete only where recorded in [QA](docs/QA.md); real-participant measurement validity remains an experimental question. Exact definitions live in [METRICS](docs/METRICS.md), and sources in [REFERENCES](REFERENCES.md).

## 1. Research question

Can one camera quantify upper-body cornhole movement repeatably, compare athletes after body-size normalization, and identify movement features associated with task outcome?

For each athlete, does performance relate more to resemblance to a selected reference, repeatability of their own motion, or individual kinematic features?

EVIDENCE: The course asks for a working prototype connecting how a movement is performed with its outcome, using real participant data.

OUR DECISION: Keep reference similarity, athlete consistency, tracking quality, and bag outcome separate throughout the interface and exports.

## 2. Why

Scoring tells us where the bag finished. It does not describe the movement that produced that result. Video can make movement measurable during ordinary practice, provided the measurements retain their limitations.

EVIDENCE: Precision-throwing research finds multiple successful strategies, including managing hand-path sensitivity and reducing release-timing error.

OUR DECISION: Preserve time-dependent movement curves and outcomes, rather than declaring one coach-selected throw universally correct.

## 3. What the assignment requires

Stage 1 needs real participant measurements, a defensible biomechanical question, an operational prototype, and a movement–outcome connection. The course materials are preserved locally under `reference_materials/course/`; they are not distributed with the application.

EVIDENCE: The project brief and syllabus emphasize actual measurements and explaining the benefits, drawbacks, and assumptions of the chosen method.

OUR DECISION: Use synthetic fixtures and the official Sports2D demonstration strictly for software QA. Collect consented participant throws for the course experiment, with a fixed recording protocol and linked outcomes.

## 4. What we know about precision throwing

Dart studies support examining joint waveforms, wrist trajectories and release timing together. They do not establish a cornhole ideal, a useful similarity threshold, or phone-video accuracy during release.

EVIDENCE: Nasu et al. (2014), Nasu and Matsuo (2015), and Tran et al. (2019) describe distinct expert strategies in small laboratory dart samples.

OUR DECISION: Treat reference resemblance as a descriptive comparison. Prioritize repeated throws within the same athlete when investigating performance.

## 5. What we know about 2D biomechanics

A camera sees a projection. Angles can be useful when motion stays near a plane perpendicular to the camera, but viewpoint and depth motion change those angles. Markerless landmarks are image estimates, not directly measured anatomical centers.

EVIDENCE: Sih et al., Yokoi and Okada, and markerless validation studies show sensitivity to perspective, occlusion and task. Gait error estimates cannot be reused as cornhole upper-limb error bounds. High waveform correlation can coexist with substantial angle error.

OUR DECISION: Call measurements projected 2D angles. Prefer a fixed side camera, block mismatched-view comparisons, retain confidence and missingness, and report raw error separately from correlation.

## 6. Why Sports2D was selected

Sports2D offers an existing local video-to-pose pipeline, annotated video, coordinate exports and angle exports. Building cornhole analysis above this reduces duplicated pose-engine work while keeping the study's own measurements explicit.

EVIDENCE: Sports2D's public API, BSD-3-Clause license, JOSS publication and inspected source document these capabilities.

OUR DECISION: Pin Sports2D **0.8.34** and Pose2Sim **0.10.49**. Use the public `Sports2D.process(config)` entry point with CPU ONNX inference. See [SPORTS2D](docs/SPORTS2D.md) for the exact source revision inspected and adapter contract.

## 7. What Sports2D can and cannot do

Sports2D tracks people and exports projected coordinates/angles. It does not know cornhole outcome, the selected reference, the reviewed release frame, or this application's scoring definitions. Its saved TRC does not preserve the full raw-confidence provenance needed here.

EVIDENCE: Inspection of version 0.8.34 shows that the public processing call returns no structured raw-pose result. Raw coordinates and confidence remain available internally during processing.

OUR DECISION: A version-locked bridge captures these named arrays at return from the processing function. It fails clearly if the contract changes. We do not modify upstream files. We disable meter conversion, C3D conversion, augmentation and inverse kinematics because single-camera data do not justify measured 3D claims. Alternative backends require an explicit selection; there is no silent substitution.

## 8. Selected measurements

Measure the throwing elbow's included angle, arm and forearm orientations, arm relative to trunk, trunk inclination, shoulder-relative wrist/elbow paths, movement duration, phase timing, and quality-gated angular velocity. Retain bilateral shoulders and hips for trunk geometry.

EVIDENCE: These quantities can be defined from visible image landmarks; precision-throwing literature motivates inspecting trajectory and timing together. It does not validate every variable for cornhole prediction.

OUR DECISION: Expose interpretable projected quantities. Exclude humeral axial rotation, forearm pronation/supination, true 3D wrist rotation, kinetics and injury labels.

## 9. Equations and processing

For elbow vertex B between shoulder A and wrist C, set `u=A−B`, `v=C−B`; the included angle is `atan2(|u×v|,u·v)` in degrees. A straight elbow is 180°. Sports2D's signed elbow convention is converted with `180−abs(wrap180(angle))` when auditing its output.

After confidence masking and separate manual corrections, interpolate short internal gaps only, then filter continuous finite runs. The default is a fourth-order Butterworth low-pass at 6 Hz applied forward/backward. Angular velocities use filtered trajectories, with orientation unwrapping within finite runs. Long gaps remain gaps. Whole-video curves remain available; trial mean, range and peak summaries use reviewed movement bounds.

EVIDENCE: Planar vector geometry defines the angles. Signal-processing literature supports phase-neutral filtering and warns that cutoff choice affects signal content and derivatives.

OUR DECISION: Use 6 Hz as a pilot setting, not a universal optimum. Store settings and evaluate 4/6/8 Hz sensitivity on recorded throws. Do not report unreliable derivatives. The authoritative per-metric equations, units and limitations are in METRICS.

## 10. Body-size and time normalization

A 5'4" athlete and a 6'8" athlete occupy different image scales. Translate their paths to the throwing shoulder, reflect horizontal direction toward the target, and divide distances by median visible upper-arm length plus median forearm length. Map the reviewed movement to 0–100% with 101 samples. Do not bridge missing intervals during resampling.

EVIDENCE: Translation, uniform scale and reflection can be removed algebraically. These operations cannot eliminate perspective, body-proportion differences, camera roll or depth motion.

OUR DECISION: Compare angles and dimensionless paths, never raw pixels across people. Show the normalization steps in the app. Preserve actual duration and event timing so normalization does not hide timing differences.

## 11. Reference comparison

Compute time-preserving angle MAE/RMSE, waveform correlation, peak/range differences, path RMSE and event timing differences against a selected trial or pointwise reference mean. Circular orientation errors use the shortest signed angular difference. A reference-set band shows sample SD, not a confidence interval.

EVIDENCE: Agreement measures answer different questions from correlation; a selected reference is not a population norm.

OUR DECISION: Offer reference, reference-set, trial-to-trial and athlete-versus-own-mean modes. Exclude the selected throw from its comparison mean; reject mismatched view, model, settings or pending corrections. The pilot similarity score is a weighted mean of `100×max(0,1−error/tolerance)`. Show every component, tolerance, omission and raw error. No dynamic time warping replaces the primary time-preserving comparison.

## 12. Athlete consistency

Consistency asks whether this athlete repeats their own movement, regardless of the chosen reference.

EVIDENCE: Repeatability and criterion validity are different. Small samples yield unstable variability estimates.

OUR DECISION: Require at least five throws from the same athlete, session, view, side, model and settings, each with at least 80% usable frames. Use RMS pointwise sample SD for elbow/trunk, two-dimensional wrist dispersion, and release-time SD. Require all four components and adequate sample coverage. Pilot tolerances are 15°, 10°, 0.25 arm lengths and 0.10 cycle. These are configurable research conventions, not validated norms.

## 13. Cornhole outcomes

Store per-bag 0/1/3 points, intended target, first contact, final resting location, throw type and notes. The board is 24 by 48 inches; hole center is (12,39), radius 3 inches. Origin is the lower-left board corner viewed from the pitcher's end.

EVIDENCE: ACL rules define board geometry and bag scoring. Spatial error is a separate measurement from categorical scoring.

OUR DECISION: Show target, contact and resting points with distinct symbols. Treat manual board clicks as approximate. Bag points are not a full round's cancellation score. Avoid inventing landing points from body tracking.

## 14. Movement–performance analysis

Explore one athlete's movement variables against bag score and spatial error. Show actual paired throws and the selected outcome definition.

EVIDENCE: Within-person associations can be confounded by fatigue, practice, camera changes and choice of target; correlation does not establish causation.

OUR DECISION: Require at least eight complete pairs for a relationship estimate, using the same comparable cohort as consistency. Keep first-contact and resting-error endpoints distinct. Show sample size, scatter, Spearman association and exploratory uncertainty. Treat multiple tested features as hypothesis generation, not proof of technique benefit.

## 15. Validation

Software verification covers known planar geometry, translation/scale/reflection, event timing, gaps, confidence masking, correction provenance, reference means, score arithmetic, serialization and the real Sports2D export path. Native release checks cover controls and the Python boundary.

EVIDENCE: Passing software tests shows implementation behavior; it does not establish human-measurement validity.

OUR DECISION: Next, freeze a consented pilot dataset; manually digitize selected frames independently, compare angle bias and agreement, repeat event annotation across raters/days, and quantify test–retest variation. Include difficult release/occlusion frames rather than only easy ones. Use laboratory reference capture when available. Record model/configuration hashes and keep participant media out of public Git.

## 16. Assumptions

EVIDENCE: Single-camera interpretation requires stable projection and sufficient visibility; pose confidence is not calibrated physical error.

OUR DECISION: Record 60 fps or higher when available, landscape, fixed tripod, stable zoom, bright lighting and a side view perpendicular to the main throwing plane. Keep both shoulders, hips, elbow and wrist visible. Label throwing side and target direction correctly. One clearly visible athlete should dominate the frame. Review all automatic event candidates, especially release. Sessions preserve camera setup and notes.

## 17. Risks and limitations

EVIDENCE: Blur, occlusion, out-of-plane motion and model bias can affect the quantities displayed. Published validation from other activities does not resolve these risks for cornhole.

OUR DECISION: Make warnings visible, preserve missing values and raw predictions, and require reanalysis after edits. Quality scores describe raw coverage/confidence, not percent accuracy. Similarity and consistency remain pilot indices. Deterministic summaries describe computed observations without giving causal coaching prescriptions. No real-participant criterion validation is claimed.

## 18. Evidence table


| Source | Question addressed | Main finding (fact from source) | Important limitation | Implication for this system (our decision) |
|---|---|---|---|---|
| Vanderbilt Project 1 brief (2026) | What constitutes a successful course project? | A working prototype must use real participant data and relate movement features to task outcome; tracking or scoring alone is insufficient. | It deliberately does not prescribe a measurement method. | Save kinematics and outcomes under the same trial ID; make within-athlete movement-versus-outcome analysis a core workflow. |
| Vanderbilt course syllabus (2026) | What learning outcomes matter? | Students must select and defend biomechanical measurements while understanding benefits, drawbacks, and assumptions. | It is course-level guidance, not a protocol. | Make assumptions, quality indicators, equations, and limitations visible rather than hiding them behind a score. |
| ACL rules and scoring (2025/26 rules pages) | What is the task geometry and legal outcome? | Boards are 27 ft front-to-front; a pitcher's box is 3 x 4 ft; the foul line is the board front; bags score 3 in the hole, 1 on the board, and 0 elsewhere/foul. | Rules can change by season and tournament format. | Store the ruleset/version; use a regulation 24 x 48 in board coordinate system and a 6 in hole; retain categorical and approximate spatial outcomes. |
| Nasu, Matsuo, and Kadota (2014) | Is one expert pattern necessarily optimal? | Eight experts and eight novices (60 throws each, seven 480 Hz cameras) showed two expert strategies: reduced timing sensitivity through hand path or reduced release-timing error. | Darts, not cornhole; laboratory high-speed 3D capture. | Never call one trial perfect form. Separate reference similarity, within-athlete consistency, and performance relationship. |
| Nasu and Matsuo (2015) | Do expert strategies have distinct joint kinematics? | The two expert strategy groups differed in upper-extremity kinematics. | Eight experts split into small groups; dart task. | Preserve joint waveforms and timing rather than collapsing the movement into one score. |
| Tran, Yano, and Kondo (2019) | Which coordination features distinguish skilled throwing strategies? | Eight experts performing 42 dart throws showed timing-sensitivity and timing-error strategies related to hand trajectory and release kinematics. | Dart flight/release and 200 Hz six-camera measurement differ from phone video. | Treat release timing as frame-limited; analyze hand/wrist path, elbow/wrist coordination proxies, and performance associations without causal language. |
| Stenum et al. (2021) | Can one-view pose estimates yield useful 2D angles? | In sagittal gait, OpenPose-based 2D angle MAE against 3D motion capture was approximately 4.0 degrees at the hip, 5.6 degrees at the knee, and 7.4 degrees at the ankle; camera perspective affected accuracy. | Lower-limb gait is more planar and slower than a cornhole release; figures are not upper-limb error bounds. | Do not reuse these values as cornhole tolerances. Validate the exact task, view, model, and landmarks. |
| Scott et al. (2023) | How does single-camera upper-limb analysis compare with reference motion capture? | Preliminary cup-drinking results for one participant reported elbow RMSE 16.3 degrees despite high waveform ICC, illustrating that reliability and agreement are different. | Conference abstract, one participant result, Azure Kinect/OpenSim rather than RGB pose estimation. | Report raw error and waveform agreement separately; do not treat correlation as absolute validity. |
| Vanmechelen et al. (2024) | Is 2D markerless upper-extremity analysis clinically promising? | Sideways-reaching videos showed promising concurrent and construct validity for upper-extremity features. | Specific clinical population and task; performance does not transfer automatically to throwing. | Use task-specific repeatability and criterion validation before making accuracy claims. |
| Sih, Hubbard, and Williams (2001); Yokoi and Okada (1994) | What assumption underlies 2D kinematics? | A single-camera planar analysis assumes motion near a plane perpendicular to the optical axis; out-of-plane displacement produces perspective error. | Corrections require information not always available. | Make side view primary, fix camera position, label view/direction, prohibit reference comparisons across incompatible views, and describe results as projected 2D measures. |
| Kanko et al. (2021) and recent markerless reviews | What errors affect markerless biomechanics? | Pose estimates are affected by occlusion, viewpoint, clothing, joint-center definition, image quality, and model/training data. Validity is task- and variable-specific. | Most validation is gait/lower limb or multi-camera. | Retain raw points/confidence, allow non-destructive correction, show missingness, and validate repeatability separately from criterion validity. |
| Challis (1999); Winter-style residual-analysis literature; SciPy signal docs | How should trajectories be filtered? | Low-pass filtering can attenuate high-frequency measurement noise, but the cutoff should preserve movement content. Forward-backward filtering removes phase lag; second-order-section filters are numerically preferable. | No universal cutoff applies across tasks, frame rates, or pose models. | Default to 4th-order zero-phase Butterworth at 6 Hz only as a documented starting point for 60+ fps video; require cutoff below Nyquist, expose it, and support residual/sensitivity review. Never differentiate raw pose data. |
| Sports2D 0.8.34 / reviewed commit `4392177` | What existing single-camera sports pipeline is closest? | Sports2D supports video pose estimation, confidence thresholds, interpolation, filters, 2D angles, TRC/MOT, annotated video, CPU/MPS, and Sports2D/Pose2Sim conventions. | Generic workflow; current saved TRC does not retain every raw confidence/correction provenance field needed here; cornhole outcomes/reference models are absent. | Follow compatible keypoint conventions and use the pinned public processing API and a version-locked raw-confidence adapter, but own the raw/corrected data model and cornhole analysis. |
| Pose2Sim 0.10.49 / reviewed commit `65bbb05` | When is Pose2Sim appropriate? | Pose2Sim is a multi-camera 3D workflow using RTMPose and OpenSim; its own documentation points single-camera planar work to Sports2D. | Calibration, synchronization, triangulation, and OpenSim make it heavier than Stage 1. | Sports2D imports Pose2Sim utilities as a dependency. Disable its 3D conversion, augmentation and inverse kinematics; reserve measured 3D work for later validation. |
| MediaPipe Pose Landmarker 0.10.35 | What lightweight fallback is available? | It accepts decoded video frames, estimates 33 landmarks, and exposes detection/presence/tracking thresholds; it runs locally. | Its normalized/world outputs are learned estimates, not measured 3D anatomical joint centers. | Provide it as an offline fallback and store visibility/presence as model confidence metadata; compute only repository-defined 2D measurements. |
| MMPose 1.3.2 / RTMPose | What primary estimator best fits the Mac and data model? | RTMPose supports fast cross-platform inference, COCO/whole-body models, confidence scores, ONNX Runtime, CoreML, and CPU deployment. | General pose benchmarks do not establish cornhole biomechanical validity. | Use RTMPose through Sports2D/RTMLib with a reproducible CPU/ONNX configuration. Record model hashes and versions; do not expose unvalidated acceleration. |
| DeepLabCut 3.0.1 | When is a custom model useful? | It supports user-defined landmarks, refinement, video analysis, and Apple GPU use through PyTorch. | Requires project-specific labeled training data and a heavier research workflow. | Do not install by default; consider it only after labeled cornhole frames reveal systematic generic-model error. |
| Apple Human Interface Guidelines (reviewed 2026-09-06) | How should a native research app behave? | Sidebars expose top-level areas; toolbars hold frequent contextual actions; semantic controls/colors support accessibility and platform consistency. | HIG does not determine the scientific workflow. | Use `NavigationSplitView`, native menus/importers, semantic colors, keyboard commands, visible feedback, and progressive disclosure. |
| YouTube Terms of Service (reviewed 2026-09-06) | Can the app download arbitrary videos? | Content cannot generally be downloaded or automated outside permitted service features, rights-holder permission, or applicable law. | Legal exceptions are jurisdiction- and use-specific. | Stage 1 stores and opens source URLs/attribution only. Analyze a user-supplied local copy for which the user has rights; do not bundle a downloader. |
