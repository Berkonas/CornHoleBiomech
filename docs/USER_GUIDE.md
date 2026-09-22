> **Full-throw revision:** Use Athletes → Throws → Results. Keep the full frame and one throw per clip. In Throws, confirm release, then open **Flight & scale** at first contact; review bag identity and reanalyze. Leave unseen outcomes unknown. Results starts with five primary measurements, flight and board views, then personal distributions. Research tools, passive models and raw diagnostics are collapsed. See [current methods](FULL_THROW_METHODS.md).

# User guide

Cornhole Biomechanics Lab is organized around athletes, throws, references, sessions, and results. It manages the underlying folders automatically while keeping scientific data visible in Finder.

## 1. Add an athlete

On first launch, the app creates a visible athlete library in `~/Documents/Cornhole Biomechanics Lab Data`. Choose **Add Athlete**, enter a participant code or name and throwing hand, and optionally add height, arm span, and notes. These anthropometric fields are context; projected arm length is calculated from the video for Stage 1 normalization.

The app restores this library at the next launch. To use another location or import an old `.cornholeproject`, use the File menu. Legacy import copies supported records and files into the active library and writes `migration-log.json`; it does not modify the old project. Command-N adds an athlete; creating a separate library is an occasional file-management action.

## 2. Import videos

Select an athlete and choose **Import Throw**. Confirm the camera view, throwing side, target direction, and optional session. The app copies the video into that athlete’s `throws` folder and leaves the selected source untouched.

Use a fixed side-view tripod setup for the primary Stage 1 measurements. Keep the throwing arm, shoulders, and hips visible. If a managed video is moved outside the app, the throw remains listed as **Missing video**; choose **Locate / Relink Video**.

## 3. Run analysis

Before analysis, **Trim / Crop / Rotate** lets you scrub the original video, mark the first and last frames, drag a crop rectangle, enter precise pixel bounds, and rotate in 90° steps. Bounds are original decoded pixels; crop happens before rotation. Keep the whole throw and the bag’s initial flight visible. Use the saved clip’s preview to confirm the framing before analysis.

The original is never overwritten. Each adjustment creates a separate silent constant-frame-rate copy and a sidecar containing hashes and the source-frame mapping. Earlier analysis/corrections are archived with that revision. The app clears active analysis and comparison results because their coordinates and frame indices no longer apply. **Use original again** returns to the untouched recording and also requires fresh analysis. Reconfirm throwing side and target direction after rotation. Do not use variable-frame-rate screen recordings to make precise timing or derivative claims.

Select the throw and choose **Analyze Trial**. Sports2D is the default pose engine. Progress and errors appear in the app. Analysis is local, and successful output is saved under the athlete’s `analyses` folder.

Advanced settings expose pose backend, confidence threshold, maximum interpolation gap, and low-pass filter. Change them as a documented analysis decision, not to make one outcome look better.

## 4. Review body and bag tracking

In **Throws → Inspect & Correct**:

- play, pause, seek, or step one frame;
- drag a body point or enter exact analysis-video pixel coordinates (prepared-clip coordinates after a crop/rotation);
- reset a point to the automatic estimate;
- add manual anchors and explicitly interpolate a short gap;
- use Undo/Redo for body-point changes;
- mark motion start, backswing, forward swing, release, follow-through, or motion end at the displayed frame.

Automatic body coordinates remain in `pose_raw.json`; edits remain in `corrections.json`.

Bag tracking is optional. Pause on a frame where the bag is clear, choose **Bag tracking → Seed tracker rectangle**, and enter a tight original-pixel rectangle around it. Re-run analysis, then review the cyan centroid frame by frame. A yellow point is manually corrected; purple is reviewed interpolation. Use **Correct centroid**, **Reset centroid to automatic**, or **Interpolate between reviewed bag points**. After checking the full launch-fit interval, choose **Mark reviewed through frame**, then reanalyze. If the bag leaves view or the tracker changes identity before the required frame, leave launch results suppressed—do not approve the interval merely to obtain a number. The automatic track remains in `bag_raw.json`; edits and review extent remain in `bag_corrections.json`.

A tracker can follow the wrong object despite a high appearance score. Treat the overlay as a measurement requiring review, especially at hand overlap, blur, release, and image exit.

## 5. Record the outcome

Choose **Add / edit outcome**. Record the official single-bag value:

- 3: through the hole;
- 1: remains on the board;
- 0: otherwise.

Optionally click the intended target, first-contact point, and final resting point on the board. These observations are approximate. Contact and rest remain separate.

## 6. Create and use references

Open **References** and create either:

- a global coach-selected reference set; or
- an athlete-specific reference/personal baseline.

Assign one or several compatible throws and record provenance/selection notes. An external reference video is imported like any other throw. Removing an assignment or deleting a reference set never deletes its source throw.

In **Compare**, choose a test throw and compatible references. Side, front/rear, and other views are not silently mixed. Raw waveform/path differences are the primary results; the optional 0–100 summary means resemblance to that selected reference—not technique quality or performance.

## 7. Interpret results

Open **Results** after tracking review. Read in this order:

1. outcome and actual sample size;
2. measurement warnings and tracking quality;
3. projected biomechanics and optional bag launch quantities;
4. personal consistency across comparable throws;
5. raw movement–performance scatter and exploratory association;
6. reference differences and transparent similarity components.

Do not interpret missing values as zero. Bag speed is shown in pixels/s and arm lengths/s unless an explicit, valid athlete-plane calibration permits m/s. Correlation does not show causation, and a stable or straighter arm path is not automatically better.

## 8. Sessions and repeated throws

Sessions group repeated throws collected with common setup details. Use them to compare current movement with an athlete’s historical baseline. For useful within-athlete interpretation, collect repeated throws under a consistent camera protocol and record all outcomes rather than selecting only successful attempts.

## 9. Export and data management

Choose **Open local report** for the readable HTML result or **Export research package** for the full transparent analysis folder. **Reveal in Finder** is available for athletes and videos.

The Manage menu can edit/relink a throw, rerun analysis, delete only derived analysis, or delete the throw. Deleting analysis preserves the source video, throw record, and reference assignments. Athlete deletion reports the affected session/video/analysis counts and asks for confirmation. Managed deletions go to macOS Trash when practical.

## 10. What the app does not establish

This is a projected 2D research prototype. It does not measure true 3D joint rotations, force, torque, muscle activity, injury risk, or universally correct form. Software tests verify calculations and file behavior; task-specific pose accuracy, bag accuracy, repeatability, and performance validity require the protocol in [VALIDATION_PLAN.md](VALIDATION_PLAN.md).

For equations and units, read [BIOMECHANICS_METHODS.md](BIOMECHANICS_METHODS.md). For checks actually completed, read [VERIFICATION.md](VERIFICATION.md).

## Elbow motion

Reanalyze old recordings to fill the **Results → Advanced → Elbow motion during the forward swing** panel. It covers forward swing through release and needs a side view and enough tracking coverage. Mean flexion describes how bent the elbow is. Excursion and SD describe how much it changes during the swing. None of these is a skill score.

## Launch Explorer

Open **Launch Explorer** in the sidebar. Move the release angle, speed, height and distance-to-board sliders to see where a drag-free bag first lands on a regulation board. **Find speed that reaches the hole** solves for the speed. **Start from … median release** loads the selected athlete's measured median.

The sensitivity table shows how far the landing moves per 1°, per 0.1 m/s and per 5 cm. It also multiplies each sensitivity by the athlete's measured SD, to show which inconsistency costs the most distance under this model. These are model values, not athlete trials.

### Simpler review workflow

In **Results**, the athlete summary (result, what differed, next practice) comes first. Then come this throw's release values, the scored-vs-missed plots, the flight and the board. Movement relationships, body mechanics and provenance expand only when needed. In **Compare → Trial vs trial**, two throws from one athlete are explained side by side.
