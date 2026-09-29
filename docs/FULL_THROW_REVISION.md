# Full-throw revision — 20 September 2026

## Repository audit and implementation plan

The native SwiftUI application owns a local schema-3 athlete/session/trial library. Python saves immutable pose and bag tracks, separate corrections, filtered kinematics, event candidates, normalized waveforms, manifests and HTML reports. Sports2D 0.8.34 supplies tracked image landmarks and upstream TRC/MOT diagnostics; custom Python computes authoritative projected angles, normalization, events and all bag measurements. Existing uncommitted pendulum/arm-motion work is retained.

Keep: Sports2D adapter, confidence masking, correction provenance, pose cache, full-resolution video, athlete/session persistence, frame review, raw exports and within-athlete comparisons.

Fix first: outcome defaulting to a miss; first-contact/final-rest fallback; missing landing event; release fits contaminated by smoothing across release/impact; launch fit quality gating; stale results presented as current; comparisons mixing contexts; unconstrained bag interpolation.

Implement: reviewed first-contact event and flight interval; image trajectory with explicit availability; reproducible calibration input; five primary results; endpoint-specific dispersion and personal descriptive ranges; advanced disclosure for body waveforms, passive models and research diagnostics. Keep outcome observations independent from pose coverage. No automatic scoring or universal optimal technique.

## Video inspection

26 player clips (9 Player 1, 6 Player 2, 11 Player 3; source folder originally spelled `Plyaer 3`, now `data/videos/Player 3`), all 1920×1080, approximately 59.94–59.97 fps, 1.59–12.89 s. Inventory and contact sheets are in `qa-artifacts/full-throw`. Full-motion samples 1, 10 and 16 show athlete, flight and board. Sample 1 includes more than one toss; isolate one throw temporally while keeping the full image. Background pedestrians can confuse person selection. The receiving board is shallow/foreshortened, bags are small and blurred, and framing shifts between samples within a clip. Camera-fixed physical kinematics cannot be assumed. No known-length object in the release plane has been established. Board coordinates cannot calibrate airborne points or athlete-plane speed.

Plan validation: analytic projectile trajectories, missing/occluded tracks, wrong calibration plane, unreviewed events, endpoint separation, unknown outcomes, independent real-video tracker review, native model decoding/build and UI review. Automatic tests establish implementation behavior, not experimental accuracy.

## Delivered behavior

- Three primary destinations: Athletes, Throws and Results. Reference comparisons, passive mechanics and setup remain under Research tools. Results presents five primary values, reviewed flight, separate contact/rest maps, within-athlete distributions and a focused movement–performance selector. Detailed body mechanics, indices and provenance use disclosure controls.
- Manual release confirmation and first-contact annotation are separate from automatic candidates and body motion end. A stationary or poorly fitted centroid does not receive launch direction/speed. Unknown scoring stays unknown through native persistence, Python, plots and reports.
- Release fits use directly supported unsmoothed bag observations and exclude impact/interpolation. The release centroid uses direct evidence rather than a filter extending through an impact. SI release speed requires explicit in-plane calibration and fixed side-camera confirmation. Raw image measurements remain qualified when camera motion is unconfirmed.
- Athlete profiles integrate optional measured upper-arm and forearm lengths. These do not create a false pixel-to-meter scale. Existing arm-mechanics work was preserved under advanced/research views.
- Schema-4 library writes preserve unknown scoring and back up older schema-2/3 indexes. Original participant clips were never changed. Development outputs are isolated in `qa-artifacts/full-throw`.

## Verification completed 21 September 2026

- Python: **122 passed**. Added independent analytical trajectory, 30 fps launch-curvature bias, wrong calibration plane, noisy/stationary track, event ordering, missing track, moving/oblique camera, endpoint separation, dispersion, personal-range exclusion and native unknown-score interoperability checks.
- Swift: **26 passed**, including unknown-outcome round trips, flight-gap decoding and schema-3 backup before schema-4 writes. The native target compiled successfully.
- Data-schema validator: development library valid, no missing-file warnings. `git diff --check`: clean.
- Actual Sports2D 0.8.34 full-frame runs: Player 1 clip 2, Player 2 clip 10, Player 3 clip 16. Each returned 100% usable required-pose frames under the configured heuristic. This is coverage, **not 100% landmark accuracy**. Automatic bounds include setup/recovery and require review.
- Player 2 bag experiment: manual seed at frame 198; inspected every tracker crop through frame 272. Bag identity stayed on the red bag. Reviewed separation approximately frame 198; first visibly flattened ground contact approximately frame 272 (about ±1 frame per event). Flight time is approximately 1.23 s at nominal 59.957 fps. Outcome observed as ground miss; no deck coordinate fabricated. SI speed, world range and apex are withheld because camera drift is visible and no release-plane scale is established. Launch values, when present, describe projected image motion only.
- HTML reports generated from the saved real-video examples. The initial native accessibility inspection confirmed simplified navigation. Further native visual interaction was blocked by the computer-use service error `Sky Computer Use native pipe closed before response`, including after reconnect/reset. A complete visual/interaction walkthrough is **not claimed**.

## Remaining experimental limitations

The system is a review-assisted 2D instrument, not automatic officiating or 3D motion capture. Bag centroids, pose geometry and release-window choices still need independent accuracy and inter-rater validation. Camera movement is declared by the reviewer, not automatically corrected. First contact and scoring are manual observations. Schematic board clicks are approximate and cannot localize ground misses; the current shallow-angle recordings do not establish calibrated lateral errors. Timing uses nominal constant-frame-rate assumptions. Personal ranges and correlations require repeated matched throws; the three development examples do not establish coaching relationships or improvement over time.

Next collection should use a tripod, a measured release-plane scale, higher shutter speed/frame rate, a calibrated receiving-board view, and repeated controlled throws per athlete. Use two independent event/point raters and test event-frame, scale and fit-window sensitivity before presenting empirical coaching conclusions. See [FULL_THROW_METHODS.md](FULL_THROW_METHODS.md) for equations, provenance, source references and a detailed experimental protocol.

## Installed release

The production build completed and was ad-hoc signed and signature-verified on 21 September 2026. `dist/Cornhole Biomechanics Lab.app` points to the updated installed bundle. Every packaged Python source matches the repository. The installed native executable has the release build’s Mach-O UUID; raw binary hashes differ because app-bundle signing updates the code signature. The build replaces only the generated app, leaving runtime and participant data separate.
