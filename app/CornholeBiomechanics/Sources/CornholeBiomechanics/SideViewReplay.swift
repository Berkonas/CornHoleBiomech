import SwiftUI

// The replay's Animation view drawn to scale, side on: the athlete as a stick figure, the bag's measured flight,
// the regulation board at the measured release → board distance, first contact on the deck, the slide and where
// the bag ended, over a floor line with 1 m ticks from the release. Everything comes from the analysis; a value
// that was not measured is not drawn (no board without the distance, no landing without the board phase).

/// What the animation needs to put the throw in metres. Built by the throw report from the analysis.
struct ReplayStage: Equatable {
    /// Video pixels per metre in the throwing plane (`FlightScale`, the flight chart's scale).
    var pixelsPerMeter: Double
    /// Bag height above the floor at release (m): `bag_release_height_m`, measured from the lowest foot point.
    var releaseHeight: Double
    /// Release → front edge of the board, horizontal (m), `summaries.release_to_board_front_m`; nil = not measured.
    var boardDistance: Double?
    /// Touchdown, slide and end on the board, inches up the deck (results.json or two_view.json → board_phase).
    var phase: BoardPhase?
}

/// The throw in metres, side on: x forward from the release point, y up from the floor. Built once per throw.
struct SideScene {
    struct Point { var frame: Int; var x: Double; var y: Double }

    let ppm: Double
    let releaseHeight: Double
    /// +1 when the throw runs left to right in the video, −1 when it is mirrored so it always runs left to right.
    let sign: Double
    /// The bag at release, release-frame pixels.
    let release: CGPoint
    let releaseFrame: Int
    let boardDistance: Double?
    /// Measured flight, release → last tracked point (pinned to first contact, see `stretch`).
    let flight: [Point]
    /// Drag-free model, same mapping as the flight.
    let model: [Point]
    /// Gravity arc from the last tracked point to first contact, where the bag was not tracked.
    let gap: [Point]
    /// First contact on the deck (board phase).
    let contact: Point?
    /// The tracked slide on the deck.
    let slide: [Point]
    /// Where the bag ended, and from which frame; `endFrame` nil = not timed (shown throughout).
    let end: Point?
    let endFrame: Int?
    /// Board phase end kind: "rest", "fell_in_hole", "left_deck", "lost", "moving_at_clip_end", "never_on_deck".
    let endKind: String?
    /// Horizontal factor applied to the flight so it meets the measured first contact (1 = none).
    let stretch: Double
    let xRange: ClosedRange<Double>
    let yRange: ClosedRange<Double>

    static let board = BoardGeometry.regulation
    /// Points kept below the floor line for the distance labels.
    static let labelBand = 34.0

    init?(replay: ReplayDocument, pose: PoseDocument?, stage: ReplayStage) {
        guard let event = replay.events["release"], let position = event.position, replay.fps > 0,
              stage.pixelsPerMeter.isFinite, stage.pixelsPerMeter > 0, stage.releaseHeight.isFinite else { return nil }
        let ppm = stage.pixelsPerMeter, height = stage.releaseHeight
        let release = CGPoint(x: position.x, y: position.y)
        let contactEvent = replay.events["first_contact"]
        let contactFrame = contactEvent?.frame
        let series = replay.filtered.isEmpty ? replay.measured : replay.filtered
        let path = series.filter { point in point.frame >= event.frame && (contactFrame.map { point.frame <= $0 } ?? true) }
        let towards = contactEvent?.position?.x ?? path.last?.x ?? Double(release.x)
        let sign: Double = towards >= Double(release.x) ? 1 : -1
        // Release-frame pixels → metres.
        func metres(_ x: Double, _ y: Double) -> (x: Double, y: Double) {
            (sign * (x - Double(release.x)) / ppm, height - (y - Double(release.y)) / ppm)
        }
        let board = Self.board
        let distance = stage.boardDistance.flatMap { value -> Double? in value.isFinite && value > 0 ? value : nil }
        // Inches up the deck → metres on the deck surface.
        func deck(_ inches: Double) -> (x: Double, y: Double)? {
            guard let distance else { return nil }
            let along = min(max(inches, 0), 48) * 0.0254
            return (distance + along * cos(board.angle), board.frontHeight + along * sin(board.angle))
        }
        // Inches up the deck → metres on the floor: in front of the board, behind it, or beside it (off the side).
        func onFloor(_ inches: Double) -> (x: Double, y: Double)? {
            guard let distance else { return nil }
            if inches < 0 { return (distance + inches * 0.0254, 0) }
            if inches > 48 { return (distance + board.length * cos(board.angle) + (inches - 48) * 0.0254, 0) }
            return (distance + inches * 0.0254 * cos(board.angle), 0)
        }

        // First contact, from the board phase (tracked on the deck).
        let phase = stage.phase
        var contact: Point?
        if let touchdown = phase?.touchdown {
            let onDeck = touchdown.on_deck != false && touchdown.v_in >= 0 && touchdown.v_in <= 48
            if let p = onDeck ? deck(touchdown.v_in) : onFloor(touchdown.v_in) {
                contact = Point(frame: touchdown.frame, x: p.x, y: p.y)
            }
        }
        // Pin the flight to it: the side camera's pixel scale and the board's position can disagree by a few
        // percent, so the flight is stretched along the throw (and tilted by the height difference) to end where
        // the bag was seen touching the deck. Only small corrections are applied (0.8–1.25); otherwise as measured.
        var stretch = 1.0, lift = 0.0, pinnedAt: Double?
        if let contact, let p = contactEvent?.position {
            let seen = metres(p.x, p.y)
            if seen.x > 0.5 {
                let k = contact.x / seen.x
                if k >= 0.8 && k <= 1.25 { stretch = k; lift = contact.y - seen.y; pinnedAt = seen.x }
            }
        }
        let lastFrame = contact?.frame ?? Int.max
        var flight: [Point] = []
        for p in path where p.frame <= lastFrame {
            let m = metres(p.x, p.y)
            flight.append(Point(frame: p.frame, x: m.x * stretch, y: m.y + (pinnedAt.map { lift * m.x / $0 } ?? 0)))
        }
        var model: [Point] = []
        for p in replay.model where p.frame >= event.frame && p.frame <= lastFrame {
            let m = metres(p.x, p.y)
            model.append(Point(frame: p.frame, x: m.x * stretch, y: m.y + (pinnedAt.map { lift * m.x / $0 } ?? 0)))
        }
        // Not tracked between the last flight point and first contact: a drag-free arc joining the two.
        var gap: [Point] = []
        if let contact, let last = flight.last, contact.frame - last.frame >= 2 {
            let g = 9.81, span = Double(contact.frame - last.frame) / replay.fps
            let rise = (contact.y - last.y + g * span * span / 2) / span
            for frame in last.frame...contact.frame {
                let t = Double(frame - last.frame) / replay.fps, u = Double(frame - last.frame) / Double(contact.frame - last.frame)
                gap.append(Point(frame: frame, x: last.x + (contact.x - last.x) * u, y: last.y + rise * t - g * t * t / 2))
            }
        }
        // The slide on the deck, then where it ended.
        var slide: [Point] = []
        if let touchdown = phase?.touchdown, contact != nil {
            let stop = phase?.end?.frame ?? Int.max
            // A bag that went in is not drawn sliding past the hole (the side camera can track it a little further).
            let intoHole = phase?.end?.kind == "fell_in_hole"
            for p in phase?.path ?? [] where p.frame >= touchdown.frame && p.frame <= stop {
                guard let v = p.v_in, !(intoHole && v > 42), let q = deck(v) else { continue }
                slide.append(Point(frame: p.frame, x: q.x, y: q.y))
            }
        }
        var end: Point?
        if let info = phase?.end {
            var place: (x: Double, y: Double)?
            switch info.kind {
            case "fell_in_hole": place = deck(board.holeAlong / 0.0254)
            case "left_deck", "never_on_deck": place = info.v_in.flatMap { onFloor($0) }
            default: place = info.v_in.flatMap { deck($0) }
            }
            if let place { end = Point(frame: info.frame ?? lastFrame, x: place.x, y: place.y) }
        }

        // The view: the athlete over the whole clip, the flight and the board, plus a margin.
        var bodyX: [Double] = [], bodyY: [Double] = []
        for frame in pose?.frames ?? [] {
            let origin = replay.toFrame(Double(release.x), Double(release.y), frame: frame.frameIndex)
            for (_, p) in frame.landmarks where p.confidence >= StickFigureReplay.minimumConfidence {
                guard let x = p.x, let y = p.y else { continue }
                bodyX.append(sign * (x - Double(origin.x)) / ppm)
                bodyY.append(height - (y - Double(origin.y)) / ppm)
            }
        }
        // 1st–99th percentile, so one stray detection does not shrink the picture.
        func percentile(_ values: [Double], _ q: Double) -> Double? {
            guard !values.isEmpty else { return nil }
            let sorted = values.sorted()
            return sorted[Int(q * Double(sorted.count - 1))]
        }
        var xs: [Double] = [0]
        xs += flight.map(\.x)
        xs += gap.map(\.x)
        if let contact { xs.append(contact.x) }
        if let end { xs.append(end.x) }
        var ys: [Double] = [height + 0.2, 2.0]
        ys += flight.map { $0.y + 0.2 }
        if let low = percentile(bodyX, 0.01), let high = percentile(bodyX, 0.99) { xs += [low, high] }
        if let top = percentile(bodyY, 0.99) { ys.append(top + 0.15) }
        if let distance { xs.append(distance + board.length * cos(board.angle)) }

        self.ppm = ppm
        releaseHeight = height
        self.sign = sign
        self.release = release
        releaseFrame = event.frame
        boardDistance = distance
        self.flight = flight
        self.model = model
        self.gap = gap
        self.contact = contact
        self.slide = slide
        self.end = end
        endFrame = phase?.end?.frame
        endKind = phase?.end?.kind
        self.stretch = stretch
        xRange = (min(xs.min() ?? 0, -0.3) - 0.35)...((xs.max() ?? 1) + 0.45)
        yRange = 0...max(ys.max() ?? 2, 2.0)
    }

    /// Pixels of `frame` (pose landmarks) → metres, about the release point as seen in that frame.
    func metres(_ p: CGPoint, frame: Int, replay: ReplayDocument) -> (x: Double, y: Double) {
        let origin = replay.toFrame(Double(release.x), Double(release.y), frame: frame)
        return (sign * Double(p.x - origin.x) / ppm, releaseHeight - Double(p.y - origin.y) / ppm)
    }

    /// Uniform scale (points per metre) and the screen position of x = 0 and of the floor, fitting the scene
    /// into `size` with room for the distance labels under the floor.
    func fit(in size: CGSize) -> (scale: Double, left: Double, floor: Double) {
        let spanX = xRange.upperBound - xRange.lowerBound, spanY = yRange.upperBound - yRange.lowerBound
        let width = Double(size.width), height = Double(size.height)
        let scale = max(1, min(width / spanX, (height - Self.labelBand) / spanY))
        let left = (width - spanX * scale) / 2 - xRange.lowerBound * scale
        let top = (height - spanY * scale - Self.labelBand) / 2
        return (scale, left, top + yRange.upperBound * scale)
    }

    /// The bag at `frame` (metres), when known: the measured flight, the untracked arc, the slide, then the end.
    func bag(at frame: Int) -> (x: Double, y: Double)? {
        guard frame >= releaseFrame else { return nil }
        if let p = flight.first(where: { $0.frame == frame }) ?? gap.first(where: { $0.frame == frame }) { return (p.x, p.y) }
        guard let contact, frame >= contact.frame else { return nil }
        if let endFrame, frame > endFrame {
            guard endKind != "fell_in_hole", let end else { return nil }
            return (end.x, end.y)
        }
        if let p = slide.first(where: { $0.frame == frame }) { return (p.x, p.y) }
        if frame == contact.frame { return (contact.x, contact.y) }
        return nil
    }
}

/// The Animation view when the throw has a metric scale: everything side on and to scale (see `SideScene`).
struct SideViewReplay: View {
    let scene: SideScene
    let replay: ReplayDocument
    let pose: PoseDocument?
    let side: ThrowingSide
    let frame: Int
    var showModel = true
    var showTrail = true
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        Canvas { context, size in
            let fit = scene.fit(in: size)
            func screen(_ x: Double, _ y: Double) -> CGPoint {
                CGPoint(x: fit.left + x * fit.scale, y: fit.floor - y * fit.scale)
            }
            func polyline(_ points: [SideScene.Point]) -> Path {
                var path = Path()
                for (index, p) in points.enumerated() {
                    if index == 0 { path.move(to: screen(p.x, p.y)) } else { path.addLine(to: screen(p.x, p.y)) }
                }
                return path
            }
            drawFloor(context, size: size, fit: fit)
            drawBoard(context, fit: fit, dark: colorScheme == .dark)

            // Bag: dashed drag-free model, the full path faint, the travelled path strong; dotted where not tracked.
            if showModel && !scene.model.isEmpty {
                context.stroke(polyline(scene.model), with: .color(.secondary), style: StrokeStyle(lineWidth: 1.5, dash: [6, 5]))
            }
            if showTrail {
                context.stroke(polyline(scene.flight), with: .color(measuredInk.opacity(0.3)), style: StrokeStyle(lineWidth: 2, lineCap: .round))
                context.stroke(polyline(scene.gap), with: .color(measuredInk.opacity(0.3)), style: StrokeStyle(lineWidth: 2, dash: [2, 4]))
                context.stroke(polyline(scene.slide), with: .color(slideInk.opacity(0.45)), style: StrokeStyle(lineWidth: 2, lineCap: .round))
            }
            context.stroke(polyline(scene.flight.filter { $0.frame <= frame }), with: .color(measuredInk),
                           style: StrokeStyle(lineWidth: 3, lineCap: .round, lineJoin: .round))
            context.stroke(polyline(scene.gap.filter { $0.frame <= frame }), with: .color(measuredInk),
                           style: StrokeStyle(lineWidth: 2.5, lineCap: .round, dash: [2, 4]))
            context.stroke(polyline(scene.slide.filter { $0.frame <= frame }), with: .color(slideInk),
                           style: StrokeStyle(lineWidth: 3, lineCap: .round, lineJoin: .round))
            // From the last slide point (or first contact) to where it ended, once it has ended.
            if let end = scene.end, let from = scene.slide.last ?? scene.contact, frame >= (scene.endFrame ?? 0) {
                var last = Path(); last.move(to: screen(from.x, from.y)); last.addLine(to: screen(end.x, end.y))
                let onDeck = scene.endKind == "rest" || scene.endKind == "fell_in_hole"
                context.stroke(last, with: .color(slideInk), style: StrokeStyle(lineWidth: onDeck ? 3 : 2, lineCap: .round, dash: onDeck ? [] : [3, 4]))
            }

            // The athlete, from this frame's landmarks, then the event markers over it.
            if let landmarks = pose?.frames[safe: frame]?.landmarks {
                StickFigureReplay.drawFigure(context, landmarks: landmarks, side: side, pixelScale: fit.scale / scene.ppm) { p in
                    let m = scene.metres(p, frame: frame, replay: replay)
                    return screen(m.x, m.y)
                }
            }
            drawMarkers(context, fit: fit)

            // The bag now.
            if let now = scene.bag(at: frame) {
                let p = screen(now.x, now.y)
                context.fill(Path(ellipseIn: CGRect(x: p.x - 6, y: p.y - 6, width: 12, height: 12)), with: .color(measuredInk))
                context.stroke(Path(ellipseIn: CGRect(x: p.x - 6, y: p.y - 6, width: 12, height: 12)), with: .color(.primary), lineWidth: 1)
            }

            var note = "Side on, to scale."
            if !scene.gap.isEmpty { note += " Dotted: not tracked (drag-free arc to first contact)." }
            context.draw(Text(note).font(.caption2).foregroundStyle(.secondary), at: CGPoint(x: size.width - 10, y: 8), anchor: .topTrailing)
        }
        .accessibilityElement()
        .accessibilityLabel("Side view of the throw to scale: the athlete, the bag's flight and the board, frame \(frame)")
        .accessibilityValue(accessibilityText)
    }

    private var accessibilityText: String {
        var parts: [String] = []
        if let distance = scene.boardDistance { parts.append("Board front \(number(distance, digits: 2)) m from the release.") }
        if let contact = scene.contact { parts.append("First contact \(number(contact.x, digits: 2)) m from the release.") }
        if let label = endLabel, let end = scene.end { parts.append("\(label) \(number(end.x, digits: 2)) m from the release.") }
        return parts.joined(separator: " ")
    }

    private var endLabel: String? {
        switch scene.endKind {
        case "fell_in_hole": "Into the hole"
        case "rest": "Stopped"
        case "left_deck", "never_on_deck": "Off the board"
        case nil: nil
        default: "Last seen"
        }
    }

    /// Floor line with a tick and label every metre from the release.
    private func drawFloor(_ context: GraphicsContext, size: CGSize, fit: (scale: Double, left: Double, floor: Double)) {
        var line = Path(); line.move(to: CGPoint(x: 0, y: fit.floor)); line.addLine(to: CGPoint(x: Double(size.width), y: fit.floor))
        context.stroke(line, with: .color(.secondary.opacity(0.7)), lineWidth: 1.5)
        let first = Int(scene.xRange.lowerBound.rounded(.up)), last = Int(scene.xRange.upperBound.rounded(.down))
        guard first <= last else { return }
        for metre in first...last {
            let x = fit.left + Double(metre) * fit.scale
            var tick = Path(); tick.move(to: CGPoint(x: x, y: fit.floor)); tick.addLine(to: CGPoint(x: x, y: fit.floor + 5))
            context.stroke(tick, with: .color(.secondary.opacity(0.7)), lineWidth: 1)
            context.draw(Text(metre == 0 ? "0" : "\(metre) m").font(.caption2).foregroundStyle(.secondary),
                         at: CGPoint(x: x, y: fit.floor + 7), anchor: .top)
        }
        context.draw(Text("Floor").font(.caption2).foregroundStyle(.secondary), at: CGPoint(x: 8, y: fit.floor - 4), anchor: .bottomLeading)
    }

    /// The regulation board side on (48 in deck, front edge 3 in and back edge 12 in high) with the hole.
    private func drawBoard(_ context: GraphicsContext, fit: (scale: Double, left: Double, floor: Double), dark: Bool) {
        guard let distance = scene.boardDistance else { return }
        let board = SideScene.board
        let run = board.length * cos(board.angle)
        func screen(_ x: Double, _ y: Double) -> CGPoint { CGPoint(x: fit.left + x * fit.scale, y: fit.floor - y * fit.scale) }
        var profile = Path()
        profile.addLines([screen(distance, 0), screen(distance, board.frontHeight), screen(distance + run, board.backHeight), screen(distance + run, 0)])
        profile.closeSubpath()
        context.fill(profile, with: .color(Color.red.opacity(dark ? 0.30 : 0.16)))
        context.stroke(profile, with: .color(.primary.opacity(0.5)), lineWidth: 1.2)
        var surface = Path(); surface.move(to: screen(distance, board.frontHeight)); surface.addLine(to: screen(distance + run, board.backHeight))
        context.stroke(surface, with: .color(.primary.opacity(0.8)), style: StrokeStyle(lineWidth: 2, lineCap: .round))
        // The hole: a 6 in gap in the deck surface, centred 39 in up from the front edge.
        let c = cos(board.angle), s = sin(board.angle)
        let near = board.holeAlong - board.holeRadius, far = board.holeAlong + board.holeRadius
        var hole = Path()
        hole.move(to: screen(distance + near * c, board.frontHeight + near * s))
        hole.addLine(to: screen(distance + far * c, board.frontHeight + far * s))
        context.stroke(hole, with: .color(.primary), style: StrokeStyle(lineWidth: 4, lineCap: .butt))
        context.draw(Text("Board front \(number(distance, digits: 2)) m from the release").font(.caption2).foregroundStyle(.secondary),
                     at: CGPoint(x: screen(distance + run, 0).x, y: fit.floor + 21), anchor: .topTrailing)
    }

    /// Release, first contact and where the bag ended; faded until the replay reaches them.
    private func drawMarkers(_ context: GraphicsContext, fit: (scale: Double, left: Double, floor: Double)) {
        func screen(_ x: Double, _ y: Double) -> CGPoint { CGPoint(x: fit.left + x * fit.scale, y: fit.floor - y * fit.scale) }
        func marker(_ p: CGPoint, _ label: String, _ color: Color, reached: Bool, labelLeft: Bool, square: Bool = false) {
            let rect = CGRect(x: p.x - 6, y: p.y - 6, width: 12, height: 12)
            let shape = square ? Path(roundedRect: rect, cornerRadius: 2) : Path(ellipseIn: rect)
            context.fill(shape, with: .color(color.opacity(reached ? 1 : 0.45)))
            context.stroke(shape, with: .color(.white), lineWidth: 1.5)
            context.draw(Text(label).font(.caption2.weight(.semibold)).foregroundStyle(color),
                         at: CGPoint(x: p.x + (labelLeft ? -8 : 8), y: p.y - 8), anchor: labelLeft ? .bottomTrailing : .bottomLeading)
        }
        marker(screen(0, scene.releaseHeight), "Release", eventColor("release"), reached: frame >= scene.releaseFrame, labelLeft: false)
        let endLeftOfContact = scene.end.flatMap { end in scene.contact.map { end.x < $0.x } } ?? false
        if let contact = scene.contact {
            marker(screen(contact.x, contact.y), "First contact", eventColor("first_contact"), reached: frame >= contact.frame,
                   labelLeft: !endLeftOfContact)
        }
        if let end = scene.end, let label = endLabel {
            let key = scene.endKind == "fell_in_hole" ? "into_hole" : "final_rest"
            let onBoard = scene.endKind == "rest" || scene.endKind == "fell_in_hole"
            let offBoard = scene.endKind == "left_deck" || scene.endKind == "never_on_deck"
            let color = onBoard ? eventColor(key) : offBoard ? missInk : Color.gray
            marker(screen(end.x, end.y), label, color, reached: frame >= (scene.endFrame ?? 0), labelLeft: endLeftOfContact,
                   square: scene.endKind != "fell_in_hole")
        }
    }
}
