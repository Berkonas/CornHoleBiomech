import SwiftUI

let launchLabSymbol = "point.topleft.down.to.point.bottomright.curvepath"

/// Release-physics teaching screen (sidebar → Launch Lab): the selected athlete's measured throws feed "Start from".
struct LaunchLabView: View {
    @EnvironmentObject private var store: ProjectStore
    @State private var measured: [MeasuredRelease] = []

    var body: some View {
        LaunchLabContent(measured: measured, athleteSelected: store.selectedAthleteID != nil)
            .task(id: store.selectedAthleteID) { measured = MeasuredRelease.load(athleteID: store.selectedAthleteID, store: store) }
    }
}

/// The Launch Lab page, independent of the library so it can be rendered on its own.
struct LaunchLabContent: View {
    let measured: [MeasuredRelease]
    let athleteSelected: Bool
    var animateOnAppear = true

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var params: LaunchParameters
    @State private var ghosts: [LaunchParameters] = []
    @State private var run: LaunchRun?
    @State private var lastThrown: LaunchParameters?
    @State private var slowMotion = false
    @State private var source: (label: String, params: LaunchParameters)?

    init(measured: [MeasuredRelease], athleteSelected: Bool, initial: LaunchParameters = LaunchLabContent.defaultParameters,
         ghosts: [LaunchParameters] = [], animateOnAppear: Bool = true) {
        self.measured = measured
        self.athleteSelected = athleteSelected
        self.animateOnAppear = animateOnAppear
        _params = State(initialValue: initial)
        _ghosts = State(initialValue: ghosts)
    }

    /// 35°, 0.80 m, regulation 27 ft pitch minus reach (7.7 m, as python `ZoneSettings`), speed solved for the hole.
    static var defaultParameters: LaunchParameters {
        var p = LaunchParameters(speed: 8, angleDegrees: 35, releaseHeight: 0.8, distanceToBoard: 7.7)
        if let v = LaunchModel(p).speedToHitHole() { p.speed = (v * 100).rounded() / 100 }
        return p
    }

    static let speedRange = 1.0...15.0, angleRange = -10.0...80.0, heightRange = 0.2...2.2, distanceRange = 1.0...12.0

    var body: some View {
        Page {
            VStack(alignment: .leading, spacing: Space.xs) {
                Text("Launch Lab").font(.largeTitle.weight(.bold))
                Text("Change how the bag leaves the hand and see where a drag-free bag first lands — and how forgiving that release is.")
                    .font(.title3).foregroundStyle(.secondary)
            }
            HStack(alignment: .top, spacing: Space.xl) {
                sceneCard
                controlsCard.frame(width: 300)
            }
            .fixedSize(horizontal: false, vertical: true)   // both cards take the taller card's height
            Card("Success map", symbol: "square.grid.3x3.fill",
                 subtitle: "Predicted first contact for every speed and angle, at h = \(number(params.releaseHeight, digits: 2)) m and \(number(params.distanceToBoard, digits: 2)) m to the board. Click or drag to try a release.") {
                SuccessMap(params: $params, throws: measured, onPick: throwNow)
            }
            sensitivityCard
            Card {
                DisclosureGroup("Model and assumptions") { assumptions.padding(.top, Space.s) }
                    .font(.headline)
            }
        }
        .onAppear { if animateOnAppear { throwNow() } }
        .onChange(of: slowMotion) { throwNow() }
    }

    // MARK: Throw

    private func throwNow() {
        if let last = lastThrown, last != params {
            ghosts = Array(([last] + ghosts.filter { $0 != last }).prefix(3))
        }
        ghosts.removeAll { $0 == params }
        lastThrown = params
        run = reduceMotion ? nil : LaunchRun(params: params, start: .now)
    }

    // MARK: Scene

    private var sceneCard: some View {
        Card {
            HStack(alignment: .firstTextBaseline) {
                CardHeader(title: "Side view", symbol: launchLabSymbol, subtitle: "To scale · 1 m grid")
                Spacer()
                Toggle("Slow motion", isOn: $slowMotion).toggleStyle(.checkbox)
                    .help("Play the throw at quarter speed")
                Button("Throw", systemImage: "play.fill", action: throwNow)
                    .buttonStyle(.borderedProminent)
                    .keyboardShortcut(.defaultAction)
                    .help("Replay the throw (Return)")
            }
            LaunchScene(params: params, ghosts: ghosts, run: run, rate: slowMotion ? 0.25 : 1)
                .aspectRatio(2.5, contentMode: .fit)
                .frame(minHeight: 260)
            sceneLegend
            Divider()
            readouts
        }
    }

    private var sceneLegend: some View {
        HStack(spacing: Space.l) {
            ForEach(LandingZone.allCases.filter { $0 != .off }, id: \.self) { zone in
                HStack(spacing: Space.xs) {
                    Capsule().fill(zone.color).frame(width: 16, height: 3)
                    Text(zone == .hole ? "Hole window (lands ≤ 45 cm short of centre)" : "On the board (or ≤ 30 cm short)")
                }
            }
            HStack(spacing: Space.xs) {
                Capsule().fill(Color.primary.opacity(0.4)).frame(width: 16, height: 1.5)
                Text(ghosts.isEmpty ? "Model path" : "Model path · faint arcs: previous throws")
            }
        }
        .font(.caption).foregroundStyle(.secondary)
    }

    // MARK: Controls

    private var controlsCard: some View {
        Card("Release", symbol: "slider.horizontal.3") {
            VStack(alignment: .leading, spacing: Space.m) {
                ParameterRow(title: "Speed", unit: "m/s", value: $params.speed, range: Self.speedRange, step: 0.05, digits: 2, commit: throwNow)
                ParameterRow(title: "Angle", unit: "°", value: $params.angleDegrees, range: Self.angleRange, step: 0.5, digits: 1, commit: throwNow)
                ParameterRow(title: "Height", unit: "m", value: $params.releaseHeight, range: Self.heightRange, step: 0.01, digits: 2, commit: throwNow)
                ParameterRow(title: "Distance to board", unit: "m", value: $params.distanceToBoard, range: Self.distanceRange, step: 0.05, digits: 2, commit: throwNow)
            }
            Spacer(minLength: Space.s)
            Divider().padding(.vertical, Space.xs)
            Button("Solve speed for the hole", systemImage: "scope", action: solve)
                .disabled(holeSpeed == nil)
                .help(holeSpeed == nil ? "No release speed reaches the hole at this angle and height." : "Set the speed that lands on the hole centre")
            startFromMenu
        }
    }

    @ViewBuilder private var startFromMenu: some View {
        VStack(alignment: .leading, spacing: Space.xs) {
            Menu {
                ForEach(measured) { m in
                    Button { apply(m) } label: {
                        Text("\(m.label) — \(number(m.speed, digits: 2)) m/s · \(number(m.angle, digits: 0))° · \(number(m.height, digits: 2)) m\(scoreSuffix(m.score))")
                    }
                }
            } label: {
                Label("Start from a measured throw", systemImage: "figure.bowling")
            }
            .disabled(measured.isEmpty)
            Group {
                if !athleteSelected {
                    Text("Select an athlete in the sidebar to start from their measured throws.")
                } else if measured.isEmpty {
                    Text("This athlete has no analysed throws with release speed, angle and height in metres yet.")
                } else if let source, source.params == params {
                    Text("From \(source.label)").lineLimit(1)
                }
            }
            .font(.caption).foregroundStyle(.secondary)
        }
    }

    private func scoreSuffix(_ score: ScoreCategory?) -> String {
        switch score { case .throughHole: " · hole"; case .onBoard: " · board"; case .offBoard: " · miss"; case nil: "" }
    }

    private func apply(_ m: MeasuredRelease) {
        func clamp(_ v: Double, _ r: ClosedRange<Double>) -> Double { min(max(v, r.lowerBound), r.upperBound) }
        params.speed = clamp(m.speed, Self.speedRange)
        params.angleDegrees = clamp(m.angle, Self.angleRange)
        params.releaseHeight = clamp(m.height, Self.heightRange)
        if let d = m.distance { params.distanceToBoard = clamp(d, Self.distanceRange) }
        source = (m.label, params)
        throwNow()
    }

    private var holeSpeed: Double? { LaunchModel(params).speedToHitHole() }

    private func solve() {
        guard let v = holeSpeed else { return }
        params.speed = (v * 100).rounded() / 100
        throwNow()
    }

    // MARK: Readouts

    /// Outcome, distance from the hole, flight time, apex and the speed that would hit the hole.
    private var readouts: some View {
        let model = LaunchModel(params), hit = model.landing(), zone = model.zone()
        let apex = params.vy > 0 ? params.releaseHeight + params.vy * params.vy / (2 * LaunchModel.gravity) : params.releaseHeight
        return HStack(alignment: .top, spacing: Space.l) {
            VStack(alignment: .leading, spacing: 2) {
                Text("Outcome").font(.caption).foregroundStyle(.secondary)
                Label(zone.label, systemImage: zone.symbol).font(.title3.weight(.semibold)).foregroundStyle(zone.color)
                Text(hit.kind.rawValue).font(.caption2).foregroundStyle(.secondary).lineLimit(2)
            }
            .frame(minWidth: 150, maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .combine)
            readout("From hole", hit.distanceToHole.map { signedCentimetres($0) } ?? "—", hit.distanceToHole == nil ? "" : "cm",
                    note: hit.distanceToHole.map { abs($0) < 0.005 ? "on centre" : $0 < 0 ? "short of centre" : "past centre" } ?? "board landings only")
            readout("Flight time", number(hit.time, digits: 2), "s", note: "to first contact")
            readout("Apex", number(apex, digits: 2), "m", note: "above the floor")
            readout("Speed for the hole", holeSpeed.map { number($0, digits: 2) } ?? "—", holeSpeed == nil ? "" : "m/s",
                    note: holeSpeed.map { deltaNote($0 - params.speed) } ?? "not reachable")
        }
    }

    private func signedCentimetres(_ metres: Double) -> String {
        let cm = metres * 100
        return (cm > 0.5 ? "+" : "") + number(cm, digits: 0)
    }

    private func deltaNote(_ delta: Double) -> String {
        abs(delta) < 0.005 ? "at this speed" : "\(delta > 0 ? "+" : "−")\(number(abs(delta), digits: 2)) from now"
    }

    private func readout(_ title: String, _ value: String, _ unit: String, note: String? = nil) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title).font(.caption).foregroundStyle(.secondary)
            HStack(alignment: .firstTextBaseline, spacing: 3) {
                Text(value).font(.title3.weight(.semibold)).monospacedDigit()
                if !unit.isEmpty { Text(unit).font(.caption).foregroundStyle(.secondary) }
            }
            if let note { Text(note).font(.caption2).foregroundStyle(.secondary).monospacedDigit() }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
    }

    // MARK: Sensitivity

    private var sensitivityCard: some View {
        let s = LaunchModel(params).sensitivity()
        let items: [(String, String, Double?)] = [
            ("Speed", "per 0.1 m/s", s.perSpeed.map { $0 * 0.1 * 100 }),
            ("Angle", "per 1°", s.perAngle.map { $0 * 100 }),
            ("Height", "per 1 cm", s.perHeight.map { $0 * 0.01 * 100 }),
        ]
        let holeDiameter = 2 * params.board.holeRadius * 100
        let largest = items.compactMap { item in item.2.map { (item.0, item.1, $0) } }.max { abs($0.2) < abs($1.2) }
        return Card("Sensitivity", symbol: "plusminus",
                    subtitle: "How far first contact moves for a small change in each release value, holding the others (central differences).") {
            HStack(alignment: .top, spacing: Space.xl) {
                ForEach(items, id: \.0) { item in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(item.0).font(.headline)
                        HStack(alignment: .firstTextBaseline, spacing: 3) {
                            Text(item.2.map { number($0, digits: 1) } ?? "—").font(.title.weight(.semibold)).monospacedDigit()
                            if item.2 != nil { Text("cm").font(.callout).foregroundStyle(.secondary) }
                        }
                        Text(item.1).font(.caption).foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilityElement(children: .combine)
                }
            }
            Group {
                if let largest {
                    Text("Here, \(largest.1.replacingOccurrences(of: "per ", with: "")) of \(largest.0.lowercased()) moves first contact \(number(abs(largest.2), digits: 0)) cm — \(abs(largest.2) >= holeDiameter ? "more than" : "\(number(abs(largest.2) / holeDiameter * 100, digits: 0)) % of") the hole's \(number(holeDiameter, digits: 0)) cm diameter.")
                } else {
                    Text("Sensitivities are computed when the throw and both small changes land on the board.")
                }
            }
            .font(.callout).foregroundStyle(.secondary)
        }
    }

    // MARK: Model

    private var assumptions: some View {
        VStack(alignment: .leading, spacing: Space.m) {
            Text("The bag is a point mass launched from the release point; only gravity acts on it.")
            VStack(alignment: .leading, spacing: Space.xs) {
                Text("x = v cos θ · t")
                Text("y = h + v sin θ · t − ½ g t²")
                Text("g = 9.80665 m/s²")
            }
            .font(.system(.body, design: .serif).italic())
            .padding(Space.m)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.primary.opacity(0.04), in: RoundedRectangle(cornerRadius: 8))
            VStack(alignment: .leading, spacing: Space.xs) {
                bullet("First contact is where the path first meets the floor, the front face, or the sloped deck (regulation board: 48 in deck, 3 in front, 12 in back, 6 in hole centred 9 in from the back).")
                bullet("Hole window: first contact on the deck from 45 cm short of the hole centre to its far edge — bags landing a little short usually slide in. On the board: elsewhere on the deck, or up to 30 cm short of it. Both allowances are stated assumptions, the same as the Python zone report.")
                bullet("Ignored: air drag (under 1.5 % change in the arc for a 0.45 kg bag), spin, sideways aim, bounce and sliding after contact.")
                bullet("Measured throws are placed by their scaled release values; how well the model matches real outcomes is checked on the athlete summary.")
            }
        }
        .font(.callout)
        .foregroundStyle(.primary)
    }

    private func bullet(_ text: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: Space.s) {
            Text("•").foregroundStyle(.secondary)
            Text(text).fixedSize(horizontal: false, vertical: true)
        }
    }
}

/// Labelled slider with an editable value field. Values snap to `step`; release or Return throws.
private struct ParameterRow: View {
    let title: String
    let unit: String
    @Binding var value: Double
    let range: ClosedRange<Double>
    let step: Double
    let digits: Int
    let commit: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(alignment: .firstTextBaseline, spacing: Space.xs) {
                Text(title)
                Spacer()
                TextField(title, value: clamped, format: .number.precision(.fractionLength(digits)))
                    .labelsHidden()
                    .multilineTextAlignment(.trailing)
                    .monospacedDigit()
                    .frame(width: 64)
                    .onSubmit(commit)
                Text(unit).foregroundStyle(.secondary).frame(width: 26, alignment: .leading)
            }
            Slider(value: snapped, in: range) { editing in if !editing { commit() } }
                .controlSize(.small)
                .accessibilityLabel(title)
                .accessibilityValue("\(number(value, digits: digits)) \(unit)")
        }
    }

    private var snapped: Binding<Double> {
        Binding(get: { value }, set: { value = min(max(($0 / step).rounded() * step, range.lowerBound), range.upperBound) })
    }

    private var clamped: Binding<Double> {
        Binding(get: { value }, set: { value = min(max($0, range.lowerBound), range.upperBound) })
    }
}
