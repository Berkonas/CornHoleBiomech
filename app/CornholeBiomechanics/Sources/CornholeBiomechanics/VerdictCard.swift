import SwiftUI

/// One headline sentence and its rows: went well / to work on / data note (insights.verdict).
/// Every "work on" item is shown (at most two), then one data note and one success; anything else
/// sits behind a "N more" disclosure so nothing Python said is silently dropped.
struct VerdictCard: View {
    let verdict: Verdict?
    /// Frame to show for a metric key, when the metric has one.
    var frameFor: (String) -> Int? = { _ in nil }
    var seek: (Int) -> Void = { _ in }
    @State private var showsMore = false

    var body: some View {
        Card {
            if let verdict {
                let split = Self.split(verdict.items)
                VStack(alignment: .leading, spacing: Space.m) {
                    Text(verdict.headline).font(.title3.weight(.semibold)).fixedSize(horizontal: false, vertical: true)
                        .accessibilityAddTraits(.isHeader)
                    if !split.shown.isEmpty {
                        VStack(alignment: .leading, spacing: Space.s) {
                            ForEach(split.shown) { item in row(item) }
                        }
                    }
                    if !split.more.isEmpty {
                        DisclosureGroup(isExpanded: $showsMore) {
                            VStack(alignment: .leading, spacing: Space.s) {
                                ForEach(split.more) { item in row(item) }
                            }.padding(.top, Space.xs)
                        } label: {
                            Text("\(split.more.count) more").font(.callout).foregroundStyle(.secondary)
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

    /// Rows shown up front (up to two "work on", then the first data note and first "went well") and the rest.
    static func split(_ items: [Verdict.Item]) -> (shown: [Verdict.Item], more: [Verdict.Item]) {
        var ids = Set(items.filter { $0.kind == "fix" }.prefix(2).map(\.id))
        if let note = items.first(where: { $0.kind == "note" }) { ids.insert(note.id) }
        if let good = items.first(where: { $0.kind == "good" }) { ids.insert(good.id) }
        return (items.filter { ids.contains($0.id) }, items.filter { !ids.contains($0.id) })
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
