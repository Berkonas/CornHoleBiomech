import Foundation

struct TrialInsights: Decodable {
    var performance: PerformanceSummary?
    struct Difference: Decodable, Identifiable {
        var metric: String; var name: String; var amount: Double; var signed_difference: Double?
        var units: String; var percent: Double; var phase: String; var explanation: String
        var id: String { metric }
    }
    struct Outcome: Decodable {
        struct Error: Decodable { var radial_error_inches: Double; var lateral_error_inches: Double; var longitudinal_error_inches: Double }
        var score_category: Int?; var spatial_error: Error?
        var error_point_kind: String?
    }
    struct Consistency: Decodable {
        struct Component: Decodable, Identifiable {
            var name: String; var variability: Double; var units: String
            var id: String { name }
        }
        struct Curve: Decodable { var mean: FlexibleNumericArray; var sd: FlexibleNumericArray }
        struct Trace: Decodable { var trial_id: String; var wrist: [[Double?]]; var elbow: [Double?] }
        var n: Int; var minimum_trials: Int; var message: String
        var components: [Component]; var curves: [String: Curve]; var traces: [Trace]; var tau: [Double]?; var equation: String?
    }
    struct BoardTrial: Decodable, Identifiable {
        var trial_id: String; var label: String; var outcome: TrialOutcome
        var id: String { trial_id }
    }
    struct Provenance: Decodable {
        struct Configuration: Decodable {
            struct Filter: Decodable { var enabled: Bool; var order: Int; var cutoff_hz: Double }
            var filter: Filter?; var confidence_threshold: Double?; var max_interpolation_gap_frames: Int?; var normalization_samples: Int?
        }
        var configuration: Configuration?
        var backend: String; var model: String; var sports2d_version: String?; var analysis_id: String?; var model_hash: String?; var camera_view: String
    }
    var trial_id: String; var athlete: String; var trial_name: String; var date: String?
    var quality: AnalysisResults.Quality; var outcome: Outcome?; var comparison_available: Bool?
    var differences: [Difference]; var coach_summary: String; var consistency: Consistency
    var warnings: [String]; var excluded_trials: [String]; var board_trials: [BoardTrial]
    var relationships: RelationshipDocument?; var provenance: Provenance; var needs_reanalysis: Bool
    var verdict: Verdict?
}

/// Per-throw coaching verdict (insights.json → verdict, from the Python coaching module).
struct Verdict: Decodable {
    struct Item: Decodable, Identifiable {
        /// "good", "fix" or "note".
        var kind: String; var text: String; var metric_key: String?
        var id: String { kind + text }
    }
    /// Drag-free flight to first contact. `distance_source` is "measured", "athlete_median" or "assumed".
    struct Physics: Decodable {
        var distance_m: Double; var distance_source: String; var landing: String; var zone: String
        var from_hole_m: Double?; var required_speed_m_s: Double?; var delta_speed_m_s: Double?; var sensitivity_m_per_m_s: Double?
        var landing_x_m: Double?; var hole_x_m: Double?
        var speed_m_s: Double?; var angle_deg: Double?; var height_m: Double?
    }
    var headline: String; var items: [Item]; var physics: Physics?
    var method: String?
}

/// A value with `digits` decimals, or "—". Values that round to zero never show as "-0".
func number(_ value: Double?, digits: Int = 1) -> String {
    guard let value else { return "—" }
    let text = value.formatted(.number.precision(.fractionLength(digits)))
    return text.hasPrefix("-") && text.dropFirst().allSatisfy({ "0.,".contains($0) }) ? String(text.dropFirst()) : text
}
