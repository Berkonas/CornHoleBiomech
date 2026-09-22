import Charts
import SwiftUI

/// Interactive drag-free launch model. Model output is never stored with athlete data.
struct LaunchExplorerView: View {
    @EnvironmentObject private var store: ProjectStore
    @State private var params = LaunchParameters(speed: 6.0, angleDegrees: 35, releaseHeight: 0.8, distanceToBoard: 7.7)
    @State private var athlete: AthleteRelease?

    private var model: LaunchModel { LaunchModel(params) }

    var body: some View {
        SectionContainer(title: "Launch Explorer", subtitle: "A physics model of how release angle, speed and height move the landing point. Model output, not measured athlete data.") {
            HStack(alignment: .top, spacing: 28) {
                controls.frame(width: 320)
                VStack(alignment: .leading, spacing: 14) {
                    chart
                    outcome
                }
            }
            sensitivityPanel
            DisclosureGroup("Model and assumptions") {
                Text("""
                A point mass leaves the hand at speed v and angle θ from height h: x = v·cosθ·t, y = h + v·sinθ·t − ½gt², g = 9.807 m/s². \
                First contact is where this path meets the floor, the front of the board, or the deck plane (regulation 48 in deck, 3 in front, \
                12 in back ≈ 10.8°, hole centre 9 in from the back). Air drag changes the arc by under 1.5 % for a 0.45 kg bag in our simulations \
                and is ignored, as are spin, lateral aim, bounce and sliding after contact. Sensitivities are central differences of the \
                first-contact position and are shown only while both perturbed throws still land on the board.
                """).font(.callout).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .onAppear {
            // Open on a throw that reaches the hole so the sensitivity table is populated.
            if let v = model.speedToHitHole() { params.speed = v }
            loadAthlete()
        }
        .onChange(of: store.selectedTrialID) { _, _ in loadAthlete() }
    }

    private var controls: some View {
        VStack(alignment: .leading, spacing: 14) {
            slider("Release angle", value: $params.angleDegrees, range: 5...70, step: 0.5, unit: "°", digits: 1)
            slider("Release speed", value: $params.speed, range: 2...12, step: 0.05, unit: "m/s", digits: 2)
            slider("Release height", value: $params.releaseHeight, range: 0.2...1.6, step: 0.01, unit: "m", digits: 2)
            slider("Release to board front", value: $params.distanceToBoard, range: 5...9, step: 0.05, unit: "m", digits: 2)
            Button("Find speed that reaches the hole") {
                if let v = model.speedToHitHole() { params.speed = v }
            }
            if let athlete {
                Button("Start from \(athlete.name)’s median release") {
                    if let a = athlete.angle { params.angleDegrees = a }
                    if let v = athlete.speed { params.speed = v }
                    if let h = athlete.height { params.releaseHeight = h }
                }
                Text("From \(athlete.throwCount) measured throws. Speed and height need a scaled recording (meter stick or reviewed flight).")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    private func slider(_ title: String, value: Binding<Double>, range: ClosedRange<Double>, step: Double, unit: String, digits: Int) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack { Text(title); Spacer(); Text("\(number(value.wrappedValue, digits: digits)) \(unit)").monospacedDigit() }
            Slider(value: value, in: range, step: step).accessibilityValue("\(number(value.wrappedValue, digits: digits)) \(unit)")
        }
    }

    private var chart: some View {
        let b = params.board
        let path = model.trajectory()
        let front = (x: params.distanceToBoard, y: b.frontHeight)
        let back = (x: front.x + b.length * cos(b.angle), y: front.y + b.length * sin(b.angle))
        let hole = (x: front.x + b.holeAlong * cos(b.angle), y: front.y + b.holeAlong * sin(b.angle))
        let apex = path.map(\.y).max() ?? params.releaseHeight
        let xMax = max(back.x, path.last?.x ?? 0) + 0.3
        let yMax = max(apex, back.y) + 0.3
        return Chart {
            ForEach(Array(path.enumerated()), id: \.offset) { _, p in
                LineMark(x: .value("Forward (m)", p.x), y: .value("Height (m)", p.y), series: .value("Part", "Flight"))
                    .foregroundStyle(scoredInk).lineStyle(StrokeStyle(lineWidth: 2))
            }
            LineMark(x: .value("Forward (m)", front.x), y: .value("Height (m)", front.y), series: .value("Part", "Board"))
                .foregroundStyle(Color.primary).lineStyle(StrokeStyle(lineWidth: 4))
            LineMark(x: .value("Forward (m)", back.x), y: .value("Height (m)", back.y), series: .value("Part", "Board"))
                .foregroundStyle(Color.primary).lineStyle(StrokeStyle(lineWidth: 4))
            PointMark(x: .value("Forward (m)", hole.x), y: .value("Height (m)", hole.y))
                .symbol { Circle().stroke(Color.primary, lineWidth: 2).frame(width: 10, height: 10) }
                .annotation(position: .top) { Text("hole").font(.caption2).foregroundStyle(.secondary) }
            PointMark(x: .value("Forward (m)", 0), y: .value("Height (m)", params.releaseHeight))
                .foregroundStyle(scoredInk)
                .annotation(position: .top) { Text("release").font(.caption2).foregroundStyle(.secondary) }
        }
        .chartXScale(domain: -0.2...xMax)
        .chartYScale(domain: 0...yMax)
        .chartXAxisLabel("Forward from release (m)")
        .chartYAxisLabel("Height above floor (m)")
        // Equal metres on both axes so launch angles look like what they are.
        .aspectRatio((xMax + 0.2) / yMax, contentMode: .fit)
        .frame(maxHeight: 300)
    }

    private var outcome: some View {
        let r = model.landing()
        let apex = model.trajectory().map(\.y).max() ?? params.releaseHeight
        return VStack(alignment: .leading, spacing: 4) {
            Text(r.kind.rawValue).font(.headline)
            if let d = r.distanceToHole {
                Text(abs(d) < params.board.holeRadius
                     ? "First contact over the hole (\(number(abs(d) * 100, digits: 0)) cm from centre)."
                     : "First contact \(number(abs(d) * 100, digits: 0)) cm \(d > 0 ? "past" : "short of") the hole centre, measured along the deck.")
            }
            Text("Flight time \(number(r.time, digits: 2)) s · peak height \(number(apex, digits: 2)) m").font(.callout).foregroundStyle(.secondary)
        }
    }

    private var sensitivityPanel: some View {
        let s = model.sensitivity()
        return VStack(alignment: .leading, spacing: 10) {
            Text("Which release variable moves the landing most?").font(.title2.weight(.semibold))
            if s.perSpeed == nil && s.perAngle == nil && s.perHeight == nil {
                Text("Sensitivities appear when the modelled throw lands on the board.").foregroundStyle(.secondary)
            } else {
                Grid(alignment: .leading, horizontalSpacing: 24, verticalSpacing: 6) {
                    GridRow {
                        Text("Change").fontWeight(.semibold); Text("Landing moves").fontWeight(.semibold)
                        if athlete != nil { Text("This athlete's usual spread (SD)").fontWeight(.semibold); Text("≈ landing spread").fontWeight(.semibold) }
                    }
                    row("+1° angle", s.perAngle.map { $0 * 1 }, spread: athlete?.angleSD, spreadUnit: "°", per: s.perAngle)
                    row("+0.1 m/s speed", s.perSpeed.map { $0 * 0.1 }, spread: athlete?.speedSD, spreadUnit: " m/s", per: s.perSpeed)
                    row("+5 cm height", s.perHeight.map { $0 * 0.05 }, spread: athlete?.heightSD, spreadUnit: " m", per: s.perHeight)
                }.font(.callout).monospacedDigit()
                Text(athlete == nil
                     ? "Select an analyzed throw with scaled release measurements to add the athlete's own spread."
                     : "Landing spread = model sensitivity × the athlete's measured SD, one variable at a time. It shows which inconsistency costs the most accuracy under this model; it is not a measured result.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    @ViewBuilder
    private func row(_ label: String, _ moves: Double?, spread: Double?, spreadUnit: String, per: Double?) -> some View {
        GridRow {
            Text(label)
            Text(moves.map { "\(number($0 * 100, digits: 0)) cm" } ?? "—")
            if athlete != nil {
                Text(spread.map { number($0, digits: spreadUnit == "°" ? 1 : 2) + spreadUnit } ?? "not measured")
                Text(spread.flatMap { sd in per.map { "± \(number(abs($0 * sd) * 100, digits: 0)) cm" } } ?? "—")
            }
        }
    }

    private func loadAthlete() {
        athlete = store.selectedTrial.flatMap { trial in
            store.analysisURL(for: trial).flatMap { AthleteRelease.load(insightsURL: $0.appendingPathComponent("insights.json"), name: store.project?.athletes.first { $0.id == trial.athleteID }?.displayName ?? "Athlete") }
        }
    }
}

/// Median and SD of measured release variables from the athlete performance summary.
struct AthleteRelease {
    var name: String
    var throwCount: Int
    var angle: Double?; var angleSD: Double?
    var speed: Double?; var speedSD: Double?
    var height: Double?; var heightSD: Double?

    static func load(insightsURL: URL, name: String) -> AthleteRelease? {
        guard let bytes = try? Data(contentsOf: insightsURL),
              let object = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any],
              let performance = object["performance"],
              let data = try? JSONSerialization.data(withJSONObject: performance),
              let summary = try? JSONDecoder.projectDecoder.decode(PerformanceSummary.self, from: data).summary else { return nil }
        let v = summary.variables
        let angle = v["bag_release_angle_deg"], speed = v["bag_release_speed_m_s"], height = v["bag_release_height_m"]
        guard angle != nil || speed != nil || height != nil else { return nil }
        return AthleteRelease(name: name, throwCount: angle?.all.n ?? speed?.all.n ?? height?.all.n ?? 0,
                              angle: angle?.all.median, angleSD: angle?.all.sd,
                              speed: speed?.all.median, speedSD: speed?.all.sd,
                              height: height?.all.median, heightSD: height?.all.sd)
    }
}
