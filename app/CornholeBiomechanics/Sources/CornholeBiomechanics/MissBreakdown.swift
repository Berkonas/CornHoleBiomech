import SwiftUI

// Blocks 1, 3 and 4 of the throw screen (design council §1): the result and its one sentence, the miss breakdown
// (two additive bars from two_view.json → attribution) and the release against the athlete's usual. Wording and
// rounding follow council §1/§7: inches whole, angles 1°, launch direction 0.5°, speed differences 0.1 m/s; no causes,
// no percentages of blame; a part is emphasised only when the engine named it (≥ 2× its noise, ≥ 3 in, ≥ 40 % of the
// axis). Anything not measured is left out with a short reason.

// MARK: - Model

/// two_view.json → attribution (python `attribution.py`, schema attribution_v1). Every field optional: older files
/// have no block and newer engines may add fields. Lengths in inches (lateral + = thrower's right, depth + = long).
struct ThrowAttribution: Decodable, Equatable {
    struct Component: Decodable, Equatable, Identifiable {
        var key: String?
        var label: String?
        /// This part's contribution to the axis's miss (in).
        var inches: Double?
        var noise_in: Double?
        var named: Bool?
        var named_in: Double?
        var share: Double?
        var usual_in: Double?
        var vs_usual_in: Double?
        /// "usual" (measured against the athlete's usual), "absolute", "line_to_hole".
        var basis: String?
        /// "flight_3d" or "heading".
        var source: String?
        var angle_deg: Double?
        var id: String { key ?? label ?? "part" }

        enum CodingKeys: String, CodingKey {
            case key, label, inches = "in", noise_in, named, named_in, share, usual_in, vs_usual_in, basis, source, angle_deg
        }
    }

    struct Axis: Decodable, Equatable {
        var miss_in: Double?
        var components: [Component]?
        var residual_in: Double?
        /// "centre_line" (lateral parts add up from the board's centre line) or "usual" (depth parts from the usual spot).
        var reference: String?
    }

    struct Driver: Decodable, Equatable, Identifiable {
        var key: String?
        var label: String?
        var value: Double?
        var usual: Double?
        var delta: Double?
        var noise: Double?
        var unit: String?
        var named: Bool?
        var status: String?
        /// Model: inches this difference moves the landing (speed: carry; launch direction: sideways at the board).
        var implied_in: Double?
        var id: String { key ?? label ?? "driver" }
    }

    struct Usual: Decodable, Equatable {
        var `throws`: Double?
        var spread_lateral_in: Double?
        var spread_depth_in: Double?
        var centre_lateral_in: Double?
        var centre_depth_in: Double?
        var source: String?
        var reason: String?
        var throwCount: Int? { `throws`.map { Int($0.rounded()) } }
    }

    struct InsideSpread: Decodable, Equatable { var lateral: Bool?; var depth: Bool? }

    var version: String?
    var status: String?
    var reason: String?
    var reasons: [String]?
    /// "throughHole", "onBoard", "offBoard".
    var result: String?
    var rest_on: String?
    var lateral: Axis?
    var depth: Axis?
    var drivers: [Driver]?
    var usual: Usual?
    var inside_spread: InsideSpread?
    var within_usual_spread: Bool?
    var sentence: String?
    var cue: String?
    /// "geometry", "physics" or "within_spread".
    var tier: String?

    func lateralComponent(_ key: String) -> Component? { lateral?.components?.first { $0.key == key } }
    func depthComponent(_ key: String) -> Component? { depth?.components?.first { $0.key == key } }
    func driver(_ key: String) -> Driver? { drivers?.first { $0.key == key } }

    var isHole: Bool { result == "throughHole" || rest_on == "hole" }
}

/// "6 in right", "2 in short", "0 in": a signed length in whole inches with its direction word.
func inchWords(_ value: Double, low: String, high: String) -> String {
    let n = abs(value).rounded()
    return n == 0 ? "0 in" : "\(number(n, digits: 0)) in \(value > 0 ? high : low)"
}

// MARK: - 1. Result and sentence

/// Block 1: the result chip and the throw's one sentence (attribution sentence, else the two-view explanation), with
/// the front camera's result to accept in one click.
struct ThrowSummaryCard: View {
    let document: TwoViewDocument
    let recorded: ScoreCategory?
    var canEdit = true
    var accept: (ScoreCategory) -> Void = { _ in }

    var body: some View {
        Card {
            HStack(alignment: .center, spacing: Space.s) {
                resultChip
                if document.result?.status == "needs_confirmation" {
                    Label("Needs confirmation", systemImage: "exclamationmark.triangle.fill")
                        .font(.caption.weight(.semibold)).foregroundStyle(.orange)
                }
                if let tier = tierText {
                    Text(tier).font(.caption).foregroundStyle(.secondary)
                }
                Spacer(minLength: 0)
            }
            Text(sentence).font(.title2.weight(.semibold)).fixedSize(horizontal: false, vertical: true)
                .textSelection(.enabled)
            if let reason = document.attribution?.reason, !reason.isEmpty {
                Text(reason).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
            suggestion
        }
    }

    private var sentence: String {
        if !document.isMeasured { return document.reason ?? "The front camera could not be used for this throw." }
        return document.attribution?.sentence ?? document.explanation?.sentence ?? "Where the bag ended was not measured."
    }

    private var tierText: String? {
        switch document.attribution?.tier {
        case "geometry": "From measured parts that add up to the miss"
        case "physics": "Measured parts, with the drag-free model for speed"
        case "within_spread": "Within this athlete's usual spread"
        default: nil
        }
    }

    private var resultChip: some View {
        let score = recorded ?? document.suggestedScore
        let text = score.map { WhereItEndedCard.label($0) } ?? "No result yet"
        let color = BoardEndsMap.color(score)
        return HStack(spacing: Space.xs) {
            Text(text).font(.headline)
            if recorded == nil, score != nil { Text("front camera").font(.caption) }
        }
        .padding(.horizontal, 10).padding(.vertical, 4)
        .foregroundStyle(color)
        .background(color.opacity(0.14), in: Capsule())
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder private var suggestion: some View {
        if let suggested = document.suggestedScore, recorded != suggested {
            HStack(spacing: Space.m) {
                Image(systemName: "video").foregroundStyle(.secondary).accessibilityHidden(true)
                Text("Front camera: ").foregroundStyle(.secondary) + Text(WhereItEndedCard.label(suggested)).bold()
                    + Text(document.result?.views_agree == false ? " (the side camera saw it differently: check the video)" : "")
                        .foregroundStyle(.secondary)
                Spacer(minLength: Space.m)
                Button(recorded == nil ? "Use This Result" : "Change to \(WhereItEndedCard.label(suggested))") { accept(suggested) }
                    .disabled(!canEdit)
            }
            .font(.callout)
        }
    }
}

// MARK: - 3. Miss breakdown

/// One additive bar: the parts of one axis's miss laid end to end from the hole line, each with its noise.
struct MissBar: Identifiable {
    struct Part: Identifiable {
        var id: String
        var label: String
        var start: Double
        var value: Double
        var noise: Double?
        var named: Bool
        var detail: String?
        /// What the parts do not explain (`residual_in`), drawn neutral.
        var unexplained = false
    }

    var id: String
    var title: String
    var low: String
    var high: String
    var parts: [Part]
    /// Parts that were not measured (not drawn; the bar then does not add up and says so).
    var missing: [String]
    var miss: Double
    /// The athlete's usual centre ± spread on this axis (≥ 5 other throws).
    var usualBand: ClosedRange<Double>?
    var insideSpread: Bool?
    var domain: ClosedRange<Double>

    static func make(_ axis: ThrowAttribution.Axis?, lateral: Bool, usual: ThrowAttribution.Usual?, insideSpread: Bool?) -> MissBar? {
        guard let axis, let miss = axis.miss_in, let components = axis.components, !components.isEmpty else { return nil }
        let low = lateral ? "left" : "short", high = lateral ? "right" : "long"
        // Depth reads from the usual spot: where the athlete usually stops, then carry and slide against their usual.
        let ordered = lateral ? components : components.filter { $0.key == "usual_spot" } + components.filter { $0.key != "usual_spot" }
        var parts: [Part] = [], missing: [String] = []
        var at = 0.0
        for component in ordered {
            let label = Self.label(component, lateral: lateral)
            guard let value = component.inches, value.isFinite else { missing.append(label); continue }
            parts.append(Part(id: component.id, label: label, start: at, value: value, noise: component.noise_in,
                              named: component.named == true, detail: Self.detail(component, lateral: lateral)))
            at += value
        }
        if let residual = axis.residual_in, abs(residual) >= 0.5 {
            parts.append(Part(id: "residual", label: "Not split into parts", start: at, value: residual, noise: nil, named: false,
                              detail: nil, unexplained: true))
        }
        guard !parts.isEmpty else { return nil }
        var band: ClosedRange<Double>?
        if let usual, (usual.throwCount ?? 0) >= 5,
           let centre = lateral ? usual.centre_lateral_in : usual.centre_depth_in,
           let spread = lateral ? usual.spread_lateral_in : usual.spread_depth_in, spread > 0 {
            band = (centre - spread)...(centre + spread)
        }
        var extent = abs(miss)
        for part in parts {
            extent = max(extent, abs(part.start), abs(part.start + part.value) + (part.noise ?? 0))
        }
        if let band { extent = max(extent, abs(band.lowerBound), abs(band.upperBound)) }
        let reach = max(12, (extent * 1.1 / 6).rounded(.up) * 6)
        return MissBar(id: lateral ? "lateral" : "depth", title: lateral ? "Left / right" : "Short / long", low: low, high: high,
                       parts: parts, missing: missing, miss: miss, usualBand: band, insideSpread: insideSpread, domain: -reach...reach)
    }

    private static func label(_ c: ThrowAttribution.Component, lateral: Bool) -> String {
        switch c.key {
        case "usual_spot": return "Your usual spot"
        case "carry": return c.basis == "usual" || c.vs_usual_in != nil ? "Carry vs your usual" : (c.label ?? "Carry")
        case "slide": return c.basis == "usual" || c.vs_usual_in != nil ? "Slide vs your usual" : (c.label ?? "Slide")
        default: return c.label ?? (c.key ?? "Part").replacingOccurrences(of: "_", with: " ").capitalized
        }
    }

    /// A second line for a part: the launch angle behind "aim", or a named part's difference from the usual.
    private static func detail(_ c: ThrowAttribution.Component, lateral: Bool) -> String? {
        var parts: [String] = []
        if c.key == "aim", let deg = c.angle_deg {
            parts.append(abs(deg) < 0.25 ? "launched straight" : "launched \(halfDegrees(deg))° \(deg > 0 ? "right" : "left")")
        }
        if lateral, c.named == true, let vs = c.vs_usual_in, abs(vs) >= 1 {
            parts.append("\(inchWords(vs, low: "left", high: "right")) of your usual")
        }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }
}

/// Block 3 (council §1/§4): two small additive bars. Left/right = release position + aim + slide drift; short/long =
/// your usual spot + carry + slide against your usual. Grey: each part's noise. Emphasised: the parts the engine named.
struct MissBreakdownCard: View {
    let attribution: ThrowAttribution

    private var bars: [MissBar] {
        [MissBar.make(attribution.lateral, lateral: true, usual: attribution.usual, insideSpread: attribution.inside_spread?.lateral),
         MissBar.make(attribution.depth, lateral: false, usual: attribution.usual, insideSpread: attribution.inside_spread?.depth)]
            .compactMap { $0 }
    }

    var body: some View {
        Card("Miss breakdown", symbol: "chart.bar.xaxis",
             subtitle: "Measured parts laid end to end from the hole line; together they reach where the bag stopped.") {
            let shown = bars
            if shown.isEmpty {
                Label(attribution.reason ?? "The parts of this miss were not measured.", systemImage: "info.circle")
                    .font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            } else {
                ForEach(shown) { bar in MissBarView(bar: bar) }
                if attribution.lateral?.miss_in == nil || attribution.depth?.miss_in == nil {
                    Text(attribution.lateral?.miss_in == nil ? "Left/right was not measured on this throw." : "Short/long was not measured on this throw.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                legend
            }
        }
    }

    private var legend: some View {
        HStack(spacing: Space.l) {
            swatch(RoundedRectangle(cornerRadius: 2).fill(Color.accentColor).frame(width: 16, height: 8), "named part")
            swatch(RoundedRectangle(cornerRadius: 2).fill(Color.secondary.opacity(0.5)).frame(width: 16, height: 8), "other part")
            swatch(Rectangle().fill(Color.gray.opacity(0.25)).frame(width: 16, height: 12), "± noise")
            swatch(Rectangle().fill(athleteInk.opacity(0.18)).frame(width: 16, height: 12), "your usual spread")
            Spacer(minLength: 0)
        }
        .font(.caption).foregroundStyle(.secondary)
    }

    private func swatch(_ shape: some View, _ text: String) -> some View {
        HStack(spacing: 5) { shape; Text(text) }
    }
}

/// One axis: a row per part (waterfall) and the total, all on one inch scale with the hole line at 0.
struct MissBarView: View {
    let bar: MissBar

    var body: some View {
        VStack(alignment: .leading, spacing: Space.xs) {
            HStack(alignment: .firstTextBaseline) {
                Text(bar.title).font(.headline)
                if bar.insideSpread == true {
                    Text("within your usual spread").font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Text("← \(bar.low)   \(bar.high) →").font(.caption2).foregroundStyle(.secondary)
            }
            Grid(alignment: .leading, horizontalSpacing: Space.m, verticalSpacing: 3) {
                ForEach(bar.parts) { part in
                    GridRow {
                        VStack(alignment: .leading, spacing: 0) {
                            Text(part.label).font(.callout.weight(part.named ? .semibold : .regular))
                                .foregroundStyle(part.unexplained ? .secondary : .primary)
                            if let detail = part.detail { Text(detail).font(.caption2).foregroundStyle(.secondary) }
                        }
                        .frame(width: 190, alignment: .leading)
                        MissBarRow(domain: bar.domain, start: part.start, value: part.value, noise: part.noise,
                                   style: part.unexplained ? .unexplained : part.named ? .named : .plain)
                            .frame(height: 18)
                        Text(inchWords(part.value, low: bar.low, high: bar.high))
                            .font(.callout.monospacedDigit().weight(part.named ? .semibold : .regular))
                            .frame(width: 92, alignment: .trailing)
                    }
                    .accessibilityElement(children: .combine)
                }
                Divider().gridCellColumns(3)
                GridRow {
                    Text("Where it stopped").font(.callout.weight(.semibold)).frame(width: 190, alignment: .leading)
                    MissBarRow(domain: bar.domain, start: 0, value: bar.miss, noise: nil, style: .total, band: bar.usualBand)
                        .frame(height: 20)
                    Text(inchWords(bar.miss, low: bar.low, high: bar.high))
                        .font(.callout.monospacedDigit().weight(.semibold)).frame(width: 92, alignment: .trailing)
                }
                .accessibilityElement(children: .combine)
            }
            if !bar.missing.isEmpty {
                Text("Not measured: \(bar.missing.joined(separator: ", ")). The parts shown do not add up to the miss.")
                    .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

/// One waterfall segment on the shared scale: the hole line, a grey band of ± noise around the segment's end, the
/// segment from `start` to `start + value`, and (total row) the athlete's usual spread.
struct MissBarRow: View {
    enum Style { case plain, named, unexplained, total }
    let domain: ClosedRange<Double>
    let start: Double
    let value: Double
    let noise: Double?
    let style: Style
    var band: ClosedRange<Double>? = nil

    var body: some View {
        Canvas { context, size in
            let span = domain.upperBound - domain.lowerBound
            func x(_ v: Double) -> Double { (min(max(v, domain.lowerBound), domain.upperBound) - domain.lowerBound) / span * Double(size.width) }
            let h = Double(size.height), mid = h / 2
            if let band {
                context.fill(Path(CGRect(x: x(band.lowerBound), y: 0, width: x(band.upperBound) - x(band.lowerBound), height: h)),
                             with: .color(athleteInk.opacity(0.18)))
            }
            let end = start + value
            if let noise, noise > 0 {
                context.fill(Path(CGRect(x: x(end - noise), y: 1, width: x(end + noise) - x(end - noise), height: h - 2)),
                             with: .color(Color.gray.opacity(0.25)))
            }
            var zero = Path(); zero.move(to: CGPoint(x: x(0), y: 0)); zero.addLine(to: CGPoint(x: x(0), y: h))
            context.stroke(zero, with: .color(.primary.opacity(0.45)), lineWidth: 1)
            if style != .total, start != 0 {
                var link = Path(); link.move(to: CGPoint(x: x(start), y: 0)); link.addLine(to: CGPoint(x: x(start), y: h))
                context.stroke(link, with: .color(.secondary.opacity(0.6)), style: StrokeStyle(lineWidth: 1, dash: [2, 2]))
            }
            let lo = x(min(start, end)), hi = x(max(start, end))
            let rect = CGRect(x: lo, y: mid - (style == .total ? 5 : 4), width: max(hi - lo, 1.5), height: style == .total ? 10 : 8)
            let fill: Color = switch style {
            case .named: Color.accentColor
            case .plain: Color.secondary.opacity(0.5)
            case .unexplained: Color.secondary.opacity(0.22)
            case .total: Color.primary.opacity(0.8)
            }
            context.fill(Path(roundedRect: rect, cornerRadius: 2), with: .color(fill))
            if style == .unexplained {
                context.stroke(Path(roundedRect: rect, cornerRadius: 2), with: .color(.secondary), style: StrokeStyle(lineWidth: 0.8, dash: [2, 2]))
            }
            if style == .total {
                // The bag where it stopped.
                let p = CGPoint(x: x(end), y: mid)
                context.fill(Path(roundedRect: CGRect(x: p.x - 5, y: p.y - 5, width: 10, height: 10), cornerRadius: 2), with: .color(Color.accentColor))
                context.stroke(Path(roundedRect: CGRect(x: p.x - 5, y: p.y - 5, width: 10, height: 10), cornerRadius: 2), with: .color(.white), lineWidth: 1)
            }
        }
        .accessibilityHidden(true)
    }
}

// MARK: - 4. Release vs your usual

/// One strip: this throw's value against the athlete's other throws, the usual with ± noise (inside reads "usual").
struct UsualStripRow: Identifiable {
    var id: String
    var label: String
    var unit: String
    var value: Double?
    var usual: Double?
    var noise: Double?
    var others: [Double]
    var named: Bool
    var valueText: String
    var deltaText: String?
    var detail: String?
    /// Why the value is missing (nothing is drawn for it).
    var reason: String?
    var minimumSpan: Double
    var low: String? = nil
    var high: String? = nil
}

/// Block 4 (council §1): release speed, release angle, launch direction and slide length as dots on the athlete's own
/// range strips. The grey band is the usual ± the measurement noise; a value inside it reads "usual".
struct ReleaseVsUsualCard: View {
    let rows: [UsualStripRow]
    var usualThrows: Int? = nil

    var body: some View {
        Card("Release vs your usual", symbol: "arrow.up.right",
             subtitle: "This throw (dark dot) among this athlete's other throws (grey dots).") {
            Grid(alignment: .leading, horizontalSpacing: Space.m, verticalSpacing: Space.s) {
                ForEach(rows) { row in
                    GridRow {
                        VStack(alignment: .leading, spacing: 1) {
                            Text(row.label).font(.callout.weight(row.named ? .semibold : .regular))
                            Text(row.valueText).font(.title3.monospacedDigit())
                        }
                        .frame(width: 150, alignment: .leading)
                        if row.value == nil {
                            Text(row.reason ?? "Not measured on this throw.").font(.caption).foregroundStyle(.secondary)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        } else {
                            UsualStrip(row: row).frame(height: 30)
                        }
                        VStack(alignment: .trailing, spacing: 1) {
                            if let delta = row.deltaText {
                                Text(delta).font(.callout.weight(row.named ? .semibold : .regular))
                                    .foregroundStyle(row.named ? Color.accentColor : .primary)
                            }
                            if let detail = row.detail { Text(detail).font(.caption).foregroundStyle(.secondary) }
                        }
                        .frame(width: 190, alignment: .trailing)
                    }
                    .accessibilityElement(children: .combine)
                }
            }
            Text(caption).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }
    }

    private var caption: String {
        var text = "Grey band: your usual ± what the measurement can resolve; inside it reads “usual”. Bold: a difference the throw's sentence names."
        if let usualThrows { text += " Usual = median of \(usualThrows) other throws." }
        return text
    }

    /// The rows from the attribution's drivers and the slide part, with dots from the athlete's other throws.
    static func rows(attribution: ThrowAttribution?, document: TwoViewDocument?, speedHistory: [Double], angleHistory: [Double],
                     others: [TwoViewHistoryEntry], speed: Double?, angle: Double?) -> [UsualStripRow] {
        func median(_ values: [Double]) -> Double? { MedianSD.of(values)?.median }
        var rows: [UsualStripRow] = []

        // Release speed (0.1 m/s), release angle (1°).
        let speedDriver = attribution?.driver("release_speed")
        // The attribution's value when it has the driver (it withholds unreliable ones: missing stays missing).
        let speedValue = speedDriver != nil ? speedDriver?.value : speed
        rows.append(row(id: "speed", label: "Release speed", unit: "m/s", value: speedValue,
                        usual: speedDriver?.usual ?? median(speedHistory), noise: speedDriver?.noise, others: speedHistory,
                        named: speedDriver?.named == true, minimumSpan: 1.0,
                        format: { "\(number($0, digits: 1)) m/s" },
                        delta: { d in "\(number(abs(d), digits: 1)) m/s \(d > 0 ? "faster" : "slower") than usual" },
                        detail: speedDriver?.named == true ? speedDriver?.implied_in.map { "about \(number(abs($0), digits: 0)) in of carry" } : nil))
        let angleDriver = attribution?.driver("release_angle")
        rows.append(row(id: "angle", label: "Release angle", unit: "°", value: angleDriver != nil ? angleDriver?.value : angle,
                        usual: angleDriver?.usual ?? median(angleHistory), noise: angleDriver?.noise, others: angleHistory,
                        named: angleDriver?.named == true, minimumSpan: 10,
                        format: { "\(number($0, digits: 0))°" },
                        delta: { d in "\(number(abs(d), digits: 0))° \(d > 0 ? "higher" : "flatter") than usual" }, detail: nil))

        // Launch direction (0.5°) and slide length (whole inches): two-camera throws only.
        if let document {
            let driver = attribution?.driver("launch_direction")
            let launchOthers = others.compactMap(\.launchDeg)
            var launch = row(id: "launch", label: "Launch direction", unit: "°", value: driver != nil ? driver?.value : document.launchDirection?.deg,
                             usual: driver?.usual ?? median(launchOthers), noise: driver?.noise, others: launchOthers,
                             named: driver?.named == true, minimumSpan: 4,
                             format: { $0.magnitude < 0.25 ? "straight" : "\(halfDegrees($0))° \($0 > 0 ? "right" : "left")" },
                             delta: { d in "\(halfDegrees(d))° \(d > 0 ? "right" : "left") of usual" },
                             detail: driver?.named == true ? driver?.implied_in.map { "about \(number(abs($0), digits: 0)) in at the board" } : nil)
            launch.low = "left"; launch.high = "right"
            if launch.value == nil {
                launch.reason = "Not measured: " + shortReason(document.flight_3d?.reason ?? document.heading?.reason)
            }
            rows.append(launch)

            let slidePart = attribution?.depthComponent("slide")
            var slideValue: Double?
            if let landing = document.landing, landing.outcome == "board", let c = landing.contact?.y_in, let r = landing.rest?.y_in {
                slideValue = r - c
            }
            let slideOthers = others.compactMap(\.slideIn)
            var slide = row(id: "slide", label: "Slide length", unit: "in", value: slideValue,
                            usual: slidePart?.usual_in ?? median(slideOthers), noise: slidePart?.noise_in, others: slideOthers,
                            named: slidePart?.named == true, minimumSpan: 12,
                            format: { "\(number($0, digits: 0)) in" },
                            delta: { d in "\(number(abs(d), digits: 0)) in \(d > 0 ? "further" : "shorter") than usual" }, detail: nil)
            if slideValue == nil {
                slide.reason = document.landing?.outcome == "hole" ? "Went into the hole."
                    : document.landing?.outcome == "off" ? "Not on the board, so no slide on the deck."
                    : "First contact or the rest point was not measured."
            }
            rows.append(slide)
        }
        return rows
    }

    private static func row(id: String, label: String, unit: String, value: Double?, usual: Double?, noise: Double?, others: [Double],
                            named: Bool, minimumSpan: Double, format: (Double) -> String, delta: (Double) -> String,
                            detail: String?) -> UsualStripRow {
        var deltaText: String?
        if let value, let usual {
            let d = value - usual
            if let noise, abs(d) <= noise { deltaText = "usual" } else { deltaText = delta(d) }
        }
        return UsualStripRow(id: id, label: label, unit: unit, value: value, usual: usual, noise: noise, others: others,
                             named: named, valueText: value.map(format) ?? "—", deltaText: deltaText, detail: detail,
                             reason: value == nil ? "Not measured on this throw." : nil, minimumSpan: minimumSpan)
    }
}

/// The strip: the athlete's other throws (grey dots), the usual ± noise (grey band, usual tick) and this throw.
struct UsualStrip: View {
    let row: UsualStripRow

    var body: some View {
        Canvas { context, size in
            var points = row.others
            if let value = row.value { points.append(value) }
            if let usual = row.usual { points += [usual - (row.noise ?? 0), usual + (row.noise ?? 0)] }
            guard var lo = points.min(), var hi = points.max() else { return }
            if hi - lo < row.minimumSpan { let mid = (lo + hi) / 2; lo = mid - row.minimumSpan / 2; hi = mid + row.minimumSpan / 2 }
            let pad = 0.08 * (hi - lo); lo -= pad; hi += pad
            let width = Double(size.width), mid = Double(size.height) * 0.4
            func x(_ v: Double) -> Double { (v - lo) / (hi - lo) * width }
            var axis = Path(); axis.move(to: CGPoint(x: 0, y: mid)); axis.addLine(to: CGPoint(x: width, y: mid))
            context.stroke(axis, with: .color(.primary.opacity(0.15)), lineWidth: 1)
            if let usual = row.usual {
                if let noise = row.noise, noise > 0 {
                    context.fill(Path(CGRect(x: x(usual - noise), y: mid - 8, width: x(usual + noise) - x(usual - noise), height: 16)),
                                 with: .color(Color.gray.opacity(0.25)))
                }
                var tick = Path(); tick.move(to: CGPoint(x: x(usual), y: mid - 9)); tick.addLine(to: CGPoint(x: x(usual), y: mid + 9))
                context.stroke(tick, with: .color(athleteInk), lineWidth: 2)
            }
            for (index, value) in row.others.enumerated() {
                let jitter = Double(index % 3 - 1) * 2.5
                context.fill(Path(ellipseIn: CGRect(x: x(value) - 2.5, y: mid + jitter - 2.5, width: 5, height: 5)),
                             with: .color(.secondary.opacity(0.55)))
            }
            if let value = row.value {
                let p = CGRect(x: x(value) - 5, y: mid - 5, width: 10, height: 10)
                context.fill(Path(ellipseIn: p), with: .color(row.named ? Color.accentColor : Color.primary))
                context.stroke(Path(ellipseIn: p), with: .color(.white), lineWidth: 1.2)
            }
            let caption = { (text: String) in Text(text).font(.caption2).foregroundStyle(.secondary) }
            let digits = row.unit == "m/s" ? 1 : 0
            context.draw(caption(row.low.map { "← \($0)" } ?? number(lo, digits: digits)), at: CGPoint(x: 0, y: Double(size.height)), anchor: .bottomLeading)
            context.draw(caption(row.high.map { "\($0) →" } ?? number(hi, digits: digits)), at: CGPoint(x: width, y: Double(size.height)), anchor: .bottomTrailing)
        }
        .accessibilityLabel(row.label)
        .accessibilityValue([row.valueText, row.deltaText].compactMap { $0 }.joined(separator: ", "))
    }
}

// MARK: - The athlete's other two-camera throws

/// What the strips and the board ghost need from one other two-camera throw (two_view.json, read loosely).
struct TwoViewHistoryEntry: Equatable, Sendable {
    var id: UUID
    /// Launch direction (°, + right): the 3D flight's, else the two-view heading.
    var launchDeg: Double?
    /// Slide along the deck, first contact → rest (in), for bags that stopped on the board.
    var slideIn: Double?
    /// Where it stopped on the deck (v in up from the front edge, right of centre); the hole for a hole.
    var rest: PlanPoint?

    static func read(id: UUID, url: URL) -> TwoViewHistoryEntry? {
        struct Point: Decodable { var x_in: Double?; var y_in: Double? }
        struct Landing: Decodable {
            var outcome: String?; var contact: Point?; var rest: Point?
            enum CodingKeys: String, CodingKey { case outcome = "where", contact, rest }
        }
        struct Flight: Decodable { var status: String?; var lateral_launch_angle_deg: Double? }
        struct Heading: Decodable { var status: String?; var deg: Double? }
        struct Slim: Decodable { var status: String?; var landing: Landing?; var flight_3d: Flight?; var heading: Heading? }
        guard let data = try? Data(contentsOf: url), let slim = try? JSONDecoder().decode(Slim.self, from: data),
              slim.status == "measured" else { return nil }
        var entry = TwoViewHistoryEntry(id: id)
        if let flight = slim.flight_3d, flight.status == "measured" || flight.status == "estimated", let deg = flight.lateral_launch_angle_deg {
            entry.launchDeg = deg
        } else if let heading = slim.heading, heading.status == "measured" || heading.status == "estimated" {
            entry.launchDeg = heading.deg
        }
        if let landing = slim.landing {
            if landing.outcome == "hole" {
                entry.rest = PlanPoint(v: 39, right: 0)
            } else if let x = landing.rest?.x_in, let y = landing.rest?.y_in {
                entry.rest = PlanPoint(v: y, right: x - 12)
            }
            if landing.outcome == "board", let c = landing.contact?.y_in, let r = landing.rest?.y_in { entry.slideIn = r - c }
        }
        return entry
    }
}

/// This athlete's two-camera throws, read once and reused until a two_view.json changes.
@MainActor enum AthleteTwoViewHistory {
    private struct Source: Sendable { var id: UUID; var url: URL }
    private static var cache: [UUID: (key: String, entries: [TwoViewHistoryEntry])] = [:]

    static func entries(athleteID: UUID, store: ProjectStore) async -> [TwoViewHistoryEntry] {
        let sources = (store.project?.trials ?? []).filter { $0.athleteID == athleteID && $0.isTwoCamera }.compactMap { trial in
            store.analysisURL(for: trial).map { Source(id: trial.id, url: $0.appendingPathComponent("two_view.json")) }
        }
        let key = sources.map { source in
            let date = (try? FileManager.default.attributesOfItem(atPath: source.url.path)[.modificationDate] as? Date) ?? .distantPast
            return "\(source.id)|\(date.timeIntervalSince1970)"
        }.joined(separator: ",")
        if let hit = cache[athleteID], hit.key == key { return hit.entries }
        let entries = await Task.detached(priority: .userInitiated) {
            sources.compactMap { TwoViewHistoryEntry.read(id: $0.id, url: $0.url) }
        }.value
        cache[athleteID] = (key, entries)
        return entries
    }
}
