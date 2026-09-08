# Release verification — 0.2.0

Status: release 0.2.0 built and exercised on 8 September 2026. This record describes software verification, not participant-validation evidence.

## Automated checks

- Python: 49 tests pass, covering known geometry, scale/translation/reflection, finite-run filtering and derivatives, missingness, stationary/missing event cases, event ordering, board coordinates, comparison/consistency arithmetic, circular angles, stale data, pipeline exports, cached pose and correction provenance.
- Swift: 7 tests pass, including native/Python data boundaries, saved correction schema, project round trip, outcomes and correction undo without changing raw pose.
- Release build: succeeds with the native Swift package in `app/`.
- Source materials: relocation was checked with per-file SHA-256 comparisons; local books/course materials remain excluded from Git.

## Real Sports2D integration

Sports2D 0.8.34 / Pose2Sim 0.10.49 ran on a 60-frame, 30-fps crop of the official Sports2D demo from inspected commit `4392177d75dff43b4da60514d3766029201a5c5e`. This is a public software test clip, not a cornhole participant trial.

Verified: raw tracked pixels and confidence, selected-person/model provenance, readable TRC and MOT with 60 samples, both annotated videos, canonical JSON/CSV/plots and source/model hashes. The canonical annotation contains all 60 frames; the upstream diagnostic annotation contains 59. Pixel TRC headers are repaired from the upstream writer's hardcoded `m` to `px`, with exact originals retained and both hashes recorded.

The adapter's elbow conversion matches installed Pose2Sim `fixed_angles` on 120 elbow samples from identical saved raw pixels; maximum discrepancy is 2.85e−14 degrees. This verifies conventions, not pose-estimator accuracy. Unit tests also cover missing/wrong versions, processing failure, missing exports, no silent backend substitution and profiling/TLS cleanup.

## UI and export review

Before the second pass, project creation/opening, athlete creation, imports, reference and empty states were exercised. Current release Results now opens after replacing the crashing system SwiftUI AVKit wrapper with `AVPlayerView`. The native worker completes insight generation using the Application Support runtime and bundled engine.

Nine clearly labeled synthetic throws exercise two references, repeated-trial consistency and paired movement/outcome summaries. Their generated values must never be presented as participant evidence.

The local HTML report was rendered at wide and narrow widths. Titles, scores, actual comparisons, wrist and board figures were inspected. Clipped UUID figure titles were replaced with meaningful titles. The original vector icon, generated representations, Finder icon and About panel (version 0.2.0, build 2) were visually inspected. Dock automation timed out, so the Dock icon is not independently verified in this record.

Verified in the running native app:

- Sports2D analysis completes on the official software test clip. Cached reanalysis preserves the raw-pose SHA-256 while applying a separate wrist correction and reviewed start event; the correction count becomes 1 and the stale marker clears.
- Direct dragging now selects the intended wrist and moves it by the drag displacement. Fixed oversized overlapping hit areas and an absolute-coordinate offset. Pixel entry provides a reproducible keyboard alternative, including for missing points. Undo/Redo buttons and Command-Z / Shift-Command-Z restore automatic/manual states; changing trials clears the previous undo history.
- Playback followed by an event seek updates video, frame label, cycle cursor, skeleton and plots together. Replaced the crashing SwiftUI AVKit wrapper with AppKit AVPlayerView; the inspector uses one dedicated transport row.
- Reference set, single reference, own mean and trial-to-trial comparisons all calculate through the native worker. The own mean excludes the selected throw and the different-backend demo clip. Synthetic fixture scores were 86, 85, 100 and 92 respectively; these are test outputs, never production defaults.
- Session creation saves athlete, camera, date and notes. Outcome entry at target (12,39) and contact (10,36) yields 3.60555 inches radial error, 2 inches left and 3 inches short. Save & import next opens the video picker.
- Results displays nine comparable board outcomes when its overlay is enabled, separate scores, uncertainty and explicit insufficient-data states. Long athlete names, references, inspector controls, and Results were checked at compact and normal sizes in light/dark appearance. Compact inspection prompted removal of a redundant picker label.
- Native research export copied all 22 analysis files byte-for-byte, including the HTML report. HTML was additionally inspected at wide and narrow browser widths.

Screenshots are saved under `/tmp/cornhole-second-pass/screenshots/`. This is representative workflow and layout coverage, not an exhaustive cross-product of every data state, OS version and display size. Missing-backend and scientific edge cases are covered by automated tests. Real participant testing and broader device testing remain outstanding.

## Reproduce checks

```sh
.venv/bin/python -m pytest
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer swift test --package-path app/CornholeBiomechanics
./build_app.sh
PYTHONPATH=python .venv/bin/python scripts/create_qa_project.py --output /tmp/new-cornhole-qa.cornholeproject
PYTHONPATH=python .venv/bin/python scripts/validate_sports2d_exports.py --analysis /path/to/sports2d-analysis
```

The fixture creator refuses to overwrite an existing project. Test media, logs and screenshots belong outside Git. Local test evidence for this development pass is under `/tmp/cornhole-second-pass/`.

## Scientific work requiring real data

Collect consented cornhole throws with the documented camera protocol. Review actual bag release and outcome labels, measure inter-rater/event reliability and test–retest repeatability, audit tracking against independent digitization/reference measurements, and report task-specific agreement. Similarity, consistency and tracking scores remain transparent pilot indices. No physical angle accuracy, causal coaching benefit or universal ideal technique is claimed.
