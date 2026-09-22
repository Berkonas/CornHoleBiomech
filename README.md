# Cornhole Biomechanics Lab

This Mac app helps you look at how an athlete throws a cornhole bag and how that movement relates to the result. It is a biomechanics course prototype that coaches can explore, not a validated coaching or clinical assessment system.

You work with athletes and their throws. The app saves your library automatically. You do not need to create a project every time you use it.

## Open the app

Double-click **Cornhole Biomechanics Lab.app** in `dist`. Or run `./run_app.sh` from this folder. The item in `dist` links to the runnable build in `~/Library/Application Support/Cornhole Biomechanics Lab/Builds`; keeping it there avoids iCloud Desktop metadata breaking its signature.

On a fresh Mac, run `./setup.sh` once, then `./build_app.sh`. Setup needs internet access for the Python dependencies and pose models. Analysis runs locally; your recordings are not uploaded by the app. This development build needs macOS and the local runtime installed by setup; it is not a standalone signed/notarized installer.

## Your first throw

1. Choose **Add Athlete**. Use a participant code if you do not want a name in the data.
2. Select that athlete and choose **Import Throw**. The app copies the video into the athlete’s library folder.
3. Trim to **one throw**, keeping the athlete, full flight and receiving board visible. Prefer temporal trimming; spatial cropping can remove the evidence needed for flight analysis. Your original stays untouched.
4. Choose **Analyze throw**. The default pose engine is Sports2D. First use can take longer while models load.
5. Review the video frame by frame. Check the throwing shoulder, elbow, wrist, hip, and release event. Correct bad points and reanalyze when prompted.
6. Use **Flight & scale** to confirm release and first board/ground contact. Review bag identity through the contact frame, then reanalyze. Calibration is optional and requires an independently measured length in the release plane.
7. Record the observed 0/1/3 bag value or leave it **unknown**. Approximate board contact and final rest stay separate; never assign board coordinates to a ground miss.
8. Open **Results** for the athlete summary, this throw's release, scored-vs-missed plots, flight and board. Use **Compare** to explain two throws.

Athlete profiles can be added, edited, or deleted from **Athletes**. Throw management is in **Throws → Manage**. Deletions need confirmation and use recoverable Trash staging. Removing an analysis keeps its video; deleting an athlete removes that profile and its managed data. Your external source recordings are not deleted.

## What the numbers mean

**Results** opens with an **Athlete summary** in three lines:
- **Result:** how many of this athlete's comparable throws scored.
- **What differed:** which release variable, if any, separated scored throws (1 or 3 points) from misses (0).
- **Next practice:** which typical scored throws to review.

The comparison uses a short, pre-chosen list of variables: release angle, speed, height and forward position, elbow angle and trunk lean at release, and throw duration. A difference is only reported when there are at least 5 throws in each group, the effect is large (Cliff's δ ≥ 0.474), and it exceeds that variable's measurement noise. The dot plots below the summary show every throw.

**This throw** shows the release angle with its tracking uncertainty, plus the release speed and release height. An elbow included angle of 180° means straight in this camera projection. There are no composite 0–100 scores: individual measurements are shown instead.

Bag measurements require separate tracking and frame-by-frame identity review. Unreviewed bag points never contribute to release detection or bag-derived measurements. Release speed and height are reported in meters when a scale exists. The scale comes from either a meter stick held in the throwing plane, or the reviewed bag flight's own fall under gravity (fixed side camera only). See [the methods](docs/FULL_THROW_METHODS.md).

These are not true 3D joint angles, joint forces, torque, muscle activation, or joint loading. Resemblance to a reference throw does not prove better technique. Associations with outcomes do not establish cause and effect. Missing estimates stay missing.

Record with the [session-day protocol](docs/RECORDING_PROTOCOL.md): tripods, the athlete filling most of the frame, a second camera on the board, and a meter stick at the start. Trimming or cropping creates a silent derived clip without changing playback speed. The previous analysis is archived.

## Compare two throws

In **Compare → Trial vs trial**, choose two throws from the same athlete. You get:
- a one-sentence explanation;
- a table of release differences next to the athlete's usual throw-to-throw spread;
- both bag flights overlaid from their release points, on equal axis scales;
- synchronized body curves and video.

## Launch Explorer

**Launch Explorer** is a drag-free 2D model of release angle, speed and height and where the bag first lands on a regulation board. It can start from the selected athlete's median measured release. It shows how far the landing moves per degree of angle or per 0.1 m/s of speed, and how much landing spread the athlete's own measured variability implies. It is a model, not measured data. The earlier 3D physics, pendulum and swing labs were removed; their notes are in `docs/archive`.

The **Cornhole Biomechanics Lab.app** shortcut on the Desktop opens the same installed build as `dist`; rebuilding updates both launchers.

## Measuring tracking accuracy

`cornhole-biomech annotation-frames` exports blinded frames. Teammates mark them in `tools/annotator.html`. `cornhole-biomech validate-tracking` then reports landmark, elbow-angle, bag and release-frame error, plus agreement between raters. See [VALIDATION_PROTOCOL.md](docs/VALIDATION_PROTOCOL.md).

## Where things live

Your default athlete data lives in `~/Documents/Cornhole Biomechanics Lab Data`, separate from the development files. **File → Choose Athlete Library** opens an existing library. **File → Import Legacy .cornholeproject** copies an older study without changing its original. Schema-2/3 libraries open normally. Their indexes are backed up before new edits save as schema 4, which supports unknown outcomes without allowing older builds to misread them as misses. Historical zeros are preserved and should be audited against video.

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

Read [the full-throw methods and equations](docs/FULL_THROW_METHODS.md) and [revision/validation record](docs/FULL_THROW_REVISION.md) for this revision. Read [the user guide](docs/USER_GUIDE.md) for controls, [the biomechanics methods](docs/BIOMECHANICS_METHODS.md) for definitions, and [the completion audit](docs/COMPLETION_AUDIT.md) for what is implemented and what still requires research. [Verification](docs/VERIFICATION.md) records what was actually tested. Older notes live in `docs/archive` and are historical, not current instructions.

For a development check, run `./verify.sh`. It runs Python tests, native Swift tests, library-schema checks, and a signed local release build. It does not certify scientific validity.
