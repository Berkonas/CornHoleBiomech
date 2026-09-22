# Version 0.6 verification — 22 September 2026

## Delivered interface

The main path is Athletes → Throws → Results, with Physics Lab available independently. Results keeps observed outcome, first-contact error, projected release angle/speed and elbow angle visible. Metric explanations, relationships, advanced mechanics and provenance expand on demand. Review video returns directly to the throw workspace.

Physics Lab opens with the animated two-link swing. The initial controls are release phase, duration and direction; detailed body geometry, stance, handedness and joint endpoints are expandable. Direct-release examples appear only in direct mode. Bag mass and board incline are visible together. Parameter experiments and equations expand on demand. Inspect release pauses at the actual computed detachment time. Practice hides both trajectory predictions and parameter-experiment outcomes until completion.

The animation uses continuous analytic joint positions and derivatives, exact geometric release conditions, interpolated numerical flight samples and elapsed-time playback. This is smooth prescribed kinematics, not a validated human motor-control or deformable-bag simulation. See PHYSICS_LAB.md and PERFORMANCE_ZONES.md for formulas, assumptions and evidence rules.

## Automated and packaged verification

- 47 Swift tests passed, including independently checked swing derivatives, release continuity, inverse dynamics, gravity moments, vacuum flight, drag, impacts, sliding and hole/edge events.
- 130 Python tests passed, including analysis, full-throw review, personal evidence gates and native-compatible output fields.
- Schema validation passed for the existing schema-4 example library.
- Production build completed; the installed Desktop target reports 0.6.0 and passes strict deep code-signature verification.
- All 27 packaged Python source modules match the repository.
- The installed Python engine reanalyzed the supplied Player 2 clip using its cached Sports2D raw pose and reviewed bag/event inputs. This is a reanalysis regression, not a fresh pose-model inference benchmark. Outputs are in qa-artifacts/final-polish-regression, including the annotated video, CSVs and numerical results.
- Release angle 48.0789953929525°, normalized speed 13.800589095454958 arm lengths/s, and elbow angle 155.40513026047765° exactly match the previous results. Physical speed remains unavailable without valid calibration. Reviewed flight output and manual inputs match exactly.
- Packaged insights/report generation succeeded for the example library. The observed score remains 0, results are not stale, all five personal metric zones remain neutral because the reviewed evidence requirements are not met, and the HTML report is generated locally.

## Native review and its limits

Before the final presentation-only build, native review confirmed the actual video/joint overlay, correction and event controls, Results values above, 1.23 s reviewed flight time, and complete bag-path display. Earlier native checks exercised swing playback, pause/resume/scrubbing, body height, handedness, stance display, force equations, direct-release comparisons and four-bag scoring/replay behavior.

The final layout changes compile and are installed. A final native screenshot recheck was blocked by repeated crashes of SkyComputerUseService while inspecting the relaunched application; macOS diagnostic reports identify that service, not a new CornholeBiomechanics crash. The Desktop shortcut was located and opened through Finder, but the service could not inspect the resulting window. Do not describe this as a completed final visual regression pass.

The selected library is the existing qa-artifacts/full-throw example library; the previously selected temporary library was missing. Its prior location selection is backed up in qa-artifacts/swing-qa-library-location.before.json. A numerical/input snapshot is in qa-artifacts/final-polish-backup. No simulation results were written as athlete throws.
