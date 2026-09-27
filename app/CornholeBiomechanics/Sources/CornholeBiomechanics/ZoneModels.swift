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
