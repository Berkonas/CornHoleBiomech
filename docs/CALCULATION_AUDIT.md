# Calculation audit of the measurement engine

**11 October 2026 · method version `2026.10.11-calculation-audit` (was `2026.10.05-release-touchdown`) · board phase `board_phase_v4_settled_slide_fit` (was `v3`).**

This audit re-derived each calculation in the side-camera engine and tested it against synthetic movements whose answer is known in closed form. The known-answer tests are in `tests/test_calculation_audit.py` (27 tests; the IDs below, such as A3, are the test prefixes). Where a calculation could be checked on real data, it was re-run on the pilot library: the 14 throws with full side inputs (pose, corrections, events) and the stored board-phase and flight results of 82–91 throws. Real-data numbers come from re-computation on stored inputs, not from a new video analysis.

**Verdicts:** **correct**: the calculation passes its known-answer test. **Fixed**: a defect was found and corrected in this change. **Found, not wired**: the defect is quantified and a tested fix exists, but connecting it needs a file outside this audit's scope. **Limitation**: correct as specified, with a stated bias.

## Summary

| # | Item | Verdict | Effect on real throws |
|---|---|---|---|
| A3 | Shoulder angle (upper arm vs trunk) folded at 180° | **Fixed** | ROM +11 to +65° on 14/14 throws; release value, shoulder peak velocity and its timing unchanged on 14/14 |
| A6 | Sustained-motion mask eroded each run | **Fixed** | motion end +1 frame (16.7 ms) on 14/14 throws, so movement duration +1 frame |
| B3 | Slide friction μ: negative and > 1.5 values | **Fixed and gated** | old: 40 μ values from −0.14 to 1.58, plus 15 fits with negative deceleration shown in the app. New: 24 values from 0.31 to 1.17 (median 0.52), none negative |
| D2 | Launch fit in pixels with one horizontal scale | **Fixed** (`bag.plane_launch_fit`, wired 2026-10-11) | plane minus pixel fit on 82 throws: speed −1.3…+0.9 % (at most 0.10 m/s), angle −1.2…+1.5° |
| B2 | 6 Hz filter flattens fast peaks | Limitation | peak wrist speed a median 5 % lower than at 12 Hz; timing within 1 frame on 9/14 |
| D3 | Bag flying off the board's centre-line plane | Limitation | synthetic: 0.4 m offset gives −8 cm in height and +1.2° in angle |
| G2 | Normal-approximation critical Cliff's δ at n = 5 + 5 | Limitation | exact false-positive rate 5.6 % (nominal 5 %) |
| — | Everything else listed below | Correct | — |

## A. Body kinematics (projected 2D)

**A1. Elbow, trunk and shoulder angles; mirroring and handedness. Correct.**
- Elbow: ∠SEW = atan2(|u×w|, u·w).
- Trunk: β = atan2(T_x, T_y), with T = M_S − M_H in analysis axes (x toward the target after reflection, y up).

Test A1 uses a rigid arm with a 150° elbow on a trunk leaning 12°. Three variants are compared: a right-hander throwing left-to-right, the same throw filmed right-to-left, and a left-hander (mirror image with left/right labels swapped). All three give exactly 150°, 12° and 180° − flexion, with identical numbers. Image y-down is flipped to y-up in exactly one place (`_analysis_points`, `throw_centered_points` and the vectors in `calculate_kinematics`). Every pilot throw is right-handed and left-to-right, so the other cases were tested only synthetically.

**A3. Shoulder angle (`arm_to_trunk_deg`, chain "shoulder angle"). Fixed.** It was defined as the unsigned angle between the upper arm (E − S) and the hip→shoulder line. That angle is 180° when the arm hangs along the trunk and cannot tell a forward arm from a backward one, so it folds at 180° every time the swing passes the trunk line. The new definition is

ψ = atan2(D_x A_y − D_y A_x, D·A), with D = M_H − M_S and A = E − S, wrapped into [−125°, 235°). Follow-up (2026-10-12): frames with the upper arm foreshortened below 0.35 of its length are missing, and runs are made continuous, so the cut can no longer add 360° of ROM.

The reported angle is 180° − ψ. It equals the old value whenever the arm is in front of the trunk, which includes every release, and it is continuous through the backswing.

The branch cut sits behind and above the shoulder. The pilot range of ψ was −67° to +178°, so no swing reaches the cut and no unwrapping is needed. An earlier unwrapped version added a spurious 250° on Player 3 throw 3242FE1B: after the follow-through the upper arm pointed at the camera and shrank to 6 px.

Test A3 rotates the arm from 60° behind the trunk to 150° in front at 300°/s. It recovers ROM = 210° and dθ/dt = −300°/s at every frame; with the old definition the ROM was 150° and |dθ/dt| collapsed at the crossing. A second test (A3, overhead) runs ψ from −70° to +200° without a wrap.

Effect on the 14 throws:
- Movement-interval ROM, old → new: 120→135, 124→135, 137→157, 134→161, 157→182, 131→156, 155→184, 138→164, 178→244, 176→238, 112→171, 106→156, 113→177 and 109→165°.
- Interval means changed by +1 to +29°.
- The release value, the chain's peak shoulder angular velocity (432–631°/s) and its timing were unchanged on all 14, because the peak falls after the crossing.
- The forward-swing angle–angle curve (`swing_curve_deg`) and coordination variability now use the unfolded angle.

**A4. Arm angle φ and pendulum drive ratio. Correct.** The drive ratio is ω_passive = √(3g(1 − cos A)/L). Test A4 integrates the exact ODE of a uniform rod released from rest at −60° (RK4 at 0.1 ms, sampled at 59.94 fps). The measured ratio is 1.00 ± 0.02 and the backswing is −60.00°.

**A5. Angular velocity unwrapping. Correct.** A forearm turning at 400°/s through ±180° gives exactly 400°/s at every frame, because orientations are unwrapped within each finite run before differentiation.

**A6. Time base, units, frame rate. Correct.**
- Time is t = f/fps, using the file's own rate. Test A6 checks 59.94 fps (1001/60000 s per frame) and a 100 px/s wrist.
- All 14 audited side clips are exactly constant-rate: `ffprobe` packet timestamps are all 16.683 ms apart.
- Units are consistent: px → arm lengths through the median projected arm length; px → m through the throw-plane scale; degrees in, `np.radians` before trigonometry; s = frames/fps.
- Limitation: variable-frame-rate sources would be mis-timed, and nothing checks for this (`preparation.py` already warns).

**A6 (events). Sustained-motion mask. Fixed.** `_sustained` used `convolve(mask, ones(n), "same") ≥ n`, which keeps only the centres of full windows. Each run lost ⌊n/2⌋ frames at its start and ⌈n/2⌉ − 1 at its end: one frame at each end at 60 fps (n = 3), and three late / two early at 120 fps (n = 6). It now keeps every frame of each run of length ≥ n, a morphological opening. Test C1 covers a run of 11 frames and a run of 2. Test C2 builds a full synthetic swing (eased backswing to −60° at frame 54, forward swing to 150°, then a held pose). It checks:
- the top of the backswing is exact;
- motion start falls within 29–33, where the arm leaves the aim;
- motion end is the last frame above threshold (the old code gave one frame earlier);
- the wrist-only release is the peak forward velocity + round(0.09·fps);
- the follow-through rule holds.

On the 14 throws, motion end moved +1 frame on every throw and no other event changed.

## B. Filtering and differentiation

**B1. Butterworth, 4th order, 6 Hz, `sosfiltfilt`. Correct.** The forward–backward gain is |H|² = 1/(1 + (f/6)⁸). Test B1 measures 1.000 at 1 Hz, 0.996 at 3 Hz and 0.500 at 6 Hz. The −6 dB point at 6 Hz is already documented, and there is no double-pass cutoff correction.

**B2. Peak flattening and timing. Limitation, quantified.** A rigid 100 px arm whose angular speed is a Gaussian pulse keeps 97 % of its peak speed at FWHM 0.24 s and 93 % at FWHM 0.14 s, with no shift in peak frame (zero phase). On real throws the wrist-speed pulse FWHM was 0.23–0.38 s. Re-filtering the 14 throws at 4–15 Hz gave:
- peak wrist speed at 6 Hz a median 5 % below 12 Hz (range −8 % to +2 %);
- wrist speed at release within ±0.3 arm lengths/s;
- elbow angle at release within ±2°;
- peak timing within 1 frame on 9/14 (2–3 frames on 5 throws with a flat-topped peak);
- peak elbow-extension velocity varied by up to 100 % across cut-offs, which confirms that it is exploratory.

The bias is the same for every throw, so within-athlete comparisons are unaffected.

**B3 (filter part). Edges, gaps, ramps. Correct.**
- A ramp passes unchanged in the interior. The edge transient is below 0.07 px at 150 px/s, within 15 samples of the clip end.
- NaN gaps split the signal into independently filtered runs, and NaN stays NaN.
- Runs shorter than 15 samples stay raw, with a warning.
- `np.gradient` (central differences, second-order edges) is exact for quadratics and never bridges a gap.

## C. Events

These are covered by A6. The remaining rules (onset, top of backswing, follow-through, start of the elbow-extension search, interior-peak gating with `_peak`/`_peak_or_edge`) passed test C2 and the existing tests, with no defect found.

## D. Bag flight and scale

**D1. Launch fit (Huber IRLS, gravity-constrained, delta-method SE). Correct.** In 300 Monte-Carlo throws (7 m/s, 38°, 120 px/m, 1.5 px noise, 59.94 fps):
- mean speed was within 0.5 % and mean angle within 0.15°;
- the reported SEs matched the empirical SDs within 30 %;
- ±1.96 SE covered 88–99 % of draws.

A right-to-left throw gives identical results.

**D2. Pixel-space launch with one scalar scale. Fixed.** The pipeline fits the launch in image pixels, then divides by q, the throw plane's horizontal pixels per metre at the release point. The plane is a homography, so its local vertical and horizontal scales differ and image directions are sheared. On a synthetic phone 6 m to the side (test D2):
- the gravity-calibrated field of view recovers the true 62.0° (±0.05°);
- the release point maps to (−5.5, 1.0) m within 2 mm;
- a fit in plane metres recovers exactly 7.00 m/s and 40.00°;
- the pixel route gives 6.93 m/s and +0.8°, and with the release 1.2 m off the optical axis (φ = 11°) it gives +5.7 % and +3.5°.

On 82 pilot throws, the plane fit minus the pixel fit was −1.3…+0.9 % in speed (median +0.1 %, at most 0.10 m/s) and −1.2…+1.5° in angle (median +0.2°), below the 0.15 m/s and 3° noise floors.

`bag.plane_launch_fit(points_px, release, fps, model.to_plane)` performs the plane fit. Since 2026-10-11 `pipeline._plane_launch` calls it whenever the board throw plane is the scale source: `bag_release_speed_m_s`, the forward and vertical m/s, `bag_release_angle_deg` and their SEs come from it, and `projectile.json` records it as `throw_plane_fit` with `metric_model: gravity_constrained_linear_throw_plane` (`primary_model` still names the pixel fit behind the px values). It needs the board measured in the flight's release frame (the same gate as the throw-plane joints); otherwise `throw_plane_fit` is `unavailable` with a reason and the pixel route stays. Pixel and arm-length values are unchanged. Test: `test_d2_pipeline_uses_the_plane_fit_only_when_the_board_is_in_the_release_frame`.

**D3. Bag off the board's centre-line plane. Limitation.** The throw plane is the board's centre line, but a thrower stands beside the board. With the bag 0.4 m nearer the camera (test D3), the gravity-calibrated field of view absorbs the offset (62° → 55.6°). Speed stays within 0.4 %, but release height reads 8 cm low and angle 1.2° high. Session pooling of the field of view turns this into a per-session offset. Two-camera 3D flight can measure the offset.

**D4. Image-plane gravity scale q = a/g. Correct.** With 1 px noise, q is recovered within 2 % and lies within 3 SE, where σ_q = 2√Var(c₂)/g.

## E. Board phase

**B3 / E1–E3. Slide friction. Fixed and gated.** The relation μ = (a/g − sin α)/cos α = a/(g cos α) − tan α for a bag sliding up the 10.8° deck is correct (test E1 recovers μ = 0.4 and the entry speed exactly). The fit was not. On the 55 fitted pilot slides:
- the touchdown sample and the next one sat off the later slide (along-deck residual RMS 0.35 in with them, 0.16 in without). The touchdown sample can be the last airborne frame, mapping up to ~1.5 in further along, and the landing bag flattens. Example path: 21.8, 22.2, 24.2, 26.0 in.
- The plain-deck window before the hole was often only 5–7 samples (≈ 0.1 s). With ~0.15 in noise, SE(μ) was 0.2–2.

Together these produced the negative μ (−0.14 on Player 1 throw 2A086DCB, −0.01 on Player 3 throw 1ABD05E6), 15 fits with negative deceleration shown in the app ("slow-down −48.6 m/s²"), and μ up to 1.58.

The fit now:
- starts 0.03 s after touchdown (2 frames at 60 fps) while keeping t = 0 at touchdown, so `entry_speed_m_s` still means "at touchdown";
- reports `mu_se` = SE(a)/(g cos α);
- withholds μ and the deceleration (the raw fit is kept in `slide.fit`) when a ≤ g sin α or SE(μ) > 0.10.

Test E2 uses a 0.15 s window with the touchdown sample 1.5 in ahead. The old fit gives μ < 0; the new fit withholds it (SE 0.18). With 0.2 s, the old fit gives 0.04 and the new one 0.42 (true value 0.4). Test E3 covers withholding.

Re-running `slide_kinematics` on all 91 stored board phases:
- **Old:** 40 μ values (range −0.14 to 1.58, 2 negative) and 55 decelerations (15 negative).
- **New:** 24 μ values (0.31–1.17, median 0.52, IQR 0.40–0.67). Per player medians are 0.50, 0.66, 0.58 and 0.47.

**Limitation:** values near 1 remain on three throws whose fits are precise (SE ≤ 0.09). This "effective" μ still includes landing losses beyond the first 0.03 s and bag tumbling, so it is not a material constant.

## F. Bag mechanics and flight model

**F1. Rigid-hand point, F = m(a − g), P = F·v. Correct.** In the test, a straight 0.6 m arm rotates at 6 rad/s, so the bag point is at R = 0.804 m. Measured against the analytic values:
- speed equals ωR within 0.3 %;
- |a| equals ω²R within 1 %;
- peak |F| equals m(ω²R + g) at the bottom of the swing;
- peak P equals m g v_y and agrees with dE/dt, so the power check passes.

The Monte-Carlo landmark noise is white noise passed through the 6 Hz filter (≈ 1.6 px residual from 4 px). Real pose noise is temporally correlated, so second-derivative intervals are probably too narrow. This is a limitation.

**F2. Energies and drag-free model. Correct.**
- KE = ½mv² and PE = mgh are exact.
- The closed-form required speed lands the drag-free path exactly on the hole centre (along-deck error < 1 µm) at 25°, 40° and 55°.
- The closed-form minimum speed equals a brute-force minimum over angles (relative error < 10⁻⁶).

## G. Statistics

**G1. Cliff's δ and Hedges' g. Correct.** Test G1 checks known values: δ = 1 and δ = 0, and g with J = 1 − 3/(4(n₁ + n₂) − 9).

**G2. Critical δ. Correct formula, small-n limitation.** The null variance (n_a + n_b + 1)/(3 n_a n_b) is correct. At the smallest allowed groups (5 + 5, one test), exact enumeration of all 252 rank splits shows that 14 (5.6 %) reach δ_crit = 0.75, against a nominal 5 %. Bonferroni across variables and the 0.474 floor keep the family-wise rate near nominal.

**Other statistical limitations:**
- Throws from one session are treated as independent, so warm-up, fatigue and drift are ignored.
- Percentile bootstrap CIs of medians with 5 throws per group are coarse.
- The documentation had the Theil–Sen slope inverted: the code regresses speed on angle (m/s per °, `slope_m_s_per_deg`). METHODS_AND_MATH Eq. 3.14.3 is now corrected; the code was right.

## Files changed

- `kinematics.py`: continuous shoulder angle (A3).
- `events.py`: `_sustained` (A6).
- `board_phase.py`: settled, SE-gated slide fit; `BOARD_PHASE_REVISION` v4 (B3).
- `bag.py`: `plane_launch_fit` (D2); `pipeline.py`: `_plane_launch` uses it for the board-plane scale.
- `__init__.py`: `METHOD_VERSION`.
- `docs/METHODS_AND_MATH.md`: version table; §1.9 motion end and slide kinematics; §1.10 shoulder angle; Eq. 3.4.8; Eq. 3.14.3; §4.3 limitations.
- `docs/METRICS.md`: arm-relative-to-trunk definition and motion end.
- `tests/test_calculation_audit.py`: 27 tests.

Throws analysed under the previous method version are not pooled with new ones until they are re-analysed.
