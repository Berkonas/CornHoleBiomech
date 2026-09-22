# Full-throw measurement contract

This is the authoritative supplement for the September 2026 revision. It supersedes older descriptions of first-contact/final-rest fallback, unconfirmed release metrics and filtered bag launch fits. Body-angle equations, anatomical landmarks and filtering details remain in [BIOMECHANICS_METHODS.md](BIOMECHANICS_METHODS.md). Scored-versus-miss statistics are defined in [METRICS.md](METRICS.md).

## Scientific question and metric hierarchy

Study **within-athlete associations** between projected body configuration, release conditions and observed performance. Similarity to a professional player is not performance. A tightly grouped set of misses is consistent but inaccurate. Tactical blocks may be effective without entering the hole.

Results opens with a three-line athlete summary (result → what differed between scored throws and misses → next practice). Below it are this throw's release values: angle ± fit uncertainty, speed, height and elbow at release. Then come the scored-vs-missed dot plots, flight path and board map. Body waveforms, velocity components and provenance are in Advanced. No composite 0–100 scores are computed or shown; reference, consistency and tracking indices were removed on 22 Sep 2026.

No red/yellow/green movement thresholds or colored personal zones are assigned. The scored-vs-missed comparison reports group medians, quartiles and Cliff's δ, and claims a difference only under the rules in the table below. Scored versus missed describes scoring categories, not universal tactical success.

## Definitions and traceability

| Metric | Classification, units | Definition / required observations | Scientific purpose and limitations | Code |
|---|---|---|---|---|
| Observed bag value | Measured by observer; 0, 1, 3, or unknown | Explicit observation, independent of pose, contact point or tracker | Task outcome; single-bag value, **not** cancellation score. Immediate video result may differ from end-of-round value after other bags interact. Record that distinction in notes. Unknown stays null. | `models.TrialOutcome`, `outcomes.outcome_summary` |
| First-contact target error | Derived; in | Observed deck contact C and intended target T: dx=Cx−Tx, dy=Cy−Ty, r=√(dx²+dy²) | Accuracy at first collision. Negative dx = left, negative dy = short from pitcher perspective. No substitution of final rest. Ground misses have no deck-plane coordinate. | `outcomes.point_errors` |
| Final-rest target error | Derived; in; research export | Same formula, with R rather than C | Includes slide/bounce/roll and interaction. Kept distinct from projectile landing. | `outcomes.outcome_summary` |
| Elbow at release | Derived from estimated pose; degrees | angle(S−E,W−E), evaluated at manually confirmed release; 180° straight | Arm configuration producing release. Filtered projected landmarks, not 3D anatomical rotation. | `geometry.vector_angle_degrees`, `kinematics.calculate_kinematics`, `pipeline.analyze_trial` |
| Projected release velocity and speed | Estimated; px/s, arm lengths/s, optionally m/s | Short-window robust quadratic x(t), y(t); velocity is first derivative at reviewed release, speed=√(vx²+vy²) | Links arm motion to flight; requires reviewed bag identity and contiguous non-interpolated observations. Motion relative to a moving camera is image motion, not world velocity. | `bag.estimate_projectile_release_kinematics` |
| Projected release angle | Estimated; degrees | atan2(v_up,v_target) × 180/π | Relative to image horizontal after target-direction reflection. Physical launch elevation additionally requires a level, perpendicular, stationary side camera. Never pool front/oblique views. | same |
| Release position relative to shoulder | Derived from estimated centroids/pose; arm lengths | (B−S)/L in target-forward/upward image axes | Body-to-bag geometry. Shoulder-relative vertical position is **not height above ground**. | `pipeline.analyze_trial` |
| Release-to-first-contact time | Derived from two reviewed events; s | (contact_frame−release_frame)/fps | Flight duration ends at first board **or ground** collision, independent of body motion end or final rest. No inferred contact from tracker loss. | `flight.flight_summary` |
| Reviewed trajectory | Estimated positions; image pixels | Saved bag centroids from release through contact, gaps preserved | Displays observed projectile path with equal x/y plotting scale. Camera motion, perspective and deformation remain. No extrapolation. | `flight.flight_summary`, native `FlightPathPanel` |
| Observed apex/rise | Derived; frame, px; research export | Minimum image y within complete reviewed flight, strictly interior; rise=y_release−y_apex | Only a fixed side camera and complete samples permit this descriptor. Discrete apex is frame-limited and not fitted world height. | `flight.flight_summary` |
| Horizontal image travel | Derived; px; research export | Absolute difference in release/contact x | Complete reviewed path and fixed side-camera confirmation required; no meters extrapolated using a release-only scale. | `flight.flight_summary` |
| First-contact grouping | Derived; in | centroid c=mean(P); RMS radius=√[mean(||P−c||²)]; n≥2. Axis SD uses n−1. | Repeatability independent of target accuracy. **Conditional on visible board contacts**; excluding misses can bias apparent precision. Report n and unlocated observations. Rest has its own grouping. | `flight.landing_dispersion` |
| Scored vs miss comparison | Derived; source feature units | Median, quartiles, SD per group (scored = 1 or 3, miss = 0); Cliff's δ; noise floor | Claimed only with ≥5 throws per group, \|δ\| ≥ 0.474 and a median difference above the noise floor. Associational, exploratory, unknown outcomes excluded. Replaces the earlier colored personal zones. | `performance.performance_summary` |
| Movement–outcome association | Derived; Spearman rho | Complete pairs for named feature and first-contact error or observed bag value; ≥8 varying pairs | Raw scatter and n shown before inference. Exploratory 95% percentile bootstrap interval, 2,000 resamples, seed 20260906; not a confirmatory test or causal coaching prescription. | `statistics.relationship`, `pipeline.analyze_relationships` |

## Frames, filtering and release fit

Raw image axes: x right, y down. Analysis axes: x toward target (reflect x for right-to-left), y up. Angles reference image axes, not a reconstructed world frame. Single-camera projection cannot recover lateral depth, true 3D joint angles, or true release height without additional calibration.

Pose coordinates retain the existing 4th-order, zero-phase 6 Hz Butterworth filter and at most three-frame automatic gap interpolation. Filtering occurs on contiguous valid runs; short runs retain explicit warnings. Body normalization is L=median(|S−E|)+median(|E−W|), a **projected** arm length. Optional tape-measured upper-arm/forearm lengths in the athlete profile provide context only. Do not turn apparent body lengths into meter calibration.

**Bag launch fits do not use the body low-pass filter.** The fit uses quality-accepted, identity-reviewed automatic or directly corrected centroids; interpolated positions are excluded because they are not independent observations of curvature. Fit a quadratic to each raw image coordinate using iteratively reweighted least squares (Huber residual weighting, up to 12 iterations). For t=(frame−release)/fps:

```
x(t) = ax + bx t + cx t²
y(t) = ay + by t + cy t²
vx = direction_sign × bx
v_up = −by
speed = hypot(vx, v_up)
angle = atan2(v_up, vx)
```

Default window is 0.12 s, at least four contiguous points. The first point can be at release or one frame later; longer gaps suppress fitting. Contact and later samples are excluded. A quadratic is used even for four/five points: a straight-line slope on accelerating motion estimates a window-average velocity, not launch velocity. This change removes that systematic timing bias but does not eliminate noisy curvature estimates.

The residual gate is vector RMSE/L ≤0.03 with a valid normalization length. It is a documented **pilot quality heuristic**, not a physical error bound or accuracy certification. A poor fit withholds velocity. Estimated *short-window* acceleration remains research-only and additionally needs ≥60 fps and ≥6 samples. The nominal ~59.95 fps player recordings fall below this conservative acceleration gate.

**Standard errors (added 22 Sep 2026).** Each fit reports the weighted least-squares covariance s²(XᵀWX)⁻¹, with s² = Σwr²/(n−p). Launch-angle and speed standard errors use the first-order propagation σθ² = (vy²σx² + vx²σy²)/v⁴ and σv² = (vx²σx² + vy²σy²)/v². They measure tracking noise inside the window only. Release-frame choice, camera motion and scale error are excluded, so they are a lower bound. Monte-Carlo checks in `tests/test_launch_and_scale.py` confirm they match the empirical spread.

**Gravity-constrained launch (added 22 Sep 2026).** When a valid scale q (px/m) exists, gravity's image acceleration g·q is known rather than estimated. The vertical fit becomes y(t) − ½gqt² = ay + by t, and the horizontal fit becomes linear. Drag changes horizontal speed by about 1 % over 0.12 s. A free quadratic's slope at the window end is its noisiest coefficient. With 2 px centroid noise at 60 fps, the constrained fit roughly quarters the angle SD (≈2.6° → ≈0.7° in simulation). With a valid scale, the constrained fit is the reported launch, and `launch.primary_model` records which model was used.

Launch values require manual release confirmation in addition to track approval. Full-flight review includes first contact; release-window review alone does not authorize the whole path. Reanalysis is required after edits. The app limits explicit bag interpolation to three missing frames and excludes those points from launch estimation.

## Calibration workflow and geometry

In Throws, scrub the video, then open **Flight & scale**. Mark release at visible bag–hand separation, mark first contact (or leave unknown), record geometry/uncertainty notes, and optionally supply a measured length. Reopen the panel at the appropriate event frame; do not mark both at the same frame.

For SI release speed, require a fixed, level, approximately perpendicular side camera and a known rigid length in the release plane. Enter its measured meters, observed pixel length, identifying object, endpoint coordinates, and method. The current frame, length inputs, source description and pixel/meter scale are stored in `calibration.json` and the manifest. Scale q=L_pixels/L_meters; v_m/s=v_pixels/s/q. Uniform scale cancels from the angle. A distant tilted board is **not** an athlete-plane calibration.

The ordinary planar-projectile equations x=x0+vx0 t and y=y0+vy0 t−½gt² motivate the model but are **not used to fabricate an unseen landing**. They assume stationary coordinates and negligible air resistance.

**Gravity scale from the reviewed flight (added 22 Sep 2026; replaces the earlier "never infer scale from gravity" rule).** A free bag accelerates downward at g. The vertical image acceleration a (px/s²), fitted over *all* reviewed frames strictly between confirmed release and first contact, therefore gives the scale of the bag's own flight plane: q = a/g.
- *Drag:* a point-mass drag simulation (0.454 kg, C_D·A 0.006–0.024 m², 6–7 m/s, 30–55°, sampled at 60 fps) biases apparent g by only −0.2 % to −1.4 %. Vertical drag adds to gravity on the way up and opposes it on the way down.
- *Gates:* the gravity scale is refused unless all of these hold: the camera is confirmed fixed, the view is a side view, release and contact are both reviewed, the bag track is reviewed through contact, there are at least 15 samples, and coverage is at least 80 %.
- *Remaining sources of error:* perspective change if the flight is not perpendicular to the optical axis, lens distortion near the frame edge, and camera tilt.
- *Priority:* a measured in-plane object (meter stick) takes priority. When both exist, the flight reports `apparent_gravity_m_s2` = a/q_measured. This is an independent check of the stick scale and of camera stability; values far from 9.8 m/s² flag a problem.

Spin, depth motion and camera motion remain unresolved. Total range in meters, landing prediction, 3D release, spin, torque and joint loads remain unavailable.

**Release height (added 22 Sep 2026).** Release height is the bag's image height at the confirmed release frame above the floor line. The floor line is the per-frame lowest heel/toe landmark (Sports2D HALPE-26 feet), medianed over ±3 frames so a lifted foot does not move it. Ankles are a labelled fallback about 7–9 cm above the floor. Height is reported in arm lengths, and in meters when a valid scale exists. It assumes a level camera.

Board locations are approximate manual top-down observations on a nominal 24×48 in deck, origin near-left, hole center (12,39) in. The schematic is not a calibrated mapping of video pixels. A board-plane homography would need surveyed corners, acceptable geometric conditioning and independent point validation; it would still be invalid for airborne points or ground contact. It is intentionally not assumed from the shallow board view in these clips. Measure the actual board before quantitative experiments.

## Within-athlete comparison and missingness

Native insights match athlete, session, camera-view label, handedness, intended-target label, throw-type label, pose backend/model/version/hash, engine hash and processing configuration. Maintain the same camera placement, pitcher-side position and stance condition within a session; record changes in session/trial notes and start a new session. Matching labels alone cannot prove equivalent camera geometry. Only compatible analyses with sufficient pose coverage enter body consistency. Outcome counts and landing points do not become zero when a movement metric is missing.

First contact is always the spatial response. When no first-contact error exists, observed bag value is the named response. Small n does not silently switch the response; the software displays insufficient evidence. Unknown outcomes are excluded from scored pairs. The current prototype does not establish longitudinal improvement from a single pooled dispersion number; collect repeated matched sessions and compare raw spread and outcome distributions before making that claim.

## Provenance and persistence

`pose_raw.json` / `bag_raw.json`: immutable model/tracker observations. Separate correction files preserve manual edits; `events.json` distinguishes candidates from manual release. `flight_review.json` stores first contact, fixed-camera confirmation and notes. `results.json.flight` includes availability, event frames, frame interval, path gaps and coverage; summaries have units, classification and definition-source metadata. `manifest.json` hashes analysis inputs, including flight review and scale.

Libraries now save as schema **4** because unknown per-bag values must not be read as misses by older software. Schema 2/3 indexes are backed up before the next save. Existing 0/1/3 values retain their historical meaning; the software cannot determine which historical zeros were accidental defaults. Audit those against recordings. Old analyses need reanalysis to populate the new scientific contract.

## Experimental validation still required

1. Use a tripod; acquire known constant-frame-rate 120 fps if practical, short exposure and clear bag/background contrast. Keep full flight and receiving board visible. Use one throw per analysis clip.
2. Place a surveyed scale/grid in the release plane and verify horizontal/vertical axes. Capture a separate calibrated board view for landing errors; synchronize views if combining them.
3. Collect repeated throws per athlete, with fixed target/task, board distance, bag, pitcher-side position and stance condition. Record every outcome, including occluded/unknown cases. Plan sample size from pilot variability rather than the software's 5/8-observation gates.
4. Have two independent reviewers label release/contact and centroid/joint points. Report inter-rater disagreement, pixel error, endpoint uncertainty and missingness. Vary release ±1 frame, fitting window and scale to assess sensitivity.
5. Compare velocity/angles against an independent calibrated camera or instrument. Evaluate high-speed reference video downsampled to 60/30 fps. Test different camera yaw/roll, occlusion and deliberately introduced tracker identity swaps.
6. Test a preregistered movement hypothesis (for example release speed versus short/long deck contact) with a repeated-session or controlled within-athlete design. Separate accuracy, grouping, scoring and tactical intent. Observational association alone is not a coaching prescription.

## Sources checked 20 September 2026

- [ACL gameplay and scoring](https://www.iplaycornhole.com/about/acl-information/rules-regulations/gameplay) and [equipment](https://www.iplaycornhole.com/about/acl-information/equipment-bags-boards): per-bag values, cancellation distinction and nominal deck geometry.
- [Sports2D upstream](https://github.com/davidpagnon/Sports2D): upstream capability context. This repository intentionally stays on its tested 0.8.34 adapter rather than assuming current upstream interfaces match.
- [OpenStax, Projectile Motion](https://openstax.org/books/physics/pages/5-3-projectile-motion): ideal independent horizontal/vertical motion under neglected drag; model assumptions, not bag-specific validation.
- [OpenCV homography tutorial](https://docs.opencv.org/4.5.1/d9/dab/tutorial_homography.html): planar transformation scope; no conversion of airborne points via the deck plane.
