# Research and audit notes

**Updated 8 September 2026.** These notes record the focused scientific/documentation audit and project decisions. The canonical source/supports/does-not-support/app-impact matrix is [docs/RESEARCH_BACKGROUND.md](docs/RESEARCH_BACKGROUND.md); equations are [docs/BIOMECHANICS_METHODS.md](docs/BIOMECHANICS_METHODS.md); validation status is [docs/VALIDATION_PLAN.md](docs/VALIDATION_PLAN.md).

## Scientific premise

Primary question: can controlled single-camera markerless video quantify upper-body cornhole kinematics repeatably and identify, within athlete, movement features associated with task performance?

Secondary question: in this athlete's current sample, is performance more closely associated with resemblance to a selected reference, repeatability of the athlete's own movement, or particular kinematic features?

The interface and exports must keep separate:

- **reference similarity** — resemblance to a named compatible reference;
- **personal consistency** — repeatability of this athlete's movement;
- **performance association** — an exploratory relationship with outcome;
- **tracking/measurement quality** — whether the input supports an estimate.

None is automatically technique quality. The project does not use “perfect form,” “ideal mechanics,” or causal coaching prescriptions without evidence.

## Repository and documentation audit

Audit baseline was branch `codex/second-pass-lab`, checkpoint `774db93` on 8 September 2026. The existing SwiftUI app, Python scientific package, tests, setup/build/run scripts, Sports2D adapter, and working analysis/export flows were retained.

Findings before this pass:

- The requested canonical filenames did not exist. Information was split among a long README, `docs/METRICS.md`, `docs/VALIDATION_PROTOCOL.md`, `docs/QA.md`, `docs/REPOSITORY_INVENTORY.md`, and historical archive notes.
- Existing methods covered body pose, reference comparison, outcomes, consistency, and basic performance relationships, but not a complete contract for bag tracking/release/velocity, shoulder-relative decomposition, radial/pendulum-like descriptors, path shape, physical calibration, or front/rear view metrics.
- The Challis reference used an incorrect shortened title. The correct title is “A procedure for the automatic determination of filter cutoff frequency for the processing of biomechanical data.”
- ACL nominal coordinates already matched the current geometry: a 24 by 48 in board and a 6 in hole centered at `(12,39)` in when `y=0` is the pitcher/front edge. Scoring language needed to distinguish a per-bag 0/1/3 value from cancellation scoring for a round and include a hanging bag as 1 point.
- `reference_materials/design/DESIGN_RESEARCH.md` concerns an unrelated “Places” product. It is legacy contamination, not evidence for Cornhole Biomechanics Lab.
- Unofficial/untracked books in `reference_materials/` were not opened, read, cited, or redistributed. They remain opaque user-owned material.
- Generated clutter included Swift `.build`, Python caches/egg metadata, virtual-environment artifacts, model weights, and duplicated release bundles. These are reproducible/ignored artifacts, not source or participant data. Root setup/build/run wrappers are intentional compatibility entry points and are retained.
- Three empty legacy `.cornholeproject` manifests had different UUIDs/timestamps, so they were not byte duplicates. Five supplied MP4s had distinct SHA-256 hashes. No original participant/reference input was deleted or modified.
- The literal supplied-video path includes a trailing space in `Participant/Reference `; code and QA must resolve the filesystem path rather than silently changing it.

The current retain/remove/migrate decisions are documented in [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md). Historical audit/plan files stay under `docs/archive/` and are not current verification evidence.

## Focused primary-source review

### Sports2D

The JOSS paper supports using Sports2D for single-video 2D keypoints, joint/segment angles, annotated video, and scientific exports. Official documentation explicitly warns that acceptable 2D angle results require near-planar sagittal/frontal movement with the camera parallel to that plane.

The official GitHub release and PyPI pages were checked on 8 September 2026: **0.8.34**, released 10 July 2026, remains the current stable release. It adds Mac support and tracking/sorting improvements. The application remains pinned to Sports2D 0.8.34 and Pose2Sim 0.10.49 because an upgrade could change pose identities, confidence access, interpolation/filter behavior, or exports. A future version must pass an isolated equivalence review before adoption; “newer” alone is not evidence of correctness.

Sports2D does not provide cornhole outcome semantics, coach references, transparent manual corrections, bag tracking, or within-athlete interpretation. Those remain application responsibilities. Upstream metric/IK/depth-like options are not evidence of calibrated 3D and stay disabled for Stage 1.

### Throwing studies

Nasu et al. (2014) and Tran et al. (2019) show that skilled dart throwers can use different movement/release strategies. Tran also measured projectile and arm kinematics together and detected release from persistent hand–projectile separation with video review.

These findings motivate trajectories, bag–wrist separation, release timing, projectile velocity/direction, and individualized analyses. They do not establish cornhole norms, transfer laboratory thresholds, validate a phone tracker, or justify millisecond precision from 60 fps video.

### Two-dimensional measurement

Sih et al. (2001) formalize the single-camera assumption: motion occurs near a calibrated plane perpendicular to the camera axis; unmeasured depth causes perspective error. Stenum et al. (2021) demonstrate useful but viewpoint- and task-dependent 2D pose estimates and the need for manual identity/landmark review and criterion comparison.

The gait paper's published angle/event errors are not cornhole upper-limb error limits. Decisions here are to label every measure projected 2D, standardize view, prohibit incompatible comparisons, retain missingness/corrections, and validate this exact camera/model/task.

### Filtering

Challis (1999) supports data-driven cutoff selection by examining whether the filtered–unfiltered residual resembles noise. It does not establish a 6 Hz universal cutoff. The app's fourth-order zero-phase 6 Hz setting is a documented pilot default; 4/6/8 Hz and interpolation sensitivity must be tested on real throws, especially for velocity and acceleration.

### ACL rules

Current official ACL rules and equipment pages were checked 8 September 2026. They support the nominal board/hole geometry and per-bag values. They do not turn manual board clicks into laboratory measurements or the board into an athlete-plane scale. Save the ruleset/date, measure the actual study board, keep target/contact/rest distinct, and label points approximate.

## Measurement decisions

- Preserve immutable automatic pose and bag tracks; corrections and interpolation are separate provenance layers.
- Use the sequence corrections → confidence mask → limited short gaps → coordinate filter → geometry → differentiation.
- Normalize shoulder-relative paths by robust projected arm length; this removes translation/uniform scale only.
- Make side view the primary Stage 1 setup. Front/rear values are lateral/projected and are not pooled with side-view values.
- Use bag tracking as a reviewable semi-automatic measurement. Suppress downstream values when identity/coverage is inadequate.
- Prefer a bag–wrist persistent-divergence release candidate; retain a visibly labeled wrist-only fallback and manual frame priority.
- Estimate release velocity from a saved local fit over several supported post-release samples, not a two-frame difference.
- Use arm lengths/s or px/s without calibration. Use m/s only with a known object in the athlete/release plane.
- Call shoulder-to-wrist/bag values radii or projected lever-distance proxies, never moment arms or torque.
- Keep pendulum-like and path-shape values descriptive. Stable radius or straightness is not automatically better.
- Show raw comparison/consistency/performance values before any 0–100 pilot summary.
- Treat five-throw/eight-pair UI gates as software guardrails, not sample-size justification.

## Evidence still required

Not yet established by documentation, unit tests, or reference videos:

- landmark and bag-centroid agreement against independent labels;
- automatic versus independently reviewed release timing;
- manual annotation repeatability;
- within- and between-session measurement repeatability;
- sensitivity to view, camera placement, filter, gaps, and frame rate;
- criterion agreement with calibrated/high-frame-rate or laboratory measures;
- stable within-athlete movement–performance associations in real course participants;
- evidence that any feedback improves performance.

Software QA and supplied-video trials must be reported separately from these scientific claims in [docs/VERIFICATION.md](docs/VERIFICATION.md).
