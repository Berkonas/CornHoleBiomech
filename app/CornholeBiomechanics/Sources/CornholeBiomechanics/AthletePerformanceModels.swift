import Foundation

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
