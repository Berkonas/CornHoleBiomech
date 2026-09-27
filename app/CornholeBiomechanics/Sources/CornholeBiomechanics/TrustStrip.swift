import SwiftUI

/// GOOD / WARNING / POOR per measurement stage, each with a glyph, and the rule in the tooltip.
struct TrustStrip: View {
    let grades: [String: String]
    static let stages = ["pose", "bag", "release", "calibration"]

    var body: some View {
        HStack(spacing: Space.s) {
            Text("Data quality").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
            ForEach(Self.stages, id: \.self) { stage in
                let grade = grades[stage]
                HStack(spacing: Space.xs) {
                    GradeGlyph(grade: grade)
                    Text("\(Self.title(stage)) \(grade.map { $0.capitalized } ?? "—")").font(.caption)
                }
                .padding(.horizontal, Space.s).padding(.vertical, 3)
                .background(gradeColor(grade).opacity(0.1), in: Capsule())
                .help(Self.rule(stage))
            }
        }
    }

    static func title(_ stage: String) -> String {
        ["pose": "Body tracking", "bag": "Bag tracking", "release": "Release", "calibration": "Scale"][stage] ?? stage
    }

    /// The grading rule for one stage (what GOOD requires).
    static func rule(_ stage: String) -> String {
        switch stage {
        case "pose": "Throwing arm and trunk visible in ≥90% of frames and around release."
        case "bag": "Bag found in ≥90% of flight frames, no gap longer than 3 frames, low noise."
        case "release": "Release confirmed, or the two automatic release cues agree within 3 frames."
        default: "GOOD needs a measured scale (meter stick) that agrees with the bag's fall. WARNING = fall-based scale only: metres are approximate."
        }
    }
}

/// Data-quality grade glyph: colour is always paired with a symbol.
struct GradeGlyph: View {
    let grade: String?
    var body: some View {
        let symbol = switch grade {
        case "GOOD": "checkmark.circle.fill"
        case "WARNING": "exclamationmark.triangle.fill"
        case "POOR": "xmark.octagon.fill"
        default: "minus.circle"
        }
        Image(systemName: symbol).foregroundStyle(gradeColor(grade)).imageScale(.small)
            .accessibilityLabel(grade?.capitalized ?? "Not graded")
    }
}
