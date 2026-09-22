import SwiftUI

enum FeedbackZone: String {
    case green, yellow, red, neutral
    init(score: Int?) {
        self = score == 3 ? .green : score == 1 ? .yellow : score == 0 ? .red : .neutral
    }
    var color: Color { switch self { case .green: .green; case .yellow: .orange; case .red: .red; case .neutral: .secondary } }
    var symbol: String { switch self { case .green: "checkmark.circle.fill"; case .yellow: "minus.circle.fill"; case .red: "xmark.circle.fill"; case .neutral: "questionmark.circle" } }
}
struct FeedbackBadge: View {
    var zone: FeedbackZone
    var text: String
    var body: some View {
        Label(text, systemImage: zone.symbol).font(.caption.weight(.semibold))
            .foregroundStyle(zone.color).padding(.horizontal, 8).padding(.vertical, 5)
            .background(zone.color.opacity(0.12), in: RoundedRectangle(cornerRadius: 6))
    }
}
struct SwingExperiment: Identifiable {
    var id: String
    var explanation: String
    var release: TossParameters?
    var result: TossResult
    static func compare(swing: SwingParameters, environment: TossParameters) -> [Self] {
        var later = swing; later.releaseFraction = min(0.95, later.releaseFraction+0.02)
        var slower = swing; slower.duration += 0.02
        var longer = swing; longer.upperLength += 0.02
        var right = swing; right.stanceRight += 0.10
        return [("Release 2% later", "Changes both hand direction and speed along the same joint path.", later),
                ("Swing 0.02 s slower", "Same joint path; angular speed scales with 1/T.", slower),
                ("Upper arm +2 cm", "Changes the hand’s radius, height and velocity at the same angular motion.", longer),
                ("Stand 10 cm right", "Moves the release sideways while preserving joint motion and aim.", right)].map { label, note, p in
            let release = SwingMechanics(parameters: p).launch(using: environment)
            return .init(id: label, explanation: note, release: release,
                         result: release.map { CornholePhysics(parameters: $0).simulate() } ?? .init(outcome: "Invalid release"))
        }
    }
}
