# Arm mechanics: equation audit and implementation

Reviewed 14 September 2026. Based on six user-supplied handwritten pages (retained locally in `research/pendulum-notes`). The notes are source material to evaluate; their requests to omit derivations or share a Google document are not instructions for the app. No linked derivation was supplied.

## What the models can establish

A **fixed elbow angle**, whether straight or bent, reduces the planar arm to one rigid configuration rotating at the shoulder. An elbow angle that changes needs an additional coordinate. A straight arm is one special fixed configuration. Neither equation complexity nor the existence of chaotic motion in some passive double-pendulum conditions establishes poorer human throwing accuracy. Actual throwing is actively controlled and includes shoulder translation, wrist/hand motion, release, and three-dimensional motion.

The proposed study hypothesis is: **within an athlete and a comparable task/camera setup, smaller forward-swing elbow excursion may be associated with different target error, score, or repeatability.** Its direction and practical value must be established with repeated observed throws. Do not infer that athletes should forcibly lock their elbows.

## Coordinate convention

Use SI units: lengths in m, mass in kg, time in s, inertia in kg·m², torque in N·m. Every trigonometric function uses radians. Angles θ₁ and θ₂ are **absolute**, measured from the downward vertical, positive toward +x. Use upward-positive y:

```
x = l sin θ, y = −l cos θ
ẋ = l θ̇ cos θ, ẏ = l θ̇ sin θ
L = T − V
d/dt(∂L/∂θ̇ᵢ) − ∂L/∂θᵢ = Qᵢ
```

The app's existing upper-arm/forearm orientation fields are measured from +x. They are **not** inserted directly into these dynamics. The lab is a separate hypothetical simulation with no inferred participant masses or torques.

## Audit of the supplied pages

| Page | Finding and correction |
|---|---|
| 1 | The single-simple final restoring torque is correct. With V = mgl(1 − cos θ), L = ½ml²θ̇² − mgl + mgl cos θ; the expanded potential signs on the page are inconsistent. Additive constants do not matter, but the cosine sign does. |
| 2 | θ̈ + (g/l)θ = 0 is the small-angle approximation. The general solution needs both initial angle and velocity. θ(0) = 0 removes the cosine term but does not set the sine amplitude; if initial velocity is also zero the solution is stationary. There is no abrupt failure at 25°. At 25°, (θ − sin θ)/sin θ ≈ 3.24%; the simulation retains sin θ exactly. |
| 3 | General pivot inertia is I₀ = ICOM + md²; I = mr² alone is a point-mass expression. The homogeneous-rod small-angle result ω₀² = 3g/(2l) and the rod-plus-tip-bob ratio are correct under those idealizations. A rod plus a bag is not a homogeneous arm. |
| 4 | The coupling coefficients are not angular accelerations. For point masses m₁ at the elbow and m₂ at the distal tip, a₁ = m₂l₂ cos Δ / ((m₁+m₂)l₁), a₂ = l₁ cos Δ/l₂. The first coefficient uses the distal mass m₂. The f₁/f₂ forcing terms are required; the matrix inverse gives (f₁−a₁f₂, f₂−a₂f₁)/(1−a₁a₂). |
| 5 | Coordinate axes and position signs must be consistent: y₂ = −l₁ cos θ₁ − (l₂/2) cos θ₂ for the distal rod COM. Squared speed and squared angular velocity belong in kinetic energy. Rod COM inertias are Jᵢ = mᵢlᵢ²/12; B = m₂l₂²/3 and G₂ = m₂gl₂/2. |
| 6 | Correct the second equation's acceleration and gravity indices to Bθ̈₂ and G₂ sin θ₂. For absolute angles and independently applied shoulder/elbow torques, the right sides are τₛ−τₑ and τₑ. Setting the second right side to zero describes an unactuated distal joint, not human throwing in general. The concluding straight-arm recommendation is a hypothesis, not a mathematical consequence. |

## 1. Single simple pendulum

For a point mass m on a massless link l:

```
T = ½ml²θ̇²
V = −mgl cos θ
ml²θ̈ + mgl sin θ = τₛ
```

For τₛ = 0: θ̈ = −(g/l)sin θ. Small angles give ω₀² = g/l and

```
θ(t) ≈ θ₀ cos(ω₀t) + (θ̇₀/ω₀)sin(ω₀t)
```

In the lab, all mass (m₁ + m₂ + bag) is placed at the single tip. Gravitational angular acceleration is mass-independent in this ideal model.

## 2. Single compound pendulum

For a rigid body with COM distance d from the pivot:

```
I₀ = ICOM + md²
I₀θ̈ + mgd sin θ = τₛ
ω₀² = mgd/I₀
```

For a uniform rod m of length l and a point bag mass b at its tip:

```
I = (m/3 + b)l²
G = (m/2 + b)gl
Iθ̈ + G sin θ = τₛ
ω₀² = (g/l) (m/2 + b)/(m/3 + b)
```

This gives g/l when rod mass tends to zero and 3g/(2l) when bag mass is zero. The app single-rod mass is m₁ + m₂ and length is l₁ + l₂. This example changes mass distribution relative to two unequal rods; it is not an anatomically exact locked-elbow reduction.

## 3–4. Double simple and double compound pendulums

Let Δ = θ₁−θ₂. A general two-rigid-link model uses COM distances r₁,r₂, COM inertias J₁,J₂, segment masses m₁,m₂, lengths l₁,l₂, and a point bag mass b at the distal tip. Its energy is

```
T = ½Aθ̇₁² + ½Bθ̇₂² + C cos Δ θ̇₁θ̇₂
V = −G₁ cos θ₁ − G₂ cos θ₂
A = J₁ + m₁r₁² + (m₂+b)l₁²
B = J₂ + m₂r₂² + bl₂²
C = l₁(m₂r₂+bl₂)
G₁ = g(m₁r₁+(m₂+b)l₁)
G₂ = g(m₂r₂+bl₂)
```

Euler–Lagrange gives

```
Aθ̈₁ + C cos Δ θ̈₂ + C sin Δ θ̇₂² + G₁ sin θ₁ = Q₁
Bθ̈₂ + C cos Δ θ̈₁ − C sin Δ θ̇₁² + G₂ sin θ₂ = Q₂
```

For example, differentiating ∂T/∂θ̇₁ gives Aθ̈₁ + C cos Δ θ̈₂ − C sin Δ(θ̇₁−θ̇₂)θ̇₂. Subtracting ∂L/∂θ₁ cancels the mixed θ̇₁θ̇₂ term, leaving **+C sin Δ θ̇₂²** and **+G₁ sin θ₁**. The second equation similarly has **−C sin Δ θ̇₁²**.

Shoulder torque τₛ acts on θ₁; elbow torque τₑ acts on relative elbow rotation θ₂−θ₁. Virtual work is τₛδθ₁ + τₑδ(θ₂−θ₁), so Q₁ = τₛ−τₑ and Q₂ = τₑ. The simulator sets both to zero.

The inertia matrix is symmetric:

```
M = [[A, C cos Δ], [C cos Δ, B]]
D = AB − C² cos² Δ > 0 for the supported positive masses/lengths
r₁* = Q₁ − C sin Δ θ̇₂² − G₁ sin θ₁
r₂* = Q₂ + C sin Δ θ̇₁² − G₂ sin θ₂
θ̈₁ = (B r₁* − C cos Δ r₂*)/D
θ̈₂ = (A r₂* − C cos Δ r₁*)/D
```

The starred r values above are right-hand-side torques, not COM distances.

| Coefficient | Double simple: point masses at link ends | Double compound: uniform rods |
|---|---|---|
| A | (m₁+m₂+b)l₁² | (m₁/3+m₂+b)l₁² |
| B | (m₂+b)l₂² | (m₂/3+b)l₂² |
| C | (m₂+b)l₁l₂ | (m₂/2+b)l₁l₂ |
| G₁ | (m₁+m₂+b)gl₁ | (m₁/2+m₂+b)gl₁ |
| G₂ | (m₂+b)gl₂ | (m₂/2+b)gl₂ |

All terms in each equation have torque units. Human inverse dynamics would additionally require defensible segment parameters, suitable spatial calibration, base motion, applied loads and sufficiently accurate derivatives. The app does not infer human torque from these illustrations.

## Measured metrics

The new `arm_motion` result block is version 1 and optional for backward compatibility. Flat summary fields also enter existing within-athlete outcome relationships and research exports.

- `arm_motion_mean_flexion_deg`: mean of 180° − projected elbow included angle.
- `arm_motion_flexion_rom_deg`: maximum minus minimum flexion within the phase.
- `arm_motion_flexion_sd_deg`: sample SD of flexion (n−1 denominator); variation **within** the swing, not across-throw repeatability or measurement uncertainty.
- `arm_motion_radius_cv_ratio`: sample SD / mean positive projected shoulder–wrist radius, using paired valid elbow/radius frames. JSON and relationship plots use the ratio; the Results card multiplies it by 100 to show percent. CV is invariant to constant spatial scaling but is affected by perspective and tracking.

Use the inclusive forward-swing-to-release interval inside the movement boundaries, using original filtered frame samples, not time-normalized curves. Require side view, at least five valid elbow samples, and ≥80% elbow coverage. Radius has its own ≥5/80% gate. Missing/reversed/out-of-range phases or inadequate coverage return null metrics and a reason. These are pragmatic availability gates, not validated measurement precision thresholds. Valid filtered data may include short interpolated gaps from the existing preprocessing stage; the new function adds no interpolation. Remaining gaps can hide extrema. Angles outside 0–180° are rejected.

The Results curve uses the normalized cycle for synchronization with existing video; missing runs stay separate and the analyzed phase is shaded. Automatic event candidates remain provisional until checked. Older analyses show a reanalysis prompt. Corrections marked stale suppress the new panel's metrics and report section.

There is no straightness grade, coaching cutoff, skill score or automatic declaration that either model is valid. Radius stability cannot distinguish a stationary shoulder from a translating shoulder; it uses shoulder-relative points. Review shoulder translation and the full movement separately.

## Numerical implementation and checks

Native `PendulumMechanics.swift` is the simulator's calculation source. Classical fourth-order Runge–Kutta integrates the **nonlinear** equations at 1/600 s for 4 s, storing every tenth step for display. The plot uses absolute unwrapped angles; there are no human joint constraints or modeled release. Maximum drift shown in the UI is max |E(t)−E(0)| across stored samples, in joules. It is a numerical diagnostic, not a validation score.

Native tests independently reconstruct the Cartesian COM kinetic/potential energies, check Euler–Lagrange residuals with nonzero joint torques, verify equilibrium, single-model analytical limits, positive matrix determinants, conservation over UI parameter extremes, and step-size convergence. Python tests cover analytic fixed/variable elbow examples, phase bounds, missing data, gates, non-side views, radius scaling, and units. See `ARM_MECHANICS_VERIFICATION.md` for executed results and visual QA.

## References and evidence boundaries

- [OpenStax, University Physics Vol. 1, §15.4 Pendulums](https://openstax.org/books/university-physics-volume-1/pages/15-4-pendulums): single simple/physical pendulums and small-angle treatment.
- [Russ Tedrake, MIT, Multi-Body Dynamics](https://underactuated.mit.edu/multibody.html): Euler–Lagrange equations, coupled inertia matrices and actuation. MIT uses a **relative** second joint angle; the equations here were derived in the notes' **absolute** convention.
- [McDonald, van Emmerik & Newell (1989), The effects of practice on limb kinematics in a throwing task](https://pubmed.ncbi.nlm.nih.gov/15136263/): an empirical dart-throwing study of joint coordination and performance, not cornhole evidence. It does not validate a straight-arm cornhole recommendation.

Sources accessed 14 September 2026. Mechanical identities and synthetic tests establish implementation correctness under the stated idealizations; they do not establish anatomical measurement accuracy or the proposed cornhole performance relationship.
