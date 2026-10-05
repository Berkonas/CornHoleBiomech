import AVKit
import SwiftUI

// Where the throw ended (python `board_phase.py`): touchdown, slide, rest or drop into the hole,
// the slide physics, and the suggested result. Also the athlete's personal green zone
// (python `zones.personal_zone`) and a quick "watch this throw" sheet.

// MARK: - Models

/// results.json → board_phase. Deck coordinates are inches: v up the deck from the front edge
/// (0–48, hole centre 39), u across (0–24, hole 12; approximate from a side camera).
struct BoardPhase: Decodable, Equatable {
    struct Touchdown: Decodable, Equatable {
        var frame: Int; var u_in: Double; var v_in: Double; var from_hole_in: Double; var on_deck: Bool?; var basis: String?
        /// Across the board from its centreline, inches; + = the thrower's right (approximate, side camera).
        var right_of_centre_in: Double?
    }
    struct End: Decodable, Equatable {
        /// "rest", "fell_in_hole", "left_deck", "lost", "moving_at_clip_end" or "never_on_deck".
        var kind: String; var frame: Int?; var u_in: Double?; var v_in: Double?; var from_hole_in: Double?; var note: String?
        var right_of_centre_in: Double?
    }
    struct Slide: Decodable, Equatable {
        var distance_in: Double?; var duration_s: Double?; var entry_speed_m_s: Double?
        var deceleration_m_s2: Double?; var mu_effective: Double?; var state: String?; var reason: String?
    }
    struct Hang: Decodable, Equatable { var seconds: Double }
    struct Suggestion: Decodable, Equatable { var score: Int?; var basis: String; var confidence: String? }
    struct PathPoint: Decodable, Equatable { var frame: Int; var u_in: Double?; var v_in: Double?; var right_of_centre_in: Double? }
    struct Lateral: Decodable, Equatable { var state: String?; var note: String?; var precision_in: Double? }

    var status: String
    var touchdown: Touchdown?
    var end: End?
    var slide: Slide?
    var hang: Hang?
    var suggested_outcome: Suggestion?
    var path: [PathPoint]?
    var lateral: Lateral?
    var flight_accepted: Bool?

    var suggestedScore: ScoreCategory? { suggested_outcome?.score.flatMap(ScoreCategory.init(rawValue:)) }

    /// The board phase for a throw: from two_view.json when the front camera measured it (left/right and how
    /// it ended measured by the front camera, along the deck by the side camera), else from results.json.
    static func load(results: URL?) -> BoardPhase? {
        guard let results else { return nil }
        struct Wrapper: Decodable { var board_phase: BoardPhase? }
        let twoView = results.deletingLastPathComponent().appendingPathComponent("two_view.json")
        if let data = try? Data(contentsOf: twoView),
           let phase = try? JSONDecoder().decode(Wrapper.self, from: data).board_phase, phase.status == "measured" {
            return phase
        }
        guard let data = try? Data(contentsOf: results),
              let phase = try? JSONDecoder().decode(Wrapper.self, from: data).board_phase, phase.status == "measured" else { return nil }
        return phase
    }

    /// Left/right came from the front camera (precise) rather than the side camera (± 3 in).
    var leftRightFromFrontCamera: Bool { lateral?.state == "front_camera" }

    /// "9 in short of the hole", "at the hole", "3 in past the hole".
    static func whereText(_ fromHole: Double) -> String {
        if abs(fromHole) <= 3 { return "at the hole" }
        return "\(number(abs(fromHole), digits: 0)) in \(fromHole > 0 ? "past" : "short of") the hole"
    }

    /// Left/right was measured (analyses from before 0.6.2 put every bag on the centreline).
    var measuresLeftRight: Bool { end?.right_of_centre_in != nil || touchdown?.right_of_centre_in != nil }

    /// Left/right is resolved to about this many inches: ± 3 in from a side camera, under 1 in from the front camera.
    var lateralPrecision: Double { leftRightFromFrontCamera ? max(0.5, lateral?.precision_in ?? 0.5) : max(3, lateral?.precision_in ?? 3) }

    /// "4 in to the thrower's right", or nil when within the side camera's precision of the centreline.
    static func sideText(_ right: Double?, precision: Double = 3) -> String? {
        guard let right, abs(right) > precision else { return nil }
        return "\(number(abs(right), digits: 0)) in to the thrower's \(right > 0 ? "right" : "left")"
    }

    /// One plain sentence: landed → slid → ended.
    var sentence: String {
        guard let touchdown, let end else { return "Where the bag ended was not measured." }
        var parts = ["Landed \(Self.whereText(touchdown.from_hole_in))"]
        if let slide = slide?.distance_in, abs(slide) >= 2 { parts.append("slid \(number(abs(slide), digits: 0)) in") }
        switch end.kind {
        case "fell_in_hole":
            parts.append(hang.map { "hung on the lip for \(number($0.seconds, digits: 1)) s and dropped in" } ?? "went into the hole")
        case "rest":
            var stopped = "stopped \(end.from_hole_in.map(Self.whereText) ?? "on the board")"
            if let side = Self.sideText(end.right_of_centre_in, precision: lateralPrecision) { stopped += " and \(side)" }
            parts.append(stopped)
        case "left_deck": parts.append("left the board")
        case "moving_at_clip_end": parts.append("was still moving when the clip ended")
        default: parts.append("was then lost from view")
        }
        return parts.joined(separator: ", ") + "."
    }
}

/// dashboards/<athlete>.json → personal_zone (python `zones.personal_zone`).
struct PersonalZone: Decodable, Equatable {
    struct Aim: Decodable, Equatable { var speed_m_s: Double; var angle_deg: Double; var p_green: Double; var speed_window_m_s: [Double]? }
    var status: String
    var message: String?
    var height_m: Double?
    var distance_m: Double
    var distance_source: String
    var regulation_distance_m: Double?
    var slide_allowance_m: Double
    var slide_source: String
    var slides_measured: Int?
    var sd_speed_m_s: Double?
    var sd_angle_deg: Double?
    var current: Aim?
    var best: Aim?
    var throws_in_green: Int?
    var n: Int?
    var sentence: String?

    /// Launch parameters for this athlete's own green zone at the given aim.
    func parameters(speed: Double? = nil, angle: Double? = nil) -> LaunchParameters? {
        guard let height = height_m else { return nil }
        return LaunchParameters(speed: speed ?? current?.speed_m_s ?? 7, angleDegrees: angle ?? current?.angle_deg ?? 35,
                                releaseHeight: height, distanceToBoard: distance_m, slideAllowance: slide_allowance_m)
    }
}

extension AthleteDashboard {
    struct DistanceInfo: Decodable, Equatable {
        var release_to_board_m: Double; var source: String; var n_measured: Int?; var regulation_release_to_board_m: Double?; var note: String?
    }
    struct LateralInfo: Decodable, Equatable { var measured: Bool; var note: String }
    struct Exclusion: Decodable, Identifiable, Equatable { var trial_id: String; var label: String; var reason: String; var id: String { trial_id } }
    struct Cohort: Decodable, Equatable { var included: [String]; var excluded: [Exclusion] }
}

// MARK: - Where it ended

/// Top view of the board (front at the left, like the side view) with the landing, the slide and the end,
/// the plain sentence, the slide physics and the suggested result with a one-click "use this result".
struct WhereItEndedCard: View {
    let phase: BoardPhase
    let recorded: ScoreCategory?
    var canEdit = true
    var accept: (ScoreCategory) -> Void = { _ in }
    var seek: (Int) -> Void = { _ in }

    var body: some View {
        Card("Where it ended", symbol: "flag.checkered",
             subtitle: "Tracked on the board after landing: touchdown, slide, and where the bag stopped or dropped in.") {
            Text(phase.sentence).font(.title3.weight(.semibold)).fixedSize(horizontal: false, vertical: true)
            BoardTopView(phase: phase).frame(height: 190)
            HStack(spacing: Space.l) {
                if let touchdown = phase.touchdown {
                    Button("Show landing", systemImage: "play.circle") { seek(touchdown.frame) }.buttonStyle(.link)
                }
                if let frame = phase.end?.frame {
                    Button(phase.end?.kind == "fell_in_hole" ? "Show drop" : "Show the end", systemImage: "play.circle") { seek(frame) }
                        .buttonStyle(.link)
                }
            }
            .font(.callout)
            slidePhysics
            suggestion
            if let note = phase.lateral?.note {
                Text(note).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    @ViewBuilder private var slidePhysics: some View {
        if let slide = phase.slide, slide.distance_in != nil {
            Grid(alignment: .leading, horizontalSpacing: Space.xl, verticalSpacing: Space.xs) {
                GridRow {
                    Text("Slide").foregroundStyle(.secondary)
                    Text("\(number(slide.distance_in, digits: 0)) in in \(number(slide.duration_s, digits: 2)) s")
                }
                if let v0 = slide.entry_speed_m_s {
                    GridRow { Text("Speed along the board at touchdown").foregroundStyle(.secondary); Text("\(number(v0, digits: 1)) m/s") }
                }
                if let a = slide.deceleration_m_s2 {
                    GridRow { Text("Slow-down on the board").foregroundStyle(.secondary); Text("\(number(a, digits: 1)) m/s²") }
                }
                if let mu = slide.mu_effective {
                    GridRow {
                        Text("Board friction (effective μ)").foregroundStyle(.secondary)
                        Text(number(mu, digits: 2)).help("From a = g (sin α + μ cos α) for a bag sliding up the 10.8° deck, fitted to the measured slide.")
                    }
                }
            }
            .font(.callout).monospacedDigit()
            if slide.mu_effective == nil, let reason = slide.reason {
                Text(reason).font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    @ViewBuilder private var suggestion: some View {
        if let suggested = phase.suggestedScore {
            HStack(spacing: Space.m) {
                Image(systemName: "wand.and.stars").foregroundStyle(.secondary).accessibilityHidden(true)
                Text("From the video: ").foregroundStyle(.secondary) + Text(Self.label(suggested)).bold()
                    + Text(phase.suggested_outcome?.confidence == "high" ? "" : " (check the video)").foregroundStyle(.secondary)
                Spacer(minLength: Space.m)
                if recorded == suggested {
                    Label("Matches the recorded result", systemImage: "checkmark.circle.fill").foregroundStyle(.green).font(.callout)
                } else {
                    Button(recorded == nil ? "Use This Result" : "Change to \(Self.label(suggested))") { accept(suggested) }
                        .disabled(!canEdit)
                        .help("Record this result for the throw (one click; you can change it any time)")
                }
            }
            .font(.callout)
        }
    }

    static func label(_ score: ScoreCategory) -> String {
        switch score {
        case .throughHole: "Hole · 3"
        case .onBoard: "Board · 1"
        case .offBoard: "Miss · 0"
        }
    }
}

/// The deck drawn to scale from above, as the thrower sees it walking up: front edge at the left, back at the
/// right, the thrower's left at the top and right at the bottom. Room is left around the deck so bags that
/// stopped just off the board still show.
struct DeckLayout {
    /// Inches shown beyond each end and each side of the 48 × 24 in deck.
    static let apron: CGFloat = 7
    let deck: CGRect
    let ppi: CGFloat

    init(size: CGSize, labelRow: CGFloat = 16) {
        let span = CGSize(width: 48 + 2 * Self.apron, height: 24 + 2 * Self.apron)
        ppi = max(0.5, min(size.width / span.width, (size.height - 2 * labelRow) / span.height))
        deck = CGRect(x: (size.width - 48 * ppi) / 2, y: (size.height - 24 * ppi) / 2, width: 48 * ppi, height: 24 * ppi)
    }

    /// Screen point of v inches up the deck and `right` inches to the thrower's right of the centreline.
    func point(v: Double, right: Double?) -> CGPoint {
        let a = Double(Self.apron)
        let vv = min(max(v, -a), 48 + a), rr = min(max(right ?? 0, -12 - a), 12 + a)
        return CGPoint(x: deck.minX + CGFloat(vv) * ppi, y: deck.midY + CGFloat(rr) * ppi)
    }

    var hole: CGPoint { point(v: 39, right: 0) }

    /// The board, hole and edge labels.
    func drawBoard(_ context: GraphicsContext, dark: Bool) {
        context.fill(Path(roundedRect: deck, cornerRadius: 3), with: .color(Color.red.opacity(dark ? 0.30 : 0.16)))
        context.stroke(Path(roundedRect: deck, cornerRadius: 3), with: .color(.primary.opacity(0.5)), lineWidth: 1.5)
        var centre = Path(); centre.move(to: CGPoint(x: deck.minX, y: deck.midY)); centre.addLine(to: CGPoint(x: deck.maxX, y: deck.midY))
        context.stroke(centre, with: .color(.primary.opacity(0.18)), style: StrokeStyle(lineWidth: 1, dash: [4, 4]))
        let r = 3 * ppi
        context.fill(Path(ellipseIn: CGRect(x: hole.x - r, y: hole.y - r, width: 2 * r, height: 2 * r)), with: .color(.primary.opacity(0.85)))
        let caption = { (text: String) in Text(text).font(.caption2).foregroundStyle(.secondary) }
        context.draw(caption("Thrower's left"), at: CGPoint(x: deck.minX, y: deck.minY - 3), anchor: .bottomLeading)
        context.draw(caption("Hole"), at: CGPoint(x: hole.x, y: deck.minY - 3), anchor: .bottom)
        context.draw(caption("Front"), at: CGPoint(x: deck.minX, y: deck.maxY + 3), anchor: .topLeading)
        context.draw(caption("Thrower's right"), at: CGPoint(x: deck.midX - 4 * ppi, y: deck.maxY + 3), anchor: .top)
        context.draw(caption("Back"), at: CGPoint(x: deck.maxX, y: deck.maxY + 3), anchor: .topTrailing)
    }

    /// A 6 × 6 in bag at `centre`.
    func bag(at centre: CGPoint) -> Path {
        let side = 6 * ppi
        return Path(roundedRect: CGRect(x: centre.x - side / 2, y: centre.y - side / 2, width: side, height: side), cornerRadius: side * 0.18)
    }
}

/// One throw on the board from above: landing (●), the tracked slide, and where it ended (the bag, drawn to size,
/// or ◎ into the hole). Left/right comes from a side camera and is approximate: the faint bar shows its ± range.
struct BoardTopView: View {
    let phase: BoardPhase
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        Canvas { context, size in
            let layout = DeckLayout(size: size)
            layout.drawBoard(context, dark: colorScheme == .dark)
            guard let touchdown = phase.touchdown else { return }
            let ink = Color.accentColor
            let start = layout.point(v: touchdown.v_in, right: touchdown.right_of_centre_in)
            var slide = Path(); slide.move(to: start)
            for p in phase.path ?? [] {
                guard let v = p.v_in, p.frame >= touchdown.frame, p.frame <= (phase.end?.frame ?? .max) else { continue }
                slide.addLine(to: layout.point(v: v, right: p.right_of_centre_in ?? touchdown.right_of_centre_in))
            }
            if let end = phase.end, let v = end.v_in {
                let stop = layout.point(v: v, right: end.right_of_centre_in)
                slide.addLine(to: stop)
                context.stroke(slide, with: .color(ink.opacity(0.85)), style: StrokeStyle(lineWidth: 2.5, lineCap: .round, lineJoin: .round))
                if phase.measuresLeftRight {
                    // Side-camera left/right uncertainty.
                    let half = CGFloat(phase.lateralPrecision) * layout.ppi
                    var bar = Path(); bar.move(to: CGPoint(x: stop.x, y: stop.y - half)); bar.addLine(to: CGPoint(x: stop.x, y: stop.y + half))
                    context.stroke(bar, with: .color(ink.opacity(0.35)), style: StrokeStyle(lineWidth: 6, lineCap: .round))
                }
                switch end.kind {
                case "fell_in_hole":
                    for radius in [7.0, 3.0] as [CGFloat] {
                        context.stroke(Path(ellipseIn: CGRect(x: stop.x - radius, y: stop.y - radius, width: 2 * radius, height: 2 * radius)),
                                       with: .color(.green), lineWidth: 2.5)
                    }
                case "rest", "left_deck", "lost", "moving_at_clip_end":
                    let bag = layout.bag(at: stop)
                    context.fill(bag, with: .color(ink.opacity(end.kind == "rest" ? 0.9 : 0.35)))
                    context.stroke(bag, with: .color(.white.opacity(0.9)), lineWidth: 1.5)
                    if end.kind != "rest" { context.draw(Text("?").font(.headline).foregroundStyle(.white), at: stop) }
                default:
                    context.draw(Text("?").font(.headline).foregroundStyle(ink), at: stop)
                }
            }
            let dot = Path(ellipseIn: CGRect(x: start.x - 5, y: start.y - 5, width: 10, height: 10))
            context.fill(dot, with: .color(.white)); context.stroke(dot, with: .color(ink), lineWidth: 2.5)
            context.draw(Text("Landed").font(.caption2.weight(.semibold)), at: CGPoint(x: start.x, y: start.y - 8), anchor: .bottom)
        }
        .accessibilityElement()
        .accessibilityLabel("Board seen from above")
        .accessibilityValue(phase.sentence)
    }
}

/// Where one throw ended, for the athlete's board map.
struct BoardEndMark: Identifiable, Equatable, Sendable {
    var id: UUID
    var number: Int
    var label: String
    /// Inches up the deck from the front edge (hole centre 39) and to the thrower's right of the centreline.
    var v: Double
    var right: Double?
    /// "rest", "fell_in_hole", "left_deck", …
    var kind: String
    var score: ScoreCategory?
}

/// Every throw's end on one board: bags drawn to size and coloured by the recorded result, numbered like the
/// throw table. Click a bag to watch that throw.
struct BoardEndsMap: View {
    let marks: [BoardEndMark]
    var select: ((UUID) -> Void)? = nil
    @Environment(\.colorScheme) private var colorScheme

    static func color(_ score: ScoreCategory?) -> Color {
        switch score {
        case .throughHole: Color(red: 0.1, green: 0.62, blue: 0.25)
        case .onBoard: scoredInk
        case .offBoard: missInk
        case nil: Color.gray
        }
    }

    var body: some View {
        GeometryReader { geometry in
            let layout = DeckLayout(size: geometry.size)
            ZStack(alignment: .topLeading) {
                Canvas { context, _ in
                    layout.drawBoard(context, dark: colorScheme == .dark)
                    for mark in marks {
                        let p = layout.point(v: mark.v, right: mark.right)
                        let color = Self.color(mark.score)
                        if mark.kind == "fell_in_hole" {
                            let r = 2.4 * layout.ppi
                            context.stroke(Path(ellipseIn: CGRect(x: p.x - r, y: p.y - r, width: 2 * r, height: 2 * r)), with: .color(color), lineWidth: 2.5)
                        } else {
                            let bag = layout.bag(at: p)
                            context.fill(bag, with: .color(color.opacity(0.72)))
                            context.stroke(bag, with: .color(.white.opacity(0.9)), lineWidth: 1)
                        }
                        context.draw(Text("\(mark.number)").font(.system(size: max(8, min(11, 3 * layout.ppi)), weight: .bold))
                                        .foregroundStyle(mark.kind == "fell_in_hole" ? color : .white), at: p)
                    }
                }
                if let select {
                    ForEach(marks) { mark in
                        let p = layout.point(v: mark.v, right: mark.right)
                        Button { select(mark.id) } label: { Color.clear.frame(width: max(14, 6 * layout.ppi), height: max(14, 6 * layout.ppi)).contentShape(Rectangle()) }
                            .buttonStyle(.plain)
                            .position(p)
                            .help("\(mark.label): click to watch")
                            .accessibilityLabel("Watch \(mark.label)")
                    }
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Where each bag ended on the board")
    }
}

/// The athlete's board map card, with the spread of where bags ended.
struct BoardEndsCard: View {
    let marks: [BoardEndMark]
    /// Throws analyzed with a version that did not measure left/right (drawn on the centreline).
    var centredCount = 0
    /// Throws whose left/right came from the front camera.
    var frontMeasured = 0
    var select: ((UUID) -> Void)? = nil

    var body: some View {
        Card("Where the bags ended", symbol: "square.grid.3x3.topleft.filled",
             subtitle: "Each analyzed throw on the board, seen from above, coloured by its recorded result.") {
            BoardEndsMap(marks: marks, select: select).frame(height: 240)
            HStack(spacing: Space.l) {
                legend(.throughHole, "Hole"); legend(.onBoard, "Board"); legend(.offBoard, "Miss"); legend(nil, "No result yet")
            }
            .font(.caption)
            if let spread { Text(spread).font(.callout).monospacedDigit().fixedSize(horizontal: false, vertical: true) }
            Text(caption).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }
    }

    private func legend(_ score: ScoreCategory?, _ text: String) -> some View {
        HStack(spacing: 5) {
            RoundedRectangle(cornerRadius: 2).fill(BoardEndsMap.color(score).opacity(0.8)).frame(width: 10, height: 10)
            Text(text).foregroundStyle(.secondary)
        }
    }

    /// "Stopped on average 6 in short and 2 in right of the hole; spread ± 9 in along, ± 5 in across (SD)."
    private var spread: String? {
        let stopped = marks.filter { $0.kind == "rest" }
        guard stopped.count >= 2, let along = MedianSD.of(stopped.map { $0.v - 39 }) else { return nil }
        var text = "Bags that stopped on the board: typically \(BoardPhase.whereText(along.median))"
        let rights = stopped.compactMap(\.right)
        if rights.count >= 2, let across = MedianSD.of(rights) {
            if let side = BoardPhase.sideText(across.median) { text += ", \(side)" }
            text += "; spread ± \(number(along.sd, digits: 0)) in along the board and ± \(number(across.sd, digits: 0)) in left/right (SD)."
        } else {
            text += "; spread ± \(number(along.sd, digits: 0)) in along the board (SD)."
        }
        return text
    }

    private var caption: String {
        var parts = [frontMeasured > 0
            ? "Bags are drawn to size (6 in). Left/right is measured by the front camera (under 1 in); along the board by the side camera (about ± 3 in)."
            : "Bags are drawn to size (6 in). Along the board is measured to about ± 3 in; left/right from the side camera is approximate (about ± 3 in)."]
        if centredCount > 0 {
            parts.append("\(centredCount) \(centredCount == 1 ? "throw was" : "throws were") analyzed before left/right was measured and \(centredCount == 1 ? "is" : "are") drawn on the centreline: re-analyze to place \(centredCount == 1 ? "it" : "them").")
        }
        if select != nil { parts.append("Click a bag to watch that throw.") }
        return parts.joined(separator: " ")
    }
}

// MARK: - Personal green zone

/// The athlete's own green zone on the release map: their height, measured distance and slide, with the
/// best aim for their consistency and (optionally) one throw highlighted. Clicking a throw opens it.
struct PersonalZoneCard: View {
    let zone: PersonalZone
    let releases: [MeasuredRelease]
    var highlight: UUID? = nil
    var distanceNote: String? = nil
    var lateralNote: String? = nil
    var select: ((UUID) -> Void)? = nil

    var body: some View {
        Card(highlight == nil ? "Green zone" : "This throw on the green zone", symbol: "scope",
             subtitle: subtitle) {
            if zone.status == "available", let params = zone.parameters() {
                if let sentence = zone.sentence {
                    Text(sentence).font(.headline).fixedSize(horizontal: false, vertical: true)
                }
                SuccessMap(params: .constant(params), throws: releases, interactive: false, highlight: highlight,
                           bestAim: zone.best.map { (speed: $0.speed_m_s, angle: $0.angle_deg) }, onSelectThrow: select)
                facts
                Text(caption).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            } else {
                Label(zone.message ?? "The green zone appears once a few throws have release speed, angle and height.",
                      systemImage: "info.circle").foregroundStyle(.secondary)
            }
        }
    }

    private var subtitle: String {
        "Release speed × angle that reach the hole window for this athlete: their release height, distance and slide."
    }

    private var facts: some View {
        Grid(alignment: .leading, horizontalSpacing: Space.xl, verticalSpacing: Space.xs) {
            if let current = zone.current {
                GridRow {
                    Text("Usual release").foregroundStyle(.secondary)
                    Text("\(number(current.angle_deg, digits: 0))° at \(number(current.speed_m_s, digits: 1)) m/s · \(number(100 * current.p_green, digits: 0))% model chance of the hole window")
                }
            }
            if let best = zone.best {
                GridRow {
                    Text("Best aim").foregroundStyle(.secondary)
                    Text("\(number(best.angle_deg, digits: 0))° at \(number(best.speed_m_s, digits: 1)) m/s · \(number(100 * best.p_green, digits: 0))%")
                }
            }
            if let sdV = zone.sd_speed_m_s, let sdA = zone.sd_angle_deg {
                GridRow { Text("Throw-to-throw spread").foregroundStyle(.secondary); Text("± \(number(sdV, digits: 2)) m/s, ± \(number(sdA, digits: 1))° (SD)") }
            }
            GridRow {
                Text("Built for").foregroundStyle(.secondary)
                Text("release height \(number(zone.height_m, digits: 2)) m · \(number(zone.distance_m, digits: 2)) m to the board (\(zone.distance_source == "measured_median" ? "measured" : "Settings")) · slide \(number(zone.slide_allowance_m * 39.37, digits: 0)) in (\(zone.slide_source == "assumed" ? "assumed" : "measured"))")
            }
        }
        .font(.callout).monospacedDigit()
    }

    private var caption: String {
        var parts = ["Green = first contact in the hole window: from one typical slide short of the hole to its far edge. The target marks the aim with the best chance for this athlete's spread; the model ignores air drag, bounce and left/right."]
        if let distanceNote { parts.append(distanceNote) }
        if let lateralNote { parts.append(lateralNote) }
        if select != nil { parts.append("Click a throw's mark to watch it.") }
        return parts.joined(separator: " ")
    }
}

// MARK: - Watch a throw

/// A throw's video in a sheet, from the athlete summary, with a link to its full report.
struct ThrowVideoSheet: View {
    let title: String
    let videoURL: URL?
    let score: ScoreCategory?
    let phase: BoardPhase?
    let openReport: () -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var player: AVPlayer?

    var body: some View {
        VStack(alignment: .leading, spacing: Space.m) {
            HStack {
                Text(title).font(.title2.weight(.semibold))
                ResultBadge(score: score)
                Spacer()
                Button("Open Full Report") { dismiss(); openReport() }
                Button("Done") { dismiss() }.keyboardShortcut(.defaultAction)
            }
            if let player {
                NativeVideoPlayer(player: player).frame(minWidth: 720, minHeight: 405)
                    .clipShape(RoundedRectangle(cornerRadius: Radius.card))
            } else {
                Label("The video for this throw could not be found.", systemImage: "video.slash").foregroundStyle(.secondary)
                    .frame(minWidth: 720, minHeight: 200)
            }
            if let phase { Text(phase.sentence).font(.callout) }
        }
        .padding(Space.xl)
        .onAppear {
            guard let videoURL else { return }
            let next = AVPlayer(url: videoURL)
            player = next
            next.play()
        }
        .onDisappear { player?.pause() }
    }
}
