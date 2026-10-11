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

## 18. Scene, throw plane and body-to-outcome chain (METHOD_VERSION 2026.09.24-scene-b)

**Stage 2 measurement contract.** Everything in this section runs on top of Stage 1 (§1–17): the
same filtered pose, the same effective bag track. It adds a scene model (board, floor, athlete
masks), replaces "first contact" with a board/floor-gated classifier, and derives a body →
release → flight → outcome chain with an explicit `state` (`measured` / `estimated` / `unavailable`)
and a Monte Carlo uncertainty on every quantity. Design spec:
[measurement-engine-design.md](superpowers/specs/2026-09-23-measurement-engine-design.md). Pilot
regression results (26 clips, 3 athletes): [SCENE_REGRESSION.md](SCENE_REGRESSION.md).

### 18.1 Camera stabilization: ECC keyframe registration

Every clip is hand-held. ORB-keypoint + RANSAC similarity transforms alone captured only ~66% of
the true sub-pixel inter-frame motion on the pilot clips, so a chain of per-step ORB transforms
drifted 15–40 px over 200–350 frames. Each frame is instead registered directly to a keyframe with
intensity-based ECC (enhanced correlation coefficient) registration, initialised from the previous
frame's registration composed with the ORB step; per-step transforms (`to_prev[t]`, frame *t* →
*t*−1) are derived from consecutive keyframe registrations, so the transform chain telescopes
without accumulating drift. A new keyframe starts whenever the correlation with the current one
falls below `KEYFRAME_MIN_CC` (0.8; pilot clips never fell below 0.93). Registration is affine, not
similarity/Euclidean: with hand-held translation the floor/board and the far walls move
differently (parallax), and an affine fit of the whole frame kept the board within ~3.5 px where a
Euclidean fit left up to 9 px of residual on one pilot session. Measured on the 26 pilot clips:
residual against frame 0 fell from up to 51 px (ORB-only) to ≤ 4.6 px (44 of 52 spot-checked
patches ≤ 3 px). `to_prev` composed into a `reference_chain` maps any frame into any other frame's
pixel coordinates (`auto_bag.py`); it is the coordinate system the flight fit, the background
plate, the board corners and the athlete masks are all expressed in.

### 18.2 Athlete masks and background plate

A Swift/Apple Vision helper (`scene_vision`, `VNGeneratePersonSegmentationRequest`, quality
`.accurate`, every 2nd frame) writes per-frame person masks to a per-trial cache keyed by video
hash and `SCENE_REVISION`. Failure (helper missing, timeout, crash, unreadable cache) is
`status: "unavailable"` with a reason (including a cache whose mask or frame size is zero or
invalid); the pipeline falls back to unmasked motion-based tracking and flags it with a bag
warning ("Person masks were not used for automatic bag tracking (reason)"). An `auto_flight.json`
cached without masks while the helper was missing is recomputed once the helper is found — masking is never required for a result, only for suppressing bystanders and the
athlete's swinging arm from the background/bag-candidate steps.

The background plate (`background.py`) is the per-pixel median of stabilized frames with masked
athlete pixels treated as missing, in the release frame's coordinate system. Bag-candidate
detection compares each frame against the plate warped to that frame (in addition to the existing
three-frame differencing), which suppresses static bystanders, static reflections and camera-shake
"motion" that three-frame differencing alone cannot distinguish from a moving bag. Candidates
inside a person mask cannot seed a flight (a swinging arm is not the bag). Because the Vision mask misses small background people, the Sports2D adapter also writes `sports2d/bystanders.json`: per-frame boxes (keypoint extent + 0.15 × body height, held ≤ 10 frames over dropouts) around every pose-tracked person except the thrower (chosen as the largest steadily tracked body, `choose_thrower`). Candidates inside a box are tagged `in_person` (`scene.tag_bystanders`): they cannot seed but may extend a flight. `auto_flight.json` is recomputed when the wrist track, arm length or bystander boxes change.

### 18.3 Board detection

`board.py` looks for a red deck framed by a dark rim, or (the pilot boards' look) a dark near-side
apron with red deck showing along its top, on the background plate. HSV segmentation: red is
`h ≤ 10° or h ≥ 150°` (OpenCV 0–180° hue) with `S ≥ RED_MIN_SAT` (40) and `V ≥ 50`; dark is
`V ≤ 70`. The largest such quadrilateral is validated by solvePnP (IPPE, 4 coplanar deck corners at
the regulation slope) and by the hole: a black-hat filter inside the rectified deck must find a
dark blob within `HOLE_TOLERANCE_IN` (4 in) of the nominal hole centre (12, 39) in. Confidence is
`0.5 × shape_score + 0.5` if the hole agrees, else `0.5 × shape_score`; `found` requires confidence
≥ 0.75 **and** the front-near corner to have come from the image (not filled in from the PnP scan
at a nominal focal length) — a hidden front corner is reported as `not_found` with the reason
`"The board's front corner is hidden; click the four deck corners."`, because a synthetic check
showed the PnP-filled corner 15–21 px (3–4 in) off even while the hole still agreed.

**Pale-deck relaxed pass (Task 8c).** On the pilot library, 10 of 26 plates (8 of 11 for one
athlete) have a paler, smaller-looking deck — median saturation 26–34 versus 55–84 on the rest —
so no quadrilateral survived at `S ≥ 40`. When the standard pass finds nothing, `detect_board`
retries the **apron path only** (not the rim path) at `S ≥ 30`, then `S ≥ 25`
(`RELAXED_RED_MIN_SATS`), through the same PnP/hole/observed-corner gates. The apron path is
restricted to the relaxed thresholds because a threshold sweep on the pilot plates found rim
candidates giving a wrong "found" as low as `S ≥ 20` (a pink TV-screen banner scored 1.0 and beat
the real board by 810 px on one plate), while the apron-only path gave no wrong "found" down to
`S ≥ 10` and every relaxed-pass quad landed within 5–7 px of the same board's quad found at the
standard threshold. With this cascade, board-found rate on the 26 pilot clips went from 16/26 to
26/26 (every quad checked by eye against the video); see
[SCENE_REGRESSION.md](SCENE_REGRESSION.md) for the full before/after table.

Output: 4 deck corners (propagated to every frame via §18.1's stabilization), hole centre, a floor
line through the front-leg base, the image→deck-inches homography, the out-of-plane angle φ of the
throwing line (> 20° flagged, not corrected — Sih, Hubbard & Williams, 2001), and confidence.
Precision is reported separately along-deck versus across-deck (in/px), since the pilot camera
angle strongly foreshortens the across-deck axis.

### 18.4 Scale: gravity-calibrated field of view, session and library pooling

A single still frame cannot separate a wide lens seen from close up from a narrow lens seen from
far away — both project the same board corners for a suitable camera distance, but disagree about
the metric scale of everything else in the frame. `calibrate_hfov_from_flight` breaks that
ambiguity: it searches the plausible horizontal-field-of-view range (55–75°) for the value whose
board-plane vertical acceleration, from the flight's own quadratic fit, matches gravity
(−9.80665 m/s², independent of lens). A root strictly inside the range gives `status: "measured"`;
if the fitted acceleration never crosses −g inside the band, the closer edge is used with
`status: "estimated"`; too few flight points, or too few HFOV samples where the PnP pose actually
solves, falls back to the nominal 65° with `status: "estimated"`. The scale (pixels/metre) is
evaluated at the flight's release point, and its value at the 55° and 75° band edges is retained so
downstream quantities can express a scale relative-SD from the disagreement between the two edges.

A single throw's ~0.4 s flight gives a noisy per-throw HFOV (spread of 10+° between throws filmed
from the same fixed camera position). `pool_session_camera_files` groups a library's throws into
recording sessions (same athlete, same recording date: a `recording_date` stated in the manifest's
trial context, else the source clip's file modification date — the video container's creation
time is not read) and pools each session's own *measured*
per-throw HFOVs with a median; the pool is `status: "measured"` only with ≥ `MIN_SESSION_THROWS`
(3) measured throws and an IQR ≤ `MAX_SESSION_IQR_DEG` (6°), otherwise `"estimated"` with a reason.
A session whose recording date is unknown (or whose members span more than one date) is capped at
`"estimated"` with that reason, since the throws cannot be confirmed to share one camera setup.
A session with fewer than 3 measured throws falls back to the median of every measured throw across
the whole library run (`source: "library_median_gravity_fov"`), which assumes the same camera and
zoom in every session. That assumption is not verified, so this fallback is at most `"estimated"`
(spec §8), with the assumption as the reason; `pool_status` keeps the pool's own median/n/IQR
verdict. `regression_check.py` runs
this as an explicit two-pass flow: pass 1 analyses every throw (so each throw's own `results.json`
carries its own per-throw calibration), pooling writes a `camera.json` into every session member,
and pass 2 re-analyses every throw so `_board_scale` (`pipeline.py`) picks up the pooled field of
view.

The board's throw-plane scale becomes the pipeline's legacy spatial calibration (Stage 1
`bag_release_speed_m_s`, `physical_units`) only when the scale is `"measured"` **and** the throw
line's out-of-plane angle is measured (`phi_status == "measured"`, φ ≤ `MAX_PHI_DEG`); otherwise a
warning states why and those values are not labelled measured from the board.

Every metre-based chain quantity is at most `"estimated"` when this scale is not `"measured"`; the
scale's relative-SD (used for the chain's Monte Carlo, §18.9) is the larger of a fixed floor
(`MIN_SCALE_REL_SD`, 1%) and a quarter of the relative spread between the 55° and 75° band-edge
scales (≈ ±2 SD), or half the relative spread across the pooled session's HFOV IQR when that is
available and larger.

### 18.5 Bag flight acceptance: stabilized-RMS

Motion candidates (camera-compensated three-frame differencing, background-plate differencing,
person-mask exclusion) are fit by RANSAC to a projectile: `x(t)` linear, `y(t)` quadratic with
downward (image +y) curvature toward the target, with the fitted image "gravity" required to be
plausible for the athlete's projected arm length. The residual used for acceptance is computed
**after** removing camera motion (§18.1's `to_prev` chain) — a whole-flight RMS residual of the
detections against the fitted parabola in the *release-frame, camera-motion-removed* coordinate
system, not raw video pixels. This separates genuine tracking scatter from hand-held camera shake,
which would otherwise inflate the residual and reject good flights. The flight is `"accepted"` only
if it clears every gate simultaneously: ≥ `MIN_INLIERS` (12) frames, ≥ `MIN_SPAN_SECONDS` (0.25 s),
≥ `MIN_COVERAGE` (60%) of frames within the flight span, a plausible trajectory, ≥
`MIN_TRAVEL_ARM_LENGTHS` (4) arm lengths of travel toward the target, and stabilized RMS ≤
`MAX_RMS_ARM_LENGTHS` (0.08 arm lengths, i.e. proportional to the athlete's own scale, not a fixed
pixel count). Any failed gate makes the flight `"needs_review"` with every reason listed; results
are never silently used.

### 18.6 Contact: board-gated classification and the 2-frame near-contact rule

The flight fit's end frame is a **candidate**, not an observed contact. `contact.py` maps that
point into the board's throw plane (`surface_at`) and classifies it as `"deck"` (within the deck
footprint, expanded by half a bag width at each end for a bag overhanging an edge, and within
`DECK_TOLERANCE_M`, 6 cm, of the deck surface height at that point), `"front"` (the board's front
face), `"floor"` (within `FLOOR_TOLERANCE_M`, 6 cm, of floor height) or `"air"`. Only `"deck"`,
`"front"` and `"floor"` are `contact.state == "measured"`; `"air"` becomes `contact.kind ==
"lost_in_flight"`.

**2-frame near-contact rule.** A descending track (fitted vertical velocity growing in image +y at
the last tracked frame) that ends within `NEAR_CONTACT_FRAMES` (2) frames of its own predicted
surface contact is still counted as a **measured** contact at the last tracked frame, rather than
`lost_in_flight`. This was added after a pilot throw landed off the board centreline: its last
observed point read "0.14 m above the floor" in the throw plane (a few centimetres outside the 6 cm
floor tolerance, because an off-centreline landing maps to a slightly wrong plane height), while
the predicted contact — extending the same fitted parabola one more frame — landed on the floor
immediately after. The contact **frame** is the observed last tracked frame, but the landing
**position** is the point where the fitted parabola meets the surface (`contact.surface_point_px`;
`landing.position_basis: "predicted_surface_point"`), because the last tracked point is still up to
2 frames in the air (`AUTO_BAG_REVISION` `auto_motion_parabola_v13_near_contact_surface_point`).
Requiring the parabola to actually reach a surface within 2 frames, on a track
that is still descending, distinguishes "the tracker stopped one frame early on a real landing"
from "the bag genuinely left the frame or the detector lost it in the air".

**Predicted contact.** When neither rule applies, the fit is `lost_in_flight`: `predict_contact`
extends the fitted parabola frame by frame (through the same camera-stabilization chain) to the
first frame whose plane position is not `"air"`, up to `MAX_PREDICT_SECONDS` (1.5 s) or the end of
the clip. This is always `state: "estimated"`, is excluded from measured-landing statistics, and is
spot-checked against the video before being trusted (§ regression acceptance criterion 3). Every
`auto_flight.json` reports `first_contact_frame` (only for a measured contact), `contact` (kind,
state, plane position, reason) and, when unavailable, `predicted_contact` (frame, plane position,
reason).

### 18.7 Suggested outcome

`suggest_outcome` proposes a 0/1/3 bag value from the post-contact track, always
`needs_confirmation: true` (a coach click is required, never auto-scored): 3 if the bag's path
after contact disappears within `HOLE_VANISH_RADIUS_IN` (4 in = 3 in hole radius + 1 in tracking
slack) of the nominal hole centre; 1 or 0 by whether the bag's tracked final-rest position lands
inside the 24×48 in deck rectangle; `None` with a reason ("no post-contact track" / "final rest not
found") when neither can be determined. The basis sentence (deck coordinates or "disappeared at the
hole") is retained alongside the score so a coach can see why it was suggested.

### 18.8 Release: first flight centroid beyond the hand

**Definition.** Release is the first refined bag centroid in the chosen flight that lies more than
`IN_HAND_ARM_LENGTHS` (0.45 projected arm lengths) from the throwing wrist landmark; earlier flight
points are dropped as still-in-hand and the parabola is refitted on the remainder. This replaced an
earlier definition (the flight fit's own first point) after a dedicated audit.

**Why.** A visual audit (`scripts/release_audit.py`, `docs/release_audit_visual.json`) judged the
true release frame by eye on all 21 accepted pilot flights (contact sheets of release−8…release+3,
2× crops on the hand point, each visual judgement a 2-frame range because motion blur at the
fingertips makes finer resolution impossible). Against that audit, the *previous* release rule
(first flight-fit frame) was within ±1 frame of the visual range on only 16/21 throws, and was
**early by 2–3 frames on 5/21** — the bag was still visibly in the fingers at the detected release,
because its last in-hand frames lie on nearly the same parabolic arc as the free flight that
follows, so the flight fit accepted them; the in-hand gate had only been applied while extending
the flight backwards, never to the fit's own first points. Dropping in-hand points from the fit's
own start fixed this: **21/21 throws land within ±1 frame of the visual range (19 exact), mean
error +0.10 frame, SD 0.30 frame** (`docs/SCENE_REGRESSION.md`, "Release onset audit"). The 0.45
arm-length in-hand radius is the same constant the backward-flight extension already used, and was
not re-tuned for this result: 0.40 and 0.45 arm lengths score identically, 0.50 also scores 21/21
within ±1 but with fewer exact matches.

`release_onset.status` records what happened: `applied` (frames dropped), `no_in_hand_points` (the
flight already started beyond the hand), `capped_min_inliers` (dropping more points would leave
fewer than `MIN_INLIERS`), or `no_wrist` (the check could not run, no wrist landmark). An automatic
release whose status is `no_wrist` or `capped_min_inliers` is graded at most WARNING.

**A second, independent cue** (`release_check`, "backward flight meets the wrist" — where the
fitted parabola, traced backward, crosses the wrist path) remains a cross-check only, not the
release definition: on the corrected data it runs 1–4 frames *before* release (the release window
grade: GOOD ≤ 4 frames, WARNING 5–6). The window widened by construction after the correction moved
release later on 7/21 throws (5 of them by +3 to +4 frames), which is why GOOD's threshold moved
from 3 to 4 frames rather than being kept fixed.

### 18.8a Working resolution and backfill to the hand (METHOD_VERSION 2026.09.27-working-1080p)

`auto_bag.auto_track_bag` searches clips taller than `WORKING_HEIGHT_PX` (1080) on frames resized by $s = 1080/h$ and maps the result back with `to_source_pixels` (lengths × 1/s, areas × 1/s², `camera_to_release` translations × 1/s, `plane_H` → S·H and `deck_H` → H·S⁻¹ with S = diag(1/s, 1/s, 1)); inputs (wrist, arm length, bystander boxes, clicked corners) are scaled by s, and `plate.jpg` is re-saved at source size so corners clicked on it stay in source pixels. `bag_segment.backfill_to_hand` fills the frames between the hand and the first detection by colour segmentation at projectile-predicted positions (fixed image gravity from the flight fit; acceptance as for gap re-acquisition; stops before the 0.45-arm-length hand zone, after 2 misses or 0.5 s; METHODS_AND_MATH §1.6); `centroid_sources.backfilled_mask` counts them. `bag_segment.extend_to_contact` (called by `auto_bag._grow_to_contact`, introduced in revision `auto_motion_parabola_v17_forward_to_contact`) does the same forward, from the last tracked centre to the deck/floor, with position, size, colour and person-region gates, up to 6 missed frames and the same physics re-check; `centroid_sources.extended_mask` counts those frames and `forward_extension` reports why the walk stopped (METHODS_AND_MATH §1.6). Player 1 4K session: accepted flights 0/10 → 10/10, boards 2/10 → 10/10; the 26 1080p pilot clips are checked against the previous commit in the change log.

### 18.9 Chain quantities (`chain.py`, `mechanics.py`)

Coordinates are the board's 2D throw plane (§18.3): x horizontal toward the board with the front
edge at x = 0, y height above the floor, SI units via §18.4's scale. Every quantity is
`{value, unit, state, formula, reason, interval, assumptions}`; `state` is `measured`, `estimated`
(with a reason) or `unavailable` (with a reason), and `interval` is a Monte Carlo 95% interval
(2.5th–97.5th percentile of 500 draws per throw, §18.10) when the value is numeric.

| Link | Quantity | Formula | State notes |
|---|---|---|---|
| Body | Shoulder angle, elbow included angle | `angle(A,B,C)` (§5), on the 6 Hz filtered pose | measured whenever the release/forward-swing pose is present |
| Body | Shoulder/elbow peak angular velocity, time relative to release | derivative of the filtered angle; search window forward-swing-start … release + 0.1 s | `unavailable` ("peak at the edge of the search window") if the extremum sits exactly on either edge — not a real peak |
| Body | Wrist speed at release, peak timing | 1st derivative of the filtered wrist, `timing.py` | reused from Stage 1 |
| Body | Peak sequence (shoulder → elbow → wrist-speed → release), lags in ms | ordering of the above peak times | **described, not graded** (Putnam 1993: fast throws; cornhole is a slow accuracy swing); 1 frame = 16.7 ms resolution |
| Release | Hand-point (bag proxy before release) speed, acceleration, velocity angle, tangential acceleration, direction rotation rate | hand point = wrist + `HAND_OFFSET_ARM_LENGTHS` (0.34 arm length) along the forearm; 1st/2nd derivative | metre-based, so capped by scale state |
| Release | Release speed, angle, height | existing ballistic flight fit + its standard error | angle "estimated" if φ > 20° (§18.3) |
| Mechanics (bag-only) | Momentum **p = m v** | `mass_kg × velocity` | mass ~ Uniform(15.5, 16.0 oz) in the Monte Carlo |
| | Kinetic/potential/mechanical energy | `KE = ½ m v²`, `PE = m g h` (h above the floor line), `E = KE + PE` | |
| | Net force on the bag **F = m(a_bag − g⃗)**, g⃗ = (0, −9.81 m/s²) | `a_bag` from the hand point's 2nd derivative over the forward swing; peak `|F|`, mean `|F|`, direction | **bag-only** (§18.11); direction `measured` only when the peak force is measured *and* its own 95% interval half-width < 15° (`MAX_DIRECTION_HALF_WIDTH_DEG`) |
| | Power on the bag **P = F·v_bag** | dot product over the forward swing | reported `measured`/`estimated` only when it agrees with `dE/dt` within 10% of peak `F·v` (`MAX_POWER_DISAGREEMENT`); otherwise "estimated (power estimates disagree)" |
| | Energy match, speed margin over minimum | `100(v²/v_req² − 1)`, `100(v/v_min − 1)`; `v_req`/`v_min` from the closed-form projectile-vs-hole solution | always `estimated`: assumes drag-free flight (Venkadesan & Mahadevan 2017: the most accurate throws sit slightly above the minimum, not at a fixed ideal) |
| | Release-timing sensitivity | Jacobian of drag-free landing w.r.t. (v, θ, h, x) at the bag's fitted release, dotted with the hand point's rates at release, × 10 ms | see §18.12 — unavailable on all 21 pilot throws |
| Flight | Predicted landing (drag-free) vs measured landing error | `mechanics.along_error_m` at the fitted release state vs the observed contact (§18.6) | always `estimated` for the prediction; the measured value needs a `measured`-state contact |
| Outcome | Along-deck error to the hole, deck coordinates, suggested 0/1/3 | §18.6/18.7 | measured-contact only |

Second-derivative quantities (hand acceleration, force, power) are `measured` only when their 95%
interval half-width is below 25% of the value (`MAX_RELATIVE_HALF_WIDTH`; Winter, 2009 —
differentiation amplifies landmark noise), otherwise "estimated" with that reason.

### 18.10 Monte Carlo inputs

Every chain quantity's uncertainty is a 500-draw (`MC_DRAWS`) Monte Carlo per throw, over:

- **scale**: a common multiplicative factor `N(1, relative_sd)` applied to speed, height and
  distance-to-board draws, where `relative_sd` comes from §18.4 (band-edge spread or session IQR
  spread, floored at 1%, defaulting to 5% only when the scale block reports no uncertainty at all);
- **bag mass**: `Uniform(15.5, 16.0 oz)` (`BAG_MASS_RANGE_KG`), nominal 15.75 oz (≈ 0.4465 kg);
- **ballistic fit covariance**: the flight fit's own standard errors on release speed, angle and
  height are added as independent normal draws before the scale factor is applied;
- **landmark noise**: `LANDMARK_NOISE_PX` (4 px on the pilot's ~300-px-tall athlete) converted to
  metres by the scale, added as 6 Hz-filtered white noise to each of the shoulder, elbow and wrist
  joint draws before the hand point and its derivatives (acceleration, force, power, the release
  rates used by timing sensitivity) are recomputed from them.

Draws propagate through the same closed-form projectile/energy formulas as the nominal value, so
the reported interval already reflects any nonlinearity (e.g. required speed, timing sensitivity).
Second-derivative and direction quantities (§18.9) use their own interval half-width, not just the
scale/landmark draws, to decide `measured` vs `estimated`.

### 18.11 Bag-only labelling rule

Every mechanics row under "Mechanics (bag-only)" in §18.9 carries the note: *"Bag-only: net
external force/power on the bag. Not a muscle, joint or hand-contact force, and says nothing about
shoulder or elbow loading."* The rigid hand-point model (§18.8, §18.12) approximates where the bag
is while still in the hand, not a measured hand force; force/power values describe the bag's own
momentum and energy budget, never a joint or muscle quantity.

### 18.12 Timing sensitivity: definition and why it is unavailable on the pilot footage

**Definition** (Nasu, Matsuo & Kadota, 2014; Hore & Watts, 2011): the change in drag-free landing
position (inches) per 10 ms of earlier/later release, computed from the Jacobian of the landing
model with respect to release speed, angle, height and along-board position, dotted with the hand
point's own rate of change of those quantities at release (`chain.timing_sensitivity_in_per_10ms`).
It requires the hand path's velocity direction at release to be within `MAX_HAND_BAG_ANGLE_DIFF_DEG`
(10°) of the bag's own fitted release angle — otherwise the hand point cannot stand in for the
bag's rate of change and the quantity is withheld with that reason. A non-finite hand direction or
rate (a stationary or missing hand path) makes it `unavailable` before that gate is applied.

**Why it is unavailable on all 21 accepted pilot throws.** The release-onset audit (§18.8) measured
the hand-point direction against the bag's fitted release angle at the visually judged release
frame on every throw: the hand path is **27–47° steeper than the bag's actual departure angle**
(median 38°), on all 21 throws — far outside the 10° gate. The rigid hand-offset model (wrist +
0.34 arm length along the forearm) tracks where a bag rigidly attached to the forearm would be; in
the last ~50–80 ms before release the real bag leaves along a shallower path than that point,
while the model's tracked point is already turning upward into the follow-through. Two causes are
not separable with body-only landmarks: genuine finger/wrist action (unmeasured — no hand
landmarks at this resolution, §18.13) and lag of the 6 Hz-filtered wrist in motion-blurred frames
(the wrist ring visibly trails the true wrist after release on the audit's contact sheets). Using
the bag's own *post-release* path instead would give the ballistic flight's rates, not the rates of
a hypothetically later or earlier release, so it cannot substitute. Timing sensitivity therefore
needs a direct measurement of the hand/bag path in the final frames of contact — a hand keypoint
model, or bag tracking continued while still in the hand — which this pass does not add.

### 18.13 Within-athlete analyses (`chain_analysis.py`, spec §6)

All analyses are within one athlete, across repeated throws; wording is associational, never
causal ("§16" of this document already sets that convention for Stage 1). Variables are
pre-specified (fixed lists in `chain_analysis.py`, not chosen after seeing the data), correlation
claims need ≥ 8 throws (`MIN_THROWS`) with both variables varying, and group comparisons need ≥ 5
throws per group (`MIN_PER_GROUP`); every analysis reports `status` so the UI never displays a
finding without enough throws. Every block also reports `value_states`: how many of the values it
used were `measured`, `estimated` or of `unknown` state (a throw analysed before states were
recorded), from each throw's chain states (`chain_states` on the athlete rows).

1. **Release → landing error budget** (`error_budget_analysis`). Central-difference Jacobian
   ∂(landing)/∂(speed, angle, height) at the athlete's mean release condition, giving `σ_R² ≈
   Σ(∂R/∂q · σ_q)²` under an independence assumption (`shares_if_independent`). Next to it: a
   **covariance-aware** check using the athlete's actual release covariance matrix, `predicted_sd_cov_in
   = √(J Σ Jᵀ)`, and the resulting `covariation_reduction = 1 − predicted_sd_cov / independent_sd` —
   the share of independent-variable landing spread that the athlete's own speed/angle/height
   covariation removes. When `covariation_reduction` exceeds `COVARIATION_MATERIAL` (0.15), the
   sentence names the dominant co-varying pair (the pair whose cross term contributes most
   negatively to the variance). `predicted_sd_in` is the SD, across throws, of each throw's own
   release condition run through the (nonlinear) drag-free model directly — the headline number,
   with no independence or linearisation assumption — reported next to the measured landing
   spread. Like every other claim it needs ≥ `MIN_THROWS` throws with a predicted landing
   (`predicted_status: "insufficient_data"` otherwise); `predicted_n` is always shown. (Venkadesan & Mahadevan, 2017; Müller & Sternad, 2004 for the tolerance–noise–covariation
   framing.)
2. **Predicted vs. measured landing** (`predicted_vs_measured`). Pearson r² between the drag-free
   prediction and the measured landing error; the unexplained remainder is attributed, without
   separating them, to bag slide, air drag and measurement error.
3. **Body → release** (`body_release_links`). Spearman ρ with a 2000-resample bootstrap 95% CI
   (Bonferroni-corrected across the 5 pre-specified pairs) for: peak elbow extension velocity vs.
   release speed; peak shoulder angular velocity vs. release speed; shoulder angle at release vs.
   release angle; elbow angle at release vs. release angle; hand speed at release vs. release speed
   (flagged near-tautological — the bag is essentially at the hand at release, so this mostly
   reflects measurement geometry).
4. **Movement → outcome** (`outcome_links`). Cliff's δ (scored vs. miss, Bonferroni-corrected across
   the pre-specified outcome-variable list) plus a rank correlation between each variable and
   |landing error| (usable even with few misses). This is also where **timing strategy** (spec §6
   item 6) lives: `chain_timing_sensitivity_in_per_10ms` is one of the pre-specified
   `OUTCOME_VARIABLES`, so its distribution and its association with scoring go through the same
   gated Cliff's-δ/rank-correlation machinery as every other outcome variable, rather than a
   separate function — unavailable on the pilot data (§18.12).
5. **Consistency** (Stage 1 §15, reused unchanged) and **speed–angle trade-off**
   (`speed_angle_tradeoff`, Theil–Sen slope of release speed vs. angle with a 95% CI; Linthorne,
   2001 — the best angle is athlete-specific, so the analysis reports a slope, not a target angle)
   and **shoulder–elbow coordination variability** (`coordination_variability`): point-wise SD of
   the stacked, time-normalised shoulder–elbow angle–angle curves across throws (curves with > 20%
   missing samples dropped), plus each kept throw's RMS deviation from the athlete's own mean
   curve.

### 18.13a Release confirmation, flight review and reanalysis (METHOD_VERSION 2026.09.24-scene-b)

- **Unconfirmed release.** When the release frame is an automatic candidate (not confirmed by a
  person), every release-dependent chain quantity is capped at `"estimated"` with the reason
  "Release is an automatic candidate; confirm visible separation…", and its flattened `chain_*`
  summary (plus `release_to_board_front_m`) is nulled with the legacy release-dependent summaries,
  so it never enters athlete analyses. Only the observed landing error
  (`measured_along_error_in`) is release-independent.
- **Flight & scale review over an accepted automatic flight.** An explicit blank first contact
  records `contact_state: "manual_unseen"` (no contact frame; the automatic contact is not used,
  with a warning) — never `"measured"` with a null frame. An unchecked fixed-camera box does not
  discard an accepted automatic flight whose camera motion was removed (per-frame
  `camera_to_release` transforms and stabilized points): its board scale and fits are kept,
  `manual_fixed_camera: false` is recorded, and a warning says why.
- **Reanalysis.** An accepted automatic flight of the current revision is re-derived through the
  same path as a first analysis, so clicked board corners (`board_corners.json` with its reference
  frame) take effect on reanalysis.
- **Nominal-FOV diagnostic.** `apparent_gravity_m_s2_at_nominal_hfov` is omitted (None) when the
  board pose cannot be solved at the nominal 65°, instead of failing the analysis.

### 18.14 Force-direction 15° rule

The net-force-on-bag direction (§18.9) is `measured` only when two conditions both hold: the peak
force magnitude itself is `measured` (§18.9's 25% relative-half-width rule), and the direction's
own Monte Carlo 95% interval half-width is below `MAX_DIRECTION_HALF_WIDTH_DEG` (15°). Direction
draws wrap around the nominal value (`(draw − nominal + 180°) % 360° − 180°`) before the interval is
taken, so a direction near ±180° is not artificially split into two clusters.

### 18.15 Not reported (spec §7)

The following are explicitly not calculated, because a single hand-held side camera and body-only
pose landmarks cannot support them: joint moments; joint or muscle forces (the bag-only mechanics
in §18.9/§18.11 are never relabelled as these); wrist flexion or "wrist snap" (no hand/finger
landmarks at this resolution); trunk axial rotation; lateral release direction (invisible to a side
camera — lateral error is measured only on the board itself, from the top-down deck coordinates);
bag spin.
