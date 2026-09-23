import Charts
import SwiftUI

/// ACL-style statistics (python `zones.sports_stats`).
struct SportsStats: Decodable {
    var bags: Int; var unknown: Int
    var points_per_bag: Double?; var ppr: Double?
    var in_percent: Double?; var on_percent: Double?; var off_percent: Double?
}

/// Physics-based release zones (python `zones.zone_report`).
struct ZoneReport: Decodable {
    struct Band: Decodable { var zone: String; var low: Double; var high: Double }
    struct Variable: Decodable, Identifiable {
        var variable: String; var key: String; var label: String; var unit: String; var center: Double
        var bands: [Band]
        var green_window: [Double]?; var green_half_width: Double?; var athlete_sd: Double?; var aim_bias: Double?; var demand_ratio: Double?
        var id: String { variable }
    }
    struct Throw: Decodable, Identifiable {
        var trial_id: String; var zone: String; var observed: Int?; var agrees: Bool?
        var speed: Double; var angle: Double; var height: Double
        var id: String { trial_id }
        func value(_ variable: String) -> Double { variable == "speed" ? speed : variable == "angle" ? angle : height }
    }
    struct Agreement: Decodable { var n: Int; var agree: Int; var rate: Double? }
    var status: String; var message: String?; var meaning: String
    var variables: [Variable]; var throwList: [Throw]; var agreement: Agreement
    enum CodingKeys: String, CodingKey {
        case status, message, meaning, variables, agreement
        case throwList = "throws"
    }
}

/// Status palette (dataviz reference): reserved meaning, always paired with an icon and label.
enum ZoneStyle {
    static func color(_ zone: String) -> Color {
        switch zone {
        case "green": Color(red: 0.047, green: 0.639, blue: 0.047)
        case "yellow": Color(red: 0.980, green: 0.698, blue: 0.098)
        default: Color(red: 0.816, green: 0.231, blue: 0.231)
        }
    }
    static func label(_ zone: String) -> String { zone == "green" ? "Hole window" : zone == "yellow" ? "On the board" : "Off" }
    static func symbol(_ zone: String) -> String { zone == "green" ? "checkmark.circle.fill" : zone == "yellow" ? "minus.circle.fill" : "xmark.circle.fill" }
}

struct SportsStatsStrip: View {
    let stats: SportsStats
    var body: some View {
        HStack(spacing: 28) {
            stat("PPR", stats.ppr.map { number($0, digits: 1) } ?? "—", "points per 4-bag round (max 12)")
            stat("In", percent(stats.in_percent), "bags in the hole")
            stat("On", percent(stats.on_percent), "bags on the board")
            stat("Off", percent(stats.off_percent), "bags off the board")
            stat("Bags", "\(stats.bags)", stats.unknown > 0 ? "\(stats.unknown) without outcome" : "with recorded outcome")
        }.padding(.vertical, 4)
    }
    private func percent(_ v: Double?) -> String { v.map { "\(number($0, digits: 0))%" } ?? "—" }
    private func stat(_ title: String, _ value: String, _ caption: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
            Text(value).font(.title.weight(.semibold)).monospacedDigit()
            Text(caption).font(.caption2).foregroundStyle(.secondary)
        }
    }
}

struct ZonesPanel: View {
    let report: ZoneReport
    let currentTrialID: String
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Release zones").font(.title2.weight(.semibold))
            if report.status != "available" {
                Text(report.message ?? "Zones need scaled release measurements.").foregroundStyle(.secondary)
            } else {
                Text("Where a bag released with each value would first land, holding the athlete's other release values at their median. Marks are this athlete's throws, shaped by their real outcome.")
                    .font(.callout).foregroundStyle(.secondary)
                HStack(spacing: 16) {
                    ForEach(["green", "yellow", "red"], id: \.self) { z in
                        Label(ZoneStyle.label(z), systemImage: ZoneStyle.symbol(z)).foregroundStyle(ZoneStyle.color(z)).font(.caption.weight(.semibold))
                    }
                    Text("● hole · ◆ board · ✕ miss").font(.caption).foregroundStyle(.secondary)
                }
                ForEach(report.variables) { v in row(v) }
                if let rate = report.agreement.rate {
                    Label("Model zone matched the real outcome in \(report.agreement.agree) of \(report.agreement.n) throws (\(number(rate * 100, digits: 0))%). Lower agreement means aim, bag bounce or measurement matter more than these release values.",
                          systemImage: "checkmark.seal").font(.callout)
                }
                DisclosureGroup("How zones are defined") {
                    Text(report.meaning + " Green = first contact from 45 cm short of the hole centre to its far edge (bags landing short usually slide in); yellow = elsewhere on the board or up to 30 cm short of it; red = otherwise, including a thin band where the bag would strike the front face of the board. Drag-free point mass; release-to-board distance from settings.")
                        .font(.callout).foregroundStyle(.secondary)
                }
            }
        }
    }

    private func row(_ v: ZoneReport.Variable) -> some View {
        let values = report.throwList.map { $0.value(v.variable) }
        let window = v.green_window ?? [v.center, v.center]
        let pad = max((window[1] - window[0]) * 2.5, (values.max() ?? v.center) - (values.min() ?? v.center), 0.05 * abs(v.center))
        let lo = min(values.min() ?? v.center, window[0]) - pad * 0.3
        let hi = max(values.max() ?? v.center, window[1]) + pad * 0.3
        return VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text("\(v.label) (\(v.unit))").font(.headline)
                Spacer()
                if let w = v.green_window {
                    Text("hole window \(fmt(w[0], v))–\(fmt(w[1], v)) · athlete SD \(v.athlete_sd.map { fmt($0, v) } ?? "—")")
                        .font(.caption).monospacedDigit().foregroundStyle(.secondary)
                }
            }
            Chart {
                ForEach(Array(v.bands.enumerated()), id: \.offset) { _, b in
                    if b.high >= lo && b.low <= hi {
                        RectangleMark(xStart: .value(v.label, max(b.low, lo)), xEnd: .value(v.label, min(b.high, hi)), yStart: .value("", 0), yEnd: .value("", 1))
                            .foregroundStyle(ZoneStyle.color(b.zone).opacity(0.28))
                    }
                }
                ForEach(report.throwList) { t in
                    PointMark(x: .value(v.label, t.value(v.variable)), y: .value("", 0.5))
                        .symbol { marker(t) }
                        .accessibilityLabel("Throw \(t.trial_id.prefix(6)), observed \(outcome(t.observed)), model \(ZoneStyle.label(t.zone))")
                        .accessibilityValue(fmt(t.value(v.variable), v))
                }
            }
            .chartXScale(domain: lo...hi)
            .chartYScale(domain: 0...1)
            .chartYAxis(.hidden)
            .frame(height: 64)
        }
    }

    @ViewBuilder private func marker(_ t: ZoneReport.Throw) -> some View {
        let current = t.trial_id == currentTrialID
        let size: CGFloat = current ? 14 : 10
        Group {
            switch t.observed {
            case 3: Image(systemName: "circle.fill").resizable()
            case 1: Image(systemName: "diamond.fill").resizable()
            case 0: Image(systemName: "xmark").resizable().fontWeight(.bold)
            default: Image(systemName: "circle.dashed").resizable()
            }
        }
        .frame(width: size, height: size)
        .foregroundStyle(Color.primary)
        .overlay { if current { Circle().stroke(Color.primary, lineWidth: 2).frame(width: size + 8, height: size + 8) } }
    }
    private func outcome(_ s: Int?) -> String { s == 3 ? "hole" : s == 1 ? "board" : s == 0 ? "miss" : "unknown" }
    private func fmt(_ x: Double, _ v: ZoneReport.Variable) -> String { v.unit == "°" ? "\(number(x, digits: 1))°" : "\(number(x, digits: 2)) \(v.unit)" }
}
