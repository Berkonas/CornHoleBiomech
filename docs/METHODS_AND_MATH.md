# Methods and Mathematics — Cornhole Biomechanics Lab

**Report companion for Vanderbilt ME/BME Biomechanics of Human Movement, Project 1 (cornhole for Vanderbilt Athletics). Written 27 September 2026.**

This document collects, in one place, the methods and every equation the system actually uses, so that sections can be copied into the course report. It is grounded in the code (`python/cornhole_biomech/`, `app/CornholeBiomechanics/Sources/CornholeBiomechanics/`) and in the existing method documents. Where an older document and the code disagree, the **code value is given here**. Longer derivations and design history are in [BIOMECHANICS_METHODS.md](BIOMECHANICS_METHODS.md) (§18 is the current scene/chain engine), [FULL_THROW_METHODS.md](FULL_THROW_METHODS.md), [METRICS.md](METRICS.md), [COACHING_SYSTEM.md](COACHING_SYSTEM.md) and the two design specs in [superpowers/specs/](superpowers/specs/).

**Versions this document describes**

| Item | Value | Where defined |
|---|---|---|
| Measurement method version | `METHOD_VERSION = "2026.09.27-thrower"` | `cornhole_biomech/__init__.py` |
| Python package | 0.6.1 | `cornhole_biomech/__init__.py` |
| Pose software | Sports2D 0.8.34 (pinned), RTMPose via RTMLib/ONNX Runtime on CPU, model `body_with_feet` (HALPE-26 incl. heel/toe points), mode `balanced` | `sports2d_adapter.py`, `config.py` |
| Automatic bag tracker | `auto_motion_parabola_v13_near_contact_surface_point` | `auto_bag.py` |
| Bag silhouette centroid | `local_median_background_mask_v1` | `bag_segment.py` |
| Bag flight filter | `ca_kalman_rts_v1` | `bag_filter.py` |

**Validation status in one line.** Software behaviour is unit-tested; the measurement accuracy of body landmarks, bag centroids and metric scale has **not** been validated against a criterion (motion capture or manual digitisation) for this task. Evidence so far is a light engineering validation on 26 hand-held pilot clips from 3 athletes (17 Sep 2026; [LIGHT_VALIDATION.md](LIGHT_VALIDATION.md), [SCENE_REGRESSION.md](SCENE_REGRESSION.md)). Every noise floor for body metrics is **provisional**.

---

## 1. System Design & Methodology

### 1.1 Pipeline overview

```
 VIDEO (side camera, ~60 fps, 1080p)                      optional BOARD CAMERA clip
   │                                                          │ 4 clicked deck corners
   ├─► camera stabilisation: ORB+RANSAC init → ECC affine      │ → homography → board inches
   │   keyframe registration → per-frame transforms           │
   ├─► pose: Sports2D / RTMPose (HALPE-26) ─► manual corrections ─► confidence mask (0.35)
   │        ─► short-gap interpolation (≤ 3 frames) ─► 4th-order zero-phase Butterworth 6 Hz
   ├─► person masks (Apple Vision) ─► background plate (median of stabilised frames)
   ├─► bag: motion candidates (3-frame + plate differencing, masks excluded)
   │        ─► physics-gated parabola seed/growth ─► silhouette centroid (Lab colour mask)
   │        ─► Kalman/RTS smoothing with leave-one-out outlier gating
   ├─► board: HSV red deck / dark rim or apron ─► PnP (IPPE) ─► throw-plane homography, φ
   │        ─► gravity-calibrated field of view ─► pixels per metre (session-pooled)
   ├─► events: body events (wrist speed) · release = first flight centroid beyond the hand
   │           · first contact = board/floor-gated end of the parabola · suggested 0/1/3
   ├─► per-throw quantities: joint angles, angular velocities, wrist speed, tempo, trunk lean
   │           · release speed/angle/height ± SE · bag p, KE, PE, F = m(a − g), P = F·v
   │           · Monte Carlo 95 % intervals · reliability status per metric · GOOD/WARNING/POOR
   └─► athlete level: PPR, In/On/Off · scored vs miss (Cliff's δ) · priority gate (5 checks)
               · consistency (SD vs noise floor) · evidence chain (Spearman ρ, bootstrap CI)
               · compensation · error budget · zones · per-throw verdict  ─►  COACH APP
```

Every stage emits a state — `measured`, `estimated` (with a reason) or `unavailable` (with a reason) — and missing information stays missing; it is never replaced with zero.

### 1.2 Video capture protocol

| | Pilot data (17 Sep 2026) | Recommended protocol ([RECORDING_PROTOCOL.md](RECORDING_PROTOCOL.md)) |
|---|---|---|
| Camera A (athlete) | One hand-held phone, side view, 1080p, ~59.95 fps; athlete ≈ 300 px tall (upper arm ≈ 60 px); board small at frame right | Tripod on the throwing-arm side, optical axis perpendicular to the throw, 1.0–1.2 m high; athlete 60–70 % of frame height; 120 fps preferred, 60 fps minimum; focus/exposure locked; 1 m stick filmed level and vertical in the throwing plane each session |
| Camera B (board) | none | Raised, all four deck corners + ~1 m of floor visible; corners (24 × 48 in) give a deck homography for landing points |
| Camera C (full flight) | the pilot view | Optional, tripod only |
| Sync | — | One clap visible to all cameras |
| Throws | ~9–11 per athlete, no outcomes recorded yet | ≥ 20 recorded throws per athlete at one target, never delete bad throws; outcome sheet per throw |

The app reads the file's real frame rate on import. Temporal resolution is one frame: $\Delta t = 1/\text{fps}$ (16.7 ms at 60 fps). Frame-rate checks use **nominal** rates with a 0.5 fps tolerance, because phones record "60 fps" as 59.94 fps (60000/1001) and "30 fps" as 29.97 fps: the quality warnings fire below 29.5 and 59.5 fps (`quality.py`), and the exploratory image-plane acceleration of the launch fit is withheld below 59.5 fps (`bag.estimate_projectile_release_kinematics`).

### 1.3 Camera stabilisation (ECC keyframe registration)

All pilot clips are hand-held (background drift up to ~100 px within a clip). Each frame is registered directly to a keyframe with intensity-based **ECC (enhanced correlation coefficient)** registration using an **affine** motion model (`cv2.findTransformECC`, `MOTION_AFFINE`), computed at ¼ image scale, initialised from the previous frame's registration composed with an ORB-feature + RANSAC similarity step (1500 ORB features, 2 px reprojection threshold). A new keyframe starts when the correlation falls below 0.8 (pilot minimum 0.93); an ECC correction > 3 px (at ¼ scale) away from the ORB prediction is distrusted. Per-step transforms telescope through keyframes, so the chain does not accumulate drift.

Affine rather than similarity was chosen because, with a moving hand-held camera, the floor/board and the far walls move differently (parallax). Measured on the 26 pilot clips: residual against frame 0 fell from up to 51 px (ORB chain) to ≤ 4.6 px (44 of 52 spot-checked patches ≤ 3 px) (BIOMECHANICS_METHODS §18.1). The resulting `camera_to_release` transforms map every frame into the release frame's pixels; the flight fit, background plate, board corners and wrist velocity are expressed in that camera-motion-free system.

### 1.4 Pose estimation and preprocessing

1. **Estimation.** Sports2D 0.8.34 runs RTMPose (HALPE-26 keypoints incl. heels/toes), CPU/ONNX Runtime. **Choosing the thrower.** Sports2D tracks every person it detects; the app keeps the person with the largest $\text{coverage}\times\text{median body diagonal}$ (fraction of frames tracked × median keypoint bounding-box diagonal, px), because the protocol films the thrower as the nearest, steadily visible body. Sports2D's own highest-likelihood choice is not used: motion blur lowers the thrower's keypoint confidence, so a still bystander can out-score them (pilot clip "playe1 - 7": a bystander by the board at half the thrower's height won on confidence). The choice, runner-up ratio and every candidate are recorded in `provenance.json`. Sports2D's own likelihood thresholds are set to 0 so that the app — not the upstream tool — decides which points are usable; its metric/3D/IK features are disabled.
2. **Processing order** (fixed): raw estimates → manual corrections (never overwrite raw) → confidence masking (landmark confidence $< 0.35$ becomes missing) → short-gap linear interpolation (gaps ≤ 3 frames; longer gaps stay missing) → coordinate filtering → angles/paths → differentiation. Coordinates are filtered *before* angles or derivatives.
3. **Filter.** 4th-order Butterworth low-pass, **6 Hz** design cutoff, applied forward and backward (`scipy.signal.sosfiltfilt`, second-order sections) on each contiguous finite run. The cutoff is capped at $0.45\,\text{fps}$ (below Nyquist). Runs shorter than $\max(9,\ 3(2n_{\text{sos}}+1)) = 15$ samples are left unfiltered with a warning.
4. **Cutoff choice by residual analysis.** Winter's residual method (`scripts/residual_analysis.py`, §3.6) on the throwing-side shoulder, elbow and wrist of two real 60 fps clips (12 signals) gave optimal cutoffs with a median of **5.5 Hz (range 3.5–7.5 Hz)**; the wrist was highest (6–7.5 Hz). 6 Hz is therefore supported but may slightly flatten wrist-speed peaks. It is a pilot setting to be re-checked on each new session.
5. **Body scale.** Projected arm length $L_{\text{arm}} = \operatorname{median}\lVert S-E\rVert + \operatorname{median}\lVert E-W\rVert$ (pixels). Many quantities are reported in arm lengths so that differently framed clips remain comparable.

### 1.5 Person masks and background plate

A Swift helper (`scene_vision`) runs Apple Vision `VNGeneratePersonSegmentationRequest` (quality `.accurate`) on every second frame and caches masks by video hash. The **background plate** is the per-pixel median of stabilised frames with athlete pixels treated as missing. Bag candidates are found by comparing each frame with the plate warped to that frame (plus camera-compensated three-frame differencing); candidates inside a person mask cannot seed a flight (a swinging arm is not the bag). Apple Vision's mask covers only the prominent (near) person, so **background people** are also boxed from the pose detector: every tracked person except the thrower gets a per-frame box (keypoint extent padded by 0.15 × body height, held through detector dropouts of ≤ 10 frames), and candidates inside a box are treated like masked ones — they cannot start a flight but can extend one, since the bag may fly in front of a bystander. If masks are unavailable the pipeline falls back to unmasked tracking and says so; masks are never required for a result.

### 1.6 Bag detection, segmentation and tracking

**Why classical:** learned ball trackers need thousands of labelled frames that do not exist for cornhole bags; a free bag must follow a parabola with downward acceleration $g$, which rejects most clutter without training ([AUTOMATIC_TRACKING.md](AUTOMATIC_TRACKING.md)).

1. **Candidates** — difference blobs (fragments within 16 px merged, area-weighted).
2. **Seeds** — blobs linked frame-to-frame with constant-velocity prediction; short windows fitted with a quadratic; RANSAC over triples as fallback. A seed must move toward the target, curve downward with image "gravity" inside the range implied by the athlete's projected shoulder–wrist length (taken as 0.45–0.90 m, ±25 %), and have small horizontal curvature.
3. **Growth and trimming** — backward extension stops while the bag is within 0.45 arm lengths of the wrist (still in hand); the end is trimmed where the path breaks from a local parabola of the preceding 15 frames (slide/bounce).
4. **Acceptance** — a flight is used without review only if **all** gates pass; otherwise it is `needs_review` with every reason listed:

| Gate | Value (code) |
|---|---|
| Detections | ≥ 12 (`MIN_INLIERS`) |
| Time span | ≥ 0.25 s |
| Coverage of flight frames | ≥ 60 % |
| Travel toward the target | ≥ 4 arm lengths |
| Whole-flight RMS residual to the parabola, in the stabilised frame | ≤ 0.08 arm lengths |
| First free-flight point from the wrist | ≤ 0.8 arm lengths |

5. **Centroid (colour + mask).** Each detection is refined to the silhouette centre (`bag_segment.py`): local background = pixel-wise median of camera-aligned frames $t\pm\{4,6,8\}$; mask = Lab colour distance $\lVert I_t - B\rVert$ above $\text{median} + 6\,\text{MAD}$ (at least 18), morphologically cleaned; centroid from image moments $(m_{10}/m_{00},\ m_{01}/m_{00})$. It replaces the detection only if within 0.75 bag lengths. The difference blob alone sat up to ~15 px from the bag centre on the pilot clips.
6. **Kalman / RTS smoothing** (`bag_filter.py`, §3.9): constant-acceleration model per image axis, measurement noise estimated per clip from third differences, **leave-one-out outlier gating** (a point more than $\max(5\sigma, 4\ \text{px})$ from a quadratic through its ±5-frame neighbours is labelled `rejected_outlier` but kept in the raw data), noise parameters chosen by maximum innovation likelihood, then forward Kalman filter + Rauch–Tung–Striebel smoother. Nothing is extrapolated before the first or after the last measurement. The smoothed path is used for display; the launch fit uses the raw accepted centroids (§1.10).

### 1.7 Board detection and the metric throw plane

`board.py` segments the background plate in HSV (red: hue ≤ 10° or ≥ 150° on OpenCV's 0–180 scale, saturation ≥ 40, value ≥ 50; dark rim/apron: value ≤ 70). If nothing is found, a relaxed **apron-only** pass retries at saturation ≥ 30 then ≥ 25 (pale decks). A candidate quadrilateral is validated by:

- **PnP**: `cv2.solvePnP` with the IPPE solver on the four coplanar deck corners at the regulation slope (object points in metres, §3.7), with a pinhole camera of assumed horizontal field of view; the PnP reprojection residual must be < 3 % of the quad width.
- **The hole**: a black-hat filter in the rectified deck must find a dark blob within 4 in of the nominal hole centre (12, 39) in.

Confidence $= 0.5\,s_{\text{shape}} + 0.5$ if the hole agrees, else $0.5\,s_{\text{shape}}$; `found` needs confidence ≥ 0.75 **and** the front-near corner observed in the image (a PnP-filled hidden corner was 3–4 in off in a synthetic check). Outputs: four deck corners (propagated to every frame through §1.3), hole centre, floor line, the image → deck-inches homography, the **throw-plane homography** (image ↔ vertical plane through the board centre line, metres, x toward the board, y up), and the out-of-plane angle φ of the throw line (> 20° flagged, not corrected; Sih, Hubbard & Williams, 2001). Pilot result: 26/26 boards found after the relaxed pass, every quad checked by eye.

If automatic detection fails, the coach clicks the four deck corners once. A separate **board-camera** clip can also be marked (four corners → deck homography) to locate landing points in board inches, with its inches-per-pixel precision reported.

### 1.8 Scale calibration (gravity-calibrated field of view)

One still frame cannot separate a wide lens close up from a narrow lens far away: both project the same board corners, but disagree on the metric scale of everything else. The bag's free flight breaks the ambiguity because it must fall at $g = 9.80665\ \text{m/s}^2$. `calibrate_hfov_from_flight` scans the horizontal field of view over **55–75°** (0.25° grid), re-solves the board pose at each value, maps the accepted flight into the throw plane, fits a quadratic to height vs time, and finds by bisection the HFOV at which the vertical acceleration equals $-g$ (§3.8).

| Outcome | Status |
|---|---|
| Root strictly inside 55–75° | `measured` |
| No crossing in the band → nearer edge used | `estimated` (reason stated) |
| < 6 flight points or < 3 solvable HFOVs → nominal 65° | `estimated` |

Single-throw HFOVs scatter by 10+° on one fixed camera, so throws are **pooled per session** (same athlete and recording date) with the median; the pool is `measured` only with ≥ 3 measured throws and IQR ≤ 6°; a session with < 3 falls back to the library median (at most `estimated`, since it assumes the same camera and zoom). Pilot pools: 58.8°, 60.3° and 56.6° (IQR 1.3–2.5°). The board scale becomes the physical scale for release speed/height only when the scale is `measured` and φ ≤ 20°. The regulation board dimensions (ACL, `regulation.py`) are the only length standard in the pilot footage; the 27 ft pitch is **not** used as a scale.

Older path still in the code for fixed cameras: a gravity scale from the reviewed flight alone, $q = a_y/g$ (px/m), gated on a confirmed fixed side camera, reviewed release and contact, ≥ 15 samples and ≥ 80 % coverage. A measured in-plane stick has priority; if both exist, $a_y/q_{\text{stick}}$ is reported as an "apparent gravity" check. A drag simulation (0.454 kg, $C_DA$ 0.006–0.024 m², 6–7 m/s, 30–55°) biased apparent $g$ by only −0.2 % to −1.4 %.

### 1.9 Event detection

**Body events** (`events.py`, `swing.py`) come from the filtered shoulder-relative wrist: motion start/end from sustained wrist speed above $\max(0.05,\ 0.12\times\text{peak})$ arm lengths/s for ≥ 0.05 s; peak backswing = most rearward wrist position before release; peak follow-through = most forward wrist position after release. Backswing *start* (for tempo) = the last frame before the fastest backward arm swing where arm angular speed < 15 % of that peak. All automatic events are candidates that a reviewer can correct; the raw candidate is preserved.

**Release = first flight centroid beyond the hand.** Release is the first refined bag centroid in the accepted flight that lies more than **0.45 projected arm lengths** from the throwing-wrist landmark; earlier flight points are dropped as still in hand and the parabola is refitted. A visual audit of all 21 accepted pilot flights (release−8…release+3 contact sheets) found **21/21 within ±1 frame** of the visually judged release (19 exact; mean error +0.10 frame, SD 0.30 frame). The earlier rule (first flight-fit point) was 2–3 frames early on 5/21. A second, independent cue — where the fitted flight traced backward meets the wrist path — is kept as a cross-check (it runs 1–4 frames early by construction) and defines the release-window grade (§1.13).

**First contact (board-gated).** The end of the flight fit is only a candidate. It is mapped into the throw plane and classified as `deck` (inside the deck footprint expanded by half a bag width, within 6 cm of the deck surface), `front` (front face), `floor` (within 6 cm of floor height) or `air`. Only deck/front/floor are `measured`. **Near-contact rule:** a descending track that ends within 2 frames of its own predicted surface contact counts as measured, with the landing position taken where the fitted parabola meets the surface. Otherwise the contact is `lost_in_flight` and a **predicted contact** is found by extending the parabola (≤ 1.5 s), always `estimated` and excluded from measured-landing statistics.

**Suggested outcome** (`contact.suggest_outcome`), always requiring a coach click: 3 if the post-contact track disappears within 4 in (3 in hole radius + 1 in slack) of the hole centre; 1 or 0 by whether the final-rest point lies on the 24 × 48 in deck; otherwise none with a reason. Final rest was correct on 3 of 5 detected rests in the spot check, so the result stays a one-click human entry.

### 1.10 Kinematics

All body quantities are **projected 2D** in the camera plane, from filtered landmarks, in analysis axes (x toward the target after reflection, y up).

| Quantity | Definition (equation in §3) | Units |
|---|---|---|
| Elbow included angle | angle $S$–$E$–$W$ (Eq. 3.4.1); 180° = straight as seen by the camera | ° |
| Shoulder angle (chain) | upper arm vs trunk axis, angle $E$–$S$–($M_S\!-\!M_H$) | ° |
| Arm angle φ | shoulder→wrist line from straight down, + toward the board (Eq. 3.4.3) | ° |
| Backswing | minimum φ from backswing start to release | ° |
| Trunk inclination | hip-midpoint → shoulder-midpoint line from image vertical, + toward the target (Eq. 3.4.4) | ° |
| Angular velocity | finite-difference derivative of the filtered (unwrapped) angle (Eq. 3.5.1) | °/s |
| Wrist speed / direction | $\lVert \dot{\mathbf W}\rVert$ of the camera-steadied filtered wrist; direction $\operatorname{atan2}(v_y, v_x)$ | arm lengths/s (m/s with scale), ° |
| Peak wrist speed and timing | max $\lVert\dot{\mathbf W}\rVert$ from peak backswing to release + 0.1 s (interior maximum only); $t_{\text{peak}}-t_{\text{rel}}$ | arm lengths/s, ms |
| Peak elbow extension velocity and timing | max $d\theta_{\text{elbow}}/dt > 0$ in the same window | °/s, ms |
| Forward-swing time | peak backswing → release | s |
| Tempo | backswing duration ÷ forward-swing duration | ratio |
| Pendulum drive ratio | measured ω at the bottom of the swing ÷ passive uniform-rod ω (Eq. 3.4.6); needs a scale | ratio |
| Hand point (chain) | wrist + 0.34 arm length along the forearm (rigid-hand model of where the bag sits) | m |

A maximum on the edge of its search window is reported as unavailable ("peak at the edge of the search window"), not as a peak. Upper-arm/forearm *orientation* ranges and velocities are computed but never shown to coaches: a segment pointing at the camera has an undefined 2D direction (one pilot clip showed a "350° forearm range").

### 1.11 Bag flight physics (release speed, angle, height)

- **Launch fit.** Accepted, identity-reviewed raw centroids in a 0.12 s window after release (≥ 4 samples; first sample within 2 frames of release; interpolated points excluded). Without a scale, a Huber-weighted quadratic in each axis gives the velocity at $t=0$ (Eq. 3.10.1). With a valid scale $q$ (px/m) the **gravity-constrained** fit is the reported launch (`launch.primary_model`): the known image acceleration $gq$ is removed and straight lines are fitted (Eq. 3.10.2), which in simulation cut the angle SD from ≈ 2.6° to ≈ 0.7° at 2 px noise, 60 fps.
- **Standard errors.** Weighted least-squares covariance, propagated to speed and angle by the delta method (Eq. 3.10.3–3.10.4). They cover tracking noise inside the window only (not release-frame choice, camera motion or scale), so they are a lower bound.
- **Release height.** Bag centroid at release above the floor line, where the floor line is the lowest heel/toe landmark medianed over ±3 frames (ankles as a labelled fallback ≈ 7–9 cm high). In the chain, height is taken in the board's throw plane.
- **Drag-free model check** (`trajectory_model.py`): in-sample RMSE and out-of-sample RMSE (fit first half, predict second half) of $x$ linear / $y$ quadratic. No drag coefficient is fitted: on the 20 accepted pilot flights a quadratic-drag model did not reduce out-of-sample error consistently (median 24.5 px vs 24.9 px for quadratic-x and 31 px for pure ballistic), and horizontal deceleration in the image is confounded with perspective.
- **Unconfirmed release.** When release is still an automatic candidate, every release-dependent chain quantity is capped at `estimated` and excluded from athlete analyses.

### 1.12 Kinetics of the bag (bag-only mechanics)

With the throw-plane scale, the chain (`chain.py`, `mechanics.py`) reports momentum $\mathbf p = m\mathbf v$, kinetic, potential and mechanical energy at release, the **net non-gravitational external force on the bag** $\mathbf F = m(\mathbf a - \mathbf g)$ over the forward swing (peak and mean magnitude, direction), and power $P = \mathbf F\cdot\mathbf v$ cross-checked against $dE/dt$ (Eq. 3.12). Bag mass: regulation 15.5–16 oz, nominal 15.75 oz = 0.4465 kg. The bag's acceleration before release comes from the second derivative of the rigid hand point (wrist + 0.34 arm length along the forearm).

Every such value carries the label *"Bag-only: net external force/power on the bag. Not a muscle, joint or hand-contact force, and says nothing about shoulder or elbow loading."*

**Uncertainty — Monte Carlo** (500 draws per throw; interval = 2.5th–97.5th percentile, needs ≥ 20 finite draws), over: a common scale factor $\mathcal N(1, \sigma_{\text{rel}})$ (Eq. 3.8.4); bag mass $\mathcal U(15.5, 16.0\ \text{oz})$; the flight fit's standard errors on speed, angle and height (height SD 2 cm); and landmark noise of 4 px per axis per frame (pilot framing; motivated by the 16–48 mm markerless joint-centre error of Needham et al., 2021), passed through the same 6 Hz filter and then through the hand-point derivatives.

**State rules.** Second-derivative quantities (hand acceleration, force, power) are `measured` only when the 95 % interval half-width is < 25 % of the value (Winter, 2009: differentiation amplifies noise); force direction only when its half-width is < 15° **and** the peak force is measured; power only when $\mathbf F\cdot\mathbf v$ and $dE/dt$ agree within 10 % of peak $\mathbf F\cdot\mathbf v$. Every metre-based quantity is at most `estimated` when the scale is not `measured`.

**Release-timing sensitivity** (change in landing per 10 ms of earlier/later release along the hand path; Nasu et al., 2014; Hore & Watts, 2011) is defined but **unavailable on all 21 pilot throws**: the rigid hand-point direction at release was 27–47° steeper than the bag's fitted release angle (gate: 10°). It needs hand keypoints or in-hand bag tracking.

Not calculated at all: joint moments, joint or muscle forces, wrist flexion/"snap", trunk axial rotation, lateral release direction, bag spin.

### 1.13 Landing zones and the hole window

The drag-free point-mass model (§3.2) predicts first contact from $(v, \theta, h)$ and the horizontal release-to-board-front distance $d$, against the regulation side profile (48 in deck, 3 in front, 12 in back, slope ≈ 10.8°, hole centre 39 in up the deck, radius 3 in):

| Zone | Rule on predicted first contact (`zones.ZoneSettings`) |
|---|---|
| **Green — hole window** | on the deck from 0.45 m short of the hole centre to the hole's far edge (bags landing short usually slide in) |
| **Yellow** | elsewhere on the deck, or on the floor ≤ 0.30 m short of the front edge |
| **Red** | further short, into the front face, or past the board |

The 0.45 m slide allowance and 0.30 m slide-up are stated, editable assumptions, not measured constants. For each release variable the others are held at the athlete's median and the variable is scanned (speed 2–14 m/s, angle 0–75°, height 0.1–2.2 m) to give its green/yellow/red bands. Every scaled throw's predicted zone is compared with its observed result (green↔3, yellow↔1, red↔0) and the agreement rate is reported. $d$ = the throw's measured release-to-board-front distance; else the athlete's median measured distance (≥ 3 measured throws); else the **release-to-board distance set in Settings** (`releaseToBoardMeters`, user-editable; default 7.7 m ≈ the 27 ft regulation pitch minus reach), labelled in the app as the assumed distance from Settings, not a measurement. (The athlete summary's release map, which has no per-throw physics, uses a fixed 7.7 m labelled "assumed regulation distance" when fewer than 3 throws have a measured distance.)

### 1.14 Reliability and quality grading

**Per-stage grades** (`quality.py`; thresholds provisional pending an annotation study):

| Stage | GOOD | WARNING | POOR |
|---|---|---|---|
| Pose | required landmarks usable in ≥ 90 % of frames and ≥ 90 % of frames within ±50 ms of release | ≥ 70 % and ≥ 60 % | otherwise |
| Bag | found in ≥ 90 % of flight frames, no gap > 3 frames, ≤ 10 % outliers, noise σ ≤ 2 px | ≥ 70 % coverage, no gap > 6 frames | otherwise, or no tracked flight |
| Calibration | an independent in-plane scale agrees with the gravity scale within 10 % | a single scale source (gravity-only or measured-only) | no physical scale |
| Release | confirmed by a person, or the two cues within 4 frames (67 ms), ≥ 6 launch-fit samples, angle SE ≤ 3° | automatic with a 5–6-frame window, a failed fit check, or an in-hand check that could not run | no confirmed release or cues > 6 frames apart |

**Per-metric rules** (`reliability.py`), for each coach metric on each throw: (1) *visible* — every defining landmark has confidence ≥ 0.35 in release ± 2 frames; (2) *in plane* — each defining segment ≥ 70 % of its median projected length (else foreshortened); (3) *stable* — filtered within 0.1 arm lengths of raw; (4) *plausible* — inside wide physiological bounds; (5) *release-window sensitivity* — an "at release" value that changes by more than its noise floor between the two release cues gets a caution; (6) bag metrics inherit the bag/release/scale grades. Result: **reliable**, **caution** (shown with the reason), **unreliable** (value withheld as "—, insufficient tracking quality"), or **not measured**. Withheld values (unreliable, or unavailable) never enter athlete analyses; the app and the Python engine apply the same rule.

**Noise floors** — the smallest difference the analysis will interpret (`reliability.py`, `performance.py`):

| Metric | Floor | Basis (provisional unless stated) |
|---|---|---|
| Release speed | 0.15 m/s (0.2 arm lengths/s) | ~2 × typical fit SE at 60 fps |
| Release angle | 3°, or 2 × median per-throw fit SE when available | fit SE (data-driven) |
| Release height | 0.03 m (0.05 arm lengths) | bag centroid + foot landmark noise |
| Release point (forward of shoulder) | 0.05 arm lengths | centroid + shoulder noise |
| Wrist speed at release / peak | 0.3 arm lengths/s | ~4 px wrist noise differentiated at 60 fps |
| Peak wrist speed timing | 35 ms | ±1 frame on peak and on release |
| Hand direction at release | 5° | — |
| Arm angle at release, backswing | 5° | ~4 px over ~100 px shoulder–wrist line |
| Peak arm swing speed | 40 °/s | arm-angle noise differentiated |
| Elbow angle at release | 10° | simulated 4 px landmark noise at pilot framing |
| Peak elbow extension speed / timing | 150 °/s / 50 ms | exploratory derivative |
| Forward-swing time | 0.035 s | ±2 frames |
| Tempo | 0.15 | ±2 frames per phase boundary |
| Trunk lean at release | 5° | simulated noise on hip–shoulder segment |

The light validation found release-value changes from a centroid-method change (blob → silhouette) of median 0.8° / 0.08 m/s / 1.6 cm (max 3.5° / 0.27 m/s / 9.5 cm), the same order as these floors.

---

## 2. Application & Feedback Framework

### 2.1 The coach app

A native macOS SwiftUI app with a packaged Python engine. The window is a three-column `NavigationSplitView` following Apple's Human Interface Guidelines:

```
Sidebar            Content column                   Detail
ATHLETES     +     Player 1                          Throw report     (a throw selected)
 Player 1  9       ┌ Summary · all throws ┐          Athlete summary  (Summary selected)
 Player 2  6       Throw 1   Hole  7.9 m/s 38°
 Player 3 11       Throw 2   —     8.1 m/s 44°
TOOLS              …                   [Import]
 Launch Lab                                          Launch Lab (content column hidden)
```

- **Throw report** (one throw): header with a one-click result picker (Hole 3 · Board 1 · Miss 0); **verdict card** (§2.3; a throw analysed before verdicts existed shows "No verdict yet" with a **Refresh Summary** button that rebuilds insights from the saved results — no pose re-run — and the report also does this once automatically); replay card (video with skeleton, measured bag path solid and the drag-free model dashed, or a stick-figure animation; event chips for backswing, peak wrist speed, release, apex, first contact); up to eight **metric tiles** (release speed, angle, height; elbow at release, trunk lean, peak wrist speed, backswing, tempo), each with ± SE or noise floor and a range bar showing the athlete's min–max, IQR and this throw — plus the physics hole window for speed and angle; time plots (joint angles, wrist speed, bag flight, timing strip); and a closed "Scientific details" disclosure (full metric table, grades and rules, launch fit, provenance). Correction tools are in one **Fix Tracking** sheet.
- **Athlete summary**: scoring tiles; coach focus (priorities and "observed differences, not yet advice"); a sortable **throw comparison table** with a *Median · SD* footer that shows $n$ per column and withholds the SD below five values (out-of-date throws — corrections or settings changed since their analysis — stay in the table, greyed with the re-analyze glyph, but are left out of the footer and of the release map until re-analyzed); consistency plots; the release map; research details (evidence chain, data-trust grade counts, compensation).
- **Launch Lab**: a to-scale scene with the regulation board and animated drag-free flight; controls for speed, angle, height and release-to-board distance ("start from" any measured throw; "solve for the hole"); readouts; a **success map** over angle 10–70° × speed 3–11 m/s coloured by predicted zone with the athlete's throws overlaid; and sensitivity readouts (§2.6).

No composite 0–100 scores are computed or shown; earlier reference-similarity, consistency and tracking indices were removed on 22 Sep 2026 because their tolerances and weights had no empirical basis.

### 2.2 How a coach uses it

1. **Upload** — Import Videos (one clip per throw or per session), assign to an athlete.
2. **Analyse** — the engine runs automatically; the throw appears with a spinner, then the Throw report opens with the verdict at the top.
3. **Record the result** — one click (Hole / Board / Miss). This is what unlocks the scored-vs-miss comparison and priorities.
4. **Check** — glance at the replay and data notes; fix tracking only if a grade is WARNING/POOR.
5. **Cue** — use the verdict's "to work on" line for the next throw; after a session, use the Athlete summary's coach focus to pick one practice theme and the named "typical scored throws" to show the athlete on video.
6. **Explore** — use Launch Lab to show the athlete how much a change in speed, angle or height moves the landing.

### 2.3 The per-throw verdict

Produced in Python (`verdict.py`) from tested math, never in the Swift views. Two independent checks:

1. **Physics check** (needs usable release speed, angle and height): predicted first contact from the drag-free model at distance $d$ (§1.13), the **speed to hole** $v^*$ at the same angle and height (bisection, Eq. 3.2.5), $\Delta v = v - v^*$, and the local sensitivity $\partial x/\partial v$ by central difference (±0.05 m/s). Values carry "≈" whenever the calibration grade is not GOOD.
2. **Personal comparison** (needs ≥ 5 other analysed throws with a usable value — not unreliable or unavailable — of the metric): a value is flagged when $\lvert x - \tilde x\rvert > \max(\text{noise floor},\ 1.5\cdot\text{IQR}/1.349)$, i.e. about 1.5 robust SD from the athlete's median, using the athlete's other throws.

**Selection.** Only flags the verdict can *name* count: non-exploratory metrics with a plain-language description (all coach metrics except the two exploratory elbow-extension derivatives). *Headline* = the physics result if available ("Released at 38° and ≈7.9 m/s: the flight model puts first contact on the board, ≈0.21 m short of the hole"); else, with named flags, "This throw differed from the athlete's usual pattern in $k$ measured variable(s)" (adding "the $j$ largest are listed" when more than are listed); else "Every reliable measurement was within this athlete's usual range" — only when at least one named metric was actually compared (this throw and ≥ 5 other throws have usable values); else "Measured. $n$ more analyzed throw(s) is/are needed…" (fewer than 5 other throws) or, with ≥ 5 other throws that lack usable values for the same metrics, "more analyzed throws are needed". *To work on* = release speed when $\lvert\Delta v\rvert\cdot\lvert\partial x/\partial v\rvert > 0.15$ m (speed carries the physics cue because it is the most sensitive and most trainable variable), plus flagged release variables and at most two flagged body metrics, each named as "unusual for this athlete" with its value and usual range (negative numbers with a true minus sign). *Went well* = speed matching the hole, or elbow/trunk/peak wrist speed within the usual range. *Data notes* = WARNING/POOR grades. At most five items, ordered fix → good → note. All wording is associational; the text never claims a body variable caused the landing.

### 2.4 Athlete-level analyses

**Scoring** (`zones.sports_stats`): per-bag values 3 (hole), 1 (board), 0 (off/foul); unknown results are excluded, never treated as misses. $\text{PPR} = 4\times$ mean points per bag (gross, no cancellation); In % / On % / Off % are shares of known outcomes. These are per-bag values, not the cancellation score of a round.

**Scored vs miss** (`performance.py`), within one athlete, over a fixed, pre-specified list of release/body variables: per group $n$, median, quartiles, SD, CV (ratio-scale only); Cliff's δ (Eq. 3.13.3) and Hedges' $g$. A variable "differed" only when **all** hold: ≥ 5 throws per group; $\lvert\delta\rvert \ge \delta_{\text{crit}}$, where $\delta_{\text{crit}}$ is the larger of 0.474 ("large") and a Bonferroni chance level across all tests (Eq. 3.13.4); and the median difference exceeds the noise floor. A second test catches two-sided misses (too high *and* too low): misses' distance from the scored median vs scored throws' leave-one-out distance.

**Coaching priority gate — five checks** (`coaching.py`). A variable becomes a priority only if it is:

1. **associated with scoring** (the Cliff's-δ rule above, as a shift or as spread);
2. **larger than measurement uncertainty** (median difference > noise floor);
3. **repeatable** (bootstrap 95 % CI of the miss − scored median difference excludes 0; 2000 resamples);
4. **measured reliably** (≥ 80 % of the athlete's values passed the per-throw rules);
5. **interpretable and modifiable** (not an exploratory derivative).

A difference above the noise floor with $\lvert\delta\rvert \ge 0.33$ that fails any check is shown as an **observed difference, not advice**, with the failed checks named. A priority names the athlete's typical scored throws (closest to the scored median) to review on video.

**Consistency.** Per metric: median, IQR, sample SD, CV (ratio-scale) and $\text{SD}/\text{noise floor}$: ≤ 1 "within measurement noise", > 2 "variable", else "moderate". Hopkins' smallest worthwhile change $0.2\times\text{SD}$ is recorded. Waveforms: elbow-angle curves resampled to 101 points over normalised movement time; pointwise mean ± 1 SD (a point needs ≥ 5 supporting throws; a waveform ≥ 80 % supported points). Consistency describes repeatability, not quality — a tightly grouped set of misses is consistent but inaccurate.

**Evidence chain** (`coaching.evidence_chain`): within-athlete Spearman ρ with a 2000-resample percentile bootstrap 95 % CI (fixed seed) for pre-specified links — body → release (wrist speed → release speed; arm angle → release angle; peak-wrist timing → release angle), release → flight (angle → apex height; speed → flight time), release → outcome and body → outcome. A link is "supported" only when $n \ge 8$ and the CI excludes 0. Pilot example: Player 3, release angle → apex height, ρ = 0.78, n = 10 (as physics expects).

**Compensation estimate** (after Müller & Sternad, 2004): with ≥ 8 scaled throws, the SD of each throw's model-predicted landing distance is compared with the SD when release speeds are randomly re-paired with the angles and heights (500 permutations). Ratio = SD(shuffled)/SD(observed); ratio > 1.1 with < 5 % of shuffles as tight → "speed and angle compensate"; ratio < 0.9 with > 95 % → "errors add up"; 0.9–1.1 → close to random pairing. When the ratio is beyond 0.9–1.1 but the permutation share does not rule out chance, the message says so ("No clear compensation… too often to rule out chance" or "wider than at random pairing, but not beyond chance") instead of calling it close to random pairing.

**Chain analyses** (`chain_analysis.py`; ≥ 8 throws for correlations, ≥ 5 per group for group comparisons; pre-specified lists): the covariance-aware landing error budget (§3.11); predicted-vs-measured landing (Pearson $r^2$); body → release Spearman links with Bonferroni-adjusted bootstrap CIs across 5 pairs (hand speed → release speed flagged near-tautological); movement → outcome with Cliff's δ and rank correlation with $\lvert$landing error$\rvert$; the speed–angle trade-off as a Theil–Sen slope with 95 % CI (Linthorne, 2001: the best angle is athlete-specific, so a slope, not a target angle); and shoulder–elbow coordination variability (pointwise SD of time-normalised angle–angle curves; curves with > 20 % missing dropped).

**Status on the pilot library:** no outcomes have been recorded yet, so dashboards show profiles, consistency and the evidence chain but no priorities.

### 2.5 Coaching rationale linked to biomechanics

The analysis hierarchy is a hypothesis structure, not a causal claim: **body movement → release mechanics → bag flight → first contact / rest → points**. The design choices follow from biomechanics:

- **Release conditions are the proximal cause of landing.** Once the bag leaves the hand, its path is (to first order) determined by release speed, angle and height (projectile motion), so the verdict and priorities start at release and only then look back to the body.
- **Speed is the dominant cue.** Near typical releases, landing is far more sensitive to 0.1 m/s of speed than to 1° of angle or 1 cm of height (Launch Lab sensitivities), and speed is trainable through swing length and tempo.
- **Accuracy, not a single ideal form.** Accurate throwers can succeed with different strategies — reducing timing sensitivity or reducing timing error (Nasu et al., 2014) — and the best release angle is athlete-specific (Linthorne, 2001). Hence every comparison is **within athlete** (scored vs miss throws of the same person), never against a "perfect" template.
- **Slightly faster than the minimum.** The most accurate throws sit slightly above the minimum speed that reaches the target (Venkadesan & Mahadevan, 2017); the chain reports speed margin over minimum and energy match rather than a fixed target.
- **Variability can be functional.** Errors in one release variable can be offset by another (Müller & Sternad, 2004); the compensation estimate and covariance-aware error budget tell the coach whether to train the *combination* rather than each variable separately.
- **Sequencing is described, not graded.** The shoulder → elbow → wrist-speed → release peak order is shown (Putnam, 1993), but cornhole is a slow accuracy swing, so no proximal-to-distal "grade" is applied.
- **Measurement honesty.** Differences smaller than the noise floor are never reported, and unreliable values are withheld rather than shown — so a cue is only given when the data can support it.

### 2.6 Launch Lab sensitivity

Launch Lab (`LaunchModel.swift`, identical equations to `zones.py`) shows the change in first-contact horizontal position as **cm per 0.1 m/s**, **cm per 1°** and **cm per 1 cm** of release height, from central differences with steps 0.01 m/s, 0.05° and 0.005 m (Eq. 3.3.1), reported only when both perturbed throws still land on the deck.

---

## 3. Mathematics

Symbols: $t$ time (s); $\text{fps}$ frame rate (Hz); $\Delta t = 1/\text{fps}$; $v$ release speed (m/s); $\theta$ release angle above horizontal (°/rad); $h$ release height above the floor (m); $d$ horizontal distance from release to the board's front edge (m); $g = 9.80665\ \text{m/s}^2$ (standard gravity, `bag.GRAVITY_M_S2`, `LaunchModel.gravity`); $m$ bag mass (kg).

### 3.1 Coordinates and time

Image pixel $(u, v_{\text{img}})$ has $u$ right and $v_{\text{img}}$ down. Analysis axes: $x = s\,u$, $y = -v_{\text{img}}$, with $s = \pm 1$ chosen so $+x$ points toward the target. Frame $f$ is at $t = f/\text{fps}$. Normalised movement time $\tau = (f - f_{\text{start}})/(f_{\text{end}} - f_{\text{start}}) \in [0,1]$, resampled at 101 points.

### 3.2 Drag-free projectile, board contact and speed to hole

Release at the origin of horizontal distance, height $h$:

$$x(t) = v\cos\theta\; t, \qquad y(t) = h + v\sin\theta\; t - \tfrac12 g t^2 \tag{3.2.1}$$

**Floor:** first positive root of $-\tfrac12 g t^2 + v_y t + h = 0$, with $v_x = v\cos\theta$, $v_y = v\sin\theta$. If $x_{\text{floor}} = v_x t_{\text{floor}} < d$, the throw is short.

**Front face:** at $t_f = d/v_x$, if $y(t_f) < h_f$ (front height 3 in = 0.0762 m) the bag strikes the front of the board.

**Deck:** the deck surface is $y = h_f + (x - d)\tan\alpha$ with slope

$$\alpha = \arcsin\!\left(\frac{h_b - h_f}{L}\right) = \arcsin\!\left(\frac{12 - 3}{48}\right) \approx 10.81^\circ \tag{3.2.2}$$

Substituting (3.2.1) gives the contact time as the first positive root of

$$-\tfrac12 g t^2 + (v_y - v_x\tan\alpha)\,t + (h - h_f + d\tan\alpha) = 0 \tag{3.2.3}$$

and the landing position up the deck $s = (v_x t - d)/\cos\alpha$; it is on the board if $0 \le s \le L = 1.2192$ m, otherwise long. Distance from the hole centre along the deck: $s - s_{\text{hole}}$ with $s_{\text{hole}} = L - 9\ \text{in} = 0.9906$ m.

Roots use $t = \dfrac{-b \pm \sqrt{b^2 - 4ac}}{2a}$ and keep the smallest $t > 10^{-12}$.

**Required speed (closed form, `mechanics.required_speed`).** With the hole centre at horizontal distance $X = d + s_{\text{hole}}\cos\alpha$ and height $Y = h_f + s_{\text{hole}}\sin\alpha$, the trajectory $y(X) = h + X\tan\theta - \dfrac{g X^2}{2v^2\cos^2\theta}$ passes through $(X, Y)$ when

$$v_{\text{req}} = \sqrt{\frac{g X^2}{2\cos^2\theta\,\left(h + X\tan\theta - Y\right)}} \tag{3.2.4}$$

(undefined when the bracket is ≤ 0: no speed reaches the hole at that angle). **Speed to hole** in the verdict and Launch Lab solves $s(v) - s_{\text{hole}} = 0$ by 80 bisection steps on $v \in [0.5, 25]$ m/s (Python) / $[0.5, 20]$ m/s (Swift) using the full contact model (3.2.3):

$$v^* : \; s(v^*, \theta, h, d) = s_{\text{hole}} \tag{3.2.5}$$

**Minimum speed over all angles** (`mechanics.minimum_speed`), with $\Delta y = Y - h$:

$$v_{\min}^2 = g\left(\Delta y + \sqrt{X^2 + \Delta y^2}\right) \tag{3.2.6}$$

**Energy match and speed margin:** $100\,(v^2/v_{\text{req}}^2 - 1)$ % and $100\,(v/v_{\min} - 1)$ %.

### 3.3 Sensitivity of the landing

Central differences of the first-contact horizontal position $x_c(v,\theta,h)$:

$$\frac{\partial x_c}{\partial q} \approx \frac{x_c(q + \delta) - x_c(q - \delta)}{2\delta}, \quad \delta_v = 0.01\ \text{m/s},\ \delta_\theta = 0.05^\circ,\ \delta_h = 0.005\ \text{m} \tag{3.3.1}$$

displayed as $100\times0.1\,\partial x_c/\partial v$ cm per 0.1 m/s, $100\,\partial x_c/\partial\theta$ cm per 1°, and $100\times0.01\,\partial x_c/\partial h$ cm per 1 cm. The verdict uses $\delta_v = 0.05$ m/s; the error-budget Jacobian (`mechanics.landing_jacobian`) uses $\delta = (0.01\ \text{m/s}, 0.1^\circ, 0.005\ \text{m})$ on the landing along the extended deck plane. The verdict's "to work on" threshold is $\lvert\Delta v\rvert\,\lvert\partial x_c/\partial v\rvert > 0.15$ m.

### 3.4 Joint and segment angles

**Included angle** at vertex $B$ with $\mathbf u = A - B$, $\mathbf w = C - B$ (numerically stable form, `geometry.vector_angle_degrees`):

$$\angle ABC = \operatorname{atan2}\!\big(\lvert u_x w_y - u_y w_x\rvert,\ \mathbf u\cdot\mathbf w\big)\cdot\frac{180}{\pi} \in [0^\circ, 180^\circ] \tag{3.4.1}$$

equivalent to $\arccos\!\big(\mathbf u\cdot\mathbf w / (\lVert\mathbf u\rVert\lVert\mathbf w\rVert)\big)$; zero-length vectors give a missing value. Elbow angle $= \angle SEW$ (180° = straight).

**Segment orientation:** $\operatorname{atan2}(\Delta y, \Delta x)$, unwrapped within finite runs before differentiation; comparisons use the shortest circular difference $((\Delta + 180) \bmod 360) - 180$. — Eq. (3.4.2)

**Arm angle** (from straight down, + toward the target), with $\mathbf D = W - S$ in image axes:

$$\varphi = \operatorname{atan2}\!\big(s\,D_u,\ D_{v}\big) \tag{3.4.3}$$

**Trunk inclination**, $\mathbf T = M_S - M_H$ in analysis axes ($M$ = bilateral midpoints):

$$\beta = \operatorname{atan2}(T_x, T_y), \quad 0^\circ = \text{vertical},\ + = \text{toward target} \tag{3.4.4}$$

**Projected arm length** $L_{\text{arm}} = \operatorname{median}_f\lVert S-E\rVert + \operatorname{median}_f\lVert E-W\rVert$; normalised point $P_{\text{norm}} = (P - S)/L_{\text{arm}}$ (arm lengths). — Eq. (3.4.5)

**Pendulum drive ratio.** A uniform rigid rod of length $L$ released from amplitude $A$ reaches, at the bottom, $\tfrac12\big(\tfrac13 mL^2\big)\omega^2 = mg\tfrac L2(1 - \cos A)$, so

$$\omega_{\text{passive}} = \sqrt{\frac{3g(1 - \cos A)}{L}}, \qquad \text{ratio} = \frac{\omega_{\text{measured}}}{\omega_{\text{passive}}} \tag{3.4.6}$$

**Hand point** (rigid-hand model): $\mathbf H = \mathbf W + 0.34\,L_{\text{arm}}\,\dfrac{\mathbf W - \mathbf E}{\lVert\mathbf W - \mathbf E\rVert}$. — Eq. (3.4.7)

### 3.5 Finite-difference derivatives

On each contiguous finite run (≥ 3 samples; gaps are never bridged), `numpy.gradient` with second-order edges:

$$\dot x_i \approx \frac{x_{i+1} - x_{i-1}}{2\Delta t}, \qquad \dot x_0 \approx \frac{-3x_0 + 4x_1 - x_2}{2\Delta t}, \qquad \dot x_{N} \approx \frac{3x_N - 4x_{N-1} + x_{N-2}}{2\Delta t} \tag{3.5.1}$$

Second derivatives apply (3.5.1) twice. Angular velocity $\omega = d\theta/dt$ (°/s); wrist velocity $\mathbf v_W = d\mathbf W/dt$, speed $\lVert\mathbf v_W\rVert$, direction $\operatorname{atan2}(v_{W,y}, v_{W,x})$; shoulder-relative wrist velocity $\mathbf v_{\text{rel}} = \mathbf v_W - \mathbf v_S$. Timing: $\Delta t_{\text{peak}} = 1000\,(f_{\text{peak}} - f_{\text{rel}})/\text{fps}$ ms. Durations: $(f_2 - f_1)/\text{fps}$; tempo $= (f_{\text{back}} - f_{\text{start}})/(f_{\text{rel}} - f_{\text{back}})$.

### 3.6 Butterworth filter and residual analysis

$n$th-order Butterworth low-pass magnitude response with cutoff $f_c$:

$$\lvert H(f)\rvert^2 = \frac{1}{1 + (f/f_c)^{2n}}, \qquad n = 4,\ f_c = 6\ \text{Hz} \tag{3.6.1}$$

Applied forward then backward (zero phase), the overall response is $\lvert H(f)\rvert^2$, so the effective attenuation at $f_c$ is −6 dB rather than −3 dB; the code does not apply a double-pass cutoff correction.

**Winter residual analysis** (Winter, 2009, §3.4.4.3; `scripts/residual_analysis.py`). For each trial cutoff $f_c \in [1, \min(25, 0.45\,\text{fps})]$ Hz (0.5 Hz steps):

$$R(f_c) = \sqrt{\frac1N\sum_{i=1}^{N}\big(x_i - \hat x_i(f_c)\big)^2} \tag{3.6.2}$$

A straight line $R \approx a + b f_c$ is fitted to the noise-dominated tail (12–20 Hz); its intercept $a$ estimates the noise RMS. The chosen cutoff is the first $f_c$ with $R(f_c) \le a$. (Challis, 1999, gives a related automatic criterion based on residual whiteness.)

### 3.7 Pinhole camera, PnP and homographies

Pinhole intrinsics from an assumed horizontal field of view (image width $W_{\text{img}}$, height $H_{\text{img}}$):

$$f = \frac{W_{\text{img}}/2}{\tan(\text{HFOV}/2)}, \qquad K = \begin{pmatrix} f & 0 & W_{\text{img}}/2 \\ 0 & f & H_{\text{img}}/2 \\ 0 & 0 & 1\end{pmatrix} \tag{3.7.1}$$

Projection of a world point $\mathbf X$: $\lambda\,(u, v, 1)^\top = K\,[R \mid \mathbf t]\,(\mathbf X, 1)^\top$. — Eq. (3.7.2)

**PnP.** Board frame: $x$ horizontal toward the back of the board, $y$ up, $z$ across. Deck corners (m): $(0, h_f, \mp w/2)$ and $(L\cos\alpha,\ h_f + L\sin\alpha,\ \pm w/2)$ with $w = 0.6096$ m. `solvePnP` (IPPE, planar) finds $R, \mathbf t$ minimising reprojection error of the four observed corners.

**Throw-plane homography** (the vertical plane $z = 0$ through the board centre line):

$$\lambda\,(u, v, 1)^\top = K\,[\mathbf r_1\ \mathbf r_2\ \mathbf t]\,(x, y, 1)^\top \equiv H_{\text{plane}}\,(x, y, 1)^\top \tag{3.7.3}$$

Image points are mapped into metres by $H_{\text{plane}}^{-1}$. Local scale at image point $\mathbf p$: $q(\mathbf p) = 1/\lVert H_{\text{plane}}^{-1}(\mathbf p + (1,0)) - H_{\text{plane}}^{-1}(\mathbf p)\rVert$ px/m. **Out-of-plane angle** of the throw line: $\phi = \arcsin\lvert R_{31}\rvert$ (the camera-depth component of the board's $x$ axis). — Eq. (3.7.4)

**Deck homography** (image → board inches, top-down; origin at a front corner, $x$ 0–24 across, $y$ 0–48 from the front edge to the back): the $3\times3$ $H$ that maps the four ordered image corners to $(0,0),(24,0),(24,48),(0,48)$, solved exactly by the four-point DLT (`cv2.getPerspectiveTransform`); $(x, y) = (\tilde x/\tilde w, \tilde y/\tilde w)$ with $(\tilde x, \tilde y, \tilde w)^\top = H(u, v, 1)^\top$. Valid only for points on the deck plane (not airborne points or floor contacts).

### 3.8 Gravity scale calibration

**Gravity-calibrated HFOV.** For each candidate HFOV, map the accepted flight points into the throw plane (3.7.3), fit $y(t) = c_0 + c_1 t + c_2 t^2$ by least squares, and define $a_y(\text{HFOV}) = 2c_2$. Solve

$$a_y(\text{HFOV}) = -g, \qquad \text{HFOV} \in [55^\circ, 75^\circ] \tag{3.8.1}$$

by grid bracketing (0.25°) and bisection (≤ 40 steps, tolerance $10^{-4}$°). The metric scale $q$ (px/m) is evaluated at the release point.

**Image-plane gravity scale** (fixed camera): a free bag's image-down acceleration $a$ (px/s²) from a Huber-weighted quadratic over the frames strictly between release and contact gives

$$q = \frac{a}{g}, \qquad \sigma_q = \frac{2\sqrt{\operatorname{Var}(c_2)}}{g}, \qquad g_{\text{apparent}} = \frac{a}{q_{\text{stick}}} \tag{3.8.2}$$

Conversions: $v_{\text{m/s}} = v_{\text{px/s}}/q$; a known in-plane length gives $q = L_{\text{px}}/L_{\text{m}}$. — Eq. (3.8.3)

**Relative scale uncertainty** for the Monte Carlo (`chain.scale_relative_sd`), floored at 1 %:

$$\sigma_{\text{rel}} = \max\!\left(0.01,\ \frac{\lvert q(\widetilde{\text{HFOV}} + \tfrac{\text{IQR}}2) - q(\widetilde{\text{HFOV}} - \tfrac{\text{IQR}}2)\rvert}{2q}\right) \text{ (pooled)}, \quad \max\!\left(0.01,\ \frac{\lvert q_{55} - q_{75}\rvert}{4q}\right) \text{ (single throw)} \tag{3.8.4}$$

(treating the 55–75° band as ≈ ±2 SD), and 5 % if no uncertainty is reported.

### 3.9 Kalman filter and Rauch–Tung–Striebel smoother (bag flight)

Per image axis the state is $\mathbf s = (p, \dot p, \ddot p)^\top$ (px, px/s, px/s²), white-noise-jerk (constant-acceleration) model:

$$\mathbf s_{k+1} = F\mathbf s_k + \mathbf w_k,\quad F = \begin{pmatrix}1 & \Delta t & \tfrac12\Delta t^2\\ 0 & 1 & \Delta t\\ 0 & 0 & 1\end{pmatrix},\quad Q = q\begin{pmatrix}\tfrac{\Delta t^5}{20} & \tfrac{\Delta t^4}{8} & \tfrac{\Delta t^3}{6}\\ \tfrac{\Delta t^4}{8} & \tfrac{\Delta t^3}{3} & \tfrac{\Delta t^2}{2}\\ \tfrac{\Delta t^3}{6} & \tfrac{\Delta t^2}{2} & \Delta t\end{pmatrix} \tag{3.9.1}$$

Measurement $z_k = p_k + e_k$, $e_k \sim \mathcal N(0, \sigma^2)$. The acceleration is estimated, not fixed to $g$, so perspective and drag are absorbed.

- **Initial noise:** for white noise, $\operatorname{Var}(\Delta^3 z) = 20\sigma^2$, so $\hat\sigma = 1.4826\,\operatorname{MAD}(\Delta^3 z)/\sqrt{20}$, with $\Delta^3 z_i = z_{i+3} - 3z_{i+2} + 3z_{i+1} - z_i$.
- **Leave-one-out gate:** point $i$ is an outlier if its distance from a quadratic through its neighbours within ±5 frames (itself excluded, ≥ 5 neighbours) exceeds $\max(5\hat\sigma, 4\ \text{px})$; flagged points are re-tested against unflagged neighbours only.
- **Noise model:** $(\sigma, q)$ maximise the innovation log-likelihood $\ell = -\tfrac12\sum_k\big(\boldsymbol\nu_k^\top S_k^{-1}\boldsymbol\nu_k + \ln\det S_k + 2\ln 2\pi\big)$ over $\sigma \in \{0.5, 0.75, 1, 1.5, 2, 3, 4, 6\}$ px and $q \in \{10^{3}, 10^{3.5}, \dots, 10^{10}\}$ px²/s⁵.
- **Forward filter:** predict $\hat{\mathbf s}_{k|k-1} = F\hat{\mathbf s}_{k-1}$, $P_{k|k-1} = FP_{k-1}F^\top + Q$; update with innovation $\boldsymbol\nu_k = z_k - H\hat{\mathbf s}_{k|k-1}$, $S_k = HP_{k|k-1}H^\top + \sigma^2 I$, $K_k = P_{k|k-1}H^\top S_k^{-1}$, $\hat{\mathbf s}_k = \hat{\mathbf s}_{k|k-1} + K_k\boldsymbol\nu_k$, $P_k = (I - K_kH)P_{k|k-1}$.
- **RTS smoother** (backward): $C_k = P_kF^\top P_{k+1|k}^{-1}$, $\hat{\mathbf s}_{k|N} = \hat{\mathbf s}_k + C_k(\hat{\mathbf s}_{k+1|N} - \hat{\mathbf s}_{k+1|k})$, $P_{k|N} = P_k + C_k(P_{k+1|N} - P_{k+1|k})C_k^\top$. — Eq. (3.9.2)

### 3.10 Least-squares launch fit and standard errors

**Huber IRLS polynomial** (`bag._robust_polynomial`): design matrix $X$ with columns $1, t, t^2$; iterate (≤ 12 times) weighted least squares $\hat{\boldsymbol\beta} = (X^\top WX)^{-1}X^\top W\mathbf y$ with weights

$$w_i = \begin{cases}1 & \lvert r_i\rvert \le 1.345\,\hat s\\[2pt] \dfrac{1.345\,\hat s}{\lvert r_i\rvert} & \text{otherwise}\end{cases}, \qquad \hat s = 1.4826\,\operatorname{median}\lvert r_i - \operatorname{median}(r)\rvert \tag{3.10.0}$$

**Free quadratic launch** ($t$ from the release frame): $x(t) = a_x + b_x t + c_x t^2$, $y(t) = a_y + b_y t + c_y t^2$ in image pixels, so

$$v_x = s\,b_x,\quad v_{\text{up}} = -b_y,\quad v = \sqrt{v_x^2 + v_{\text{up}}^2},\quad \theta = \operatorname{atan2}(v_{\text{up}}, v_x) \tag{3.10.1}$$

**Gravity-constrained launch** (image $y$ down, scale $q$ px/m):

$$y(t) - \tfrac12 g q\, t^2 = a_y + b_y t, \qquad x(t) = a_x + b_x t \tag{3.10.2}$$

**Covariance and standard errors:**

$$\widehat{\operatorname{Cov}}(\hat{\boldsymbol\beta}) = s^2 (X^\top WX)^{-1}, \qquad s^2 = \frac{\sum_i w_i r_i^2}{n - p} \tag{3.10.3}$$

(reported only with $n - p \ge 2$). Delta-method propagation, treating the two axes as independent ($\sigma_x^2 = \operatorname{Var}(b_x)$, $\sigma_y^2 = \operatorname{Var}(b_y)$):

$$\sigma_\theta^2 = \frac{v_y^2\sigma_x^2 + v_x^2\sigma_y^2}{v^4}, \qquad \sigma_v^2 = \frac{v_x^2\sigma_x^2 + v_y^2\sigma_y^2}{v^2} \tag{3.10.4}$$

Fit quality: $\text{RMSE} = \sqrt{\tfrac1n\sum\big(r_{x,i}^2 + r_{y,i}^2\big)}$; the release fit is withheld if RMSE $/L_{\text{arm}} > 0.06$ (configured pilot heuristic). The ballistic model check reports the same RMSE in sample and out of sample (first half → second half).

### 3.11 Landing error budget (covariance-aware)

With Jacobian $\mathbf J = (\partial R/\partial v,\ \partial R/\partial\theta,\ \partial R/\partial h)$ at the athlete's mean release (3.3.1) and per-variable sample SDs $\sigma_q$:

$$\sigma_{R,\text{ind}}^2 \approx \sum_q\left(\frac{\partial R}{\partial q}\sigma_q\right)^2, \qquad \text{share}_q = \frac{(\partial R/\partial q\ \sigma_q)^2}{\sigma_{R,\text{ind}}^2} \tag{3.11.1}$$

Using the athlete's empirical $3\times3$ release covariance $\Sigma$ (sample, $n-1$):

$$\sigma_{R,\text{cov}} = \sqrt{\mathbf J\,\Sigma\,\mathbf J^\top}, \qquad \text{covariation reduction} = 1 - \frac{\sigma_{R,\text{cov}}}{\sigma_{R,\text{ind}}}, \qquad \text{share}^{\text{cov}}_i = \frac{J_i(\Sigma\mathbf J^\top)_i}{\mathbf J\Sigma\mathbf J^\top} \tag{3.11.2}$$

Covariance shares can be negative when a pair's covariation reduces spread; a reduction > 0.15 names the pair with the most negative cross term $2J_aJ_b\Sigma_{ab}$. The headline predicted SD is the SD across throws of each throw's own release run through the nonlinear model (no linearisation). Predicted vs measured: Pearson $r^2$.

### 3.12 Mechanical energy, momentum, force and power of the bag

$$\mathbf p = m\mathbf v,\qquad KE = \tfrac12 m\lVert\mathbf v\rVert^2,\qquad PE = mgh,\qquad E = KE + PE \tag{3.12.1}$$

$$\mathbf F = m(\mathbf a - \mathbf g),\ \ \mathbf g = (0, -g)\ \Rightarrow\ F_x = m a_x,\ F_y = m(a_y + g) \tag{3.12.2}$$

$$P = \mathbf F\cdot\mathbf v, \qquad \frac{dE}{dt} = \frac{d}{dt}\Big(\tfrac12 m\lVert\mathbf v\rVert^2 + mgy\Big) \ \ (\text{check: } \lvert P - dE/dt\rvert \le 0.10\max P) \tag{3.12.3}$$

with $m \in [15.5, 16.0]$ oz $= [0.4394, 0.4536]$ kg (nominal 0.4465 kg), $h$ above the floor line, and $\mathbf a$ from the second derivative of the hand point (3.4.7). **Timing sensitivity** (defined; unavailable on pilot data): $\big(x_c(f_{\text{rel}}+1) - x_c(f_{\text{rel}}-1)\big)/(2\Delta t)\times 0.010$ s.

**Monte Carlo propagation.** For draws $j = 1\dots500$: $s_j \sim \mathcal N(1, \sigma_{\text{rel}})$, $m_j \sim \mathcal U(m_{\min}, m_{\max})$,

$$v_j = (v + \varepsilon_{v,j})\,s_j,\quad \theta_j = \theta + \varepsilon_{\theta,j},\quad h_j = (h + \varepsilon_{h,j})\,s_j,\quad d_j = d\,s_j,\quad \varepsilon \sim \mathcal N(0, \text{SE}^2) \tag{3.12.4}$$

and for the body chain, joint positions $\times s_j$ plus 6 Hz-filtered Gaussian noise (4 px per axis, converted to metres). Every quantity is recomputed per draw through the same formulas; the 95 % interval is the 2.5th–97.5th percentile. Force direction draws are wrapped around the nominal value, $((\psi_j - \psi_0 + 180) \bmod 360) - 180$, before the interval.

### 3.13 Descriptive statistics and effect sizes

**Median** of sorted $x_{(1)} \le \dots \le x_{(n)}$: $x_{((n+1)/2)}$ for odd $n$, the mean of the two middle values for even $n$.

**Sample SD** ($n-1$): $s = \sqrt{\tfrac{1}{n-1}\sum_i (x_i - \bar x)^2}$; CV $= 100\,s/\bar x$ (ratio-scale only). The app withholds the SD in the throw-comparison footer below 5 values. — Eq. (3.13.1)

**Quartiles** (linear interpolation, NumPy default, identical in Swift): with 0-indexed sorted values and $h = p(n-1)$,

$$Q(p) = x_{\lfloor h\rfloor} + (h - \lfloor h\rfloor)\big(x_{\lfloor h\rfloor + 1} - x_{\lfloor h\rfloor}\big),\qquad \text{IQR} = Q(0.75) - Q(0.25) \tag{3.13.2}$$

Robust SD $\approx \text{IQR}/1.349$ (normal distribution).

**Cliff's δ** (scored $a$ vs miss $b$):

$$\delta = \frac{\#\{(i,j): a_i > b_j\} - \#\{(i,j): a_i < b_j\}}{n_a n_b} \in [-1, 1] \tag{3.13.3}$$

**Critical δ** (Bonferroni over $k$ tests, $\alpha = 0.05$; null variance of δ from the Mann–Whitney distribution):

$$\delta_{\text{crit}} = \max\!\left(0.474,\ z_{1-\alpha/(2k)}\sqrt{\frac{n_a + n_b + 1}{3n_an_b}}\right) \tag{3.13.4}$$

**Hedges' g:** $g = \dfrac{\bar a - \bar b}{s_p}\left(1 - \dfrac{3}{4(n_a + n_b) - 9}\right)$, $s_p = \sqrt{\dfrac{(n_a-1)s_a^2 + (n_b-1)s_b^2}{n_a + n_b - 2}}$. — Eq. (3.13.5)

**Landing grouping:** RMS radius $= \sqrt{\tfrac1n\sum\lVert\mathbf P_i - \bar{\mathbf P}\rVert^2}$ (in); target errors $e_x = P_x - T_x$ (− left), $e_y = P_y - T_y$ (− short), $r = \sqrt{e_x^2 + e_y^2}$ (in). **Smallest worthwhile change** $= 0.2\,s$. — Eq. (3.13.6)

### 3.14 Spearman ρ, bootstrap CIs and Theil–Sen

**Spearman ρ** = Pearson correlation of the ranks (ties get average ranks; `scipy.stats.spearmanr`); without ties $\rho = 1 - \dfrac{6\sum d_i^2}{n(n^2-1)}$. Reported only with ≥ 8 complete pairs and variation in both variables. — Eq. (3.14.1)

**Percentile bootstrap CI.** Draw $B = 2000$ resamples of the $n$ pairs with replacement (fixed seed; resamples with a constant variable are skipped); compute $\rho^{*}_b$; the 95 % CI is $[Q_{2.5\%}(\rho^*),\ Q_{97.5\%}(\rho^*)]$ (for $k$ Bonferroni-adjusted tests in `chain_analysis`, $[Q_{\alpha/2k}, Q_{1-\alpha/2k}]$). The same procedure on medians gives the CI of the miss − scored median difference (priority check 3). — Eq. (3.14.2)

**Theil–Sen slope** of release angle on speed: $\hat b = \operatorname{median}_{i<j}\dfrac{\theta_j - \theta_i}{v_j - v_i}$, with its 95 % CI (`scipy.stats.theilslopes`). — Eq. (3.14.3)

**Compensation permutation test:** $\text{ratio} = \overline{\operatorname{SD}}\big(x_c(\pi(v), \theta, h)\big)/\operatorname{SD}\big(x_c(v, \theta, h)\big)$ over 500 random permutations $\pi$. — Eq. (3.14.4)

---

## 4. Adaptations and Assumptions

### 4.1 What was adapted from standard methods, and why

| Standard method | Adaptation here | Reason |
|---|---|---|
| 3D motion capture / calibrated multi-camera | **Single-camera, projected 2D planar analysis** in the camera (sagittal) plane | The course brief asks for a bespoke, accessible system; a phone camera can be used at practice. Values are projected angles, not 3D joint rotations (Sih et al., 2001; Stenum et al., 2021). |
| Fixed tripod camera | **Hand-held camera stabilised** by ECC keyframe registration, affine model | The pilot footage was all hand-held; re-recording was out of scope. Residual drift ≤ 4.6 px after registration. |
| Markers on anatomical landmarks | **Markerless pose** (RTMPose via Sports2D), confidence-masked, 6 Hz Butterworth | No sensors or markers; RTMPose landmarks are model estimates, not palpated joint centres (Needham et al., 2021 report 16–48 mm joint-centre error in 3D). |
| Measurement error from a validation study | **Provisional noise floors** from simulated landmark noise (~4 px) at pilot framing | The athlete is only ~300 px tall (upper arm ~60 px): 2–4 px landmark noise gives ~5–10° elbow-angle SD, as large as real throw-to-throw differences. Floors stop the app from interpreting differences smaller than that. |
| Calibration object in the motion plane | **Regulation board (ACL) + gravity-calibrated field of view**, pooled per session | No meter stick was filmed in the pilot; the board is the only known length, and a single image leaves the focal length ambiguous — gravity on the bag's own flight resolves it. |
| Projectile with aerodynamic drag | **Drag-free** point mass | Drag is not identifiable: horizontal deceleration in the image is confounded with perspective, a drag model did not improve out-of-sample prediction, and simulated drag changes apparent $g$ by only −0.2 to −1.4 % over a flight. |
| Instrumented bag (IMU) | **Video-only bag tracking** | Course rules: no sensors on the bag. |
| Manual release frame | **Automatic release** = first flight centroid beyond 0.45 arm lengths from the wrist, with a second cue as cross-check | 21/21 pilot throws within ±1 frame of a visual audit; manual override always wins. |
| Population norms / "ideal technique" | **Within-athlete** scored-vs-miss comparisons, gated claims | No published cornhole norms exist; accurate throwers use different strategies (Nasu et al., 2014; Linthorne, 2001). |
| Joint kinetics (inverse dynamics) | **Bag-only** mechanics $\mathbf F = m(\mathbf a - \mathbf g)$ | Segment inertias, ground reaction forces and 3D kinematics are unavailable; only the bag's own momentum and energy budget can be computed. |
| Regulation pitch geometry | Regulation **board** constants used for geometry; release-to-board distance **measured** per throw; 7.7 m used only as a labelled fallback | Pilot throws measured roughly 6 m from release to the board front, shorter than the ~7.7 m of regulation play (board-camera estimates; to be confirmed), so assuming the regulation distance would bias every landing prediction. The fallback distance is the Settings value (default 7.7 m), which the coach can change. |

### 4.2 Assumptions

- The throw is approximately planar and the camera views it roughly side-on; out-of-plane angle φ > 20° is flagged, not corrected.
- The camera is level (release height and trunk inclination use image vertical).
- The bag is a point mass after release (no spin, deformation or lift); first contact is predicted without bounce or slide.
- The bag sits rigidly 0.34 arm lengths beyond the wrist along the forearm while in the hand (rigid-hand model; shown to fail at the last ~50–80 ms before release on pilot data).
- Board dimensions are nominal ACL values (24 × 48 in deck, 3 in front, 12 in back, 6 in hole centred 9 in from the back); the actual study board should be measured (certification tolerances ±0.25 in).
- Throws within a recording session share one camera and zoom (for HFOV pooling); a library-wide fallback assumes the same camera in every session and is at most `estimated`.
- Unknown outcomes are unknown — never misses.
- Associations are within one athlete, exploratory, and never causal.

### 4.3 Limitations

| Limitation | Consequence |
|---|---|
| No criterion validation (motion capture / manual digitisation) yet | Landmark, centroid and angle accuracy for this task are unknown; all body noise floors are provisional. |
| Small athlete in frame (pilot) | Elbow-angle noise ~5–10° SD; derivative metrics (elbow extension speed) are exploratory. |
| Single camera | Lateral release direction, trunk rotation and depth are invisible; lateral error exists only on the board. |
| Gravity-only scale (WARNING grade) | Metres are approximate (a few percent); verdict numbers carry "≈". |
| 60 fps | One frame = 16.7 ms; release timing and peak timing cannot be finer; release-timing sensitivity unavailable. |
| No hand/finger landmarks | No wrist-snap, grip or finger-release measures. |
| Final-rest detection | Correct on 3/5 in the spot check; scoring stays a human click. |
| Pilot library | 26 clips, 3 athletes, ~10 throws each, no outcomes recorded: no priorities can be claimed yet; the stress test suggests 20–40 throws per athlete for reliable outcome comparisons ([STRESS_TEST.md](STRESS_TEST.md)). |
| Multiple comparisons | Bonferroni control within analyses; the scored-vs-miss analysis is exploratory across variables. |
| 6 Hz filter | Supported by residual analysis on 12 signals, but may flatten wrist-speed peaks. |

---

## 5. References

Only sources listed in [REFERENCES.md](REFERENCES.md) and [RESEARCH_BACKGROUND.md](RESEARCH_BACKGROUND.md) are cited. Web sources were accessed 8 September 2026 unless stated.

**Course sources**

- Zelik, K. E. (2026). *Project 1: Biomechanics of Human Movement (Fall 2026)*. Vanderbilt University. Course handout, updated 21 August 2026.
- Zelik, K. E. (2026). *ME 3890/5890 & BME 3890/8901: Biomechanics of Human Movement, Fall 2026*. Vanderbilt University. Syllabus, updated 21 August 2026.

**Biomechanics, motor control and throwing**

- Challis, J. H. (1999). A procedure for the automatic determination of filter cutoff frequency for the processing of biomechanical data. *Journal of Applied Biomechanics, 15*(3), 303–317. https://doi.org/10.1123/jab.15.3.303
- Hore, J., & Watts, S. (2011). Skilled throwers use physics to time ball release to the nearest millisecond. *Journal of Neurophysiology, 106*, 2024–2033. https://doi.org/10.1152/jn.00059.2011
- Linthorne, N. P. (2001). Optimum release angle in the shot put. *Journal of Sports Sciences, 19*(5), 359–372. https://doi.org/10.1080/02640410152006135
- Müller, H., & Sternad, D. (2004). Decomposition of variability in the execution of goal-oriented tasks: Three components of skill improvement. *Journal of Experimental Psychology: Human Perception and Performance, 30*(1), 212–233. https://doi.org/10.1037/0096-1523.30.1.212
- Nasu, D., Matsuo, T., & Kadota, K. (2014). Two types of motor strategy for accurate dart throwing. *PLOS ONE, 9*(2), e88536. https://doi.org/10.1371/journal.pone.0088536
- Needham, L., Evans, M., Wade, L., Cosker, D., McGuigan, M. P., Bilzon, J. L., & Colyer, S. L. (2021). The accuracy of several pose estimation methods for 3D joint centre localisation. *Scientific Reports, 11*, 20673. https://doi.org/10.1038/s41598-021-00212-x
- Putnam, C. A. (1993). Sequential motions of body segments in striking and throwing skills of humans. *Journal of Biomechanics, 26*(Suppl. 1), 125–135. https://doi.org/10.1016/0021-9290(93)90084-R
- Sih, B. L., Hubbard, M., & Williams, K. R. (2001). Correcting out-of-plane errors in two-dimensional imaging using nonimage-related information. *Journal of Biomechanics, 34*(2), 257–260. https://doi.org/10.1016/S0021-9290(00)00185-8
- Stenum, J., Rossi, C., & Roemmich, R. T. (2021). Two-dimensional video-based analysis of human gait using pose estimation. *PLOS Computational Biology, 17*(4), e1008935. https://doi.org/10.1371/journal.pcbi.1008935
- Tran, B. N., Yano, S., & Kondo, T. (2019). Coordination of human movements resulting in motor strategies exploited by skilled players during a throwing task. *PLOS ONE, 14*(10), e0223837. https://doi.org/10.1371/journal.pone.0223837
- Venkadesan, M., & Mahadevan, L. (2017). Optimal strategies for throwing accurately. *Royal Society Open Science, 4*, 170136. https://doi.org/10.1098/rsos.170136
- Winter, D. A. (2009). *Biomechanics and Motor Control of Human Movement* (4th ed.). John Wiley & Sons.

**Pose estimation software**

- Jiang, T., Lu, P., Zhang, L., et al. (2023). RTMPose: Real-time multi-person pose estimation based on MMPose. *arXiv*. https://doi.org/10.48550/arXiv.2303.07399
- Pagnon, D., & Kim, H. (2024). Sports2D: Compute 2D human pose and angles from a video or a webcam. *Journal of Open Source Software, 9*(101), 6849. https://doi.org/10.21105/joss.06849
- Pagnon, D. (2026). *Sports2D v0.8.34* [software release]. https://github.com/davidpagnon/Sports2D/releases/tag/v0.8.34 (released 10 July 2026).
- Pagnon, D., Domalain, M., & Reveret, L. (2022). Pose2Sim: An open-source Python package for multiview markerless kinematics. *Journal of Open Source Software, 7*(79), 4362. https://doi.org/10.21105/joss.04362

**Cornhole rules and equipment**

- American Cornhole League. *Rules & Regulations* (page updated 24 October 2025; accessed 8 September 2026). https://www.iplaycornhole.com/about/acl-information/rules-regulations
- American Cornhole League. *Bags + Equipment: Board Info & Resources* (accessed 8 September 2026). https://www.iplaycornhole.com/about/acl-information/equipment-bags-boards

**Numerical implementation documentation** (implementation semantics only, not evidence for parameter choices)

- SciPy Developers. `scipy.signal.butter`; `scipy.signal.sosfiltfilt`; `scipy.stats.spearmanr`; `scipy.stats.bootstrap`. https://docs.scipy.org/doc/scipy/reference/ (accessed 8 September 2026).

**Methods named in the code but not in the curated bibliography.** The following are named in code comments or other docs and are *not* listed in REFERENCES.md; add a verified full citation there before citing them in the report: Romano et al. (2006) for the 0.474 "large" Cliff's-δ threshold (`performance.py`); Hopkins' smallest worthwhile change (`coaching.py`); Rauch, Tung & Striebel (1965) and Bar-Shalom, Li & Kirubarajan (2001) for the Kalman/RTS smoother (`bag_filter.py`); the ECC registration algorithm (`cv2.findTransformECC`, `auto_bag.py`); Huang et al. (2019), TrackNet (arXiv:1907.03698), cited in [AUTOMATIC_TRACKING.md](AUTOMATIC_TRACKING.md) as background for classical tracking.
