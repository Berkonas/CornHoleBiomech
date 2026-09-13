# Cornhole Biomechanics Lab

This Mac app helps you look at how an athlete throws a cornhole bag and how that movement relates to the result. It is a biomechanics course prototype that coaches can explore, not a validated coaching or clinical assessment system.

You work with athletes and their throws. The app saves your library automatically. You do not need to create a project every time you use it.

## Open the app

Double-click **Cornhole Biomechanics Lab.app** in `dist`. Or run `./run_app.sh` from this folder. The item in `dist` links to the runnable build in `~/Library/Application Support/Cornhole Biomechanics Lab/Builds`; keeping it there avoids iCloud Desktop metadata breaking its signature.

On a fresh Mac, run `./setup.sh` once, then `./build_app.sh`. Setup needs internet access for the Python dependencies and pose models. Analysis runs locally; your recordings are not uploaded by the app. This development build needs macOS and the local runtime installed by setup; it is not a standalone signed/notarized installer.

## Your first throw

1. Choose **Add Athlete**. Use a participant code if you do not want a name in the data.
2. Select that athlete and choose **Import Throw**. The app copies the video into the athlete’s library folder.
3. Open **Trim / Crop / Rotate** if needed. Drag a crop rectangle, choose the first and last frames, or correct camera rotation. Keep the full throwing motion and bag visible. Your original stays untouched.
4. Choose **Analyze throw**. The default pose engine is Sports2D. First use can take longer while models load.
5. Review the video frame by frame. Check the throwing shoulder, elbow, wrist, hip, and release event. Correct bad points and reanalyze when prompted.
6. Record the observed outcome. Board clicks are approximate manual measurements; do not guess an outcome you cannot see.
7. Open **Results** for movement measurements, outcome, trajectories, consistency, and limitations. Use **Compare** only with suitable reference throws.

Athlete profiles can be added, edited, or deleted from **Athletes**. Throw management is in **Throws → Manage**. Deletions need confirmation and use recoverable Trash staging. Removing an analysis keeps its video; deleting an athlete removes that profile and its managed data. Your external source recordings are not deleted.

## What the numbers mean

The main measurements are projected **2D kinematics**: elbow included angle, trunk inclination, movement timing, wrist trajectory, shoulder movement, and shoulder-to-wrist radial distance. An elbow included angle of 180° means straight in this camera projection. Most distances are in arm lengths, not meters.

Bag measurements require separate tracking and frame-by-frame identity review. A tracker can confidently follow the wrong object. Unreviewed bag points do not contribute to release detection or bag-derived measurements. Physical speed in m/s requires a valid calibration in the athlete’s movement plane; a board-plane calibration cannot be reused for this.

These are not true 3D joint angles, joint forces, torque, muscle activation, or joint loading. A shoulder-to-bag distance is not a moment arm. Reference similarity tells you how much movements resemble one another; it does not prove better technique. Associations with outcomes do not establish cause and effect. Missing estimates stay missing.

Use a fixed, level side-view camera for the primary analysis. Keep the athlete and release region in view, use a clear background, and record at a known constant frame rate. Trimming or cropping creates a silent derived clip without stretching or changing nominal playback speed. Previous analysis is archived because its frame labels and coordinates no longer apply.

## Where things live

Your default athlete data lives in `~/Documents/Cornhole Biomechanics Lab Data`, separate from the development files. **File → Choose Athlete Library** opens an existing library. **File → Import Legacy .cornholeproject** copies an older study without changing its original. Schema-2 libraries open normally; the app keeps an index backup and saves new edits as schema 3 so older builds cannot misread prepared-video coordinates.

This folder contains:

| Folder | What it is for |
|---|---|
| `dist` | The app you open |
| `docs` | User guide, methods, validation, and development notes |
| `app` | Native Mac interface, icons, and local model assets |
| `python` | Scientific calculations and video-processing engine |
| `tests` | Automated scientific and integration tests |
| `scripts` | Setup, build, verification, and QA helpers |
| `research` | Your local course PDFs and reference material; not bundled or committed |

Hidden `.git`, `.venv`, and `.build` items are development support files. They are not extra participant libraries.

## For the course project

The assignment requires real data you collect from real participants, a system demonstration, and evidence linking movement to performance. Supplied clips and synthetic tests help check the software, but they do not replace that study. You still need an approved collection protocol, consent as appropriate, repeated throws with observed outcomes, manual measurement checks, and a defensible discussion of limitations.

Read [the user guide](docs/USER_GUIDE.md) for controls, [the biomechanics methods](docs/BIOMECHANICS_METHODS.md) for definitions, and [the completion audit](docs/COMPLETION_AUDIT.md) for what is implemented and what still requires research. [Verification](docs/VERIFICATION.md) records what was actually tested. Older notes live in `docs/archive` and are historical, not current instructions.

For a development check, run `./verify.sh`. It runs Python tests, native Swift tests, library-schema checks, and a signed local release build. It does not certify scientific validity.
