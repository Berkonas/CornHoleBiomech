# Scientific metrics guide

This guide documents projected body metrics. The current [full-throw contract](FULL_THROW_METHODS.md) defines release, flight, outcome, personal distributions and availability gates. Every angle is a projection into the image plane. None is a measured 3D anatomical rotation. Pilot scoring tolerances are configuration choices, not population norms or validated error limits.

## Coordinates and landmarks

Raw image: x right, y down, pixels. Analysis: x toward target (reflect when necessary), y up. Shoulder-relative paths subtract the throwing shoulder each frame and divide by robust arm length. Both shoulder and both hip estimates are required for the midpoint trunk. Markerless points are model estimates, not palpated anatomical joint centers.

For 2D vectors, define `A(u,v) = atan2(|ux vy − uy vx|, u·v) × 180/π`. Zero-length or missing defining vectors produce missing values. Orientations are unwrapped only within contiguous finite runs before differentiation; orientation comparison uses the shortest circular difference.

## Kinematic metrics

| Metric | Plain meaning / defining landmarks | Equation and units | Measurement interval | Interpretation and limitations | Sports2D convention |
|---|---|---|---|---|---|
| **2D projected elbow included angle** | How straight the throwing elbow appears; shoulder S, elbow E, wrist W | `A(S−E,W−E)`, degrees, 0–180; **180 is straight** | Whole waveform, movement summary, release candidate | Smaller angle means more flexed in this view. Not 3D flexion or axial rotation. | Signed elbow flexion F uses different offset/sign. Included angle = `180 − abs(wrap180(F))`. Synthetic tests cover 0°,45°,90°,135°,180° and both signs. |
| **Upper-arm orientation** | Throwing shoulder-to-elbow direction | `atan2(Sy−Ey, signX*(Ex−Sx))`, degrees | Waveform, mean, ROM, velocity | Segment direction relative to target-forward horizontal, not shoulder internal/external rotation. | Sports2D arm uses E−S and an image-y correction; equal only with matching left/right, floor and facing settings. Recompute from pixels for authority. |
| **Forearm orientation** | Elbow-to-wrist direction | `atan2(Ey−Wy, signX*(Wx−Ex))`, degrees | Waveform, mean, ROM, velocity | Not pronation or supination. | Same caveat as upper arm. |
| **Arm relative to trunk** | Arm direction against trunk axis; upper arm and midpoint hip→shoulder | `A(E−S,midS−midH)` in analysis axes, degrees | Waveform, mean, ROM, release | Unsigned projected angle; does not isolate shoulder articulation from projection errors. | Upstream shoulder flexion is signed and uses a reversed upper-arm vector; not interchangeable. |
| **Trunk inclination** | How far the trunk leans toward the target | `atan2(trunkX,trunkY)`, degrees; positive toward target | Waveform, mean, ROM, release | Depends on camera roll and bilateral landmark visibility. Not a lumbar joint angle. | Upstream Trunk is measured from horizontal; no direct comparison without axis/offset audit. Recompute from midpoint landmarks. |
| **Normalized wrist path** | Wrist movement relative to shoulder, scaled to body size | `[signX*(Wx−Sx), Sy−Wy]/Larm`, arm lengths | Whole normalized cycle and marked events | Removes image translation/uniform scale; not perspective or limb-proportion effects. | Generic pixel TRC exists; normalization is ours. |
| **Normalized elbow path** | Elbow movement relative to shoulder | Same equation using E, arm lengths | Whole cycle | Useful for aligned skeleton. Same projection limits. | Generic pixel TRC; normalization is ours. |
| **Shoulder/hip paths** | Context for aligned trunk skeleton | Same shoulder-centered equation for bilateral shoulders/hips | Whole cycle | Visual context; no extra similarity components assigned. | Generic TRC points; normalization is ours. |
| **Angular velocity** | How fast the filtered projected angle changes | Time-aware finite difference on contiguous finite runs, degrees/s | Whole waveform, mean and peak absolute | Calculated only with ≥80% finite angle coverage; frame rate and filter warnings still matter. No gap bridging. | Native angular definitions/filters differ; not substituted. |
| **Mean and ROM** | Typical angle and observed excursion | Finite mean; finite max−min, degrees | Mean, ROM and velocity summaries use reviewed motion start through end (inclusive); full-video curves remain exported | Missing extremes and inaccurate event bounds affect summaries. Review the movement interval. | Similar concepts, but only matching definitions/intervals are comparable. |

`Larm = median(||S−E||) + median(||E−W||)` over finite filtered points. Optional height/arm span are contextual, not needed to calculate this scale.

## Time and events

| Metric | Equation / units | Meaning and limits |
|---|---|---|
| Movement duration | `(endFrame − startFrame)/fps`, seconds | Effective automatic/manual bounds; no sub-frame precision |
| Normalized time | `τ=(frame−start)/(end−start)`, 0–1 | Default 101 samples; interpolation only between adjacent finite supports, preserving long missing gaps |
| Motion start/end | Sustained wrist-speed heuristic | Candidate movement interval; review against video |
| Peak backswing | Minimum target-axis wrist position before release candidate | A wrist-path event, not a muscle activation event |
| Forward swing | Frame following backswing, bounded by release | Coarse heuristic onset; manually correct when necessary |
| Release candidate | Peak target-axis wrist velocity after backswing | **Not observed bag–hand separation.** Review and manually label actual visible release when possible. Uncertainty at least a frame interval and larger with blur/occlusion. |
| Peak follow-through | Maximum forward wrist position after candidate release | Kinematic proxy; video review remains necessary |
| Event timing error | `abs(τtrial−mean(τreferences))`, cycle fraction | Preserves timing differences rather than warping them away |

Manual event values retain automatic candidates and must be within the video and ordered. Empty event fields remain missing. All dates/settings and effective frame indices are exported.

## Reference comparison (raw errors only)

A reference may be one selected throw or a set. The pointwise mean represents the set; ±1 sample SD describes its spread, not uncertainty in the mean. A trial cannot include itself as a reference. Camera views and normalized grids must match.

| Error | Formula | Units / interpretation |
|---|---|---|
| Angle MAE | `mean(abs(trial−reference))` over paired finite samples | degrees; overall waveform error |
| Angle RMSE | `sqrt(mean(error²))` | degrees; emphasizes larger differences |
| Waveform correlation | Pearson correlation of paired samples if both vary and n≥3 | unitless; similar shape does not imply absolute agreement |
| Peak / ROM difference | Absolute difference in paired-sample maximum / range | degrees; affected by missing extrema |
| Wrist / elbow path RMSE | `sqrt(mean(||ptrial−preference||²))` | arm lengths; Euclidean path discrepancy |
| Largest movement difference | Maximum absolute angle error or Euclidean point error at a normalized sample | degrees or arm lengths, with cycle percentage and phase; ranked after division by pilot tolerance |

For segment orientation and trunk inclination, signed error is wrapped into `[-180°,180°)`. The elbow included angle and unsigned arm/trunk angle use ordinary subtraction. The largest-difference UI uses **pointwise** error; the error table uses **whole-cycle** errors.

A 0–100 "Reference Similarity" composite was removed on 22 September 2026. Its tolerances (15°, 10°, 0.25 arm lengths, 0.10 cycle) and weights (1.0/0.75) had no empirical basis, and the single number hid which component differed. The raw errors above are reported instead. Resemblance to a reference is not skill, correct form, accuracy or safety.

## Athlete consistency

At least **five comparable throws** are required. Comparable means same athlete, session (including unassigned session group), camera view, throwing side, pose backend/model, processing configuration and **measurement method version** (`METHOD_VERSION` in `python/cornhole_biomech/__init__.py`, bumped only when a saved number's meaning changes), with ≥80% usable frames and no pending corrections. Five is a pilot display threshold, not evidence of adequate sample size.

At each cycle point, calculate sample SD across throws (`ddof=1`). A waveform's variability is the RMS of its pointwise SD. Wrist variability is `sqrt(mean(SDx²+SDy²))`. Timing variability is sample SD of release-cycle fractions. A point needs at least five supporting throws; a waveform needs ≥80% supported points. The variabilities are reported in their own units. The former 0–100 consistency index, built from arbitrary tolerances, was removed. A repeatable movement can still perform poorly.

## Tracking quality

There is no composite tracking score; the former 50/30/20-weighted index was removed. The following are reported separately:
- usable-frame percentage;
- release-window visibility (share of frames within ±50 ms of release where all throwing-arm and trunk landmarks are raw-visible above the confidence threshold);
- mean pose confidence;
- manual and interpolated point counts;
- per-landmark low-confidence counts;
- fps, resolution and view.

Manual corrections never inflate raw tracking confidence. Model confidence is not a calibrated physical error. Real accuracy comes from the annotation workflow in [VALIDATION_PROTOCOL.md](VALIDATION_PROTOCOL.md).

## Scored versus missed throws

`performance.py` compares scored throws (1 or 3 points) with misses (0) for one athlete. Unknown outcomes are excluded. It uses a fixed list of release variables: angle, speed, height, forward position, elbow and trunk at release, and duration. For each variable it reports n, median, quartiles, SD, CV (ratio-scale variables only), Cliff's δ = P(scored > miss) − P(scored < miss), and Hedges' g.

A variable "differed" only when all of these hold:
- at least 5 throws per group;
- |δ| ≥ 0.474 (large; Romano et al., 2006);
- the median difference exceeds the variable's noise floor.

The release-angle noise floor is 2 × the median per-throw fit standard error. The other floors are provisional estimates listed in the code, to be replaced by validation results. The analysis is exploratory and is not corrected for the number of variables. Wording is associational.

## Cornhole outcomes

Official per-bag result: **3 through hole, 1 on board, 0 off board/foul**. This is a bag result, not the net cancellation score for an inning. The app does not invent an overall Athlete Score.

Board: x 0–24 inches left→right; y 0–48 inches pitcher→back. Hole center (12,39), radius 3 inches. Target `T`, observed landing `P`:

- Lateral error `Px−Tx` (negative left, positive right), inches.
- Longitudinal error `Py−Ty` (negative short, positive long), inches.
- Radial target error `sqrt(lateral²+longitudinal²)`, inches.

Trial summaries and spatial relationships use first contact only; final rest has a separate error. Unknown outcomes are null, not zero. No spatial error exists without both target and the observed endpoint. Board clicks are approximate deck-plane observations, not calibrated video measurements. Ground misses have no board-plane location.

## Performance relationships

Within-athlete scatter plots retain observations, sample size and separate task outcomes. Features include release elbow/trunk, elbow ROM, movement duration, release timing and wrist deviations. Use target error when available; otherwise use 0/1/3 bag result. Never mix inches and score categories in one response variable.

Spearman rho is the correlation of ranks; report only with at least **eight complete pairs** and variation in both variables. The 95% interval is a percentile bootstrap from 2,000 resamples using a fixed seed. Constant bootstrap samples are omitted. These exploratory intervals do not solve dependence, multiple comparisons, selection bias or small samples. No trend line is imposed and no association is described as causal.

## Reproducibility and interpretation

Raw pose, corrections, configuration, effective events, source hashes, model hashes and normalized trajectories are retained. Corrections mark derived results stale until reanalysis; changing a source normalized file invalidates its comparison. The deterministic summary simply formats actual outcomes, differences, sample size and warning state. It supplies no diagnosis or prescriptive technique advice.

Sports2D 0.8.34's pixel TRC header is corrected from its upstream hardcoded `m` to `px`; the original and repair hashes are retained. See [SPORTS2D](SPORTS2D.md). Zero Z never represents measured depth.

## Arm-motion descriptors

The `arm_motion_*` fields describe the inclusive forward-swing-to-release interval in native-rate filtered side-view data. They include mean flexion (180° minus included elbow angle), flexion excursion, sample SD and shoulder–wrist radius CV. The UI shows CV × 100 as percent; saved values are ratios. They require ≥5 usable samples and ≥80% coverage, with a separate radius gate. Null values mean unavailable. These gates do not establish anatomical accuracy. Earlier passive-pendulum notes are archived in `archive/PENDULUM_MODELS.md`.
