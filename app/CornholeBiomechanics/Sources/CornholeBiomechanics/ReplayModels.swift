import Foundation
import SwiftUI

/// One measured throw, as written by `replay.py`. Bag paths are in the release frame's
/// pixels; `release_to_frame[f]` maps them onto frame f of the (possibly hand-held) video.
struct ReplayDocument: Decodable {
    struct Point: Decodable, Hashable { var frame: Int; var x: Double; var y: Double }
    struct Value: Decodable, Hashable { var key: String; var label: String; var unit: String; var value: Double?; var status: String }
    struct Position: Decodable, Hashable { var x: Double; var y: Double }
    struct Event: Decodable {
        var frame: Int
        var label: String
        var position: Position?
        var window: [Int]?
        var values: [Value]?
        var status: String?
        var note: String?
    }
    var fps: Double
    var frame_count: Int
    var width: Int
    var height: Int
    var coordinates: String
    var release_to_frame: [String: [[Double]]]?
    var measured: [Point]
    var filtered: [Point]
    var model: [Point]
    var after_contact: [Point]
    var model_note: String?
    var model_rmse_px: Double?
    var events: [String: Event]
    var grades: [String: String]

    static func load(_ url: URL?) -> ReplayDocument? {
        guard let url, let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(ReplayDocument.self, from: data)
    }

    /// Release-frame pixels → pixels of `frame` (identity for a fixed camera).
    func toFrame(_ x: Double, _ y: Double, frame: Int) -> CGPoint {
        guard let m = release_to_frame?[String(frame)] ?? nearestTransform(frame), m.count == 2, m[0].count == 3 else {
            return CGPoint(x: x, y: y)
        }
        return CGPoint(x: m[0][0] * x + m[0][1] * y + m[0][2], y: m[1][0] * x + m[1][1] * y + m[1][2])
    }
    private func nearestTransform(_ frame: Int) -> [[Double]]? {
        guard let transforms = release_to_frame, !transforms.isEmpty else { return nil }
        let clamped = min(max(frame, 0), frame_count - 1)
        return transforms[String(clamped)]
    }

    /// Display order of events on the timeline.
    static let eventOrder = ["peak_backswing", "peak_wrist_speed", "peak_elbow_extension", "release", "apex", "first_contact", "final_rest", "into_hole"]
    var orderedEvents: [(key: String, event: Event)] {
        Self.eventOrder.compactMap { key in events[key].map { (key, $0) } }
    }
}

/// Per-throw coach metric with reliability (results.json → coach_metrics).
struct CoachMetricRow: Decodable, Identifiable {
    var id: String { key ?? label }
    var key: String?
    var label: String
    var unit: String
    var group: String
    var definition: String
    var event: String?
    var frame: Int?
    var status: String
    var reasons: [String]
    var value: Double?
    var exploratory: Bool?
    /// Smallest change the measurement can resolve (same unit as `value`).
    var noise_floor: Double?

    /// A row for a metric the analysis did not produce: shown as "—", "Not measured".
    static func notMeasured(key: String, label: String, unit: String, group: String) -> CoachMetricRow {
        CoachMetricRow(key: key, label: label, unit: unit, group: group, definition: "Not produced by this analysis.",
                       event: nil, frame: nil, status: "not_measured", reasons: [], value: nil, exploratory: nil, noise_floor: nil)
    }

    /// Statuses whose value must never be used (same rule as Python `verdict._usable`).
    static let unusableStatuses: Set<String> = ["unreliable", "unavailable"]

    /// The value when it may be used (not unreliable or unavailable, finite); nil otherwise.
    var usableValue: Double? {
        guard !Self.unusableStatuses.contains(status), let value, value.isFinite else { return nil }
        return value
    }

    var statusText: String {
        switch status {
        case "reliable": "Reliable"
        case "caution": "Use with caution"
        case "unreliable": "Insufficient tracking quality"
        default: "Not measured"
        }
    }
}

struct CoachMetricsDocument: Decodable {
    var coach_metrics: [String: CoachMetricRow]
    var release_window: [Int]?
    var event_frames: [String: Int?]?
    var wrist_speed_arm_lengths_s: [Double?]?

    static func load(_ url: URL?) -> CoachMetricsDocument? {
        guard let url, let data = try? Data(contentsOf: url) else { return nil }
        guard var document = try? JSONDecoder().decode(CoachMetricsDocument.self, from: data) else { return nil }
        for key in document.coach_metrics.keys { document.coach_metrics[key]?.key = key }
        return document
    }
    func rows(group: String) -> [CoachMetricRow] {
        coachMetricOrder.compactMap { coach_metrics[$0] }.filter { $0.group == group }
    }
}

let coachMetricOrder = [
    "bag_release_speed_m_s", "bag_release_angle_deg", "bag_release_height_m", "bag_release_position_forward_arm_lengths",
    "wrist_speed_at_release_arm_lengths_s", "wrist_peak_speed_arm_lengths_s", "wrist_direction_at_release_deg",
    "swing_release_arm_angle_deg", "swing_backswing_angle_deg", "elbow_angle_deg_at_release",
    "elbow_peak_extension_velocity_deg_s", "trunk_inclination_deg_at_release",
    "wrist_peak_speed_time_rel_release_ms", "elbow_peak_extension_time_rel_release_ms", "swing_forward_duration_s", "swing_tempo_ratio",
]

/// Athlete-level coaching dashboard (dashboards/<athlete>.json, from coaching.py).
struct AthleteDashboard: Decodable {
    struct Sports: Decodable { var bags: Int?; var points_per_bag: Double?; var ppr: Double?; var in_percent: Double?; var on_percent: Double?; var off_percent: Double? }
    struct Dispersion: Decodable { var n: Int?; var rms_radius_inches: Double? }
    struct Performance: Decodable {
        var sports: Sports?
        var counts: [String: Int]?
        var scored_percent: Double?
        var hole_percent: Double?
        var mean_target_error_inches: Double?
        var landing_dispersion: Dispersion?
    }
    struct ProfileValue: Decodable, Identifiable, Hashable { var trial_id: String; var value: Double; var score: Int?; var id: String { trial_id } }
    struct Profile: Decodable, Identifiable {
        var key: String; var label: String; var unit: String; var group: String; var n: Int
        var median: Double; var q25: Double; var q75: Double; var sd: Double; var cv_percent: Double?
        var noise_floor: Double?; var sd_to_noise: Double?; var consistency: String
        var smallest_worthwhile_change: Double?
        var values: [ProfileValue]
        var id: String { key }
    }
    struct Example: Decodable, Hashable { var trial_id: String; var label: String }
    struct Priority: Decodable, Identifiable {
        var key: String; var label: String; var unit: String; var sentence: String?
        var checks: [String: Bool]; var practice: String?; var example_throws: [Example]?
        var why_not_a_priority: [String]?; var kind: String
        var n_scored: Int?; var n_miss: Int?; var cliffs_delta: Double?
        var id: String { key }
    }
    struct Compensation: Decodable {
        var status: String; var n: Int; var ratio: Double?; var message: String
        var observed_spread_m: Double?; var random_pairing_spread_m: Double?; var chance_as_tight: Double?; var method: String?
    }
    struct Link: Decodable, Identifiable {
        var stage: String; var from: String; var to: String; var n: Int; var rho: Double?; var status: String
        var supported: Bool; var from_label: String; var to_label: String
        /// Bootstrap 95% CI of ρ, when estimated.
        var ci: [Double?]?
        var id: String { from + to }
    }
    struct Trust: Decodable { var `throws`: Int; var grades: [String: [String: Int]]; var overall: [String: String]; var reliable_metric_share: Double? }
    struct Variable: Decodable { var key: String; var label: String; var sd: Double?; var unit: String; var sd_to_noise: Double? }

    var athlete: String?
    var athlete_id: String?
    var `throws`: Int
    var throws_with_outcome: Int
    var performance: Performance
    var headline: String
    var release_profile: [Profile]
    var most_variable: Variable?
    var compensation: Compensation
    var evidence_chain: [Link]
    var priorities: [Priority]
    var observed_differences: [Priority]
    var trust: Trust
    var trial_labels: [String: String]?
    /// The athlete's own green zone (height, measured distance and slide, consistency).
    var personal_zone: PersonalZone?
    var distance: DistanceInfo?
    var lateral: LateralInfo?
    /// Throw-to-throw consistency over every comparable throw (not a per-throw snapshot).
    var consistency: TrialInsights.Consistency?
    /// Which throws the summary pooled, and why any were left out.
    var cohort: Cohort?

    static func load(_ url: URL?) -> AthleteDashboard? {
        guard let url, let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(AthleteDashboard.self, from: data)
    }
}

/// "40–46°", "9.8–10.2 arm lengths/s": the unit once, after the range.
func formatRange(_ low: Double, _ high: Double, unit: String) -> String {
    let lowText = formatValue(low, unit: unit), highText = formatValue(high, unit: unit)
    let suffix = unit == "°" ? "°" : unit.isEmpty ? "" : " \(unit)"
    // A dash between negative numbers misreads ("-63–-54"), so negative ranges use "to".
    let separator = low < 0 || high < 0 ? " to " : "–"
    guard !suffix.isEmpty, lowText.hasSuffix(suffix) else { return "\(lowText)\(separator)\(highText)" }
    return "\(lowText.dropLast(suffix.count))\(separator)\(highText)"
}

func gradeColor(_ grade: String?) -> Color {
    switch grade {
    case "GOOD": .green
    case "WARNING": .orange
    case "POOR": .red
    default: .secondary
    }
}

/// Numbers with units the way a coach reads them: 42°, 7.8 m/s, −50 ms.
func formatValue(_ value: Double?, unit: String) -> String {
    guard let value else { return "—" }
    switch unit {
    case "°": return "\(number(value, digits: 0))°"
    case "ms": return "\(number(value, digits: 0)) ms"
    case "°/s": return "\(number(value, digits: 0)) °/s"
    case "m": return "\(number(value, digits: 2)) m"
    case "s": return "\(number(value, digits: 2)) s"
    case "m/s": return "\(number(value, digits: 1)) m/s"
    case "arm lengths/s": return "\(number(value, digits: 1)) arm lengths/s"
    case "": return number(value, digits: 2)
    default: return "\(number(value, digits: 2)) \(unit)"
    }
}
