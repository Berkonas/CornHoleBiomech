> Current release/flight/outcome behavior is specified in [FULL_THROW_METHODS.md](FULL_THROW_METHODS.md). It supersedes older launch filtering, release-confirmation and endpoint fallback descriptions below.

# Biomechanics methods

**Stage 1 measurement contract — updated 10 September 2026, app 0.4**

This document defines what Cornhole Biomechanics Lab may calculate and what each value means. It is the canonical specification for equations, units, coordinate systems, assumptions, and missing-data behavior. A field is reported only when the required observations and quality checks exist. Missing information stays missing; it is never replaced with zero.

Stage 1 is controlled, single-camera, **projected 2D kinematics**. It does not measure 3D joint rotations, forces, moments, torques, muscle activity, injury risk, or a universally correct throwing technique. Sports2D itself cautions that useful 2D angles require motion to remain near a sagittal or frontal plane and the camera to be parallel to that plane ([Sports2D documentation](https://github.com/davidpagnon/Sports2D)).

## 1. Coordinate and time conventions

Let a raw image point be `p_px = (u,v)`:

- `u` increases to image right;
- `v` increases downward;
- raw distance is in pixels.

Analysis coordinates first invert the image vertical axis, so `x` is image right and `y` is up. A trial metadata flag then reflects the horizontal coordinate when necessary:

`p_forward = (s*x, y)`, where `s` is `+1` or `−1` and **+x always points toward the target**.

The reflection is saved with the trial. It must not be inferred differently for separate metrics. Every export identifies the raw, analysis, and target-forward convention it uses.

For frame `f` and measured frame rate `fps`, `t = f/fps` seconds. For a reviewed movement bounded by frames `f_start` and `f_end`:

`tau = (f − f_start)/(f_end − f_start)`, with `0 <= tau <= 1`.

Normalized comparisons use 101 samples from 0–100% of the reviewed movement. Actual duration and event times remain available; time normalization must not erase them. Comparisons never bridge a long missing interval merely to fill the normalized grid.

## 2. Observations and provenance

Video preparation is non-destructive. Trim indices use the half-open source interval `[start, end)`; a prepared frame `f` maps to source frame `f + start`. Crop uses original decoded pixel bounds and is followed by an optional clockwise quarter-turn rotation. No rescaling, mirroring, stabilization, or speed adjustment is performed. The original and prepared hashes, bounds, rotation, and frame rate are saved in the sidecar and analysis manifest. Clips are transcoded with MPEG-4 and omit audio; compression may affect tracking and must not be confused with a lossless recording. Variable-frame-rate source timing is not preserved. Use known constant-frame-rate recordings for timed measurements. Review landmarks and events again after preparation; previous analysis and calibration are archived, not reused.

Body points are pose-model estimates, not palpated anatomical joint centers. For each landmark and bag centroid, the data layers remain distinct:

1. immutable automatic coordinates and model/tracker confidence;
2. manual corrections, with frame, author/source, and timestamp;
3. short-gap interpolation, with source frames and method;
4. effective coordinates used for derived calculations.

Manual edits never overwrite automatic results or inflate automatic confidence. Long gaps and rejected points remain missing. The effective release is the manual frame when one exists; otherwise it is the automatic candidate. Both values and their methods are retained.

## 3. Processing order

The required order is:

`raw estimates -> manual corrections -> confidence masking -> limited short-gap interpolation -> coordinate filtering -> angles/paths -> differentiation`

Coordinates are filtered before calculating angles or derivatives. Differentiating raw frame-to-frame pose or bag positions is not an acceptable release-speed method.

Bag samples beyond the explicitly reviewed-through frame are masked before zero-phase filtering. Otherwise a tracker drifting to the background after release could contaminate earlier values through the filter. Unreviewed centroids remain visible as diagnostic tracking data, but cannot enter bag trajectories, radial distances, automatic bag/wrist release detection, or launch calculations. Review extent is necessary, not evidence of accuracy by itself.

The pilot default is a fourth-order, zero-phase Butterworth low-pass filter at 6 Hz, implemented in second-order sections. This is a reproducible starting setting, **not** a universal biomechanical cutoff. The cutoff must be positive and below Nyquist (`fps/2`); filter order, cutoff, frame rate, finite-run behavior, and interpolation limit are saved. Too-short finite runs remain unfiltered or missing with a warning rather than being silently padded into a result.

[Challis (1999)](https://doi.org/10.1123/jab.15.3.303) supports choosing cutoff frequency from the signal/noise behavior of the data. It does not establish 6 Hz for markerless cornhole video. Representative real throws therefore require 4/6/8 Hz sensitivity analysis, with special attention to derivatives and event timing.

## 4. Body-size normalization

For throwing shoulder `S`, elbow `E`, and wrist `W`, robust projected arm length is:

`L_arm = median(||S−E||) + median(||E−W||)`

The medians use valid, quality-accepted frames. If either segment lacks adequate support or `L_arm <= 0`, normalized metrics are missing.

For a point `P`:

`P_norm(t) = [P_forward(t) − S_forward(t)] / L_arm`

Units are arm lengths. This removes image translation and uniform scale. It does **not** remove perspective, foreshortening, camera roll, out-of-plane motion, marker-location bias, or true differences in limb proportions. Raw pixels must not be compared between differently framed athletes.

## 5. Projected body angles

For the included planar angle `ABC`, with vertex `B`, define `a=A−B` and `c=C−B`:

`angle(A,B,C) = atan2(|a_x*c_y − a_y*c_x|, a dot c) * 180/pi`

Its domain is 0–180°. A missing point or zero-length vector produces a missing angle.

| Metric | Definition and unit | Reported interval | Interpretation and limitations |
|---|---|---|---|
| Projected elbow included angle | `angle(S,E,W)`, degrees | Waveform; release; forward swing; movement min/max/ROM | 180° appears straight and smaller values appear more flexed. It is not a 3D anatomical elbow angle. |
| Elbow extension deficit | `180° − elbow_angle_release`, degrees | Effective release | Describes projected departure from a straight elbow. A smaller value is not automatically better. |
| Elbow min, max, and ROM | finite `min(theta)`, `max(theta)`, and `max−min`, degrees | Reviewed movement; forward-swing summaries are labeled separately | Sensitive to missing extrema, event bounds, filtering, and view. |
| Upper-arm orientation | `atan2(E_y−S_y, E_x−S_x)`, degrees | Waveform, release, ROM, angular velocity | Counterclockwise from target-forward horizontal after reflection. Not humeral internal/external rotation. |
| Forearm orientation | `atan2(W_y−E_y, W_x−E_x)`, degrees | Waveform, release, ROM, angular velocity | Not pronation/supination or 3D wrist orientation. |
| Arm relative to trunk | `angle(E,S,M_S−M_H translated to S)`, degrees | Waveform and release | Unsigned projected relation between upper arm and trunk axis. It does not isolate a shoulder joint rotation. |
| Trunk inclination | `atan2(T_x,T_y)`, where `T=M_S−M_H`, degrees | Waveform and release | 0° is image-vertical; positive is toward target. Depends on bilateral shoulders/hips and camera roll; it is not a lumbar angle. |
| Projected angular velocity | derivative of an unwrapped, filtered orientation, degrees/s | Contiguous quality-accepted runs | Unwrap signed orientations before differentiating. Do not bridge gaps. Elbow angular velocity uses the filtered included-angle waveform without circular wrapping. |

`M_S` and `M_H` are the midpoints of left/right shoulders and hips. If a required bilateral point is unavailable, trunk-derived values are missing. Sports2D angle exports use their own named conventions; Cornhole Biomechanics Lab recomputes its authoritative metrics from saved pixels and retains upstream outputs only as diagnostic provenance.

## 6. Shoulder, wrist, and body translation

Global and shoulder-relative motion answer different questions:

- global wrist position: `W(t)`;
- shoulder position: `S(t)`;
- shoulder-relative wrist position: `W_rel(t)=W(t)−S(t)`;
- global wrist velocity: `v_W=dW/dt`;
- shoulder velocity: `v_S=dS/dt`;
- shoulder-relative wrist velocity: `v_rel=d(W−S)/dt=v_W−v_S`.

Displacement, path length, mean speed, and peak speed may be summarized over the reviewed movement or a named phase. Image-space outputs use px or px/s. Body-normalized outputs use arm lengths or arm lengths/s. Physical m or m/s is allowed only with valid athlete-plane spatial calibration.

This is a **projected kinematic decomposition**. It may describe how much of image-plane wrist motion accompanies shoulder translation versus arm motion relative to the shoulder. It is not a decomposition of force, power, impulse, or causal contribution.

## 7. Radial and pendulum-like descriptors

The following are descriptive geometry, not true moment arms:

`r_wrist(t) = ||W(t)−S(t)||`

`r_bag(t) = ||B(t)−S(t)||`

Normalize either by `L_arm` when comparing scale. A biomechanical moment arm requires a force vector and line of action; these video distances must therefore be called **shoulder-to-wrist radius**, **shoulder-to-bag radial distance**, **arm radius**, or **projected lever-distance proxy**, never torque or moment arm.

For the forward swing, pendulum-like descriptors are:

- mean, sample SD, range, and—only when mean radius is nonzero—coefficient of variation of `r_wrist/L_arm`;
- angular position `phi(t)=atan2(W_y−S_y, W_x−S_x)`;
- angular sweep `max(phi_unwrapped)−min(phi_unwrapped)` in degrees;
- angular velocity `d(phi_unwrapped)/dt` in degrees/s;
- simultaneous elbow-angle behavior.

A nearly rigid planar pendulum would have relatively stable radius, but a human throw includes elbow and shoulder motion and trunk translation. These values are labeled **exploratory descriptors**. Stable radius is not a quality judgment, and the raw values must precede any optional composite index.

## 8. Path shape

For consecutive valid points `p_i` in one continuous path:

`L = sum(||p_i−p_(i−1)||)`

`D = ||p_end−p_start||`

`straightness = D/L`, with `0 <= straightness <= 1`.

If fewer than two supported points exist or `L=0`, straightness is missing. A value near 1 means the measured path was direct between its endpoints; it does not mean the throw was better.

Additional, explicitly named descriptors may include:

- RMS orthogonal deviation from a least-squares forward path, in px or arm lengths;
- normalized trajectory RMSE between repeated throws, in arm lengths;
- local curvature, `kappa=|x' y''−y' x''|/(x'^2+y'^2)^(3/2)`, only from a quality-supported local fit and with the fit settings saved;
- pointwise path variability across compatible repeated throws.

Wrist/hand straightness is not applied to post-release bag flight as a technique target. Side-view projectile flight should arc, so `straightness=1` is neither expected nor preferred for the bag.

## 9. Events and phases

The event sequence is:

`motion start -> backswing -> forward swing -> release -> follow-through -> motion end`

Automatic values are candidates. The video reviewer may correct any event frame; the raw candidate remains preserved. Event frames must lie within the video and maintain the required order. Phase summaries use inclusive, explicitly recorded bounds.

When a trustworthy bag track exists, an automatic release candidate uses prior bag–wrist co-movement followed by a configurable separation threshold and **persistent** divergence over multiple frames, supported by forward motion and track quality. Thresholds, persistence window, and fallback reason are saved. When bag evidence is absent, a wrist-velocity heuristic may provide a lower-confidence candidate and must be labeled as such.

Temporal sampling resolution is one frame: `1000/fps` ms (about 16.7 ms at 60 fps; 8.3 ms at 120 fps). Displaying milliseconds converts a frame interval; it does not create sub-frame precision. Manual review can still be uncertain by more than one frame because of blur, occlusion, or an ambiguous visual separation.

## 10. Bag tracking

Bag tracking is semi-automatic by design. A manual seed with an image tracker or appearance/color tracker is acceptable; an object detector may be used only when its identity is reviewable. The tracker must never silently substitute a hand, shadow, or background object.

For every frame, retain:

- raw automatic centroid `B_auto=(x,y)`;
- tracker identity/method and configuration;
- confidence or an explicit quality state;
- manual corrected centroid, when supplied;
- interpolation provenance;
- effective centroid and missing reason.

The overlay and review screen are part of the measurement process. Low-confidence runs, abrupt implausible jumps, identity loss, and missing release-window points produce warnings. A bag-derived event or velocity is suppressed when its required track is not supported.

Automatic coverage is not treated as identity validation. The reviewer records the last frame whose bag identity has been checked in the separate correction document. A launch fit is permitted only when `reviewed_through_frame` reaches the final frame requested by the configured fit window. Changing the seed, adding/removing a centroid correction, or regenerating interpolation clears that approval in the native workflow. Until review covers the full interval, launch velocity, angle, acceleration, and release-position summaries remain missing with status `suppressed_unreviewed_track`.

## 11. Bag release position, velocity, and angle

Release position is the effective bag centroid at the effective release frame. Report its raw image position and, when possible, shoulder-relative position normalized by `L_arm`.

For the first several reliable post-release samples, fit local functions `x(t)` and `y(t)` using a documented robust linear or low-order polynomial estimator. Save the frames, polynomial order, weighting/robust method, residual, and exclusions. At release time `t_r`:

`v_x = dx/dt at t_r`

`v_y = dy/dt at t_r`

`speed = sqrt(v_x^2+v_y^2)`

`release_angle = atan2(v_y,v_x) * 180/pi`

In target-forward coordinates, positive `v_x` is toward the target and positive `v_y` is upward. Report projected forward velocity, vertical velocity, speed, and angle together with track/fit quality.

Without spatial calibration, velocity units are arm lengths/s for primary comparison and optionally px/s for diagnostics. A physical conversion uses a known object located approximately in the athlete/release motion plane:

`scale = known_length_m / observed_length_px`

`v_mps = scale * v_pxps`.

Record calibration object, known dimension, frames, plane, and uncertainty. The distant board must not be used as an athlete-plane scale unless a validated camera model accounts for perspective. Never label pixel-derived values m/s.

Acceleration is optional and exploratory. If frame rate, track coverage, and residual checks support it, use the second derivative of the saved local fit; do not difference noisy centroids. Report px/s², arm lengths/s², or calibrated m/s² with a prominent quality warning. Do not constrain measured vertical acceleration to `−9.81 m/s²`; a rotating/deforming bag has aerodynamics and tracking error.

## 12. View-specific measurement sets

| View | Stage 1 measurements that may be interpreted | Important exclusions |
|---|---|---|
| Side | Projected elbow and arm/trunk geometry; wrist/elbow paths; trunk inclination; movement timing; reviewed release; forward/upward bag velocity and angle; radial descriptors | Out-of-plane/lateral motion, axial rotations, physical depth |
| Front or rear | Mediolateral wrist/bag path; projected shot-line alignment; trunk lateral motion; projected arm-plane deviation; lateral release direction | Sagittal elbow geometry and side-view release angle are not interchangeable with side-view values |
| Other/unknown | Tracking review and explicitly exploratory image-space descriptions | No reference score or pooled biomechanics comparison unless a validation protocol defines compatibility |

Left/right side recordings may be reflected into a common target-forward axis only when their view labels and geometry are otherwise compatible. Front/rear and side trials are not pooled as identical measurements.

## 13. Cornhole outcome and board coordinates

The board coordinate system is top-down, viewed from the pitcher's end:

- origin: near-left deck corner;
- `x`: 0–24 in, left to right;
- `y`: 0–48 in, pitcher/front edge toward the back edge;
- nominal hole center: `(12,39)` in;
- nominal hole radius: 3 in.

These nominal values follow the ACL board geometry checked 8 September 2026. The current ACL rules allow manufacturing tolerances, so a study using physical board coordinates should measure the actual board. The saved ruleset and geometry date remain part of provenance.

Record independently: intended target `T`, first contact `C`, final rest `R`, per-bag value, and foul/dead-bag state. Manual clicks are approximate. When target and one named endpoint `P` exist:

`lateral_error = P_x−T_x` in inches (negative left, positive right)

`longitudinal_error = P_y−T_y` in inches (negative short, positive long)

`radial_error = sqrt(lateral_error^2 + longitudinal_error^2)` in inches.

Do not mix first contact and final rest into one response variable. ACL bag values are 3 through the hole, 1 lying on the board or hanging in the hole, and 0 otherwise/foul at the end of the round. This is a **single-bag value**, not the cancellation score awarded for a complete round ([ACL rules, checked 2026-09-08](https://www.iplaycornhole.com/about/acl-information/rules-regulations)).

## 14. Reference comparison

A reference is coach-selected, athlete-specific, or a compatible set; it is never called perfect form. Trials must match view, target-forward convention, throwing side handling, pose model, processing configuration, and normalized time grid.

Primary raw comparisons are:

- waveform MAE: `mean(|trial−reference|)`, degrees;
- waveform RMSE: `sqrt(mean(error^2))`, degrees;
- waveform correlation when both signals vary and at least three paired points exist;
- absolute peak and ROM differences, degrees;
- wrist/elbow path RMSE: `sqrt(mean(||p_trial−p_ref||^2))`, arm lengths;
- release timing difference, cycle fraction and frames/ms where frame rates permit;
- release-position difference, arm lengths;
- release-speed difference, only in identical valid units;
- release-angle difference, degrees, only for compatible views.

Orientation errors use the shortest signed circular difference. A reference set uses its pointwise mean and may show ±1 sample SD as a variability band; this is not a confidence interval.

The raw errors above are the comparison. The former weighted 0–100 similarity composite was removed on 22 Sep 2026 because its tolerances and weights had no empirical basis.

## 15. Personal consistency

Personal consistency describes repeatability, not quality. For compatible throws from the same athlete, calculate pointwise sample SD (`ddof=1`) and report raw summaries such as:

- RMS pointwise SD for elbow/trunk waveforms, degrees;
- two-dimensional wrist-path dispersion, arm lengths;
- release-time SD, frames, ms, and cycle fraction;
- release angle/speed variability in comparable units;
- elbow-at-release and trunk-at-release variability;
- board radial-error variability, inches;
- forward-path and normalized-radius variability.

Always show `n`, missingness, session, view, and settings. The software may require five throws before displaying a pilot composite, but five is not a scientifically justified universal sample size. Any 0–100 consistency index is secondary, exposes its tolerances, and cannot say whether the repeated motion is effective.

## 16. Movement–performance relationships

Analyze within athlete before pooling athletes. Candidate responses are the per-bag value or one explicitly named spatial endpoint/error. Candidate features include release elbow angle/deficit, elbow ROM, trunk inclination, timing, shoulder motion, normalized wrist path, straightness, radius variability, bag release position/speed/angle, reference error, and raw consistency measures.

Show the raw scatter, `n`, mean/median, SD or robust spread, missing/excluded trials, and units. Spearman rank correlation may be reported only when both variables vary and the configured minimum complete-pair count is met. A bootstrap interval is exploratory and records its method, resamples, and seed. The current eight-pair display gate is a software guardrail, not a power calculation or universal sample-size rule.

Do not use causal or prescriptive language. Acceptable wording is: “In this athlete's current sample, lower target error tended to occur with greater projected elbow extension at release.” It remains a hypothesis to test with more throws.

## 17. Quality, precision, and reporting

Every analysis exposes pose/tracker identity and version/hash where possible, fps, resolution, view, throwing side, target direction, confidence threshold, raw and usable missingness, longest gap, manual and interpolated point counts, filter settings, event source, bag-track quality, calibration method, and whether physical units are valid.

Model confidence is not percent accuracy. Tracking quality, reference similarity, personal consistency, and performance association are separate constructs. Display sensible precision—typically one decimal degree and no more time precision than the frame interval supports. Unit tests verify equations; task-specific validation is governed by [VALIDATION_PLAN.md](VALIDATION_PLAN.md).
