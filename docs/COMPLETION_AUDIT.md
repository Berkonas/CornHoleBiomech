# What is finished, and what is still a research task?

Updated 13 September 2026 for version 0.4.0. This checks the earlier 58-part brief and the follow-up about simpler athlete/video workflows. “Implemented” means the feature exists with the stated checks. It does not mean the measurement has been scientifically validated.

## What was already there

The previous pass had working Sports2D integration, an automatically restored athlete library, legacy import, human-readable storage, management/deletion controls, reference sets, pose corrections with Undo/Redo, bag tracking with review metadata, event editing, projected biomechanics, outcomes, comparison, consistency, relationship analysis, and local exports. It had 63 Python tests and 14 Swift tests. Real-video QA had exposed bag identity failures and substantial automatic release disagreement. That evidence is preserved in [the previous verification record](archive/VERIFICATION_0.3.md).

The main gaps were a missing crop/trim/rotation workflow, a toolbar and navigation that obscured athlete context, prototype scores leading the results, several newer features missing from native scatter plots, and unfinished current documentation/folder cleanup. Review gating also covered bag launch but did not fully protect other bag-derived measures.

## Software changes completed in this pass

| Brief area | Current status |
|---|---|
| 1–6: scope, audit, course premise, evidence | Existing scientific scope retained. Course handout reviewed. Canonical methods and source bibliography remain in `docs`. |
| 7: directory cleanup | Performed: app assets/models grouped, research material grouped, older root notes archived, README rewritten. No original participant video deleted. |
| 8–13: athlete library, persistence, migration, management | Implemented. Athlete-first launch; named toolbar actions; athlete-filtered Throws/Results/Compare; optional sessions now accessible on the athlete profile. Schema-2 index backup and schema-3 support protect prepared-video coordinates from older apps. |
| 14–15: references and reproducible architecture | Existing first-class global/athlete reference sets retained. Removing an assignment does not remove the source throw. Python remains a separate scientific engine behind the native app. |
| 16–19: coordinates, normalization, angles, events | Implemented with projected-2D terminology and manual event priority. Editing view/throwing hand/target direction marks analysis stale. |
| 20–23: bag tracking, release, velocity, acceleration | Implemented with explicit review and calibration gates. Unreviewed bag points now cannot affect radial distances, trajectories, automatic release, or zero-phase filtering. Acceleration remains exploratory. |
| 24–30: translation, relative motion, arm/radius/path measures, view and filtering | Implemented. Angular-velocity summary units corrected to degrees/s. Scientific assumptions are in the methods document. |
| 31–36: outcome, association, reference similarity, consistency, coaching insight | Implemented as descriptive/exploratory output with sample-size limits. Native scatter plots now decode new numeric features dynamically. No validated coaching prescription is claimed. |
| 37–40: results, synchronized inspection, review, quality | Measurements and observed outcome lead Results. Pilot scores are in a disclosure section. Compare leads with raw movement differences. Existing synchronized movement/video and quality panels retained. |
| 41–46: validation and sensitivity | Software regression tests and limited earlier real-video QA exist. Full criterion validity, multi-person tracking validation, and repeated independent annotation remain incomplete. |
| 47: real participant science | Not completed by software development. Requires recordings collected for the course, observed outcomes, appropriate permission/consent, repeated trials, and analysis of the actual study. |
| 48–53: documentation, value, restraint, precision, regression | README simplified; current folder map, user guide, methods, audit, and verification record updated. App remains focused on human movement rather than task scoring alone. |
| 54: complete native end-to-end checklist | Partial. Earlier native checks cover import/relaunch/analysis/correction/Undo/Redo/outcome/reference creation. This pass verified native crop/trim save, archived prior analysis, relaunch, and prepared-video playback. Final UI rerun was interrupted by the native automation connection failure; not all 30 actions were freshly exercised. |
| 55–58: release gates, quality, verification, handoff | Local build and automated checks are available through `./verify.sh`; signed build packaging was repaired. Remaining limitations and exact verification results are recorded separately. No production-readiness claim. |

## New video workflow

Preview a throw before analysis. In **Trim / Crop / Rotate**, scrub or play the original, mark a frame interval, drag a crop box or enter pixel bounds, and select a clockwise quarter-turn rotation. Save a separate silent analysis copy. The original is preserved, and the revision sidecar records the two hashes, geometry, frame rate, and original-to-derived frame mapping. Existing analysis/corrections are archived; new analysis is required. **Use original again** reverses the active input selection without overwriting the recording.

This is not a general video editor: it does not stabilize, stretch, change speed, edit audio, or combine multiple throws into one trial. Keeping those operations out protects the meaning of the measurements. Constant-frame-rate source recordings are required for defensible timing/derivative interpretation.

## What remains before calling this a validated coaching system

1. Collect the actual course dataset and observed performance outcomes; the supplied QA clips do not meet that requirement by themselves.
2. Measure pose and visible-release disagreement against independently reviewed annotations across participants, camera setups, and successful/failed throws.
3. Evaluate bag identity/occlusion explicitly. The earlier supplied clip does not contain enough reliable post-release bag visibility to support a launch estimate.
4. Repeat filtering and frame-rate sensitivity on representative recordings. The earlier downsampling check did not rerun the pose detector and is not a full capture-rate validation.
5. Run the complete native checklist after restoring UI automation, including multi-throw comparison and session/trial/athlete deletion confirmations in an isolated library. Automated tests cover core deletion/persistence behavior, but are not substitutes for every interface check.
6. Evaluate usefulness with athletes/coaches and prepare the course demonstration/report using actual participant findings. No coaching intervention benefit has been established.

The app is a local research prototype. A notarized standalone installer, cross-platform support, clinical use, 3D kinetics, and production deployment are outside this delivered build.
