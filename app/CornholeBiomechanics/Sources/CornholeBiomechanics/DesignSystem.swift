import SwiftUI

// Visual system (spec §7). Data inks are fixed and reused everywhere; `measuredInk` and `modelInk`
// live next to the replay that introduced them.

// Validated categorical slots 1–2 (dataviz reference palette); rows also carry the group name.
let scoredInk = Color(red: 0.165, green: 0.471, blue: 0.839)
let missInk = Color(red: 0.922, green: 0.408, blue: 0.204)
/// The athlete's own data (curves, IQR bands).
let athleteInk = Color(red: 0.15, green: 0.51, blue: 0.56)

/// Movement events in order, with coach-facing names.
let eventNames: [(String, String)] = [("motion_start", "Start"), ("peak_backswing", "Backswing"), ("forward_swing", "Forward swing"), ("release", "Release"), ("peak_follow_through", "Follow-through"), ("motion_end", "End")]

/// Spacing scale: 4 / 8 / 12 / 16 / 24 / 32.
enum Space {
    static let xs: CGFloat = 4, s: CGFloat = 8, m: CGFloat = 12, l: CGFloat = 16, xl: CGFloat = 24, xxl: CGFloat = 32
}

enum Radius { static let card: CGFloat = 12 }

// MARK: - Page and card

/// One scrolling detail page: 24 pt margins, 24 pt between cards, readable max width 1120.
struct Page<Content: View>: View {
    private let content: Content
    init(@ViewBuilder content: () -> Content) { self.content = content() }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Space.xl) { content }
                .frame(maxWidth: 1120, alignment: .leading)
                .padding(Space.xl)
                .frame(maxWidth: .infinity)
        }
        .background(Color(nsColor: .windowBackgroundColor))
    }
}

struct CardHeader: View {
    let title: String
    var symbol: String? = nil
    var subtitle: String? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: Space.xs) {
            Group {
                if let symbol { Label(title, systemImage: symbol) } else { Text(title) }
            }
            .font(.title2.weight(.semibold))
            if let subtitle { Text(subtitle).font(.callout).foregroundStyle(.secondary) }
        }
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(.isHeader)
    }
}

/// Grouped content on a raised surface: padding 16, corner radius 12, optional header.
struct Card<Content: View>: View {
    private let title: String?
    private let symbol: String?
    private let subtitle: String?
    private let content: Content

    init(_ title: String? = nil, symbol: String? = nil, subtitle: String? = nil, @ViewBuilder content: () -> Content) {
        self.title = title; self.symbol = symbol; self.subtitle = subtitle; self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: Space.m) {
            if let title { CardHeader(title: title, symbol: symbol, subtitle: subtitle) }
            content
        }
        .padding(Space.l)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: Radius.card))
        .overlay(RoundedRectangle(cornerRadius: Radius.card).strokeBorder(.separator.opacity(0.6)))
    }
}

// MARK: - Range bar

/// Where one value sits among an athlete's history: dots, interquartile band, target band, current mark.
struct RangeBarModel {
    let values: [Double]
    let current: Double?
    let target: ClosedRange<Double>?

    /// Everything that must be visible (values, current, target), padded 10 % of the span each side.
    var domain: ClosedRange<Double> {
        var points = values.filter(\.isFinite)
        if let current, current.isFinite { points.append(current) }
        if let target { points += [target.lowerBound, target.upperBound] }
        guard var lo = points.min(), var hi = points.max() else { return 0...1 }
        let minimumSpan = 1e-6 * max(abs(lo), abs(hi)) + 1e-3
        if hi - lo < minimumSpan {
            let mid = (lo + hi) / 2
            lo = mid - minimumSpan / 2; hi = mid + minimumSpan / 2
        }
        let pad = 0.1 * (hi - lo)
        return (lo - pad)...(hi + pad)
    }

    /// First and third quartile by linear interpolation (NumPy's default); nil below three values.
    var quartiles: (Double, Double)? {
        let sorted = values.filter(\.isFinite).sorted()
        guard sorted.count >= 3 else { return nil }
        func percentile(_ p: Double) -> Double {
            let position = p * Double(sorted.count - 1)
            let lower = Int(position.rounded(.down)), upper = min(lower + 1, sorted.count - 1)
            return sorted[lower] + (sorted[upper] - sorted[lower]) * (position - Double(lower))
        }
        return (percentile(0.25), percentile(0.75))
    }
}

struct RangeBar: View {
    let model: RangeBarModel
    init(model: RangeBarModel) { self.model = model }

    var body: some View {
        Canvas { context, size in
            let domain = model.domain
            let span = domain.upperBound - domain.lowerBound
            func x(_ value: Double) -> CGFloat { CGFloat((value - domain.lowerBound) / span) * size.width }
            let mid = size.height / 2
            context.fill(Path(roundedRect: CGRect(x: 0, y: mid - 1.5, width: size.width, height: 3), cornerRadius: 1.5),
                         with: .color(.secondary.opacity(0.18)))
            if let target = model.target {
                let rect = CGRect(x: x(target.lowerBound), y: 2, width: max(x(target.upperBound) - x(target.lowerBound), 2), height: size.height - 4)
                context.fill(Path(roundedRect: rect, cornerRadius: 3), with: .color(.green.opacity(0.18)))
                context.stroke(Path(roundedRect: rect, cornerRadius: 3), with: .color(.green.opacity(0.55)), lineWidth: 1)
            }
            if let (q1, q3) = model.quartiles {
                let rect = CGRect(x: x(q1), y: mid - 4, width: max(x(q3) - x(q1), 3), height: 8)
                context.fill(Path(roundedRect: rect, cornerRadius: 4), with: .color(athleteInk.opacity(0.35)))
            }
            for value in model.values where value.isFinite {
                context.fill(Path(ellipseIn: CGRect(x: x(value) - 2, y: mid - 2, width: 4, height: 4)), with: .color(.secondary.opacity(0.7)))
            }
            if let current = model.current, current.isFinite {
                let marker = CGRect(x: x(current) - 2, y: 1, width: 4, height: size.height - 2)
                context.fill(Path(roundedRect: marker, cornerRadius: 2), with: .color(.primary))
            }
        }
        .frame(height: 22)
        .accessibilityElement()
        .accessibilityLabel(accessibilityText)
    }

    private var accessibilityText: String {
        var parts: [String] = []
        if let current = model.current { parts.append("This throw \(number(current, digits: 2))") }
        if let (q1, q3) = model.quartiles { parts.append("usual range \(number(q1, digits: 2)) to \(number(q3, digits: 2))") }
        if let target = model.target { parts.append("target \(number(target.lowerBound, digits: 2)) to \(number(target.upperBound, digits: 2))") }
        parts.append("\(model.values.count) throws")
        return parts.joined(separator: ", ")
    }
}

// MARK: - Metric tile

/// Plus-or-minus next to a tile value: a standard error from the fit, or the metric's noise floor.
struct MetricUncertainty: Equatable {
    enum Kind: String { case standardError = "standard error", noiseFloor = "noise floor" }
    let value: Double
    let kind: Kind
}

/// Headline label, monospaced value with unit, reliability glyph, and the value against the athlete's history.
/// An unreliable value is withheld ("—") and its reason shown.
struct MetricTile: View {
    let row: CoachMetricRow
    let history: [Double]
    var target: ClosedRange<Double>? = nil
    var uncertainty: MetricUncertainty? = nil
    var seek: ((Int) -> Void)? = nil
    @State private var showsInfo = false

    init(row: CoachMetricRow, history: [Double], target: ClosedRange<Double>? = nil,
         uncertainty: MetricUncertainty? = nil, seek: ((Int) -> Void)? = nil) {
        self.row = row; self.history = history; self.target = target; self.uncertainty = uncertainty; self.seek = seek
    }

    var body: some View {
        VStack(alignment: .leading, spacing: Space.s) {
            HStack(alignment: .firstTextBaseline, spacing: Space.xs) {
                Text(row.label).font(.headline).lineLimit(2)
                Spacer(minLength: Space.xs)
                if isFlagged { ReliabilityGlyph(status: row.status).help(row.statusText) }
                Button { showsInfo.toggle() } label: { Image(systemName: "info.circle") }
                    .buttonStyle(.borderless).foregroundStyle(.secondary)
                    .help("About \(row.label.lowercased())")
                    .accessibilityLabel("About \(row.label)")
                    .popover(isPresented: $showsInfo, arrowEdge: .bottom) { info }
            }
            HStack(alignment: .firstTextBaseline, spacing: Space.xs) {
                // Degrees sit on the number (38°); other units follow as smaller secondary text.
                Text(value.map { number($0, digits: digits) + (row.unit == "°" ? "°" : "") } ?? "—").font(.title.monospacedDigit())
                if value != nil, !row.unit.isEmpty, row.unit != "°" { Text(row.unit).font(.callout).foregroundStyle(.secondary) }
                if value != nil, let uncertainty {
                    Text("± \(number(uncertainty.value, digits: uncertaintyDigits))").font(.callout.monospacedDigit())
                        .foregroundStyle(.secondary)
                        .help("± \(uncertainty.kind.rawValue)")
                }
            }
            if !history.isEmpty || target != nil {
                RangeBar(model: RangeBarModel(values: history, current: value, target: target))
            }
            if isFlagged {
                Text(row.reasons.first ?? row.statusText).font(.caption).foregroundStyle(.secondary).lineLimit(3)
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack {
                if let (q1, q3) = RangeBarModel(values: history, current: nil, target: nil).quartiles {
                    Text("Usual \(Self.range(q1, q3, digits: digits))").monospacedDigit()
                } else if value == nil && !isFlagged {
                    Text(row.statusText)
                }
                Spacer()
                if seek != nil, row.frame != nil {
                    // A hint, not a second control: the whole tile is the click target.
                    Label("Show in video", systemImage: "play.circle").labelStyle(.titleAndIcon)
                        .accessibilityHidden(true)
                }
            }
            .font(.caption).foregroundStyle(.secondary)
        }
        .padding(Space.m)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: Radius.card))
        .overlay(RoundedRectangle(cornerRadius: Radius.card).strokeBorder(.separator.opacity(0.6)))
        .contentShape(RoundedRectangle(cornerRadius: Radius.card))
        // Clicking anywhere on the tile shows its moment in the replay (spec §3.4).
        .onTapGesture { if let seek, let frame = row.frame { seek(frame) } }
        .accessibilityAction(named: "Show in video") { if let seek, let frame = row.frame { seek(frame) } }
        .help(row.frame != nil && seek != nil ? "\(row.definition)\nClick to show this moment in the replay." : row.definition)
    }

    private var info: some View {
        VStack(alignment: .leading, spacing: Space.s) {
            Text(row.label).font(.headline)
            Text(row.definition).fixedSize(horizontal: false, vertical: true)
            if let uncertainty {
                Text("± is the \(uncertainty.kind.rawValue): \(number(uncertainty.value, digits: uncertaintyDigits)) \(row.unit)")
                    .font(.callout).foregroundStyle(.secondary)
            }
            HStack(spacing: Space.xs) {
                ReliabilityGlyph(status: row.status)
                Text(row.statusText)
            }.font(.callout)
            ForEach(row.reasons, id: \.self) { Text($0).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true) }
        }
        .padding(Space.l)
        .frame(width: 300, alignment: .leading)
    }

    /// Only caution / unreliable measurements carry a glyph and a reason; reliable ones stay quiet.
    private var isFlagged: Bool { row.status == "caution" || row.status == "unreliable" }

    /// The value shown: withheld when the measurement failed its reliability rules.
    private var value: Double? { row.status == "unreliable" ? nil : row.value.flatMap { $0.isFinite ? $0 : nil } }

    private var digits: Int {
        guard let value else { return 1 }
        if row.unit == "m" { return 2 }   // centimetre resolution, as in the throw comparison table
        return abs(value) >= 100 ? 0 : abs(value) >= 10 || row.unit == "°" ? 0 : abs(value) >= 1 ? 1 : 2
    }
    /// The value's decimals for uncertainties of 1 or more; one decimal more (at most two) below 1.
    private var uncertaintyDigits: Int {
        guard let u = uncertainty?.value, u < 1 else { return digits }
        return digits > 0 ? min(digits + 1, 2) : 1
    }

    /// "150–158", or "−59 to −54" when a bound is negative (a dash between negatives misreads).
    static func range(_ low: Double, _ high: Double, digits: Int) -> String {
        let a = number(low, digits: digits), b = number(high, digits: digits)
        return low < 0 || high < 0 ? "\(a) to \(b)" : "\(a)–\(b)"
    }
}

/// Reliability status always carries a glyph as well as a colour.
struct ReliabilityGlyph: View {
    let status: String
    var body: some View {
        let (symbol, color): (String, Color) = switch status {
        case "reliable": ("checkmark.circle.fill", .green)
        case "caution": ("exclamationmark.triangle.fill", .orange)
        case "unreliable": ("xmark.octagon.fill", .red)
        default: ("minus.circle", .secondary)
        }
        Image(systemName: symbol).foregroundStyle(color).accessibilityLabel(status.isEmpty ? "Not measured" : status.capitalized)
    }
}

// MARK: - Result badge

/// Observed result of a throw: Hole / Board / Miss, or an em dash when not recorded.
struct ResultBadge: View {
    let score: ScoreCategory?
    init(score: ScoreCategory?) { self.score = score }

    var body: some View {
        let (text, symbol, color): (String, String, Color) = switch score {
        case .throughHole: ("Hole", "circle.inset.filled", scoredInk)
        case .onBoard: ("Board", "square.fill", scoredInk)
        case .offBoard: ("Miss", "xmark", missInk)
        case nil: ("—", "", Color.secondary)
        }
        HStack(spacing: Space.xs) {
            if !symbol.isEmpty { Image(systemName: symbol).imageScale(.small) }
            Text(text)
        }
        .font(.caption.weight(.semibold))
        .padding(.horizontal, 7).padding(.vertical, 2)
        .foregroundStyle(color)
        .background(color.opacity(score == nil ? 0.08 : 0.15), in: Capsule())
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(score == nil ? "No result recorded" : "Result: \(text)")
    }
}

// MARK: - Empty state

struct EmptyState: View {
    let title: String
    let symbol: String
    let message: String
    let action: (label: String, run: () -> Void)?

    init(_ title: String, symbol: String, message: String, action: (label: String, run: () -> Void)? = nil) {
        self.title = title; self.symbol = symbol; self.message = message; self.action = action
    }

    var body: some View {
        ContentUnavailableView {
            Label(title, systemImage: symbol)
        } description: {
            Text(message)
        } actions: {
            if let action { Button(action.label, action: action.run).buttonStyle(.borderedProminent) }
        }
    }
}
