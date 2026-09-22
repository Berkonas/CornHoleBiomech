# What green, yellow and red actually mean

Added in 0.6.0. Colors have explicit definitions and text/icons; they are not universal technique, medical, safety or skill grades.

## Simulation

The hole disk is green, solid board yellow, off-board region red. This is geometry for the point-bag model. A projected airborne point inside the green disk does not itself score. Terminal capture is 3/green, stationary board rest is 1/yellow, ground contact is 0/red, and unresolved/invalid is gray. Simplified hole capture, no bag deformability, and the absence of finite bag/rim physics limit real-world accuracy. The four one-input sensitivity experiments recompute the full model; their colors reflect the resulting terminal states.

## Observed video outcomes

An explicitly recorded bag value 3 is green, 1 is yellow, and 0 is red. Missing outcomes are gray and remain null. A 1-point board bag can be tactically intentional. These colors describe scoring categories, not a coach's assessment of the decision.

## Empirical zones for release metrics

For each of projected bag angle, calibrated speed (m/s), normalized speed (arm lengths/s), elbow included angle and trunk inclination, `flight.personal_evidence` compares the selected value with outcome-group interquartile intervals (IQRs). Units are kept separate. Eligibility is assigned by `insights.generate_insights`:

1. Same athlete, session, throwing side, camera view, throw type, intended target, pose backend/model/version, source hash and processing configuration (existing compatibility gate).
2. No pending corrections; at least 80% usable pose frames.
3. Fixed side-camera setup explicitly confirmed, release manually reviewed, and at least 80% raw release-window landmark visibility.
4. Bag metrics additionally require reviewed identity covering the launch fit and an `estimated` launch fit status.
5. Finite metric and an explicitly observed outcome. Unknown scores do not enter either scored group.
6. Exclude the current throw from both groups. Require at least **10 other eligible hole throws and 10 other eligible board/miss throws** for the particular metric. The current measurement must independently meet the same review gates.

Let H=[Q25,H,Q75,H] for hole throws and B=[Q25,B,Q75,B] for board/miss throws, calculated with NumPy's linear quantile interpolation. For selected value x:

| Zone | Exact condition | Meaning |
|---|---|---|
| Green | x∈H and x∉B | Matches the middle 50% of this athlete's hole group only |
| Red | x∈B and x∉H | Matches the middle 50% of this athlete's board/miss group only |
| Yellow | x lies in both intervals, or in neither | Overlap or insufficient separation; the groups do not classify the value |
| Gray | Eligibility, measurement or sample-count requirement missing | No color interpretation available |

Boundaries are inclusive. A zero-width IQR is an observed constant, not a manufactured tolerance. Outliers outside both IQRs are yellow, never automatically red. Board/miss values deliberately combine scores 0 and 1 for this exploratory comparison; individual outcome categories remain visible elsewhere.

**This is a declared exploratory display rule.** Central 50%, the 10-per-group minimum and the 80% visibility gates are transparent display/review choices, not validated statistical decision boundaries. Green does not mean a statistically significant association, a successful next throw, or a causal benefit. Red does not mean wrong or unsafe mechanics. Sample distributions may overlap and change as data accumulates. No success probability is estimated. The app shows the intervals, eligible counts and explanation; users can inspect the broader neutral distributions (minimum five observations) separately.

At least 20 historical throws plus the current throw are therefore needed even in the best case. The small development video set does not establish these personal ranges. Do not fabricate a green range to fill the UI. Collect repeated, comparable throws and independently review release, scale, tracking and outcome first.

## Why the metrics matter

- Release angle distributes initial velocity between horizontal travel and vertical height. Its effect depends on speed and position; 45° is not a universal cornhole optimum.
- Release speed sets translational kinetic energy and affects flight/contact at a given angle. Projected or body-normalized measurements must not be substituted for calibrated 3D speed.
- Elbow configuration changes the hand's position and the velocity produced by link motion. The same elbow angle can coexist with different angular velocities and outcomes.
- Trunk inclination may alter release geometry, but measured association alone cannot isolate its causal effect. The current swing simulator holds the trunk fixed.

These mechanism explanations accompany the primary measurements. Raw video metrics remain measured/derived/estimated as previously documented; the feedback classification is a separate descriptive inference.

## Verification

Python tests independently check IQR thresholds, leave-current-out counts, green/red/yellow cases, overlap, outside-both ambiguity, insufficient groups, review gating, nonfinite metrics, unknown outcomes and bag identity review. Native decoding uses optional feedback for backward compatibility. Existing results can refresh to obtain descriptive feedback; absent review metadata yields gray until properly reviewed/reanalyzed. No old athlete records are recoded as successes or failures by this feature.
