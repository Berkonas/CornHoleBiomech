# Cornhole Biomechanics Lab

Cornhole Biomechanics Lab is a native macOS research application and a reusable Python analysis package for local, single-camera, markerless analysis of cornhole throws. It connects **how a participant moves** with **what the throw produces** while keeping raw videos, raw pose estimates, corrections, analysis settings, and results inspectable.

Stage 1 is a research prototype, not a medical device, clinical assessment, coaching oracle, or validated commercial scoring system. The software is implemented and tested; scientific completion still requires the project team to collect and evaluate real participant trials.

## 1. What this project is

The app supports this workflow:

```text
Create/open project → add athlete → import local video → label view/side/direction
→ run local pose estimation → inspect tracking → correct landmarks/events
→ record board outcome → inspect movement → select reference trial(s)
→ compare → analyze repeated trials → export
```

The interface is native SwiftUI and uses AVKit for video. A tested Python package performs the scientific calculations. There are no accounts, advertisements, analytics, cloud databases, OpenAI calls, or generated interpretations.

## 2. Research question

Primary research question:

> Can a single-camera, markerless 2D video-analysis system quantify upper-body cornhole throwing kinematics in a repeatable and interpretable way, normalize those measurements across athletes with different body sizes and proportions, and identify which movement features or deviations from a coach-selected reference pattern are associated with task performance?

Secondary research question:

> For an individual athlete, are better cornhole outcomes associated more strongly with similarity to a reference technique, with consistency of their own technique, or with specific kinematic features such as elbow motion, arm trajectory, trunk orientation, and timing?

## 3. Why this problem matters

Cornhole scores tell a coach what happened, but not why it happened. Laboratory motion capture can provide detailed biomechanics, but it is expensive, time-consuming, and impractical for routine training. If ordinary phone video can provide sufficiently repeatable upper-body kinematics, a coach could obtain individualized, evidence-based feedback during normal practice. The system must account for body-size differences, camera limitations, measurement uncertainty, and the possibility that more than one successful throwing strategy exists.

The app therefore keeps three questions separate:

1. **Reference similarity:** How similar is this throw to a coach-selected reference or reference set?
2. **Within-athlete consistency:** How repeatable are this athlete's own measured features?
3. **Performance relationship:** Which movement features are associated with better or worse outcomes?

A high similarity score is not automatically a good throw. Skilled precision throwers can use different successful motor strategies.

## 4. Stage 1 scope

Stage 1 is video-only and runs locally. It includes local video import, RTMPose and MediaPipe pose backends, upper-body projected 2D kinematics, quality gates, manual pose/event correction, reference comparison, outcome recording, within-athlete exploratory statistics, plots, annotated video, and transparent exports.

It does not include IMUs, force plates, EMG, cloud storage, accounts, generative AI, clinical interpretation, automated YouTube downloading, or Stage 2/3 hardware and AI features.

## 5. What the application measures

All angle names mean **projected into the image plane**.

| Measurement | Definition | Units | Interpretation and main limitation |
|---|---|---:|---|
| 2D projected elbow angle | Angle shoulder–elbow–wrist | degrees | Image-plane elbow flexion geometry; changes with out-of-plane rotation |
| Upper-arm orientation | Throwing shoulder→elbow direction from image horizontal | degrees | Segment orientation in target-forward, y-up axes |
| Forearm orientation | Throwing elbow→wrist direction from image horizontal | degrees | Segment orientation, not pronation/supination |
| Arm angle relative to trunk | Unsigned angle between upper arm and hip→shoulder trunk axis | degrees | Projected arm/trunk configuration |
| Trunk inclination | Signed trunk top displacement relative to image vertical | degrees | Positive toward target after direction reflection |
| Wrist trajectory | Wrist minus throwing shoulder, divided by arm length | arm lengths | Dimensionless shoulder-centered path |
| Elbow trajectory | Elbow minus throwing shoulder, divided by arm length | arm lengths | Dimensionless shoulder-centered path |
| Angle range of motion | finite maximum minus finite minimum | degrees | Observed projected range in the analyzed interval |
| Angular velocity | derivative of filtered angle | degrees/second | Reported only with adequate finite coverage |
| Movement duration | effective motion-end frame minus motion-start frame, divided by fps | seconds | Frame-limited duration |
| Event timing | event position within effective motion interval | cycle fraction or percent | Release cannot be more precise than the recording frames |

Summary values are calculated over the available analyzed frames; release values use the effective automatic-or-manual release frame.

## 6. Human anatomy involved

Primary markerless estimates are left/right shoulder, elbow, wrist, and hip. The throwing-side shoulder, elbow, and wrist define the arm. The hip midpoint and shoulder midpoint define the trunk. Hip points are used as a trunk reference even though the study focus is upper-body motion.

The model estimates image keypoints, not palpated anatomical joint centers. Stage 1 does not infer shoulder internal/external rotation, humeral axial rotation, forearm pronation/supination, or 3D wrist rotation from ordinary 2D video.

## 7. Coordinate-system definitions

- Raw video pixels: origin at image top-left; x increases right; y increases downward.
- Kinematic axes: y is flipped upward.
- Target-forward axes: x is reflected for right-to-left trials so positive x always points toward the target.
- Relative trajectories: throwing shoulder is the origin on every frame.
- Body scale: relative arm paths are divided by median upper-arm length plus median forearm length.
- Board coordinates: `(0, 0)` is the left corner at the pitcher end; x runs left-to-right from 0–24 inches and y runs pitcher-to-back from 0–48 inches. Hole center is `(12, 39)` inches and hole radius is 3 inches.
- Normalized time: motion start is 0% and motion end is 100%.

Direction reflection, translation, and uniform scale normalization cannot remove perspective distortion or recover motion perpendicular to the image plane.

## 8. Camera setup

Use a side/sagittal-like view for primary Stage 1 comparison:

- Put the phone on a tripod or stable support; do not hand-hold it.
- Keep the optical axis as perpendicular as practical to the main motion plane.
- Keep the entire upper body and throwing arm visible throughout the throw.
- Avoid severe perspective, digital zoom changes, motion blur, and backlighting.
- Use the same camera position and framing when comparing trials.
- Record at 60 fps or higher when available; 120 fps may improve later event work.
- Label every video Side, Front, or Other / Exploratory.

The engine warns below 60 fps and more strongly below 30 fps. The comparison command blocks incompatible camera-view labels. Front/other recordings can be explored but are not silently treated as side-view equivalents.

## 9. Pose estimation

The primary backend is RTMPose through RTMLib and ONNX Runtime on CPU. MediaPipe Pose Landmarker 0.10.35 is an offline fallback. Both expose per-keypoint confidence-like scores, although those scores are not calibrated physical position-error bounds.

The setup step downloads model files once. After models are cached, analysis is offline. Every manifest records the backend, model identity/version, model hash when available, video hash, and backend metadata. Raw predictions are cached by video/model/device key so reopening a trial does not repeat inference unnecessarily.

Sports2D received particular attention during tool review because it already offers research-oriented single-camera 2D processing. This project uses its ideas and documented ecosystem as a reference, but adds an independent cornhole-specific workflow, correction/provenance model, normalization, outcome model, reference comparison, and movement–performance analysis. See [RESEARCH_NOTES.md](RESEARCH_NOTES.md) and [REFERENCES.md](REFERENCES.md).

## 10. Manual pose correction

After analysis, open **Trials → Inspect & Correct**, pause at a frame, select a landmark, and drag it to the corrected image location. Green points meet the configured confidence threshold; red points do not; corrected points have a distinct blue/yellow treatment. Native Undo/Redo and “Reset to automatic” are supported.

The file `pose_raw.json` is never edited. Corrections live in `corrections.json` with frame, landmark, corrected x/y, kind, and timestamp. Optional interpolation creates explicitly labeled `interpolated` correction records between two user anchors. It is visible and reversible. Re-run analysis after correction so filtering, events, kinematics, plots, and quality metrics use the effective points.

## 11. Equations for joint angles

For planar angle `ABC`, where `B` is the joint:

```text
u = A − B
v = C − B

θ = atan2(|uₓvᵧ − uᵧvₓ|, u · v) × 180/π
```

This stable form produces an unsigned result from 0° to 180°. A zero-length or non-finite vector produces a missing value, not an invented angle. Synthetic tests verify 0°, 45°, 90°, 135°, and 180° cases.

Signed segment orientation uses `atan2(vᵧ, vₓ)`. Trunk inclination uses `atan2(trunkₓ, trunkᵧ)` so 0° is image vertical after the y-up and target-direction transformations.

## 12. Filtering

The processing order is corrections → confidence mask → short internal-gap interpolation → coordinate filtering → angle calculation → differentiation. The engine never differentiates raw noisy pose coordinates directly.

Default filtering is a fourth-order, zero-phase Butterworth low-pass filter with a 6 Hz cutoff. It is a documented pilot starting point, not a universal optimum copied from another task. Forward/backward second-order-section filtering avoids phase lag but can be sensitive at signal edges. Runs too short for defensible filtering remain unfiltered and generate a warning. The cutoff, order, enable state, frame rate, and effective cutoff are saved in the manifest and exposed under Advanced Analysis. The engine rejects a cutoff at or above Nyquist.

Pilot data should be inspected spectrally and against manual traces before confirming the cutoff. Velocity is omitted when finite angle coverage is below the configured 80% threshold.

## 13. Anthropometric normalization

Raw pixels are never used for between-athlete trajectory scoring. The robust arm scale is:

```text
Larm = median(||shoulder − elbow||) + median(||elbow − wrist||)

p̂wrist(t) = [p_wrist(t) − p_shoulder(t)] / Larm
```

Medians use finite frames and reduce the influence of isolated keypoint errors. Joint angles are already invariant to uniform scale. This normalization removes translation and uniform image scale, but not perspective, out-of-plane motion, or genuine anatomical/strategy differences. Height and arm span are optional context and are not required.

## 14. Time normalization

Automatic candidates identify motion start, peak backswing, forward swing, visible release, peak follow-through, and motion end from wrist-path behavior. Manual frames are stored separately and take precedence as the effective event.

For selected start/end times:

```text
τ = (t − t_start) / (t_end − t_start)
```

Each curve is linearly resampled to 101 samples from 0–100% by default. Release timing is reported as a cycle fraction. At 60 fps the frame interval is about 16.7 ms; the app never claims sub-frame bag-release timing.

## 15. Reference comparison

One or several analyzed trials may be marked **Coach-Selected Reference**. A reference set uses its pointwise trajectory mean and, when `n > 1`, standard deviation. The test trial is compared after target-direction reflection, shoulder translation, arm-length scaling, and time normalization.

The primary comparison preserves movement-cycle time. Dynamic time warping is not used to erase timing differences. The app reports angle MAE, RMSE, waveform correlation where defined, peak and range differences, event-timing difference, and normalized wrist/elbow path RMSE. Different camera-view labels are rejected.

## 16. Similarity score

Raw errors appear before the score. Each configured component is transformed by:

```text
component score = 100 × max(0, 1 − raw error / tolerance)
overall score   = weighted mean of available component scores
```

The interface exposes every component's raw error, units, tolerance, weight, score, and equation. Missing components are omitted and named. Current tolerances are stored configuration values for pilot use, not population norms. They should later be derived from reference variability, measurement uncertainty, and pilot data.

With one reference, the result is labeled **“Prototype reference similarity – single reference trial.”** The score means reference similarity, never “perfect mechanics” or performance quality.

## 17. Performance outcome

Every trial can store intended target, 3/1/0 score, throw type, notes, and approximate board clicks for intended point, first contact, and final resting point. ACL board coordinates use inches and documented dimensions. When intended and actual points exist, the Python engine calculates signed lateral error, signed longitudinal error, and radial error.

A manual click is labeled approximate. It must not be interpreted as instrument-level spatial precision. Score categories are 3 through the hole, 1 on the board, and 0 off board/foul.

## 18. Movement-versus-performance analysis

The initial analysis is within one athlete. It evaluates elbow angle at release, elbow range, trunk inclination at release, movement duration, and release timing against approximate radial target error when available, otherwise 0/1/3 score.

The Results view shows raw paired observations, sample size, feature mean/median/standard deviation/range, and Spearman rank correlation with bootstrap confidence interval when justified. Fewer than eight complete pairs by default produces exactly: **“Not enough trials to estimate this relationship reliably.”** No small-sample machine learning is used, and observational correlation is not described as causal.

Reference similarity, personal consistency, and movement–outcome association remain separate sections. This prevents the system from assuming that copying the reference guarantees success.

## 19. What the system CAN claim

- It computes reproducible image-plane geometry from stored markerless estimates and corrections.
- It can compare compatible-view trials after documented translation, reflection, scale, and time normalization.
- It can quantify trial-to-trial variability for one athlete.
- It can describe exploratory within-athlete associations between complete movement and outcome observations.
- It can reveal tracking gaps, low confidence, correction counts, filtering conditions, and other quality warnings.

Claims still depend on the quality and validity of the recordings and pose estimates.

## 20. What the system CANNOT claim

- A 2D projected value is not a true 3D anatomical joint orientation.
- Pose keypoints are not ground-truth joint centers.
- Reference similarity is not proof of performance quality, safety, or ideal form.
- Correlation does not show that a movement feature causes an outcome.
- The software does not diagnose injury, prescribe treatment, or estimate joint loads.
- Public/YouTube test footage does not satisfy the course requirement for participant performance data.
- This pilot does not provide population norms.

## 21. 2D limitations

Single-camera results are sensitive to camera angle, perspective, lens distortion, occlusion, cropping, motion blur, pose-model domain shift, clothing, lighting, and movement out of the image plane. Even a reliable repeated 2D signal can be biased relative to 3D anatomy; reliability is not the same as validity. Body normalization does not correct foreshortening. A side-view label describes the protocol goal, not proof of perfect sagittal alignment.

## 22. How to install

Requirements used for this build:

- macOS 15 or later on Apple Silicon
- Xcode 26.6 at `/Applications/Xcode.app` (Swift 6.3.3, code compiled in Swift 5 language mode)
- Python 3.11 or 3.12
- Internet access once for Python packages/model download

From Terminal:

```bash
cd "/Users/berkonas21/Desktop/Classes Fall 2026/Biomech/Project 1 - Cornhole"
./setup.sh
./build_app.sh
```

`setup.sh` creates `.venv`, installs the local package plus tested pose dependencies, and caches the official MediaPipe fallback model. RTMPose model files download into the user model cache on first use. Analysis is local after caches exist.

## 23. How to launch the Mac app

```bash
./run_app.sh
```

Or open `dist/Cornhole Biomechanics Lab.app` in Finder. The ad-hoc-signed development build expects to remain within this repository so it can locate `.venv` and `python/`. The working name and version are centralized near the top of [Models.swift](CornholeBiomechanics/Sources/CornholeBiomechanics/Models.swift).

Create a `.cornholeproject` folder from the welcome screen. The app copies imported videos into that project and never modifies the selected source file.

## 24. How to run analysis from Python

The bundled development Python currently requires an explicit package path in this workspace:

```bash
export PYTHONPATH="$PWD/python"

.venv/bin/python -m cornhole_biomech probe
.venv/bin/python -m cornhole_biomech video-info "/path/to/throw.mov"
.venv/bin/python -m cornhole_biomech analyze "/path/to/throw.mov" \
  --output "/path/to/output" \
  --trial-id "trial-001" --athlete-id "participant-001" \
  --view side --throwing-side right --target-direction left_to_right
```

Additional commands:

```bash
.venv/bin/python -m cornhole_biomech compare \
  --test "/path/to/test-analysis" \
  --reference "/path/to/reference-analysis" \
  --output "/path/to/comparison"

.venv/bin/python -m cornhole_biomech batch "/path/to/batch-spec.json"
.venv/bin/python -m cornhole_biomech relationships \
  --analysis "/path/to/trial-analysis" \
  --outcomes "/path/to/outcomes.json" \
  --output "/path/to/relationships.json"
```

Use `--backend mediapipe` for the fallback. `--pose-input` accepts canonical `pose_raw.json`, enabling reproducible tests and external pose interchange without rerunning inference. All command output is structured JSON lines (`progress`, `result`, or `error`), not unstructured text scraping.

## 25. Input files

- Local `.mov`, `.mp4`, or another OpenCV/AVFoundation-readable video.
- Required labels: athlete, camera view, throwing side, and target direction.
- Optional source URL and attribution/permission note.
- Optional canonical pose JSON for CLI analysis.
- Optional corrections, manual event overrides, and configuration JSON.

The app intentionally does not download YouTube media. It can retain and open a source URL. The user is responsible for permission to download or analyze any third-party recording; failure of an external source never blocks normal local-video analysis.

## 26. Output files

Each analyzed trial can contain:

| File | Purpose |
|---|---|
| `manifest.json` | versions, hashes, model, configuration, provenance, output inventory |
| `pose_raw.json` | immutable frame-by-frame markerless estimates |
| `pose_cache.json` | cache key for video/model/device inputs |
| `corrections.json` | separate manual/interpolated point changes |
| `events.json` | automatic and manual event frames |
| `outcome.json` | trial outcome and approximate board points |
| `keypoints.csv` | raw, effective, filtered, confidence, and correction flags |
| `kinematics.csv` | frame-time projected angles, velocities, and normalized paths |
| `normalized.json` | 101-sample curves and normalized event timing |
| `results.json` | summaries, quality, warnings, claim scope |
| `annotated.mp4` | source frames with filtered skeleton overlay |
| `angle_trajectories.png` | selected projected angle curves |
| `wrist_trajectory.png` | dimensionless shoulder-relative wrist path |
| `summary.md` | concise auditable result summary |

A comparison adds `comparison.json` and `comparison_elbow_angle.png`. Relationship analysis adds `outcomes.json` and `relationships.json`. Export copies the selected analysis package without altering it.

## 27. Data organization

```text
Study.cornholeproject/
├── project.json                  # project, athlete, trial metadata
├── videos/                       # immutable imported copies
├── analyses/<trial UUID>/        # per-trial scientific package
├── comparisons/<trial UUID>/     # test-to-reference result
├── relationships/<athlete UUID>/ # within-athlete result
└── exports/                      # reserved project export location
```

Large frame arrays remain in transparent files rather than metadata records. A stable UUID links athlete, trial, outcome, analysis, and comparison. Writes use atomic replacement where practical. Original assignment PDFs, books, papers, and videos are ignored by Git and never changed by setup or analysis.

## 28. Validation and tests

Run all automated checks:

```bash
PYTHONPATH=python .venv/bin/python -m pytest -q
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer \
  swift test --package-path CornholeBiomechanics
./build_app.sh
codesign --verify --deep --strict "dist/Cornhole Biomechanics Lab.app"
```

The Python suite contains 25 tests covering exact known angles, scale/translation invariance, time resampling, left/right mirroring, low confidence, correction separation, short-gap interpolation, filtering, event detection/override, time-preserving curve errors, score transparency, exported comparison curves, board errors, sample-size gating, consistency/performance separation, quality warning gates, and a video-to-result-package integration test. Five Swift tests cover portable project/outcome encoding, non-destructive correction undo, and the Python-to-Swift result boundary. The release app is built, plist-checked, ad-hoc signed, launched, and visually reviewed in the active system appearance; semantic colors and controls support light, dark, and increased-contrast behavior.

Automated correctness does not establish criterion validity. Follow [docs/VALIDATION_PROTOCOL.md](docs/VALIDATION_PROTOCOL.md) with real, consented participant trials.

## 29. Troubleshooting

**“Python environment was not found.”** Run `./setup.sh` from the repository root. Use Python 3.11/3.12, not the system Python 3.9.

**`No module named cornhole_biomech` at the command line.** Run `export PYTHONPATH="$PWD/python"` first. The Mac app sets this automatically.

**MediaPipe fails to initialize.** This project pins `mediapipe>=0.10.21,<0.11`; a tested 1.0.1 macOS build failed during graph initialization. Re-run setup and confirm `.venv/bin/python -m pip show mediapipe` reports 0.10.35 or another compatible 0.10 release.

**Pose inference is slow.** The default CPU path prioritizes compatibility and reproducibility. Trim unrelated footage before import, keep one athlete visible, and reuse the cached pose result. Do not interrupt model download on the first RTMPose use.

**A comparison is unavailable.** Analyze both trials, mark at least one reference, and ensure camera-view labels match. Side-to-front comparison is intentionally blocked.

**Velocity is unavailable.** Inspect quality warnings. Low finite coverage or filter failure prevents defensible differentiation.

**The app cannot open a video.** Convert it to a standard local H.264 `.mp4` or QuickTime `.mov`; preserve the original separately.

## 30. Scientific references

The complete bibliography—including peer-reviewed precision-throwing, markerless-validation, camera-geometry, filtering, software, ACL, Apple HIG, and YouTube policy sources—is in [REFERENCES.md](REFERENCES.md). The source-to-decision evidence table is in [RESEARCH_NOTES.md](RESEARCH_NOTES.md).

Seed scientific papers include Nasu, Matsuo, and Kadota (2014), [doi:10.1371/journal.pone.0088536](https://doi.org/10.1371/journal.pone.0088536); Nasu and Matsuo (2015), [doi:10.5432/jjpehss.14047](https://doi.org/10.5432/jjpehss.14047); and Tran, Yano, and Kondo (2019), [doi:10.1371/journal.pone.0223837](https://doi.org/10.1371/journal.pone.0223837).

## 31. Open-source acknowledgements

- NumPy, SciPy, pandas, Matplotlib, and OpenCV provide numerical, signal-processing, tabular, plotting, and video operations.
- RTMLib/RTMPose and ONNX Runtime provide the primary local pose path.
- MediaPipe Pose Landmarker provides the fallback.
- Sports2D, Pose2Sim, MMPose/RTMPose, MediaPipe, and DeepLabCut informed the documented tool review; their versions, licenses, repositories, and requested citations are listed in [REFERENCES.md](REFERENCES.md).
- SwiftUI, Charts, AVFoundation, and AVKit provide the native macOS interface.

No dependency's output is treated as ground truth merely because it is produced by an established package.

## 32. Future Stage 2 / Stage 3 extensions

Stage 2 may add deliberately synchronized sensors such as IMUs only after video timing, calibration, storage, and validation are stable. Stage 3 may add an optional `ExplanationProvider` that consumes compact numerical results, but it must remain separate from measurement code, state uncertainty, use secure user-provided credentials, and never replace raw evidence.

Other defensible extensions include calibrated 2D distance, multiple-camera 3D reconstruction with Pose2Sim, cornhole-specific labeled pose training with DeepLabCut, validated hand landmarks, multi-trial reference uncertainty, front-view exploratory measures, richer repeatability statistics, and preregistered participant analysis. None are silently implied by Stage 1.
