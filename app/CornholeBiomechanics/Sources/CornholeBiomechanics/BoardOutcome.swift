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
    }
    struct End: Decodable, Equatable {
        /// "rest", "fell_in_hole", "left_deck", "lost", "moving_at_clip_end" or "never_on_deck".
        var kind: String; var frame: Int?; var u_in: Double?; var v_in: Double?; var from_hole_in: Double?; var note: String?
    }
    struct Slide: Decodable, Equatable {
        var distance_in: Double?; var duration_s: Double?; var entry_speed_m_s: Double?
        var deceleration_m_s2: Double?; var mu_effective: Double?; var state: String?; var reason: String?
    }
    struct Hang: Decodable, Equatable { var seconds: Double }
    struct Suggestion: Decodable, Equatable { var score: Int?; var basis: String; var confidence: String? }
    struct PathPoint: Decodable, Equatable { var frame: Int; var u_in: Double?; var v_in: Double? }
    struct Lateral: Decodable, Equatable { var state: String?; var note: String? }

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

    /// board_phase from results.json, when it was measured.
    static func load(results: URL?) -> BoardPhase? {
        guard let results, let data = try? Data(contentsOf: results) else { return nil }
        struct Wrapper: Decodable { var board_phase: BoardPhase? }
        guard let phase = try? JSONDecoder().decode(Wrapper.self, from: data).board_phase, phase.status == "measured" else { return nil }
        return phase
    }

    /// "9 in short of the hole", "at the hole", "3 in past the hole".
    static func whereText(_ fromHole: Double) -> String {
        if abs(fromHole) <= 3 { return "at the hole" }
        return "\(number(abs(fromHole), digits: 0)) in \(fromHole > 0 ? "past" : "short of") the hole"
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
            parts.append("stopped \(end.from_hole_in.map(Self.whereText) ?? "on the board")")
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
            BoardTopView(phase: phase).frame(height: 150)
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

/// The deck from above, front edge at the left: hole, landing (●), slide (line) and end (■ rest, ◎ into the hole).
/// Left/right comes from a side camera and is only approximate, so points are drawn on the centreline.
struct BoardTopView: View {
    let phase: BoardPhase
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        Canvas { context, size in
            let margin: CGFloat = 16
            let length = size.width - 2 * margin
            let width = min(size.height - 2 * margin - 14, length / 2)
            let origin = CGPoint(x: margin, y: (size.height - width) / 2 - 6)
            func point(_ v: Double) -> CGPoint {
                CGPoint(x: origin.x + CGFloat(min(max(v, -4), 52) / 48) * length, y: origin.y + width / 2)
            }
            let deck = CGRect(x: origin.x, y: origin.y, width: length, height: width)
            context.fill(Path(roundedRect: deck, cornerRadius: 3), with: .color(Color.red.opacity(colorScheme == .dark ? 0.30 : 0.18)))
            context.stroke(Path(roundedRect: deck, cornerRadius: 3), with: .color(.primary.opacity(0.5)), lineWidth: 1.5)
            let holeCentre = CGPoint(x: origin.x + CGFloat(39.0 / 48) * length, y: origin.y + width / 2)
            let r = CGFloat(3.0 / 48) * length
            context.fill(Path(ellipseIn: CGRect(x: holeCentre.x - r, y: holeCentre.y - r, width: 2 * r, height: 2 * r)),
                         with: .color(.primary.opacity(0.85)))
            context.draw(Text("Front").font(.caption2).foregroundStyle(.secondary), at: CGPoint(x: deck.minX, y: deck.maxY + 3), anchor: .topLeading)
            context.draw(Text("Back").font(.caption2).foregroundStyle(.secondary), at: CGPoint(x: deck.maxX, y: deck.maxY + 3), anchor: .topTrailing)
            context.draw(Text("Hole").font(.caption2).foregroundStyle(.secondary), at: CGPoint(x: holeCentre.x, y: deck.minY - 2), anchor: .bottom)
            guard let touchdown = phase.touchdown else { return }
            let start = point(touchdown.v_in)
            let ink = Color.accentColor
            if let end = phase.end, let v = end.v_in {
                let stop = point(v)
                var slide = Path(); slide.move(to: start); slide.addLine(to: stop)
                context.stroke(slide, with: .color(ink), style: StrokeStyle(lineWidth: 3, lineCap: .round))
                switch end.kind {
                case "fell_in_hole":
                    for radius in [7.0, 3.0] as [CGFloat] {
                        context.stroke(Path(ellipseIn: CGRect(x: stop.x - radius, y: stop.y - radius, width: 2 * radius, height: 2 * radius)),
                                       with: .color(.green), lineWidth: 2.5)
                    }
                case "rest":
                    let side: CGFloat = 12
                    let square = Path(roundedRect: CGRect(x: stop.x - side / 2, y: stop.y - side / 2, width: side, height: side), cornerRadius: 2)
                    context.fill(square, with: .color(ink)); context.stroke(square, with: .color(.white.opacity(0.9)), lineWidth: 1.5)
                default:
                    context.draw(Text("?").font(.headline).foregroundStyle(ink), at: stop)
                }
            }
            let dot = Path(ellipseIn: CGRect(x: start.x - 6, y: start.y - 6, width: 12, height: 12))
            context.fill(dot, with: .color(.white)); context.stroke(dot, with: .color(ink), lineWidth: 2.5)
            context.draw(Text("Landed").font(.caption2.weight(.semibold)), at: CGPoint(x: start.x, y: start.y + 9), anchor: .top)
        }
        .accessibilityElement()
        .accessibilityLabel("Board seen from above")
        .accessibilityValue(phase.sentence)
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
