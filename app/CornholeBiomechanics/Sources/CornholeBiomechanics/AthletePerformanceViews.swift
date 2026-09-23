import Charts
import SwiftUI

/// Within-athlete scored-versus-miss summary written by `performance.py`.
struct AthletePerformance: Decodable {
    struct Feedback: Decodable { var result: String; var why: String; var next: String; var caveat: String; var physics: String? }
    struct Group: Decodable { var n: Int; var median: Double?; var sd: Double?; var cv_percent: Double?; var q25: Double?; var q75: Double? }
    struct Point: Decodable, Identifiable {
        var trial_id: String; var label: String; var value: Double; var group: String?
        var id: String { trial_id }
    }
    struct Variable: Decodable {
        var label: String; var unit: String; var decimals: Int
        var all: Group; var scored: Group; var miss: Group
        var n_scored: Int; var n_miss: Int
        var cliffs_delta: Double?; var noise_floor: Double?
        var below_noise_floor: Bool; var distinguishes: Bool; var spread_distinguishes: Bool? = nil
        var points: [Point]?
    }
    var success_definition: String
    var counts: [String: Int]
    var variables: [String: Variable]
    var feedback: Feedback
    var method: String
}

/// Display order of the pre-chosen release variables (matches performance.VARIABLES).
let performanceVariableOrder = [
    "bag_release_angle_deg", "bag_release_speed_m_s", "bag_release_speed_arm_lengths_s",
    "bag_release_height_m", "bag_release_height_arm_lengths", "bag_release_position_forward_arm_lengths",
    "swing_release_arm_angle_deg", "swing_peak_angular_velocity_deg_s", "swing_backswing_angle_deg", "swing_tempo_ratio",
    "elbow_angle_deg_at_release", "trunk_inclination_deg_at_release",
]
// Validated categorical slots 1–2 (dataviz reference palette); rows also carry the group name.
let scoredInk = Color(red: 0.165, green: 0.471, blue: 0.839)
let missInk = Color(red: 0.922, green: 0.408, blue: 0.204)

/// Level 1 result → level 2 association → level 3 next step.
struct AthleteSummaryCard: View {
    let summary: AthletePerformance
    var body: some View {
        ResearchCard(title: "Athlete summary", symbol: "text.bubble") {
            row("Result", summary.feedback.result, symbol: "target")
            row("What differed", summary.feedback.why, symbol: "arrow.left.arrow.right")
            row("Next practice", summary.feedback.next, symbol: "figure.run")
            if let physics = summary.feedback.physics { row("Physics check", physics, symbol: "function") }
            Text(summary.feedback.caveat).font(.caption).foregroundStyle(.secondary)
        }
    }
    private func row(_ title: String, _ text: String, symbol: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            Label(title, systemImage: symbol).font(.subheadline.weight(.semibold)).frame(width: 150, alignment: .leading)
            Text(text).font(.body).textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
        }
    }
}

/// One dot strip per release variable: scored and missed throws on separate rows.
struct ScoredVersusMissedPanel: View {
    let summary: AthletePerformance
    let currentTrialID: String
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Scored vs missed throws").font(.title2.weight(.semibold))
            Text("Each dot is one throw by this athlete. The vertical tick is each group's median; the ringed dot is this throw. Success = \(summary.success_definition).")
                .font(.callout).foregroundStyle(.secondary)
            if summary.variables.values.allSatisfy({ $0.n_scored + $0.n_miss == 0 }) {
                Label("Record Hole, Board or Miss for this athlete's throws (buttons at the top) to compare scored throws with misses.",
                      systemImage: "hand.tap").foregroundStyle(.secondary)
            } else {
                ForEach(featured, id: \.self) { key in
                    if let variable = summary.variables[key] { strip(variable) }
                }
                let others = keys.filter { !featured.contains($0) }
                if !others.isEmpty {
                    DisclosureGroup("All measured variables (\(others.count) more)") {
                        ForEach(others, id: \.self) { key in
                            if let variable = summary.variables[key] { strip(variable) }
                        }
                    }
                }
            }
            DisclosureGroup("How “differed” is decided") {
                Text(summary.method).font(.callout).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    private var keys: [String] { performanceVariableOrder.filter { summary.variables[$0] != nil } }
    /// Variables that differed between scored and missed throws; otherwise the three largest effects.
    private var featured: [String] {
        let differed = keys.filter { summary.variables[$0]?.distinguishes == true || summary.variables[$0]?.spread_distinguishes == true }
        if !differed.isEmpty { return differed }
        return Array(keys.sorted { abs(summary.variables[$0]?.cliffs_delta ?? 0) > abs(summary.variables[$1]?.cliffs_delta ?? 0) }.prefix(3))
    }

    private func strip(_ v: AthletePerformance.Variable) -> some View {
        let points = (v.points ?? []).filter { $0.group != nil }
        return VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline) {
                Text(v.unit.isEmpty ? v.label : "\(v.label) (\(v.unit))").font(.headline)
                if v.distinguishes {
                    Label("Differed between groups", systemImage: "checkmark.seal").font(.caption.weight(.semibold)).foregroundStyle(.primary)
                } else if v.below_noise_floor {
                    Label("Difference within measurement error", systemImage: "equal.circle").font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Text("scored n = \(v.n_scored) · missed n = \(v.n_miss)").font(.caption).monospacedDigit().foregroundStyle(.secondary)
            }
            Chart {
                ForEach(points) { p in
                    let current = p.trial_id == currentTrialID
                    let ink = p.group == "scored" ? scoredInk : missInk
                    PointMark(x: .value(v.label, p.value), y: .value("Group", groupName(p.group)))
                        .symbol {
                            // A surface ring separates overlapping dots; the current throw gets a primary-ink ring.
                            Circle().fill(ink.opacity(0.85))
                                .overlay(Circle().stroke(current ? Color.primary : Color(nsColor: .windowBackgroundColor), lineWidth: 2))
                                .frame(width: current ? 14 : 9, height: current ? 14 : 9)
                        }
                        .annotation(position: .top, spacing: 1) {
                            if current { Text("this throw").font(.caption2).foregroundStyle(.secondary) }
                        }
                        .accessibilityLabel("\(p.label), \(groupName(p.group))\(current ? ", this throw" : "")")
                        .accessibilityValue("\(format(p.value, v)) \(v.unit)")
                }
                ForEach([("Scored", v.scored.median), ("Missed", v.miss.median)], id: \.0) { name, median in
                    if let median {
                        PointMark(x: .value(v.label, median), y: .value("Group", name))
                            .symbol { Rectangle().fill(Color.primary).frame(width: 2, height: 22) }
                            .accessibilityLabel("\(name) median").accessibilityValue("\(format(median, v)) \(v.unit)")
                    }
                }
            }
            .chartYScale(domain: ["Scored", "Missed"])
            .chartXScale(domain: paddedDomain(points.map(\.value)))
            .frame(height: 96)
            if let delta = v.cliffs_delta {
                Text("Medians: scored \(withUnit(v.scored.median, v)), missed \(withUnit(v.miss.median, v)) · Cliff’s δ \(number(delta, digits: 2)) · noise floor \(withUnit(v.noise_floor, v))")
                    .font(.caption).monospacedDigit().foregroundStyle(.secondary)
            }
        }.padding(.vertical, 4)
    }
    private func groupName(_ group: String?) -> String { group == "scored" ? "Scored" : "Missed" }
    private func format(_ value: Double?, _ v: AthletePerformance.Variable) -> String { number(value, digits: v.decimals) }
    private func withUnit(_ value: Double?, _ v: AthletePerformance.Variable) -> String {
        format(value, v) + (v.unit == "°" ? "°" : " \(v.unit)")
    }
    /// Data range plus 8 % on each side so edge dots and rings are not clipped.
    private func paddedDomain(_ values: [Double]) -> ClosedRange<Double> {
        guard let low = values.min(), let high = values.max() else { return 0...1 }
        let pad = max((high - low) * 0.08, abs(high) * 0.01, 1e-3)
        return (low - pad)...(high + pad)
    }
}
