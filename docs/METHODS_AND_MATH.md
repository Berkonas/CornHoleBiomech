# Methods and Mathematics — Cornhole Biomechanics Lab

**Report companion for Vanderbilt ME/BME Biomechanics of Human Movement, Project 1 (cornhole for Vanderbilt Athletics). Written 27 September 2026.**

This document collects, in one place, the methods and every equation the system actually uses, so that sections can be copied into the course report. It is grounded in the code (`python/cornhole_biomech/`, `app/CornholeBiomechanics/Sources/CornholeBiomechanics/`) and in the existing method documents. Where an older document and the code disagree, the **code value is given here**. Longer derivations and design history are in [BIOMECHANICS_METHODS.md](BIOMECHANICS_METHODS.md) (§18 is the current scene/chain engine), [FULL_THROW_METHODS.md](FULL_THROW_METHODS.md), [METRICS.md](METRICS.md), [COACHING_SYSTEM.md](COACHING_SYSTEM.md) and the two design specs in [superpowers/specs/](superpowers/specs/).

**Versions this document describes**

| Item | Value | Where defined |
|---|---|---|
| Measurement method version | `METHOD_VERSION = "2026.10.05-release-touchdown"` | `cornhole_biomech/__init__.py` |
| Body-event detector | `filtered_shoulder_relative_wrist_heuristic_v4_peak_plus_delay` | `events.py` |
| Python package | 0.6.2 | `cornhole_biomech/__init__.py` |
| Pose software | Sports2D 0.8.34 (pinned), RTMPose via RTMLib/ONNX Runtime on CPU, model `body_with_feet` (HALPE-26 incl. heel/toe points), mode `balanced` | `sports2d_adapter.py`, `config.py` |
| Automatic bag tracker | `auto_motion_parabola_v18_hand_to_touchdown` | `auto_bag.py` |
| Bag silhouette centroid | `local_median_background_mask_v1` | `bag_segment.py` |
| Bag flight filter | `ca_kalman_rts_v1` | `bag_filter.py` |
| Board phase (touchdown, slide, end) | `board_phase_v3_deck_footprint_touchdown` | `board_phase.py` |
| Two-camera combination | `two_view_v5_knocked_confirm` | `two_view.py`, `front_view.py`, `front_track.py` |

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

0. **Working resolution** — the search (blob sizes, merge distances, segmentation windows, board detection) was built and validated on 1080p footage, so a taller clip (the 4K Player 1 session) is searched on frames resized to 1080 px high (INTER_AREA) and every pixel result is mapped back to source pixels (with $s = 1080/h$: positions, fit coefficients and accelerations × $1/s$, areas × $1/s^2$, camera transforms' translations × $1/s$, and the board homographies as $S\,H_{\text{plane}}$ and $H_{\text{deck}}\,S^{-1}$ with $S=\mathrm{diag}(1/s,1/s,1)$). At full 4K the bag's difference blob exceeded the 1080p-tuned size limits and fragmented (frame-to-frame centroid jitter 17 px median), so 0/10 Player 1 flights were accepted and 2/10 boards found; at the working resolution 8/10 flights and 10/10 boards, and the decoded frames need 1.7 GB instead of 7 GB (peak memory 3–4 GB instead of 12.4 GB). 1080p clips are searched unchanged.
1. **Candidates** — difference blobs (fragments within 16 px merged, area-weighted).
2. **Seeds** — blobs linked frame-to-frame with constant-velocity prediction; short windows fitted with a quadratic; RANSAC over triples as fallback. A seed must move toward the target, curve downward with image "gravity" inside the range implied by the athlete's projected shoulder–wrist length (taken as 0.45–0.90 m, ±25 %), and have small horizontal curvature.
3. **Growth and trimming** — backward extension stops while the bag is within 0.45 arm lengths of the wrist (still in hand); the end is trimmed where the path breaks from a local parabola of the preceding 15 frames (slide/bounce), or where the last point lies more than 2 × the trim limit (6 × the inlier tolerance, ≈ 36 px) off the whole-flight parabola — the same gross-deviation rule already used at the start. *Why (QA audit, 5 Oct 2026):* on Player 3 take 1 throw 4 the bag slid for six frames after touching down at frame 218; those slide points joined the 15-frame local window, so the local rule never broke, they sat 62–170 px off the arc, the flight was rejected at 32 px RMS, and a near-static object was tracked instead (release fell back to the wrist proxy, 4 frames early; touchdown and first contact came from the wrong object). With the rule the flight runs 150–219 and is accepted (4.4 px RMS). On the other 13 audited throws every flight still ends at the same frame.
   **Which flight stands for the throw.** The flight starting nearest the throwing wrist is used among the *accepted* flights; when none is accepted, only a candidate that travels at least 4 arm lengths toward the target (the travel gate of item 4) may stand in. A near-static object (0.1–0.2 arm lengths over 0.2–0.8 s on that throw) is never used: with no travelling candidate the result is "not found" (release then comes from the wrist proxy, §1.9) rather than a release, board background and touchdown taken from the wrong object.
   **Backfill to the hand.** Detection differences grey levels, so a red bag crossing a wall of similar brightness goes undetected for its first frames of flight. Walking back from the first mask-measured centre, each earlier frame is searched with the colour (LAB) segmentation at the position predicted from the nearest six mask-measured centres, and accepted by the gap-filling rule (within half a bag length of the prediction, typical bag size, outside the hand); the walk stops before the prediction reaches the hand (0.45 arm lengths), after two misses or **0.5 s**. Release is then the earliest free-flight centre. On the Player 1 session this recovered 7 frames on throw 3 (release 70 → 63, visually 62–63) and 2 on throw 10 (101 → 99, visually 99–100); throws whose detections already reached the hand are unchanged.
   *Projectile prediction (revision v18).* The prediction is a projectile: $y$ has the flight fit's own image gravity as fixed curvature and only position and velocity are fitted ($x$ straight). A free quadratic through six early, noisy centres extrapolated backwards bends with their noise: on Player 4 take 5 throw 3 it missed the bag by 21 px one frame back and 49 px three frames back, so the walk stopped at once; with gravity fixed the bag was found in every frame back to the hand (12 frames, release 180 = visual). A centre whose mask was not found (`source` "detection", the detector's contrast edge, 18 px off the bag centre there) is not used to predict; that frame is re-searched and, if the mask is found, re-measured. *Cap:* the detector missed 10–22 frames after release on the audited throws (Player 2 take 4 throw 2: release 168/169, first detection 190); the old 15-frame cap stopped 6 frames short of the hand, the flight was left starting 1.8 arm lengths from the wrist (needs review) and release fell back to the wrist proxy (163). 0.5 s (30 frames at 60 fps) covers the longest gap seen; the hand rule still ends the walk at release.
   **Forward growth to first contact** (`bag_segment.extend_to_contact`, `auto_bag._grow_to_contact`). *Defect it fixes (QA audit, 5 Oct 2026):* the detected flight stopped 0.30–0.37 s before touchdown while the bag was plainly visible — Player 1 throw 5A659FED ended at frame 215 (touchdown 233), Player 4 throw 681A89BF at 203 (touchdown 225, fit coverage 0.68). Cause: in front of the concrete pillar, posters and bystanders the red bag's grey-level difference is weak, so detections thin out, and `find_flights` split each throw into **two** candidate flights; the first one found claimed (removed) the late-flight detections, so the flight that starts at the hand — the one used — could no longer grow forward, and the motion-only extension gives up after 3 missed frames anyway. Colour search was only used backwards (to the hand), never forwards. Now, when the chosen flight ends in the air, each next frame is searched with the colour (LAB) segmentation at the position predicted by a quadratic through the last 8 centres, seeded also at every motion candidate of the clip within the gate (including those claimed by another candidate flight). A mask component is accepted only if **all** hold: (1) within 0.5 bag lengths of the prediction (the gap-filling rule), widened by half for each missed frame; (2) area 0.4–2.5 × the median of the last centres; (3) bag colour: its a*/b* chromaticity within 0.75 × the bag's chroma of the bag's own colour (median of the last 10 centres; at least 10 Lab units); (4) after a missed frame, not inside a person mask or pose-tracked bystander box, so the track never re-acquires on a person; and it must not touch the search window. Up to **6** consecutive frames may be missed (pillar, legs; the longest real gap seen was 2 frames, 3 when a bystander box covered the bag's path), the walk stops at 1 s or when the bag leaves the view, and the background median uses **earlier frames only** ($t-\{4,6,8,10,12\}$): near the landing the bag later rests where it touched down, and a symmetric median can merge it with the falling bag (synthetic landing test: mask area ×2.2, centre 6 px off; on the six real throws no measurable change). With a board the walk **stops at first contact**: at the first accepted centre the board model classifies as deck/front/floor (the same `surface_at` test as the contact classification below), or when the predicted centre has reached a surface and the bag is not seen in the air there. The grown flight then passes the existing physics gates: an end that breaks from the local parabola of the preceding 15 frames is trimmed (slide/bounce), and the whole flight must still be a plausible gravity arc toward the target with RMS residual within the acceptance limit (or no worse than before) — otherwise the growth is discarded and the detected flight kept (`forward_extension.status = rejected_by_physics_gate`). Added centres are labelled `extended_mask` (`centroid_sources`); the Kalman leave-one-out gate (item 6) is unchanged and still screens them. *Colour-gate evidence* (6 staged two-camera throws, 336 bag centres): the bag's a*/b* distance from its own previous 10 frames was p50 0.12, p95 0.48, p99 0.72, max 0.91 of its chroma (lighting changed L* by up to ~45 units on OpenCV's 8-bit scale but a*/b* little), while 30 other mask components 50–90 px away were ≥ 0.45 (median 0.80) — so colour is one of four gates, not a classifier on its own. *Result:* replaying the stored automatic flights through the new stage, both truncated throws now end at the board-phase touchdown frame (215 → 233, 203 → 225; 16 and 22 frames added, 2 frames bridged behind a bystander's legs); the added centres agree with the motion-detector mask centroids from an untruncated run of the same clip to median 0.1 px (max 0.8 px); the other four throws, already tracked to touchdown, are bit-identical. On Player 1 throw 5A659FED the truncated arc had pulled the gravity-calibrated field of view to 54.1° (release speed 7.28 m/s); the full arc gives 64.3° (8.30 m/s), in line with the same session's other throw (61.9°). The contact this produces is described under the local-path contact rule (§1.9).
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

**Body events** (`events.py`, `swing.py`, `timing.py`) come from the filtered shoulder-relative wrist $\mathbf w(t)$ (arm lengths; x toward the target, y up). The wrist is *moving* when $\lVert\dot{\mathbf w}\rVert \ge \max(0.05,\ 0.12\times\text{peak})$ arm lengths/s.

| Event | Rule |
|---|---|
| Peak backswing (top) | most rearward wrist ($\min w_x$) before release |
| Motion start | the **start of the throwing swing**: find the fastest rearward wrist movement ($\max(-\dot w_x)$) in the 1 s before the top, then take the last frame before it where the wrist is not moving. Falls back to the first sustained (≥ 0.05 s) moving frame if the wrist never goes quiet |
| Forward swing | first valid frame after the top |
| Peak follow-through | the arm's **highest point after release**: the first frame in $[t_\text{rel},\ \min(t_\text{end},\ t_\text{rel}+2\text{ s})]$ where $w_y$ is within 0.02 arm lengths of its maximum in that window |
| Motion end | last frame of sustained (≥ 0.05 s) moving |
| Peak elbow extension | max $d\theta_\text{elbow}/dt>0$ from the first frame after the top where $d\theta_\text{elbow}/dt \le 0$ (extension carried over from the backswing has ended) to release + 0.1 s; none if the elbow only flexes in the forward swing |

Backswing *start* (for tempo, `swing.py`) = the last frame before the fastest backward arm swing where arm angular speed < 15 % of that peak; it agreed with motion start within 0–2 frames on 5 of the 6 audited throws below (on the sixth it found no quiet frame, so tempo is unavailable there). All automatic events are candidates that a reviewer can correct; the raw candidate is preserved.

*Why (QA audit, 6 two-camera throws from Players 1, 2 and 4, side camera 59.94 fps, each event checked on the video frames):* the earlier rules were motion start = first sustained wrist motion in the clip, peak follow-through = most forward wrist after release, and elbow search from the top of the backswing. Motion start fired on walking in, aiming adjustments and practice swings in 5 of 6 throws (frames 1, 1, 10, 11, 37, while the swing started at frames 80–117); it now lands where the arm leaves the aiming position (115, 117, 80, 96, 108, 110). Because motion start→end bounds the movement interval, movement duration, normalized time τ and the interval mean/ROM summaries changed with it (`METHOD_VERSION` 2026.10.05-body-events). The most forward wrist occurs at φ ≈ 90°, 0–4 frames after release on all 6 throws, while the arm kept rising for a further 0.1–1.4 s; the new event is the highest point (173, 256, 219, 200, 183, 187 vs release 167, 170, 157, 166, 165, 165). Height is measured relative to the shoulder, not in the image: on one throw the image-highest wrist (frame 227) was the athlete standing up while holding the arm level, 53 frames after the arm itself peaked. The 0.02 arm-length tolerance (≈ 2 px) is the wobble of a held pose (0.024 arm lengths peak-to-peak over 1 s), so a held follow-through gives its arrival, not an arbitrary frame of the hold. On two throws the elbow straightened through the backswing and only flexed in the forward swing; the old search returned the decaying tail of the backswing extension (+8 and +7 °/s, 5 and 2 frames after the top) as the "peak". These throws now report peak elbow extension as unavailable; the other four kept the same frame and value. Release was unchanged on all 6.

**Release without an accepted flight (wrist-only proxy).** When no accepted bag flight supplies release, release = the frame of peak forward (target-axis) shoulder-relative wrist velocity **+ 0.09 s** (`RELEASE_AFTER_PEAK_WRIST_SPEED_S`), kept inside the motion. The bag rolls off the fingers after the hand has passed its peak forward speed (the hand decelerates as the arm rises). On the 13 audited throws with a frame-checked release (four players, 59.94 fps) the peak came 4–7 frames before release (median 5.5, mean 5.4 frames = 90 ms); without the delay the proxy was early on every throw (Player 2 take 4 throw 2: 163 vs 168/169; Player 3 take 1 throw 4: 144 vs 148). With it the residual was −2 to +1 frames (12 of 13 within ±1; the calibration is in-sample, so ±2 frames is the stated uncertainty). This candidate is never "confirmed": quality grading treats it as an unconfirmed automatic release (§1.14), and a manual release always wins.

**Release = first flight centroid beyond the hand.** Release is the first refined bag centroid in the accepted flight that lies more than **0.45 projected arm lengths** from the throwing-wrist landmark; earlier flight points are dropped as still in hand and the parabola is refitted. A visual audit of all 21 accepted pilot flights (release−8…release+3 contact sheets) found **21/21 within ±1 frame** of the visually judged release (19 exact; mean error +0.10 frame, SD 0.30 frame). The earlier rule (first flight-fit point) was 2–3 frames early on 5/21. A second, independent cue — where the fitted flight traced backward meets the wrist path — is kept as a cross-check (it runs 1–4 frames early by construction) and defines the release-window grade (§1.13).

**First contact (board-gated).** The end of the flight fit is only a candidate. It is mapped into the throw plane and classified as `deck` (inside the deck footprint expanded by half a bag width, within 6 cm of the deck surface), `front` (front face), `floor` (within 6 cm of floor height) or `air`. Only deck/front/floor are `measured`. **Near-contact rule:** a descending track that ends within 2 frames of its own predicted surface contact counts as measured, with the landing position taken where the fitted parabola meets the surface. Otherwise the contact is `lost_in_flight` and a **predicted contact** is found by extending the parabola (≤ 1.5 s), always `estimated` and excluded from measured-landing statistics. **Local-path contact rule** (forward growth, §1.6): when the forward walk ends because the bag's *local* path (quadratic through its last 8 centres) reaches the deck/front/floor in the very next frame and the bag is not seen in the air there, the last tracked frame of the descending track is the observed first contact, of the kind the local path hits, and the landing position is the tracked centre in that frame. The whole-flight parabola is not used here: it drifts from the end of a real flight (drag, perspective) and, sampled once per frame (~10 cm of fall per frame at landing), can step over the ±6 cm deck band — on Player 1 throw 5A659FED it reported the floor two frames later, while the video and the board phase show the deck at frame 233. A predicted next-frame point is not used as the landing position because it lies past the surface by up to a frame of motion (there ~18 in of across-deck error).

**Suggested outcome** (`contact.suggest_outcome`), always requiring a coach click: 3 if the post-contact track disappears within 4 in (3 in hole radius + 1 in slack) of the hole centre; 1 or 0 by whether the final-rest point lies on the 24 × 48 in deck; otherwise none with a reason. Final rest was correct on 3 of 5 detected rests in the spot check, so the result stays a one-click human entry.

**Board phase: touchdown, slide, rest or drop** (`board_phase.py`). The flight tracker deliberately stops where the path leaves the parabola, and the earlier rule took the first quiet 0.2 s after contact as the final rest. On the tripod clips that rule scored a bag that paused on the lip of the hole for 0.6 s and then dropped through (throw 22) as a board bag, and lost a bag that landed short and slid in (throw 18). The board phase follows the bag on the deck to the **end of the clip**:

1. Region: the deck quadrilateral (release-frame pixels) grown upward by 1.2 bag lengths, since a bag lying on the deck projects above the deck surface.
2. Empty-board background: per-pixel Lab median of up to 11 camera-aligned frames from 1 s before release until the bag nears the board (bags already lying still are part of it).
3. Each later frame is camera-aligned; the bag is the connected change region (threshold median + 6 MAD, ≥ 18) of 0.25–4× the in-flight bag area nearest the prediction (entering with the flight's last velocity; re-acquired after 2 missed frames).
4. Positions map to the deck with the deck homography: $v$ = inches up the deck from the front edge (hole centre 39 in), $u$ = inches across.
5. Events: **touchdown** = first sample that can lie on the deck (below); a bag seen over the board only in the air **never touched down** (board phase `not_found`, end `never_on_deck`; first contact then comes from the flight's own contact, and when that is a measured floor contact the suggested result is 0, "flew over the board without landing on it", medium confidence); **stop** = the along-deck position (3-sample median) stays within max(1 in, 3 × pixel precision) for 0.2 s; a bag that disappears for ≥ 0.12 s within 6.5 in (hole radius + half a bag) of the hole centre along the deck **fell in** (its visible area usually shrinks by ≥ 35 % as it tips in; a stop before the drop is reported as time "on the lip"); a bag still present at the end of the clip **rests** there; a bag lost at the edge of the deck **left** it — at the front or back edge (last seen within half a bag, 3 in, of it: below 3 in or beyond 45 in along; checked first because along is measured to about an inch and across only to ±3 in — Player 4 take 5 throw 3 was last seen 1.5 in up the deck and 2.7 in across and fell off the front, which the side rule had reported; the end carries `edge`: front/back/side) or, while still moving, with its centre within half a bag (3 in) of a side edge (≤ 3 in or ≥ 21 in across), where the bag already overhangs the edge. The side rule came from the tracking audit: Player 2 take 5 throw 4 was last seen sliding at 21.6 in across and was next visible on the floor, but was reported as "lost". Across-board position is only ±3 in from the side camera, so the rule needs the bag to be moving (no stop) when it vanishes; a bag that stopped and later disappeared stays "lost" (hidden or picked up).
   *Touchdown test (revision v3).* One side view cannot tell "high above the deck" from "on the deck but further across": both move the bag up in the picture. The bag's centre is mapped onto the plane 0.6 in above the deck (camera pose from the board corners); it can be on the deck only if that point lies on the deck, allowing the bag's overhang plus the across precision at the side edges (−6 to 30 in across) and the overhang at the front/back (−3 to 51 in along). An airborne bag can still map onto that footprint, so the sample must also have stopped falling: its image centre drops by at most **0.38 bag lengths** to the next sample. *Evidence (14 audited side throws, frame by frame):* touchdown samples mapped −4.0 to +15.7 in across; airborne samples 6.2–28 in beyond the far side edge, or past the back edge for the bag that sailed long (Player 3 take 2 throw 1: 3.9–11.6 in past it), except one frame before touchdown on 5 throws (−0.5 to −5.6 in across). Centre drop to the next sample: −0.03 to 0.33 bag lengths at the 13 frame-checked touchdowns (0.31–0.33 when a corner lands first), 0.42–0.64 for those airborne samples; the cut-off is midway, and with that small margin a touchdown can still be one frame off. The older rule (≤ 7 cm from the deck in the centre-line throw plane, else the first sample seen over the board) gave Player 3 take 2 throw 1 an airborne "touchdown" 30 in to the side of a board it never touched, gave Player 2 take 3 throw 3 one frame early (a bag landing at the far front corner reads 9–12 cm "high"), and was one frame late on Player 3 take 1 throw 4 (7.2 cm at the visible touchdown, frame 218).
   *Side-camera re-run of the 14 audited two-camera throws (5 Oct 2026, before → after revisions v18/v3, each changed value checked on the frames):* release 144 → 150 on Player 3 take 1 throw 4 (visual 148/149; the real flight is now accepted) and 174 → 180 on Player 4 take 5 throw 3 (visual 180; backfill now reaches the hand); replaying the Mac run's stored flights, Player 2 take 4 throw 2 goes 163 → 169 (visual 168/169) and the static object chosen on Player 3 take 1 throw 4 is rejected (wrist proxy 149). Touchdown 234 → 235 on Player 2 take 3 throw 3 (visual 235), 220 → 218 on Player 3 take 1 throw 4 (visual 218), 220 → 219 on Player 4 take 1 throw 1 (a corner touches at 219, flat at 220), and Player 3 take 2 throw 1 has none (it sailed over the back of the board onto the floor; previously an airborne "touchdown" at 211). The other 10 throws kept every release, contact, touchdown and end frame.
6. Suggested score: 3 fell in, 1 rests on the deck, 0 left the deck; always a one-click coach confirmation. When the flight tracker lost the bag in the air, a touchdown seen on the deck becomes the measured first contact.

**Slide kinematics.** On the plain deck before the hole, a least-squares constant-deceleration fit $s(t)=s_0+v_0t-\tfrac12 a t^2$ gives the entry speed along the deck $v_0$ and the deceleration $a$. For a bag sliding **up** the slope $\alpha$ (10.8°), $a = g(\sin\alpha + \mu\cos\alpha)$, so the effective kinetic friction is $\mu = (a/g - \sin\alpha)/\cos\alpha$ (withheld for slides < 4 in or < 5 samples, or a non-decelerating fit).

**Validation on the tripod clips (Player 1 throws 17–24, Players 3–4, checked frame by frame):** the end was classified correctly on 10/10 clips where the board was located (3 holes, including the 0.6 s hang; 7 board bags, including bags resting against the lip); the earlier rule got 5 of the same 7 Player 1 throws right. Slides were 10–23 in; plain-deck $\mu$ = 0.32–0.49, entry speed 1.9–2.5 m/s. **Lateral position:** from a side camera the deck's across direction runs nearly along the optical axis, and the along-deck position from the homography and from the centre-line throw plane differed by a median of ≈ 3 in; $u$ is reported as approximate and never used for the decision, and positions along the deck carry about ±3 in. Throws were made straight at the board; left/right needs the board camera.

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
| Peak elbow extension velocity and timing | max $d\theta_{\text{elbow}}/dt > 0$ in the same window, but starting where extension carried over from the backswing has ended (first $d\theta/dt\le 0$ after the top, §1.9); unavailable if the elbow only flexes in the forward swing | °/s, ms |
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

**Personal green zone** (`zones.personal_zone`, shown on the athlete summary, each throw report and the Launch Lab). The zone above uses one athlete's own inputs: the median measured **release height** (stature, knee bend and arm length show up here), the median measured **release-to-board distance** (§1.13), and the athlete's median measured **slide** on the board (board phase, §1.9; ≥ 3 measured slides, clipped to 0.10–0.70 m, otherwise the stated 0.45 m). The athlete's throw-to-throw spread of speed and angle ($\sigma_v$, $\sigma_\theta$, sample SDs) then gives, for every aim point $(v,\theta)$, the probability that a release scattered around it lands in the hole window:

$$P_{\text{green}}(v,\theta)=\iint \mathbb 1_{\text{green}}(v',\theta')\,\mathcal N(v'-v;\sigma_v)\,\mathcal N(\theta'-\theta;\sigma_\theta)\,dv'\,d\theta' ,$$

computed as a Gaussian blur of the green map on a 0.02 m/s × 0.5° grid (speed and angle treated as independent; their covariation is the compensation analysis of §2.4). The **best aim** is the arg-max within the athlete's own observed angle range ± 8°, so the suggestion stays a change they can make; the usual aim is their median release. This is the practical form of motor abundance (Bernstein; Müller & Sternad, 2004): there is no single right speed or angle, but a set of combinations that reach the hole, and a release placed where that set is widest relative to the athlete's own variability is the most forgiving. On Player 1's 11 scaled tripod throws (measured distance 5.48 m) the model gives $P_{\text{green}}$ = 40 % at the usual release; the observed hole rate was 42 % (5/12).

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

**Outcome first.** The verdict reads the recorded result and the board phase before any model: a **hole** gets no corrections ("In the hole: 3 points. It landed 15 in short of the hole and slid 15 in into the hole."), the release is offered as a reference throw, a slide of ≥ 4 in is named as part of the shot, and a disagreeing flight model or an unusual body value is shown only as a note. For a **board or miss** with a measured rest point, the first "work on" item is signed from where the bag really stopped (e.g. "ended 9 in short of the hole … about 0.12 m/s faster would have carried it there, if it slides the same way", using $\Delta v = -\Delta s\cos\alpha/(\partial x/\partial v)$), replacing the model-only speed advice.

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
| Single camera | Lateral release direction, trunk rotation and depth are invisible from the side; two-camera takes (§5) measure left/right, heading and frontal-plane body from a front camera. |
| Gravity-only scale (WARNING grade) | Metres are approximate (a few percent); verdict numbers carry "≈". |
| 60 fps | One frame = 16.7 ms; release timing and peak timing cannot be finer; release-timing sensitivity unavailable. |
| No hand/finger landmarks | No wrist-snap, grip or finger-release measures. |
| Final-rest detection | Board phase correct on 10/10 tripod clips with a located board; still a one-click confirmation, and a clip that ends < 0.5 s after the bag stops is flagged (a late drop cannot be ruled out). |
| Throwing distance | The pilot sessions were thrown from about 5.1–5.8 m (release to board front), not the 27 ft regulation pitch (≈ 7.7 m from release); every zone and verdict uses the measured distance, so results do not transfer directly to regulation distance. |
| Lateral (left/right) | Not measured from the side camera alone; measured on two-camera takes from the front camera (§5.2, ±0.5 in across the deck). |
| Pilot library | 26 clips, 3 athletes, ~10 throws each, no outcomes recorded: no priorities can be claimed yet; the stress test suggests 20–40 throws per athlete for reliable outcome comparisons ([STRESS_TEST.md](STRESS_TEST.md)). |
| Multiple comparisons | Bonferroni control within analyses; the scored-vs-miss analysis is exploratory across variables. |
| 6 Hz filter | Supported by residual analysis on 12 signals, but may flatten wrist-speed peaks. |

---

## 5. Two-Camera Takes (Final Data Collection protocol)

The final data collection (Fall 2026) uses **two phones per take**: the original side camera, and a
**front camera** on a tripod behind the board looking back along the throw line at the athlete. A *take*
is one continuous recording per camera: the athlete claps, shows the take number with their fingers,
then throws four bags. Each athlete has 5–7 takes. The side camera keeps every method in §1–§3; the
front camera adds what one side camera cannot see: **left/right**, where the bag stopped across the
board, whether it went in, and frontal-plane body measures. Code: `takes.py` (§5.1), `front_view.py`
and `front_track.py` (§5.2), `two_view.py` (§5.3).

| Camera | Device (this collection) | Video | Sees |
|---|---|---|---|
| Side | iPhone 15 Pro Max | 1920×1080, 59.94 fps (variable frame rate) | body chain, release speed/angle/height, flight, distance along the board |
| Front | iPhone 17 Pro | 1280×720, 30 fps | deck in board inches, sideways landing and rest, hole/board/off, frontal pose, stance |

### 5.1 Takes, synchronisation and throws

**Pairing.** File names are matched case-insensitively on `take <n> <front|side>` with any separator
(`Take_2_side.mov` = `take_2_Side.MOV`). A take with only one camera is reported, never guessed.

**Camera roles.** Each file's *camera signature* — QuickTime device model (read from `moov/meta`; only
model and creation date are kept, never location), frame size and nominal frame rate — is compared
across the athlete's folder. The signature most `Front`-named files share is the front camera, the one
most `Side`-named files share is the side camera (majority vote). A pair whose two signatures are
exactly reversed is reported as **swapped labels** and used in its true roles; the files are never
renamed (Player 1, take 3: the file named *Front* was recorded by the side phone). When both phones
share a signature the names are trusted and that is stated.

**Synchronisation from sound.** Both phones record audio; the clap and every bag impact are sharp
transients heard by both. For each soundtrack (16 kHz mono):

$$e(t) = 20\log_{10}\Big(\mathrm{RMS}_{5\,\text{ms}}\big[\mathrm{HP}_{300\,\text{Hz}}(s)\big](t)\Big),\qquad
\tilde e(t) = e(t) - \mathrm{median}_{1\,\text{s}}\,e(t)$$

The high-pass removes hall rumble and the low end of voices; the 1 s running median removes slow
loudness changes so only transients remain. The offset is the lag $\tau$ that maximises the normalised
cross-correlation $r(\tau)$ of $\tilde e_\text{side}$ and $\tilde e_\text{front}$ over $|\tau| \le 12$ s
with ≥ 8 s of overlap; convention $t_\text{front} = t_\text{side} + \tau$.
The offset is **accepted** when $r \ge 0.35$ and the peak beats every lag outside ±100 ms by a margin
≥ 0.08. *Justification (pilot evidence):* on all 23 Final Data Collection pairs, $r$ = 0.44–0.74 and the
margin 0.10–0.35; both gates sit below every real pair. **Uncertainty ±17.5 ms**: sound travels
≈ 2.9 ms per metre and the two microphones are at different distances from the clap and the board
(±15 ms), plus half an envelope hop (2.5 ms). That is about half a front-camera frame (33 ms), so the
front frame matched to a side frame is the right one or its neighbour. Each throw also gets a **direct
check**: the side camera's first-contact frame against the first front frame with the bag on the deck
(`sync_check`; agreement within ±4 front frames = the 2-frame sync tolerance plus 2 frames because the
front camera sees the bag reach the deck late at its grazing angle).
**Front picture lag.** Aligned soundtracks are not quite aligned pictures: what each phone shows at a
timestamp also depends on exposure, rolling-shutter readout (the deck sits low in the front picture and is read
out late) and audio-path latency. The tracking audit found the front camera showing first contact and release
one front frame *after* the sound-mapped frame on all six audited throws (always the same direction, so a bias,
not noise). The lag is therefore measured per front camera set-up (device, frame size, date) over every throw
where both views saw first contact, $\ell_i = (f^\text{front}_\text{first on deck} - f^\text{front}_\text{mapped side contact})/\text{fps}_\text{front} + \ell_\text{applied}$,
minus the expected quantisation $\tfrac{1}{2}(1/\text{fps}_\text{front} - 1/\text{fps}_\text{side})$ (both "first frame on
the deck" values come half a frame after the true contact on average, while the mapping rounds to the nearest
frame). The set-up's **interquartile mean** (≥ 8 throws; robust like a median but not stuck on whole frames) is
added to the mapping, $t_\text{front} = t_\text{side} + \tau + \ell$ (`two_view.pool_front_lag`, stored as
`front_lag_s` in each take record; new or re-prepared takes of a measured set-up inherit it). One throw's value
is ±1–2 front frames (30 fps, a bag reaching the deck within a frame), so only the pooled value is used. A pooled
lag beyond ±100 ms (3 front frames) or with an interquartile spread above 70 ms (about 2 frames) is not a picture
lag but a sync or tracking fault: it is rejected and the mapping stays as the sound gives it. Only results from
the current front tracker (`two_view_v2` or later) are pooled. `two_view_v4_landing_guards` keeps the same tracker
(it only leaves the hole interior out of the deck track and bags out of the deck alignment, §5.2): on the 92-throw
library the pooled lag moved from 21.3 to 21.2 ms (79 throws with both contacts), so its results are pooled too. `analyze_library.py` pools it after the front-camera pass and re-runs the front camera once for throws
analysed with a different lag.
If sync fails, the two views are analysed separately and combined only by throw order (stated in the report).

**Finding throws (side video).** The side video is streamed once at 480 px width. A three-frame
difference ($\min(|I_t - I_{t-1}|, |I_{t+1}-I_t|) > 14$ grey levels) gives small moving blobs
(4–400 px²); blobs are linked frame to frame (gate 7 px, ≤ 3 missed frames) into tracklets; a
tracklet of ≥ 8 points moving towards the board at 1.5–20 px per frame is bag-like; tracklets that chain
within 0.25 s form one flight, which must cross ≥ 35 % of the frame width (a bag carried in the hand or a
person walking does not). Flights closer than 2 s are one throw. Bag impacts in the front soundtrack
(the front phone stands by the board) confirm each flight within ±0.45 s. When a take has more flights
than throws and enough of them were heard landing, the unheard ones are left out, latest first, with a note
(Player 1 takes 4 and 6: the fifth "flight" was the side phone being picked up at the end of the take).
Two more guards came from the same check. A "flight" during which the picture itself moves is the camera,
not a bag: it is dropped when the median number of moving blobs per frame over it is at least 15 and at
least 4× the take's typical frame (real flights 4–9, the take's typical frame 3, a bumped side phone 23 —
Player 4 take 3 at 21 s). And a flight already heard landing is never merged with the next one, however
close, so one stray movement cannot chain two throws together. Thresholds were set on
Player 1 and Player 4 takes: all 4 throws were found on every checked take, with no false flights from
people walking through the side view.

**Clips.** Each throw becomes a side clip from 2.5 s before the flight starts (the whole swing from the
stance) to 1.6 s after it ends (slide and rest), and a front clip covering the same synchronised time.
Clips are written in one decode pass per camera (H.264, CRF 12, near-lossless). Every clip frame's
source timestamp is stored, so side frame → front frame mapping uses real times, not nominal rates
(the side phone records at a variable frame rate). The originals are never changed.

**Side board with bags on the deck.** Later throws in a take have earlier bags on the deck, which can
hide the board edges the side detector needs. The empty-board corners are found once at the take start
and carried to each clip's first frame by ECC alignment (`board_corners.json`, source `take_reference`).
When neither the take start nor the throw's own clip gives a deck (people beside the board; Player 1 takes 1 and 3: detector
confidence 0.42 against the 0.75 gate, while the same deck was found at 0.88–0.89 on other clips of the
take), the deck **another throw of the athlete found** is used: same take first, then the other takes,
highest detector confidence; it is carried from that throw's background plate into this clip's first frame
by ECC on the board area and kept only if the alignment converges with correlation ≥ 0.6 (source
`sibling_throw`). Only decks the detector itself found are shared, never shared or clicked ones, and
clicked corners are never replaced. The side phone is on a tripod for the whole session, so one deck
seen well is a better reference than a weak detection on a cluttered clip.

**Side field-of-view search range.** The gravity calibration (§3.8) now searches 45–85° for the root
(`SEARCH_HFOV_RANGE_DEG`) while the reported scale band stays 55–75°. *Reason:* the Final Data
Collection side phone solved at exactly 55.0°, the old search edge, so every throw was flagged even
though gravity matched within 0.003 m/s². A root at a search edge is a bound, not a measurement;
widening the search lets the fit find its own root, and the reported uncertainty keeps the wider band.

**Side field of view pooled per camera set-up.** One throw's ~0.4 s flight calibrates the field of view
noisily (per-throw values 51–65° on the spot check). For two-camera takes the per-throw values are pooled
(median, §3.8) over every throw recorded by the same side phone (device model and frame size), on the
same date, with the deck at the same place in the picture (centre within 25 px, so the tripod did not
move) — across athletes, because the lens does not depend on who throws. Pooling per athlete instead gave
61.1° for Player 1 (8 throws) and 52.6° for Player 4 (4 throws) although their decks were 11 px apart in
the same picture: an 8° disagreement the camera cannot have. The library run analyses each athlete, then
re-pools over the whole set-up and refreshes every throw.

### 5.2 Front camera

**Board frame.** x 0–24 in left→right *as the thrower sees it*, y 0–48 in from the front edge, hole centre
(12, 39), radius 3 in. The front camera faces the thrower, so its image is mirrored: the thrower's
front-left corner (0, 0) is the far-right deck corner in the image. All signed lateral values are in the
thrower's frame (− left, + right).

**Finding the deck** (on a median plate of the take's first 1.5 s, so people and moving bags vanish).
1. The black end apron nearest the camera is the widest dark (V ≤ 75), wide (≥ 6 % of the image width,
   aspect ≥ 2.5) component in the lower two thirds; up to four candidates are tried (furniture can be dark too).
2. The deck's red paint above it (hue ≤ 12 or ≥ 150, S ≥ 25, V ≥ 60; this hall gives S 30–60) gives the two
   side edges by RANSAC line fits (RMS ≤ 3 px).
3. The far (front) edge is chosen among gradient-scored candidate rows by the **hole test**: the deck
   homography from each candidate must put the dark hole within 4 in of (12, 39); the best fit wins.

On all 10 checked takes (Players 1 and 4) the deck was found with the hole 0.04–0.43 in from its nominal
place. A coach can set the four corners by hand (`set-front-corners`), which always wins.

**Deck homography.** $\mathbf H$ maps image pixels to deck inches from the four corners. Its local
resolution is reported: at mid-deck one pixel is ≈ 0.3–0.5 in across, so the lateral precision label is ±0.5 in.

**Camera drift.** The front phone sinks slowly on its tripod (≈ 40 px over a 30 s take, with exposure
changes). Every 5th frame of a clip is aligned to the take's reference frame by ECC (affine,
brightness-invariant) on a window around the deck, apron and legs, seeded by phase correlation; corners
in between are interpolated. Alignment correlation was 0.97–0.997; frames below 0.6 keep the last good warp.
*Bags are left out of the alignment* (`bag_red_mask`: bag-red pixels, hue ≤ 12 or ≥ 150, S ≥ 60, V ≥ 35, grown by
9 px — about a third of a near bag — for blur and shadow; the deck paint at S 25–60 stays in). A bag in the frame
that the reference does not have, or the reverse, pulls an image fit towards itself: Player 2 take 4 throw 2 had its
far corners rise 27 px when the bag landed by the far edge, with the camera still, and the throw's rest moved 17 in
sideways ("9 in left" instead of 8 in right, which the side camera confirmed); two later throws of that take were
pulled 24–27 px by the bags already on the deck. Each key frame is solved with this frame's bag pixels masked, then
again with the reference's bag pixels carried into the frame added. With less texture an ECC fit can settle on a
stretched warp, so a solve whose affine part departs from the identity by more than 2 % (`ALIGN_MAX_LINEAR`; a real
drift showed ≤ 0.3 %, 1 px across the deck) is repeated from a fresh phase-correlation start and the more rigid,
better-correlated fit kept. *Shape guard:* the phone drifts as a whole, so the deck keeps its shape in the picture;
a key frame whose corners (translation removed) depart from the clip's median deck shape by more than 3 px
(`ALIGN_SHAPE_TOLERANCE_PX`; all 92 library throws ≤ 1.24 px once bags are masked, while on the three pulled
throws the far and near edges had moved 24–29 px apart before) is dropped and interpolated from its neighbours (`max_shape_change_px` and
`shape_rejected_frames` are reported in `alignment`).

**Camera model.** With the field of view fixed, a pose from four deck points has 6 unknowns and 8
equations, so a wrong field of view leaves a PnP reprojection residual. Scanning 40–95° gives a sharp
V-shaped minimum (residual < 0.3 px, ≈ 0.28 px per degree either side): 60.7–65.8° on this collection,
±2.5°. The **median over every take the same front phone recorded that day** is used (the field of view
belongs to the lens, not the tripod position, so all athletes' takes count; one take is an outlier now and
then — Player 1 take 3 gave 76.6° against 65.7° for take 1); otherwise the take's own value;
otherwise the nominal 68° (`estimated`). IPPE `solvePnP` then gives the camera position (≈ 4.0 m from
the board front, 1.27 m high, on the centre line). Rays through image points are intersected with the
floor (stance) or with the vertical plane at the side camera's measured release distance (release hand).
Cross-check: the release height implied by the front ray is compared with the side camera's release height.
**Corner check.** True corners leave ≤ 1.3 px of PnP residual at the pooled field of view on this collection.
When the residual exceeds 2.5 px, or the take's deck-shape field of view is more than 8° from the pooled one
(about 3× its ±2.5° noise), the corners are treated as misplaced (Player 1 take 5: 6.5 px, 90.9° against
66.1°, one corner 26 px inside the deck). The camera is then `estimated`, and stance, release-hand offset
and aim are withheld with a note asking for clicked corners (each withheld measure gives that as its reason, not
"ankles not seen"); positions on the deck are kept but marked
`estimated`, and hole / board / off is shown but not recorded automatically (it comes from the same corners).

**Where the bag ended.** *Before* = median of 12 frames ending 0.25 s before release (bag in the hand),
warped onto the last frame's board position; *after* = median of the clip's last 0.3 s. Changed pixels
(CIELAB ΔE > 18) form blobs; a blob is a bag when its area is 0.25–15× the expected image area of a
6 × 6 in bag **at that place**: on the deck from the deck homography at the blob's centre, on the floor by projecting a
6 × 6 in floor square at the blob's lowest point with the camera pose (never below the deck-centre value). Earlier
the limit was 15× the deck-centre bag everywhere, and a bag that slid off the back end and lay near the camera
(Player 1 take 5 throw 4: 3069 px² against 176 px² at the deck centre, limit 2635) was never seen. Each blob is tested against the **empty board** from the take start: a bag
*appeared* there when the after image differs from the empty board more than the before image does;
otherwise the blob is a bag that was knocked away. Then:
- centre on the deck (within 0.75 in sideways, −3 to 54 in along; at this grazing view a bag's own
  thickness pushes its pixels past the back edge) → **board**, rest x from the homography — but only for a whole
  bag: at least one bag top face at that place (`MIN_ON_DECK_AREA_FRACTION` = 1.0) and differing from the empty
  board by a mean ΔE ≥ 18 (the changed-pixel threshold). On the red deck the colour test says little. Library
  evidence (92 throws): every whole bag that came to rest on the deck (38 changes, thrown or knocked) was 1.3–11× its top
  face (top plus visible side) and at least 22 ΔE from the empty board; the 13 smaller changes were specks, shadows
  and nudged bags' edges at 0.24–0.76× — Player 1
  take 5 throw 4's "board" rest was a 95 px² speck (0.3×) while the bag lay on the floor. Smaller changes are
  counted (`small_on_deck`) but are not a bag;
- on the floor under the deck (where a bag through the hole lies) and at least 0.6× the deck-centre bag
  area → **hole**. The region is the floor rectangle under the deck, ±12 in across, from 0.45 m behind the
  front edge to 3 cm short of the back edge, projected with the camera pose (the hole's centre is 23 cm
  short of the back edge). A bag that slides off the back end lands beyond the back edge, nearer the
  camera; an earlier region drawn as a fixed proportion of the image reached past the back legs and took
  two such Player 4 bags for bags in the hole, while the side camera saw them leave the deck (a bag there is nearer the camera than the deck centre, so it is
  never smaller; Player 1 take 3: the bag was 996 px² against an expected 227, shadow specks ≈ 70);
- on the floor near the board → **off**, its floor position from the camera ray. The search covers the
  floor band from 2.5 deck image heights above the deck's far edge down to the frame's bottom edge (bags
  that slide off the back end come towards the camera — Player 4 take 5 throw 1 stopped at the frame edge),
  but a blob counts only when it is whole-bag sized (≥ 0.6×), bag-coloured (≥ 40 % of its pixels red as
  the bags of this collection: deck-paint hue, saturation ≥ 60; real bags measured S 88–166, floor glare
  and reflections S 13–86 and yellow hue) and its floor point lies within ±2 m of the centre line, from
  2.5 m short of the board to the camera. The colour test also applies under the board. It removed four
  false "off the board" rests on Player 2 (glare on the shiny floor) and kept every real one checked. Without that gate a shiny floor's reflections and
  people far to the side were taken for bags (Player 1 take 3: four such blobs on one throw, none after);
- no new bag, but the tracked bag reached the hole → **hole**, only when the deck track starts at first contact
  (within `PATH_START_MAX_FRAMES` = 3 front frames after the mapped side contact, the sync check's 2-frame tolerance
  plus the front camera's 1-frame lag), has its first-contact point, and moves from the open deck into the hole.
  Player 3 take 2 throw 1 sailed off the back of the board and out of view, yet its "track" began 36 frames after
  contact on the flickering hole interior and said hole. A track that does not start at contact is not used to pick
  between candidates either (the largest change is taken);
- **bag followed off the deck**: when the deck track starts at contact and its last 3 points
  (`PATH_OFF_DECK_POINTS`) lie more than a bag width (6 in) outside the deck, and a new floor bag lies nearer the
  track's end than any change on the deck or under the board, the floor bag is the thrown one → **off**; the other
  changes were bags it moved. Library evidence: 10 throws (Player 1 take 4 throw 2, take 5 throw 4; Player 2 take 2
  throw 3, take 3 throw 4; Player 3 take 1 throw 2, take 2 throw 3, take 4 throw 2; Player 4 take 4 throw 1, take 6
  throw 4, and Player 3 take 1 throw 3 newly placed) were checked frame by frame: in each the bag slid or tumbled off
  the deck to the floor where the track ended, while a nudged bag or a speck on the deck (or a knocked bag in the
  hole) had been taken for the rest. A bag dropping through the hole also leaves the deck plane in the track, but it
  ends at the bag under the board, which is then nearer;
- no new bag anywhere (`deck_clear`): the whole deck is visible, so the bag is not on the board and not in the
  hole → **off**. It is *suggested* only when the side camera also saw the bag leave the deck or never land on
  it; otherwise it needs confirmation (Player 4 take 5 throw 3 dropped off the front edge, hidden by the deck).

If one throw changes both the deck and the under-board region (it knocked a bag in), the front camera
cannot tell which bag was thrown. The side camera, which follows the thrown bag from release to rest,
decides: a side ending "rest" → the bag on the deck, "fell_in_hole" → the hole. Player 1 had five such
throws, the thrown bag stopping at the hole's lip while it pushed the bag already there into the hole.
Without a side ending the throw stays `ambiguous` (needs confirmation, nothing recorded automatically).
When the side ending chose, the two views are not independent on that throw: the agreement is reported as
unknown, the suggestion's confidence as medium, and the result **always needs the coach's confirmation**. From
the side the thrown and the knocked bag overlap: over the 92-throw library the side ending picked the right bag
on 5 of 7 such throws; the other two (Player 1) slid into the hole while nudging an old bag and were read as
"rest".

**Bag path in the front camera** (`front_track.py`; the replay overlay `front_path` and the deck track
below). *Candidates* in each frame (searched at half resolution) are pixels that are bag-red (hue ≤ 12 or
≥ 150, S ≥ 60, V ≥ 35), differ from the empty scene by > 30 (8-bit, largest channel; the scene is the
median of every 3rd frame from 2.5 s to 0.2 s before release, shifted for camera drift by the deck
corners) and differ from the same frame 2 frames before *and* after by > 20. Evidence (727 bag
detections on 21 throws, two libraries, 2nd–98th percentile): bag hue 165–180 and 0–8, S 63–145, difference
from the empty scene 50–173; the still scene differs by a median of 2–4 and only 1 % of its pixels change by
more than 8 over two frames; the deck paint is S 25–60 and the wooden wall slats hue 15–28, so neither
passes. *The bag* is the set of candidates that one drag-free projectile explains: seen through a fixed
pinhole camera, its image position is $u = (a_0 + a_1 t + a_2 t^2)/D$, $v = (c_0 + c_1 t + c_2 t^2)/D$
with the shared depth $D = 1 + d_1 t + d_2 t^2$ ($a_2$, $d_2$ come only from camera pitch). RANSAC (1500
draws of three candidates ≥ 3 frames apart, level-camera model solved exactly, scored over *all* frames)
picks the model, then a robust least-squares fit of the full model refines it. A model is accepted only if
the bag comes towards the camera the whole way, its depth shrinks 1.3–8× (measured 2.2–3.3), its gravity
term puts the release 3–30 m from the camera ($Z_0 = f g / (2 c_2)$; measured 7.4–9.4 m — a person
walking or a rolled bag has no gravity term) and, at the side camera's contact frame, it is within 1.5
deck widths of the deck (else retried without this, for bags that end well off the board). A frame keeps
its candidate only if it lies within 4 px + 0.75 × its size of the model (residuals: median 0.6 px, 98th
percentile 2.9 px, i.e. a third of the tolerance) and its area is within 6× of the size the depth predicts
(a tumbling bag changes 2.5× between frames); a path seen in fewer than 6 frames or 30 % of the flight is
dropped. Frames without a consistent candidate stay empty. The path runs from release to one frame after
the side camera's contact (the front camera sees the bag reach the deck 0–2 frames, median 1, after it on
11 throws). Before this, nearest-blob linking of frame differences followed a bystander or the thrower's
body on 6 of 13 Final Data Collection throws and stayed half on the body on 2 more; now all 13 (and 8 of an
earlier test library) follow the bag from the hand to the deck, 1.1–1.8 s per throw. Only red bags are
found; the path is for display and no number is computed from it.

**First contact across the board.** The moving bag near the deck is tracked from just before the side
camera's contact time with the same colour and motion test (blobs with ≥ 15 % moving pixels; a bag at rest
ends the track), linked by the best chain through all frames (+1 per frame, minus (step ÷ 90 px)², minus
0.5 per skipped frame, at most 3 skipped; the last flight steps before contact are 32–73 px). Each point is
the bag in that very frame: the earlier frame-pair differencing put it one frame early or late (44–71 px
off on all 13 throws). A blob lying ≥ 80 % inside the hole's outline (`DECK_HOLE_INTERIOR_SHARE`) is left out: the
hole's dark-red interior flickers and passes the motion test with nothing moving (Player 3 take 2 throw 1, 12
frames; a bag going in is seen above the rim before it drops, then under the board). The point nearest the
synchronised contact frame, among points
within 6 in (one bag width) of the deck, gives $x_\text{contact}$ (earlier points are the bag still in the
air, whose deck-plane mapping runs far off). The heading uses first contact; the resting place stands in
only for a bag that stayed on the board, never for one that slid or bounced off. Without a side contact, the first three consecutive tracked points on the deck mark it
(source stated).

**Heading (left/right aim).** From the release hand to first contact, in the floor plane:

$$\psi = \operatorname{atan2}\big(X_\text{contact} - X_\text{release},\; D_\text{release} + y_\text{contact}\cos\theta\big)$$

$X$ = sideways from the centre line (m), $D_\text{release}$ = side-camera release-to-board-front distance
(the athlete's median if missing on a throw), $\theta$ = board slope; + = to the thrower's right. The
sideways miss the heading alone would give at the hole is reported too, so *aim* and *standing
off-centre* can be separated. Noise ≈ 0.5° (±0.5 in contact precision and ±3 cm hand position over ~6 m).

**Frontal-plane body** (Sports2D on the front clip; joints with confidence ≥ 0.3; ±1-frame mean at release).
The front camera looks down the throw line, so its image plane is the athlete's frontal plane. Image
angles are corrected for camera roll, measured from the board's level back edge.

| Measure | Definition | Noise used |
|---|---|---|
| Trunk side lean | hip centre → shoulder centre vs vertical; + towards the throwing arm | 6° |
| Shoulder tilt | shoulder line vs horizontal; + throwing shoulder lower | shown only |
| Hand across body | (wrist − throwing shoulder) sideways ÷ shoulder width at release; + towards the midline | 0.15 shoulder widths |
| Follow-through | the same, 0.15 s after release | shown only |
| Release offset | release hand's sideways distance from the centre line (ray ∩ release plane) | 0.03 m |
| Stance offset / width | ankle rays ∩ floor (7 cm ankle height), 1 s before release | shown only |

### 5.3 Combined result: where it ended and why

**Fusion.** Across (x) comes from the front camera; along (y) comes from the side camera's board phase
(§1.13) when it has one, because the side view sees distance along the deck without the front camera's
grazing foreshortening; otherwise the front homography's y. The result (hole 3 / board 1 / off 0) comes
from the front camera; the side camera's board phase is a cross-check, and any disagreement is shown as
*needs confirmation*.

**Guards on hole / board** (`decide_result`). The front camera's hole or board is withheld (no category, *needs
confirmation*, with the reason and the front camera's reading kept as `front_category`) when
- the side camera measured first contact on the **floor** and its board phase saw no touchdown on the deck
  (`side_hit_floor_first`; a bag that hits the floor first is also a foul). The contact kind alone is not used: on six
  library throws that stayed on the board or went in the side contact said floor while the board phase saw the bag
  land on the deck; only Player 2 take 1 throw 3 and Player 3 take 1 throw 1 and take 2 throw 1 had neither, and
  all three missed the board. Such a throw also gets no first contact on the deck (a deck point the front camera
  tracked was the bag passing over the board in the air);
- the front deck corners are **suspect** (§5.2) and the side camera saw the bag leave the board (the same corners
  place the bag);
- the hole came only from the tracked path and the **sync check failed** (the two cameras disagree on when the bag
  landed, so the path is not this bag's).

These are safety nets: on the 92-throw library none fires once the §5.2 landing rules are in (Player 3 take 2
throw 1, which they were written for, is already off the board with the deck clear).

**Signed miss** at rest from the hole centre, thrower's frame: $\Delta x = x_\text{rest} - 12$ (right +),
$\Delta y = y_\text{rest} - 39$ (long +), distance $\sqrt{\Delta x^2+\Delta y^2}$.

**Automatic result.** A confident front-camera result (views agree or the side camera has no ending, no
knocked bag, corners not suspect) is recorded as the throw's outcome with the note
*"Recorded automatically…"*; it never replaces a result someone entered. When a re-analysis is no longer
confident, an earlier automatic result is removed, so the throw shows as needing a result.

**The coach sentence** (outcome first; associations, never "because"):
- in the hole → no correction;
- within 3 in both ways (the hole radius) → "close";
- otherwise `N in short/long` with the release speed, and `N in left/right` with the aim when
  $|\psi| \ge 0.3°$. The hand across the body (≥ 0.25 shoulder widths, ≈ 2× its noise) or a stance
  ≥ 15 cm off the centre line is named **only when it points the same way as the miss** (across the body
  sends the bag toward the non-throwing side). Trunk side lean is a steady personal trait for most
  athletes (≈ 10° on every Player 1 throw), so it is compared across throws on the athlete summary, not
  named per throw.

**Athlete level.** `front_heading_deg`, `front_arm_across_body_sw`, `front_trunk_side_lean_deg` and
`front_release_offset_m` join the scored-vs-miss and relationship analyses (§2.4) with the noise floors
above, under the same evidence gate (≥ 5 throws per group, Cliff's δ ≥ 0.474, difference > noise).

**Limits.** The front camera sees the deck at a grazing angle, so along-board distance from it alone is
coarse (that is why y comes from the side). A bag that lands far off the board, outside the front view, is
`unavailable`, not "off". Frontal body angles are 2D image angles. Sound sync assumes both microphones
heard the same events; it is checked per throw but not against an external clock.

---

## 6. References

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
