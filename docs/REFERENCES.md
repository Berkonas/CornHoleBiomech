# References

**Web sources accessed 8 September 2026 unless another date is stated.** Software/model versions and hashes used for a particular trial belong in that trial's manifest; this bibliography records the evidence reviewed for the application.

## Course sources

- Zelik, K. E. (2026). *Project 1: Biomechanics of Human Movement (Fall 2026)*. Vanderbilt University. Local course handout, file `research/course/Project 1 Topics - Fall 2026 - 082126.pdf`, updated 21 August 2026.
- Zelik, K. E. (2026). *ME 3890/5890 & BME 3890/8901: Biomechanics of Human Movement, Fall 2026*. Vanderbilt University. Local syllabus, file `research/course/Biomechanics_Syllabus_Fall2026_082126.pdf`, updated 21 August 2026.

The course PDFs are local source material and are not distributed with the application.

## Primary biomechanics and motor-control literature

- Challis, J. H. (1999). A procedure for the automatic determination of filter cutoff frequency for the processing of biomechanical data. *Journal of Applied Biomechanics, 15*(3), 303–317. [https://doi.org/10.1123/jab.15.3.303](https://doi.org/10.1123/jab.15.3.303). [Author's institutional publication record and abstract](https://pure.psu.edu/en/publications/a-procedure-for-the-automatic-determination-of-filter-cutoff-freq/).
- Nasu, D., Matsuo, T., & Kadota, K. (2014). Two types of motor strategy for accurate dart throwing. *PLOS ONE, 9*(2), e88536. [https://doi.org/10.1371/journal.pone.0088536](https://doi.org/10.1371/journal.pone.0088536). [Full article](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0088536).
- Sih, B. L., Hubbard, M., & Williams, K. R. (2001). Correcting out-of-plane errors in two-dimensional imaging using nonimage-related information. *Journal of Biomechanics, 34*(2), 257–260. [https://doi.org/10.1016/S0021-9290(00)00185-8](https://doi.org/10.1016/S0021-9290(00)00185-8). [Publisher abstract](https://www.sciencedirect.com/science/article/abs/pii/S0021929000001858).
- Stenum, J., Rossi, C., & Roemmich, R. T. (2021). Two-dimensional video-based analysis of human gait using pose estimation. *PLOS Computational Biology, 17*(4), e1008935. [https://doi.org/10.1371/journal.pcbi.1008935](https://doi.org/10.1371/journal.pcbi.1008935). [Full article](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1008935).
- Tran, B. N., Yano, S., & Kondo, T. (2019). Coordination of human movements resulting in motor strategies exploited by skilled players during a throwing task. *PLOS ONE, 14*(10), e0223837. [https://doi.org/10.1371/journal.pone.0223837](https://doi.org/10.1371/journal.pone.0223837). [Full article](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0223837).

These task-specific studies motivate questions and methods. Their numerical results are not cornhole validation thresholds; see [RESEARCH_BACKGROUND.md](RESEARCH_BACKGROUND.md) for the explicit supports/does-not-support matrix.

## Sports2D and pose software

- Pagnon, D., & Kim, H. (2024). Sports2D: Compute 2D human pose and angles from a video or a webcam. *Journal of Open Source Software, 9*(101), 6849. [https://doi.org/10.21105/joss.06849](https://doi.org/10.21105/joss.06849). [JOSS article and paper](https://joss.theoj.org/papers/10.21105/joss.06849). Published 24 September 2024.
- Pagnon, D. (2026). *Sports2D v0.8.34: MacOS support, enhanced sorting function*. [Official GitHub release](https://github.com/davidpagnon/Sports2D/releases/tag/v0.8.34). Released 10 July 2026; tag commit `fe6dcad`; latest stable release when checked 8 September 2026.
- Sports2D maintainers. *Sports2D repository and documentation*. [https://github.com/davidpagnon/Sports2D](https://github.com/davidpagnon/Sports2D). Current documentation checked 8 September 2026.
- Python Packaging Authority. *sports2d 0.8.34*. [https://pypi.org/project/sports2d/0.8.34/](https://pypi.org/project/sports2d/0.8.34/). Current package status checked 8 September 2026.
- Pagnon, D., Domalain, M., & Reveret, L. (2022). Pose2Sim: An open-source Python package for multiview markerless kinematics. *Journal of Open Source Software, 7*(79), 4362. [https://doi.org/10.21105/joss.04362](https://doi.org/10.21105/joss.04362). [Official repository](https://github.com/perfanalytics/pose2sim).
- Jiang, T., Lu, P., Zhang, L., et al. (2023). RTMPose: Real-time multi-person pose estimation based on MMPose. *arXiv*. [https://doi.org/10.48550/arXiv.2303.07399](https://doi.org/10.48550/arXiv.2303.07399). [Official MMPose repository](https://github.com/open-mmlab/mmpose).
- Google. *MediaPipe Pose Landmarker*. [Official documentation](https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker). Checked 8 September 2026.

Pinned application targets are **Sports2D 0.8.34** and **Pose2Sim 0.10.49**. “Latest” is time-dependent, so it is always accompanied by the check date. A later release is not adopted without the isolated equivalence review in [SPORTS2D.md](SPORTS2D.md).

## Cornhole rules and geometry

- American Cornhole League. *Rules & Regulations*. [https://www.iplaycornhole.com/about/acl-information/rules-regulations](https://www.iplaycornhole.com/about/acl-information/rules-regulations). Page states “updated 10/24/25”; current page checked 8 September 2026. Used for play layout, nominal board dimensions, bag values, fouls, and cancellation scoring.
- American Cornhole League. *Bags + Equipment: Board Info & Resources*. [https://www.iplaycornhole.com/about/acl-information/equipment-bags-boards](https://www.iplaycornhole.com/about/acl-information/equipment-bags-boards). Checked 8 September 2026. Used for current certified-board tolerances and nominal deck angle.

Because rules can change, every participant protocol/report should state the rule page and access date actually used. The application stores a per-bag 0/1/3 value; it does not calculate a full round's cancellation score unless that separate feature is explicitly implemented.

## Numerical implementation documentation

- SciPy Developers. `scipy.signal.butter`. [Official API documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.butter.html). Checked 8 September 2026.
- SciPy Developers. `scipy.signal.sosfiltfilt`. [Official API documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.sosfiltfilt.html). Checked 8 September 2026.
- SciPy Developers. `scipy.stats.spearmanr`. [Official API documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.spearmanr.html). Checked 8 September 2026.
- SciPy Developers. `scipy.stats.bootstrap`. [Official API documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html). Checked 8 September 2026.

API documentation supports implementation semantics; it is not evidence that a chosen biomechanical parameter, cutoff, or sample size is scientifically appropriate.

## Throwing accuracy and release mechanics (added 2026-09-24)

Added for the scene/throw-plane/body-to-outcome chain engine (`METHOD_VERSION 2026.09.24-scene`;
[measurement-engine design spec §10](superpowers/specs/2026-09-23-measurement-engine-design.md#10-references-to-add-to-docsreferencesmd)).
Two of the spec's nine listed sources are already cited above and are not duplicated here: Nasu,
Matsuo & Kadota (2014, under "Primary biomechanics and motor-control literature") and Sih, Hubbard
& Williams (2001) with Tran, Yano & Kondo (2019, same section).

- Venkadesan, M., & Mahadevan, L. (2017). Optimal strategies for throwing accurately. *Royal Society Open Science, 4*, 170136. [https://doi.org/10.1098/rsos.170136](https://doi.org/10.1098/rsos.170136). Motivates the release-speed-margin-over-minimum and release→landing error-budget analyses (`chain_analysis.error_budget_analysis`, `mechanics.speed_margin_over_minimum`).
- Hore, J., & Watts, S. (2011). Skilled throwers use physics to time ball release to the nearest millisecond. *Journal of Neurophysiology, 106*, 2024–2033. [https://doi.org/10.1152/jn.00059.2011](https://doi.org/10.1152/jn.00059.2011). Motivates the release-timing-sensitivity quantity; see [BIOMECHANICS_METHODS.md](BIOMECHANICS_METHODS.md) for why it is currently unavailable on the pilot footage.
- Putnam, C. A. (1993). Sequential motions of body segments in striking and throwing skills of humans. *Journal of Biomechanics, 26*(Suppl. 1), 125–135. [https://doi.org/10.1016/0021-9290(93)90084-R](https://doi.org/10.1016/0021-9290(93)90084-R). Motivates the shoulder→elbow→wrist-speed→release peak-sequence description (`chain.body_chain`); explicitly not used to grade the sequence (cornhole is a slow accuracy swing, not the fast throws the source describes).
- Linthorne, N. P. (2001). Optimum release angle in the shot put. *Journal of Sports Sciences, 19*(5), 359–372. [https://doi.org/10.1080/02640410152006135](https://doi.org/10.1080/02640410152006135). Motivates the within-athlete speed–angle trade-off analysis (`chain_analysis.speed_angle_tradeoff`); the source's finding that the best angle is athlete-specific is why the analysis reports a Theil–Sen slope, not a fixed target angle.
- Müller, H., & Sternad, D. (2004). Decomposition of variability in the execution of goal-oriented tasks: three components of skill improvement. *Journal of Experimental Psychology: Human Perception and Performance, 30*(1), 212–233. [https://doi.org/10.1037/0096-1523.30.1.212](https://doi.org/10.1037/0096-1523.30.1.212). Tolerance–Noise–Covariation framing for the covariance-aware error budget and covariation-reduction figure (`chain_analysis.error_budget_analysis`) and for `coaching.py`'s existing compensation analysis.
- Needham, L., Evans, M., Wade, L., Cosker, D., McGuigan, M. P., Bilzon, J. L., & Colyer, S. L. (2021). The accuracy of several pose estimation methods for 3D joint centre localisation. *Scientific Reports, 11*, 20673. [https://doi.org/10.1038/s41598-021-00212-x](https://doi.org/10.1038/s41598-021-00212-x). Reported 16–48 mm markerless joint-centre error is the source of `LANDMARK_NOISE_PX`/`landmark_noise_m` in the chain's Monte Carlo (`chain.py`).
- Winter, D. A. (2009). *Biomechanics and Motor Control of Human Movement* (4th ed.). John Wiley & Sons. General reference for differentiation noise amplification, motivating the rule that second-derivative chain quantities (acceleration, force, power) are reported only when their Monte Carlo interval is narrower than the between-throw effect being described.

## Source-use boundary

Untracked local books and design files under `research/` were **not read, cited, redistributed, or used as evidence** in this pass. They remain opaque user-owned material. The unrelated legacy `research/design/DESIGN_RESEARCH.md` was identified in the earlier audit as research for a different “Places” product and is not a source for this application.
