import SwiftUI

private struct TossComparison {
    var parameters: TossParameters
    var result: TossResult
    var swing: SwingParameters? = nil
}

struct CornholePhysicsView: View {
    @State private var swing = SwingParameters()
    @State private var swingEnabled = true
    @State private var experiments: [SwingExperiment] = []
    @State private var parameters = TossParameters.example("Center flight")
    @State private var result = CornholePhysics(parameters: .example("Center flight")).simulate()
    @State private var comparison: TossComparison?
    @State private var time = 0.0
    @State private var playing = false
    @State private var lastTick: Date?
    @State private var playbackRate = 0.5
    @State private var practice = false
    @State private var round: [TossComparison] = []
    @State private var pendingThrow = false
    @State private var reveal = false
    @State private var showEquations = false
    @State private var showExperiments = false
    private let timer = Timer.publish(every: 1.0/60, on: .main, in: .common).autoconnect()

    private var swingModel: SwingMechanics { .init(parameters: swing) }
    private var effectiveParameters: TossParameters { swingEnabled ? swingModel.launch(using: parameters) ?? parameters : parameters }
    private var model: CornholePhysics { .init(parameters: effectiveParameters) }
    private var startTime: Double { swingEnabled ? -swing.releaseTime : 0 }
    private var inspected: TossSample {
        if swingEnabled && time < 0 {
            let pose = swingModel.pose(at: swing.releaseTime+time)
            return .init(time: time, position: pose.wrist-TossVector(x: swingModel.release.wrist.x), velocity: pose.velocity, phase: .swing)
        }
        return result.sample(at: time) ?? .init(time: 0, position: .zero, velocity: .zero, phase: .flight)
    }
    private var showPrediction: Bool { !practice || reveal }

    var body: some View {
        SectionContainer(title: "Physics Lab", subtitle: "Change the release. Follow the forces. See where the bag goes.") {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 7) {
                    Label("Interactive model · hypothetical throws", systemImage: "cube.transparent").font(.headline)
                    Text("A 3D point-mass simulation with gravity, optional wind and drag, and simplified board contact. These are learning scenarios, separate from athlete results.")
                        .foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                }
                Spacer()
                Toggle("Practice round", isOn: $practice).toggleStyle(.switch).fixedSize()
                    .disabled(playing)
            }
            Picker("Release source", selection: $swingEnabled) {
                Text("Animated arm swing").tag(true)
                Text("Direct release controls").tag(false)
            }.pickerStyle(.segmented).disabled(playing || pendingThrow)
            Text("1. Adjust the motion   →   2. Play the throw   →   3. Inspect the result")
                .font(.callout).foregroundStyle(.secondary)
            if !swingEnabled {
            HStack {
                Text("Examples").foregroundStyle(.secondary)
                ForEach(["Center flight", "High arc", "Slide approach", "Crosswind"], id: \.self) { name in
                    Button(name) { swingEnabled = false; parameters = .example(name) }.disabled(playing || pendingThrow)
                }
            }
            }
            if practice { practiceCard }
            if !swingEnabled { quickControls }
            playback
            if swingEnabled {
                SwingLabPanel(parameters: $swing, bagMass: parameters.mass, boardAngle: parameters.boardAngle, time: time, launch: swingModel.launch(using: parameters))
                    .disabled(playing || pendingThrow)
            }
            if !result.samples.isEmpty {
                simulationStage
                if showPrediction { resultsCard }
            }
            controls
            comparisonCard
            DisclosureGroup("Explore what changes the outcome", isExpanded: $showExperiments) {
                if showPrediction { experimentCard }
            ResearchCard(title: "Try one change at a time", symbol: "lightbulb") {
                if swingEnabled {
                    Text("Save a comparison, then change release phase, swing duration or direction. Release phase changes the hand’s position and velocity together. A longer duration slows the same joint path. Compare first contact and final rest before trying another change.")
                } else {
                Text("Speed changes launch energy. Elevation divides that speed between upward and horizontal motion. Aim changes lateral velocity. Save a comparison, then change one control. Try +0.2 m/s of speed, +2° of elevation, or +1° of aim. Watch first contact separately from final rest: a board hit can still slide off.")
                }
                Text("A higher angle is not automatically better. Speed, height, angle and aim act together. In vacuum, bag mass does not change the flight. With drag, mass changes acceleration because the same drag force acts on a different mass.")
                    .font(.callout).foregroundStyle(.secondary)
            }
            }
            if !result.samples.isEmpty { equations }
        }
        .onAppear { recompute() }
        .onChange(of: parameters) { _, _ in recompute() }
        .onChange(of: swing) { _, _ in recompute() }
        .onChange(of: swingEnabled) { _, _ in recompute() }
        .onChange(of: practice) { _, _ in playing = false; pendingThrow = false; reveal = false; time = startTime }
        .onChange(of: playing) { _, _ in lastTick = nil }
        .onReceive(timer) { now in
            guard playing else { return }
            let elapsed = lastTick.map { max(0, now.timeIntervalSince($0)) } ?? 1.0/60
            lastTick = now
            time = min(result.duration, time+playbackRate*elapsed)
            if time >= result.duration {
                playing = false; reveal = true
                if pendingThrow { round.append(.init(parameters: effectiveParameters, result: result, swing: swingEnabled ? swing : nil)); pendingThrow = false }
            }
        }
        .onDisappear { playing = false; pendingThrow = false }
    }

    private func recompute() {
        playing = false; pendingThrow = false; reveal = false; time = startTime
        if swingEnabled && swingModel.launch(using: parameters) == nil {
            result = TossResult(outcome: "Adjust the swing to produce a valid release")
        } else { result = model.simulate() }
        experiments = swingEnabled ? SwingExperiment.compare(swing: swing, environment: parameters) : []
    }

    private var quickControls: some View {
        HStack(alignment: .top, spacing: 24) {
            control("Speed", value: $parameters.speed, range: 4...14, unit: "m/s", digits: 2, help: "")
            control("Elevation", value: $parameters.elevation, range: 10...75, unit: "°", digits: 1, help: "")
            control("Aim (+ right)", value: $parameters.aim, range: -12...12, unit: "°", digits: 1, help: "")
        }.disabled(playing || pendingThrow)
    }

    private var simulationStage: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label("Flight & board", systemImage: "point.topleft.down.curvedto.point.bottomright.up").font(.headline)
                Spacer()
                Text("\(inspected.phase.rawValue)  ·  \(number(time, digits: 2)) s").monospacedDigit()
            }
            PhysicsFlightCanvas(parameters: effectiveParameters, result: result, referenceParameters: comparison?.parameters,
                                reference: comparison?.result, time: time, prediction: showPrediction, swing: swingEnabled ? swing : nil)
                .frame(height: 215)
            HStack(alignment: .top, spacing: 24) {
                PhysicsBoardCanvas(parameters: effectiveParameters, result: result, reference: comparison?.result, time: time, prediction: showPrediction)
                    .frame(width: 220, height: 240)
                VStack(alignment: .leading, spacing: 12) {
                    Text("Inspect the moving bag").font(.headline)
                    Text("x = \(number(inspected.position.x, digits: 2)) m forward\ny = \(number(inspected.position.y, digits: 2)) m right\nz = \(number(inspected.position.z, digits: 2)) m high")
                        .monospacedDigit().lineSpacing(5)
                    Text("Speed  \(number(inspected.velocity.length, digits: 2)) m/s\nKinetic energy  \(number(0.5*parameters.mass*pow(inspected.velocity.length, 2), digits: 2)) J")
                        .monospacedDigit().lineSpacing(5)
                    if inspected.phase == .swing {
                        Text("Bag held: acceleration comes from the prescribed joint motion; gravity contributes to grip force.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    if inspected.phase == .flight {
                        let acceleration = model.acceleration(inspected.velocity)
                        Text("Acceleration (x, y, z)\n(\(number(acceleration.x, digits: 2)), \(number(acceleration.y, digits: 2)), \(number(acceleration.z, digits: 2))) m/s²")
                            .font(.callout).monospacedDigit()
                    }
                    Text("Blue: current throw · orange dashed: saved comparison. Side view hides lateral motion; the board view shows left/right aim. Each x starts at its own release. Bag symbols mark a point, not a physical footprint.")
                        .font(.caption).foregroundStyle(.secondary)
                }.frame(maxWidth: .infinity, alignment: .leading)
            }
        }.padding(20).background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 16))
    }

    private var playback: some View {
        VStack(spacing: 10) {
            HStack {
                Button {
                    if practice && !reveal {
                        guard round.count < 4 else { return }
                        pendingThrow = true
                    }
                    time = startTime; playing = true
                } label: { Label(practice && !reveal ? "Throw bag \(min(round.count+1, 4))" : "Throw / replay", systemImage: "play.fill") }
                    .buttonStyle(.borderedProminent).disabled(playing || result.samples.isEmpty || (practice && round.count >= 4 && !reveal))
                Button(playing ? "Pause" : "Resume") { playing.toggle() }.disabled(result.samples.isEmpty || time >= result.duration || (!playing && time <= startTime))
                if swingEnabled {
                    Button("Inspect release") { playing = false; time = 0 }
                        .disabled(result.samples.isEmpty || (practice && !reveal))
                }
                Picker("Playback", selection: $playbackRate) {
                    Text("¼ speed").tag(0.25); Text("½ speed").tag(0.5); Text("Real time").tag(1.0)
                }.frame(width: 190)
                Spacer()
                if !practice {
                    Button("Save comparison") { comparison = .init(parameters: effectiveParameters, result: result, swing: swingEnabled ? swing : nil) }.disabled(result.samples.isEmpty)
                }
            }
            HStack {
                Text(swingEnabled ? "Time from release" : "Inspect time").font(.callout)
                Slider(value: $time, in: startTime...max(0.001, result.duration), onEditingChanged: { _ in playing = false })
                    .disabled(practice && !reveal).accessibilityLabel("Inspect simulation time in seconds")
                Text("\(number(time, digits: 2)) / \(number(result.duration, digits: 2)) s").monospacedDigit().frame(width: 135)
            }
        }
    }

    private var roundScoreText: String {
        let total = round.compactMap(\.result.score).reduce(0, +)
        let unresolved = round.filter { $0.result.score == nil }.count
        return unresolved == 0 ? "\(total) / 12 model points" : "\(total) known points · \(unresolved) unresolved"
    }

    private var practiceCard: some View {
        ResearchCard(title: "Four-bag practice · \(round.count)/4 thrown", symbol: "flag.checkered") {
            HStack {
                Text(roundScoreText).font(.title2.bold())
                Spacer()
                Button("New round") { playing = false; pendingThrow = false; round = []; reveal = false; time = startTime }
            }
            Text("Set the release and press Throw. The prediction stays hidden until the bag finishes. Each throw is independent; no bag-to-bag collisions or opponent cancellation scoring.")
                .font(.callout).foregroundStyle(.secondary)
            ForEach(Array(round.enumerated()), id: \.offset) { index, shot in
                HStack {
                    Text("\(index+1). \(shot.result.outcome)")
                    Spacer()
                    Text("\(number(shot.parameters.speed, digits: 2)) m/s · \(number(shot.parameters.elevation))° · aim \(number(shot.parameters.aim, digits: 1))°").monospacedDigit()
                }.font(.callout)
            }
            if reveal && round.count < 4 {
                Button("Set up next throw") { reveal = false; time = startTime }.disabled(playing)
            }
        }
    }

    private var resultsCard: some View {
        ResearchCard(title: "Predicted result", symbol: "scope") {
            FeedbackBadge(zone: FeedbackZone(score: result.score), text: result.outcome)
            Text("Green: hole capture · yellow: board rest · red: ground miss · gray: unresolved. Board-map zones show the point model’s geometry, not safe or ideal joint angles.").font(.caption).foregroundStyle(.secondary)
            HStack(alignment: .top, spacing: 28) {
                metric(result.outcome, value: result.score.map { "\($0) \($0 == 1 ? "point" : "points")" } ?? "Unresolved")
                metric("Apex above ground", value: "\(number(result.apex, digits: 2)) m")
                metric("Time to first contact / entry", value: "\(number(result.firstContact?.time, digits: 3)) s")
            }
            if let first = result.firstContact {
                let error = first.position-model.board.hole
                Text("First contact / hole entry relative to hole center: \(signed(error.x)) m forward, \(signed(error.y)) m right. Negative = short / left. These are horizontal offsets, not distance along the deck.")
                    .font(.callout).monospacedDigit()
            }
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 220))], alignment: .leading) {
                ForEach(result.events) { event in
                    Button("\(event.label) · \(number(event.sample.time, digits: 2)) s") { playing = false; time = event.sample.time }
                        .buttonStyle(.link).font(.caption)
                }
            }
            Text("Scores use a center-point hole-capture rule. Edge clips, overhang, spin, bag folding and rolling are not resolved; actual bag outcomes may differ substantially.")
                .font(.caption).foregroundStyle(.secondary)
        }
    }

    private func metric(_ title: String, value: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.caption).foregroundStyle(.secondary)
            Text(value).font(.title3.weight(.semibold)).monospacedDigit()
        }.frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder private var experimentCard: some View {
        if swingEnabled, !experiments.isEmpty {
            ResearchCard(title: "What changes the outcome?", symbol: "arrow.triangle.branch") {
                Text("Each row changes one input from this swing and recomputes mechanics and flight. These are deterministic model comparisons, not probabilities or measured athlete effects.").font(.caption).foregroundStyle(.secondary)
                ForEach(experiments) { experiment in
                    HStack(alignment: .top, spacing: 16) {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(experiment.id).font(.callout.weight(.semibold))
                            Text(experiment.explanation).font(.caption).foregroundStyle(.secondary)
                        }.frame(maxWidth: .infinity, alignment: .leading)
                        if let p = experiment.release {
                            Text("\(number(p.speed, digits: 2)) m/s · \(number(p.elevation, digits: 1))°\nh = \(number(p.height, digits: 2)) m").font(.caption).monospacedDigit()
                        }
                        FeedbackBadge(zone: FeedbackZone(score: experiment.result.score), text: experiment.result.outcome)
                    }.padding(.vertical, 5)
                }
                Text("Color describes the combined terminal result. It does not assign a universal good/bad zone to arm length, release angle, torque or body size.").font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    private var controls: some View {
        ResearchCard(title: "Board, bag & environment", symbol: "slider.horizontal.3") {
            if !swingEnabled {
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 20) {
                control("Release height", value: $parameters.height, range: 0.3...2, unit: "m", digits: 2,
                        help: "Higher release gives the bag more time before reaching the same landing height.")
                control("Release position · positive right", value: $parameters.lateral, range: -1...1, unit: "m", digits: 2,
                        help: "Moves the starting point sideways without changing initial aim.")
                control("Release to board front", value: $parameters.distance, range: 3...10, unit: "m", digits: 2,
                        help: "Horizontal distance from the release point; not the official front-to-front court spacing.")
            }
            }
            control("Board incline", value: $parameters.boardAngle, range: 0...25, unit: "°", digits: 1, help: "Deck length stays fixed; changing incline changes the back height, normal impact velocity and downhill gravity component. 11° is the nominal example.")
            control("Bag mass", value: $parameters.mass, range: 0.3...0.6, unit: "kg", digits: 3,
                    help: "Mass sets weight and the force needed to hold the bag. It changes free-flight acceleration only when drag is active.")
            DisclosureGroup("Wind, drag, friction & bounce") {
                VStack(alignment: .leading, spacing: 18) {
                    Toggle("Include aerodynamic drag and wind", isOn: $parameters.airEnabled)
                    Text("Air density ρ = 1.225 kg/m³. Drag area, friction and bounce are illustrative inputs, not measured properties of your bag.")
                        .font(.caption).foregroundStyle(.secondary)
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 20) {
                        control("Effective drag area · CᴅA", value: $parameters.dragArea, range: 0...0.035, unit: "m²", digits: 3,
                                help: "Coefficient × exposed area; larger values increase force relative to the air.").disabled(!parameters.airEnabled)
                        control("Wind · positive tailwind", value: $parameters.windForward, range: -6...6, unit: "m/s", digits: 1,
                                help: "Negative means headwind, toward the thrower.").disabled(!parameters.airEnabled)
                        control("Wind · positive to right", value: $parameters.windRight, range: -6...6, unit: "m/s", digits: 1,
                                help: "Steady crosswind acts through air-relative velocity.").disabled(!parameters.airEnabled)
                        control("Board friction · μ", value: $parameters.friction, range: 0...0.8, unit: "", digits: 2,
                                help: "Resists sliding and tangential motion at impact. Same μ used for the static hold threshold.")
                        control("Normal restitution · e", value: $parameters.restitution, range: 0...0.6, unit: "", digits: 2,
                                help: "0 removes normal rebound; larger values preserve more normal impact speed.")
                    }
                }.padding(.top, 12)
            }.padding(.top, 12)
        }.disabled(playing || pendingThrow)
    }

    private func control(_ title: String, value: Binding<Double>, range: ClosedRange<Double>, unit: String, digits: Int, help: String) -> some View {
        let bounded = Binding<Double>(get: { value.wrappedValue }, set: { candidate in
            guard candidate.isFinite else { return }
            value.wrappedValue = min(range.upperBound, max(range.lowerBound, candidate))
        })
        return VStack(alignment: .leading, spacing: 5) {
            HStack {
                Text(title).font(.callout.weight(.medium))
                Spacer(minLength: 6)
                TextField(title, value: bounded, format: .number.precision(.fractionLength(digits)))
                    .textFieldStyle(.roundedBorder).frame(width: 70).monospacedDigit()
                    .onSubmit { value.wrappedValue = min(range.upperBound, max(range.lowerBound, value.wrappedValue.isFinite ? value.wrappedValue : range.lowerBound)) }
                Text(unit).font(.caption).frame(width: 30, alignment: .leading)
            }
            Slider(value: bounded, in: range).accessibilityLabel(title)
            if !help.isEmpty { Text(help).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true) }
        }
    }

    @ViewBuilder private var comparisonCard: some View {
        if let saved = comparison, !practice {
            ResearchCard(title: "Saved comparison", symbol: "arrow.left.arrow.right") {
                HStack {
                    Text("\(number(saved.parameters.speed, digits: 2)) m/s · \(number(saved.parameters.elevation, digits: 1))° elevation · \(number(saved.parameters.aim, digits: 1))° aim · \(saved.result.outcome)").font(.callout)
                    Spacer()
                    Button("Restore") { swingEnabled = saved.swing != nil; if let motion = saved.swing { swing = motion }; parameters = saved.parameters }
                    Button("Clear") { comparison = nil }
                }
                if let a = saved.result.firstContact, let b = result.firstContact {
                    let savedHole = CornholePhysics(parameters: saved.parameters).board.hole
                    Text("Change in first-contact offset from hole: Δforward \(signed((b.position.x-model.board.hole.x)-(a.position.x-savedHole.x))) m, Δright \(signed(b.position.y-a.position.y)) m; Δt \(signed(b.time-a.time)) s. Apex change: \(signed(result.apex-saved.result.apex)) m.")
                        .font(.callout).monospacedDigit()
                }
                Text("Each trajectory’s x coordinate starts at its own release. Saved boards show their corresponding distances. Offset changes above compare contact relative to each hole; the board close-up uses the current board’s coordinates.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    private var equations: some View {
        DisclosureGroup("Show the mathematics, numerical method & assumptions", isExpanded: $showEquations) {
            VStack(alignment: .leading, spacing: 14) {
                Text("Coordinates: x forward, y right as seen by the thrower, z upward; origin on the ground below the release along x, with lateral start y₀. All internal calculations use meters, seconds, kilograms and radians.")
                formula("v₀ = (v cos θ cos φ, v cos θ sin φ, v sin θ)\nr₀ = (0, y₀, h)\nv₀ = (\(number(effectiveParameters.velocity.x, digits: 3)), \(number(effectiveParameters.velocity.y, digits: 3)), \(number(effectiveParameters.velocity.z, digits: 3))) m/s")
                formula("Vacuum: r(t) = r₀ + v₀t + ½(0, 0, −g)t²\ng = 9.81 m/s²;  Eₖ,₀ = ½mv² = \(number(0.5*parameters.mass*effectiveParameters.speed*effectiveParameters.speed, digits: 3)) J")
                formula("With air: u = v − w\nFᴅ = −½ρ(CᴅA)|u|u\ndr/dt = v;  dv/dt = (0,0,−g) + Fᴅ/m\n½ρ(CᴅA)/m = \(number(0.5*CornholePhysics.density*parameters.dragArea/parameters.mass, digits: 5)) m⁻¹\n\(parameters.airEnabled ? "Drag is active." : "Drag is OFF; wind has no effect.")")
                let v = effectiveParameters.velocity
                let vacuumTime = (v.z+sqrt(v.z*v.z+2*CornholePhysics.gravity*effectiveParameters.height))/CornholePhysics.gravity
                Text("Independent vacuum check, ignoring the board: time to ground = [v₀z + √(v₀z² + 2gh)] / g = \(number(vacuumTime, digits: 3)) s; x = v₀x t = \(number(v.x*vacuumTime, digits: 3)) m. This is not the board-contact time and does not apply to drag-on flight.")
                formula("Board: n = (−sin α, 0, cos α); α = \(number(parameters.boardAngle, digits: 1))°\nvₙ = v · n;  vₜ = v − vₙn\nvₙ⁺ = −e vₙ⁻\nvₜ⁺ = max(0, 1 − μ(1+e)|vₙ⁻|/|vₜ⁻|) vₜ⁻\nSliding: a = gₜ − μg cos α · v/|v|\nStatic hold when |gₜ| ≤ μg cos α")
                Text("Method: fourth-order Runge–Kutta for flight at 1/480 s. Downward board-plane and ground crossings are located by bisection. Contact applies a restitution impulse and capped Coulomb friction impulse. Rebounds below 0.18 m/s settle onto the board. Sliding uses a gravity step followed by a friction velocity projection; segment intersections resolve hole entry and edge exit. A 10 s limit returns unresolved rather than a made-up score.")
                Text("Geometry: 1.2192 × 0.6096 m deck (48 × 24 in), 0.07112 m front height, \(number(parameters.boardAngle, digits: 1))° incline, 0.1524 m hole diameter, center 0.9906 m along the deck from the front. A center point entering the hole is captured immediately, regardless of speed. A stationary center on the deck scores 1; ground contact scores 0. No finite bag shape, rim collision, folding, spin/lift, rolling, board flex, other bags or wind force during board contact. These approximations are especially unreliable at the hole and edges.")
                Text("Use the simulation to explain mechanisms and compare hypothetical scenarios. Neither the presets nor contact parameters are validated prescriptions for a player. The displayed digits help compare computations; they do not represent experimental accuracy.")
                HStack {
                    Link("OpenStax · drag", destination: URL(string: "https://openstax.org/books/university-physics-volume-1/pages/6-4-drag-force-and-terminal-speed")!)
                    Link("OpenStax · friction", destination: URL(string: "https://openstax.org/books/university-physics-volume-1/pages/6-2-friction")!)
                    Link("ACL · equipment geometry", destination: URL(string: "https://www.iplaycornhole.com/about/acl-information/equipment-bags-boards")!)
                }
            }.font(.callout).textSelection(.enabled).padding(.vertical, 12)
        }
    }
    private func formula(_ text: String) -> some View {
        Text(text).font(.system(.callout, design: .monospaced)).fixedSize(horizontal: false, vertical: true)
            .padding(12).frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.secondary.opacity(0.07), in: RoundedRectangle(cornerRadius: 8))
    }
    private func signed(_ value: Double) -> String { String(format: "%+.3f", value) }
}
