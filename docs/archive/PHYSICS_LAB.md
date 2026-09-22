# Interactive Cornhole Physics Lab

Flight lab added in 0.5.0; animated linked-arm swing and evidence zones added in 0.6.0. Open **Physics Lab** in the main sidebar; an athlete or video is not required. This is an educational numerical experiment, not a validated soft-bag simulator or prediction of an athlete's next throw. It does not write hypothetical results into the athlete library.

## Using the lab

- Choose **Animated arm swing** (default) or **Direct release controls**. In swing mode, release speed, angle and position are computed from the arm; in direct mode, the top controls change release speed, elevation above horizontal, and lateral aim. Sliders and numeric fields share SI values. Positive aim points right from the thrower's perspective.
- **Throw / replay** animates the solution at quarter, half, or real-time speed. Pause, resume, scrub, choose **Inspect release**, or click a contact event to inspect it. The side view uses the same distance scale horizontally and vertically; lateral motion is visible in the board close-up.
- **Board, bag & environment** changes release height, lateral position, horizontal distance to the receiving board front, mass, drag area, wind, friction, and restitution. Distance is measured from release, not from the throwing board front; 8.23 m is an illustrative default, not an assertion that these distances are interchangeable.
- **Save comparison** keeps one full parameter set and trajectory in memory. Change one variable to see differences in contact offset from the corresponding hole, contact time and apex. **Restore** restores all inputs. Orange is the saved throw; blue is the current throw. A changed board distance shows both board locations in side view. The board close-up uses the current board coordinates.
- **Practice round** hides predictions until the throw completes and counts four independent bags. Results use model values 0, 1 or 3; there is no opponent cancellation scoring, obstruction or bag-to-bag contact. Replays do not count as additional throws. **New round** clears the temporary round.
- Scenarios demonstrate a center flight, a higher arc, a lower sliding approach and a crosswind. The center/high-arc launch speeds are obtained analytically to meet the hole center in vacuum. They are examples, not empirically optimal techniques.
- **Explore what changes the outcome** opens one-input swing experiments and a coaching explanation. Body geometry, joint motion, force calculations, and environmental details are also expandable, so the starting screen stays focused on adjusting and playing a throw.
- The expanded mathematics section shows the exact equations, current velocity components, initial energy, drag factor and an independent vacuum calculation. The live inspector gives position, speed, kinetic energy and flight acceleration at the chosen time.

Comparison and practice state are temporary and reset when the lab view is recreated or the app closes. They do not create athlete trials.

## Coordinate frame and geometry

World axes: x forward toward the receiving board, y right as viewed by the thrower, z upward. Ground is z=0. Position at release is (0, y₀, h). Velocity is

    v₀ = (v cos θ cos φ, v cos θ sin φ, v sin θ).

θ is elevation and φ is lateral aim. UI angles are degrees; integration uses radians. All other internal units are m, s, kg, N and J.

The receiving board has a 1.2192 m by 0.6096 m deck (48 by 24 inches), 0.07112 m (2.8 inch) front height and an adjustable incline, default 11°. At the default angle these consistent inputs give a back height of approximately 0.304 m; deck length is along the incline, not its horizontal projection. The 0.1524 m diameter hole is centered laterally at u=0.9906 m along the deck from the front (9 inches from the back).

At front position o=(D,0,0.07112), tangent t=(cos α,0,sin α), normal n=(−sin α,0,cos α), a surface point is o+ut+(0,y,0). Finite surface bounds are 0≤u≤1.2192 and |y|≤0.3048. Board view projects world x to u=(x−D)/cos α, ignoring the bag's height. It is a top projection, not evidence that an airborne point touches the board.

[ACL equipment specifications](https://www.iplaycornhole.com/about/acl-information/equipment-bags-boards) supply the geometry and nominal bag mass. They do not supply the simulated friction, drag, or restitution parameters.

## Flight equations

    ṙ = v
    u = v − w
    F_drag = −½ρ(C_D A)|u|u
    v̇ = (0,0,−g) + F_drag/m

Gravity g=9.81 m/s² and air density ρ=1.225 kg/m³ are held constant. Wind w=(w_x,w_y,0) is uniform and steady. C_D A is a single effective area; it is not calculated from bag orientation. Illustrative default C_D A=0.012 m² and m=0.454 kg. Air is initially disabled. When disabled, neither wind nor mass changes trajectory. Mass still changes energy. When air is active, doubling mass halves drag acceleration at the same air-relative velocity.

Classical fourth-order Runge–Kutta integrates position and velocity at a nominal 1/480 s. Air drag follows the standard quadratic model in [OpenStax, Drag Force and Terminal Speed](https://openstax.org/books/university-physics-volume-1/pages/6-4-drag-force-and-terminal-speed). A cornhole bag's orientation-dependent drag and lift need measurements; this constant-area model is not their validation.

Vacuum reference (before any board collision):

    r(t) = r₀ + v₀t + ½(0,0,−g)t²
    t_ground = [v₀z + sqrt(v₀z² + 2gh)] / g
    x_ground = v₀x t_ground
    kinetic energy = ½m|v|²

The displayed ground-range check explicitly ignores the board and drag. It must not be mistaken for board contact time. Apex is the maximum sampled world height, not height above the inclined board. Samples are retained every four integration steps plus event endpoints; flight apex discretization at that spacing is about 0.1 mm in the vacuum examples, far below the uncertainty of real bag physics.

## Contact, sliding and model scoring

Downward crossings of the board's plane are located by 24 bisection iterations using the flight integrator; the finite board bounds are then checked. The same procedure locates ground contact. Incoming velocity is retained with each event. On the solid deck:

    v_n = v · n
    v_t = v − v_n n
    v_n⁺ = −e v_n⁻
    v_t⁺ = max(0, 1 − μ(1+e)|v_n⁻|/|v_t⁻|) v_t⁻

A zero tangential speed remains zero in the impulse step. This is a normal restitution impulse and a tangential Coulomb impulse capped to avoid reversing tangential motion. Normal rebound speed below 0.18 m/s is removed as a settling approximation to avoid endless micro-bounces. This deliberately dissipates extra energy; it is not a measured bag property.

During sliding:

    g_t = g_vector − (g_vector · n)n
    v_free = v + g_t Δt
    v_next = max(0, 1 − μg cos α Δt / |v_free|) v_free
    r_next = r + ½(v + v_next)Δt

The zero-vector case is handled separately. This velocity projection approximates Coulomb friction without numerically oscillating through zero speed. It also holds a resting point if |g_t|≤μg cos α. The same μ is used for the static threshold and kinetic friction, unlike a more complete two-coefficient material model. Sliding is a first-order approximation in velocity with a trapezoidal position update; RK4 accuracy is claimed only for free flight. See [OpenStax, Friction](https://openstax.org/books/university-physics-volume-1/pages/6-2-friction) for the friction model.

Segment-circle entry detects hole crossings during a sliding step; segment-boundary intersections detect edge exit. The earliest event wins. The bag then either captures or resumes flight from the board edge. Time remaining within a collision step is advanced in the next step from that event; no physical time is skipped.

- **3:** point crosses the hole disk in descent or enters the disk while sliding. Capture is immediate, regardless of speed.
- **1:** point stops on the solid board, with static friction able to hold it.
- **0:** point contacts the ground; simulation stops without modeling ground bounce/roll.
- **Unresolved:** still moving at the 10 s horizon; never silently assigned a board point.

First-contact offsets are horizontal Δx and Δy from hole center. They can describe a ground miss and are not deck-plane errors or final-rest errors. First hole entry is reported as an entry event, although it is not contact with solid wood. A board hit may subsequently bounce or slide off. The score refers to the terminal modeled state.

## Deliberate limits

After release the bag is a translating point, not a 6-inch cloth body. The animated swing is a prescribed two-link rigid-arm model, not a model of human muscle control. No folding, deformability, finite footprint, rim collision, overhang support, spin, aerodynamic lift, tumbling, rolling, board flex or other bags are modeled. The hole rule may be very wrong near the rim or for a fast sliding bag. Board contact neglects air forces. Surface parameters and the settling threshold are illustrative, with no fitted real-bag validation. These limitations are visible in the app, including beside the result, not only in this document.

Digits support repeatable comparisons of computations. They are not an experimental confidence interval. Any coaching prescription requires calibrated video, repeated trials, independently observed outcomes, and measured material parameters. The model provides a mechanism to test, not evidence that one person's technique should match another's.

## Verification

`CornholePhysicsTests.swift` independently checks vacuum range/contact timing and trajectory against closed-form equations, energy conservation, mass independence, drag direction and mass scaling, wind symmetry, time-step refinement, analytically targeted hole examples, impact impulse/restitution and energy loss, high-friction rest, frictionless board exit, hole crossing without numerical tunneling, bounded control extremes, chronological samples, honest unresolved results and invalid input rejection.

Implementation: `CornholePhysics.swift` (pure mechanics), `CornholePhysicsView.swift` (controls, calculations, practice state), `PhysicsCanvases.swift` (equal-scale side view and board projection). Tests validate those stated equations and idealizations, not the fidelity of a deformable cornhole bag.

## Animated swing: inputs become release conditions

`SwingParameters` holds body height H, shoulder-height ratio c, shoulder width W, standing body-axis position (x_s,y_s), throwing hand, horizontal swing yaw φ, upper-arm length l₁, elbow-to-bag-center length l₂, segment masses, joint endpoint angles, forward-swing duration T and release fraction u_r. The distal segment includes the hand/grip offset; do not copy a forearm-only measurement into it without accounting for this offset.

The standing trunk is fixed and upright. The UI's shoulder-height ratio (default 0.82), width and segment masses are explicitly editable illustrative geometry, not validated anthropometric regressions. Handedness selects one shoulder; it does not confer extra speed or an accuracy correction. With d=(cosφ,sinφ,0) and lateral unit b=(−sinφ,cosφ,0):

    r_shoulder = (x_s,y_s,cH) ± (W/2)b

Use + for the right shoulder and − for the left. x_s is relative to the throwing foul line; the receiving board front has a separately specified x coordinate. Drawn feet are illustrative and do not adjudicate foot fouls.

Both joint paths use the same declared smooth interpolation:

    u = clamp(t/T,0,1)
    S(u) = 10u³ − 15u⁴ + 6u⁵
    S′(u) = 30u² − 60u³ + 30u⁴
    S″(u) = 60u − 180u² + 120u³
    q_i = q_i,start + (q_i,end − q_i,start) S(u)
    ω_i = Δq_i S′(u)/T
    α_i = Δq_i S″(u)/T²

The absolute upper-arm angle q₁ is measured from downward vertical toward the board. q₂=q₁+elbow flexion is the absolute distal angle. The included elbow angle is 180°−|q₂−q₁|. Interpolation starts at the backswing endpoint and ends at the follow-through endpoint, both at rest with zero angular acceleration. This is a controllable smooth path, not a claimed human motor-control law. Shoulder translation, torso rotation, stepping, wrist articulation and muscle feedback are absent.

    r_bag = r_shoulder + Σ l_i(sin q_i d − cos q_i ẑ)
    v_bag = Σ l_i ω_i(cos q_i d + sin q_i ẑ)
    a_bag = Σ l_i[(α_i cos q_i − ω_i² sin q_i)d
                       + (α_i sin q_i + ω_i² cos q_i)ẑ]

At t_r=u_rT the bag detaches with exactly this position and velocity. Free-flight speed is |v_bag|; elevation is atan2(v_z,sqrt(v_x²+v_y²)); aim is atan2(v_y,v_x). No additional launch impulse is invented. The flight origin shifts horizontally to the release x coordinate, so the solver's board distance is x_board−x_release, not the court spacing. World lateral position remains relative to the board center. Negative launch elevations are allowed; an early release can go toward the ground. Backward launches, below-ground arm paths and out-of-range states return an explicit invalid-release message rather than silently clamping a new throw into existence.

The playback clock is relative to release: negative times show the held bag, zero is detachment, positive times show flight and follow-through. The enlarged arm view and court side view use the same pose. The stance map shows the throwing shoulder and yaw in top projection.

## Gravitational force and inverse dynamics

Weight is m_b g downward. Before detachment, ignoring air on the held bag, the required resultant hand-on-bag force is

    F_grip = m_b(a_bag − g_vector).

At rest its magnitude equals m_b g. During the swing it includes tangential and centripetal acceleration. It is not the force of a particular muscle or contact pressure at a finger.

The two links are uniform rods and the bag is a point at the distal tip. Use the double-compound mass matrix and gravity terms already derived in [Arm Mechanics](PENDULUM_MODELS.md):

    Q₁ = Aα₁ + C cos(q₁−q₂)α₂ + C sin(q₁−q₂)ω₂² + G₁ sin q₁
    Q₂ = Bα₂ + C cos(q₁−q₂)α₁ − C sin(q₁−q₂)ω₁² + G₂ sin q₂
    τ_elbow = Q₂; τ_shoulder = Q₁ + Q₂.

These are the net joint torques required to track the chosen motion, not forward predictions of movement under fixed muscle effort. Changing bag mass changes required force and torque; it does not slow a prescribed path. To study slower movement change T, which changes angular velocity as 1/T and acceleration as 1/T². There is no estimated human strength limit, injury threshold, muscle co-contraction or tissue load. The force panel stops its calculations at the instant just before detachment and says so after release.

Reference mechanics: [MIT multibody equations](https://underactuated.mit.edu/multibody.html) and [OpenStax rotational variables](https://openstax.org/books/university-physics-volume-1/pages/10-1-rotational-variables). The particular motion curve and body proportions are declared modeling choices, not findings from these sources.

## Color zones and one-input comparisons

The simulated board map uses its actual geometric regions: green hole disk, yellow solid deck, red off-board background. An airborne projection into a region does not itself imply that outcome. The final-result badge is green only for terminal model capture, yellow for terminal board rest, red for ground contact and gray for unresolved/invalid cases. Colors do not identify safe or optimal joint angles.

Four sensitivity rows recompute complete coupled swing/flight solutions with release fraction +0.02, duration +0.02 s, upper length +0.02 m or lateral stance +0.10 m, holding other inputs fixed. They show new release speed, elevation, height and final outcome. Discontinuous score changes are possible at the simplified hole and board boundaries; these are not confidence intervals or probabilities. The changes are declared experiments, not coaching prescriptions.

Real-video analysis uses a different evidence-based color definition; see [Performance Zones](PERFORMANCE_ZONES.md). Simulator results never supply empirical athlete thresholds.

## Additional swing verification

`SwingMechanicsTests.swift` checks hand velocity and acceleration against independent finite differences of position, exact link lengths, release continuity, timing-scale laws, body-height and stance translations, handedness symmetry, static gravity moments from independent Cartesian moment arms, inverse/forward dynamics consistency, grip-force scaling with mass, downward early releases and board-angle geometry. These verify the implemented mechanics, not physiological realism.
