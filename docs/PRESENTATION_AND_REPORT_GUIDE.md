# Cornhole Biomechanics Lab: Presentation and Report Master Guide

*Written 12 October 2026 from `main` at commit 0baf328f (engine 0.6.2, method version `2026.10.12-throw-plane-launch`).*

**Project 1, ME 3890-01 Biomechanics of Human Movement (Vanderbilt, Fall 2026), Prof. Karl Zelik.**

**Team:** Berk Kasimcan, John Wilson, Eliam Chang, Emily Park. **Client (fictional brief):** the Vanderbilt Athletics cornhole coach and sport scientist.

**Deliverables (Tuesday 20 October 2026, start of class):** a client report (zip to Brightspace, appendices allowed) and a 10-minute presentation/demo followed by 10 minutes of Q&A with the class.

This guide is the one place to build the report and the talk from. It covers the problem, every step of the processing pipeline from raw video to coach feedback, the mathematics and physics, the biomechanics reasoning, every design choice with its alternatives, the validation evidence, the results on our 92 real throws, the limitations and risks, a slide-by-slide talk plan, a section-by-section report plan, and a bank of likely Q&A questions with answers.

It was written from the code and the method documents in this repository. Where a document and the code disagree, the code was treated as the source of truth. Deeper derivations live in [METHODS_AND_MATH.md](METHODS_AND_MATH.md) (the formal methods), [METRICS.md](METRICS.md) (metric definitions and noise floors) and [CAMERAS_AND_MEASURES.md](CAMERAS_AND_MEASURES.md) (one-page camera map). Section numbers like "METHODS §1.9" below point there.

## 0. How to use this guide

**Labels on numbers.** Every number in this guide has a source. Three labels tell you how much to trust it before you put it on a slide:

| Label | Meaning | What to do |
|---|---|---|
| **[REPO]** | Taken from a method document, a test, or a calculation in this repository, with the file named. | Safe to quote. Cite the method, not this guide. |
| **[CHECK]** | Read from the athlete dashboards saved on `main` on 12 October 2026, or from two documents that disagree slightly. | Open the app and confirm the number on the athlete summary before it goes in the report. Outcomes may change once the 25 throws in "Needs your eye" are confirmed. |
| **[FILL]** | Not in the repository (dates, venue, participant details, your own reflections). | The team writes it in. Never invent it. |

**Two readers, two documents.** The report goes to the coach and sport scientist; write the body for them (plain language, what it means for training) and put the equations, code references and validation tables in appendices for Prof. Zelik. The talk goes to classmates; lead with what you did and learned, not background.

**One rule for everything you say.** The project's own ground rules are also the safest rules for Q&A: missing stays missing, every number has an uncertainty or a reliability grade, associations are never called causes, and a made throw gets no corrections. If you stick to these, you can defend every sentence.

**A note on AI use.** The course requires LLM use with verification. This guide was drafted by an AI assistant from the repository's code and documents. Each [REPO] number traces to a file; verify the [CHECK] numbers in the app and write the [FILL] items yourselves. Say in the report how AI was used (Section 18).

---

## 1. The assignment, decoded into a checklist

### 1.1 What the brief and the 8 October announcement require

The table maps each requirement to where this guide gives you the material and to how our system meets it. Use it as the final checklist before submission.

| # | Requirement (from the Project 1 handout and the 8 Oct announcement) | How our system meets it | Guide section |
|---|---|---|---|
| R1 | A bespoke, evidence-based training-analytics system for one sport (we chose **cornhole**) | Native macOS app plus a Python science engine built for cornhole: regulation board geometry, 0/1/3 scoring, underhand pendulum swing, bag flight and slide | 3, 5, 6 |
| R2 | Track movement in ways that give **individualized** insight | Every comparison is within one athlete (their scored vs missed throws, their usual spread, their personal green zone). No population "ideal" | 9, 10 |
| R3 | **Link specific movement features to task performance** (tracking or scoring alone is not enough) | The chain body → release → flight → landing → points, each link measured: release conditions from the bag flight, drag-free flight to the board, measured landing and slide, outcome; within-athlete statistics (Cliff's δ, Spearman ρ with bootstrap CIs) under a strict evidence gate | 6, 7, 9, 12 |
| R4 | Translate it into **feedback** that genuinely helps a coach or athlete | One plain sentence per throw from a 4-part miss explanation, a "Needs your eye" queue, a personal green zone (best speed × angle aim), Launch Lab, a printable PDF athlete report | 10 |
| R5 | **Real performance data from real participants** (not simulated or pre-existing) | 4 athletes, 23 two-camera takes, **92 real throws**, every throw analysed by the app [REPO: VALIDATION_PLAN, METHODS §5] | 6.1, 12 |
| R6 | Equipment realistically available; **no sensors on or in the bag** | Two phones on tripods; markerless pose; the bag is tracked only in video | 4, 6 |
| R7 | Research existing products, published research, open-source tools; an existing end-to-end solution does not satisfy the brief | We reuse open-source pose (Sports2D/RTMPose) and build everything cornhole-specific ourselves: bag tracking, board, scale from gravity, events, two-camera fusion, outcome, statistics, feedback | 4, 5 |
| R8 | Compare/contrast against **alternative approaches**, with credible references | Alternatives table (motion capture, IMUs, depth cameras, deep trackers, commercial apps, manual scoring) and per-step alternatives | 5, 8 |
| R9 | Address a broad range of factors, not just biomechanics | Cost, setup time, coach workload, privacy, data storage, analysis time, usability, recruiting use | 13 |
| R10 | **Limitations, unknowns, uncertainties and risks** | Every metric carries a status and uncertainty; explicit limitations, risks and a validation plan | 11, 14 |
| R11 | Bonus: useful for **evaluating recruits** | Athlete profile (backswing, trunk lean, peak wrist speed: strongly athlete-specific), consistency vs noise floor, PPR and In/On/Off from a 20-throw session | 13.3 |
| R12 | Final work must **drastically exceed the AI baseline report** | Real data, a working app, measured uncertainty, iterated methods, validation evidence, negative results reported honestly | 18 |
| R13 | Report written **to the client** (coach and sport scientist), appendices for Prof. Zelik | Report outline with a client-facing body and technical appendices | 17 |
| R14 | Talk: sport background and problem; solution and rationale; demonstration; why it is likely to improve training | Slide plan and demo script; skip long background | 16 |
| R15 | Talk: interesting parts, what you learned, hardest part, surprises, what you would do differently, what kept you up at night | Ready-made story material from the project history | 15 |
| R16 | Q&A: explain and defend every decision | 45 likely questions with answers | 19 |

### 1.2 What the graders will probe

From the handout's emphasis, expect pressure on four things: (1) is the movement-to-outcome link evidence-based or just a correlation; (2) how do you know the measurements are accurate enough; (3) why this design over the alternatives; (4) what would actually change in a Vanderbilt practice. Each has a prepared answer in Section 19.

---

## 2. The story in one page (use this to anchor both deliverables)

**The problem.** A cornhole coach sees where the bag ends up, not why. Two misses that look identical (both 12 inches short) can come from different causes: a softer release, a flatter release, a bag that landed in the right place and slid less than usual, or a release that started off line. Without measurement, a coach either guesses or applies one "ideal form" to every athlete.

**Our solution.** Two phones on tripods (one beside the lane, one behind the board) and a Mac app. The app finds the athlete's body and the bag automatically, measures the bag's release speed, angle and height from its own flight, tracks it to the board, decides hole/board/off, and splits every miss into measured parts: where it was released, where it was aimed, how far it carried compared with the athlete's usual, and how far it slid. It then gives one plain sentence per throw and, across many throws, tells the coach which (if any) movement features really separate this athlete's good throws from bad ones, but only when the evidence is strong enough.

**Why it is credible.** Physics does the heavy lifting: a bag in flight must fall at $g = 9.81$ m/s², so the bag's own arc rejects false detections and even calibrates the camera's metric scale. Every number carries a status (`measured`/`estimated`/`unavailable`), a quality grade and an uncertainty; differences smaller than measurement noise are never reported; associations are never called causes.

**What we learned from 92 real throws** [CHECK where marked in Section 12]:

1. All four athletes release at almost the same speed (median 7.46–7.56 m/s; between-athlete SD 0.04 m/s, ICC ≈ 0.01) [REPO: METRICS "Metric review"]. What differs is throw-to-throw speed **consistency** (SD 0.21–0.44 m/s within an athlete, 1.4–2.9× the 0.15 m/s noise floor).
2. Our athletes naturally release near 40°, which is the "forgiving" angle: at their release height and distance one degree moves first contact only about 1 cm, while 0.1 m/s of speed moves it about 13 cm [REPO: engine model, Section 8.5]. So speed control, not angle, is the main lever on distance.
3. Body "style" is strongly individual (backswing ICC 0.96, trunk lean ICC 0.90) but barely changes from throw to throw, so it describes how an athlete throws, not why one throw missed [REPO: METRICS "Metric review"].
4. Many misses are made **after** landing: in the miss explanations the slide or sideways slide is a named part as often as the carry (carry named 24 times, slide drift 15, aim 13, slide 13) [REPO: METHODS §5.5].
5. With 20–28 throws per athlete, **no** movement feature passed the full evidence gate for a coaching priority. That is the honest answer: per-group sample sizes of about 7–8 are needed even for perfect separation, and our stress test shows 20–40 throws per athlete are needed to detect a real cause reliably [REPO: performance.minimum_claim_group, STRESS_TEST].

**Why it would help Vanderbilt.** A practice can be filmed with two phones; results arrive in about 2 minutes per throw on a Mac; the coach confirms only the throws the app is unsure about; and the feedback is individual, quantified and honest about what is noise. It also produces a repeatable athlete profile that could support recruit evaluation.

---

## 3. Sport background and the specific problem

### 3.1 Cornhole in numbers (regulation, American Cornhole League)

| Item | Value | Source |
|---|---|---|
| Board deck | 24 in × 48 in (0.6096 × 1.2192 m) | ACL Rules; `regulation.py` |
| Front / back height | 3 in / 12 in (front varies 2.5–4 in on certified boards; 3 in default) | ACL; `regulation.py` |
| Deck slope | $\alpha = \arcsin\big((12-3)/48\big) \approx 10.8°$ (ACL nominal 11°) | Eq. 3.2.2 |
| Hole | 6 in diameter (radius 3 in), centre 9 in from the back, centred across: (12, 39) in from the front-left corner | ACL; `regulation.py` |
| Pitch | 27 ft front edge to front edge (≈ 8.23 m); release-to-board-front in regulation play ≈ 7.7 m (27 ft minus reach) | ACL; `zones.py` default |
| Bag | 6 × 6 in, 15.5–16 oz (0.439–0.454 kg), nominal 15.75 oz = 0.4465 kg | ACL; `regulation.py` |
| Per-bag score | 3 in the hole, 1 on the board, 0 off/foul; rounds use cancellation scoring | ACL Rules |
| Common performance stat | PPR (points per round) = 4 × mean points per bag (gross, no cancellation); In / On / Off % | ACL; `zones.sports_stats` |

The ACL broadcasts events on ESPN platforms (the handout's own point). Treat equipment numbers as nominal: certified boards have tolerances (23.75–24.25 in width, 47.75–48.25 in length) and a real practice board should be measured.

### 3.2 The movement

A cornhole throw is an **underhand, mostly sagittal-plane pendulum swing** of the throwing arm, usually with a forward step:

1. **Set-up / aim:** standing in the pitcher's box, bag held at about waist height.
2. **Backswing:** the arm swings back behind the trunk (our athletes' backswing reached arm angles of −31° to −78° from straight down, Section 12) [CHECK].
3. **Forward swing:** the arm swings forward and up; the bag accelerates mostly by shoulder flexion with a near-straight elbow (elbow at release ≈ 151–162° in projection) [CHECK]; the trunk leans toward the board.
4. **Release:** the bag rolls off the fingers after the hand has passed its peak forward speed. In our audited throws peak forward wrist speed came 4–7 frames (≈ 90 ms) before release [REPO: METHODS §1.9].
5. **Flight:** about 1.1 s at our distances; the bag usually spins flat (we do not measure spin).
6. **Landing and slide:** the bag first contacts the 10.8° deck and slides; on our athletes the median slide is 0.42–0.56 m (17–22 in) [CHECK: dashboards, `personal_zone.slide_allowance_m`]. A bag landing short of the hole often slides in.

The **outcome is decided by release conditions plus what happens on the board**. Once the bag leaves the hand its flight is (to first order) a projectile set by release speed, angle, height and direction. The body matters through how consistently it produces those release conditions.

### 3.3 The specific problem we chose

> **Problem statement (use this wording or close to it):** A cornhole coach can see where every bag ends up, but not which part of the throw caused a miss, and whether a difference in an athlete's movement is real or just noise. We built a two-phone system that measures each throw from body to release to flight to landing, explains each miss in measured parts, and only turns a movement difference into coaching advice when the athlete's own data supports it.

Why this problem is worth solving for the client:

- **Coach time is the bottleneck.** The coach watches four bags per round and can't measure release speed by eye; 0.1 m/s of speed (invisible) moves the landing about 13 cm (5 in) at our distances.
- **Misses have different causes that look the same.** Short can be carry (release) or slide (board behaviour); left/right can be release position or aim. Training the wrong one wastes practice.
- **There is no single correct technique.** Accurate throwers in other aiming tasks use different strategies (Nasu et al., 2014), and the best release angle is athlete-specific (Linthorne, 2001). A template-matching system would coach athletes away from a working style.
- **Measurement noise is real.** Markerless pose and phone video have errors of several pixels; a system that reports every difference will send coaches chasing noise. Ours reports only differences above a stated noise floor.

### 3.4 The client and the users

| Person | What they need from the system |
|---|---|
| Head coach | One plain cue per throw; which athletes need what; who is consistent; fast, low-effort workflow at practice |
| Sport scientist | Transparent methods, uncertainty on every number, exported data (CSV/JSON), validation status, reproducibility |
| Athlete | A short, specific, believable next-throw cue; seeing their own good throws on video |
| Recruiting staff (bonus) | A comparable profile and consistency measures from a short filmed session |

---

## 4. From the problem to design requirements

Each requirement below drove concrete design choices. In the report this table is a compact way to show the design was reasoned, not accidental.

| Design requirement | Why (source) | Design choice it produced |
|---|---|---|
| D1. No sensors on/in the bag; affordable, portable equipment | Course constraint; a practice gym | Phones on tripods only; markerless pose; bag tracked by video |
| D2. Measure the bag's release, not only the body | Release conditions are the proximal cause of landing (projectile physics) | Physics-gated bag tracking and a launch fit on the first 0.12 s of flight |
| D3. Metric units without a calibration object in every clip | Coaches won't film a meter stick every session; pilot footage had none | Scale from the regulation board (PnP) plus the bag's own fall at $g$ (gravity-calibrated field of view) |
| D4. See left/right and the real landing, not just distance along the throw | Zelik's interim feedback: "How does the system address heading (left–right) errors?"; peer review: "nothing measures left/right" [REPO: FEEDBACK_RESPONSE] | Second (front) camera behind the board; sound sync; 3D flight fit; deck homography |
| D5. Outcome recorded with minimal coach effort | Zelik: "Can recording the result be automated? The coach is busy" | Automatic hole/board/off from the front camera; one-click confirmation only when unsure ("Needs your eye") |
| D6. Individual, not template-based | Multiple successful strategies exist (Nasu 2014; Linthorne 2001; Müller & Sternad 2004) | Within-athlete comparisons only; personal green zone; athlete's "usual" as the baseline |
| D7. Never report noise as a finding | Markerless error is several px; small samples | Noise floors per metric, reliability rules per throw, evidence gate with Bonferroni-corrected Cliff's δ |
| D8. Explainable and traceable for Q&A | Course grading; sport scientist user | Every number has a status, grade, uncertainty and a method section; no composite 0–100 scores |
| D9. Plain, short coach language | Peer review: "simplify for coaches" | One sentence per throw; no jargon; never "because/caused/fault/should" |
| D10. Runs locally, protects athlete video | Privacy; no internet at a gym | All analysis on the Mac; one analysis at a time (the Mac crashed when the whole library ran in parallel) |

---

## 5. Alternatives considered (and why we chose what we did)

### 5.1 Whole-system alternatives

| Approach | What it gives | Why not (or why only partly) | Credible basis to cite |
|---|---|---|---|
| **Optical motion capture** (marker-based, e.g. 8–12 infrared cameras) | Gold-standard 3D joint kinematics at 100–500 Hz | Lab-only, expensive, slow set-up, markers on athletes, not usable at routine practice; still needs a separate bag measurement. Best used as a **validation criterion**, not the product | Nasu et al. 2014 (7-camera 480 Hz darts); Tran et al. 2019 (six 200 Hz cameras) as examples of lab set-ups |
| **Wearable IMUs on the arm/wrist** | Arm angular velocity and timing at high rate, no line of sight needed | Gives the body but not the bag's release speed/angle or landing; drift; still needs video for outcome; athlete burden. A good **future add-on** for timing | Needs a citation if used in the report [FILL: an IMU throwing validation paper] |
| **Sensor in the bag (IMU/"smart bag")** | Direct release velocity and spin | **Forbidden by the brief** | Handout |
| **Depth camera / LiDAR** (e.g. Kinect-type, iPhone LiDAR) | 3D body points | Short range (a few metres), poor for a fast small bag at 6–8 m, extra hardware and software | Needs a citation if used [FILL] |
| **Commercial video-analysis apps** (slow-motion, drawing tools, side-by-side) | Easy replay and manual angles | Manual, no automatic bag physics, no outcome link, no uncertainty, no statistics; an "existing end-to-end solution" would not satisfy the brief | Name products only with a source; avoid marketing claims [FILL] |
| **Manual scoring sheet + coach's eye** | Outcome only | No movement-to-outcome link; the brief explicitly says tracking or scoring alone is not enough | Handout |
| **One side camera only** (our first version) | Body + release speed/angle/height + distance along the board | Blind to left/right and to the across-board landing; can't tell hole from board reliably | Sih et al. 2001 (2D planar assumption); our pilot |
| **Two phones, physics-fused (our final design)** | Side: body, release, flight, along-board landing. Front: hole/board/off, left/right, frontal body. Both: sync, 3D bag flight, miss explanation | Not full 3D body kinematics; 30 fps front camera; needs a validation study (planned) | This repo, METHODS §5 |

### 5.2 Per-step alternatives (the "why this, not that" list)

| Step | Chosen | Alternatives considered | Why chosen |
|---|---|---|---|
| Pose model | **Sports2D 0.8.34 + RTMPose (HALPE-26, with heel/toe points)**, CPU/ONNX, pinned version | MediaPipe Pose, OpenPose, commercial pose | Open-source with a peer-reviewed paper (Pagnon & Kim 2024), multi-person tracking, foot points for release height, runs on a Mac CPU; pinned so numbers don't change silently [REPO: SPORTS2D.md] |
| Choosing the thrower | Largest coverage × median body size | Sports2D's highest-confidence person | Motion blur lowers the thrower's confidence; a still bystander won on confidence in pilot clip "playe1 - 7" [REPO: METHODS §1.4] |
| Filter | **4th-order zero-phase Butterworth, 6 Hz** | No filter; other cutoffs (4, 8, 12 Hz); Kalman on joints | Standard in biomechanics (Winter 2009); residual analysis on 12 real signals gave median optimum 5.5 Hz (3.5–7.5) [REPO: METHODS §1.4] |
| Bag detection | **Classical: motion differencing + physics-gated parabola** | TrackNet-type deep ball trackers; SAM 2 segmentation | No labelled cornhole data to train a network (TrackNet needs thousands of labels: Huang et al. 2019); SAM 2 is multi-GB and slow on CPU; a free bag **must** fall at $g$, which rejects almost all clutter for free [REPO: AUTOMATIC_TRACKING.md] |
| Bag centre | Colour (Lab) silhouette centroid | Difference-blob centre | The blob sat up to ~15 px off the bag centre [REPO: METHODS §1.6] |
| Bag path smoothing | Constant-acceleration Kalman + RTS smoother with outlier gating | Spline; no smoothing | Gives a clean display path, rejects outliers without deleting raw data; launch fit still uses raw points |
| Metric scale | **Board PnP + gravity-calibrated field of view, pooled per camera set-up** | Meter stick each session; regulation pitch distance; assumed lens | Pilot footage had no stick; one image can't separate focal length from distance; gravity on the bag breaks the ambiguity; pooling removes single-throw noise [REPO: METHODS §1.8, §5.1] |
| Release detection | **First bag centroid > 0.45 arm lengths from the wrist** | Peak wrist speed; first point of the flight fit; manual | 21/21 pilot throws within ±1 frame of a visual audit (19 exact) [REPO: METHODS §1.9] |
| Flight model | **Drag-free** point mass | Quadratic drag | Drag did not improve out-of-sample prediction (median 24.5 vs 24.9 px); drag changes apparent $g$ by only −0.2 to −1.4 % [REPO: METHODS §1.11] |
| Outcome | **Automatic from the front camera**, coach confirms only unsure throws | Coach clicks every throw; side camera only | Zelik asked for automation; the side view can't see the hole well |
| Two-camera sync | **Audio cross-correlation (clap + bag impacts)** | Timecode hardware; visual clap frame; flash | Free, automatic, ±17.5 ms; works on every pair (r = 0.44–0.74) [REPO: METHODS §5.1] |
| 3D bag flight | **Physics-constrained fit: side arc + front lateral line** | Stereo triangulation | The two phones are not calibrated to each other; the bag flies straight at the front camera, so it only has to answer "how far left/right" [REPO: METHODS §5.4] |
| Statistics | **Within-athlete Cliff's δ, Bonferroni critical δ, bootstrap CIs, Spearman ρ** | t-tests across athletes; machine learning | Small samples, non-normal data, nested throws; nonparametric and conservative; ML would overfit 20 throws |
| Scores | **No composite score** | 0–100 "technique" or "consistency" index | Removed on 22 Sep 2026: tolerances and weights had no empirical basis and hid which component differed [REPO: METRICS] |

---

## 6. System overview

### 6.1 Hardware and the recording set-up (final data collection)

| | Side camera | Front camera |
|---|---|---|
| Device | iPhone 15 Pro Max | iPhone 17 Pro |
| Video | 1920 × 1080, 59.94 fps (variable frame rate) | 1280 × 720, 30 fps |
| Placement | Tripod beside the throwing lane, optical axis across the throw | Tripod behind the board, looking back along the throw line at the thrower |
| Sees well | Throw plane (sagittal): forward–back and up–down | Frontal plane: left–right and up–down |
| Cannot see | Left–right (depth toward the camera) | Distance along the throw (the bag flies at it) |
| Scale from | Board deck (PnP) checked by gravity on the bag's arc | Deck corners (homography; camera pose from the deck shape) |

[REPO: METHODS §5, CAMERAS_AND_MEASURES]. The front camera sat about 4.0 m from the board front, 1.27 m high, on the centre line (from PnP) [REPO: METHODS §5.2]. Release-to-board-front distance was 5.3–5.9 m per athlete (median per athlete), shorter than the ≈ 7.7 m of regulation play [CHECK: dashboards `distance`].

**Take protocol.** One take = one continuous recording per camera: the athlete claps, shows the take number with their fingers, then throws four bags. Files are named `Take_<n>_Side` / `Take_<n>_Front`.

**Data set.** 4 athletes (Player 1–4, all right-handed), 23 takes (7, 5, 5, 6), 4 throws each = **92 throws**, 46 video files [REPO: data/videos/Final Data Collection, METHODS §5.2]. [FILL: date(s), venue, board used, bag colour (red), consent procedure, athletes' experience level.]

**Earlier data (iteration history, worth one slide):** 26 hand-held single-camera pilot clips from 3 athletes on 17 September 2026, then tripod sessions in late September, then the two-camera Final Data Collection. Each stage fixed problems found in the previous one (Section 15).

### 6.2 Software architecture

```
 SwiftUI macOS app (app/CornholeBiomechanics)          Python science engine (python/cornhole_biomech)
 ─────────────────────────────────────────────          ─────────────────────────────────────────────
 Athlete library, Import Takes, queue (one at a time) ──► worker process; streams JSON-line progress
 Take screen, Throw report, Needs your eye                 pose · bag · board · scale · events · chain
 Athlete summary, Launch Lab, PDF report  ◄──────────────  CSV / JSON / PNG outputs per throw
 SceneVision helper (Apple Vision person masks)            athlete-level statistics and feedback text
```

- About 640 Python tests (644 passing on 12 Oct 2026) and 87 Swift tests; `./verify.sh` runs everything plus a signed build [REPO: RECOVERY_STATUS 2026-10-12].
- Each throw takes about 2 minutes to analyse on the Mac; only one analysis runs at a time (a Mac-wide lock), because full-library parallel runs crashed the Mac [REPO: APP_GUIDE, CLAUDE.md].
- Every output carries a method version (`METHOD_VERSION = "2026.10.12-throw-plane-launch"`); throws analysed with different versions are not pooled.

### 6.3 The core chain the app shows

```
 BODY ──► RELEASE ──► FLIGHT ──► LANDING / SLIDE ──► OUTCOME ──► ADVICE
 pose      speed,      drag-free   first contact,      3 / 1 / 0   one sentence,
 swing     angle,      projectile  slide, rest,        (front      4-part explanation,
 timing    height,     (3D with    left/right          camera)     evidence-gated
           direction   2 cameras)  (front camera)                  priorities
```

It is a **hypothesis structure, not a causal claim**: we measure each link and state which links the data support.

---

## 7. The processing pipeline, step by step

For each step: **what** it does, **how**, the **key numbers** (with code source), **why** it was designed that way, and what can **go wrong** and how the app guards against it. In the talk you need only the one-line "what" of each step; in the report appendix you need all of it.

### 7.0 The whole pipeline at a glance

```
 TWO VIDEOS (side 59.94 fps 1080p, front 30 fps 720p) per take
   │
   ├─ A. Take preparation: pair files → identify camera roles → sync from sound → find the 4 throws → cut clips
   │
   ├─ B. Side camera (per throw)
   │     B1 stabilise camera  B2 pose (Sports2D/RTMPose) → clean → 6 Hz filter
   │     B3 person masks + background plate   B4 bag tracking (physics-gated) → centroid → Kalman/RTS
   │     B5 board detection (PnP)   B6 metric scale (gravity-calibrated FOV, pooled)
   │     B7 events (backswing, release, peak wrist speed, first contact)   B8 launch fit (speed, angle, height ± SE)
   │     B9 body kinematics   B10 board phase (touchdown, slide, rest / hole / off)   B11 bag mechanics + Monte Carlo
   │
   ├─ C. Front camera (per throw)
   │     C1 deck + homography + camera pose   C2 drift correction   C3 where the bag ended (hole/board/off)
   │     C4 deck track + first contact across   C5 heading   C6 frontal-plane body (Sports2D)
   │
   ├─ D. Combined: result + landing point, 3D flight, miss attribution, coach sentence, 4-part explanation
   │
   └─ E. Athlete level: scoring, release profile, consistency, scored vs missed, evidence chain,
         priorities gate, compensation, personal green zone, PDF report
```

Every stage outputs a state: `measured`, `estimated` (with a reason) or `unavailable` (with a reason). **Missing stays missing**; nothing is ever filled with zero or a guess.

### 7.1 A. Take preparation (both cameras)

| Step | What and how | Key numbers | Why / safeguards |
|---|---|---|---|
| Pairing | Match `take <n> <front/side>` file names, any capitalisation | — | A take with one camera is reported, never guessed |
| Camera roles | Compare each file's device model, frame size and frame rate; majority vote decides which phone is "side" and which is "front" | — | Player 1 take 3: the file named *Front* was recorded by the side phone. Detected as **swapped labels** and used in its true roles; files never renamed [REPO: METHODS §5.1] |
| Sound sync | Both phones hear the clap and every bag impact. High-pass 300 Hz → 5 ms RMS envelope in dB → subtract 1 s running median → normalised cross-correlation over ±12 s | Accept if $r \ge 0.35$ and the peak beats every lag outside ±100 ms by ≥ 0.08. On all 23 pairs $r$ = 0.44–0.74, margin 0.10–0.35. Uncertainty **±17.5 ms** (sound travel ≈ 2.9 ms/m and mic distances ±15 ms, plus half an envelope hop) | Free and automatic; ±17.5 ms is about half a front frame. Each throw also gets a direct check: side first-contact frame vs first front frame with the bag on the deck (±4 front frames) |
| Front picture lag | What a phone shows at a timestamp also depends on exposure, rolling shutter and audio latency; the front showed contact one frame late on all 6 audited throws | Pooled per front set-up (interquartile mean, ≥ 8 throws): ≈ 21 ms over 79 throws [REPO: METHODS §5.1; CAMERAS_AND_MEASURES says 18 ms, CHECK which is current] | Rejected if beyond ±100 ms or spread > 70 ms (that would be a sync fault, not a lag) |
| Finding throws | Side video at 480 px: three-frame differencing → small moving blobs → tracklets → a flight must cross ≥ 35 % of the frame toward the board; flights within 2 s are one throw; confirmed by an impact sound in the front audio (±0.45 s) | Blobs 4–400 px², 1.5–20 px/frame | Rejects people walking and a bumped camera (median ≥ 15 moving blobs per frame and ≥ 4× typical); Player 1 takes 4 and 6 had a fifth "flight" that was the phone being picked up |
| Clips | Side clip from 2.5 s before flight start to 1.6 s after it ends; front clip covering the same synchronised time; H.264 CRF 12 | Each frame's source timestamp stored | Side phone records variable frame rate, so real timestamps are used, not nominal rates. Originals are never changed |

### 7.2 B. Side camera, per throw

**B1. Camera stabilisation.** Each frame is registered to a keyframe by ECC (enhanced correlation coefficient) with an affine model at ¼ scale, initialised by ORB features + RANSAC. New keyframe when correlation < 0.8. *Why:* the pilot clips were hand-held (drift up to ~100 px); after registration the residual was ≤ 4.6 px (from up to 51 px) [REPO: METHODS §1.3]. On tripods it removes small bumps. Affine, not similarity, because floor and far walls move differently under parallax.

**B2. Pose.** Sports2D 0.8.34 runs RTMPose (HALPE-26 keypoints, including heels and toes) on the CPU. Processing order is fixed: raw → manual corrections (never overwrite raw) → confidence mask (< 0.35 becomes missing) → linear interpolation of gaps ≤ 3 frames only → 4th-order zero-phase Butterworth at 6 Hz → angles → derivatives. Coordinates are filtered **before** angles and derivatives. Body scale: projected arm length $L_{arm}$ = median shoulder–elbow + median elbow–wrist (pixels), so differently framed clips compare. *Thrower choice:* the tracked person with the largest coverage × median body size (a still bystander can win on confidence because blur lowers the thrower's) [REPO: METHODS §1.4].

**B3. Person masks and background plate.** Apple Vision person segmentation on every second frame; the background plate is the per-pixel median of stabilised frames with people treated as missing. Bystanders get a padded box from the pose tracker. Bag candidates inside a person cannot start a flight (a swinging arm is not the bag) but can extend one (the bag may fly in front of a bystander). If masks are unavailable the pipeline says so and continues.

**B4. Bag tracking.** The heart of the system. Steps [REPO: METHODS §1.6, AUTOMATIC_TRACKING]:

1. *Candidates:* frame difference against the plate and three-frame differencing (camera-compensated); fragments within 16 px merged.
2. *Seeds:* blobs linked frame to frame, short windows fitted with a quadratic; a seed must move toward the target, curve **downward** with an image "gravity" in the range implied by the athlete's size (shoulder–wrist 0.45–0.90 m), and have small horizontal curvature.
3. *Growth and trimming:* extend backward until the bag is within 0.45 arm lengths of the wrist (still in hand) and forward to first contact using colour (Lab) search at the predicted position (four gates: distance, area, bag colour, not inside a person); trim where the path breaks from a local parabola (slide/bounce).
4. *Acceptance (all must hold):* ≥ 12 detections, ≥ 0.25 s, ≥ 60 % coverage, ≥ 4 arm lengths of travel, RMS residual to the parabola ≤ 0.08 arm lengths, first free point ≤ 0.8 arm lengths from the wrist. Otherwise `needs_review` with every reason listed.
5. *Centroid:* colour silhouette centre from image moments (the raw difference blob sat up to 15 px off).
6. *Smoothing:* constant-acceleration Kalman filter + Rauch–Tung–Striebel smoother, noise estimated per clip, leave-one-out outlier gating (outliers labelled, never deleted). The smoothed path is for display; the launch fit uses raw accepted centroids.

*Working resolution:* 4K clips are searched at 1080 px height and results mapped back. At full 4K the bag blob fragmented and 0/10 Player 1 flights were accepted; at 1080p 8/10 were, with a quarter of the memory [REPO: METHODS §1.6].

**B5. Board detection.** HSV segmentation of the red deck and dark rim/apron on the background plate; a candidate quad must pass PnP (IPPE solver on the four deck corners at the regulation slope, reprojection < 3 % of quad width) and the **hole test** (a dark blob within 4 in of (12, 39) in). Confidence ≥ 0.75 and the front-near corner must be seen. Outputs: deck corners, image → deck-inches homography, the **throw-plane homography** (image ↔ vertical plane through the board centre line, metres), and the out-of-plane angle φ of the throw line (> 20° flagged). Later throws in a take have bags on the deck, so the empty-board corners from the take start (or from a sibling throw) are carried by ECC alignment [REPO: METHODS §1.7, §5.1].

**B6. Metric scale.** One image cannot separate a wide lens up close from a narrow lens far away. The bag's flight must fall at $g = 9.80665$ m/s², so the app scans the horizontal field of view (HFOV), re-solves the board pose at each value, maps the flight into the throw plane, fits height vs time, and finds the HFOV where the vertical acceleration equals $-g$ (Section 8.6). Single throws scatter (51–65°), so values are **pooled** (median) over every throw from the same phone, date and tripod position (deck centre within 25 px), across athletes, because the lens does not depend on who throws. Pooling per athlete instead gave 61.1° vs 52.6° for two athletes filmed by the same unmoved camera, an 8° disagreement the lens cannot have [REPO: METHODS §1.8, §5.1].

**B7. Events.**

| Event | Rule | Evidence |
|---|---|---|
| Release | First refined bag centroid more than **0.45 arm lengths** from the wrist; earlier points are "in hand"; parabola refitted | 21/21 pilot throws within ±1 frame of visual release (19 exact; mean +0.10 frame, SD 0.30) |
| Release (no accepted flight) | Peak forward wrist speed + **0.09 s** | On 13 audited throws peak came 4–7 frames before release (median 5.5); residual −2 to +1 frames; always "unconfirmed" |
| Top of backswing | Most rearward shoulder-relative wrist before release | — |
| Motion start | Last quiet frame before the fastest rearward wrist movement in the 1 s before the top | Old rule fired on walking/aiming in 5 of 6 throws |
| Peak follow-through | Arm's highest point after release (within 0.02 arm lengths of the max) | Old "most forward" fell 0–4 frames after release |
| First contact | End of the flight classified as deck / front face / floor within 6 cm; a near-contact rule; otherwise `lost_in_flight` and a predicted contact marked `estimated` | — |

[REPO: METHODS §1.9]. All automatic events are candidates a reviewer can correct; the raw candidate is kept.

**B8. Launch fit (release speed, angle, height).** Raw accepted centroids in the first 0.12 s after release (≥ 4 samples). With a valid scale the **gravity-constrained** fit removes the known $\frac12 g q t^2$ and fits straight lines, which cut the angle SD from ≈ 2.6° to ≈ 0.7° in simulation at 2 px noise, 60 fps. When the board plane is the scale, the fit is done directly in throw-plane metres (`bag.plane_launch_fit`; differs from the pixel route by −1.3…+0.9 % in speed). Huber-weighted least squares; standard errors by the delta method. Release height = bag centre above the lowest heel/toe landmark (±3-frame median) [REPO: METHODS §1.11, CALCULATION_AUDIT D2].

**B9. Body kinematics** (all projected 2D in the camera plane): elbow included angle, shoulder angle (continuous through the trunk line), arm angle φ from straight down, backswing, trunk inclination, wrist speed and direction, peak wrist speed and its timing, forward-swing time, tempo (backswing ÷ forward-swing time), pendulum drive ratio. Definitions in Section 8.3 and METRICS.

**B10. Board phase** (touchdown, slide, rest/hole/off). After the flight, the bag is followed on the deck to the end of the clip with an empty-board background and the deck homography. Touchdown = first sample that can lie on the deck **and** has stopped falling (centre drops ≤ 0.38 bag lengths to the next sample). Stop = along-deck position steady within max(1 in, 3 px precision) for 0.2 s. Fell in = disappears ≥ 0.12 s within 6.5 in of the hole centre. Left the deck = lost at an edge. Slide kinematics: constant-deceleration fit $s(t) = s_0 + v_0 t - \frac12 a t^2$ gives the entry speed and an effective friction $\mu = a/(g\cos\alpha) - \tan\alpha$ (gated; research only). On 10/10 tripod clips with a located board the end was classified correctly, including a bag that hung on the lip for 0.6 s then dropped [REPO: METHODS §1.9].

**B11. Bag mechanics and Monte Carlo.** With a metric scale: momentum, kinetic and potential energy at release, net non-gravitational force on the bag $\mathbf F = m(\mathbf a - \mathbf g)$ during the forward swing and power $P = \mathbf F\cdot\mathbf v$ (checked against $dE/dt$). Always labelled *"Bag-only: not a muscle, joint or hand-contact force."* Uncertainty from 500 Monte Carlo draws over scale, bag mass, fit errors and 4 px landmark noise; second-derivative quantities are `measured` only when their 95 % interval half-width is < 25 % of the value [REPO: METHODS §1.12].

### 7.3 C. Front camera, per throw

**C1. Deck, homography and camera pose.** On a median plate of the take's first 1.5 s: the dark end apron, the red deck's side edges (RANSAC lines), and the front edge chosen by the **hole test** (the homography from each candidate must put the hole within 4 in of (12, 39)). Found on all 10 checked takes with the hole 0.04–0.43 in from nominal. One pixel ≈ 0.3–0.5 in across at mid-deck, so lateral precision is stated as ±0.5 in. The front camera's field of view comes from the PnP reprojection residual's sharp V-shaped minimum (60.7–65.8°, ±2.5°), pooled per phone and day. A corner check (residual > 2.5 px or FOV > 8° off) marks corners as suspect and withholds what depends on them [REPO: METHODS §5.2].

**C2. Drift correction.** The front phone sank ~40 px over a 30 s take. Every 5th frame is ECC-aligned to the take's reference on the deck area, **with bag pixels masked out** (a bag that wasn't in the reference pulled the fit 24–27 px on three throws and moved one rest 17 in sideways). A shape guard drops key frames whose deck shape changes by > 3 px (all 92 throws ≤ 1.24 px once bags are masked).

**C3. Where the bag ended (hole / board / off).** Compare the scene before release (bag in hand) and after the bag stops, both against the empty board. New-bag blobs are classified: whole-bag-sized on the deck → **board**; under the board in the hole region → **hole**; on the floor, bag-coloured, near the board → **off**; nothing new anywhere with the deck fully visible → **off** (only suggested when the side camera agrees). Knocked bags: when one throw changes the deck and the hole region, the side camera's ending decides; a deck track that turns more than 45° after contact while another bag moved is flagged for confirmation [REPO: METHODS §5.2, VALIDATION_PLAN].

**C4. First contact across the board.** The moving bag near the deck is tracked from just before the synced contact time with colour + motion; the point nearest the contact frame within 6 in of the deck gives $x_{contact}$. Since `two_view_v7` the front camera's own first-contact frame is used (on 34 of 86 throws the nearest synced frame still showed the bag in the air).

**C5. Heading (left/right aim).** $\psi = \operatorname{atan2}(X_{contact} - X_{release},\ D_{release} + y_{contact}\cos\alpha)$; noise ≈ 0.5°.

**C6. Frontal-plane body.** Sports2D on the front clip, joints ≥ 0.3 confidence, roll-corrected from the board's level back edge, same 6 Hz filter. Measures: trunk side lean, shoulder tilt, hand across the body, release offset, stance, **hand-path sideways range** in the forward swing (ICC 0.89, kept), **trunk lean change** set-up → release (ICC 0.77, kept), hip sway (ICC 0.66, **dropped** as a scalar: within-athlete spread was two thirds of the between-athlete spread). No elbow or shoulder angles from the front: the arm swings toward that camera [REPO: METHODS §5.2].

### 7.4 D. Combining the two cameras

| Output | How | Key numbers |
|---|---|---|
| Result (3/1/0) | From the front camera; the side board phase is a cross-check; disagreement → *needs confirmation*. Guards withhold the front result when the side saw a floor contact with no touchdown, when corners are suspect, or when a hole came only from a track whose sync check failed | A confident result is recorded automatically as **auto**; it never overwrites a person's entry |
| Landing point | Across (x) from the front camera; along (y) from the side board phase (the front sees the deck at a grazing angle) | Precision ellipse ±0.5 in across, ±2 in along |
| 3D bag flight | Side camera gives the arc along and up (metric); front camera only has to find $X_0$ and $V_x$ in $X(\tau) = X_0 + V_x\tau$; RANSAC on candidate lines, then robust least squares on image residuals with nuisance timing offset δ (±4 frames) and front FOV (pooled ± 8°) | 72/92 throws fitted (38 measured, 34 estimated); landing across the deck agrees with the front camera's measured contact to median 0.8 in (86 % within 2 in, SD 1.35 in); launch angle vs heading median 0.34°; release position vs front pose hand median 1 cm [REPO: METHODS §5.4] |
| Miss attribution | Left/right identity and short/long split against the athlete's usual (Section 8.9) | Results Section 12.5 |
| Coach sentence + 4-part explanation | Built only from named parts (Section 10) | — |

### 7.5 E. Athlete level

Scoring (PPR, In/On/Off), release profile (median, IQR, SD, CV, SD ÷ noise floor), consistency waveforms, scored-vs-missed comparison with the evidence gate, evidence chain (Spearman ρ with bootstrap CIs), five-check coaching priority gate, compensation (permutation) test, landing error budget, personal green zone, and the PDF report. Details in Sections 8.10–8.12 and 10.

### 7.6 The quality system that runs through every step

| Layer | What it does |
|---|---|
| Status per number | `measured` / `estimated` (with reason) / `unavailable` (with reason) |
| Stage grades | Pose, bag, calibration, release each graded GOOD / WARNING / POOR with stated thresholds (e.g. release GOOD = confirmed by a person, or the two release cues within 4 frames, ≥ 6 fit samples, angle SE ≤ 3°) |
| Per-metric reliability rules | (1) visible: landmark confidence ≥ 0.35 in release ± 2 frames; (2) in plane: segment ≥ 70 % of its median length (else foreshortened); (3) stable: filtered within 0.1 arm lengths of raw; (4) plausible: inside physiological bounds; (5) release-window sensitivity; (6) bag metrics inherit bag/release/scale grades. Result: reliable / caution / unreliable (withheld) / not measured |
| Noise floors | The smallest difference the analysis will interpret (Section 9.3) |
| Evidence gate | Group sizes, effect size above a multiple-test chance level, difference above noise (Section 8.10) |
| Human in the loop | "Needs your eye" queue; manual corrections always win and never overwrite raw data |

---

## 8. The mathematics and physics

Every equation here is implemented in the code named next to it; the formal numbering (Eq. 3.x) matches METHODS_AND_MATH §3. For the talk, pick **two** pieces of math to show: the projectile/sensitivity result (8.4–8.5) and the gravity calibration (8.6). They are the most original and the easiest to explain.

**Symbols.** $t$ time (s); fps frame rate; $\Delta t = 1/\text{fps}$ (16.7 ms at 60 fps, 33 ms at 30 fps); $v$ release speed (m/s); $\theta$ release angle above horizontal; $h$ release height above the floor (m); $d$ horizontal distance from release to the board's front edge (m); $g = 9.80665$ m/s²; $m$ bag mass (0.4465 kg nominal); $\alpha$ deck slope (10.81°).

### 8.1 Coordinates and time

Image pixels $(u, v_{img})$ have $u$ right and $v_{img}$ down. Analysis axes: $x = s\,u$, $y = -v_{img}$, with $s = \pm1$ chosen so $+x$ points toward the target (a left-to-right throw and a right-to-left throw, and a left-hander, give identical numbers; tested in CALCULATION_AUDIT A1). Frame $f$ is at $t = f/\text{fps}$. Normalised movement time $\tau = (f - f_{start})/(f_{end} - f_{start}) \in [0,1]$, resampled at 101 points for waveform comparisons. Shoulder-relative, size-normalised points: $P_{norm} = (P - S)/L_{arm}$ (arm lengths).

### 8.2 Filtering and differentiation

**Butterworth low-pass** (`filtering.py`), 4th order, cutoff $f_c = 6$ Hz:

$$|H(f)|^2 = \frac{1}{1 + (f/f_c)^{2n}},\quad n = 4$$

applied forward and backward (`scipy.signal.sosfiltfilt`) so there is **zero phase lag**: peaks are not shifted in time, which matters for event timing. The double pass squares the response (−6 dB at $f_c$). Runs shorter than 15 samples are left raw with a warning; gaps are never bridged by the filter.

**Why 6 Hz: Winter's residual analysis** (`scripts/residual_analysis.py`). For trial cutoffs $f_c$ from 1 Hz upward, compute

$$R(f_c) = \sqrt{\tfrac1N\textstyle\sum_i \big(x_i - \hat x_i(f_c)\big)^2}$$

fit a line to the noise-dominated tail (12–20 Hz); its intercept estimates the noise RMS; choose the first $f_c$ with $R(f_c) \le$ that intercept. On 12 shoulder/elbow/wrist signals from two real 60 fps clips: median optimum **5.5 Hz** (range 3.5–7.5 Hz; wrist highest, 6–7.5 Hz) [REPO: METHODS §1.4]. Trade-off stated honestly: 6 Hz flattens fast peaks (peak wrist speed ≈ 5 % lower than at 12 Hz on 14 audited throws), but the same filter is used on every throw, so within-athlete comparisons are unaffected [REPO: CALCULATION_AUDIT B2].

**Finite differences** on each contiguous run (`numpy.gradient`, second-order edges):

$$\dot x_i \approx \frac{x_{i+1} - x_{i-1}}{2\Delta t}$$

**Why derivatives are dangerous (talk point).** Differentiation amplifies noise roughly by $1/\Delta t$ per derivative. With 4 px landmark noise at 60 fps a position is fine, a velocity is noisy, and an acceleration is mostly noise unless filtered (Winter, 2009). That is why peak elbow-extension speed is labelled *exploratory* and why force and power on the bag are only `measured` when the Monte Carlo interval is tight.

### 8.3 Joint and segment angles (all projected 2D)

**Included angle** at vertex $B$ with $\mathbf u = A - B$, $\mathbf w = C - B$ (numerically stable form, `geometry.vector_angle_degrees`):

$$\angle ABC = \operatorname{atan2}\big(|u_x w_y - u_y w_x|,\ \mathbf u\cdot\mathbf w\big)\cdot\frac{180}{\pi} \in [0°, 180°]$$

Elbow angle $= \angle SEW$ (180° = straight in the image).

**Arm angle** (from straight down, + toward the board), $\mathbf D = W - S$: $\varphi = \operatorname{atan2}(s\,D_u,\ D_v)$. 0° = hanging, +90° = pointing at the board, negative = behind the body (backswing).

**Trunk inclination**, $\mathbf T$ = shoulder midpoint − hip midpoint: $\beta = \operatorname{atan2}(T_x, T_y)$, 0° vertical, + toward the target.

**Shoulder angle (upper arm vs trunk)**, signed and continuous: $\psi = \operatorname{atan2}(D_xA_y - D_yA_x,\ \mathbf D\cdot\mathbf A)$ with $\mathbf D$ = hip mid − shoulder mid, $\mathbf A = E - S$, wrapped into $[-125°, 235°)$; reported as $180° - \psi$. *Why:* the plain included angle folds at 180° each time the arm passes the trunk line, which under-read range of motion by 11–65° on all 14 audited throws [REPO: CALCULATION_AUDIT A3]. Frames where the upper arm is foreshortened below 35 % of its length are missing.

**Tempo** = backswing duration ÷ forward-swing duration; **forward-swing time** = top of backswing → release.

**Pendulum drive ratio.** A uniform rod of length $L$ released from amplitude $A$ reaches at the bottom $\tfrac12\big(\tfrac13 mL^2\big)\omega^2 = mg\tfrac L2(1-\cos A)$, so

$$\omega_{passive} = \sqrt{\frac{3g(1-\cos A)}{L}},\qquad \text{ratio} = \frac{\omega_{measured}}{\omega_{passive}}$$

About 1 means a passive pendulum swing; above 1 means the athlete actively drives the arm. (A biomechanics talking point: the cornhole swing is close to, but faster than, a free pendulum.) Needs a metric scale.

**Hand point** (where the bag sits in the hand): $\mathbf H = \mathbf W + 0.34\,L_{arm}\,\widehat{(\mathbf W - \mathbf E)}$, a rigid-hand model, shown to fail in the last 50–80 ms before release (the wrist flexes), which is why release-timing sensitivity is unavailable (Section 14).

### 8.4 Projectile flight, deck contact and the speed to the hole

Drag-free point mass released at height $h$:

$$x(t) = v\cos\theta\; t,\qquad y(t) = h + v\sin\theta\; t - \tfrac12 g t^2$$

**Deck contact.** The deck surface is $y = h_f + (x - d)\tan\alpha$ with $h_f$ = 3 in and $\alpha = \arcsin(9/48) \approx 10.81°$. Substituting gives the contact time as the first positive root of

$$-\tfrac12 g t^2 + (v_y - v_x\tan\alpha)\,t + (h - h_f + d\tan\alpha) = 0$$

and the landing position up the deck $s = (v_x t - d)/\cos\alpha$ (on the board if $0 \le s \le 1.219$ m; the hole centre is at $s_{hole} = 0.9906$ m). The model also checks the floor (short) and the front face (if $y < h_f$ at $x = d$).

**Required speed through the hole centre** at angle $\theta$, with $X = d + s_{hole}\cos\alpha$ and $Y = h_f + s_{hole}\sin\alpha$:

$$v_{req} = \sqrt{\frac{g X^2}{2\cos^2\theta\,\big(h + X\tan\theta - Y\big)}}$$

**Minimum speed over all angles** ($\Delta y = Y - h$): $v_{min}^2 = g\big(\Delta y + \sqrt{X^2 + \Delta y^2}\big)$, reached at $\tan\theta^* = \big(\Delta y + \sqrt{X^2+\Delta y^2}\big)/X$.

### 8.5 Worked example and sensitivity (the key physics insight)

Using the engine's own model (`zones.landing`, `mechanics.landing_jacobian`, `attribution.carry_sensitivity`) at a typical release of our athletes: $v$ = 7.5 m/s, $\theta$ = 40°, $h$ = 1.0 m, $d$ = 5.7 m [REPO: computed 12 Oct 2026 with the repository code]:

| Quantity | Value |
|---|---|
| Flight time to first contact | 1.12 s |
| First contact up the deck | 0.77 m (hole centre at 0.99 m), i.e. **22 cm short**, then the usual 0.4–0.55 m slide carries it toward the hole |
| Speed that lands exactly on the hole centre at 40° | 7.66 m/s |
| Minimum speed to reach the hole at any angle | 7.655 m/s, at $\theta^* \approx 41.8°$ |
| Kinetic / potential energy at release | 12.6 J / 4.4 J; momentum 3.35 kg·m/s |

**Sensitivity of first contact** at the speed that reaches the hole (central differences, Eq. 3.3.1):

| Release angle | Speed to hole (m/s) | Per +0.1 m/s | Per +1° | Per +1 cm height |
|---|---|---|---|---|
| 25° | 8.31 | +10.5 cm | +9.0 cm | +1.1 cm |
| 30° | 7.96 | +11.7 cm | +6.3 cm | +1.0 cm |
| 35° | 7.76 | +12.5 cm | +3.7 cm | +0.9 cm |
| **40°** | **7.66** | **+13.2 cm** | **+1.0 cm** | **+0.8 cm** |
| 45° | 7.68 | +13.7 cm | −1.8 cm | +0.7 cm |
| 50° | 7.80 | +13.9 cm | −5.0 cm | +0.6 cm |

And directly: at 40°, 1.0 m, 5.7 m, releasing at 7.3, 7.4, 7.5, 7.6, 7.7, 7.8 m/s puts first contact at 0.51, 0.64, 0.77, 0.91, 1.04, 1.18 m up the deck. A 0.5 m/s range sweeps the whole upper half of the board.

**What to say about this.**

1. Near 40–42° the landing is almost insensitive to angle (this is the minimum-speed angle, where $\partial x/\partial\theta \approx 0$). Our athletes' median release angles are 37–44° [CHECK], i.e. they already throw in the angle-forgiving region (consistent with Venkadesan & Mahadevan, 2017, who show accurate throwers release slightly above the minimum speed where errors matter least).
2. In that region **speed is the dominant lever**: about 13 cm (5 in) of carry per 0.1 m/s. Our athletes' throw-to-throw speed SD of 0.21–0.44 m/s [CHECK] therefore implies ±28–58 cm of first-contact spread from speed alone, a large share of a 1.22 m deck.
3. Flatter throwers (25–30°) are 6–9× more sensitive to angle. So the "right" angle advice depends on the athlete, which is why the app gives a personal green zone, not a universal target.
4. At the regulation distance (release ≈ 7.7 m from the board front) the speed to the hole at 40° is 8.86 m/s, so our results (5.3–5.9 m) do **not** transfer directly to regulation play (Section 14).

### 8.6 Camera geometry and the gravity-calibrated scale

**Pinhole camera** from an assumed horizontal field of view (image width $W$, height $H_{img}$):

$$f = \frac{W/2}{\tan(\text{HFOV}/2)},\qquad K = \begin{pmatrix} f & 0 & W/2\\ 0 & f & H_{img}/2\\ 0 & 0 & 1\end{pmatrix},\qquad \lambda\,(u,v,1)^\top = K\,[R\,|\,\mathbf t]\,(\mathbf X, 1)^\top$$

**PnP (perspective-n-point).** The four deck corners have known 3D positions on the sloped board, e.g. $(0, h_f, \mp w/2)$ and $(L\cos\alpha, h_f + L\sin\alpha, \pm w/2)$. OpenCV `solvePnP` (IPPE, planar) finds the board's rotation $R$ and translation $\mathbf t$ relative to the camera.

**Throw-plane homography.** The vertical plane $z = 0$ through the board's centre line maps to the image by $H_{plane} = K[\mathbf r_1\ \mathbf r_2\ \mathbf t]$; image points map back to metres by $H_{plane}^{-1}$. The out-of-plane angle of the throw line is $\phi = \arcsin|R_{31}|$ (> 20° flagged, after Sih et al., 2001).

**Deck homography** (image → board inches, top-down): the 3×3 $H$ mapping the four corners to $(0,0), (24,0), (24,48), (0,48)$, solved exactly (four-point DLT). Valid only for points on the deck plane.

**The gravity trick (the most original piece of math; show it in the talk).** A single image of the board cannot separate "wide lens, close" from "narrow lens, far": both put the corners in the same pixels but disagree on the scale everywhere else. The bag's free flight breaks the tie. For each candidate HFOV, re-solve PnP, map the flight into the throw plane, fit $y(t) = c_0 + c_1 t + c_2 t^2$, and solve

$$a_y(\text{HFOV}) = 2c_2 = -g$$

by grid bracketing (0.25°) and bisection. Search range 45–85° (reported band 55–75°); per-throw values are noisy (51–65°), so the median over all throws from the same phone, date and tripod position is used. Status `measured` only for a pool of ≥ 3 measured throws with IQR ≤ 6°. Uncertainty for the Monte Carlo: $\sigma_{rel} = \max\big(0.01, |q(\widetilde{HFOV} + IQR/2) - q(\widetilde{HFOV} - IQR/2)|/2q\big)$. Drag biases apparent $g$ by only −0.2 to −1.4 % in simulation (0.454 kg bag, $C_DA$ 0.006–0.024 m²) [REPO: METHODS §1.8, §3.8].

*Honest caveat:* on the Final Data Collection the side camera's first tripod position gave a session spread of 7.1° IQR, so on 45 of 92 throws release speed comes from the flight's own gravity scale ($q = a/g$ px/m) rather than the board-plane fit [REPO: VALIDATION_PLAN].

### 8.7 Bag tracking mathematics

**Kalman filter + RTS smoother** (`bag_filter.py`), per image axis, state $\mathbf s = (p, \dot p, \ddot p)$, constant-acceleration (white-noise jerk) model:

$$\mathbf s_{k+1} = F\mathbf s_k + \mathbf w_k,\quad F = \begin{pmatrix}1 & \Delta t & \tfrac12\Delta t^2\\ 0 & 1 & \Delta t\\ 0 & 0 & 1\end{pmatrix}$$

Measurement noise is estimated from third differences ($\operatorname{Var}(\Delta^3 z) = 20\sigma^2$ for white noise, so $\hat\sigma = 1.4826\,\text{MAD}(\Delta^3 z)/\sqrt{20}$); process noise and $\sigma$ are chosen by maximum innovation likelihood; a leave-one-out gate flags points more than $\max(5\hat\sigma, 4\text{ px})$ from a quadratic through their ±5-frame neighbours. Forward Kalman filter, then the Rauch–Tung–Striebel backward pass. Acceleration is estimated, not fixed to $g$, so perspective is absorbed. Nothing is extrapolated beyond the measured ends.

**Launch fit** (`bag.py`): Huber-weighted (IRLS) least squares, weights $w_i = 1$ if $|r_i| \le 1.345\hat s$ else $1.345\hat s/|r_i|$, $\hat s = 1.4826\,\text{MAD}$. Gravity-constrained version with scale $q$ (px/m), image $y$ down:

$$y(t) - \tfrac12 g q\, t^2 = a_y + b_y t,\qquad x(t) = a_x + b_x t$$

$v_x = s\,b_x$, $v_{up} = -b_y$, $v = \sqrt{v_x^2 + v_{up}^2}$, $\theta = \operatorname{atan2}(v_{up}, v_x)$. Covariance $s^2(X^\top W X)^{-1}$; delta-method standard errors

$$\sigma_\theta^2 = \frac{v_y^2\sigma_x^2 + v_x^2\sigma_y^2}{v^4},\qquad \sigma_v^2 = \frac{v_x^2\sigma_x^2 + v_y^2\sigma_y^2}{v^2}$$

These cover tracking noise inside the window only, so they are a lower bound on the true uncertainty (say this if asked).

### 8.8 Bag energy, momentum, force and power; Monte Carlo

$$\mathbf p = m\mathbf v,\quad KE = \tfrac12 m|\mathbf v|^2,\quad PE = mgh,\quad \mathbf F = m(\mathbf a - \mathbf g),\quad P = \mathbf F\cdot\mathbf v \ \ \text{(checked against } dE/dt\text{ within 10 \%)}$$

Monte Carlo (500 draws): scale factor $\sim\mathcal N(1, \sigma_{rel})$, mass $\sim\mathcal U(15.5, 16.0)$ oz, fit errors on speed/angle/height, and 4 px landmark noise passed through the same 6 Hz filter (4 px motivated by the 16–48 mm markerless joint-centre error of Needham et al., 2021). 95 % interval = 2.5th–97.5th percentile. These are **bag-only** quantities, never muscle or joint loads.

### 8.9 Two-camera mathematics

**Sound sync.** $e(t) = 20\log_{10}\big(\text{RMS}_{5\,ms}[\text{HP}_{300\,Hz}(s)](t)\big)$, $\tilde e = e - \text{median}_{1\,s}(e)$; offset $\tau$ maximises the normalised cross-correlation of $\tilde e_{side}$ and $\tilde e_{front}$; $t_{front} = t_{side} + \tau + \ell$ ($\ell$ = pooled picture lag).

**3D bag flight** (front_view's world frame: $X$ thrower's right, $Y$ along the throw, $Z$ up):

$$Y(\tau) = a_0 + a_1\tau + a_2\tau^2,\quad Z(\tau) = b_0 + b_1\tau + b_2\tau^2,\quad X(\tau) = X_0 + V_x\tau$$

$Y, Z$ from the side camera (refitted at the bag's own lateral position each iteration); $X$ is linear because nothing pushes a drag-free bag sideways. The front camera's images give $X_0, V_x$ by minimising $\sum_k \rho\big(\|\pi_k(\mathbf P(\tau_k + \delta); h) - \mathbf p_k\|\big)$ with a soft-L1 loss, timing offset $\delta$ and front FOV $h$ as nuisance parameters. Lateral launch angle $= \operatorname{atan2}(V_x, a_1)$.

**Miss attribution, left/right (an exact identity).** With $D$ = horizontal distance from release to first contact:

$$\Delta x_{rest} = \underbrace{X_0}_{\text{release position}} + \underbrace{D\tan\psi}_{\text{aim}} + \underbrace{(x_{rest} - x_c)}_{\text{slide drift}} + r_x$$

**Short/long, split against the athlete's usual** (median over their other throws, ≥ 8):

$$\Delta y_{rest} = \underbrace{(\tilde y_c - 39) + \tilde s}_{\text{usual spot}} + \underbrace{(y_c - \tilde y_c)}_{\text{carry}} + \underbrace{(s - \tilde s)}_{\text{slide}}$$

**Naming rule.** A part is named only when $|p| \ge 2\sigma_p$, $|p| \ge 3$ in (the hole radius: a smaller part could not by itself turn a hole into a miss), $|p| \ge 40\,\%$ of that axis's miss, and it has the same sign as the miss; at most two parts per throw. Noise per part: release position 1.2 in, aim $D\tan 0.5° \approx$ 2.4 in, slide drift 1 in, carry and slide 2 in. Release speed is named as the driver of a carry only when $|\Delta v| \ge 0.15$ m/s, implying $\Delta v\cdot\partial s/\partial v$ of carry with $\partial s/\partial v \approx 1.33$ m per m/s at our median release (the flat-ground $2R/v \approx 1.8$ overstated it by 35 %) [REPO: METHODS §5.5, METRICS "Miss attribution"].

### 8.10 Statistics

| Tool | Formula / rule | Why this one |
|---|---|---|
| Median, IQR, robust SD | Quartiles by linear interpolation; robust SD ≈ IQR/1.349 or 1.4826 × MAD | Small, skewed samples; one wild throw should not dominate |
| Sample SD, CV | $s = \sqrt{\frac{1}{n-1}\sum(x_i - \bar x)^2}$; CV = 100 s/x̄ (ratio scales only); SD withheld below 5 values | — |
| Cliff's δ | $\delta = \dfrac{\#\{a_i > b_j\} - \#\{a_i < b_j\}}{n_a n_b} \in [-1, 1]$ (scored $a$ vs missed $b$) | Nonparametric effect size, no normality assumption, interpretable as P(scored > miss) − P(scored < miss) |
| Critical δ | $\delta_{crit} = \max\!\Big(0.474,\ z_{1-\alpha/(2k)}\sqrt{\dfrac{n_a + n_b + 1}{3n_an_b}}\Big)$ | 0.474 = "large" (Romano et al., 2006, citation to add); Bonferroni over $k$ tests. With $k$ = 24: 1.18 at 5+5 (no claim possible), 0.92 at 8+8, 0.81 at 10+10, 0.74 at 12+12, 0.66 at 15+15 [REPO: computed] |
| Minimum group size | `performance.minimum_claim_group`: smallest $n$ per group at which even perfect separation can pass | 7 per group at $k$ = 24, 8 at $k$ = 32 |
| Hedges' $g$ | $g = \dfrac{\bar a - \bar b}{s_p}\Big(1 - \dfrac{3}{4(n_a+n_b) - 9}\Big)$ | Reported alongside δ for readers who expect a standardized mean difference |
| Spearman ρ + bootstrap CI | Rank correlation; 2000 resamples, fixed seed, percentile 95 % CI; only with ≥ 8 pairs; "supported" when the CI excludes 0 | Monotonic links (not necessarily linear), robust to outliers |
| Bootstrap CI of a median difference | Same resampling on miss − scored medians | Priority check 3 ("repeatable") |
| Theil–Sen slope | Median of pairwise slopes of speed on angle, with 95 % CI | Speed–angle trade-off, robust to outliers; no fixed "best angle" (Linthorne, 2001) |
| Compensation (permutation) test | ratio = mean SD(landing with speeds randomly re-paired) / SD(observed landing), 500 permutations | Do speed and angle errors cancel? (Müller & Sternad, 2004, "covariation" component) |
| Error budget | $\sigma^2_{R,ind} \approx \sum_q (\partial R/\partial q\ \sigma_q)^2$ vs $\sigma_{R,cov} = \sqrt{\mathbf J\Sigma\mathbf J^\top}$ | Which release variable's variability costs the most landing spread, with and without covariation |
| ICC | Front measures: ICC(1,1) one-way, kept when ≥ 0.75 ("good", Koo & Li, 2016). Metric review: ≈ between² / (between² + within²) | Is a measure an athlete trait (high ICC) or a throw-to-throw signal (low ICC)? |
| Smallest worthwhile change | 0.2 × between-throw SD (Hopkins) | Recorded as the smallest difference worth discussing (citation to add) |

### 8.11 The personal green zone (motor abundance made practical)

Green = predicted first contact on the deck from (slide allowance) short of the hole centre to the hole's far edge, where slide allowance = the athlete's own median measured slide (≥ 3 slides, clipped to 0.10–0.70 m; else 0.45 m). For every aim point $(v, \theta)$, the probability that a release scattered by the athlete's own SDs lands green:

$$P_{green}(v,\theta) = \iint \mathbb 1_{green}(v', \theta')\,\mathcal N(v' - v; \sigma_v)\,\mathcal N(\theta' - \theta; \sigma_\theta)\,dv'\,d\theta'$$

computed as a Gaussian blur of the green map on a 0.02 m/s × 0.5° grid. The **best aim** is the arg-max within the athlete's observed angle range ± 8° (a change they can actually make). Interpretation: there is no single right speed or angle but a set of combinations that reach the hole (Bernstein's motor abundance; Müller & Sternad, 2004); the best release is where that set is widest relative to the athlete's own variability. Model check on Player 1's 11 scaled tripod throws: model 40 % vs observed 42 % (5/12) hole rate [REPO: METHODS §1.13].

### 8.12 Slide on the deck

For a bag sliding up the slope, $a = g(\sin\alpha + \mu\cos\alpha)$, so the effective kinetic friction is $\mu = a/(g\cos\alpha) - \tan\alpha$, from a least-squares fit $s(t) = s_0 + v_0 t - \tfrac12 a t^2$ starting 2 frames after touchdown. Withheld for short slides, $\mu < 0$, or SE($\mu$) > 0.10. After the audit, 24 slides report $\mu$ = 0.31–1.17 (median 0.52), none negative [REPO: CALCULATION_AUDIT B3]. μ is research-only in the app.

---

## 9. The biomechanics reasoning

### 9.1 The hierarchy: why we start at release and look back to the body

```
 body movement → release conditions → bag flight → first contact → slide → rest → points
   (indirect)       (proximal cause)     (physics)     (measured)    (board)
```

- **Release conditions are the proximal determinant of landing.** After the bag leaves the hand, its path is set by release speed, angle, height and direction (projectile physics, Section 8.4). So the verdict starts at release and only then looks back to the body.
- **The body matters through consistency of release.** A body feature can only change the outcome by changing release conditions or the slide. So body → release links are measured (evidence chain), and body features are compared with the athlete's own usual, not with a template.
- **Speed is the dominant cue near typical releases.** 0.1 m/s ≈ 13 cm vs 1° ≈ 1 cm at 40° (Section 8.5); speed is also trainable through swing length and tempo.
- **Accuracy, not one ideal form.** Experts reach accuracy with different strategies, either by reducing timing sensitivity (hand path) or by reducing timing error (Nasu et al., 2014); the best release angle is athlete-specific (Linthorne, 2001). Hence every comparison is within athlete.
- **Slightly faster than the minimum.** The most accurate throws sit slightly above the minimum speed that reaches the target, where errors cost least (Venkadesan & Mahadevan, 2017). The app reports speed margin over minimum and energy match, not a fixed speed target.
- **Variability can be functional.** Errors in one release variable can be offset by another (Müller & Sternad, 2004: tolerance, noise and covariation). The compensation test and the covariance-aware error budget tell the coach whether to train the *combination* or each variable.
- **Sequencing is described, not graded.** The shoulder → elbow → wrist-speed → release peak order is shown (Putnam, 1993), but cornhole is a slow accuracy swing, so no proximal-to-distal "grade" is applied.
- **Timing of release.** Skilled throwers time release to the millisecond (Hore & Watts, 2011). At 60 fps one frame is 16.7 ms, so we report timing to a frame and say so; release-timing sensitivity was defined but is unavailable on our footage (the rigid-hand model fails in the last 50–80 ms).

### 9.2 The movement measured, phase by phase

| Phase | What we measure (camera) | Biomechanical meaning |
|---|---|---|
| Set-up | Stance width and offset, set-up trunk lean (front) | Base of support, alignment with the board |
| Backswing | Backswing angle (min arm angle φ), backswing duration (side) | Swing amplitude: potential energy available to a pendulum-like swing |
| Forward swing | Forward-swing time, tempo, peak wrist speed and its timing, peak elbow extension speed (exploratory), shoulder angle (side); hand-path sideways range, trunk lean change (front) | How the athlete generates and controls release speed; whether the hand path stays in the throw plane |
| Release | Release speed, angle, height, point, launch direction, sideways release position (side + 3D); elbow, arm angle, trunk lean, hand across body at release | The conditions that determine the flight |
| Flight | Arc, apex, time of flight, drag-free model residual (side), 3D path (both) | Check of the projectile model |
| Landing | First contact along (side) and across (front), touchdown, slide length, entry speed, μ (research), rest, hole/board/off | Where the throw was decided: in flight or on the board |

### 9.3 Which metrics are worth showing: the metric review

Measured on the 92-throw library [REPO: METRICS "Metric review (2026-10-12)"]. *SD within* = throw-to-throw SD inside an athlete; *SD between* = SD of athlete means; *ICC* ≈ between²/(between² + within²), the share of variation that is athlete-to-athlete (4 athletes, indicative only); *Within/noise* ≥ 1 means one throw can differ from usual by more than the measurement resolves.

| Metric | Usable | SD within | SD between | Noise floor | ICC | Within/noise | Tier |
|---|---|---|---|---|---|---|---|
| Release speed (m/s) | 96 % | 0.32 | 0.04 | 0.15 | 0.01 | 2.1 | per throw |
| Release angle (°) | 97 % | 4.3 | 3.4 | 3.0 | 0.38 | 1.4 | per throw |
| Release height (m) | 96 % | 0.09 | 0.06 | 0.03 | 0.31 | 2.9 | per throw |
| Release point (arm lengths) | 97 % | 0.11 | 0.13 | 0.05 | 0.59 | 2.1 | per throw |
| Forward swing time (s) | 97 % | 0.050 | 0.065 | 0.035 | 0.62 | 1.4 | per throw |
| Tempo (back ÷ forward) | 93 % | 0.31 | 0.27 | 0.15 | 0.42 | 2.1 | per throw |
| Peak wrist speed (arm lengths/s) | 85 % | 0.43 | 0.74 | 0.3 | 0.75 | 1.4 | athlete profile |
| Peak wrist speed timing (ms) | 83 % | 20 | 23 | 35 | 0.59 | 0.6 | athlete profile |
| Backswing (°) | 100 % | 4.3 | 20.3 | 5 | 0.96 | 0.9 | athlete profile |
| Trunk lean at release (°) | 97 % | 2.4 | 7.2 | 5 | 0.90 | 0.5 | athlete profile |
| Elbow angle at release (°) | 67 % | 2.4 | 4.5 | 10 | 0.77 | 0.2 | advanced |
| Arm angle at release (°) | 68 % | 6.7 | 6.7 | 5 | 0.50 | 1.3 | advanced |
| Peak elbow extension speed (°/s) | 70 % | 29 | 54 | 150 | 0.78 | 0.2 | advanced (exploratory) |

**How to explain the tiers in one breath:** *per-throw* metrics change from throw to throw by more than their noise, so they can explain a single miss; *athlete-profile* metrics are strongly individual (high ICC) but stable, so they describe how someone throws (useful for recruiting and for not coaching away a working style); *advanced* metrics are too often withheld or vary less than their noise floor, so they stay in "All measurements". Elbow angle at release left the headline tiles for this reason.

**Noise floors** (smallest difference interpreted) and their basis: release speed 0.15 m/s (~2 × typical fit SE at 60 fps); release angle 3° or 2 × median per-throw fit SE; height 0.03 m; release point 0.05 arm lengths; wrist speed 0.3 arm lengths/s (~4 px noise differentiated); peak timing 35 ms (±1 frame on peak and release); arm angle and backswing 5° (~4 px over ~100 px); elbow 10° (simulated 4 px noise); forward-swing time 0.035 s (±2 frames); tempo 0.15; trunk lean 5°. Front: heading 0.5°, hand across body 0.15 shoulder widths, trunk side lean 6°, release offset 0.03 m, hand-path range 0.05 sw, trunk lean change 1.5° [REPO: METHODS §1.14, METRICS]. **Most body floors are provisional** until the blinded validation (Section 11.3).

### 9.4 What we deliberately do not measure (and why)

Joint moments, joint or muscle forces (no force plates, segment inertias or 3D kinematics, so no inverse dynamics); wrist flexion/"snap" and grip (no hand keypoints); trunk axial rotation (needs 3D); bag spin (would need a high-speed close view); 3D joint angles (two uncalibrated 2D views). Force on the bag is reported only as "bag-only". Saying what you don't claim is a strength in Q&A.

---

## 10. Feedback design: from numbers to a coach's next throw

### 10.1 Principles (each is a design decision you can defend)

1. **Outcome first.** A made throw gets no corrections ("In the hole. Nothing to change."). Advice for a board bag or miss starts from where the bag actually stopped, signed short/long and left/right, not from the model alone (peer review: "what if the app says too fast but it landed next to the target?").
2. **Bandwidth feedback.** A miss within one robust SD of the athlete's usual spread on both axes gets "Normal spread: keep the same throw." Feedback only when outside the normal band (bandwidth knowledge-of-results; citation to add, e.g. Sherwood 1988 or a motor-learning text [FILL]).
3. **No cue after an odd slide.** A miss named as "slide" gets no aim change: moving the aim point after one random slide only adds variance (Deming's funnel experiment; citation to add [FILL]).
4. **One cue at a time.** At most two named parts and one next-throw cue per throw.
5. **Associations, not causes.** Never "because", "caused", "fault" or "should"; a test runs the sentence builder over 1,800 synthetic cases to enforce it [REPO: METHODS §5.5].
6. **Body measures are athlete-level, not per-throw.** No per-throw model links a body measure to where the bag went, so body measures appear as evidence in the explanation and in the athlete summary under the evidence gate, never as the named cause of one miss.
7. **No composite scores.** Removed because their weights had no empirical basis.

### 10.2 What the coach sees for one throw

**The sentence (sentence_v2):** `[Result]: [N in short/long], [N in left/right]. [Largest named part]. [Cue].`
Example from the methods: *"Board: 9 in short, 8 in right. Most of the short came from the carry (it landed 11 in shorter than usual, about 0.4 m/s slower release). Next: throw a touch harder."*

**The four-part explanation (attribution_v2):**

| Part | Content |
|---|---|
| Observed | Where it stopped; first contact against the usual spot or the hole; the slide |
| Measured evidence | Named parts; release speed, angle and launch direction that differ from the usual by more than their noise, with the carry each implies; front-camera body measures at release that differ by ≥ 2× their noise |
| Possible explanation | Only where geometry or the drag-free flight ties a measured difference to the miss (launch line → lateral contact; release-speed change → carry); otherwise it says the measured release does not account for the miss |
| What to review | What to look at on video, tied to that evidence |

`phase` separates a miss made **in the flight** (release position, aim, carry) from one made **after landing** (slide).

**The throw report** (top to bottom): result chip and sentence → board from above to scale (first contact ring, slide arrow, rest, precision ellipse, ghost of the usual) → miss breakdown bars with noise bands → release vs your usual (dot among the athlete's other throws) → replay (side, front, both synchronised, animation with side + top views, the 3D path drawn solid where seen and dashed where modelled) → Details (scientific tables, quality, provenance). Export Figure saves a PNG for slides [REPO: APP_GUIDE].

### 10.3 What the coach sees across a session

- **Take screen:** four throws side by side, synchronised video, board from above, points and In/On/Off, release bag by bag vs the athlete's usual band (shows drift within a take).
- **Needs your eye:** only the throws the cameras were unsure about, one at a time, with In/On/Off keys. A person's answer is never overwritten by re-analysis.
- **Athlete summary:** scoring tiles; coach focus (priorities that passed the five-check gate, and "observed differences, not yet advice"); sortable throw table with Median · SD footer (SD withheld below 5 values); release map; evidence chain; data trust counts; compensation.
- **Personal green zone:** "Aiming for about 38° at 7.6 m/s instead of the usual 44° at 7.5 m/s would raise the model's chance of reaching the hole window from 57 % to 62 %, with this athlete's current consistency." (Player 1) [CHECK]
- **Launch Lab:** a to-scale board with an animated drag-free flight; sliders for speed, angle, height, distance; a success map; sensitivities in cm per 0.1 m/s, per 1°, per 1 cm.
- **Print Report (PDF):** cover with counts and PPR, where the bags landed, release conditions by outcome, consistency vs noise floor, miss explanations, scored vs missed with "how many throws a claim needs", and a limitations box.

### 10.4 The five-check coaching priority gate

A movement feature becomes a **priority** only if it is (1) associated with scoring (Cliff's δ above the Bonferroni critical δ and ≥ 0.474, ≥ 5 throws per group); (2) larger than measurement noise; (3) repeatable (bootstrap 95 % CI of the miss − scored median difference excludes 0); (4) measured reliably on ≥ 80 % of the athlete's throws; (5) interpretable and modifiable (not an exploratory derivative). A difference above noise with |δ| ≥ 0.33 that fails a check is shown as an **observed difference, not advice**, with the failed checks named. A priority names the athlete's typical scored throws to review on video.

---

## 11. Validation and reliability: what we know, what we don't, and the plan

Be precise in the report about three different things: **software verification** (does the code compute what we intended?), **measurement validation** (is it accurate against a criterion?), and **analysis validity** (do the statistics avoid false claims?).

### 11.1 What has been verified or checked

| Evidence | Result | Source |
|---|---|---|
| Automated tests | ≈ 640 Python tests and 87 Swift tests pass (644 / 87 on 12 Oct 2026); CI on Python 3.11 and 3.12 | RECOVERY_STATUS |
| Known-answer calculation audit | 27 tests against closed-form synthetic movements; 3 defects fixed (shoulder-angle fold, motion-end erosion, negative friction), 1 found and wired (plane launch fit), 3 limitations quantified | CALCULATION_AUDIT |
| Release frame (pilot) | 21/21 accepted flights within ±1 frame of visual release (19 exact) | METHODS §1.9 |
| Release proxy without a flight | −2 to +1 frames on 13 audited throws (in-sample; ±2 frames stated) | METHODS §1.9 |
| Board phase end (tripod clips) | 10/10 correct, including a 0.6 s lip hang then drop | METHODS §1.9 |
| Sound sync | All 23 pairs accepted, r = 0.44–0.74, margin 0.10–0.35; uncertainty ±17.5 ms | METHODS §5.1 |
| 3D flight agreement | Landing across: median 0.8 in from the front camera's measured contact, 86 % within 2 in; launch angle vs heading median 0.34°; release position vs pose hand median 1 cm | METHODS §5.4 |
| 3D flight synthetic test | Known projectile with clutter: $X_0$ within 2 cm, $V_x$ within 0.04 m/s, timing to ±10 ms | tests/test_flight3d.py |
| Front body reliability | Hand-path range ICC 0.89, trunk lean change ICC 0.77 (kept), hip sway ICC 0.66 (dropped) | METHODS §5.2 |
| Pilot internal consistency | Bag found in a median 100 % of flight frames; jitter 0.49 px; drag-free residual 3–17 px | LIGHT_VALIDATION |
| Sensitivity to tracker choice | Changing only the bag-centre method moved release by median 0.8° / 0.08 m/s / 1.6 cm: the same order as the noise floors | LIGHT_VALIDATION |
| Preliminary visual check (one reviewer, not blinded) | Hole/board/off matched the frames on 8/8 random throws; front contact frame correct ±1 frame on 7/7; knocked-bag rule fixed after 3 of 4 flags were false | VALIDATION_PLAN |
| Personal zone model check | Player 1: model 40 % vs observed 42 % hole rate (11 scaled tripod throws) | METHODS §1.13 |

### 11.2 Analysis validity: the stress test

Simulated athletes with a **known** cause of misses, 200 sessions per cell, realistic measurement noise (speed 0.12 m/s, angle 1°, height 2 cm) [REPO: STRESS_TEST]:

| Athlete type | 10 throws | 20 throws | 40 throws |
|---|---|---|---|
| Novice, inconsistent speed: any claim / correct variable | 0 % | 56 % (speed 55 %) | 94 % (speed 94 %) |
| Intermediate, inconsistent angle | 0 % | 14 % (angle 13 %) | 47 % (angle 43 %) |
| Pro, misses from bag behaviour (no release cause) | 0 % | 0 % | 4 % |
| Null (outcome unrelated to release) | 0 % | 1 % | 3 % |

**Reading:** false claims stay at or below about 5 %; real causes need roughly **20–40 throws per athlete**; the physics-based priority (spread ÷ green window) names the true release driver even with 10 throws and correctly says "not a release problem" for the pro. Note: the stress test predates the stricter Bonferroni gate, so current power is lower still (for a true δ ≈ 0.6, a 20–24-throw athlete gets a finding 12–22 % of the time) [REPO: METHODS §2.4].

### 11.3 What has NOT been validated (say this plainly)

There is **no criterion validation yet** against motion capture or blinded manual digitisation for this task. Landmark, bag-centroid and metric-scale accuracy are therefore unknown; body noise floors are provisional. The validation plan, agreed before looking at results [REPO: VALIDATION_PLAN]:

| Quantity | Reference | Acceptance |
|---|---|---|
| Release frame (side) | manual first free frame | median \|error\| ≤ 1 frame, 90 % ≤ 2 |
| First contact (side, front) | manual first frame on the deck | ≤ 1 frame on 90 % |
| Camera sync | clap and impact frames | ≤ 17 ms |
| Contact and rest on the board | manual points on the front deck | ≤ 2 in across, ≤ 3 in along |
| Outcome | recorded result | ≥ 95 % agreement, every disagreement explained |
| Knocked-bag identity | manual | no silent wrong bag |
| Release speed and angle | manual centroids over 0.12 s, same fit | within 0.15 m/s and 3° |
| Joint landmarks at release | manual landmarks | median ≤ 4 px |

Sample: 20 throws (5 per athlete, chosen before looking), stratified by outcome, including knocked bags, the throws without a 3D flight and Player 3; a second rater on 5 throws for inter-rater agreement; Bland–Altman bias and limits of agreement per athlete and pooled. Tools exist: `tools/annotator.html` (blinded), `annotation-frames`, `validate-tracking`, `bag-benchmark`. **[FILL: if the team runs any of this before 20 Oct, put the results here; even 5 throws would strengthen the report a lot.]**

---

## 12. Results and insights from the 92 real throws

> **Before you present any number in this section:** the per-athlete values below were read from the athlete dashboards saved on `main` on 12 October 2026 [CHECK]. Some throws still have no confirmed result (they wait in "Needs your eye"), so counts and PPR will change once those are confirmed. Re-read each athlete summary in the app (or print the PDF report) and update the tables. Library-level numbers marked [REPO] come from the method documents.

### 12.1 Data set

| | Player 1 | Player 2 | Player 3 | Player 4 | All |
|---|---|---|---|---|---|
| Takes (two-camera) | 7 | 5 | 5 | 6 | 23 |
| Throws | 28 | 20 | 20 | 24 | 92 |
| Throwing hand | right | right | right | right | |
| Release → board front (median, m) [CHECK] | 5.76 | 5.88 | 5.31 | 5.49 | 5.3–5.9 |
| Data trust: calibration grade [CHECK] | WARNING (20/28) | WARNING (14/20) | GOOD | GOOD | |
| Share of coach metrics reliable [CHECK] | 85 % | 79 % | 95 % | 97 % | |

### 12.2 Outcomes

From the dashboards [CHECK]:

| | Player 1 | Player 2 | Player 3 | Player 4 |
|---|---|---|---|---|
| Hole / Board / Off / no result yet | 8 / 18 / 2 / 0 | 0 / 6 / 7 / 7 | 2 / 5 / 8 / 5 | 8 / 8 / 8 / 0 |
| In / On / Off % (of known results) | 29 / 64 / 7 | 0 / 46 / 54 | 13 / 33 / 53 | 33 / 33 / 33 |
| PPR (4 × points per bag, known results) | 6.0 | 1.85 | 2.93 | 5.33 |
| First-contact grouping, RMS radius (in) | 7.8 (n 28) | 8.6 (n 11) | 12.6 (n 13) | 9.5 (n 22) |

From the two-camera results over the whole library: **18 holes, 38 board, 36 off** [REPO: METHODS §5.5, 11 Oct]. The dashboards hold 18 / 37 / 25 with 12 throws still without a recorded result. **Reconcile these after confirming the "Needs your eye" throws** and use one set of numbers everywhere.

### 12.3 Release profiles (median, with throw-to-throw SD) [CHECK]

| | Player 1 | Player 2 | Player 3 | Player 4 |
|---|---|---|---|---|
| Release speed (m/s) | 7.49 (0.21) | 7.55 (0.24) | 7.56 (0.35) | 7.46 (0.44) |
| Release angle (°) | 44.2 (2.9) | 41.9 (3.8) | 40.3 (5.6) | 37.5 (3.6) |
| Release height (m) | 1.01 (0.06) | 0.96 (0.06) | 1.08 (0.10) | 0.94 (0.12) |
| Backswing (arm angle, °) | −45 | −32 | −78 | −58 |
| Trunk lean at release (°) | 22 | 11 | 12 | 4 |
| Tempo (back ÷ forward) | 1.46 (0.08) | 1.73 (0.13) | 1.89 (0.52) | 1.81 (0.32) |
| Elbow at release (°, projected) | 162 | 151 | 155 | 157 |
| Least consistent feature (SD ÷ noise) | release height (2.1×) | release height (2.2×) | tempo (3.5×) | release height (3.9×) |

### 12.4 Evidence chain (within-athlete Spearman ρ, bootstrap 95 % CI; "supported" = CI excludes 0, n ≥ 8) [CHECK]

| Link | Player 1 | Player 2 | Player 3 | Player 4 |
|---|---|---|---|---|
| Release angle → apex height (physics check) | **0.85** | **0.97** | **0.86** | **0.80** |
| Wrist speed at release → release speed (body → release) | **0.55** | 0.23 (n 9) | 0.51 | **0.70** |
| Arm angle at release → release angle | 0.32 | −0.45 (n 9) | **0.68** | −0.16 |
| Release speed → flight time | −0.32 | 0.06 | 0.13 | 0.00 |
| Release angle → points | 0.00 | −0.46 | −0.11 | 0.18 |
| Release speed → points | 0.21 | 0.23 | 0.04 | 0.04 |
| Peak wrist timing → points | 0.14 | n < 8 | 0.52 | 0.14 |

**Bold = supported.** The physics links hold for every athlete (a built-in sanity check that the measurements are coherent). Some body → release links are supported. **No release → points or body → points link is supported** for any athlete yet; with 20–28 throws and many outcomes being decided on the board, that is expected (Section 11.2).

### 12.5 Miss attribution over the library [REPO: METHODS §5.5, 11 Oct 2026]

- Tiers: 10 throws within the athlete's normal spread ("keep the same throw"), 17 "physics" (a named release-speed or launch-direction change next to the part), 65 "geometry" (18 of them holes).
- Named parts: **carry 24, slide drift 15, aim 13, slide 13**, release position 2. Release speed named on 13 throws, launch direction on 12. No named part disagrees in sign with the miss.
- 27 throws get a cue: 12 "softer", 8 "harder", 6 aim, 1 release spot.
- Left/right closure (3D flight vs measured contact): median |0.8| in, 90th percentile 2.3 in.

### 12.6 Coaching outputs per athlete [CHECK]

| | Priorities passed | Observed differences (not advice) | Personal green zone: usual → suggested aim (model P(hole window)) | Speed–angle compensation |
|---|---|---|---|---|
| Player 1 | none | none | 44° at 7.5 m/s → 38° at 7.6 m/s (57 % → 62 %) | no (ratio 0.96) |
| Player 2 | none | misses: higher release angle (45° vs 41°), different sideways release point, height, heading; all fail "associated" and "repeatable" | 42° at 7.5 → 40° at 7.7 (48 % → 56 %) | **yes** (ratio 1.14: keep the combination) |
| Player 3 | none | misses: higher arm angle at release (72° vs 66°); fails 3 checks | 40° at 7.6 → 38° at 7.3 (32 % → 42 %) | not beyond chance (1.13) |
| Player 4 | none | none | usual 37° at 7.5 already in the best part (42 %); "the gain comes from repeating it" | no (1.05) |

### 12.7 The insights to lead with (talk and report)

1. **Speed consistency, not speed, separates these athletes.** Median release speed is 7.46–7.56 m/s for all four (between-athlete SD 0.04 m/s, ICC ≈ 0.01), but throw-to-throw SD ranges 0.21–0.44 m/s. At ~13 cm per 0.1 m/s, Player 4's speed spread alone implies about ±58 cm of first-contact scatter, Player 1's about ±28 cm. *Training implication:* speed-control drills (distance ladders, feedback on carry) for the less consistent athletes.
2. **They already throw at the forgiving angle.** Releases at 37–44° sit where 1° costs only ~1 cm. Angle drills would buy little; the green-zone suggestions move angle by 2–6° mainly to reach a wider part of the speed window.
3. **Style is individual and stable.** Backswing ranges from −32° to −78° across athletes (ICC 0.96) and trunk lean from 4° to 22° (ICC 0.90), yet both barely change from throw to throw. A template-based system would coach these differences away; ours treats them as the athlete's profile.
4. **Many misses happen after landing.** Slide and sideways slide are named about as often as carry. Board behaviour (landing spot, bag feel, slide) deserves practice time, and the app tells the coach when a miss was a slide, not a release problem, and gives no aim cue for it.
5. **Honest null result: no priorities yet.** With 20–28 throws, nothing passed the five-check gate. The system says how many throws a claim needs (about 7–8 per group at minimum; 20–40 per athlete in the stress test). This is a feature: the system refuses to invent advice.
6. **The physics model is coherent with the data.** Angle → apex is supported for every athlete; the personal zone model predicted 40 % vs 42 % observed for Player 1; 3D flight and front camera agree on lateral landing to under an inch.

---

## 13. How this benefits Vanderbilt Athletics

### 13.1 In practice: a week with the system

| When | What the coach does | What the system gives |
|---|---|---|
| Set-up (≈ 10 min [FILL: time it]) | Two phones on tripods: side of the lane, behind the board; clap at the start of each take | — |
| During practice | Athletes throw takes of 4 bags; coach watches as usual | Videos recorded |
| After practice | Drop the take folder on the app | Synced, cut, analysed throws (~2 min each, one at a time); automatic hole/board/off |
| 2–5 min review | Answer "Needs your eye" for unsure throws | Confirmed outcomes |
| Coaching | Read one sentence per throw; Take screen for drift within a take; athlete summary for patterns | Specific cues: "throw a touch softer", "aim about 4 in further left", or "normal spread: keep the same throw" |
| Weekly | Print the PDF report per athlete; compare with last week | Consistency vs noise floor, green zone, scored vs missed with sample-size status |

### 13.2 Why it should improve training (the "why we should be convinced" slide)

1. **It measures what the eye can't.** 0.1 m/s of release speed is invisible but worth ~5 in of carry.
2. **It separates causes that look the same.** Carry vs slide, aim vs release position: a different drill for each.
3. **It is individual.** Advice is relative to each athlete's own usual and green zone, consistent with the evidence that skilled throwers succeed with different strategies.
4. **It doesn't chase noise.** Noise floors, bandwidth feedback and the evidence gate mean a cue is given only when the data can support it, the opposite of "over-coaching".
5. **It follows motor-learning principles** (knowledge of results, bandwidth feedback, one cue at a time, no adjustment after a random error); these need proper citations in the report [FILL].
6. **It gets better as data accumulates.** Each new throw tightens the athlete's usual and moves them toward the 20–40 throws the statistics need.
7. **What would prove it (propose this):** a 4–6 week within-team study. Athletes alternate blocks with and without app feedback (or two matched groups), 40 throws per athlete per week, primary outcome PPR and first-contact grouping at a fixed distance, secondary outcome release-speed SD. Pre-register the analysis. We have not run this; say so.

### 13.3 Recruiting (the bonus)

A 20–40-throw filmed session gives: PPR and In/On/Off; release speed and angle consistency against the noise floor; landing grouping; and a stable profile (backswing, trunk lean, peak wrist speed) that is strongly athlete-specific (ICC 0.75–0.96). Use it as one input with clear caveats: a short session, an unfamiliar venue and nerves all change results; the profile describes style, not quality; and no norms exist to rank recruits against. Keep recruits' video private and get consent.

### 13.4 Practical factors (cost, time, privacy, usability)

| Factor | Our system | Notes |
|---|---|---|
| Hardware cost | Two phones + two tripods + a Mac [FILL: rough $] | No sensors; equipment teams already own |
| Software cost | Open source (MIT licence); pinned open-source pose model | No subscription |
| Set-up time | [FILL: measured minutes] | Tripod positions can be marked with tape |
| Analysis time | ~2 min per throw on the Mac, one at a time; queue survives restarts | A 40-throw session ≈ 80 min of background processing [CHECK on your Mac] |
| Coach effort | Answer only unsure throws; one sentence per throw | Zelik's "the coach is busy" point |
| Privacy | All analysis local; no automatic upload | Our repository is public: see risks |
| Skills needed | Coach: none beyond the app; sport scientist: can read CSV/JSON exports | |
| Robustness | Graded quality and reasons when something fails; works with person masks off | Needs reasonable lighting and a visible board |

---

## 14. Limitations, uncertainties and risks

### 14.1 Measurement limitations

| Limitation | Consequence | Mitigation / what we say |
|---|---|---|
| No criterion validation yet | Accuracy of landmarks, centroids and scale unknown; body noise floors provisional | Validation plan with acceptance criteria agreed in advance (Section 11.3) |
| Projected 2D body angles | Not 3D joint angles; out-of-plane motion distorts (Sih 2001) | Side camera perpendicular; φ > 20° flagged; foreshortened segments withheld; front camera only for sideways measures |
| Two uncalibrated cameras | No 3D skeleton; 3D bag flight is a physics fit, not stereo | Stated; 3D fit validated against independent front measures |
| Frame rates (side 60, front 30 fps) | Timing to ±1 frame (16.7 / 33 ms); release-timing sensitivity unavailable | Report timing in frames; recommend 120 fps side camera |
| Metric scale from gravity (WARNING on 2 athletes) | Metres approximate (a few %); verdict numbers carry "≈" | Pooled per camera set-up; a meter stick in the throw plane would make it GOOD |
| Side FOV unstable at the first tripod position | On 45 of 92 throws release speed from the flight's own gravity scale | Stated; within-athlete comparisons less affected |
| Drag-free model | Small bias in long flights; drag and perspective not separable from one camera | Drag changed apparent g by < 1.5 % in simulation; a drag model did not improve prediction |
| Throw plane = board centre line | A bag released 0.4 m nearer the camera reads ≈ 8 cm low and ≈ 1° high | Session pooling makes it a per-session offset [REPO: CALCULATION_AUDIT D3] |
| 6 Hz filter | Peak wrist speed ≈ 5 % lower than at 12 Hz | Same filter for all throws; residual analysis supports 6 Hz |
| No hand keypoints | No wrist snap, grip, finger release | Out of scope; possible with hand models |
| Red bags on a red deck | Harder bag segmentation on the board; our own protocol advised contrasting bags | Colour gates tuned on this data; next collection should use contrasting bags |
| Knocked bags | The thrown bag and a knocked bag can be confused | Flagged "needs confirmation"; side ending decides; 5 of 7 knock throws resolved correctly by the side ending [REPO: METHODS §5.2] |
| Front camera grazing view | Along-board distance coarse from the front | Along comes from the side board phase |
| Shorter pitch | Release-to-board 5.3–5.9 m vs ≈ 7.7 m regulation | Every model uses the measured distance; results don't transfer directly |

### 14.2 Statistical limitations

- **Small samples:** 4 athletes, 20–28 throws each. Within-athlete descriptions only; no population claims. The evidence gate needs ~7–8 throws per group for even a perfect separation; power is low (12–22 % for δ ≈ 0.6 at 20–24 throws).
- **Multiple comparisons:** Bonferroni within analyses; scored-vs-missed is exploratory across variables.
- **Throws are not independent:** fatigue, learning, takes and sessions; serial dependence is not modelled.
- **The athlete's usual moves** as throws are added and mixes sessions.
- **Associations, not causes:** even a passed gate is a hypothesis for the coach to test.

### 14.3 Risks (broader than biomechanics)

| Risk | Why it matters | Mitigation |
|---|---|---|
| Over-coaching or wrong advice | Telling an athlete to change something that is noise can make them worse | Noise floors, bandwidth feedback, evidence gate, no cue after an odd slide, associational wording |
| False confidence in numbers | Precise-looking decimals can mislead | Status + grade + uncertainty on every number; "≈" when the scale isn't GOOD; values withheld when unreliable |
| Misuse for selection or recruiting decisions | Unvalidated, short-session data could unfairly label an athlete | State validation status; use as one input; no norms; consent |
| Privacy and consent | Athlete video is personal data. **Our repository is public and contains the 46 Final Data Collection videos; athletes' consent to public sharing is not recorded in the repository** | Decide before submission: record consent or make the repository private (see Section 22) |
| Copyrighted material | Earlier commits contained copyrighted books/course files (still in history) | Owner decision pending (history rewrite or private repo); do not cite or distribute them |
| Technology risk | macOS-only; Python environment; model files; long analyses crashed the Mac when parallel | One analysis at a time; queue persists; pinned versions; tests |
| Injury | Cornhole is low-load; no evidence the system changes injury risk | Bag-only forces are labelled as not joint loads; no loading claims |
| Generalisation | Venue, lighting, bag colour, camera models, athlete handedness | Left-handed path tested only synthetically; re-check gates on new venues |

### 14.4 What kept us up at night (honest uncertainties for the talk)

- That a single wrong automatic outcome or a knocked bag silently becomes "data" (hence the "Needs your eye" queue and never overwriting a person's entry).
- That the scale is right: one wrong field of view changes every metre-based number (hence pooling across throws and athletes from the same camera, and the gravity check).
- That we would give advice from noise (hence the evidence gate, which, honestly, means no priorities yet).
- That release timing is a frame off on some throws, which shifts every "at release" body value.

---

## 15. The project story: iterations, hardest parts, surprises

The announcement asks for "what you did and what you learned". This project has a strong iteration story; one slide of it is worth more than three slides of background.

### 15.1 Timeline (dates from the repository; add the ones marked [FILL])

| Date | Milestone | What it taught us |
|---|---|---|
| 21 Aug 2026 | Project handout | — |
| [FILL] | AI baseline report submitted | The floor we had to exceed (Section 18) |
| 8 Sep | Evidence review (RESEARCH_BACKGROUND, REFERENCES) | No published work validates this combination; we must validate it ourselves |
| 17 Sep | **Pilot:** 26 hand-held single-camera clips, 3 athletes | 20/26 flights tracked automatically, but hand-held drift up to 100 px, athlete only ~300 px tall, board tiny, no known length |
| 22 Sep | Recording protocol written; 0–100 composite scores removed | Fix the data before fixing the code; don't publish numbers whose weights are invented |
| 23–24 Sep | Measurement engine: camera stabilisation, board PnP, gravity-calibrated scale, release rule, evidence chain | 21/21 releases within ±1 frame; metres from gravity |
| 24 Sep | Interim report feedback (Zelik + peer review) | Left/right missing; automate outcomes; "it's the combination, not one right speed or angle"; outcome first |
| late Sep | Tripod sessions; board phase, personal green zone, outcome-first verdict | Board end correct on 10/10 clips; model 40 % vs observed 42 % |
| [FILL] | **Final Data Collection:** 4 athletes, 23 two-camera takes, 92 throws | Two views: left/right, automatic hole/board/off |
| 5–6 Oct | QA audit, frame by frame, of two-camera throws | Forward growth to contact, release backfill, touchdown rule, body events fixed with evidence |
| 11 Oct | Calculation audit (27 known-answer tests) | Shoulder-angle fold, friction sign, plane launch fit |
| 12 Oct | Metric review, metric tiers, full re-analysis of all 92 throws, validation plan, PDF report | Which metrics are per-throw signals vs athlete traits |
| 20 Oct | Report + presentation | — |

### 15.2 The hardest parts (pick two for the talk)

1. **Finding a red bag on a red board in a busy gym.** In front of a pillar, posters and bystanders, the bag's grey-level difference was weak, detections thinned out, and one throw split into two candidate flights; the tracked flight stopped 0.3 s before touchdown. Fix: colour-gated forward growth with four gates (distance, size, bag colour, not on a person). Result: both truncated throws now end at the touchdown frame and the corrected arc changed one throw's field of view from 54° to 64° (release speed 7.28 → 8.30 m/s) [REPO: METHODS §1.6]. Lesson: one tracking error propagates into scale and every metre-based number.
2. **Getting metres out of a phone.** One image can't separate lens width from distance. Using gravity on the bag's own flight fixed it, but single throws scattered by 10+°, and pooling per athlete gave two athletes an 8° disagreement with the same unmoved camera. Pooling per camera set-up fixed it.
3. **Syncing two phones without hardware.** Sound cross-correlation worked on all 23 pairs, but then the front camera consistently showed contact one frame late: a picture lag from exposure/rolling shutter, now measured and pooled.
4. **Which bag was thrown?** When a bag knocks another, the front camera sees two changes. The side camera's ending decides; when unsure the throw goes to "Needs your eye".
5. **Being honest with small samples.** Adding a Bonferroni correction meant that at 5 + 5 throws no claim is even possible. Accepting a "no priorities yet" result was harder than building the feature.

### 15.3 Surprises (good material for "what surprised you")

- All four athletes release at almost exactly the same speed; they differ in how consistently they do it.
- They already throw at the angle where angle errors matter least.
- Many misses are made after landing, on the board.
- A still bystander can beat the thrower on pose-model confidence because motion blur lowers the thrower's score.
- 4K video tracked **worse** than 1080p (the bag fragmented; 0/10 vs 8/10 flights).
- The phone labelled "Front" was actually the side phone on one take; a phone being picked up looked like a fifth throw.
- The front phone slowly sank about 40 px on its tripod during a 30 s take.
- Hip sway looked like a meaningful frontal-plane measure but was mostly noise (ICC 0.66), so it was dropped.

### 15.4 What we would do differently

- Contrasting bag colour (our own protocol said "avoid red bags on a red board").
- 120 fps on the side camera; a meter stick in the throwing plane at the start of every session; fix the tripod before the first take.
- Throw from the regulation distance (27 ft) so results transfer to competition.
- 40+ throws per athlete, and a fixed paper outcome sheet as a backup.
- Run the blinded validation subset (5 throws per athlete) right after collection, before tuning anything.
- Include at least one left-handed athlete.

---

## 16. The 10-minute presentation plan

**Audience:** classmates (not the client). **Goal:** show what we built, what the data revealed, and what we learned; make the demo the centre. **Don't:** spend more than ~1.5 minutes on background.

### 16.1 Timing and slides

| Time | Slide / segment | Content | Visual | Speaker [FILL] |
|---|---|---|---|---|
| 0:00–0:40 | 1. Hook | Two bags, both ~10 in short [FILL: pick two real throws]. Same miss? Show side-by-side: one under-carried, one landed fine and slid less. "A coach can't tell these apart by eye. We can." | Two throw reports' board-from-above figures (Export Figure) | |
| 0:40–1:30 | 2. Sport, client, problem | Board/hole/pitch in one picture; per-bag 3/1/0; the coach's question: *which part of the throw caused the miss, and is it real or noise?* | Board diagram with dimensions | |
| 1:30–2:30 | 3. Our solution | Two phones, no sensors on the bag, Mac app; the chain body → release → flight → landing → outcome → advice | CAMERAS_AND_MEASURES map as a graphic; pipeline diagram (Section 7.0) | |
| 2:30–3:15 | 4. Two clever ideas | (a) Physics as the tracker's filter: a free bag must fall at g. (b) Gravity as a ruler: find the lens setting where the bag falls at exactly 9.81 m/s² | Bag arc overlay; HFOV vs apparent g curve crossing −g | |
| 3:15–6:00 | 5. Demo | See 16.2 | Live app (backup: screen recording) | |
| 6:00–7:45 | 6. What the data revealed | 3 insights: speed consistency, forgiving angle (sensitivity table), slide misses; plus the honest null (no priorities yet, and why) | Release-speed dot plot per athlete; sensitivity table; named-parts bar chart | |
| 7:45–8:45 | 7. Why it should improve training | Measures the invisible (0.1 m/s ≈ 5 in); separates causes; individual; refuses to chase noise; how we'd prove it (4–6 week study) | 4 icons + study design | |
| 8:45–9:30 | 8. Limits and validation | 2D body, no criterion validation yet (plan with acceptance criteria), shorter pitch, small sample | Validation plan table | |
| 9:30–10:00 | 9. What we learned | Hardest part, biggest surprise, what we'd do differently; one-line close: *"Measure the throw, explain the miss, and only coach what the data can support."* | Iteration timeline | |

### 16.2 Demo script (≈ 2.5 minutes)

**Recommended format:** recorded or pre-analysed live. Analysis takes about 2 minutes per throw and runs one at a time, so a fresh take of 4 throws needs ~8 minutes. Two good options:

- **Option A (safest):** film a take of a teammate the day before, import it, and demo the finished results live in the app. Show a 10-second clip of the filming so the class sees "a real person measured".
- **Option B (more impressive):** at the start of the talk, drop a pre-recorded take folder on the app so it analyses while you speak; by the demo the first throws are done. Keep Option A ready if anything fails. Do not run more than one analysis at a time.

**Click path (practise it until it takes under 3 minutes):**

1. Athlete list → one athlete → **Take screen**: synced side + front video; play one throw; point at "From above" with numbered bags and the points/In-On-Off counts. (20 s)
2. Click a **missed** throw → **Throw report**: read the one sentence aloud; show the board figure (first contact ring → slide → rest, precision ellipse). (30 s)
3. **Miss breakdown** bars: "this part is carry, this part is slide; the grey band is measurement noise; only parts above it are named." (25 s)
4. **Release vs your usual**: the dot among the athlete's other throws. (15 s)
5. **Replay → Both / Animation**: synced views, measured arc solid, model dashed, top view with launch direction. (30 s)
6. **Needs your eye**: answer one with key 1/2/3. "The coach only confirms the throws we're unsure of." (15 s)
7. **Athlete summary**: personal green zone sentence and the scored-vs-missed panel saying how many throws a claim needs. Optional: Launch Lab slider to show 0.1 m/s ≈ 13 cm. (25 s)

**Demo safety checklist:** app built and opened from the Desktop shortcut the morning of; library loaded; Do Not Disturb on; display mirrored and tested on the room projector; screen recording of the same click path as backup; mouse, not trackpad, if possible.

### 16.3 Figures to prepare (all available from the app or repo)

- Throw report board figure and side + top animation frame (Export Figure… gives PNG).
- Athlete summary screenshot; release map; Launch Lab success map (`docs/images/` has light/dark examples).
- Pipeline diagram (Section 7.0) and camera map (CAMERAS_AND_MEASURES).
- Sensitivity table (Section 8.5) or a plot of first contact vs speed at 40°.
- Metric review table (Section 9.3), simplified to three tiers.
- Per-athlete release-speed strip plot showing equal medians and different spreads (from the PDF report's "Release conditions" page).

### 16.4 Talk tips

- Use the athletes' codes (Player 1–4), never names.
- Every number you say should have its unit and, ideally, its uncertainty ("about 13 cm per 0.1 m/s").
- Say "associated with", never "caused by", for body-to-outcome links.
- Assign Q&A owners by topic in advance: tracking and cameras, physics and math, statistics and feedback, sport and coaching value [FILL names].

---

## 17. The client report plan

**Audience:** the cornhole coach and the sport scientist. Write the body in plain language, lead each section with the answer, and move equations and code to appendices (allowed, and useful to Prof. Zelik). Submit as a zip: report PDF + appendices + example videos/figures + a link to the repository.

### 17.1 Suggested structure

| Section | Content | Source in this guide | Length (suggested) |
|---|---|---|---|
| Executive summary | Problem, solution, three findings, recommendation, limitations in one paragraph each | 2, 12.7, 13 | 1 page |
| 1. The problem and your goals | Coach's question; why outcome alone is not enough | 3 | 0.5 page |
| 2. Background | Cornhole rules and equipment; the underhand throw; what the literature says about accuracy (strategies, minimum speed, variability); existing measurement options | 3, 5, 9.1 | 1.5 pages |
| 3. Our system | Hardware and set-up; what each camera measures; workflow for a practice | 6, 13.1, CAMERAS_AND_MEASURES | 1.5 pages |
| 4. How it measures | Pipeline in plain words with one figure; the physics-gated bag tracking; gravity scale; release; landing; two-camera fusion | 7 (condensed), 8.4–8.6 | 2 pages |
| 5. How it gives feedback | Outcome first; one sentence; 4-part explanation; evidence gate; green zone; PDF report | 10 | 1 page |
| 6. Data we collected | Participants (codes), protocol, 92 throws, consent | 6.1, [FILL] | 0.5 page |
| 7. What the data revealed | Outcomes; release profiles; evidence chain; miss attribution; per-athlete coaching outputs; key insights | 12 | 2–3 pages |
| 8. Recommendations | Per athlete (as hypotheses to test), for the team, and for recruiting | 12.6, 12.7, 13.3 | 1 page |
| 9. How far to trust it | Verification evidence; stress test; what is not validated; validation plan | 11 | 1 page |
| 10. Alternatives and why ours | Comparison table; cost and practicality | 5, 13.4 | 1 page |
| 11. Limitations and risks | Measurement, statistical, broader risks | 14 | 1 page |
| 12. Next steps | Validation study, more throws, regulation distance, 120 fps, training-effect study | 13.2, 15.4 | 0.5 page |
| References | Verified sources only | 21 | |
| Appendices (for Prof. Zelik) | A: equations (Section 8). B: metric definitions and noise floors (METRICS). C: pipeline parameters and gates (Section 7). D: validation evidence and plan (Section 11). E: per-athlete PDF reports from the app. F: AI baseline comparison and AI-use statement (Section 18). G: repository, how to run, test summary. H: example videos / figures | | |

### 17.2 Writing rules for the report

- Lead with the finding, then the evidence, then the caveat.
- Use the same terms everywhere: release speed/angle/height, first contact, slide, rest, carry, aim, release position, "usual", noise floor.
- Give every result as value ± uncertainty or with its noise floor and n.
- Separate what is **measured**, **estimated** and **not measured**; the app already labels each value.
- Put the "Associations are not causes" sentence near every body-to-outcome statement.
- Cite primary sources (Section 21); add the citations marked "to add" before using those claims.

---

## 18. Exceeding the AI baseline, and how AI was used

The course required an AI-generated 5-page baseline report in week 1. The final report should show, explicitly, how far beyond it the team went. Fill the left column from your actual baseline report [FILL]; typical baseline content is shown as a guide.

| Typical AI baseline content | What our team actually did |
|---|---|
| Generic list of possible sensors (IMUs, mocap, cameras) | Built and tested a working two-phone system; justified each choice against alternatives with measured evidence |
| Generic metrics ("release angle", "follow-through") with textbook targets (e.g. "45° is optimal") | Measured our athletes: they release at 37–44°, and the physics shows ~40° is the angle-forgiving region at their distance; speed, not angle, is the lever |
| No real data | 92 real throws from 4 athletes, two cameras each, every throw analysed |
| Accuracy claims without evidence | Status, grade and uncertainty on every number; known-answer tests; stress test of false claims; frame-by-frame audits; a pre-agreed validation plan |
| Population "ideal form" | Within-athlete analysis; personal green zone; strategies differ by athlete |
| Feedback ideas in the abstract | A running app producing one-sentence feedback, miss breakdowns, a review queue and a PDF report |
| Limitations as a generic paragraph | Specific, quantified limitations (e.g. 45 of 92 throws on the flight's own gravity scale; ICC of each metric) |

**AI-use statement (draft, adapt):** "We used LLM assistants (Claude) throughout for literature search support, code development, code review and drafting documentation, including this report's outline. Every number in the report was checked against the app's outputs or the repository's tests and method documents, and every reference was verified against the original source. The baseline report generated in week 1 is in Appendix F for comparison."

---

## 19. Q&A preparation: likely questions and answers

Answer pattern: **answer in one sentence → the evidence (a number) → the limit.** If you don't know, say what you would measure to find out.

### 19.1 Problem and design

**Q1. Why cornhole and not bocce or disc golf putting?** [FILL: the team's real reason.] A good technical answer: cornhole's outcome depends on a short, mostly planar underhand throw plus a measurable flight and slide, which suits video and physics; and the regulation board gives us a free calibration object in every frame.

**Q2. Isn't this just tracking and scoring?** No. Scoring alone is what the coach already has. We measure the chain from body to release to flight to landing, split each miss into measured parts, and test within each athlete whether movement features are associated with scoring, under an explicit evidence gate.

**Q3. Why two phones and not one?** One side camera cannot see left/right or reliably tell hole from board; Prof. Zelik's interim feedback asked exactly that. The front camera adds left/right (±0.5 in on the deck), the automatic result, and frontal-plane body measures.

**Q4. Why not motion capture?** It is the accuracy gold standard but lab-bound, expensive and slow to set up, and it still doesn't measure the bag's landing. We'd use it to validate our system, not as the product.

**Q5. Why not IMUs on the athlete?** They'd give good arm timing but not the bag's release speed and angle or where it landed, which are what decide the outcome. They are a sensible future add-on for release timing.

**Q6. Why not a deep-learning bag tracker?** No labelled cornhole data exists, and networks like TrackNet need thousands of labelled frames. Physics is a stronger prior: a free bag must fall at g, which rejects nearly all clutter without training.

**Q7. Why Sports2D/RTMPose and not MediaPipe?** Open source with a peer-reviewed paper, multi-person tracking (so we can box out bystanders), heel/toe points for release height, and it runs on a Mac CPU. We pinned the version so numbers can't change silently.

**Q8. What is new here versus existing apps?** Automatic physics-gated bag tracking, a metric scale from gravity, two-phone sync from sound, a 3D bag flight from two uncalibrated phones, a miss split into measured parts, and statistics that refuse to make claims the data can't support.

### 19.2 Measurement and math

**Q9. How do you get metres from a phone video?** From the regulation board's known size (PnP) plus gravity: we find the lens field of view at which the bag's flight falls at exactly 9.81 m/s², and pool that over all throws from the same camera position.

**Q10. How accurate is release speed?** Within a throw the fit's standard error is small, but that is a lower bound. We use a 0.15 m/s noise floor (about two typical fit SEs at 60 fps). A change of tracking method moved speed by a median 0.08 m/s. Criterion validation against manual centroids is planned with a 0.15 m/s acceptance threshold.

**Q11. How do you know when the bag is released?** The first bag position more than 0.45 arm lengths from the wrist. On 21 pilot flights it matched visual release within ±1 frame (19 exact).

**Q12. 60 fps is only 16.7 ms per frame. Is that enough?** For release speed and angle, yes: the fit uses ~7 frames of flight. For release timing, no: skilled throwers time release to milliseconds (Hore & Watts 2011), which is why we don't report timing sensitivity. We'd use 120 fps next time.

**Q13. Why a 6 Hz filter?** Standard 4th-order zero-phase Butterworth; Winter's residual analysis on 12 of our signals gave a median optimal cutoff of 5.5 Hz. It lowers peak wrist speed by about 5 % vs 12 Hz, the same for every throw, so within-athlete comparisons are unaffected.

**Q14. Why ignore air drag?** A drag model didn't improve prediction on our flights (out-of-sample error 24.5 vs 24.9 px), and simulated drag changes the apparent g by under 1.5 %. One camera also can't separate drag from motion toward the lens.

**Q15. Your body angles are 2D. Isn't that wrong?** They are projected angles in the camera plane, and we label them that way. The side camera is perpendicular to a mostly planar throw; segments that point at the camera are withheld; the out-of-plane angle is checked. We never call them 3D joint angles.

**Q16. How do you sync two phones?** By sound: the clap and every bag impact. Cross-correlating the two soundtracks gives the offset within ±17.5 ms (about half a front-camera frame), checked per throw against the landing frame in both views.

**Q17. How can you get 3D bag flight from two uncalibrated phones?** The side camera already measures the arc along and up in metres. The front camera only has to answer "how far left or right", which is a straight line in a drag-free flight. We fit that line to the front images with physics. It agrees with independent front-camera landing measures to a median 0.8 in.

**Q18. What does "noise floor" mean?** The smallest difference we interpret, based on how much the measurement itself can wobble. If two throws differ by less than it, we treat them as the same.

**Q19. How do you handle a knocked bag?** The front camera sees two changes; the side camera, which follows the thrown bag, decides; if still unsure, the throw goes to "Needs your eye" and nothing is recorded automatically.

**Q20. Why is the force on the bag "bag-only"?** It's $m(\mathbf a - \mathbf g)$ of the bag, from its acceleration. It is not a muscle or joint force; we have no force plates or 3D segments for inverse dynamics.

### 19.3 Statistics and evidence

**Q21. With 20–28 throws, can you claim anything?** Within-athlete descriptions, yes; movement-to-outcome claims, mostly no. Our gate needs about 7–8 throws per group even for perfect separation, and our stress test shows 20–40 throws per athlete to detect a real cause. With our data, no priority passed, and the app says so.

**Q22. Why Cliff's δ and not a t-test?** Small, non-normal samples with outliers. δ is nonparametric and directly interpretable (probability scored > missed minus the reverse). We use the 0.474 "large" threshold and a Bonferroni chance level, whichever is stricter.

**Q23. Isn't Bonferroni too conservative?** Yes, deliberately: a false coaching cue costs practice time and athlete trust. The cost is low power, which we state (12–22 % for a medium-large effect at 20–24 throws).

**Q24. How do you avoid false positives overall?** Noise floors, multiple-comparison control, a bootstrap repeatability check, a reliability check, and the stress test showing ≤ ~5 % false claims on simulated athletes with no real cause.

**Q25. Why compare within athletes instead of to an expert?** There are no cornhole norms, and accurate throwers use different strategies (Nasu 2014); the best angle is athlete-specific (Linthorne 2001). A template would coach away working styles. Our data agree: style measures differ strongly between athletes (ICC 0.90–0.96) but are stable within each.

**Q26. What is ICC and why does it matter here?** The share of variation that is between athletes rather than throw-to-throw. High ICC (backswing 0.96) means a trait, useful for profiling; low ICC (release speed ≈ 0.01) means the signal is throw-to-throw, useful for per-throw feedback.

**Q27. Correlation isn't causation. How do you handle that?** Every body-to-outcome statement is worded as an association; the coach sentence can't say "because", "caused", "fault" or "should" (tested on 1,800 cases). Only physics links (release speed → carry) are stated as mechanisms, through the flight model.

**Q28. Your throws aren't independent. Does that matter?** Yes: fatigue, learning, and takes create dependence that we don't model, so CIs are somewhat optimistic. More sessions per athlete would let us model it.

### 19.4 Results

**Q29. What was the most important finding?** All four athletes release at about the same speed (7.5 m/s), but their throw-to-throw speed consistency differs by 2×, and at their release angle speed is the lever: 0.1 m/s ≈ 13 cm of carry, while 1° ≈ 1 cm.

**Q30. Did anything surprise you?** Many misses were made on the board (slide), not in the air; and the athletes already release near the angle where angle errors cost least.

**Q31. Did the system find what each athlete should change?** It found per-athlete hypotheses (green-zone aims, speed consistency) but no movement feature passed the full evidence gate yet. That's the honest result for 20–28 throws.

**Q32. How do you know the hole/board/off detection works?** It matched the frames on 8 of 8 randomly checked throws and the board phase on 10 of 10 tripod clips; unsure throws are queued for the coach. A blinded check against recorded results (target ≥ 95 %) is in the validation plan.

**Q33. Why did Player 2 score so few holes?** [CHECK / FILL from the app.] The data show their misses had a higher release angle (median 45° vs 41°) but that difference did not pass the repeatability check; their release speed and angle compensate each other (ratio 1.14).

### 19.5 Value, limits and risks

**Q34. Why should a coach believe this improves training?** It measures what the eye can't (release speed), separates causes that look identical, is individual, and refuses to give advice from noise. We have not yet shown a training effect; we propose a 4–6 week within-team study (Section 13.2).

**Q35. How long does it take to use?** About 2 minutes of computer time per throw in the background; the coach only confirms unsure throws. [FILL: set-up minutes.]

**Q36. Could it be used for recruiting?** As one input: a 20–40-throw session gives PPR, consistency and a stable style profile. With caveats: unvalidated, no norms, short sessions are noisy, and recruits must consent.

**Q37. What is the biggest limitation?** No criterion validation yet. The plan has acceptance criteria agreed before looking: release ±1 frame, speed ±0.15 m/s, angle ±3°, landing ±2–3 in, outcome ≥ 95 %.

**Q38. Your distance was shorter than regulation. Does that matter?** Yes for transfer: at ~7.7 m the speed to the hole is ~8.9 m/s instead of ~7.7 m/s, and sensitivities change. The model uses the measured distance, so it works at any distance, but our athletes' numbers apply to our set-up.

**Q39. What about privacy?** Analysis is local. The repository is public and contains the participant videos; [FILL: state the consent obtained or the decision to make the repository private].

**Q40. What happens when tracking fails?** The value becomes `unavailable` with a reason (never zero), the stage gets a WARNING/POOR grade, and athlete analyses exclude it. The coach can fix tracking or confirm the result manually; manual entries always win.

**Q41. Would it work for a left-handed athlete or a different gym?** Left-handed throws are handled by mirroring and tested synthetically, not on real data. A new venue needs a visible board and reasonable light; colour gates were tuned on red bags here and should be re-checked.

**Q42. Why no overall "technique score"?** We built one early and removed it: its weights had no empirical basis and it hid which component differed. Coaches get the components with their uncertainty instead.

**Q43. What would you do with another month?** Run the blinded validation, collect 40+ throws per athlete at regulation distance with 120 fps and contrasting bags, and run the training-effect study.

**Q44. What was the hardest part?** Tracking a red bag on a red board in a cluttered gym, and getting a trustworthy metric scale from a phone; both are solved with physics, and both taught us that one tracking error propagates into every metre-based number.

**Q45. How did you use AI, and how did you check it?** Throughout (coding, review, documentation); every number is traceable to code, tests or app output, and references were checked against originals. [FILL: specifics.]

---

## 20. Glossary (for slides and the report)

| Term | Meaning |
|---|---|
| Release speed / angle / height | Bag speed, launch angle above horizontal, and height above the floor at the moment it leaves the hand |
| Launch direction (heading) | Left/right direction of the throw, + to the thrower's right |
| First contact | Where the bag first touches the deck, front face or floor |
| Slide / slide drift | Distance from first contact to rest along / across the board |
| Rest | Where the bag stopped |
| Carry | How far first contact was from the athlete's usual first contact |
| Usual | Median over the athlete's other throws (≥ 8) |
| Noise floor | Smallest difference the analysis interprets |
| Arm length | Projected shoulder–elbow + elbow–wrist length, used to scale body positions |
| Projected 2D angle | An angle measured in the camera image plane, not a 3D joint angle |
| PnP | Perspective-n-point: camera pose from known 3D points (the deck corners) |
| Homography | 3×3 mapping between a plane and the image |
| HFOV | Horizontal field of view of the camera lens |
| Kalman / RTS smoother | Optimal smoothing of a noisy track under a motion model, forward then backward |
| Cliff's δ | Nonparametric effect size between two groups, −1 to 1 |
| ICC | Intraclass correlation: share of variation between athletes |
| PPR | Points per round = 4 × mean points per bag |
| Green zone | Release combinations predicted to land in the hole window |
| measured / estimated / unavailable | The status every number carries |

---

## 21. References

### 21.1 Verified sources already in the repository (docs/REFERENCES.md)

- American Cornhole League. *Rules & Regulations* (updated 24 Oct 2025; accessed 8 Sep 2026). https://www.iplaycornhole.com/about/acl-information/rules-regulations
- American Cornhole League. *Bags + Equipment: Board Info & Resources* (accessed 8 Sep 2026). https://www.iplaycornhole.com/about/acl-information/equipment-bags-boards
- Challis, J. H. (1999). A procedure for the automatic determination of filter cutoff frequency for the processing of biomechanical data. *Journal of Applied Biomechanics, 15*(3), 303–317. https://doi.org/10.1123/jab.15.3.303
- Hore, J., & Watts, S. (2011). Skilled throwers use physics to time ball release to the nearest millisecond. *Journal of Neurophysiology, 106*, 2024–2033. https://doi.org/10.1152/jn.00059.2011
- Jiang, T., et al. (2023). RTMPose: Real-time multi-person pose estimation based on MMPose. *arXiv*. https://doi.org/10.48550/arXiv.2303.07399
- Linthorne, N. P. (2001). Optimum release angle in the shot put. *Journal of Sports Sciences, 19*(5), 359–372. https://doi.org/10.1080/02640410152006135
- Müller, H., & Sternad, D. (2004). Decomposition of variability in the execution of goal-oriented tasks: Three components of skill improvement. *J. Exp. Psychol.: Human Perception and Performance, 30*(1), 212–233. https://doi.org/10.1037/0096-1523.30.1.212
- Nasu, D., Matsuo, T., & Kadota, K. (2014). Two types of motor strategy for accurate dart throwing. *PLOS ONE, 9*(2), e88536. https://doi.org/10.1371/journal.pone.0088536
- Needham, L., et al. (2021). The accuracy of several pose estimation methods for 3D joint centre localisation. *Scientific Reports, 11*, 20673. https://doi.org/10.1038/s41598-021-00212-x
- Pagnon, D., & Kim, H. (2024). Sports2D: Compute 2D human pose and angles from a video or a webcam. *Journal of Open Source Software, 9*(101), 6849. https://doi.org/10.21105/joss.06849
- Pagnon, D., Domalain, M., & Reveret, L. (2022). Pose2Sim: An open-source Python package for multiview markerless kinematics. *JOSS, 7*(79), 4362. https://doi.org/10.21105/joss.04362
- Putnam, C. A. (1993). Sequential motions of body segments in striking and throwing skills of humans. *Journal of Biomechanics, 26*(Suppl. 1), 125–135. https://doi.org/10.1016/0021-9290(93)90084-R
- Sih, B. L., Hubbard, M., & Williams, K. R. (2001). Correcting out-of-plane errors in two-dimensional imaging using nonimage-related information. *Journal of Biomechanics, 34*(2), 257–260. https://doi.org/10.1016/S0021-9290(00)00185-8
- Stenum, J., Rossi, C., & Roemmich, R. T. (2021). Two-dimensional video-based analysis of human gait using pose estimation. *PLOS Computational Biology, 17*(4), e1008935. https://doi.org/10.1371/journal.pcbi.1008935
- Tran, B. N., Yano, S., & Kondo, T. (2019). Coordination of human movements resulting in motor strategies exploited by skilled players during a throwing task. *PLOS ONE, 14*(10), e0223837. https://doi.org/10.1371/journal.pone.0223837
- Venkadesan, M., & Mahadevan, L. (2017). Optimal strategies for throwing accurately. *Royal Society Open Science, 4*, 170136. https://doi.org/10.1098/rsos.170136
- Winter, D. A. (2009). *Biomechanics and Motor Control of Human Movement* (4th ed.). Wiley.
- Zelik, K. E. (2026). *Project 1: Biomechanics of Human Movement (Fall 2026)*. Vanderbilt University course handout, updated 21 Aug 2026.

### 21.2 Claims that need a citation added before the report (verify each against the original)

| Claim used | Suggested source to find and verify |
|---|---|
| Cliff's δ ≥ 0.474 is "large" | Romano, J., et al. (2006), conference paper on appropriate statistics for ordinal survey data |
| Smallest worthwhile change = 0.2 × SD | Hopkins, W. G., e.g. Hopkins (2000/2004) on measures of reliability / progressive statistics |
| ICC ≥ 0.75 is "good" | Koo, T. K., & Li, M. Y. (2016). *J Chiropractic Medicine, 15*(2), 155–163 (named in METHODS §5.2; add to REFERENCES.md) |
| Kalman filter / RTS smoother | Rauch, Tung & Striebel (1965), *AIAA Journal*; or Bar-Shalom, Li & Kirubarajan (2001) |
| ECC image registration | Evangelidis & Psarakis (2008), *IEEE TPAMI* |
| PnP IPPE solver | Collins & Bartoli (2014), *IJCV* (Infinitesimal Plane-based Pose Estimation) |
| TrackNet needs large labelled data | Huang, Y.-C., et al. (2019), TrackNet, arXiv:1907.03698 |
| Bandwidth knowledge-of-results feedback | e.g. Sherwood (1988) or Lee & Carnahan (1990); or a motor learning textbook (Schmidt & Lee) |
| Deming's funnel (adjusting after random error adds variance) | Deming, W. E. (1986/1994) |
| Motor abundance | Bernstein (1967) or Latash (2012) |
| IMU / depth camera alternatives (if discussed) | A peer-reviewed validation study for each |
| Commercial video apps (if named) | Product documentation, not marketing claims |

Do **not** cite the copyrighted books that were once in the repository's history; cite published sources you can access.

---

## 22. Fill-in and decision checklist before 20 October

**Numbers to confirm in the app**
- [ ] Confirm the throws in "Needs your eye", then re-read every athlete summary; update Section 12 tables (outcomes, PPR, release profiles, evidence chain, green zone). Reconcile the two outcome totals (18/38/36 vs dashboards).
- [ ] Print each athlete's PDF report for the appendix.
- [ ] Confirm the front picture lag value (≈ 21 ms in METHODS vs 18 ms in CAMERAS_AND_MEASURES).

**Facts only the team knows**
- [ ] Data collection date(s), venue, board, bags; athletes' experience levels (as codes); consent obtained.
- [ ] Set-up time in minutes; equipment cost estimate.
- [ ] The AI baseline report's main claims (Section 18 table).
- [ ] Who presents which slide; who owns which Q&A topic.
- [ ] Two real throws for the hook slide (one "carry" miss and one "slide" miss of similar size).

**Decisions to make**
- [ ] Repository visibility and consent: the public repository contains the participant videos and old copyrighted files in history. Either record the athletes' consent to public sharing, or make the repository private before linking it in the report.
- [ ] Live vs recorded demo; prepare the backup recording either way.
- [ ] Whether to run a small blinded validation (even 5 throws) before submission.

**Final checks**
- [ ] Every body-to-outcome sentence says "associated with".
- [ ] Every number has a unit and an uncertainty or noise floor.
- [ ] Every reference opened and verified; "needs citation" items either cited or removed.
- [ ] Appendices include equations, metric definitions, validation evidence, AI-use statement, and how to run the code.
