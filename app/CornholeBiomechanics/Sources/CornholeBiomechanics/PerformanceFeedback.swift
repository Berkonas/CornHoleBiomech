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

/// A plotted empirical classification domain, never a universal target range.
struct EvidenceRangeView: View {
    var feedback: PerformanceSummary.Evidence.Feedback
    var value: Double?
    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            if feedback.zone != "neutral", let value,
               let hole = feedback.ranges["hole"], let other = feedback.ranges["board_or_miss"],
               let hl = hole.low, let hh = hole.high, let ol = other.low, let oh = other.high {
                let lo = min(hl, ol, value), hi = max(hh, oh, value)
                let pad = max((hi-lo)*0.12, 0.01)
                let lower = lo-pad, upper = hi+pad
                Canvas { context, size in
                    func x(_ v: Double) -> Double { (v-lower)/(upper-lower)*size.width }
                    let cuts = [lower, hl, hh, ol, oh, upper].sorted()
                    for (a,b) in zip(cuts, cuts.dropFirst()) where b > a {
                        let mid = (a+b)/2
                        let inHole = hl...hh ~= mid, inOther = ol...oh ~= mid
                        let zone: FeedbackZone = inHole && !inOther ? .green : inOther && !inHole ? .red : .yellow
                        context.fill(Path(CGRect(x:x(a), y:9, width:x(b)-x(a), height:12)), with:.color(zone.color.opacity(0.7)))
                    }
                    var mark = Path(); mark.move(to:.init(x:x(value),y:2)); mark.addLine(to:.init(x:x(value),y:29))
                    context.stroke(mark, with:.color(.primary), lineWidth:2)
                }.frame(height: 31)
                    .accessibilityLabel("Current value \(number(value)). Hole range \(number(hl)) to \(number(hh)); board/miss range \(number(ol)) to \(number(oh)). \(feedback.explanation)")
                Text("Hole: \(number(hl))–\(number(hh)) · board/miss: \(number(ol))–\(number(oh))")
                    .font(.caption2).monospacedDigit().foregroundStyle(.secondary)
                Text("Line = this throw · yellow = overlap or outside both ranges").font(.caption2).foregroundStyle(.secondary)
            } else {
                Text("No defensible colored range yet").font(.caption2).foregroundStyle(.secondary)
            }
            Text("Other reviewed throws: \(feedback.ranges["hole"]?.n ?? 0)/\(feedback.minimum_per_group) hole · \(feedback.ranges["board_or_miss"]?.n ?? 0)/\(feedback.minimum_per_group) board/miss")
                .font(.caption2).foregroundStyle(.secondary)
        }
    }
}
