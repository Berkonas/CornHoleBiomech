# Measurement Engine Redesign — Design Spec

Date: 2026-09-23 · Branch: `codex/second-pass-lab` · Part 1 of 2 (Part 2: coach metrics + UI redesign, separate spec)

## 1. Intent

**Goal.** Make the analysis of the existing Sep 17 pilot clips trustworthy and scientifically richer, so that the
app can link the athlete's body motion → release mechanics → bag trajectory → outcome, and give individualized,
evidence-backed feedback to a coach.

**What the user asked for**
- Isolate the athlete and the board from the busy atrium background so tracking/measurement are not disturbed.
- Use regulation cornhole constants (bag size/weight, board size/angle, pitch distance) in the calculations.
- Fix bag tracking that reports "first contact" in mid-air; use computer vision to find the board and the landing.
- Add meaningful biomechanics/physics outputs (release velocity/angle, wrist velocity/acceleration, shoulder/elbow
  angular velocity, coordination/timing, momentum, KE, PE, power where defensible, force as a 2D vector) and — most
  importantly — test how they relate to outcome, landing location and within-athlete consistency.
- Keep calculations transparent with assumptions and uncertainty; do not report what a single 2D camera cannot support.
- Ground the logic in published upper-body/throwing biomechanics.

**Constraints (decided)**
- Footage: **existing clips only** (hand-held, side view, 1080p ~60 fps, athlete ~300 px tall, board at frame right,
  red bags on a red deck, reflective floor, bystanders). No re-recording.
- Deployment: **coach on a Mac** — SwiftUI app + Python engine, packaged `.app`.
- Approach: **scene model** (Apple Vision + OpenCV), no large model downloads (~14 GB disk free), no training data.
- Design principles carried from earlier rounds: within-athlete, associational claims only; no composite scores;
  no fake precision; everything versioned (`METHOD_VERSION`).

**Success criteria**
1. On the 26 pilot clips, the board is located automatically on ≥ 22 clips (the rest via one-time corner clicks).
2. No throw reports an observed first contact unless the bag is at the deck or floor; every former mid-air
   contact becomes `lost_in_flight` with a labeled predicted contact (spot-checked in video).
3. Release frames unchanged or within ±1 frame of the current engine on all 26 clips.
4. Every chain quantity (§5) is produced with a state (measured / estimated / unavailable), a formula, and an
   uncertainty; bag-only mechanical quantities are labeled as such.
5. The movement→performance analyses (§6) run on a session with outcomes entered and produce only claims that
   pass the stated gates.

## 2. Architecture

A new **Scene** stage runs before bag tracking. Data flow:

```
video → camera stabilization (exists, ORB+RANSAC similarity chain)
      → athlete masks (scene_vision, Swift/Apple Vision)
      → background plate (background.py)
      → board model (board.py)
      → bag candidates vs plate, athlete pixels + off-corridor excluded (auto_bag.py)
      → flight fit (exists) → contact classified against deck/floor (contact.py)
      → landing + final rest in board inches → suggested outcome
      → chain quantities (chain.py, mechanics.py) → per-athlete analyses (chain_analysis.py)
```

### 2.1 Units

| Unit | Language | Purpose | Depends on |
|---|---|---|---|
| `scene_vision` | Swift executable target in `app/CornholeBiomechanics/Package.swift` | Apple Vision `VNGeneratePersonSegmentationRequest` (quality `.accurate`) on every 2nd frame; writes `athlete_masks.npz`-compatible output (uint8 masks at ½ resolution, run-length or PNG sequence) + per-person bounding boxes per frame as JSON | AVFoundation, Vision |
| `regulation.py` | Python | Single source of regulation constants (§3) | — |
| `background.py` | Python | Median of stabilized frames with athlete masked → clean plate (in release-frame coordinates) + per-frame warp to raw frames | stabilization transforms, masks |
| `board.py` | Python/OpenCV | Detect board quad (red deck + dark rim + hole), validate against regulation geometry, propagate per frame via stabilization; floor line; image→deck homography; out-of-plane angle φ; confidence | plate, `regulation.py` |
| `contact.py` | Python | Classify flight end: deck / floor / lost_in_flight; predicted contact by parabola extrapolation; final-rest classification (hole / board / off) | board model, flight fit |
| `mechanics.py` | Python | Bag-only mechanics: p, KE, PE, E, force vector, power, energy match, timing sensitivity | chain kinematics, `regulation.py` |
| `chain.py` | Python | Per-throw body → release → flight → outcome record, with states, formulas, uncertainties (Monte Carlo) | kinematics.py, timing.py, mechanics.py |
| `chain_analysis.py` | Python | Within-athlete analyses (§6) | chain records, performance.py, coaching.py |

Existing modules reused, not duplicated: `kinematics.py` (angles/angular velocities), `timing.py` (wrist speed,
peak timing), `filtering.py` (6 Hz Butterworth, residual-analysis justified), `performance.py` (Cliff's delta,
Holm), `coaching.py` (compensation), `bag_filter.py`, `bag_segment.py`, `zones.py` (switches to `regulation.py`).

Swift ↔ Python: Python invokes the `scene_vision` binary (path passed by the app / found next to the Python
runtime); outputs cached in the trial folder keyed by video hash + `SCENE_REVISION`.

## 3. Regulation constants (`regulation.py`)

Source: American Cornhole League rules and equipment pages (already in `docs/REFERENCES.md`).

| Constant | Value | Notes |
|---|---|---|
| Board deck | 48 × 24 in (1.2192 × 0.6096 m) | |
| Back height | 12 in | |
| Front height | 3 in default (2.5–4 in allowed) | configurable per session; deck angle ≈ 10.8° at 3 in |
| Hole | 6 in diameter; centre 9 in from top edge, 12 in from each side | |
| Bag | 6 × 6 in; 15.5–16 oz | nominal m = 0.447 kg (15.75 oz), range 0.439–0.454 kg propagated |
| Pitch | 27 ft front edge to front edge | used only as a sanity check, never as an assumed scale |
| g | 9.81 m/s² | |

## 4. Scene: athlete, background, board, contact

### 4.1 Athlete masks
- Used to (a) keep the pose track on the masked person nearest the tracked skeleton (bystanders ignored),
  (b) exclude athlete pixels (swinging arm/hand) from bag motion candidates until release + 2 frames,
  (c) render an "athlete on black" QA view.
- Pose accuracy itself is not claimed to improve from masking (RTMPose is trained on natural images).

### 4.2 Background plate
- Median of stabilized frames with masked athlete pixels treated as missing. Bag detection compares each frame
  against the plate warped to that frame, instead of three-frame differencing only. This suppresses bystanders,
  reflections that are static, and camera-shake "motion". The existing differencing remains as a fallback.
- Floor reflections are rejected: candidates below the floor line whose vertical motion mirrors a candidate above it.

### 4.3 Board model
- Detection on the plate: red/dark-rim colour segmentation → largest convex quadrilateral → hole (dark ellipse)
  detection inside it. Validate: deck aspect after homography ≈ 2:1, hole at (12 in, 9 in from top) ± tolerance.
- Output: 4 deck corners (raw per frame via stabilization), hole centre/ellipse, floor line (through the front
  legs / front-edge base), homography image → deck inches, out-of-plane angle φ of the throwing line, confidence.
- Precision reported per axis (along-deck vs across-deck in/px), since the pilot view is strongly foreshortened.
- Fallback: coach clicks 4 corners once per session; reused for clips whose plate aligns (ORB) with the reference.

### 4.4 Contact and landing (fixes mid-air "contact")
- The flight-fit end frame is a **candidate**. It is an **observed** first contact only if the bag centroid is
  within the deck quad expanded by ½ bag width (3 in → px via board scale), or the bag's lower edge is at the floor
  line within tolerance.
- Otherwise: `lost_in_flight`. The fitted parabola is extended to its first intersection with the deck region or
  floor line → **predicted contact** (frame, position, uncertainty from the fit covariance). Never counted as
  measured; excluded from landing statistics unless the coach confirms.
- Landing and final rest mapped to deck inches. Suggested outcome: bag vanishes within the hole ellipse → 3;
  final rest inside deck → 1; otherwise 0. Coach confirms with one click.

### 4.5 Scale
- Board length → m/px at the board. Cross-checked against the existing gravity-derived flight scale and athlete
  stature scale; > 10 % disagreement flags the throw. Speeds divided by cos φ; φ > 20° → flagged, not corrected
  (Sih et al., 2001).

## 5. Chain quantities per throw (`chain.py`, `mechanics.py`)

2D sagittal plane of the side camera; x toward the board, y up; SI units via §4.5 scale. Each quantity carries
`state`, `formula`, `inputs`, `assumptions`, `uncertainty` (95 % interval).

| Link | Quantity | Method |
|---|---|---|
| Body | Shoulder angle (upper arm vs trunk) and elbow included angle — at release and time series over forward swing | pose landmarks, 6 Hz zero-lag Butterworth |
| Body | Shoulder and elbow angular velocity; peak values and time of peak relative to release (ms) | derivative of filtered angles |
| Body | Wrist position, velocity vector, acceleration vector before release | 1st/2nd derivative of filtered wrist |
| Body | Segment peak sequence: shoulder → elbow → wrist-speed → release, lags in ms | **described, not graded** (Putnam, 1993 describes fast throws; cornhole is a slow accuracy swing); resolution 1 frame = 16.7 ms |
| Body | Shoulder–elbow coordination variability across throws (angle–angle) | see §6.5 |
| Release | Release velocity vector, speed, angle | existing ballistic fit + SE |
| Release | Release height h above floor line | board floor line |
| Mechanics (bag-only) | Momentum **p = m v** (vector) | m range propagated |
| | **KE = ½ m v²**, **PE = m g h**, **E = KE + PE** at release | |
| | Net force of hand on bag **F = m (a_bag − g⃗)**, g⃗ = (0, −9.81) m/s², i.e. F_x = m a_x, F_y = m (a_y + 9.81) | a_bag during forward swing from wrist kinematics plus rigid hand offset (~0.34 arm length beyond wrist along forearm): a_bag = a_wrist + α×r − ω² r; peak and mean |F|, direction |
| | Power to bag **P = F · v_bag**; cross-checked with dE/dt | reported only when both agree within uncertainty |
| | Energy match: release speed relative to the minimum speed that reaches the hole centre from this release height and angle (%) | target is "slightly above minimum" (Venkadesan & Mahadevan, 2017); no fixed ideal |
| | Release timing sensitivity: landing change (in) per 10 ms early/late release, computed from the hand path's position, velocity and acceleration at release propagated through projectile flight | Nasu et al., 2014 ("time in success zone"); Hore & Watts, 2011 |
| Flight | Drag-free predicted landing from (v, θ, h) vs measured landing | |
| Outcome | Landing along/across deck (in), error to hole along the throwing line, final rest, outcome 0/1/3 | |

**Labeling rule.** Mechanics rows are presented as "bag-only: net external force/power on a 0.45 kg bag". The app
states that these are **not muscle, joint, or hand-contact forces** and do not indicate shoulder/elbow loading.

**Uncertainty.** Monte Carlo (≈ 500 draws/throw) over: scale (from the three-way cross-check spread), bag mass
range, ballistic fit covariance, landmark noise (per-joint SD from pose noise floors; Needham et al., 2021
report 16–48 mm markerless joint-centre error). Second-derivative quantities (acceleration, force, power) are
reported only when their interval is narrower than the between-throw effect being described (noise amplification
of differentiation; Winter).

## 6. Linking movement to performance (`chain_analysis.py`)

All within one athlete, across repeated throws. Pre-specified variable list (fixed before data), Holm correction
across the list, associational wording only, claims need ≥ 5 throws per group and effect > noise floor
(existing gates in `performance.py`).

1. **Release → landing error budget.** Jacobian ∂R/∂v, ∂R/∂θ, ∂R/∂h at the athlete's mean release;
   σ_R² ≈ (∂R/∂v σ_v)² + (∂R/∂θ σ_θ)² + (∂R/∂h σ_h)² → share of landing spread from each release variable
   (Venkadesan & Mahadevan, 2017). Reported next to the measured landing spread.
2. **Predicted vs measured landing.** R² of drag-free prediction vs measured landing; the remainder is labeled
   slide/drag/measurement error.
3. **Body → release.** Spearman ρ with bootstrap 95 % CI for a short fixed list (peak elbow extension velocity
   vs release speed; shoulder angle at release vs release angle; peak-to-release lags vs release speed; wrist speed
   at release vs release speed).
4. **Movement → outcome.** Scored vs miss via Cliff's delta (existing) extended to chain variables; rank
   correlation with continuous landing error (usable with few misses).
5. **Consistency.** SD/CV per variable vs its noise floor ("within measurement noise" when below);
   Tolerance–Noise–Covariation style compensation (Müller & Sternad, 2004; existing `coaching.py`);
   within-athlete speed–angle trade-off (Linthorne, 2001); shoulder–elbow angle–angle variability across throws
   (lower variability associated with accuracy in prior throwing studies).
6. **Timing strategy.** Distribution of release timing sensitivity across throws; whether made throws have
   lower sensitivity (Nasu et al., 2014 two-strategy framing), reported descriptively.

## 7. Explicitly not reported

Joint moments, joint/muscle forces, wrist flexion or "wrist snap" (no hand landmarks at this resolution), trunk
axial rotation and lateral release direction (invisible to a side camera; lateral error measured on the board
only), bag spin.

## 8. Failure handling

Every stage emits `measured | estimated(reason) | unavailable(reason)`; the UI never shows a number without it.
- Board not found → one-time corner clicks; until then scale falls back to gravity scale (labeled), no landing.
- `scene_vision` fails → current motion-based tracking, flagged.
- Contact not observed → predicted only, excluded from landing statistics unless confirmed.
- Chain values whose CI exceeds between-throw differences → greyed "within measurement noise", excluded from claims.

## 9. Testing

- Synthetic unit tests: projectile with known (v, θ, h) → sensitivities/error budget; known planar arm motion →
  angular velocities, peak order, force vector (incl. gravity sign); rendered board at known pose → corners,
  homography, φ; hand-computed p, KE, PE, P; contact classifier on synthetic tracks ending mid-air vs on deck.
- Regression on 26 pilot clips: board-found rate, mid-air contacts removed (spot-check frames), release frames
  within ±1 of current, before/after report in `docs/`.
- Swift: `scene_vision` output-format test; existing VisualQA snapshots updated for new views.
- `METHOD_VERSION` bump; `scripts/reanalyze_library.py` reruns the pilot library.

## 10. References to add to `docs/REFERENCES.md`

- Venkadesan, M., & Mahadevan, L. (2017). Optimal strategies for throwing accurately. *R. Soc. Open Sci.*, 4, 170136. https://doi.org/10.1098/rsos.170136
- Nasu, D., Matsuo, T., & Kadota, K. (2014). *PLOS ONE*, 9(2), e88536 (already cited).
- Hore, J., & Watts, S. (2011). Skilled throwers use physics to time ball release to the nearest millisecond. *J. Neurophysiol.*, 106, 2024–2033. https://doi.org/10.1152/jn.00059.2011
- Putnam, C. A. (1993). Sequential motions of body segments in striking and throwing skills. *J. Biomech.*, 26(S1), 125–135. https://doi.org/10.1016/0021-9290(93)90084-R
- Linthorne, N. P. (2001). Optimum release angle in the shot put. *J. Sports Sci.*, 19(5), 359–372. https://doi.org/10.1080/02640410152006135
- Müller, H., & Sternad, D. (2004). Decomposition of variability in the execution of goal-oriented tasks. *J. Exp. Psychol. Hum. Percept. Perform.*, 30(1), 212–233. https://doi.org/10.1037/0096-1523.30.1.212
- Needham, L., et al. (2021). The accuracy of several pose estimation methods for 3D joint centre localisation. *Sci. Rep.*, 11, 20673. https://doi.org/10.1038/s41598-021-00212-x
- Winter, D. A. (2009). *Biomechanics and Motor Control of Human Movement* (4th ed.). Wiley.
- Sih, Hubbard & Williams (2001) and Tran et al. (2019) — already cited.

## 11. Out of scope for this spec

Coach-facing metric selection, dashboard layout and UI redesign (Part 2 spec, built on this engine's outputs);
heavy ML segmentation (SAM2/YOLO); re-recording protocol changes.
