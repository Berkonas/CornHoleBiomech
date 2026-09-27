import Charts
import SwiftUI

// Athlete summary, consistency (spec §4.5): elbow-angle curves over the normalised movement cycle
// (each throw faint, coloured by result; mean ± 1 SD band) and release-profile dot strips.

/// Data colour of a result: scored blue (hole or board), miss orange, no result grey.
func resultInk(_ score: ScoreCategory?) -> Color {
    switch score {
    case .throughHole, .onBoard: scoredInk
    case .offBoard: missInk
    case nil: Color.gray
    }
}

/// Fewest throws before the summary judges spread (consistency, "unusual").
let minimumThrowsToJudge = 5

// MARK: - Elbow curves

/// Per-throw elbow curves and their mean ± 1 SD, in movement-cycle percent.
struct ElbowCurves: Equatable {
    struct Point: Identifiable, Equatable {
        var id: String { "\(series)-\(x)" }
        var series: String
        var trial: UUID?
        var x: Double
        var y: Double
    }
    struct BandPoint: Identifiable, Equatable {
        var id: Double { x }
        var x: Double, mean: Double, low: Double, high: Double
    }

    var lines: [Point] = []
    var band: [BandPoint] = []
    var throwCount = 0

    /// Lines break at missing samples (a new series per run), so gaps are never bridged.
    init(consistency: TrialInsights.Consistency) {
        guard let tau = consistency.tau, !tau.isEmpty else { return }
        for trace in consistency.traces {
            var run = 0, inRun = false
            for (i, t) in tau.enumerated() {
                guard let v = trace.elbow[safe: i] ?? nil, v.isFinite else { if inRun { run += 1; inRun = false }; continue }
                inRun = true
                lines.append(Point(series: "\(trace.trial_id)#\(run)", trial: UUID(uuidString: trace.trial_id), x: 100 * t, y: v))
            }
        }
        throwCount = consistency.traces.count
        let mean = consistency.curves["elbow_angle_deg"]?.mean.scalars
        let sd = consistency.curves["elbow_angle_deg"]?.sd.scalars
        if let mean, let sd {
            band = tau.enumerated().compactMap { i, t in
                guard let m = mean[safe: i] ?? nil, let s = sd[safe: i] ?? nil, m.isFinite, s.isFinite else { return nil }
                return BandPoint(x: 100 * t, mean: m, low: m - s, high: m + s)
            }
        }
    }

    var domain: ClosedRange<Double> {
        let values = lines.map(\.y) + band.flatMap { [$0.low, $0.high] }
        return JointAngleChart.domain(values)
    }
}

struct ElbowConsistencyChart: View {
    let curves: ElbowCurves
    let scores: [UUID: ScoreCategory]

    var body: some View {
        VStack(alignment: .leading, spacing: Space.s) {
            Chart {
                ForEach(curves.band) { p in
                    AreaMark(x: .value("Movement cycle (%)", p.x), yStart: .value("Elbow angle (°)", p.low), yEnd: .value("Elbow angle (°)", p.high),
                             series: .value("Series", "band"))
                        .foregroundStyle(athleteInk.opacity(0.16))
                        .interpolationMethod(.monotone)
                }
                ForEach(curves.lines) { p in
                    LineMark(x: .value("Movement cycle (%)", p.x), y: .value("Elbow angle (°)", p.y), series: .value("Series", p.series))
                        .foregroundStyle(resultInk(p.trial.flatMap { scores[$0] }).opacity(0.45))
                        .lineStyle(StrokeStyle(lineWidth: 1.2))
                        .interpolationMethod(.monotone)
                }
                ForEach(curves.band) { p in
                    LineMark(x: .value("Movement cycle (%)", p.x), y: .value("Elbow angle (°)", p.mean), series: .value("Series", "mean"))
                        .foregroundStyle(athleteInk)
                        .lineStyle(StrokeStyle(lineWidth: 3))
                        .interpolationMethod(.monotone)
                }
            }
            .chartXScale(domain: 0...100)
            .chartYScale(domain: curves.domain)
            .chartXAxisLabel("Movement cycle (% from start to end of the throw)", alignment: .center)
            .chartYAxisLabel("Elbow angle (°)", position: .leading)
            .chartLegend(.hidden)
            .frame(height: 240)
            .accessibilityLabel("Elbow angle in degrees over the movement cycle for \(curves.throwCount) throws, with their mean and one standard deviation band")
            HStack(spacing: Space.l) {
                ChartLegendItem(color: scoredInk, label: "Scored throw")
                ChartLegendItem(color: missInk, label: "Miss")
                ChartLegendItem(color: .gray, label: "No result")
                if !curves.band.isEmpty { ChartLegendItem(color: athleteInk, label: "Average ± 1 SD (shaded)") }
            }
            Text("Each line is one throw, stretched to the same length so throws can be laid on top of each other. 180° = straight arm. A narrow shaded band means the arm moves the same way every throw.")
                .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }
    }
}

// MARK: - Release profile strips

/// One dot per throw for each release and body measure, with the middle half shaded and the median marked;
/// the spread is compared with measurement noise only from `minimumThrowsToJudge` throws.
struct ReleaseProfileStrips: View {
    let profile: [AthleteDashboard.Profile]

    var body: some View {
        VStack(alignment: .leading, spacing: Space.m) {
            ForEach(profile) { row in
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .center, spacing: Space.l) {
                        title(row).frame(width: 200, alignment: .leading)
                        strip(row).frame(minWidth: 280)
                        Self.consistencyNote(row).frame(width: 210, alignment: .leading)
                    }
                    VStack(alignment: .leading, spacing: Space.xs) {
                        title(row)
                        strip(row)
                        Self.consistencyNote(row)
                    }
                }
                if row.id != profile.last?.id { Divider() }
            }
            HStack(spacing: Space.l) {
                legendMark(.throughHole, "Hole"); legendMark(.onBoard, "Board"); legendMark(.offBoard, "Miss"); legendMark(nil, "No result")
                HStack(spacing: Space.xs) {
                    RoundedRectangle(cornerRadius: 2).fill(athleteInk.opacity(0.3)).frame(width: 18, height: 8)
                    Text("Middle half of throws, line = median")
                }
            }
            .font(.caption).foregroundStyle(.secondary)
        }
    }

    private func title(_ row: AthleteDashboard.Profile) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(row.label).font(.callout.weight(.medium))
            Text("Typical \(formatValue(row.median, unit: row.unit)) · middle half \(formatRange(row.q25, row.q75, unit: row.unit))")
                .font(.caption).monospacedDigit().foregroundStyle(.secondary)
        }
    }

    private func strip(_ row: AthleteDashboard.Profile) -> some View {
        Chart {
            RectangleMark(xStart: .value(row.label, row.q25), xEnd: .value(row.label, row.q75), yStart: .value("", 0.2), yEnd: .value("", 0.8))
                .foregroundStyle(athleteInk.opacity(0.3))
            RuleMark(x: .value(row.label, row.median), yStart: .value("", 0.1), yEnd: .value("", 0.9))
                .foregroundStyle(athleteInk).lineStyle(StrokeStyle(lineWidth: 2))
            ForEach(row.values) { value in
                let score = value.score.flatMap(ScoreCategory.init(rawValue:))
                PointMark(x: .value(row.label, value.value), y: .value("", 0.5))
                    .symbol { ResultMark(score: score) }
                    .accessibilityLabel(score.map { "Throw, \(ResultMark.name($0))" } ?? "Throw, no result")
                    .accessibilityValue(formatValue(value.value, unit: row.unit))
            }
        }
        .chartYScale(domain: 0...1)
        .chartYAxis(.hidden)
        .chartXScale(domain: Self.domain(row))
        .chartXAxis { AxisMarks(values: .automatic(desiredCount: 4)) }
        .chartXAxisLabel(row.unit.isEmpty ? row.label : "\(row.label) (\(row.unit))", alignment: .center)
        .frame(height: 64)
    }

    /// Plain-English spread verdict; "too few throws" below `minimumThrowsToJudge`.
    static func consistencyNote(_ row: AthleteDashboard.Profile) -> some View {
        let judged = row.n >= minimumThrowsToJudge
        let steady = row.consistency == "within measurement noise"
        let (symbol, color, text): (String, Color, String) =
            !judged ? ("minus.circle", .secondary, "Too few throws to judge (\(row.n))")
            : steady ? ("checkmark.circle.fill", .green, "As steady as the camera can measure")
            : row.consistency == "variable" ? ("arrow.left.and.right.circle.fill", .orange, "Varies more than measurement noise")
            : ("minus.circle", .secondary, row.consistency.prefix(1).uppercased() + row.consistency.dropFirst())
        return VStack(alignment: .leading, spacing: 2) {
            Label(text, systemImage: symbol).font(.caption.weight(.semibold)).foregroundStyle(color)
            if judged {
                Text("Spread (SD) \(formatValue(row.sd, unit: row.unit)) · noise \(formatValue(row.noise_floor, unit: row.unit))")
                    .font(.caption2).monospacedDigit().foregroundStyle(.secondary)
            }
        }
        .help("Throw-to-throw standard deviation compared with the smallest change this measurement can resolve.")
    }

    /// Data range plus padding so the dots use the strip's width.
    static func domain(_ row: AthleteDashboard.Profile) -> ClosedRange<Double> {
        let values = row.values.map(\.value) + [row.q25, row.q75]
        guard let low = values.min(), let high = values.max() else { return 0...1 }
        let pad = max((high - low) * 0.12, abs(high) * 0.02, 1e-3)
        return (low - pad)...(high + pad)
    }

    private func legendMark(_ score: ScoreCategory?, _ label: String) -> some View {
        HStack(spacing: Space.xs) { ResultMark(score: score); Text(label) }
    }
}

/// A throw's mark in dot plots: shape and colour both carry the result
/// (● hole, ◆ board blue; ✕ miss orange; ○ no result grey).
struct ResultMark: View {
    let score: ScoreCategory?
    var size: CGFloat = 9

    static func name(_ score: ScoreCategory) -> String {
        switch score { case .throughHole: "hole"; case .onBoard: "board"; case .offBoard: "miss" }
    }

    var body: some View {
        let ink = resultInk(score)
        Group {
            switch score {
            case .throughHole: Circle().fill(ink)
            case .onBoard: Rectangle().fill(ink).rotationEffect(.degrees(45)).scaleEffect(0.78)
            case .offBoard: Image(systemName: "xmark").resizable().fontWeight(.heavy).foregroundStyle(ink)
            case nil: Circle().strokeBorder(ink, lineWidth: 1.8)
            }
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }
}
