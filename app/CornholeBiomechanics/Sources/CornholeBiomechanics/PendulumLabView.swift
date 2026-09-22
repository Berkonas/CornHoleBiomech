import Charts
import SwiftUI

struct PendulumLabView: View {
    @State private var kind = PendulumKind.singleCompound
    @State private var angle = -35.0
    @State private var bend = 30.0
    @State private var length = 0.65
    @State private var bag = 0.45
    @State private var time = 0.0
    @State private var showEquations = false

    init(initialKind: PendulumKind = .singleCompound, showEquations: Bool = false) {
        _kind = State(initialValue: initialKind)
        _showEquations = State(initialValue: showEquations)
    }

    private var model: PendulumMechanics {
        var p = PendulumParameters()
        p.l1 = length * 0.30/0.65; p.l2 = length * 0.35/0.65; p.bag = bag
        return PendulumMechanics(kind: kind, p: p)
    }

    var body: some View {
        let mechanics = model
        let samples = mechanics.simulate(angleDegrees: angle, bendDegrees: bend)
        let sample = samples.min { abs($0.time-time) < abs($1.time-time) }
        SectionContainer(title: "Arm Mechanics", subtitle: "Explore the equations. Test the throwing hypothesis with measured outcomes.") {
            Text("One link or two?").font(.title2.weight(.semibold))
            Text("A fixed elbow makes the arm approximately one rigid link—even when bent. Elbow motion adds a second degree of freedom. A simpler model alone does not prove that keeping the arm straight improves accuracy.")
                .foregroundStyle(.secondary)
            Picker("Pendulum model", selection: $kind) {
                ForEach(PendulumKind.allCases) { Text($0.rawValue).tag($0) }
            }.pickerStyle(.segmented)
            Text(kind.assumption).font(.headline)
            Label("Illustrative passive simulation · no participant measurements", systemImage: "info.circle")
                .font(.callout).foregroundStyle(.secondary)
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], alignment: .leading, spacing: 18) {
                control("Initial angle θ₁", value: $angle, range: -80...80, unit: "°")
                control("Initial bend θ₂ − θ₁", value: $bend, range: -90...90, unit: "°").disabled(!kind.isDouble)
                control("Total link length", value: $length, range: 0.4...1, unit: "m", digits: 2)
                control("Tip bag mass", value: $bag, range: 0...0.6, unit: "kg", digits: 2)
            }.padding(.vertical, 8)
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: 24) {
                    diagram(mechanics, sample: sample).frame(width: 290)
                    trajectory(samples).frame(minWidth: 320)
                }
                VStack(spacing: 20) { diagram(mechanics, sample: sample); trajectory(samples) }
            }
            HStack {
                Text("Inspect motion").font(.callout)
                Slider(value: $time, in: 0...4).accessibilityLabel("Simulation time in seconds")
                Text("\(time.formatted(.number.precision(.fractionLength(2)))) s").monospacedDigit().frame(width: 64)
                Button("Reset") { time = 0; angle = -35; bend = 30; length = 0.65; bag = 0.45 }
            }
            HStack(spacing: 24) {
                if let period = mechanics.smallAnglePeriod {
                    VStack(alignment: .leading) {
                        Text("Small-angle period").font(.caption).foregroundStyle(.secondary)
                        Text("\(number(period, digits: 3)) s").font(.title3.monospacedDigit())
                        Text("Linearized estimate; the simulation uses sin θ.").font(.caption).foregroundStyle(.secondary)
                    }
                }
                if let first = samples.first {
                    let drift = samples.map { abs($0.energy-first.energy) }.max() ?? 0
                    VStack(alignment: .leading) {
                        Text("Maximum sampled energy drift").font(.caption).foregroundStyle(.secondary)
                        Text(String(format: "%.2e J", drift)).font(.title3.monospacedDigit())
                        Text("Numerical check for this undriven, frictionless model.").font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
            Text("Example parameters: m₁ = 2.00 kg, m₂ = 1.00 kg, g = 9.81 m/s²; l₁:l₂ = 30:35. Single models combine m₁ + m₂. Mass placement changes between models. All start at rest; shoulder fixed; no joint limits, muscle torque, friction, air resistance, or bag release. These are mechanical examples, not anatomical parameter estimates or predictions of a throw.")
                .font(.caption).foregroundStyle(.secondary)
            Divider()
            equations(mechanics)
            ResearchCard(title: "Test the elbow-motion hypothesis", symbol: "chart.dots.scatter") {
                Text("In Results, compare mean elbow flexion and forward-swing excursion with observed target error or score. Low excursion means the elbow changes less within a throw; repeatability requires several comparable throws. A fixed bent elbow can have low excursion too.")
                Text("Use repeated side-view recordings, review shoulder–elbow–wrist landmarks and release, and compare throws within the same athlete and setup. Shoulder translation, wrist motion, release timing and out-of-plane movement can all matter. Do not prescribe locking the elbow from these models.").font(.callout).foregroundStyle(.secondary)
            }
        }
    }

    private func control(_ title: String, value: Binding<Double>, range: ClosedRange<Double>, unit: String, digits: Int = 0) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack { Text(title); Spacer(); Text("\(number(value.wrappedValue, digits: digits)) \(unit)").monospacedDigit() }
            Slider(value: value, in: range).accessibilityLabel(title)
        }
    }

    private func diagram(_ m: PendulumMechanics, sample: PendulumSample?) -> some View {
        VStack(alignment: .leading) {
            Text("Link geometry").font(.headline)
            Canvas { context, size in
                let s = sample?.state ?? PendulumState(q1: 0, q2: 0, w1: 0, w2: 0)
                let scale = min(size.width, size.height)*0.43/(m.p.l1+m.p.l2)
                let pivot = CGPoint(x: size.width/2, y: size.height/2)
                func endpoint(_ start: CGPoint, _ l: Double, _ q: Double) -> CGPoint {
                    CGPoint(x: start.x+scale*l*sin(q), y: start.y+scale*l*cos(q))
                }
                let joint = endpoint(pivot, m.p.l1, s.q1)
                let tip = m.kind.isDouble ? endpoint(joint, m.p.l2, s.q2) : endpoint(pivot, m.p.l1+m.p.l2, s.q1)
                var vertical = Path(); vertical.move(to: pivot); vertical.addLine(to: CGPoint(x: pivot.x, y: size.height-8))
                context.stroke(vertical, with: .color(.secondary.opacity(0.5)), style: StrokeStyle(dash: [4,4]))
                var path = Path(); path.move(to: pivot)
                if m.kind.isDouble { path.addLine(to: joint) }
                path.addLine(to: tip)
                context.stroke(path, with: .color(athleteInk), style: StrokeStyle(lineWidth: m.kind.isCompound ? 10 : 3, lineCap: .round, lineJoin: .round))
                for (point, label) in [(pivot, "Pivot"), (tip, "Tip")] + (m.kind.isDouble ? [(joint, "Elbow")] : []) {
                    context.fill(Path(ellipseIn: CGRect(x: point.x-5, y: point.y-5, width: 10, height: 10)), with: .color(.primary))
                    context.draw(Text(label).font(.caption), at: CGPoint(x: point.x+27, y: point.y-12))
                }
            }.frame(height: 240)
            Text("Dashed line: downward vertical. Rod thickness indicates distributed mass; links are shown to scale.").font(.caption).foregroundStyle(.secondary)
        }.accessibilityElement(children: .ignore).accessibilityLabel("\(kind.rawValue) link geometry at \(number(time, digits: 2)) seconds. \(kind.assumption)")
    }

    private func trajectory(_ samples: [PendulumSample]) -> some View {
        VStack(alignment: .leading) {
            Text("Absolute link angles").font(.headline)
            Chart {
                ForEach(samples) { p in
                    LineMark(x: .value("Time", p.time), y: .value("Angle", p.state.q1*180 / .pi), series: .value("Link", "θ₁"))
                        .foregroundStyle(by: .value("Link", "θ₁"))
                    if kind.isDouble {
                        LineMark(x: .value("Time", p.time), y: .value("Angle", p.state.q2*180 / .pi), series: .value("Link", "θ₂"))
                            .foregroundStyle(by: .value("Link", "θ₂"))
                    }
                }
                RuleMark(x: .value("Inspection time", time)).foregroundStyle(.secondary).lineStyle(StrokeStyle(dash: [4,4]))
            }.chartForegroundStyleScale(domain: kind.isDouble ? ["θ₁", "θ₂"] : ["θ₁"],
                                         range: kind.isDouble ? [athleteInk, Color.orange] : [athleteInk])
                .chartXAxisLabel("Time (s)").chartYAxisLabel("Angle from downward vertical (°)")
                .chartXScale(domain: 0...4).frame(height: 240)
            Text(kind.isDouble ? "θ₂ is measured from vertical, not from the upper arm. The simulation allows full rotation and is not constrained by human joint anatomy." : "θ₁ follows the single link from downward vertical. The nonlinear motion starts at rest.")
                .font(.caption).foregroundStyle(.secondary)
        }
    }

    private func equations(_ model: PendulumMechanics) -> some View {
        let k = model.coefficients
        return DisclosureGroup("Corrected equations & assumptions", isExpanded: $showEquations) {
            VStack(alignment: .leading, spacing: 12) {
                Text("Convention: x forward, y up; θ measured from downward vertical. Angles in radians in every calculation. L = T − V; d/dt(∂L/∂θ̇ᵢ) − ∂L/∂θᵢ = Qᵢ.")
                if !kind.isDouble {
                    formula("I θ̈ + G sin θ = τₛ")
                    if kind == .singleSimple {
                        formula("I = (m + mᵦ)l²;  G = (m + mᵦ)gl;  θ̈ = −(g/l) sin θ  when τₛ = 0")
                    } else {
                        formula("I = (m/3 + mᵦ)l²;  G = (m/2 + mᵦ)gl")
                        Text("General rigid body: I = ICOM + md², G = mgd. A uniform rod has ICOM = ml²/12 and pivot inertia ml²/3. The tip bag adds mᵦl² to I and mᵦgl to G.")
                    }
                    formula("ω₀² = G/I;  θ(t) ≈ θ₀ cos(ω₀t) + (θ̇₀/ω₀) sin(ω₀t)")
                    Text("Small-angle error is gradual: (θ − sin θ)/sin θ ≈ 3.24% at 25°. There is no universal failure angle. The app integrates the nonlinear equation.")
                } else {
                    formula("Δ = θ₁ − θ₂\nA θ̈₁ + C cos Δ θ̈₂ + C sin Δ θ̇₂² + G₁ sin θ₁ = τₛ − τₑ\nB θ̈₂ + C cos Δ θ̈₁ − C sin Δ θ̇₁² + G₂ sin θ₂ = τₑ")
                    if kind == .doubleSimple {
                        formula("A = (m₁ + m₂ + mᵦ)l₁²;  B = (m₂ + mᵦ)l₂²\nC = (m₂ + mᵦ)l₁l₂\nG₁ = (m₁ + m₂ + mᵦ)gl₁;  G₂ = (m₂ + mᵦ)gl₂")
                    } else {
                        formula("A = (m₁/3 + m₂ + mᵦ)l₁²;  B = (m₂/3 + mᵦ)l₂²\nC = (m₂/2 + mᵦ)l₁l₂\nG₁ = (m₁/2 + m₂ + mᵦ)gl₁;  G₂ = (m₂/2 + mᵦ)gl₂")
                    }
                    Text("τₛ is shoulder torque, τₑ is elbow torque acting positively on θ₂ − θ₁. Both are zero in this passive demonstration. The two equations are solved together through a symmetric mass matrix; its determinant is AB − C² cos² Δ.")
                    formula("T = ½Aθ̇₁² + ½Bθ̇₂² + C cos Δ θ̇₁θ̇₂\nV = −G₁ cos θ₁ − G₂ cos θ₂")
                }
                Text("Current coefficients: A / I = \(number(k.a, digits: 4)) kg·m²; B = \(number(k.b, digits: 4)) kg·m²; C = \(number(k.c, digits: 4)) kg·m²; G₁ / G = \(number(k.g1, digits: 4)) N·m; G₂ = \(number(k.g2, digits: 4)) N·m.")
                    .font(.caption).monospacedDigit()
                Text("Corrections to the supplied notes: use consistent upward y; y₂ = −l₁ cos θ₁ − (l₂/2) cos θ₂ for the second rod COM; velocity terms in T are squared; the second equation uses Bθ̈₂ and G₂ sin θ₂. I = mr² only describes a point mass; the general expression includes COM inertia. Double-simple coupling uses the distal mass m₂.")
                    .font(.callout)
                HStack {
                    Link("OpenStax · pendulums", destination: URL(string: "https://openstax.org/books/university-physics-volume-1/pages/15-4-pendulums")!)
                    Link("MIT · Lagrange & coupled dynamics", destination: URL(string: "https://underactuated.mit.edu/multibody.html")!)
                }.font(.callout)
                Text("MIT uses a relative second joint angle. These equations are independently derived in the absolute-angle convention used in your notes.").font(.caption).foregroundStyle(.secondary)
            }.textSelection(.enabled).padding(.vertical, 12)
        }
    }
    private func formula(_ value: String) -> some View {
        Text(value).font(.system(.body, design: .monospaced)).fixedSize(horizontal: false, vertical: true)
            .padding(12).frame(maxWidth: .infinity, alignment: .leading)
            .background(.quaternary, in: RoundedRectangle(cornerRadius: 8))
    }
}
