# Cornhole Biomechanics Lab

## What this app does

Cornhole Biomechanics Lab connects a thrower's movement with the bag's result. Import a local video, check the tracked body points, record the outcome, and inspect the throw inside a native Mac app. You can compare a throw with a coach-selected reference, another throw, or the athlete's own repeated movement.

The Results screen combines video, projected joint angles, normalized wrist paths, reference differences, tracking quality and a board map. After enough comparable throws, it shows repeatability and exploratory movement–outcome relationships. All explanations are deterministic statements calculated from the data. There is no generative coach or hidden overall athlete score.

This is Stage 1 research software. A working application does not establish measurement validity. Real participant recordings and the validation protocol remain part of the course project.

## The research question

Can single-camera markerless video quantify upper-body cornhole kinematics repeatably, normalize measurements across athletes with different body proportions, and identify movement features associated with task performance?

## Why this matters

Scoring tells us what happened to the bag. Movement measurements can help us investigate how the athlete threw it. The important questions remain separate: resemblance to a reference, repeatability of the athlete's own motion, and association with task outcome. Successful throws need not all look alike.

## What Stage 1 measures

```text
Video → Body tracking → Movement measurements → Reference comparison
                                                   ↓
                            Athlete insights ← Cornhole outcome
```

Stage 1 measures image-plane elbow angle, upper-arm and forearm orientations, arm relative to trunk, trunk inclination, shoulder-relative arm paths and movement timing. It records official 0/1/3 bag outcomes and optional approximate board locations. It does not recover ground-truth 3D rotations, force, muscle activity or injury risk from one camera.

## Quick start

1. Open `dist/Cornhole Biomechanics Lab.app` after installation/build.
2. Create a project in a local folder you choose and add an athlete.
3. Start a recording session to carry camera and athlete details into each import.
4. Import a throw and choose **Analyze**. Sports2D is the default engine.
5. In **Trials**, review **Inspect & Correct** and **Quality & Events**.
6. Record the bag outcome. Open **Results** to understand the throw.
7. Mark reference throws in **Reference**, then use **Compare**.

Original videos are copied into the selected project; they are never overwritten. Project data is separate from the source repository.

## How to record a good video

Use a fixed tripod and a clear side view, with the optical axis roughly perpendicular to the throwing plane. Keep both shoulders, both hips and the entire throwing arm visible. Use consistent framing and lighting, avoid motion blur and zoom changes, and record at 60 fps or higher when practical. Frame rate alone cannot rescue blurred or obscured landmarks. Prefer one visible thrower; verify that the selected Sports2D track is the intended athlete.

## How to analyze a throw

The app runs a local Python worker and reports its stage. First use may download model weights. Once models are cached, analysis can run offline. **Cancel** stops the worker; retain the video and re-run incomplete analysis.

Drag a tracked point to correct it, or choose **Correction actions → Enter pixel coordinates** for precise keyboard entry. Corrections and interpolated anchors remain separate from raw pose. Undo/Redo buttons, Command-Z, Shift-Command-Z and reset are supported. Reanalyze after changing tracking or events. The original model predictions are reused from cache when the video/model settings match.

Automatic release is a wrist-speed **candidate**, not a direct observation of bag separation. Inspect the recording and manually set visible release where possible. Events remain frame limited.

Use **Advanced Analysis** for backend, model, confidence, interpolation and filter settings. Direct RTMPose and MediaPipe are explicit alternatives if Sports2D is unavailable or fails; the app never silently changes engines.

## Understanding the Results screen

- **ACL bag result:** 0, 1 or 3 points. This is the bag's outcome, not an inning's cancellation score.
- **Reference Similarity:** 0–100 resemblance to selected reference throws. Expand the components to see errors, units, tolerances, weights and formula.
- **Athlete Consistency:** repeatability across at least five comparable throws. Missing data produces “More trials needed.”
- **Tracking Quality:** a transparent pilot confidence index. Review camera, frame-rate and occlusion warnings even if similarity is high.
- **Performance relationships:** scatter plots, sample size and Spearman estimates when at least eight complete pairs exist and both variables vary.

Select a listed movement difference or timeline event to seek the video and synchronized plots. The wrist path uses arm lengths. The board map uses different symbols for target, first contact and final rest; overlay comparable throws to inspect dispersion.

## What each biomechanics metric means

The elbow measurement is an **included angle**: 180° is straight, and a smaller value is more flexed in the image. Segment orientation says which way an arm segment points; it does not measure forearm twist or shoulder axial rotation. Trunk inclination says how far the midpoint trunk leans toward the target in the camera plane.

For elbow points S (shoulder), E (elbow), W (wrist):

`angle = atan2(|(S−E) × (W−E)|, (S−E) · (W−E))`

Convert to degrees. Missing/degenerate points produce missing angles. See [docs/METRICS.md](docs/METRICS.md) for every metric, interval, unit, equation, Sports2D convention and limitation.

## How body-size normalization works

A 5′4″ athlete and a 6′8″ athlete can follow similar relative paths while producing very different pixel distances. Camera distance changes pixels too. We therefore align the throwing shoulders and divide the wrist path by estimated arm length:

`Larm = median(upper-arm length) + median(forearm length)`

`normalized wrist = (wrist − throwing shoulder) / Larm`

Horizontal direction is reflected toward the target; vertical direction points up. Movement start and end map to 0–100%. This removes translation and uniform image scale, while preserving timing differences. It cannot remove perspective or actual limb-proportion differences. The app includes a visual explanation under **How bodies are aligned**.

## How reference comparison works

Mark one or several analyzed throws as references. The app compares normalized waveforms to their pointwise mean; the spread is shown when multiple references exist. Camera views and time grids must match. It reports angle errors, wrist-path RMSE and timing differences without dynamic time warping.

`component = 100 × max(0, 1 − error / tolerance)`

The displayed total is the weighted mean of available components. Pilot tolerances are visible and saved. Missing components are named. A changing reference changes the meaning of the score.

## Why the reference is not called “perfect form”

A reference is a selected comparison pattern. It is not proof of an optimal technique. Skilled precision throwers can use different strategies, and similarity does not guarantee points. The app preserves that distinction.

## How consistency is measured

Use at least five throws from the same athlete, session, view, throwing hand, pose model and processing settings, with at least 80% usable frames. The app measures pointwise waveform variability in elbow, trunk and wrist, plus release-timing variability. All four components must be supported to show a score. The mean and variability remain visible alongside the score.

`Consistency = mean(100 × max(0, 1 − variability / pilot tolerance))`

This describes repeatability, not whether the technique is good. **Athlete vs own mean** comparison excludes the selected throw from the comparison mean.

## How movement is related to performance

Relationships are explored within a comparable athlete group. Target error is preferred when spatial observations exist; otherwise the response is the 0/1/3 bag outcome. Contact and final-rest measurements are not pooled into one spatial response. At least eight complete pairs and variation in both measures are required for Spearman rho and a bootstrap interval. This threshold does not guarantee statistical power, and correlation does not establish causation.

## Sports2D integration

The pinned runtime is **Sports2D 0.8.34** with **Pose2Sim 0.10.49**. Sports2D provides RTMPose tracking, native angles, diagnostic processing, annotated video and TRC/MOT. Our code adds corrections, cornhole-specific measurements, normalization, reference comparison, sessions, outcomes and interpretation.

The adapter calls the public Python API. Because this version does not return raw confidence, a small version-locked bridge preserves its tracked pre-interpolation arrays; unsupported versions fail explicitly. The app retains model hashes, backend versions, settings and source hashes.

Metric conversion, C3D, camera/floor estimation, marker augmentation and inverse kinematics are disabled in the uncalibrated Stage 1 profile. Pixel coordinates must not be presented as measured millimeters or 3D biomechanics. CPU is the validated default; MPS/CoreML requires a separate equivalence check. See [docs/SPORTS2D.md](docs/SPORTS2D.md) for capability decisions and native-export differences.

## Files and exports

A trial directory retains `pose_raw.json`, `corrections.json`, `events.json`, `normalized.json`, `keypoints.csv`, `kinematics.csv`, `results.json`, `manifest.json`, plots and annotated video. Outcomes add `outcome.json`. Opening Results generates `insights.json`, `summary.md`, relationship information and a self-contained **report.html** with embedded figures.

Use **Open local report** for the readable report and **Export research package** for the complete trial folder. Sports2D diagnostic artifacts live in its own subfolder and keep their original configuration/date when cached pose is reused. Comparisons have separate exports. Raw data remains available, but opening CSV is not needed to understand a result.

## Validation

Mathematical, normalization, correction, cache, decoding and integration tests support software correctness. A real Sports2D sample-video run checks the backend. Synthetic QA projects are clearly labeled and never counted as participant data. Follow [docs/VALIDATION_PROTOCOL.md](docs/VALIDATION_PROTOCOL.md) for real recordings, manual digitization, rater repeatability and agreement testing. Final verification is recorded in [docs/QA.md](docs/QA.md).

## Limitations

Single-camera results are sensitive to camera placement, projection, occlusion, motion blur and model errors. Automatic release needs review. Board points are approximate. Pilot scores are not validated norms. Several successful styles may exist. The current native release uses a local installed Python runtime; it is not a standalone distributable for another Mac without setup. See METRICS.md for precise summary intervals and missing-data rules.

## How to install

Requirements: macOS 15 or newer, Xcode with command-line tools, Python 3.11 or 3.12, and network access for the initial package/model installation.

```sh
./setup.sh
./build_app.sh
./run_app.sh
```

The root scripts are compatibility entry points; implementations live in `scripts/`. Setup installs the runtime under `~/Library/Application Support/Cornhole Biomechanics Lab/Runtime`, with a repository `.venv` symlink for development. The release bundles its Python source. This avoids launching a Python environment from macOS-protected Desktop folders. Set `CORNHOLE_PYTHON=/path/to/python3.12` for setup if needed.

## How to run

Open the built app in Finder, or run `./run_app.sh`. Keep projects in a local folder you select. For command-line analysis:

```sh
PYTHONPATH=python .venv/bin/python -m cornhole_biomech probe
PYTHONPATH=python .venv/bin/python -m cornhole_biomech --help
```

## Testing

```sh
.venv/bin/python -m pytest
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer swift test --package-path app/CornholeBiomechanics
./build_app.sh
```

For a visibly synthetic nine-throw UI fixture:

```sh
.venv/bin/python scripts/create_qa_project.py --output /tmp/Cornhole-QA.cornholeproject
```

The destination must not already exist. These generated videos and numbers test the software; they are not experimental results.

## Repository layout

`app/` contains the native Swift package and icon asset catalog. `python/` contains the existing scientific engine. `tests/` contains Python tests; Swift tests remain beside their package. `docs/` contains specifications, validation and QA. `resources/branding/` holds the editable original SVG and icon representations. `scripts/` contains installation, build and QA utilities. `reference_materials/` holds unchanged local books and course files and is excluded from Git.

## References

[REFERENCES.md](REFERENCES.md) lists course material, precision-throwing literature, markerless measurement research, Sports2D, signal processing, ACL rules and Apple documentation. [RESEARCH_NOTES.md](RESEARCH_NOTES.md) separates the evidence from this project's decisions.

## Future Stage 2 and Stage 3

Later stages can investigate synchronized sensors, calibrated multi-camera validation and individualized models after sufficient real data exist. They should preserve the separation between movement measurement, repeatability, task outcome and evidence for coaching decisions.

## Release verification status

See [docs/QA.md](docs/QA.md) for the verified native workflows, test results and remaining validation scope. A successful build and passing calculations do not establish task-specific biomechanical accuracy.

The Appearance menu provides System, Light and Dark modes. In Inspect & Correct, the frame cursor carries into Movement Events; **Mark event** labels the displayed frame. The outcome editor can **Save & import next throw** while retaining the session's recording metadata. The quality disclosure shows the saved filter, confidence and gap settings used for that analysis.

Analysis manifests include a path-independent SHA-256 fingerprint of the Python engine source in addition to video, model, settings and correction provenance. Preserve the project and recorded engine revision to reproduce a measurement. Sports2D pixel TRC headers are corrected to `px`, with exact upstream originals retained; see [the export notes](docs/SPORTS2D.md#upstream-export-quirks-verified-on-0834).
