# Research background

**Evidence review completed 8 September 2026.** This document distinguishes external evidence from decisions made for Cornhole Biomechanics Lab. The literature motivates measurements and cautions; it does not establish that this app is accurate for cornhole.

## Why this project exists

Cornhole scoring tells a coach **what** happened. The value of a biomechanics system is helping investigate **how** the athlete moved and which measurable changes repeatedly accompany better or worse outcomes.

Laboratory motion capture can provide detailed biomechanics but is difficult to use routinely during cornhole practice because it requires equipment, space, setup, and expertise. A controlled phone-video workflow is more accessible, but one camera cannot reproduce every laboratory measurement and must not pretend to. Its useful scope is a smaller set of repeatable, interpretable projected kinematic measures collected frequently and linked to the same athlete's outcomes.

The intended advantage is longitudinal, individualized evidence: **“What changes when this athlete throws better?”** It is not “Does this athlete copy one supposedly perfect player?”

## Research questions

Primary question:

> Can controlled single-camera markerless video quantify upper-body cornhole kinematics repeatably and identify within-athlete movement features associated with task performance?

Secondary question:

> For an athlete's current sample, is performance more closely associated with resemblance to a coach-selected reference, repeatability of the athlete's own movement, or particular kinematic features?

The software keeps three constructs separate:

1. **Reference similarity** — resemblance to a named, compatible reference trial or set.
2. **Personal consistency** — repeatability of this athlete's own movement.
3. **Performance association** — exploratory relation between measured features and outcomes.

None is a synonym for technique quality. A different technique is not automatically poor, and a similar technique is not automatically effective.

## Course basis

The local Vanderbilt Project 1 handout requires a bespoke system that measures real participant movement, relates movement characteristics to performance, and produces individualized insight beyond tracking or scoring. It also requires comparison of alternative measurement choices and frank treatment of assumptions, limitations, uncertainty, and risk. The syllabus emphasizes open-ended problem solving and the benefits and drawbacks of measurement methods.

Synthetic fixtures and external/reference videos can verify software. They cannot substitute for consented, provenance-supported participant data collected for the course experiment.

## Evidence and application decisions

The table below uses primary publications, official project documentation, and official rules. “Does not support” is as important as “Supports.” All web sources were checked on **2026-09-08**.

| Source | Supports | Does not support | App impact |
|---|---|---|---|
| Vanderbilt Project 1 handout, local PDF, updated 2026-08-21 | A working bespoke measurement/analysis system; real participant performance data; movement-to-outcome evidence; individualized insight; alternatives and limitations. | Any particular pose model, metric, cutoff, accuracy threshold, or conclusion about throwing technique. | Make movement–performance analysis central; label QA versus participant evidence; retain assumptions and uncertainty. |
| Vanderbilt course syllabus, local PDF, updated 2026-08-21 | Defensible measurement selection, benefits/drawbacks/assumptions, open-ended project work, and reporting. | Validation of this software or its scientific measurements. | Document equations, units, alternatives, risks, and validation status. |
| [Pagnon & Kim, Sports2D, JOSS 2024](https://joss.theoj.org/papers/10.21105/joss.06849), published 2024-09-24 | An open-source workflow can obtain 2D keypoints and joint/segment angles from one video/webcam and create editable scientific outputs and annotated video. | Cornhole-specific validity; phone upper-limb accuracy; bag tracking; outcomes; reference sets; coaching claims. | Reuse the generic pose/diagnostic foundation and own the cornhole data, review, outcome, and interpretation layers. |
| [Sports2D official documentation](https://github.com/davidpagnon/Sports2D) and [v0.8.34 release](https://github.com/davidpagnon/Sports2D/releases/tag/v0.8.34), released 2026-07-10; [PyPI 0.8.34](https://pypi.org/project/sports2d/0.8.34/) | Current stable package status; public Python/configuration workflow; RTMPose tracking; confidence/interpolation/filter options; TRC/MOT/video outputs; Mac support; warnings that useful angles require near-planar motion and a parallel camera. | That upstream defaults are optimal for this task; that height/perspective conversion yields athlete-plane ground truth; that single-camera depth/OpenSim-style outputs are research-grade 3D; automatic upgrade safety. | Keep **Sports2D 0.8.34** and Pose2Sim 0.10.49 pinned. Preserve the version-locked confidence bridge and provenance. Use conservative gaps and app-defined metrics. Disable metric/3D/IK features until separately validated. Reassess a future version in an isolated branch with export, angle, confidence, model, and real-video equivalence tests before upgrading. |
| [Nasu, Matsuo & Kadota (2014)](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0088536) | Eight experts and eight novices made 60 dart throws under seven-camera 480 Hz measurement; experts showed at least two strategies—reducing timing sensitivity through hand path or reducing release-timing error. | A universal expert pattern; cornhole norms/tolerances; generalization from darts to bags; millisecond precision from ordinary phone video. | Keep trajectory, release timing, reference resemblance, and personal consistency separate; allow multiple successful strategies; use frame-limited timing. |
| [Tran, Yano & Kondo (2019)](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0223837) | Eight expert dart players completed 42 measured throws with six 200 Hz cameras. Joint/hand and projectile kinematics were studied together; release was detected from persistent thumb–dart separation and checked in video. | Validity of a phone bag tracker; cornhole causal prescriptions; transfer of its 20 Hz processing or marker thresholds; claims that hand motion alone predicts bag outcome. | Track the projectile where possible; make bag–wrist persistent divergence a release candidate; preserve manual review; relate bag speed/direction to body kinematics without copying task-specific thresholds. |
| [Stenum, Rossi & Roemmich (2021)](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1008935) | In simultaneous OpenPose/video and motion-capture gait data, viewpoint affected estimates; manual identity/left-right review was needed; criterion comparison was essential. The paper reports task-specific gait errors. | Reuse of gait error values as RTMPose upper-limb cornhole thresholds; generic claims of phone-video accuracy; equivalence across views or tasks. | Fix and record camera geometry; use view-specific metrics; review person/landmarks; validate this task/model separately; report agreement and repeatability separately. |
| [Sih, Hubbard & Williams (2001)](https://www.sciencedirect.com/science/article/abs/pii/S0021929000001858) | Single-camera 2D analysis assumes motion in a calibrated plane perpendicular to the camera axis. Out-of-plane motion creates error; correction is possible when camera distance and out-of-plane information are known. | Assuming zero depth; treating a distant board as athlete-plane scale; applying an unmeasured correction; a generic error bound. | Describe all body/bag values as projected 2D; prioritize a perpendicular side view; reject incompatible comparisons; require a motion-plane calibration object for physical velocity. |
| [Challis (1999)](https://pure.psu.edu/en/publications/a-procedure-for-the-automatic-determination-of-filter-cutoff-freq/), DOI [10.1123/jab.15.3.303](https://doi.org/10.1123/jab.15.3.303) | A method for selecting Butterworth cutoff by varying it until the residual best approximates white noise; evaluation included signal and first/second derivatives. | A universal 6 Hz cutoff, a required filter order, or validation on short/gapped markerless cornhole trajectories. | Treat 6 Hz as a pilot start; save settings; inspect residuals and 4/6/8 Hz sensitivity, especially for velocity/acceleration. |
| [ACL Rules & Regulations](https://www.iplaycornhole.com/about/acl-information/rules-regulations), page updated 2025-10-24 and checked 2026-09-08 | Nominal board is 2 by 4 ft; hole is 6 in diameter, centered, with center 9 in from the back; board spacing is 27 ft front-to-front; bag values are 3 through hole, 1 on board or hanging in hole, 0 otherwise/foul; round scoring uses cancellation. | Laboratory precision of a clicked board point; a single bag value as the round score; permanence of rules across future seasons. | Use nominal `(12,39)` in hole center from the pitcher/front origin and `r=3` in; save rule date; label clicks approximate; store foul state; call 0/1/3 a per-bag value. |
| [ACL Equipment: boards](https://www.iplaycornhole.com/about/acl-information/equipment-bags-boards), checked 2026-09-08 | Certification tolerances include 23.75–24.25 in width, 47.75–48.25 in length, 6 in hole with ±0.0625 in tolerance, and nominal 11° deck angle. | That every practice board has nominal dimensions or that board geometry calibrates the athlete's motion plane. | Measure the actual study board for spatial work; keep rule nominal geometry as the UI default; do not use the distant board for athlete-plane m/s. |

## Cornhole-specific evidence gap

The reviewed sources establish why trajectory, release, projectile, filtering, and viewpoint deserve attention. None validates the complete combination used here: cornhole underhand throwing, a deformable bag, one consumer camera, Sports2D/RTMPose body landmarks, semi-automatic bag tracking, manual event review, and approximate board outcomes.

Consequently:

- no published error number is copied into a cornhole pass/fail threshold;
- no numerical metric is called a biomechanical norm;
- no coach-selected reference is called ideal or perfect;
- no association is described as causal;
- no software test is described as measurement validation.

The research contribution is the transparent workflow and the planned task-specific evidence—not a claim that the evidence already exists.

## Design decisions that remain hypotheses

The following are application choices to test, not findings from the literature:

- side view as the primary Stage 1 setup;
- 6 Hz fourth-order zero-phase filtering as a pilot default;
- maximum short-gap interpolation policy;
- the automatic bag–wrist release rule and its persistence parameters;
- arm-length normalization for path comparison;
- which release, radius, path, or trunk metrics are most useful;
- five-throw and eight-pair display gates;
- any reference-similarity or consistency tolerances;
- wording of deterministic coach-facing summaries.

Their evaluation belongs in [VALIDATION_PLAN.md](VALIDATION_PLAN.md). Full equations and units are in [BIOMECHANICS_METHODS.md](BIOMECHANICS_METHODS.md).
