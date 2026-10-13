import SwiftUI

// The single-throw "why it missed" view: this throw only (no other throws, no usual group), the distance error as the
// side camera sees it and the left/right error as the front camera sees it, the one or two reasons that account for
// the miss, and what to change. Numbers are this throw's measured landing (two_view.json → landing, board inches:
// x across 0–24 with the hole at 12, y up the deck from the front edge with the hole at 39) and its launch direction.

/// What happened to one bag, split into the flight (where it first touched) and the slide (what happened after), on
/// each axis. Pure data so the wording rules can be tested.
struct MissStory: Equatable {
    static let holeX = 12.0, holeY = 39.0, holeRadius = 3.0

    enum Part: String { case flightDistance, slideDistance, aim, sideSlide }

    struct Reason: Equatable {
        var part: Part
        var inches: Double
        var why: String
        var fix: String
    }

    var made: Bool
    var offBoard: Bool
    /// First contact and rest in board inches (nil when not measured).
    var contact: (x: Double, y: Double)?
    var rest: (x: Double, y: Double)?
    /// Launch direction relative to the line from the release to the hole (°, + = right), when measured.
    var launchVsHoleDeg: Double?
    var headline: String
    var reasons: [Reason]
    /// Where the bag would have had to land (same slide, moved by the miss) to finish in the hole; nil when unknown.
    var target: (x: Double, y: Double)? = nil

    static func == (a: MissStory, b: MissStory) -> Bool {
        a.made == b.made && a.offBoard == b.offBoard && a.headline == b.headline && a.reasons == b.reasons
            && a.contact?.x == b.contact?.x && a.contact?.y == b.contact?.y && a.rest?.x == b.rest?.x && a.rest?.y == b.rest?.y
    }

    /// Short (−) / long (+) and left (−) / right (+) of the hole where the bag stopped.
    var missAlong: Double? { rest.map { $0.y - Self.holeY } }
    var missAcross: Double? { rest.map { $0.x - Self.holeX } }

    init(contact: (x: Double, y: Double)?, rest: (x: Double, y: Double)?, made: Bool, offBoard: Bool,
         launchVsHoleDeg: Double?) {
        self.made = made
        self.offBoard = offBoard
        self.contact = contact
        self.rest = rest
        self.launchVsHoleDeg = launchVsHoleDeg
        if made {
            headline = "In the hole"
            reasons = []
            return
        }
        guard let rest else {
            headline = offBoard ? "Off the board" : "Where it stopped was not measured"
            reasons = []
            return
        }
        let along = rest.y - Self.holeY, across = rest.x - Self.holeX
        func distance(_ v: Double) -> String { abs(v) < 1 ? "on distance" : "\(Self.inches(v)) in \(v < 0 ? "short" : "long")" }
        func side(_ v: Double) -> String { abs(v) < 1 ? "on line" : "\(Self.inches(v)) in \(v < 0 ? "left" : "right")" }
        headline = (offBoard ? "Off the board: " : "") + "\(distance(along)), \(side(across))"

        var found: [Reason] = []
        // Distance (side camera): did the bag land in the wrong place, or slide the wrong amount after landing?
        if abs(along) >= Self.holeRadius {
            if let contact {
                let landedBefore = Self.holeY - contact.y          // + = landed before the hole
                let slid = rest.y - contact.y
                if along < 0 {
                    found.append(Reason(part: .flightDistance, inches: abs(along),
                                        why: "It landed \(Self.inches(landedBefore)) in before the hole and slid only \(Self.inches(slid)) in.",
                                        fix: "Land it about \(Self.inches(along)) in further up the board: a little more speed or a slightly higher arc."))
                } else if contact.y > Self.holeY {
                    found.append(Reason(part: .flightDistance, inches: along,
                                        why: "It flew past the hole: first contact \(Self.inches(contact.y - Self.holeY)) in beyond it.",
                                        fix: "Land it about \(Self.inches(along)) in shorter: a little less speed."))
                } else {
                    found.append(Reason(part: .slideDistance, inches: along,
                                        why: "It landed before the hole but slid \(Self.inches(slid)) in, past it by \(Self.inches(along)) in.",
                                        fix: "Land it about \(Self.inches(along)) in shorter, or flatter so it slides less."))
                }
            } else {
                found.append(Reason(part: .flightDistance, inches: abs(along),
                                    why: "It stopped \(distance(along)) of the hole (first contact not seen).",
                                    fix: along < 0 ? "Carry it further up the board." : "Take a little off the throw."))
            }
        }
        // Left / right (front camera): was it launched off line, or did it slide sideways after landing?
        if abs(across) >= Self.holeRadius {
            let aimed = contact.map { $0.x - Self.holeX } ?? across
            let drift = contact.map { rest.x - $0.x } ?? 0
            if abs(aimed) >= abs(drift) {
                let angle = launchVsHoleDeg.map { abs($0) >= 0.25 ? " (launched \(Self.halfDegrees($0))° \($0 < 0 ? "left" : "right") of the line to the hole)" : "" } ?? ""
                found.append(Reason(part: .aim, inches: abs(across),
                                    why: "It came down \(side(aimed)) of the hole\(angle).",
                                    fix: "Aim about \(Self.inches(across)) in further \(across > 0 ? "left" : "right"): square the shoulders and keep the hand moving straight at the hole."))
            } else {
                found.append(Reason(part: .sideSlide, inches: abs(across),
                                    why: "It landed \(side(aimed)) but slid \(Self.inches(drift)) in \(drift < 0 ? "left" : "right") after landing.",
                                    fix: "Land it flat and closer to the hole so it has less room to slide sideways."))
            }
        }
        reasons = found.sorted { $0.inches > $1.inches }
    }

    static func inches(_ v: Double) -> String { number(abs(v).rounded(), digits: 0) }
    static func halfDegrees(_ v: Double) -> String {
        let half = (abs(v) * 2).rounded() / 2
        return number(half, digits: half == half.rounded() ? 0 : 1)
    }

    init(document: TwoViewDocument, launchVsHoleDeg: Double?, target: (x: Double, y: Double)?) {
        self.init(document: document, launchVsHoleDeg: launchVsHoleDeg)
        self.target = made ? nil : target
    }

    init(document: TwoViewDocument, launchVsHoleDeg: Double?) {
        let landing = document.landing
        func point(_ p: TwoViewDocument.LandingPoint?) -> (x: Double, y: Double)? {
            guard let x = p?.x_in, let y = p?.y_in else { return nil }
            return (x, y)
        }
        let made = landing?.outcome == "hole" || document.result?.category == "throughHole"
        self.init(contact: point(landing?.contact), rest: point(landing?.rest), made: made,
                  offBoard: landing?.outcome == "off", launchVsHoleDeg: launchVsHoleDeg)
    }
}

/// Block 1 for a two-camera throw: the result, two simple drawings (side: distance; front: left/right), why it
/// missed and what to change. Nothing from other throws.
struct WhyItMissedCard: View {
    let story: MissStory
    let recorded: ScoreCategory?
    let suggested: ScoreCategory?
    var releaseSpeed: Double?
    var releaseAngle: Double?
    /// What would have put it in (release and body changes), from the attribution's fix targets.
    var fix: ThrowAttribution.Fix? = nil
    var canEdit = true
    var accept: (ScoreCategory) -> Void = { _ in }

    var body: some View {
        Card {
            HStack(alignment: .firstTextBaseline, spacing: Space.m) {
                resultChip
                Text(story.headline).font(.title.weight(.semibold))
                Spacer(minLength: 0)
            }
            if let suggested, recorded != suggested {
                HStack(spacing: Space.s) {
                    Text("Front camera says \(WhereItEndedCard.label(suggested)).").foregroundStyle(.secondary)
                    Button(recorded == nil ? "Use This Result" : "Change to \(WhereItEndedCard.label(suggested))") { accept(suggested) }
                        .disabled(!canEdit)
                }
                .font(.callout)
            }
            if !story.made {
                HStack(alignment: .top, spacing: Space.l) {
                    panel("Distance", camera: "side camera") { SideMissDrawing(story: story) }
                    panel("Left / right", camera: "front camera") { FrontMissDrawing(story: story) }
                }
            }
            if story.made {
                Label("In the hole: nothing to fix on this throw.", systemImage: "checkmark.circle.fill")
                    .font(.title3).foregroundStyle(eventColor("into_hole"))
            } else if story.reasons.isEmpty {
                Label(story.rest == nil ? "Where the bag stopped was not measured, so the miss cannot be explained."
                                        : "Within the hole's reach on both axes: a near miss, nothing to fix.",
                      systemImage: "info.circle").foregroundStyle(.secondary)
            } else {
                Grid(alignment: .leadingFirstTextBaseline, horizontalSpacing: Space.m, verticalSpacing: Space.s) {
                    GridRow {
                        Text("Why").font(.headline).foregroundStyle(.secondary)
                        VStack(alignment: .leading, spacing: 4) {
                            ForEach(story.reasons, id: \.part.rawValue) { Text($0.why).fixedSize(horizontal: false, vertical: true) }
                        }
                    }
                    GridRow {
                        Text("Fix").font(.headline).foregroundStyle(.secondary)
                        VStack(alignment: .leading, spacing: 4) {
                            ForEach(story.reasons, id: \.part.rawValue) { reason in
                                Label(reason.fix, systemImage: "arrow.right.circle.fill").fixedSize(horizontal: false, vertical: true)
                                    .symbolRenderingMode(.hierarchical).foregroundStyle(Self.target)
                            }
                            ForEach(releaseChanges, id: \.self) { line in
                                Label(line, systemImage: "scope").fixedSize(horizontal: false, vertical: true).foregroundStyle(Self.target)
                            }
                        }
                    }
                }
                .font(.body)
                bodyChanges
            }
            if let speed = releaseSpeed, let angle = releaseAngle {
                Text("Release: \(number(speed, digits: 1)) m/s at \(number(angle, digits: 0))° (side camera).")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    static let target = Color(red: 0.13, green: 0.62, blue: 0.30)

    /// The release changes that would have moved first contact onto the green target (drag-free flight from this
    /// throw's release; launch direction from the release-to-board geometry).
    private var releaseChanges: [String] {
        guard let fix else { return [] }
        var lines: [String] = []
        if let dv = fix.speed_change_m_s, abs(dv) >= 0.02 {
            let percent = releaseSpeed.map { " (about \(number(abs(dv) / $0 * 100, digits: 0)) %)" } ?? ""
            var line = "Release about \(number(abs(dv), digits: 2)) m/s \(dv > 0 ? "faster" : "slower")\(percent)"
            if let da = fix.angle_change_deg { line += ", or about \(number(abs(da), digits: 1))° \(da > 0 ? "higher" : "flatter")" }
            lines.append(line + ".")
        }
        if let dpsi = fix.launch_change_deg, abs(dpsi) >= 0.25 {
            lines.append("Launch about \(number(abs(dpsi), digits: 1))° further \(dpsi < 0 ? "left" : "right").")
        }
        return lines
    }

    /// Body measures on this throw against the athlete's throws that went in, as biomechanical reasons and fixes.
    @ViewBuilder private var bodyChanges: some View {
        if let fix, let body = fix.body, !body.isEmpty {
            let basis = fix.body_basis
            let made = basis?.kind == "made" ? "throws that went in" : "throws that scored"
            let cues = body.compactMap { change in
                BodyCue.make(change, missAlong: story.missAlong, missAcross: story.missAcross, angleChange: fix.angle_change_deg).map { (change, $0) }
            }.sorted { ($0.1.fitsMiss && $0.0.beyond_noise == true ? 0 : 1) < ($1.1.fitsMiss && $1.0.beyond_noise == true ? 0 : 1) }
            VStack(alignment: .leading, spacing: Space.s) {
                Text("Body: why it may have missed, and what to change").font(.headline)
                ForEach(cues, id: \.0.key) { change, cue in
                    let clear = change.beyond_noise == true
                    VStack(alignment: .leading, spacing: 2) {
                        HStack(alignment: .firstTextBaseline, spacing: Space.s) {
                            Image(systemName: clear ? "figure.walk.motion" : "circle.dotted")
                                .foregroundStyle(clear ? Self.target : .secondary)
                            Text(cue.reason).fixedSize(horizontal: false, vertical: true)
                                .foregroundStyle(clear ? .primary : .secondary)
                        }
                        HStack(alignment: .firstTextBaseline, spacing: Space.s) {
                            Image(systemName: "arrow.turn.down.right").foregroundStyle(Self.target).font(.caption)
                            Text(cue.fix).bold().foregroundStyle(Self.target).fixedSize(horizontal: false, vertical: true)
                            if clear && cue.fitsMiss {
                                Text("fits this miss").font(.caption.weight(.semibold)).padding(.horizontal, 6).padding(.vertical, 1)
                                    .background(Self.target.opacity(0.15), in: Capsule()).foregroundStyle(Self.target)
                            } else if !clear {
                                Text("within measurement noise").font(.caption).foregroundStyle(.secondary)
                            }
                        }
                        .padding(.leading, 22)
                    }
                }
                Text("Compared with your \(basis?.throwCount.map(String.init) ?? "") \(made). \"Fits this miss\": the difference is the kind that would push the bag the way it missed. Associations to try, not proven causes.")
                    .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    static func value(_ v: Double?, _ unit: String) -> String {
        guard let v else { return "—" }
        switch unit {
        case "°": return number(v, digits: 0) + "°"
        case "s": return number(v, digits: 2) + " s"
        case "ms": return number(v, digits: 0) + " ms"
        default: return number(v, digits: 2) + " " + unit
        }
    }

    private func panel(_ title: String, camera: String, @ViewBuilder content: () -> some View) -> some View {
        VStack(alignment: .leading, spacing: Space.xs) {
            HStack(spacing: Space.xs) {
                Text(title).font(.headline)
                Text("· \(camera)").font(.caption).foregroundStyle(.secondary)
            }
            content().frame(height: 190).frame(maxWidth: .infinity)
                .background(Color.secondary.opacity(0.05), in: RoundedRectangle(cornerRadius: 8))
        }
        .frame(maxWidth: .infinity)
    }

    private var resultChip: some View {
        let score = recorded ?? suggested
        let color = BoardEndsMap.color(score)
        return Text(score.map { WhereItEndedCard.label($0) } ?? "No result yet").font(.headline)
            .padding(.horizontal, 10).padding(.vertical, 4)
            .foregroundStyle(color).background(color.opacity(0.14), in: Capsule())
    }
}

// MARK: - Drawings

private let deckFill = Color(red: 0.93, green: 0.87, blue: 0.75)

/// Side view: the board's slope with the hole, the bag coming down to first contact and sliding to where it stopped.
struct SideMissDrawing: View {
    let story: MissStory

    var body: some View {
        Canvas { context, size in
            let w = Double(size.width), h = Double(size.height)
            // Deck from 0 to 48 in along, front edge low on the left; drawn to a common inch scale.
            let left = 26.0, right = w - 18
            let scale = (right - left) / 48
            let frontY = h - 42, rise = 12 * scale * 0.6
            func deck(_ v: Double) -> CGPoint { CGPoint(x: left + v * scale, y: frontY - rise * v / 48) }
            // Floor and board.
            var floor = Path(); floor.move(to: CGPoint(x: 6, y: frontY + 10)); floor.addLine(to: CGPoint(x: w - 6, y: frontY + 10))
            context.stroke(floor, with: .color(.secondary.opacity(0.4)), lineWidth: 1)
            var board = Path()
            board.move(to: CGPoint(x: left, y: frontY + 10)); board.addLine(to: deck(0)); board.addLine(to: deck(48))
            board.addLine(to: CGPoint(x: right, y: frontY + 10)); board.closeSubpath()
            context.fill(board, with: .color(deckFill))
            context.stroke(board, with: .color(.primary.opacity(0.5)), lineWidth: 1)
            // The hole: a gap in the deck line, 6 in wide.
            let h0 = deck(MissStory.holeY - 3), h1 = deck(MissStory.holeY + 3)
            var gap = Path(); gap.move(to: h0); gap.addLine(to: h1)
            context.stroke(gap, with: .color(.black), style: StrokeStyle(lineWidth: 5, lineCap: .butt))
            context.draw(Text("hole").font(.caption2.weight(.semibold)).foregroundStyle(.secondary),
                         at: CGPoint(x: (h0.x + h1.x) / 2, y: min(h0.y, h1.y) - 6), anchor: .bottom)
            context.draw(Text("thrower →").font(.caption2).foregroundStyle(.secondary), at: CGPoint(x: 6, y: 10), anchor: .topLeading)

            guard let contact = story.contact else {
                if let rest = story.rest { drawBag(context, at: deck(min(max(rest.y, -6), 54)), color: eventColor("final_rest")) }
                return
            }
            let c = deck(min(max(contact.y, -6), 54))
            // The bag's arrival: a short arc coming down from the thrower's side.
            var arc = Path()
            arc.move(to: CGPoint(x: c.x - 60, y: c.y - 70))
            arc.addQuadCurve(to: c, control: CGPoint(x: c.x - 18, y: c.y - 70))
            context.stroke(arc, with: .color(measuredInk), style: StrokeStyle(lineWidth: 2, lineCap: .round, dash: [5, 4]))
            if let rest = story.rest {
                let r = deck(min(max(rest.y, -6), 54))
                var slide = Path(); slide.move(to: CGPoint(x: c.x, y: c.y - 5)); slide.addLine(to: CGPoint(x: r.x, y: r.y - 5))
                context.stroke(slide, with: .color(slideInk), style: StrokeStyle(lineWidth: 3, lineCap: .round))
                drawBag(context, at: r, color: eventColor("final_rest"))
                // The error, measured along the deck from the hole to where it stopped.
                let along = rest.y - MissStory.holeY
                if abs(along) >= 1 {
                    let hc = deck(MissStory.holeY)
                    var gapLine = Path()
                    let y = frontY + 18
                    gapLine.move(to: CGPoint(x: hc.x, y: y)); gapLine.addLine(to: CGPoint(x: r.x, y: y))
                    for x in [hc.x, r.x] { gapLine.move(to: CGPoint(x: x, y: y - 4)); gapLine.addLine(to: CGPoint(x: x, y: y + 4)) }
                    context.stroke(gapLine, with: .color(.red.opacity(0.85)), style: StrokeStyle(lineWidth: 1.5))
                    context.draw(Text("\(MissStory.inches(along)) in \(along < 0 ? "short" : "long")").font(.caption.weight(.semibold))
                        .foregroundStyle(.red), at: CGPoint(x: (hc.x + r.x) / 2, y: y + 5), anchor: .top)
                }
            }
            if let target = story.target {
                // Where it needed to land to slide into the hole (same slide), green.
                let t = deck(min(max(target.y, -6), 54)), hc = deck(MissStory.holeY)
                var ideal = Path()
                ideal.move(to: CGPoint(x: t.x - 60, y: t.y - 70))
                ideal.addQuadCurve(to: t, control: CGPoint(x: t.x - 18, y: t.y - 70))
                ideal.move(to: CGPoint(x: t.x, y: t.y - 5)); ideal.addLine(to: CGPoint(x: hc.x, y: hc.y - 5))
                context.stroke(ideal, with: .color(WhyItMissedCard.target), style: StrokeStyle(lineWidth: 2, lineCap: .round, dash: [4, 3]))
                drawTarget(context, at: t)
                context.draw(Text("land here").font(.caption2.weight(.semibold)).foregroundStyle(WhyItMissedCard.target),
                             at: CGPoint(x: t.x, y: t.y + 9), anchor: .top)
            }
            drawRing(context, at: c)
            context.draw(Text("landed").font(.caption2.weight(.semibold)).foregroundStyle(eventColor("first_contact")),
                         at: CGPoint(x: c.x, y: c.y - 14), anchor: .bottom)
        }
        .accessibilityElement().accessibilityLabel("Side view of the board: where the bag landed and where it stopped")
    }
}

/// Front view: the board as the thrower sees it from behind (24 in wide, hole on the centre line), where the bag
/// landed and where it ended up across the board.
struct FrontMissDrawing: View {
    let story: MissStory

    var body: some View {
        Canvas { context, size in
            let w = Double(size.width), h = Double(size.height)
            // Top-down, thrower at the bottom: x across (thrower's left → right), y up the deck (front at the bottom).
            let boardH = h - 30, scale = boardH / 48, boardW = 24 * scale
            let x0 = (w - boardW) / 2, yFront = h - 14
            func pt(_ x: Double, _ y: Double) -> CGPoint { CGPoint(x: x0 + x * scale, y: yFront - y * scale) }
            let rect = CGRect(x: x0, y: yFront - boardH, width: boardW, height: boardH)
            context.fill(Path(roundedRect: rect, cornerRadius: 3), with: .color(deckFill))
            context.stroke(Path(roundedRect: rect, cornerRadius: 3), with: .color(.primary.opacity(0.5)), lineWidth: 1)
            var centre = Path(); centre.move(to: pt(12, -6)); centre.addLine(to: pt(12, 54))
            context.stroke(centre, with: .color(.primary.opacity(0.25)), style: StrokeStyle(lineWidth: 1, dash: [4, 3]))
            let hole = pt(MissStory.holeX, MissStory.holeY), hr = 3 * scale
            context.fill(Path(ellipseIn: CGRect(x: hole.x - hr, y: hole.y - hr, width: 2 * hr, height: 2 * hr)), with: .color(.black.opacity(0.85)))
            context.draw(Text("thrower ↓").font(.caption2).foregroundStyle(.secondary), at: CGPoint(x: 6, y: h - 4), anchor: .bottomLeading)
            context.draw(Text("← left").font(.caption2).foregroundStyle(.secondary), at: CGPoint(x: 8, y: 6), anchor: .topLeading)
            context.draw(Text("right →").font(.caption2).foregroundStyle(.secondary), at: CGPoint(x: w - 8, y: 6), anchor: .topTrailing)
            let clampX = { (x: Double) in min(max(x, -10), 34) }, clampY = { (y: Double) in min(max(y, -6), 54) }
            if let contact = story.contact, let rest = story.rest {
                var slide = Path(); slide.move(to: pt(clampX(contact.x), clampY(contact.y))); slide.addLine(to: pt(clampX(rest.x), clampY(rest.y)))
                context.stroke(slide, with: .color(slideInk), style: StrokeStyle(lineWidth: 3, lineCap: .round))
            }
            if let rest = story.rest {
                drawBag(context, at: pt(clampX(rest.x), clampY(rest.y)), color: eventColor("final_rest"))
                let across = rest.x - MissStory.holeX
                if abs(across) >= 1 {
                    let y = hole.y - hr - 10
                    var gap = Path(); gap.move(to: CGPoint(x: hole.x, y: y)); gap.addLine(to: CGPoint(x: pt(clampX(rest.x), 0).x, y: y))
                    context.stroke(gap, with: .color(.red.opacity(0.85)), lineWidth: 1.5)
                    context.draw(Text("\(MissStory.inches(across)) in \(across < 0 ? "left" : "right")").font(.caption.weight(.semibold))
                        .foregroundStyle(.red), at: CGPoint(x: (hole.x + pt(clampX(rest.x), 0).x) / 2, y: y - 3), anchor: .bottom)
                }
            }
            if let target = story.target {
                let t = pt(clampX(target.x), clampY(target.y))
                var ideal = Path(); ideal.move(to: t); ideal.addLine(to: hole)
                context.stroke(ideal, with: .color(WhyItMissedCard.target), style: StrokeStyle(lineWidth: 2, lineCap: .round, dash: [4, 3]))
                drawTarget(context, at: t)
            }
            if let contact = story.contact { drawRing(context, at: pt(clampX(contact.x), clampY(contact.y))) }
        }
        .accessibilityElement().accessibilityLabel("The board from behind the thrower: where the bag landed and stopped across the board")
    }
}

private func drawBag(_ context: GraphicsContext, at p: CGPoint, color: Color) {
    let s: CGFloat = 13
    let bag = Path(roundedRect: CGRect(x: p.x - s / 2, y: p.y - s / 2, width: s, height: s), cornerRadius: 3)
    context.fill(bag, with: .color(color))
    context.stroke(bag, with: .color(.white), lineWidth: 1.5)
}

private func drawTarget(_ context: GraphicsContext, at p: CGPoint) {
    let r: CGFloat = 8
    let ring = Path(ellipseIn: CGRect(x: p.x - r, y: p.y - r, width: 2 * r, height: 2 * r))
    context.fill(ring, with: .color(WhyItMissedCard.target.opacity(0.25)))
    context.stroke(ring, with: .color(WhyItMissedCard.target), lineWidth: 2.2)
    context.fill(Path(ellipseIn: CGRect(x: p.x - 2.5, y: p.y - 2.5, width: 5, height: 5)), with: .color(WhyItMissedCard.target))
}

private func drawRing(_ context: GraphicsContext, at p: CGPoint) {
    let r: CGFloat = 7
    let ring = Path(ellipseIn: CGRect(x: p.x - r, y: p.y - r, width: 2 * r, height: 2 * r))
    context.stroke(ring, with: .color(.white), lineWidth: 4)
    context.stroke(ring, with: .color(eventColor("first_contact")), lineWidth: 2)
}
