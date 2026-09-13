# Verification record — version 0.4.0

Updated 13 September 2026. This records checks actually performed. It supersedes the [0.3 record](archive/VERIFICATION_0.3.md), which retains earlier real-video observations, filtering sensitivity, and limitations.

## Automated checks

`./verify.sh` runs the scientific tests, native model/persistence tests, a read-only schema scan, and the signed release build.

- Python: **85 tests passed**.
- Swift: **17 tests passed**, zero failures.
- Library schemas: the repository no longer contains participant-library manifests; that scan correctly reports none. Separate scans passed for the prepared-video QA library (schema 3) and nine-throw synthetic library (schema 1), with no missing-file warnings. Automated fixtures exercise versions 1, 2, and 3, path escape rejection, and future-version rejection.
- Release: Swift production compilation, ad-hoc signing, and strict signature verification pass. Build assembly/signing uses a temporary directory, then installs under `~/Library/Application Support/Cornhole Biomechanics Lab/Builds`. `dist/Cornhole Biomechanics Lab.app` is a link to that local build. Keeping the executable outside iCloud Desktop prevents Finder metadata from repeatedly invalidating its signature after installation.
- `git diff --check`: no whitespace errors.

SwiftPM reports that user-level caches are not writable under this sandbox. Those are cache warnings, not compilation/test failures. The app is a local development build, not a notarized independently distributable installer.

An unsandboxed verification run initially exposed an environment-dependent test assumption: macOS successfully followed a moved library’s security-scoped bookmark, while the “missing library” fixture expected recovery to fail. The fixture now explicitly removes its recovery bookmark before testing the unavailable-path case. This preserves bookmark recovery in the app and makes the missing-path test deterministic. The full suite was rerun afterward.

New regression coverage includes trim bounds, all four rotations, crop geometry, preservation of original bytes, frame mapping, collision/overwrite rejection, preparation provenance mismatch, angular-velocity units, schema handling, dynamic native relationship fields, prepared-video persistence, missing prepared copies, restoring the original, archiving corrections, deletion of managed revisions, and metadata-triggered reanalysis.

## Prepared real-video check

The earlier supplied-video QA copy was used; it is not claimed as a newly collected course-participant recording. In the native app, a disposable library copy at `/tmp/Cornhole-0.4-QA` was opened and a video revision was saved with:

| Property | Verified value |
|---|---|
| Original | 267 frames, 376 × 376 pixels, 60 fps |
| Retained source frames | 10 through 249 inclusive |
| Crop | x=8, y=0, width=360, height=376 pixels |
| Rotation | 0° |
| Prepared clip | 240 frames, 360 × 376 pixels, 60 fps, silent |
| Source mapping | source frame = prepared frame + 10 |
| Original SHA-256 | `3366ba600f1e59af179012ce398cb9470e583c62e98942162b2fe0ef879d30a8`, unchanged |

The original managed file remained intact. The old analysis/corrections were archived under the video revision; active analysis was cleared without adding another throw. After relaunch, the same athlete and prepared throw remained. Native playback of the prepared clip was visually confirmed. An initially blank pre-analysis player was found and fixed during this check.

On 13 September, a fresh Sports2D run on the prepared clip completed through annotated-video rendering. The exported manifest included matching prepared/original hashes and the preparation sidecar. Pose frame coverage was 100%; this is coverage, not anatomical accuracy. The automatic wrist-motion release candidate was prepared frame 160, corresponding to source frame 170. No manual release or bag track was silently copied into the new coordinates. The earlier source-video manual release observation was frame 176, so automatic timing still needs review. Angular-velocity summary metadata correctly reported `degrees/s`.

Outputs included raw pose, keypoints CSV, kinematics CSV, events, corrections, normalized data, results, provenance manifest, angle/wrist plots, and annotated MP4. The run is under `/tmp/cornhole-0.4-prepared-20260913`; temporary QA folders are not permanent participant storage.

## Multi-throw integration check

`scripts/create_qa_project.py` completed a separate nine-throw synthetic software workflow at `/tmp/cornhole-0.4-synthetic-20260913`. It produced nine analyses, seven two-reference comparisons, personal consistency, exploratory movement–outcome calculations, and a self-contained report. All inputs and outcomes are explicitly synthetic and cannot support course findings. Report generation was rerun after changing the report to lead with projected movement measurements rather than pilot indices.

The regenerated report was 766,965 bytes, with nine throws in consistency and nine relationship rows. A content assertion verified that projected movement measurements precede experimental indices. This is a generation/content check, not a fresh visual review of the final HTML report.

## Native interface verification boundary

Earlier native checks covered athlete creation/relaunch, video import/relaunch, full Sports2D analysis, point correction, Undo/Redo, event editing, reanalysis, outcome entry, board clicks, reference-set creation, and report generation. This pass additionally exercised prepared-video save, archived analysis, persistence, and playback.

The native UI-control connection failed on the final restart with `Sky Computer Use native pipe closed before response`. Reconnecting and resetting the session did not recover it. Therefore the latest session controls, complete Results layout, and all destructive confirmation flows were not freshly clicked through in this final build. Native model/filesystem tests cover their central data behavior; that is not equivalent to full UI verification. A complete 30-step native checklist remains open.

## Scientific limits

The earlier QA showed bag identity failures even with nominal 100% tracker coverage. The updated pipeline masks unreviewed bag points before filtering and excludes them from every bag-derived measurement and automatic bag/wrist release candidate. The earlier recording had inadequate reliable post-release visibility for a launch fit; missing launch velocity/angle/acceleration is the appropriate result.

No criterion-validity claim, cornhole-specific error bound, calibrated real-world bag speed, coaching benefit, clinical assessment, or final participant-study finding has been established. The earlier filter/frame-rate checks were limited software sensitivity experiments. See [the completion audit](COMPLETION_AUDIT.md) and [validation plan](VALIDATION_PLAN.md) for the remaining work.
