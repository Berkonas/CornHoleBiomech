# Cornhole Biomechanics Lab — app guide

This Mac app helps you look at how an athlete throws a cornhole bag and how that movement relates to the result. It is a biomechanics course prototype that coaches can explore, not a validated coaching or clinical assessment system.

You work with athletes and their throws. The app saves your library automatically. You do not need to create a project every time you use it.

## Open the app

Double-click **Cornhole Biomechanics Lab.app** in `dist`. Or run `./run_app.sh` from this folder. The runnable build is stored directly in this checkout’s `dist/`; the Desktop icon points to it. Keep the checkout in `~/GitHub/CornHoleBiomech`, outside iCloud Desktop.

On a fresh Mac, run `./setup.sh` once, then `./build_app.sh`. Setup needs internet access for the Python dependencies and pose models. Analysis runs locally; your recordings are not uploaded by the app. This development build needs macOS and the local runtime installed by setup; it is not a standalone signed/notarized installer.

## Try it on the pilot clips

`data/libraries/Cornhole Pilot Library` holds Players 1–3 (26 clips from 17 September), already analyzed. Open it with **File → Choose Athlete Library**. Outcomes are not filled in: record Hole / Board / Miss for each throw with the buttons at the top of **Results**, and the scored-vs-missed analysis and the ACL stats appear. The source clips are in `data/videos`. To build a library from other folders, see `scripts/build_library.py`.

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

### Import & analyse

1. Choose **Throw → Import Takes…** (⇧⌘T) or **Import** in the throw list, or drop the folder on the throw
   list. The import window also takes a dropped folder, or **Choose Folder…**.
2. The app pairs the files and checks which phone recorded each one (device, size, frame rate). A pair whose
   labels are swapped is used in its true roles and marked **Labels swapped**; takes already in the library are
   unticked.
3. Confirm the **athlete**, the **throwing side** and the **board direction** in the side video. Both are
   remembered for that athlete (saved with the athlete in the library) and filled in next time.
4. Click **Import & Analyse**. Analysis always follows import; there is no separate step.

Each take is prepared in turn (the two cameras are synchronised from the clap and the bag impacts, each throw
is cut into a side clip and a front clip, the original videos are not changed), the front camera's field of
view is pooled over the takes, and then every throw is analysed, **one at a time**.

**The queue panel** at the bottom of the window shows where the work is, for example
"Take 3/6 · Throw 2/4 · Bag tracking (5/10) · about 6 min left". The time left is the median of the last ten
throws this Mac finished (about 2 minutes per throw before any has finished). **Pause** lets the current throw
finish and then waits; **Resume** carries on; **Cancel All** stops the queue (throws already analysed keep their
results). A throw or take that fails does not stop the others: it is listed under **needs attention** in the
panel instead of interrupting you. You can keep working while the queue runs, and import more takes: they join
the end of the queue.

**After a restart.** The queue is saved in the library (`analysis-queue.json`). If the app is quit or the Mac
restarts, the queue carries on two seconds after the library opens again (a paused queue stays paused). The
throw that was running starts again from the beginning. A take that was being prepared is prepared again; its
half-finished folder is left in the athlete's `takes` folder and can be deleted.

### The Take screen

The take is the main view after import: the app opens the first imported take, and its four bags fill in as
they are analysed. Select a take's first row (**Take 3**, with its points and in/on/off) in the throw list to
open it again; the arrows at the top go to the previous or next take.

- **Points and counts**: for example 6/12 points and "1 in · 3 on · 0 off" from the recorded results.
- **The take video**: the four throws one after another as a single video, side camera on the left and front
  camera on the right, in step (synchronised from the sound). The scrubber has one segment per throw with a red
  tick at each release; click a throw's number to jump to its release, or drag along the bar.
- **From above**: the board to scale with the four bags numbered. A hollow ring is where the bag landed, the line
  is the slide, and the filled square (a 6 in bag) is where it stopped; a bag that stopped further off the board
  is an arrow at the edge, and bags in the hole are numbered around it. The cross is the group centre (the mean
  of where the bags stopped), described as for example "Group 6 in right, 4 in short". Four bags are a snapshot:
  the screen shows the range, never a standard deviation. While the video plays, the bag being played is
  highlighted.
- **Four throw cards**: the result (with **auto** when the app recorded it from the front camera), the first
  sentence of the throw's explanation, and **Needs your eye** with **In / On / Off** buttons when the cameras were
  not sure. Click a card to open the throw report. While a throw waits or is analysed, its card says so.
- **Release, bag by bag**: release speed, angle and heading (to 0.5°) for bags 1–4 against this athlete's usual
  band (the middle half of their other throws, shown once there are at least 8), so drift within a take (bag 4
  softer) is visible.

### Needs your eye

Throws whose result the engine could not decide (the front camera asked for confirmation, or could not tell
where the bag ended) collect in **Needs Your Eye** in the sidebar, with a count. One throw at a time it shows the
front camera's clip looping around the moment the bag came to rest (paused on the rest frame with Reduce Motion
on), the front and side cameras' readings in one line, and **In / On / Off** (keys **1**, **2**, **3**).
**Later** moves a throw to the end. After an answer the next throw appears; **Undo** in the bar at the top puts
back what was there. The same buttons are on an unsure throw's card on the Take screen.

A person's result is never overwritten: an answer is recorded only when the throw has no result or an automatic
one, and a later re-analysis never replaces a result a person entered. Automatic results are marked **auto** and
can be changed at any time (right-click a throw card, or **Add or Edit Outcome** in the report). Where the bag
landed and where it stopped stay measured automatically; the buttons only record the result.

### In each throw report

The report reads top to bottom in five blocks, then **Details** (collapsed):

1. **Result and one sentence.** The result chip (Hole · 3 / Board · 1 / Miss · 0; *front camera* until a result
   is recorded, **Needs confirmation** when the cameras were not sure) and the throw's sentence, for example
   "Board: 13 in short, 10 in right. Most of the short came from the slide … Next: land it about 13 in further."
   **Use This Result** records the front camera's result in one click.
2. **Where it ended**, the board from above and to scale (2 × 4 ft, front edge at the left, the thrower's left at
   the top): first contact (hollow ring) → slide (arrow, "slid 7 in") → where it stopped (filled 6 in bag) with its
   precision ellipse (±0.5 in across from the front camera, ±2 in along from the side camera), the hole, the
   dashed miss line from the hole, and a faint ghost of this athlete's usual: the other throws' rest points, the
   usual group (with at least 8 throws) and the usual landing line. A bag beyond the view is an arrow at the edge.
3. **Miss breakdown.** Two small additive bars, laid end to end from the hole line: *left/right* = release
   position + aim (launch direction) + slide drift; *short/long* = your usual spot + carry and slide against your
   usual. The grey band on each part is its measurement noise; a part is drawn in colour and bold only when the
   engine names it (at least 2× its noise, 3 in and 40 % of that direction's miss). The last row is where the bag
   stopped, over a band showing your usual spread. A part that was not measured is listed, not drawn, and the bar
   then says it does not add up. Not shown for a bag in the hole.
4. **Release vs your usual.** Release speed, release angle, launch direction (to 0.5°) and slide length as a dark
   dot among this athlete's other throws (grey dots). The grey band is the usual ± what the measurement can
   resolve: inside it the value reads "usual". A difference the sentence names is bold, with what it does to the
   landing ("about 15 in of carry").
5. **Replay.** **Side**, **Front**, **Both** (synchronised) and **Animation**. On the front video the bag's 3D
   flight is drawn as it flies: solid where the front camera saw the bag on that frame, dashed where the path is
   the model only (bag hidden, out of the picture or not found); without a 3D flight the older front tracker's
   path is shown and the reason is written in the corner. **Animation** shows two panels drawn to scale and in step:
   the side view (stick figure, measured arc solid, untracked gap dotted, drag-free model dashed, the usual landing
   as a faint ring) above the top view, which shares the side view's distance axis. In the top view the flight is
   a straight line along the measured launch direction (we measure the direction, not a curve) next to the dashed
   line from the release point to the hole, with the angle between them shaded and labelled. From first contact
   the top view enlarges to the board and the bag slides to rest at its measured pace. Playback pauses at
   release, first contact and rest, each with one callout tied to the sentence (turn this off under **Show**).
   Speeds are 1× and ¼×; drag the slider to scrub. With **Reduce Motion** on, the board appears enlarged at
   first contact without the zoom.

**Export Figure…** under the board and next to the animation controls saves a PNG (light, 2× resolution) of the
board or of the side + top panels at the current frame, for reports and slides.

**Details** holds everything else: the side camera's verdict, the front camera (body at release seen from the
front: hand across the body, trunk lean, release point and stance as plausibility checks, not causes; camera sync,
board tracking and the 3D flight fit), the release and body tiles (release height and its standard error, swing),
the slide (entry speed; slow-down and effective μ are research-only because μ comes out negative on some throws),
the plots, the green zone and the scientific details (all measurements, quality, launch fit, provenance).

Anything not measured is left out with a short reason; nothing is filled in.

How it works and how accurate it is: [METHODS_AND_MATH.md §5](METHODS_AND_MATH.md). For a batch of athletes from
the command line, use `scripts/add_takes_to_library.py`, then `scripts/analyze_library.py` (one athlete at a time).

## What changed in this version (board phase and personal green zone)

- **Where it ended.** Each throw report has a *Where it ended* card: where the bag landed on the board, how far it slid, and whether it stopped or dropped into the hole (including bags that hang on the lip and fall a moment later). The slide physics (speed along the board, slow-down, effective friction μ) are under the report's **Details**; the card shows a suggested result; **Use This Result** records it in one click. The flight chart marks *Landed* and *Stopped* / *Into the hole*, and the replay shows the slide.
- **Made throws get no corrections.** A hole is summarized as what worked (and a slide-in is named as part of the shot). Board bags and misses get signed advice from where the bag really stopped: "ended 9 in short … about 0.12 m/s faster".
- **Your distance, not 27 ft.** The app measures release point → front of the board in the videos (≈ 5.1–5.8 m in the tripod sessions) and uses it everywhere. The distance in Settings → Analysis is only a fallback.
- **Left/right is not measured** by the side camera; throws are assumed straight at the board. Record the board camera to measure left/right misses.
- **Personal green zone.** The athlete summary, each throw report and the Launch Lab show the athlete's own green zone (their release height, measured distance and measured slide) with a **best aim** target chosen for their consistency. In the Launch Lab choose **Use [athlete]'s green zone**. On the summary, click a throw on the map, or ▶ in the table, to watch it.
- **The summary uses every throw.** The consistency average pools every comparable analyzed throw and lists any left out with the reason. Throws analyzed with an older version are left out until re-analyzed: use **Re-analyze All** (the throws run one at a time).
- **One analysis at a time.** Imports and re-analyses go through one queue (see *Import & analyse*), and the engine refuses to start a second analysis on the same Mac until the first finishes, even from another copy of the app. Running several at once can use all the memory and freeze the computer.

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

Your default athlete data lives in `data/libraries/Cornhole Biomechanics Lab Data`, inside the checkout alongside the development files. **File → Choose Athlete Library** opens an existing library. **File → Import Legacy .cornholeproject** copies an older study without changing its original. Schema-2/3 libraries open normally. Their indexes are backed up before new edits save as schema 4, which supports unknown outcomes without allowing older builds to misread them as misses. Historical zeros are preserved and should be audited against video.

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
