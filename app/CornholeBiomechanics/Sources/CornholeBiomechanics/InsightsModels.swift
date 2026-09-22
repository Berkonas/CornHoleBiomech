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
}

func metricLabel(_ key: String) -> String {
    let extended = [
        "arm_motion_mean_flexion_deg": "Mean projected elbow flexion (°)",
        "arm_motion_flexion_rom_deg": "Forward-swing elbow excursion (°)",
        "arm_motion_flexion_sd_deg": "Within-swing elbow flexion SD (°)",
        "arm_motion_radius_cv_ratio": "Forward-swing radius CV (ratio)",
        "elbow_extension_deficit_deg_at_release": "Elbow extension deficit at release (°)",
        "shoulder_translation_net_arm_lengths": "Shoulder net translation (arm lengths)",
        "shoulder_peak_speed_arm_lengths_s": "Peak projected shoulder speed (arm lengths/s)",
        "wrist_relative_peak_speed_arm_lengths_s": "Peak shoulder-relative wrist speed (arm lengths/s)",
        "shoulder_wrist_radius_at_release_arm_lengths": "Shoulder-to-wrist distance at release (arm lengths)",
        "shoulder_wrist_radius_forward_swing_sd_arm_lengths": "Forward-swing radial distance SD (arm lengths)",
        "wrist_forward_swing_path_straightness_ratio": "Forward-swing path straightness (0–1)",
        "wrist_forward_swing_path_rms_fitted_line_deviation_arm_lengths": "Forward-swing line deviation RMS (arm lengths)",
        "bag_release_speed_arm_lengths_s": "Projected bag launch speed (arm lengths/s)",
        "bag_release_angle_deg": "Projected bag launch angle (°)",
        "bag_release_position_forward_arm_lengths": "Bag release position, forward (arm lengths)",
        "bag_release_position_vertical_arm_lengths": "Bag release position, vertical (arm lengths)",
        "elbow_angle_mae_deg": "Elbow angle mean absolute difference (°)",
        "trunk_inclination_mae_deg": "Trunk inclination mean absolute difference (°)",
        "upper_arm_orientation_mae_deg": "Upper-arm orientation mean absolute difference (°)",
        "forearm_orientation_mae_deg": "Forearm orientation mean absolute difference (°)",
        "arm_to_trunk_mae_deg": "Arm-to-trunk mean absolute difference (°)",
        "wrist_path_rmse_arm_lengths": "Wrist-path RMS difference (arm lengths)"
    ]
    if let label = extended[key] { return label }
    let relationships = ["elbow_angle_deg_at_release": "Elbow at release (°)", "elbow_angle_deg_rom": "Elbow range of motion (°)", "trunk_inclination_deg_at_release": "Trunk at release (°)", "movement_duration_seconds": "Movement duration (s)", "release_timing_cycle": "Release timing (cycle fraction)", "wrist_reference_deviation_arm_lengths": "Wrist deviation from reference (arm lengths)", "wrist_path_deviation_from_athlete_mean_arm_lengths": "Wrist deviation from own mean (arm lengths)"]
    if let label = relationships[key] { return label }
    let names = ["elbow_angle_deg":"Elbow included angle", "arm_to_trunk_deg":"Arm relative to trunk", "trunk_inclination_deg":"Trunk inclination", "upper_arm_orientation_deg":"Upper-arm orientation", "forearm_orientation_deg":"Forearm orientation", "wrist_path_rmse_arm_lengths":"Wrist-path RMSE", "release_timing_abs_difference_cycle":"Release timing difference", "elbow_angle_mae_deg":"Elbow angle", "upper_arm_orientation_mae_deg":"Upper-arm orientation", "forearm_orientation_mae_deg":"Forearm orientation", "arm_to_trunk_mae_deg":"Arm relative to trunk", "trunk_inclination_mae_deg":"Trunk inclination"]
    return names[key] ?? key.replacingOccurrences(of: "_", with: " ").capitalized
}
func metricUnits(_ key: String) -> String { key.contains("arm_lengths") ? "arm lengths" : key.contains("cycle") ? "cycle fraction" : "degrees" }
func number(_ value: Double?, digits: Int = 1) -> String { value?.formatted(.number.precision(.fractionLength(digits))) ?? "—" }

func metricMechanism(_ key: String) -> String {
    switch key {
    case "bag_release_angle_deg": "Why it matters: angle divides release velocity between forward travel and height; its effect depends on speed and release position."
    case "bag_release_speed_m_s", "bag_release_speed_arm_lengths_s": "Why it matters: speed changes flight distance and impact velocity at a given angle; projected video speed is not automatically true 3D speed."
    case "elbow_angle_deg_at_release": "Why it matters: elbow configuration changes hand position and the velocity produced by joint motion. The same angle can accompany many different throws."
    default: "Interpret within the same athlete and recording setup; an association with outcome is not a causal effect."
    }
}
