import SwiftUI

/// One headline sentence and up to three rows: went well / to work on / data note (insights.verdict).
/// When corrections changed since the analysis, a stale banner replaces the verdict.
struct VerdictCard: View {
    let verdict: Verdict?
    let stale: Bool
    var canReanalyze = true
    var reanalyze: () -> Void = {}
    /// Frame to show for a metric key, when the metric has one.
    var frameFor: (String) -> Int? = { _ in nil }
    var seek: (Int) -> Void = { _ in }

    var body: some View {
        Card {
            if stale {
                staleBanner
            } else if let verdict {
                VStack(alignment: .leading, spacing: Space.m) {
                    Text(verdict.headline).font(.title3.weight(.semibold)).fixedSize(horizontal: false, vertical: true)
                        .accessibilityAddTraits(.isHeader)
                    if !verdict.items.isEmpty {
                        VStack(alignment: .leading, spacing: Space.s) {
                            ForEach(verdict.items.prefix(3)) { item in row(item) }
                        }
                    }
                    if let physics = verdict.physics {
                        Text(Self.distanceNote(physics)).font(.caption).foregroundStyle(.secondary)
                    }
                }
            } else {
                Label {
                    VStack(alignment: .leading, spacing: Space.xs) {
                        Text("No verdict yet").font(.headline)
                        Text("Re-analyze this throw with the current version to get a plain-English summary.")
                            .font(.callout).foregroundStyle(.secondary)
                    }
                } icon: { Image(systemName: "text.bubble").foregroundStyle(.secondary) }
            }
        }
    }

    private var staleBanner: some View {
        HStack(alignment: .center, spacing: Space.m) {
            Image(systemName: "arrow.triangle.2.circlepath").font(.title2).foregroundStyle(.orange)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: Space.xs) {
                Text("Analysis out of date").font(.title3.weight(.semibold))
                Text("Tracking or events were corrected after this analysis. Re-analyze to update the verdict and the numbers below.")
                    .font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: Space.m)
            Button("Re-analyze", systemImage: "arrow.clockwise", action: reanalyze)
                .buttonStyle(.borderedProminent).disabled(!canReanalyze)
        }
    }

    @ViewBuilder private func row(_ item: Verdict.Item) -> some View {
        let style = Self.style(item.kind)
        let frame = item.metric_key.flatMap(frameFor)
        let content = HStack(alignment: .firstTextBaseline, spacing: Space.s) {
            Image(systemName: style.symbol).foregroundStyle(style.color).accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(style.title).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                Text(item.text).fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: Space.s)
            if frame != nil {
                Image(systemName: "play.circle").foregroundStyle(.secondary).accessibilityHidden(true)
            }
        }
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(style.title): \(item.text)")
        if let frame {
            Button { seek(frame) } label: { content }
                .buttonStyle(.plain)
                .help("Show this moment in the replay")
                .accessibilityHint("Shows this moment in the replay")
        } else {
            content
        }
    }

    static func style(_ kind: String) -> (title: String, symbol: String, color: Color) {
        switch kind {
        case "good": ("Went well", "checkmark.circle.fill", .green)
        case "fix": ("Work on", "arrow.up.forward.circle.fill", .orange)
        default: ("Data note", "info.circle", .secondary)
        }
    }

    /// Where the board distance in the physics check came from, in plain words.
    static func distanceNote(_ physics: Verdict.Physics) -> String {
        let distance = "\(number(physics.distance_m, digits: 1)) m"
        switch physics.distance_source {
        case "measured": return "Flight checked against the board \(distance) away, measured in this video."
        case "athlete_median": return "Flight checked against the board at \(distance), this athlete's usual measured distance."
        default: return "Flight checked against the board at \(distance), the assumed regulation distance."
        }
    }
}
