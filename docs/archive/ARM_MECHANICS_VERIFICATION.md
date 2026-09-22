# Arm Mechanics verification — 14 September 2026

## Implemented

- Native **Arm Mechanics** sidebar destination: all four nonlinear pendulum models, adjustable initial conditions, length and bag mass, geometry and angle plots, time scrubber, energy drift and corrected equation disclosures.
- **Results** panel: projected mean flexion, elbow excursion, sample SD and radius CV; phase and coverage context; normalized curve with forward-swing shading and a synchronized video cursor.
- Python result blocks, flat summary fields, metric metadata, outcome relationships, portable HTML report section and phase figure.
- Backward compatibility: the new result block is optional. Existing recordings require reanalysis for the new metrics; no participant library was rewritten or reanalyzed as part of this implementation.
- Six original supplied pages retained locally in `research/pendulum-notes`; corrected derivations and audit in [PENDULUM_MODELS.md](PENDULUM_MODELS.md).

## Executed checks

| Check | Result |
|---|---|
| Full Python suite | **104 passed** |
| Native model/persistence and mechanics suite | **23 passed**, zero failures |
| Independent mechanics check | All four models satisfy finite-difference Euler–Lagrange residuals from independently reconstructed Cartesian energies, including nonzero shoulder/elbow torque mapping |
| Analytical cases | Single point-mass and uniform-rod limits, mass independence for simple single, equilibrium |
| Numerical checks | Positive inertia determinants, energy drift < 10⁻⁵ of gravitational energy scale over UI control extremes, RK4 refinement at 0.002 and 0.001 s against 0.0001 s |
| Production build | Passed; ad-hoc signed and strict signature-verified; rebuilt again after visual corrections |
| Synthetic integration | Nine throws analyzed; every arm-motion block matches its flat summary values; all four new features appear in outcome relationships with nine complete pairs |
| Synthetic library schema | Schema 3 passed with no missing-file warnings |
| Export | Self-contained HTML includes saved gated metrics, corrected equations and embedded phase plot; automated test checks stale metric suppression and stale plot removal |
| Whitespace | `git diff --check` passed |

The initial convergence test used coarser steps (0.01 and 0.005 s); one endpoint comparison was not in the fourth-order asymptotic regime. Refinement at steps bracketing the production solver (0.002 and 0.001 s) passed for all four models against the finer reference. No equation change was needed. Conservation and the independent energy-based residual tests passed separately.

## Visual QA

Rendered the actual native SwiftUI views offscreen through `NSHostingView`:

- All four model selections at 1050 px width.
- Double compound model at 760 px content width, verifying stacked geometry/curve layout.
- Expanded double-compound equations, including signs, indices, units and sources.
- Measured-results panel decoded from the real synthetic Python JSON output.
- Exported phase figure, inspected as an image.

Fixed an unused θ₂ legend entry in single-link mode and changed the model controls to two balanced columns. Native renders show readable labels, plots, units, phase shading and wrapped equations. The measured synthetic example shows 25.9° mean flexion, 4.4° excursion, 1.4° within-swing SD and 0.3% radius CV, from frames 12–36 with 100% coverage. These are synthetic software-QA values, not participant findings.

Artifacts are retained locally under `qa-artifacts/arm-mechanics-20260914`, including the render harness, PNGs, self-contained synthetic report and test/build logs. The disposable nine-throw fixture is `/tmp/cornhole-arm-qa.cornholeproject`; its app support path is isolated from the user's library.

**Remaining UI limitation:** the native computer-use inspection service repeatedly failed with “Sky Computer Use native pipe closed before response,” including after a reset. The app launched successfully with the isolated fixture, but this session could not verify live clicks, scrolling, time dragging or video synchronization through that service. Offscreen rendering verifies layout, not hands-on interaction. The QA processes were closed after review.

## Scientific boundary

These checks establish correct implementation of the stated idealized equations and descriptors. They do not validate anatomical 2D measurements against ground truth, identify human torques, or demonstrate that straighter elbows improve cornhole outcomes. A fixed bent elbow also has one rigid configuration. The app explicitly presents the straight-arm idea as a hypothesis requiring repeated real throws and reviewed outcomes.

Open the rebuilt app through `dist/Cornhole Biomechanics Lab.app`. A separate old version 0.2.0 application exists directly on the Desktop; it was not replaced. The `dist` link points to the verified updated build in Application Support.
