# Verification record

**Run date:** 10 September 2026  
**Branch:** `codex/second-pass-lab`  
**Pre-change checkpoint:** `774db93` (baseline code before the library/reliability pass: `f650ccc`)

This record distinguishes code checks from measurement validation. Passing checks below does not establish markerless-pose accuracy, bag-tracking validity, coaching benefit, or a causal movement–performance relationship.

## Status against the development brief

| Area | Status in this pass | Evidence or remaining boundary |
|---|---|---|
| Repository audit and safe checkpoint | Completed | Existing Swift/Python architecture retained; user-owned videos and legacy projects left untracked and unchanged. |
| Project organization | Completed without risky relocation | Canonical documentation map and generated-file rules are in `PROJECT_STRUCTURE.md`; source layout remained stable because moving it offered risk without user benefit. Stale generated copies were quarantined under `/tmp`, not deleted from user data. |
| Athlete-library launch and durable storage | Implemented and exercised | Visible managed library, Application Support index/bookmark, atomic schema-v2 project writes, missing-library recovery, stable UUIDs, reopen restoration. |
| Legacy project import/migration | Implemented and unit tested | Non-destructive copy, migration log, idempotency, future-schema rejection, legacy reference-set conversion. Three repository legacy manifests passed read-only schema validation. |
| Athlete/session/trial/reference management | Implemented | Edit, rename, reveal, relink, reanalyze, analysis-only deletion, reference assignment removal, and confirmed destructive operations. Disposable filesystem tests verify source preservation. |
| First-class reference sets | Implemented | Global/athlete scope, provenance, notes, multi-trial membership, selected-set comparison, and stale-assignment invalidation. Real-video comparison needs a second analyzed compatible throw. |
| Projected 2D biomechanics expansion | Implemented and synthetically tested | Elbow extension descriptors, global/relative wrist motion, shoulder translation, radius/angle sweep, path shape, bag geometry, explicit units/view scope. |
| Semi-automatic bag tracking | Implemented and real-video tested | Immutable automatic track, seed, separate corrections, interpolation provenance, overlay, QA command, and explicit review extent. Real sample exposed identity loss; launch is now suppressed unless review covers the full fit. |
| Outcome and board workflow | Implemented and exercised | Native 0/1/3 entry plus independent approximate target/contact/rest points and calculated error. |
| Consistency and performance relationships | Existing implementation retained and expanded with bag/features | Synthetic tests cover calculation and insufficiency states. The supplied sample has `n=1`, so real relationship estimates correctly remain unavailable. |
| Local report/export | Implemented and exercised | `report.html` and `insights.json` generated from stored data; research-folder export remains a native save-panel action. |
| One-command verification | Completed | `./verify.sh` runs Python, Swift, schema scan, and signed release build without modifying participant data. |

## Automated software verification

Final clean run of `./verify.sh`:

- **Python:** 63 tests passed.
- **Swift:** 14 tests passed.
- **Schema scan:** 3 legacy manifests valid; 0 retained missing-file warnings.
- **Release build:** succeeded; ad-hoc code signing succeeded; `dist/Cornhole Biomechanics Lab.app` created.

The test suite includes the requested angle cases, degenerate-vector behavior, coordinate reflection, scale/translation invariance, time normalization, unwrap behavior, Nyquist rejection, finite-gap handling, correction provenance, manual event priority, event ordering, path straightness, known velocity/polynomial motion, release divergence, radii, physical-unit calibration gate, incompatible views, reference comparison, missing/deleted files, migration, library restoration, bag review gating, and reference-set validity.

## Native end-to-end workflow actually exercised

An isolated library at `/tmp/Cornhole-Biomechanics-E2E-Library` was used so QA records did not become participant data.

1. Launched to Athlete Library and created athlete `QA-REFERENCE-01`.
2. Quit/reopened and observed the athlete still present.
3. Imported the first supplied MP4 through the native workflow. The managed-copy SHA-256 exactly matched the source.
4. Quit/reopened and observed the throw still present.
5. Ran the default Sports2D analysis to completion.
6. Inspected pose and event frames; manually set release to frame 176.
7. Entered a wrist correction at frame 176; Undo restored Automatic, Redo restored Manual; raw pose bytes did not change.
8. Reanalyzed from cached raw pose with correction/event provenance retained.
9. Seeded and reran bag tracking; the tracker lost bag identity after rapid motion even though its internal coverage was 100%.
10. Confirmed the updated pipeline suppresses launch through explicit `suppressed_unreviewed_track` status instead of presenting the false estimate.
11. Recorded a disposable outcome of 1 and approximate target/contact/rest board points; calculated first-contact radial error was 2.06 in.
12. Created a global coach-selected reference set, assigned the analyzed throw, and confirmed the Compare screen identified that selected set. Self-comparison was correctly excluded.
13. Generated a 402 KB self-contained `report.html` and a 33 KB `insights.json`.

Not every destructive UI action was executed on real-video data. Athlete/trial/analysis/reference deletion was instead verified using disposable Swift filesystem tests and injected Trash handling; this avoids risking the supplied files. Numerical reference comparison, multi-throw consistency, and movement–performance calculations were verified by synthetic/integration tests, but the real-video library had only one fully analyzed throw and therefore correctly disabled self-comparison and displayed “More trials needed.”

## Supplied-video inventory and immutability

Literal source directory (including the trailing space in `Reference `):

`Participant/Reference /Cornhole Study.cornholeproject/videos/`

| File suffix | Frames | Duration | FPS | Resolution | SHA-256 |
|---|---:|---:|---:|---:|---|
| base | 267 | 4.450 s | 60 | 376×376 | `3366ba600f1e59af179012ce398cb9470e583c62e98942162b2fe0ef879d30a8` |
| `(1)` | 255 | 4.250 s | 60 | 376×376 | `67fc8fbe2e680ed0eab98b54f07c07bdcc4a56f68cf110f78d11762eb05d25c5` |
| `(2)` | 234 | 3.900 s | 60 | 376×376 | `ea176e206570ecca5308443d84f7bcfbde8672e030591cb84c551ec8b9415c4c` |
| `(3)` | 216 | 3.600 s | 60 | 376×376 | `734be5afa4a10de85da5d625cadc464e5928515faa0360681fff7fb208bea2fe` |
| `(4)` | 262 | 4.367 s | 60 | 376×376 | `1cf907c41ad6c053cc22994e9d9edc7d5af62e0c7a5572af3807afdbc37da536` |

All five files passed metadata/readability checks. The base file received the full native Sports2D, correction, event, outcome, report, bag-tracking, filter, and frame-rate QA workflow. Originals were not modified. These files are treated only as supplied software-QA material; provenance does not establish course-participant consent or eligibility.

## Real-video pose result

Default 6 Hz run on the base file used Sports2D 0.8.34, `body_with_feet-balanced`, 267 frames at 60 fps and 376×376 pixels. Raw pose coverage was 100%; missing samples were 1.02%; mean model confidence was 0.754; the transparent pilot tracking index was 91.54/100. Two left-wrist finite runs at frames 222–230 were too short for zero-phase filtering and remained unfiltered with warnings.

With manual release at frame 176, selected projected results were:

- elbow included angle: 157.4°; extension deficit: 22.6°;
- trunk inclination: 29.5°;
- shoulder net translation: 0.367 arm lengths;
- shoulder-to-wrist radius: 1.051 arm lengths;
- forward-swing radius SD: 0.018 arm lengths;
- forward-swing wrist-path straightness: 0.787;
- movement duration: 3.18 s; release timing: 0.539 of the analyzed movement cycle.

A two-frame, two-pass visual QA annotation included throwing shoulder, elbow, wrist, hip, and bag. Against the pose model, the four body landmarks averaged 10.09 px or 0.108 arm lengths of disagreement. Per-landmark means were shoulder 8.34 px, elbow 5.43 px, wrist 13.00 px, and hip 13.59 px. Repeat annotations differed by roughly 1.2–1.8 px for body landmarks and 0.96 px for the bag. These hand-read image centers are approximate QA observations—not anatomical ground truth, a criterion-validity result, or a cornhole error threshold.

## Bag-tracking and release QA

Six frames were manually labeled for the base video (150, 156, 162, 168, 174, 177). Three late frames were explicitly marked as automatic identity failures.

| Tracker | Missing-label-frame rate | Mean error | Median error | RMSE | Maximum | Reviewed identity failures |
|---|---:|---:|---:|---:|---:|---|
| OpenCV CSRT | 0% | 72.04 px | 26.37 px | 111.86 px | 218.66 px | 168, 174, 177 |
| Template matching | 0% | 28.79 px | 17.31 px | 43.19 px | 85.29 px | 168, 174, 177 |

Using a provisional 70 px arm-length scale only for normalized QA, mean error was 1.03 arm lengths for CSRT and 0.41 for template matching. Neither tracker retained bag identity sufficiently for an interpretable launch fit. CSRT was not silently replaced after explicit selection; `auto` chose CSRT because it was available. One video is insufficient evidence to change the global default.

The wrist-motion automatic release candidate was frame 170; manual visual release was frame 176: 6 frames or 100 ms earlier at 60 fps. The failed bag/wrist track proposed frame 167, 9 frames or 150 ms earlier, and is not treated as valid evidence. The bag was only clearly visible for about one frame after release, whereas the configured fit required review through frame 184. The final launch velocity, angle, and acceleration therefore remain missing. This is the intended safe behavior.

## Filter sensitivity on the real pose track

The same raw pose, correction, manual release, and finite-gap rules were analyzed at 4, 6, and 8 Hz. Values are descriptive and rounded here; complete settings remain in each manifest.

| Cutoff | Auto release | Elbow at manual release | Trunk at release | Peak elbow angular speed | Forward wrist straightness | Shoulder net translation |
|---:|---:|---:|---:|---:|---:|---:|
| 4 Hz | 170 | 157.73° | 29.29° | 306.78°/s | 0.7930 | 0.3573 arm lengths |
| 6 Hz | 170 | 157.39° | 29.53° | 313.86°/s | 0.7869 | 0.3671 arm lengths |
| 8 Hz | 171 | 157.21° | 29.69° | 327.52°/s | 0.7857 | 0.3520 arm lengths |

Release-frame position metrics were comparatively stable across these pilot cutoffs; the derivative was more sensitive, as expected. This does not select a universally correct cutoff.

## Processing frame-rate sensitivity

No supplied recording exceeded 60 fps. For a limited processing-only check, the saved pose series and video were subsampled from 60 to 30 fps without re-running the detector. The automatic release time remained 2.833 s (frame 170 vs 85); manual release remained 2.933 s (176 vs 88). Elbow at release changed 157.08°→157.29°, trunk 29.53°→29.62°, path straightness 0.7851→0.7842, peak elbow angular speed 313.86→314.28°/s, and shoulder translation 0.3671→0.3380 arm lengths. This checks resampling/filter behavior only; it does not measure the effect of frame rate on blur, exposure, pose inference, or release visibility.

## Not yet scientifically validated

- No rights/provenance evidence establishes the supplied files as course participant data.
- No synchronized marker-based motion capture or calibrated multi-camera criterion reference was available.
- The two-frame visual pose check is too small and approximate for criterion validity.
- Bag tracking failed on the tested rapid post-release motion and requires per-frame correction or better recording conditions.
- No valid athlete-plane spatial calibration was available, so physical m/s is not reported.
- No repeated, consented real-participant dataset with outcomes was available for measurement repeatability or movement–performance relationships.
- No recording above 60 fps was available for a true acquisition frame-rate study.
- No evidence establishes reference similarity as technique quality or any metric as causal for performance.

Follow `VALIDATION_PLAN.md` before making task-validity, coaching-effectiveness, or participant-science claims.
