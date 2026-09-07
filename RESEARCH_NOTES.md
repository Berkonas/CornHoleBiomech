# Research Notes

Research reviewed on 2026-09-06. This document separates evidence from design decisions. It is a scientific plan, not a claim that Stage 1 has already been validated.

## Research rationale

Primary question: **Can a single-camera, markerless 2D video-analysis system quantify upper-body cornhole throwing kinematics in a repeatable and interpretable way, normalize those measurements across athletes with different body sizes and proportions, and identify which movement features or deviations from a coach-selected reference pattern are associated with task performance?**

Secondary question: **For an individual athlete, are better cornhole outcomes associated more strongly with similarity to a reference technique, with consistency of their own technique, or with specific kinematic features such as elbow motion, arm trajectory, trunk orientation, and timing?**

Cornhole scores tell a coach what happened, but not why it happened. Laboratory motion capture can provide detailed biomechanics, but it is expensive, time-consuming, and impractical for routine training. If ordinary phone video can provide sufficiently repeatable upper-body kinematics, a coach could obtain individualized, evidence-based feedback during normal practice. The system must account for body-size differences, camera limitations, measurement uncertainty, and the possibility that more than one successful throwing strategy exists.

The course assignment requires real participant data and an evidence-based connection between how a movement is performed and its outcome. Public video may test software, but cannot satisfy that experimental requirement.

## Evidence table

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
| Sports2D 0.8.34 / reviewed commit `4392177` | What existing single-camera sports pipeline is closest? | Sports2D supports video pose estimation, confidence thresholds, interpolation, filters, 2D angles, TRC/MOT, annotated video, CPU/MPS, and Sports2D/Pose2Sim conventions. | Generic workflow; current saved TRC does not retain every raw confidence/correction provenance field needed here; cornhole outcomes/reference models are absent. | Follow compatible keypoint conventions and provide an adapter/import path, but own the raw/corrected data model and cornhole analysis. |
| Pose2Sim 0.10.49 / reviewed commit `65bbb05` | When is Pose2Sim appropriate? | Pose2Sim is a multi-camera 3D workflow using RTMPose and OpenSim; its own documentation points single-camera planar work to Sports2D. | Calibration, synchronization, triangulation, and OpenSim make it heavier than Stage 1. | Keep as a future 3D validation/Stage 2 route, not the Stage 1 runtime. |
| MediaPipe Pose Landmarker 0.10.35 | What lightweight fallback is available? | It accepts decoded video frames, estimates 33 landmarks, and exposes detection/presence/tracking thresholds; it runs locally. | Its normalized/world outputs are learned estimates, not measured 3D anatomical joint centers. | Provide it as an offline fallback and store visibility/presence as model confidence metadata; compute only repository-defined 2D measurements. |
| MMPose 1.3.2 / RTMPose | What primary estimator best fits the Mac and data model? | RTMPose supports fast cross-platform inference, COCO/whole-body models, confidence scores, ONNX Runtime, CoreML, and CPU deployment. | General pose benchmarks do not establish cornhole biomechanical validity. | Use RTMPose through RTMLib as primary, prefer MPS/ONNX where reliable, and always retain CPU fallback. Record model URL/hash/version. |
| DeepLabCut 3.0.1 | When is a custom model useful? | It supports user-defined landmarks, refinement, video analysis, and Apple GPU use through PyTorch. | Requires project-specific labeled training data and a heavier research workflow. | Do not install by default; consider it only after labeled cornhole frames reveal systematic generic-model error. |
| Apple Human Interface Guidelines (reviewed 2026-09-06) | How should a native research app behave? | Sidebars expose top-level areas; toolbars hold frequent contextual actions; semantic controls/colors support accessibility and platform consistency. | HIG does not determine the scientific workflow. | Use `NavigationSplitView`, native menus/importers, semantic colors, keyboard commands, visible feedback, and progressive disclosure. |
| YouTube Terms of Service (reviewed 2026-09-06) | Can the app download arbitrary videos? | Content cannot generally be downloaded or automated outside permitted service features, rights-holder permission, or applicable law. | Legal exceptions are jurisdiction- and use-specific. | Stage 1 stores and opens source URLs/attribution only. Analyze a user-supplied local copy for which the user has rights; do not bundle a downloader. |

## Scientific measurement specification

### Coordinate systems

Raw image coordinates use `x` increasing right and `y` increasing down, in pixels. Calculations first convert to a mathematical image frame, `x` right and `y` up. The trial records target direction (`leftToRight` or `rightToLeft`). A throw-centered frame then uses:

- origin: throwing shoulder for arm trajectories;
- positive horizontal: toward the target;
- positive vertical: upward in the image;
- scale: median high-confidence upper-arm length plus median high-confidence forearm length.

Coordinates in the throw-centered frame are dimensionless arm lengths. This removes translation, image scale, and a left/right-facing reflection from trajectory comparison. It does not remove perspective, camera-rotation, anatomical-proportion, or out-of-plane errors.

Board coordinates use inches on the board surface: origin at the lower-left corner when viewed from above from the pitcher's end, `x` across the 24 in width, and `y` toward the raised/hole end over the 48 in length. Clicks are explicitly approximate. The standard hole is centered at `(12, 39)` with radius `3` in.

### Landmark definitions

Required points are left/right shoulder, elbow, wrist, and hip. A markerless point is the model's image estimate of a landmark, not a ground-truth joint center. Mid-shoulder and mid-hip are confidence-weighted means only when both bilateral points are usable. Throwing-side shoulder/elbow/wrist supply arm measures. Opposite-side landmarks provide trunk context and quality checks.

### Angles and trajectories

For planar angle `ABC`, with `B` the vertex:

```text
u = A - B
v = C - B
theta = atan2(abs(u_x v_y - u_y v_x), u dot v)
```

`theta` is converted to degrees and lies in `[0, 180]`. Degenerate vectors yield missing data rather than zero.

| Quantity | Definition | Units | Interpretation and limitation |
|---|---|---|---|
| 2D projected elbow flexion angle | shoulder-elbow-wrist planar angle | degrees | Included angle in the image plane; not 3D elbow rotation. |
| Upper-arm orientation | signed angle of shoulder-to-elbow vector from throw-forward horizontal | degrees | Segment direction in the selected camera projection. |
| Forearm orientation | signed angle of elbow-to-wrist vector from throw-forward horizontal | degrees | Segment direction in the selected camera projection. |
| Arm relative to trunk | unsigned planar angle between shoulder-to-elbow and mid-hip-to-mid-shoulder | degrees | Upper-arm posture relative to projected trunk; not shoulder axial rotation. |
| Trunk inclination | signed angle between mid-hip-to-mid-shoulder and image vertical; positive toward target | degrees | Projected lean. Sensitive to camera roll and out-of-plane rotation. |
| Wrist trajectory | `(wrist - throwing shoulder) / arm_length` in throw-centered axes | arm lengths | Dimensionless shoulder-relative path. |
| Elbow trajectory | `(elbow - throwing shoulder) / arm_length` in throw-centered axes | arm lengths | Dimensionless shoulder-relative path. |
| Range of motion | maximum minus minimum over selected interval | degrees | Sensitive to missing extremes and event bounds. |
| Movement duration | corrected end time minus corrected start time | seconds | Precision limited by frame interval. |
| Angular velocity | time derivative of filtered, gap-limited angle samples | degrees/second | Not reported when sampling/filter/coverage quality fails. |
| Event timing | event time relative to corrected movement interval | percent cycle and frame | No claim of sub-frame precision. |
| Throw-to-throw variability | pointwise SD/median absolute deviation of time-normalized curves | native units | Within-athlete repeatability, not criterion validity. |

### Missingness, confidence, and correction

- Store raw model point `(x, y, confidence)` for every landmark/frame.
- A corrected point never overwrites the raw point.
- The effective point is corrected if present, otherwise raw if confidence passes the configured threshold.
- Short internal gaps may be linearly interpolated only up to the configured maximum. Interpolated values are labeled and can be regenerated or removed.
- Filtering applies after correction/gap handling. Raw, effective, interpolated, and filtered values remain distinguishable.
- Angles require all defining points. Low-confidence points propagate missingness rather than becoming plausible-looking zeros.

### Events

Automatic candidates are motion start, peak backswing, forward swing onset, release, peak follow-through, and motion end. The prototype uses filtered shoulder-relative wrist speed and target-axis position with conservative heuristics. Automatic and manual frame indices are stored separately; manual values take precedence without deleting automatic values. Release from video is an estimated visible release frame with uncertainty of at least one frame interval and potentially more under blur or occlusion.

### Filtering

Default: fourth-order low-pass Butterworth, represented as second-order sections and applied forward/backward (zero phase), cutoff 6 Hz for video at 60 fps or higher. For lower frame rates the cutoff is capped below 0.45 times sampling frequency. Filtering is skipped with a warning when a valid continuous sequence is too short. This is a starting setting, not a universal truth. The advanced panel exposes filter type/order/cutoff/gap limit; exports record the effective values. Pilot work should compare raw and filtered traces, run cutoff sensitivity (for example 4/6/8 Hz), and use residual/frequency analysis on representative trials.

### Time and body-size normalization

Selected movement is mapped to `tau = (t - t_start) / (t_end - t_start)` and resampled at 101 equally spaced values. Angles are scale invariant in ideal planar geometry. Relative trajectories are divided by the sum of median high-confidence upper-arm and forearm lengths. Raw pixels are never used in inter-athlete scoring. Normalization cannot remove all anatomical or camera differences, so athlete-specific analyses remain primary.

### Reference comparison

Normal time-preserving comparisons are computed first:

- MAE and RMSE for each angle curve;
- peak and range-of-motion differences;
- selected event timing differences;
- normalized wrist/elbow path RMSE;
- waveform correlation when coverage and variance are adequate.

Dynamic time warping, if enabled later, is secondary and labeled shape similarity; it never replaces the time-preserving result. Incompatible camera views are blocked.

The prototype Reference Similarity Score is an explainable convenience index, not performance quality. Each component uses the configured tolerance:

```text
component score = 100 * max(0, 1 - error / tolerance)
overall score = weighted mean of available component scores
```

Raw errors appear first. Default tolerances are explicitly provisional configuration values, not population norms. A single-trial result is labeled **Prototype reference similarity - single reference trial**. When several references exist, comparison uses their pointwise mean with a variability envelope and stores every contributing trial ID.

### Outcome and performance relationships

Each trial stores intended target, throw type, score category (3/1/0), notes, and optional approximate first-contact/final-rest board coordinates. If target and contact/rest are available, the system reports radial, longitudinal, and lateral error in board inches, with a manual-click precision warning.

Relationships are within-athlete first. Candidate features include elbow angle at release, elbow range, trunk inclination at release, wrist-path deviation, duration, normalized release timing, reference similarity, and consistency. The first analysis uses scatter plots, grouped summaries, and Spearman correlation. It reports sample size and never uses causal phrasing. Fewer than eight complete paired trials returns: **Not enough trials to estimate this relationship reliably.** Eight is a display safety threshold chosen for the pilot, not proof that eight trials give adequate statistical power; interval estimates will remain wide and must be interpreted cautiously.

## Camera protocol

1. Use a tripod or fixed stable support. Do not hand-hold or pan.
2. Select `Side` for primary Stage 1 analysis. Position the optical axis as perpendicular as practical to the throwing plane.
3. Keep shoulders, both hips, and the entire throwing arm visible throughout backswing, release, and follow-through.
4. Use adequate diffuse light, short exposure if available, and no changing digital zoom.
5. Record 60 fps or higher when available. Higher frame rate helps event timing only if exposure and pose quality remain adequate.
6. Reuse camera position, resolution, zoom, orientation, and athlete location when comparing trials.
7. Record throwing side, target direction, view, frame rate, and resolution.
8. Do not compare `Side`, `Front`, and `Other / Exploratory` measurements as if they were the same quantity.

## Validation plan

1. **Mathematical tests:** known 0, 45, 90, 135, and 180 degree vector angles, including degenerate input.
2. **Scale invariance:** scale synthetic skeletons by 0.5 and 2; angles and normalized paths must agree within floating-point tolerance.
3. **Translation invariance:** translate the entire skeleton; body-centered results must agree.
4. **Time resampling:** sample the same analytic movement at different frame counts; normalized curves must agree within a declared tolerance.
5. **Mirroring:** mirror a motion, reverse target direction, and switch throwing side; throw-centered measures must agree.
6. **Confidence:** a required low-confidence point must make its derived sample missing and reduce the quality score.
7. **Correction provenance:** corrections must change effective/derived data while raw values remain byte-for-byte recoverable; undo/reset is tested in the app model.
8. **Reference-set behavior:** pointwise mean/SD and single-reference labeling are tested.
9. **Video regression:** after the team records a consented pilot clip, freeze only expected high-level metrics and model/config hashes; do not place identifiable participant video in public source control.
10. **Criterion and reliability study:** compare manual digitization or laboratory reference measurements on selected frames, repeat analysis by raters/days, and report bias/agreement separately from repeatability.

## Risk register and boundaries

- Single-camera 2D cannot support shoulder internal/external rotation, humeral axial rotation, pronation/supination, or true 3D wrist rotation claims.
- Occlusion and motion blur are expected around release. Quality gating may make release variables unavailable.
- Model confidence is not a calibrated physical error in pixels or degrees.
- Similarity to one coach-selected trial is not evidence of performance quality.
- Observational within-person association does not establish causation.
- Manual board clicks and visible release frames do not justify false precision.
- A polished visualization cannot rescue an unsuitable camera view or poor tracking.
