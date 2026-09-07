# Stage 1 Implementation Plan

This plan is based on the Phase 0 review in `RESEARCH_NOTES.md`. The working product name is centralized as **Cornhole Biomechanics Lab** so it can be changed later.

## System boundary

Stage 1 is local and video-only. It has no accounts, cloud database, analytics, advertising, OpenAI calls, generated interpretation, IMUs, force plates, or EMG. A future explanation provider may consume compact numerical JSON, but no such provider is active.

## Architecture

```text
Native SwiftUI app
  Project/Athlete/Trial metadata (portable JSON)
  AVFoundation playback + overlays
  Correction/event/outcome editors
  Charts and board interaction
          |
          | structured JSON request + JSON-line progress
          v
Python package: cornhole_biomech
  video -> pose -> corrections -> gap handling/filtering
        -> events -> kinematics -> normalization
        -> reference comparison -> outcomes/statistics -> exports
          |
          v
Transparent trial analysis package
  manifest.json, pose_raw.json, corrections.json,
  keypoints.csv, kinematics.csv, results.json,
  annotated.mp4, selected PNG figures
```

Large frame-wise arrays live in trial files, not application database rows. Raw source video and raw model predictions are immutable. Every derived result identifies its input, model, configuration, corrections, reference IDs, package/app versions, and timestamp.

## Data model

- **Project:** stable ID, name, creation/update dates, schema version, athletes, references, analysis defaults.
- **Athlete:** stable ID, participant code/name, dominant hand, optional height/arm span/notes.
- **Trial:** stable ID, athlete ID, source video relative path, optional source URL/attribution, view, throwing side, target direction, throw type, outcome, events, pose/analysis paths, reference flag, analysis version.
- **Outcome:** target type/text, score category, optional intended/contact/rest board points, notes, recorded precision warning.
- **Point sample:** raw `(x, y, confidence)`, optional corrected `(x, y)`, correction timestamp/source, optional interpolation state.
- **Event:** automatic frame/confidence/method plus optional manual frame.
- **Analysis manifest:** app/package/backend/model versions and hashes, input hash, configuration, reference IDs, correction hash, timestamps, quality summary, warnings.

Schema migrations are explicit. Unknown fields are tolerated when possible; supported versions are never silently rewritten.

## Pose backends

1. **Primary:** RTMPose through RTMLib, using a COCO whole-body/body model and ONNX Runtime. Prefer the Apple MPS/CoreML/ONNX path only after a runtime self-test; CPU is always available.
2. **Fallback:** MediaPipe Pose Landmarker for a smaller installation and 33-landmark output.
3. **Interchange:** OpenPose-style JSON and Sports2D pixel TRC import. This lets Sports2D be run independently while keeping this application's correction and provenance model.
4. **Future/custom:** DeepLabCut only after the team creates and validates a cornhole-specific labeled dataset.

The setup script installs the tested core dependencies. Model downloads are explicit, checksummed, cached locally, and recorded. Reopening a trial reuses pose output when video/model/config hashes match.

## Scientific processing order

1. Read video metadata and validate frame rate/resolution/duration.
2. Estimate landmarks and confidence; cache raw results.
3. Apply non-destructive point corrections.
4. Mask low-confidence samples; interpolate only short internal gaps.
5. Filter coordinate trajectories using the recorded configuration.
6. Detect event candidates; apply separately stored manual event overrides.
7. Compute projected angles, relative trajectories, range, duration, and quality-gated velocities.
8. Normalize coordinates by robust segment length and movement time to 101 samples.
9. Compare compatible-view trials to one reference or reference set.
10. Attach outcome and compute approximate board errors.
11. Analyze within-athlete feature/outcome relationships only when enough complete trials exist.
12. Export deterministic machine-readable data, concise plots, and optional annotated video.

## Native app information architecture

The main `NavigationSplitView` routes are Overview, Athletes, Reference, Trials, Compare, and Results. The toolbar contains Import Video, Analyze, Add Outcome, Compare, and Export only when each action is valid. File/Edit/View/Trial/Help menus expose the same important commands and shortcuts.

Primary flow:

```text
Create/open project -> add athlete -> import video
-> label side/view/direction -> run local pose
-> inspect quality and overlay -> correct landmarks/events
-> attach outcome -> inspect movement
-> set reference or compare -> repeated-trial relationship analysis -> export
```

The About / Study Rationale area repeats the research questions and explains why movement-plus-outcome matters. Unavailable operations explain what is missing; no control presents unimplemented behavior as working.

## Correction and comparison interaction

- Video overlay shows required landmarks, skeleton, confidence state, selected projected angles, and correction badges.
- Paused-frame joints can be dragged. Undo/redo use the native undo manager; reset removes only the correction.
- Optional interpolation between two user corrections is previewed, labeled, and reversible.
- Events appear on a frame/time ruler with automatic and manual markers visually distinct.
- Comparison synchronizes by normalized movement percent while each video's actual frame/time remains visible.
- Ghost skeletons align at throwing shoulder, reflect target direction into a common forward axis, and scale by robust arm length. A caption states that translation/reflection/scale were applied.

## Similarity and performance presentation

Comparison panels show raw MAE/RMSE/peak/ROM/timing/path errors, then component scores and the overall reference-similarity index. Each value has an explanation containing its equation, units, reference IDs, tolerance, and limitation. Single-reference results carry the required prototype label.

Results keep three separate sections:

1. Reference similarity.
2. Within-athlete consistency.
3. Movement-versus-performance relationship.

Relationship plots show raw points, athlete ID context, `n`, an optional monotonic trend, Spearman rho, and a cautious interpretation. They never call an association causal.

## Quality gates

- Block biomechanical comparison across different camera-view labels.
- Warn below 60 fps; stronger warning below 30 fps or when metadata is unreliable.
- Warn when required throwing-arm points have excessive missingness, frame cropping is likely, confidence is poor, interpolation is extensive, or filter requirements fail.
- Do not report velocity when filtered coverage is inadequate.
- Do not report an association below the configured complete-pair threshold.
- Preserve export even when analysis is partial so problems can be audited.

## Verification and completion order

1. Phase 0 documents committed before application code.
2. Python geometry/correction/normalization tests.
3. Video-to-pose proof of concept on a short consented or rights-cleared clip.
4. Comparison, reference set, and outcome/statistics tests.
5. Swift data persistence and process-boundary tests.
6. Native playback/overlay/correction/event/outcome workflows.
7. Export and annotated-video verification.
8. Release build, resizing/Dark Mode/keyboard/VoiceOver review, and README usability pass.

Stage 1 is scientifically complete only after the team adds real participant trials and executes the validation protocol. Software completion cannot substitute for that data collection.
