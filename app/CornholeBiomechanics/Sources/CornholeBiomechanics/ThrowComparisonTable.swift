import SwiftUI

// Athlete summary, throw comparison (spec §4.4): one row per analysed throw, sortable, with a
// "Median · SD" footer computed here in Swift. Double-click opens the throw's report.

// MARK: - Statistics

/// Median and sample standard deviation of one column.
struct MedianSD: Equatable {
    var median: Double
    /// Sample SD (n − 1); nil below two values.
    var sd: Double?
    var n: Int

    /// Finite values only; nil when there are none.
    static func of(_ values: [Double]) -> MedianSD? {
        let sorted = values.filter(\.isFinite).sorted()
        guard !sorted.isEmpty else { return nil }
        let n = sorted.count
        let median = n % 2 == 1 ? sorted[n / 2] : (sorted[n / 2 - 1] + sorted[n / 2]) / 2
        guard n >= 2 else { return MedianSD(median: median, sd: nil, n: n) }
        let mean = sorted.reduce(0, +) / Double(n)
        let variance = sorted.reduce(0) { $0 + ($1 - mean) * ($1 - mean) } / Double(n - 1)
        return MedianSD(median: median, sd: variance.squareRoot(), n: n)
    }
}

// MARK: - Row

/// One analysed throw as the summary shows it. Values are reliable or caution only; an unreliable or
/// missing value is absent from `values` and its reason (if any) is in `withheld`.
struct SummaryThrowRow: Identifiable, Equatable, Sendable {
    var id: UUID
    /// 1-based position among the athlete's throws, oldest first.
    var number: Int
    var label: String
    var score: ScoreCategory?
    var values: [String: Double] = [:]
    var withheld: [String: String] = [:]
    /// Tracking grades (pose, bag, release, calibration → GOOD / WARNING / POOR).
    var grades: [String: String] = [:]
    /// Corrections or settings changed after this analysis.
    var isStale = false
    /// Measured release-to-board-front distance (m), when the analysis had a metric scale.
    var distance: Double?

    static let speedKey = "bag_release_speed_m_s", angleKey = "bag_release_angle_deg", heightKey = "bag_release_height_m"

    var speed: Double? { values[Self.speedKey] }
    var angle: Double? { values[Self.angleKey] }
    var height: Double? { values[Self.heightKey] }
    var elbow: Double? { values["elbow_angle_deg_at_release"] }
    var wristPeak: Double? { values["wrist_peak_speed_arm_lengths_s"] }
    var tempo: Double? { values["swing_tempo_ratio"] }

    /// Sort key for a numeric column: missing values sort after every measured one (ascending).
    subscript(sortValue key: String) -> Double { values[key] ?? .infinity }

    /// Sort key: hole 3, board 1, miss 0, no result −1.
    var resultPoints: Int { score?.rawValue ?? -1 }

    /// Worst grade across stages: POOR > WARNING > GOOD; nil when ungraded.
    var worstGrade: String? {
        let order = ["GOOD": 0, "WARNING": 1, "POOR": 2]
        return grades.values.max { (order[$0] ?? -1) < (order[$1] ?? -1) }
    }
    /// Sort key: 0 good … 2 poor, 3 out of date.
    var qualityRank: Int {
        if isStale { return 3 }
        return ["GOOD": 0, "WARNING": 1, "POOR": 2][worstGrade ?? ""] ?? -1
    }

    /// Release in metres for the success map, when speed, angle and height were all measured.
    var release: MeasuredRelease? {
        guard let speed, let angle, let height else { return nil }
        return MeasuredRelease(id: id, label: label, speed: speed, angle: angle, height: height, score: score, distance: distance)
    }
}

extension SummaryThrowRow {
    /// What the file reads need from one trial, captured on the main actor.
    struct Source: Sendable {
        var id: UUID
        var number: Int
        var label: String
        var score: ScoreCategory?
        var analysisURL: URL
    }

    /// Reads results.json, replay.json grades and the stale marker for each analysed throw, off the main actor.
    static func load(_ sources: [Source]) async -> [SummaryThrowRow] {
        await Task.detached(priority: .userInitiated) { sources.map(read) }.value
    }

    static func read(_ source: Source) -> SummaryThrowRow {
        var row = SummaryThrowRow(id: source.id, number: source.number, label: source.label, score: source.score)
        let results = source.analysisURL.appendingPathComponent("results.json")
        if let metrics = CoachMetricsDocument.load(results)?.coach_metrics {
            for column in ThrowComparisonTable.columns {
                guard let metric = metrics[column.key] else { continue }
                if metric.status != "unreliable", let value = metric.value, value.isFinite {
                    row.values[column.key] = value
                } else {
                    row.withheld[column.key] = metric.reasons.first ?? metric.statusText
                }
            }
        }
        struct Grades: Decodable { var grades: [String: String]? }
        if let data = try? Data(contentsOf: source.analysisURL.appendingPathComponent("replay.json")) {
            row.grades = (try? JSONDecoder().decode(Grades.self, from: data).grades) ?? [:]
        }
        row.isStale = FileManager.default.fileExists(atPath: source.analysisURL.appendingPathComponent("needs_reanalysis.json").path)
        row.distance = MeasuredRelease.releaseToBoard(results)
        return row
    }
}

// MARK: - Table

struct ThrowComparisonTable: View {
    let rows: [SummaryThrowRow]
    let open: (UUID) -> Void
    @State private var sortOrder = [KeyPathComparator(\SummaryThrowRow.number)]
    @State private var selection = Set<UUID>()

    struct Column {
        var key: String
        var title: String
        var unit: String
        var digits: Int
        var value: KeyPath<SummaryThrowRow, Double?>
        var sortValue: KeyPath<SummaryThrowRow, Double> { \SummaryThrowRow.[sortValue: key] }
    }

    /// The six numeric columns, in order (keys as in results.json → coach_metrics).
    static let columns: [Column] = [
        Column(key: SummaryThrowRow.speedKey, title: "Speed", unit: "m/s", digits: 1, value: \.speed),
        Column(key: SummaryThrowRow.angleKey, title: "Angle", unit: "°", digits: 0, value: \.angle),
        Column(key: SummaryThrowRow.heightKey, title: "Height", unit: "m", digits: 2, value: \.height),
        Column(key: "elbow_angle_deg_at_release", title: "Elbow at release", unit: "°", digits: 0, value: \.elbow),
        Column(key: "wrist_peak_speed_arm_lengths_s", title: "Peak wrist speed", unit: "arm lengths/s", digits: 1, value: \.wristPeak),
        Column(key: "swing_tempo_ratio", title: "Tempo", unit: "back ÷ forward", digits: 2, value: \.tempo),
    ]

    private var sorted: [SummaryThrowRow] { rows.sorted(using: sortOrder) }

    var body: some View {
        VStack(alignment: .leading, spacing: Space.s) {
            Table(sorted, selection: $selection, sortOrder: $sortOrder) {
                TableColumn("Throw", value: \.number) { row in Text(row.label).lineLimit(1).help(row.label) }
                    .width(min: 90, ideal: 120)
                TableColumn("Result", value: \.resultPoints) { row in ResultBadge(score: row.score) }
                    .width(min: 60, ideal: 70)
                numberColumn(Self.columns[0])
                numberColumn(Self.columns[1])
                numberColumn(Self.columns[2])
                numberColumn(Self.columns[3])
                numberColumn(Self.columns[4])
                numberColumn(Self.columns[5])
                TableColumn("Quality", value: \.qualityRank) { row in QualityCell(row: row) }
                    .width(min: 56, ideal: 64)
            }
            .contextMenu(forSelectionType: UUID.self) { ids in
                if let id = ids.first { Button("Open Throw") { open(id) } }
            } primaryAction: { ids in
                if let id = ids.first { open(id) }
            }
            .frame(height: min(CGFloat(rows.count) * 24 + 34, 420))
            footer
            Text("Double-click a throw to open its report. — = not measured or not reliable enough to show (hover for the reason). Angles are in the camera's view.")
                .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }
    }

    private func numberColumn(_ column: Column) -> some TableColumnContent<SummaryThrowRow, KeyPathComparator<SummaryThrowRow>> {
        TableColumn(column.unit.isEmpty ? column.title : "\(column.title) (\(column.unit))", value: column.sortValue) { row in
            if let value = row[keyPath: column.value] {
                Text(number(value, digits: column.digits)).monospacedDigit()
            } else {
                Text("—").foregroundStyle(.secondary)
                    .help(row.withheld[column.key] ?? "Not measured")
                    .accessibilityLabel("Not shown: \(row.withheld[column.key] ?? "not measured")")
            }
        }
        .width(min: 64, ideal: column.key.hasPrefix("wrist") || column.key.hasPrefix("elbow") ? 120 : 84)
        .alignment(.trailing)
    }

    /// "Median · SD" for every numeric column, as one text row under the table.
    private var footer: some View {
        ViewThatFits(in: .horizontal) {
            HStack(alignment: .firstTextBaseline, spacing: Space.l) { footerItems }
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 170), alignment: .leading)], alignment: .leading, spacing: Space.xs) { footerItems }
        }
        .font(.caption).monospacedDigit()
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder private var footerItems: some View {
        Text("Median · SD").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
        ForEach(Self.columns, id: \.key) { column in
            HStack(spacing: Space.xs) {
                Text(column.title).foregroundStyle(.secondary)
                Text(Self.footerText(rows.compactMap { $0[keyPath: column.value] }, column: column))
            }
            .fixedSize()
        }
    }

    /// "7.8 · 0.58 m/s"; "7.8 m/s" with one value; "—" with none.
    static func footerText(_ values: [Double], column: Column) -> String {
        guard let stats = MedianSD.of(values) else { return "—" }
        let unit = column.unit == "°" ? "°" : column.unit.contains("÷") ? "" : " \(column.unit)"
        let median = number(stats.median, digits: column.digits)
        guard let sd = stats.sd else { return median + unit }
        return "\(median) · \(number(sd, digits: column.digits + 1))\(unit)"
    }
}

/// Worst tracking grade (glyph + colour), or "out of date".
private struct QualityCell: View {
    let row: SummaryThrowRow
    var body: some View {
        if row.isStale {
            Image(systemName: "arrow.triangle.2.circlepath").foregroundStyle(.orange)
                .help("Corrections changed after this analysis: re-analyze to update its numbers.")
                .accessibilityLabel("Out of date")
        } else if let grade = row.worstGrade {
            GradeGlyph(grade: grade)
                .help(TrustStrip.stages.compactMap { stage in row.grades[stage].map { "\(TrustStrip.title(stage)): \($0.capitalized)" } }
                    .joined(separator: "\n"))
        } else {
            Text("—").foregroundStyle(.secondary).help("No quality grades: re-analyze with the current version.")
        }
    }
}
