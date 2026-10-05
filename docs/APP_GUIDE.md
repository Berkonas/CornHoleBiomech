# Cornhole Biomechanics Lab — app guide

This Mac app helps you look at how an athlete throws a cornhole bag and how that movement relates to the result. It is a biomechanics course prototype that coaches can explore, not a validated coaching or clinical assessment system.

You work with athletes and their throws. The app saves your library automatically. You do not need to create a project every time you use it.

## Open the app

Double-click **Cornhole Biomechanics Lab.app** in `dist`. Or run `./run_app.sh` from this folder. The item in `dist` links to the runnable build in `~/Library/Application Support/Cornhole Biomechanics Lab/Builds`; keeping it there avoids iCloud Desktop metadata breaking its signature.

On a fresh Mac, run `./setup.sh` once, then `./build_app.sh`. Setup needs internet access for the Python dependencies and pose models. Analysis runs locally; your recordings are not uploaded by the app. This development build needs macOS and the local runtime installed by setup; it is not a standalone signed/notarized installer.

## Try it on the pilot clips

`~/Documents/Cornhole Pilot Library` holds Players 1–3 (26 clips from 17 September), already analyzed. Open it with **File → Choose Athlete Library**. Outcomes are not filled in: record Hole / Board / Miss for each throw with the buttons at the top of **Results**, and the scored-vs-missed analysis and the ACL stats appear. The source clips are in `data/videos`. To build a library from other folders, see `scripts/build_library.py`.

## A session in five steps

1. Choose **Add Athlete**. Use a participant code if you do not want a name in the data.
2. Choose **Import Throw** and select **all** of the session's videos at once. Each is copied into the library and analyzed automatically: body tracking, bag flight, release, swing. No clicking through frames is needed.
3. In **Throws**, a green **Bag ✓ auto** means the bag's flight was found and passed the projectile-physics checks. **Bag: review** means it was not sure. Open that throw, select the bag near release and track it, or mark release and contact in **Flight & scale**.
4. In **Results**, click **Hole · 3**, **Board · 1** or **Miss · 0** for each throw. Optionally use **Add outcome → Measure on board video** to place the landing in board inches.
5. Read the **Athlete summary** (result → what differed → next practice → physics check), the release **zones**, and the **scored vs missed** plots. Use **Compare → Trial vs trial** to explain two throws, and **Launch Explorer** to show the athlete how a body change moves the landing.

How the automatic tracking works, and how it did on the pilot clips, is in [AUTOMATIC_TRACKING.md](AUTOMATIC_TRACKING.md). Record with the [session protocol](RECORDING_PROTOCOL.md) for the best results.

Athlete profiles can be added, edited, or deleted from **Athletes**. Throw management is in **Throws → Manage**. Deletions need confirmation and use recoverable Trash staging. Removing an analysis keeps its video; deleting an athlete removes that profile and its managed data. Your external source recordings are not deleted.

## Two-camera takes (side + front)

The Fall 2026 collection films each **take** (the athlete claps, shows the take number, throws four bags)
with two phones: the side camera and a front camera on a tripod behind the board. Name the files
`Take_<n>_Side` and `Take_<n>_Front` (capitalisation does not matter) and keep one athlete's takes in one folder.

1. Select the athlete, then choose **Throw → Import Two-Camera Takes…** (⇧⌘T) and pick the folder.
2. The app pairs the files and checks which phone recorded each one (device, size, frame rate). A pair whose
   labels are swapped is used in its true roles and marked **Labels swapped**; takes already in the library are
   unticked. Choose the throwing side and the direction the board is in the side video.
3. **Import** prepares the takes one at a time: the two cameras are synchronised from the clap and the bag
   impacts, each throw is found and cut into a side clip and a front clip, and the front camera is calibrated
   from the board. The original videos are not changed. The throws then analyse one at a time (≈ 2 minutes each).
4. The throw list groups throws by take. Each report adds **Where it ended**: hole / board / off from the front
   camera, the miss in inches (short/long, left/right), the aim, and the frontal-plane body measures. The replay
   has **Side**, **Front**, **Both** (synchronised) and **Animation** views. **Animation** is a to-scale side
   view: the stick figure throws, the bag flies its measured path (a dotted arc where the camera lost it), lands
   at the measured first contact and slides to where it ended; the board, the floor and the release-to-board
   distance are drawn in metres. **From above** (in *Where it ended*) draws the lane to scale with the board
   2 ft × 4 ft along the throw: a strip with the release point, the aim line and the board, and an enlarged
   board with the landing, the slide and the rest point (or an arrow off the board for a miss) and a 6 in scale.
   A confident front-camera result is filled in automatically; check it against the video and change it if it
   is wrong.

How it works and how accurate it is: [METHODS_AND_MATH.md §5](METHODS_AND_MATH.md). For a batch of athletes from
the command line, use `scripts/add_takes_to_library.py`, then `scripts/analyze_library.py` (one athlete at a time).

## What changed in this version (board phase and personal green zone)

- **Where it ended.** Each throw report has a *Where it ended* card: where the bag landed on the board, how far it slid, and whether it stopped or dropped into the hole (including bags that hang on the lip and fall a moment later). It shows the slide physics (speed along the board, slow-down, effective friction μ) and a suggested result; **Use This Result** records it in one click. The flight chart marks *Landed* and *Stopped* / *Into the hole*, and the replay shows the slide.
- **Made throws get no corrections.** A hole is summarized as what worked (and a slide-in is named as part of the shot). Board bags and misses get signed advice from where the bag really stopped: "ended 9 in short … about 0.12 m/s faster".
- **Your distance, not 27 ft.** The app measures release point → front of the board in the videos (≈ 5.1–5.8 m in the tripod sessions) and uses it everywhere. The distance in Settings → Analysis is only a fallback.
- **Left/right is not measured** by the side camera; throws are assumed straight at the board. Record the board camera to measure left/right misses.
- **Personal green zone.** The athlete summary, each throw report and the Launch Lab show the athlete's own green zone (their release height, measured distance and measured slide) with a **best aim** target chosen for their consistency. In the Launch Lab choose **Use [athlete]'s green zone**. On the summary, click a throw on the map, or ▶ in the table, to watch it.
- **The summary uses every throw.** The consistency average pools every comparable analyzed throw and lists any left out with the reason. Throws analyzed with an older version are left out until re-analyzed: use **Re-analyze All** (the throws run one at a time).
- **One analysis at a time.** Imports and re-analyses go through a queue ("Throw 3 of 12"), and the engine refuses to start a second analysis on the same Mac until the first finishes, even from another copy of the app. Running several at once can use all the memory and freeze the computer.

## What the numbers mean

**Results** opens with an **Athlete summary** in three lines:
- **Result:** how many of this athlete's comparable throws scored.
- **What differed:** which release variable, if any, separated scored throws (1 or 3 points) from misses (0).
- **Next practice:** which typical scored throws to review.

The comparison uses a short, pre-chosen list of variables: release angle, speed, height and forward position, elbow angle and trunk lean at release, and throw duration. A difference is only reported when there are at least 5 throws in each group, the effect is large (Cliff's δ ≥ 0.474), and it exceeds that variable's measurement noise. The dot plots below the summary show every throw.

**This throw** shows the release angle with its tracking uncertainty, plus the release speed and release height. **Swing** shows the arm angle at release, peak arm swing speed, backswing, tempo (backswing ÷ forward-swing time) and the pendulum drive ratio. The drive ratio is measured arm speed ÷ what gravity alone would give; above 1 means the arm is actively driven.

**ACL stats** give points per round (PPR = 4 × points per bag) and In / On / Off %. **Release zones** show, for release speed, angle and height, the ranges a drag-free bag would need to land in the hole window (green), elsewhere on the board (yellow) or off it (red), around the athlete's own median release. The athlete's throws are marked by their real outcome, together with how often the model agreed. The **physics check** names the release variable whose spread, or off-centre aim, costs this athlete the most. An elbow included angle of 180° means straight in this camera projection. There are no composite 0–100 scores: individual measurements are shown instead.

Bag measurements require separate tracking and frame-by-frame identity review. Unreviewed bag points never contribute to release detection or bag-derived measurements. Release speed and height are reported in meters when a scale exists. The scale comes from either a meter stick held in the throwing plane, or the reviewed bag flight's own fall under gravity (fixed side camera only). See [the methods](FULL_THROW_METHODS.md).

These are not true 3D joint angles, joint forces, torque, muscle activation, or joint loading. Resemblance to a reference throw does not prove better technique. Associations with outcomes do not establish cause and effect. Missing estimates stay missing.

Record with the [session-day protocol](RECORDING_PROTOCOL.md): tripods, the athlete filling most of the frame, a second camera on the board, and a meter stick at the start. Trimming or cropping creates a silent derived clip without changing playback speed. The previous analysis is archived.

## Compare two throws

In **Compare → Trial vs trial**, choose two throws from the same athlete. You get:
- a one-sentence explanation;
- a table of release differences next to the athlete's usual throw-to-throw spread;
- both bag flights overlaid from their release points, on equal axis scales;
- synchronized body curves and video.

## Launch Explorer

**Body swing** mode animates a stick figure. Change the arm angle at release, backswing, swing speed, step, knee bend or body height, and watch the pendulum swing, release and flight update. The panel shows how far each change moves the landing. **Release values** mode is the direct angle/speed/height model.

**Coach Dashboard** summarizes one athlete: points, release profile and consistency, what differed on better throws (coaching priorities pass a five-part evidence gate; other differences are shown as observations, not advice), the body → release → flight → outcome evidence chain, and data trust. **Throw Replay** plays the measured throw over the video (measured path solid, drag-free model dashed, release / apex / first contact / rest pins) with every metric linked to its frame. See [COACHING_SYSTEM.md](COACHING_SYSTEM.md) and, for what has been checked, [LIGHT_VALIDATION.md](LIGHT_VALIDATION.md).

**Launch Explorer** is a drag-free 2D model of release angle, speed and height and where the bag first lands on a regulation board. It can start from the selected athlete's median measured release. It shows how far the landing moves per degree of angle or per 0.1 m/s of speed, and how much landing spread the athlete's own measured variability implies. It is a model, not measured data. The earlier 3D physics, pendulum and swing labs were removed; their notes are in `docs/archive`.

The **Cornhole Biomechanics Lab.app** shortcut on the Desktop opens the same installed build as `dist`; rebuilding updates both launchers.

## How trustworthy is the analysis?

[STRESS_TEST.md](STRESS_TEST.md) runs the analysis on simulated athletes whose true cause of misses is known.
- The outcome comparison makes at most about 5 % false claims.
- It needs about 20–40 throws to detect a real cause.
- The physics check names the true cause even with 10 throws.

For pros with tight releases, the app correctly says misses likely come from aim or bag behaviour, not body mechanics. Record at least 20 throws per athlete, preferably 30–40.

## Measuring tracking accuracy

`cornhole-biomech annotation-frames` exports blinded frames. Teammates mark them in `tools/annotator.html` (in the repository root). `cornhole-biomech validate-tracking` then reports landmark, elbow-angle, bag and release-frame error, plus agreement between raters. See [VALIDATION_PROTOCOL.md](VALIDATION_PROTOCOL.md). For the bag alone, `cornhole-biomech bag-annotation-frames` and `bag-benchmark` score each tracker stage per flight phase ([BAG_TRACKING_VALIDATION.md](BAG_TRACKING_VALIDATION.md)). The second-pass audit and plan are in [SECOND_PASS_AUDIT.md](SECOND_PASS_AUDIT.md).

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
| `data` | Your recordings (`data/videos`), bag-validation frames and spot-check sheets; not bundled or committed |
| `research` | Your local course PDFs and reference material; not bundled or committed |

Hidden `.git`, `.venv`, and `.build` items are development support files. They are not extra participant libraries.

## For the course project

The assignment requires real data you collect from real participants, a system demonstration, and evidence linking movement to performance. Supplied clips and synthetic tests help check the software, but they do not replace that study. You still need an approved collection protocol, consent as appropriate, repeated throws with observed outcomes, manual measurement checks, and a defensible discussion of limitations.

Read [the full-throw methods and equations](FULL_THROW_METHODS.md) and [revision/validation record](FULL_THROW_REVISION.md) for this revision. Read [the user guide](USER_GUIDE.md) for controls, [the biomechanics methods](BIOMECHANICS_METHODS.md) for definitions, and [the completion audit](COMPLETION_AUDIT.md) for what is implemented and what still requires research. [Verification](VERIFICATION.md) records what was actually tested. Older notes live in `docs/archive` and are historical, not current instructions.

For a development check, run `./verify.sh`. It runs Python tests, native Swift tests, library-schema checks, and a signed local release build. It does not certify scientific validity.
