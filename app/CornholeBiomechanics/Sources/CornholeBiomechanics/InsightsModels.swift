import Foundation

struct TrialInsights: Decodable {
    struct Difference: Decodable, Identifiable {
        var metric: String; var name: String; var amount: Double; var signed_difference: Double?
        var units: String; var percent: Double; var phase: String; var explanation: String
        var id: String { metric }
    }
    struct Outcome: Decodable {
        struct Error: Decodable { var radial_error_inches: Double; var lateral_error_inches: Double; var longitudinal_error_inches: Double }
        var score_category: Int; var spatial_error: Error?
        var error_point_kind: String?
    }
    struct Consistency: Decodable {
        struct Component: Decodable, Identifiable {
            var name: String; var variability: Double; var units: String; var tolerance: Double; var weight: Double; var score: Double
            var id: String { name }
        }
        struct Curve: Decodable { var mean: FlexibleNumericArray; var sd: FlexibleNumericArray }
        struct Trace: Decodable { var trial_id: String; var wrist: [[Double?]]; var elbow: [Double?] }
        var n: Int; var minimum_trials: Int; var score: Double?; var message: String
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
    var quality: AnalysisResults.Quality; var outcome: Outcome?; var similarity: ComparisonDocument.Similarity?
    var differences: [Difference]; var coach_summary: String; var consistency: Consistency
    var warnings: [String]; var excluded_trials: [String]; var board_trials: [BoardTrial]
    var relationships: RelationshipDocument?; var provenance: Provenance; var needs_reanalysis: Bool
}

func metricLabel(_ key: String) -> String {
    let relationships = ["elbow_angle_deg_at_release": "Elbow at release (°)", "elbow_angle_deg_rom": "Elbow range of motion (°)", "trunk_inclination_deg_at_release": "Trunk at release (°)", "movement_duration_seconds": "Movement duration (s)", "release_timing_cycle": "Release timing (cycle fraction)", "reference_similarity_score": "Reference Similarity (0–100)", "wrist_reference_deviation_arm_lengths": "Wrist deviation from reference (arm lengths)", "wrist_path_deviation_from_athlete_mean_arm_lengths": "Wrist deviation from own mean (arm lengths)"]
    if let label = relationships[key] { return label }
    let names = ["elbow_angle_deg":"Elbow included angle", "arm_to_trunk_deg":"Arm relative to trunk", "trunk_inclination_deg":"Trunk inclination", "upper_arm_orientation_deg":"Upper-arm orientation", "forearm_orientation_deg":"Forearm orientation", "wrist_path_rmse_arm_lengths":"Wrist-path RMSE", "release_timing_abs_difference_cycle":"Release timing difference", "elbow_angle_mae_deg":"Elbow angle", "upper_arm_orientation_mae_deg":"Upper-arm orientation", "forearm_orientation_mae_deg":"Forearm orientation", "arm_to_trunk_mae_deg":"Arm relative to trunk", "trunk_inclination_mae_deg":"Trunk inclination"]
    return names[key] ?? key.replacingOccurrences(of: "_", with: " ").capitalized
}
func metricUnits(_ key: String) -> String { key.contains("arm_lengths") ? "arm lengths" : key.contains("cycle") ? "cycle fraction" : "degrees" }
func number(_ value: Double?, digits: Int = 1) -> String { value?.formatted(.number.precision(.fractionLength(digits))) ?? "—" }
