import AppKit
import SwiftUI
import UniformTypeIdentifiers

// The throw seen from above (design council §1 "board from above" and §5 "two synchronised orthographic panels").
// Everything is drawn to scale in inches, nothing stretched: the regulation 24 × 48 in board with its long side along
// the throw, the release point and the launch direction from the 3D flight (METHODS_AND_MATH §5.4; the two-view heading
// when the 3D flight is unavailable), first contact and where the bag stopped from the front camera (§5.3), and the slide
// timed by the side camera's board phase. The path from release to first contact is a straight, labelled line: we
// measure its direction, not a curve. A value that was not measured is not drawn, and `notes` says why.

typealias PlanPoint = ThrowFromAbove.Geometry.DeckPoint

/// Screen mapping of the top view: `scale` points per inch, the same along and across (orthographic, to scale).
struct PlanMap: Equatable {
    var scale: Double
    var origin: CGPoint

    /// Screen point of `a` inches along the throw from the release point and `r` inches to the thrower's right.
    func point(_ a: Double, _ r: Double) -> CGPoint {
        CGPoint(x: Double(origin.x) + a * scale, y: Double(origin.y) + r * scale)
    }

    /// The mapping a fraction `t` of the way to `other` (still uniform, so still to scale).
    func blended(with other: PlanMap, _ t: Double) -> PlanMap {
        let u = min(max(t, 0), 1)
        return PlanMap(scale: scale + (other.scale - scale) * u,
                       origin: CGPoint(x: Double(origin.x) + (Double(other.origin.x) - Double(origin.x)) * u,
                                       y: Double(origin.y) + (Double(other.origin.y) - Double(origin.y)) * u))
    }
}

/// One throw from above, in inches: `a` along the throw from the release point (horizontal), `r` to the thrower's right
/// of the board's centre line. Built once per throw from two_view.json and the side camera's board phase.
struct TopDownScene: Equatable {
    /// The athlete's usual group of rest points (ghost on the board).
    struct UsualGroup: Equatable {
        var centre: PlanPoint
        var spreadAlong: Double
        var spreadAcross: Double
        var throwCount: Int
    }

    static let inch = 0.0254
    static var footprint: Double { ThrowFromAbove.Geometry.footprint }

    /// Release → front edge of the board (in, horizontal, side camera); nil = not measured (only the board is drawn).
    let boardFront: Double?
    /// Release point sideways from the centre line (in, + right); nil = not measured.
    let releaseRight: Double?
    /// Sideways launch direction (°, + right) and where it came from ("3D flight", "release hand → first contact").
    let launchDeg: Double?
    let launchSource: String?
    let launchEstimated: Bool
    /// First contact and where the bag stopped, on the deck (v inches up from the front edge, right of centre).
    let contact: PlanPoint?
    let rest: PlanPoint?
    let inHole: Bool
    let offBoard: Bool
    /// Side-camera frames of release, first contact and the end of the slide.
    let releaseFrame: Int?
    let contactFrame: Int?
    let endFrame: Int?
    /// Side camera: inches up the deck by frame during the slide (the bag moves at its measured pace).
    let slideProgress: [Int: Double]
    /// The athlete's usual first contact (inches up the deck) and usual group of rests; nil when unknown.
    let usualContactV: Double?
    let usualGroup: UsualGroup?
    /// Where the athlete's other throws stopped (faint dots).
    let others: [PlanPoint]
    /// Precision of the rest point (in): across from the front camera's deck homography, along from the side camera.
    let precisionAcross: Double
    let precisionAlong: Double
    /// "13 in short · 10 in right"; nil when the miss was not measured.
    let missText: String?
    /// What could not be drawn, and why.
    let notes: [String]

    /// - Parameters:
    ///   - releaseToBoardM: release → board front (m, side camera), the same distance the side panel uses.
    ///   - others: rest points of the athlete's other throws.
    init?(document: TwoViewDocument, phase: BoardPhase?, releaseToBoardM: Double?, releaseFrame: Int?, others: [PlanPoint] = []) {
        guard document.isMeasured, let landing = document.landing else { return nil }
        var notes: [String] = []
        var contact: PlanPoint?
        if let c = landing.contact, let x = c.x_in, let y = c.y_in { contact = PlanPoint(v: y, right: x - 12) }
        let inHole = landing.outcome == "hole"
        var rest: PlanPoint?
        if inHole {
            rest = PlanPoint(v: 39, right: 0)
        } else if let r = landing.rest, let x = r.x_in, let y = r.y_in {
            rest = PlanPoint(v: y, right: x - 12)
        }
        guard contact != nil || rest != nil else { return nil }
        if contact == nil { notes.append("First contact was not seen on the board, so the slide is not drawn.") }
        if rest == nil { notes.append("Where the bag stopped was not measured in both directions.") }
        if landing.contact?.status == "estimated" || landing.rest?.status == "estimated" {
            notes.append("Board positions are estimated: the front camera's board corners look misplaced on this take.")
        }

        let distance = releaseToBoardM.flatMap { $0.isFinite && $0 > 0 ? $0 : nil }
        if distance == nil { notes.append("The release → board distance was not measured, so only the board is drawn.") }
        var releaseRight: Double?, launchDeg: Double?, launchSource: String?, launchEstimated = false
        if let launch = document.launchDirection {
            launchDeg = launch.deg
            launchSource = launch.source
            launchEstimated = launch.status != "measured"
            releaseRight = launch.releaseRightM.map { $0 / Self.inch }
            if releaseRight == nil { notes.append("The release point's sideways position was not measured, so the launch line is not drawn.") }
        } else {
            notes.append("Launch direction not measured: " + shortReason(document.flight_3d?.reason ?? document.heading?.reason))
        }

        var progress: [Int: Double] = [:]
        for point in phase?.path ?? [] {
            if let v = point.v_in { progress[point.frame] = v }
        }

        // The athlete's usual: first contact from the carry component's usual (relative to the hole along the deck),
        // the group from the attribution's usual centre and spread (≥ 8 other throws, council §1), else from the
        // other throws' rests loaded by the report.
        let attribution = document.attribution
        var usualContactV: Double?
        if let carry = attribution?.depthComponent("carry"), let usual = carry.usual_in { usualContactV = 39 + usual }
        var group: UsualGroup?
        if let usual = attribution?.usual, let n = usual.throwCount, n >= 8, let sa = usual.spread_depth_in, let sr = usual.spread_lateral_in {
            group = UsualGroup(centre: PlanPoint(v: 39 + (usual.centre_depth_in ?? 0), right: usual.centre_lateral_in ?? 0),
                               spreadAlong: sa, spreadAcross: sr, throwCount: n)
        } else if others.count >= 8, let along = MedianSD.of(others.map(\.v)), let across = MedianSD.of(others.map(\.right)),
                  let sa = along.sd, let sr = across.sd {
            group = UsualGroup(centre: PlanPoint(v: along.median, right: across.median), spreadAlong: sa, spreadAcross: sr,
                               throwCount: others.count)
        }

        var miss: String?
        if let m = document.miss {
            let parts = [distanceText(m.short_long_in), sidewaysText(m.left_right_in)].compactMap { $0 }
            if !parts.isEmpty { miss = parts.joined(separator: " · ") }
        }

        boardFront = distance.map { $0 / Self.inch }
        self.releaseRight = releaseRight
        self.launchDeg = launchDeg
        self.launchSource = launchSource
        self.launchEstimated = launchEstimated
        self.contact = contact
        self.rest = rest
        self.inHole = inHole
        offBoard = landing.outcome == "off"
        self.releaseFrame = releaseFrame
        contactFrame = phase?.touchdown?.frame ?? document.frames?.contact_side
        endFrame = phase?.end?.frame
        slideProgress = progress
        self.usualContactV = usualContactV
        usualGroup = group
        self.others = others
        precisionAcross = max(0.5, phase?.leftRightFromFrontCamera == true ? (phase?.lateral?.precision_in ?? 0.5) : 0.5)
        precisionAlong = 2
        missText = miss
        self.notes = notes
    }

    // MARK: Geometry

    var front: Double { boardFront ?? 0 }

    /// Top-view position of a deck point (the deck rises 10.8°, so its 48 in cover 47.2 in of floor).
    func ground(_ p: PlanPoint) -> (a: Double, r: Double) {
        (front + ThrowFromAbove.Geometry.ground(p.v), p.right)
    }

    var hole: (a: Double, r: Double) { (front + 39 * ThrowFromAbove.Geometry.slopeCos, 0) }

    /// Release point, direction and distance are all known: the launch line can be drawn.
    var hasLaunchLine: Bool { boardFront != nil && releaseRight != nil && launchDeg != nil }

    /// Sideways position (in) on the launch line `a` inches along.
    func lineRight(at a: Double) -> Double? {
        guard let r0 = releaseRight, let deg = launchDeg else { return nil }
        return r0 + tan(deg * .pi / 180) * a
    }

    /// Angle between the line from the release point to the hole and the launch line (°, + = launched right of it).
    var wedgeDeg: Double? {
        guard boardFront != nil, let r0 = releaseRight, let deg = launchDeg else { return nil }
        return deg - atan2(-r0, hole.a) * 180 / .pi
    }

    /// Slide along the deck, first contact → rest (in); nil in the hole or when either end is missing.
    var slideLength: Double? {
        guard let contact, let rest, !inHole else { return nil }
        return rest.v - contact.v
    }

    /// Where the bag is at side frame `frame` (top view, inches): on the launch line from release to first contact
    /// (`sideAlong`: the side camera's measured distance along the throw, else even pace — drag-free horizontal motion),
    /// then contact → rest at the side camera's measured pace along the deck.
    func bag(at frame: Int, sideAlong: Double?) -> (a: Double, r: Double)? {
        guard let r0 = releaseFrame, frame >= r0 else { return nil }
        if let c0 = contactFrame, frame < c0 {
            guard hasLaunchLine else { return nil }
            let end = contact.map { ground($0).a } ?? hole.a
            let along = min(max(sideAlong ?? end * Double(frame - r0) / Double(max(1, c0 - r0)), 0), end)
            guard let r = lineRight(at: along) else { return nil }
            return (along, r)
        }
        guard let contact, let c0 = contactFrame else { return nil }
        let start = ground(contact)
        guard let rest else { return frame == c0 ? start : nil }
        let stop = ground(rest)
        if let e0 = endFrame, frame > e0 { return inHole ? nil : stop }
        var t = 0.0
        if let e0 = endFrame, e0 > c0 { t = min(1, Double(frame - c0) / Double(e0 - c0)) }
        if !offBoard, abs(rest.v - contact.v) > 1 {
            // The last measured position along the deck at or before this frame.
            var k = frame
            while k >= c0, slideProgress[k] == nil { k -= 1 }
            if k >= c0, let v = slideProgress[k] { t = min(max((v - contact.v) / (rest.v - contact.v), 0), 1) }
        }
        return (start.a + (stop.a - start.a) * t, start.r + (stop.r - start.r) * t)
    }

    /// The whole throw framed in `size`: aligned with the side panel when `align` (its points per metre and screen x
    /// of the release) is given, so both panels share the along-the-throw axis; nil without the board distance.
    func flightMap(in size: CGSize, align: (scale: Double, left: Double)?) -> PlanMap? {
        guard let front = boardFront else { return nil }
        var across: [Double] = [-12, 12]
        if let r = releaseRight { across.append(r) }
        for p in [contact, rest].compactMap({ $0 }) { across.append(p.right) }
        let lo = across.min() ?? -12, hi = across.max() ?? 12
        let height = Double(size.height), width = Double(size.width)
        if let align {
            let scale = align.scale * Self.inch
            return PlanMap(scale: scale, origin: CGPoint(x: align.left, y: height / 2 - (lo + hi) / 2 * scale))
        }
        let a0 = -20.0, a1 = front + Self.footprint + 20
        let scale = max(0.05, min((width - 20) / (a1 - a0), (height - 28) / max(hi - lo + 8, 1)))
        return PlanMap(scale: scale, origin: CGPoint(x: (width - (a1 - a0) * scale) / 2 - a0 * scale, y: height / 2 - (lo + hi) / 2 * scale))
    }

    /// The board enlarged with a little floor around it.
    func boardMap(in size: CGSize) -> PlanMap {
        let apron = 8.0, row = 16.0
        let a0 = front - apron, a1 = front + Self.footprint + apron
        let r0 = -12 - apron, r1 = 12 + apron
        let width = Double(size.width), height = Double(size.height)
        let scale = max(0.5, min((width - 20) / (a1 - a0), (height - 2 * row) / (r1 - r0)))
        return PlanMap(scale: scale, origin: CGPoint(x: width / 2 - (a0 + a1) / 2 * scale, y: height / 2 - (r0 + r1) / 2 * scale))
    }

    var accessibilityText: String {
        var parts: [String] = []
        if let w = wedgeDeg { parts.append("Launched \(halfDegrees(w))° \(w > 0 ? "right" : "left") of the line to the hole.") }
        if let contact { parts.append("First contact \(number(contact.v, digits: 0)) in up the board, \(sidewaysText(contact.right) ?? "on line").") }
        if let length = slideLength { parts.append("Slid \(number(abs(length), digits: 0)) in.") }
        if inHole { parts.append("In the hole.") } else if let missText { parts.append("Ended \(missText) of the hole.") }
        return parts.joined(separator: " ")
    }
}

/// "1.5" for 1.4°: angles to the nearest 0.5° (council §7).
func halfDegrees(_ value: Double) -> String {
    let half = (abs(value) * 2).rounded() / 2
    return number(half, digits: half == half.rounded() ? 0 : 1)
}

// MARK: - Drawing

extension TopDownScene {
    /// Draws the scene with `map`. `detail` 0 → the whole throw (launch labels), 1 → the board enlarged (board labels).
    /// `frame` nil draws the end state (the report's hero board); otherwise the bag at that side frame.
    func draw(_ context: GraphicsContext, size: CGSize, map: PlanMap, detail: Double, frame: Int?, sideAlong: Double?, dark: Bool) {
        let caption = { (text: String) in Text(text).font(.caption2).foregroundStyle(.secondary) }
        let boardLabels = detail > 0.5
        let reachedContact: Bool
        let reachedEnd: Bool
        if let frame {
            reachedContact = contactFrame.map { frame >= $0 } ?? true
            reachedEnd = endFrame.map { frame >= $0 } ?? reachedContact
        } else {
            reachedContact = true
            reachedEnd = true
        }

        // Centre line, the board (24 × 48 in, to scale; low front edge heavier) and the hole.
        if boardFront != nil {
            var centre = Path()
            centre.move(to: map.point(-30, 0)); centre.addLine(to: map.point(front + Self.footprint + 30, 0))
            context.stroke(centre, with: .color(.primary.opacity(0.15)), style: StrokeStyle(lineWidth: 1, dash: [4, 4]))
        }
        let tl = map.point(front, -12), br = map.point(front + Self.footprint, 12)
        let deck = CGRect(x: tl.x, y: tl.y, width: br.x - tl.x, height: br.y - tl.y)
        context.fill(Path(roundedRect: deck, cornerRadius: 2), with: .color(Color.red.opacity(dark ? 0.30 : 0.16)))
        context.stroke(Path(roundedRect: deck, cornerRadius: 2), with: .color(.primary.opacity(0.5)), lineWidth: 1.2)
        var edge = Path()
        edge.move(to: CGPoint(x: deck.minX, y: deck.minY)); edge.addLine(to: CGPoint(x: deck.minX, y: deck.maxY))
        context.stroke(edge, with: .color(.primary.opacity(0.8)), style: StrokeStyle(lineWidth: 2.5, lineCap: .round))
        let holePoint = map.point(hole.a, hole.r)
        let holeRadius = CGFloat(max(1.5, 3 * map.scale))
        context.fill(Path(ellipseIn: CGRect(x: holePoint.x - holeRadius, y: holePoint.y - holeRadius, width: 2 * holeRadius, height: 2 * holeRadius)),
                     with: .color(.primary.opacity(0.85)))
        if boardLabels {
            context.draw(caption("Front edge"), at: CGPoint(x: deck.minX, y: deck.maxY + 3), anchor: .topLeading)
            context.draw(caption("Back"), at: CGPoint(x: deck.maxX, y: deck.maxY + 3), anchor: .topTrailing)
        }

        // Ghost of the usual: the other throws' rests, the usual group and the usual first contact.
        if detail > 0.2 {
            for p in others {
                let g = ground(p), q = map.point(g.a, g.r)
                context.fill(Path(ellipseIn: CGRect(x: q.x - 2.5, y: q.y - 2.5, width: 5, height: 5)), with: .color(.secondary.opacity(0.35)))
            }
            if let group = usualGroup {
                let g = ground(group.centre), c = map.point(g.a, g.r)
                let w = CGFloat(2 * group.spreadAlong * ThrowFromAbove.Geometry.slopeCos * map.scale), h = CGFloat(2 * group.spreadAcross * map.scale)
                let ellipse = Path(ellipseIn: CGRect(x: c.x - w / 2, y: c.y - h / 2, width: w, height: h))
                context.fill(ellipse, with: .color(.secondary.opacity(0.07)))
                context.stroke(ellipse, with: .color(.secondary.opacity(0.7)), style: StrokeStyle(lineWidth: 1.2, dash: [4, 3]))
                if boardLabels {
                    context.draw(caption("your usual group"), at: CGPoint(x: c.x + w / 2 * 0.72, y: c.y - h / 2 * 0.72 - 2), anchor: .bottomLeading)
                }
            }
        }
        if let v = usualContactV {
            let a = front + ThrowFromAbove.Geometry.ground(v)
            var tick = Path(); tick.move(to: map.point(a, -12)); tick.addLine(to: map.point(a, 12))
            context.stroke(tick, with: .color(.secondary.opacity(0.75)), style: StrokeStyle(lineWidth: 1.2, dash: [2, 3]))
            if boardLabels { context.draw(caption("usual landing"), at: planShift(map.point(a, -12), 0, -3), anchor: .bottom) }
        }

        // Launch: the line from the release point to the hole (reference, dashed), the measured launch line (solid) and
        // the wedge between them, all to scale.
        if hasLaunchLine, let r0 = releaseRight, let deg = launchDeg {
            let release = map.point(0, r0)
            let slope = tan(deg * .pi / 180)
            let endA = contact.map { ground($0).a } ?? hole.a
            let end = map.point(endA, r0 + slope * endA)
            let wedgeEnd = map.point(hole.a, r0 + slope * hole.a)
            var wedge = Path(); wedge.move(to: release); wedge.addLine(to: holePoint); wedge.addLine(to: wedgeEnd); wedge.closeSubpath()
            context.fill(wedge, with: .color(Color.accentColor.opacity(0.2)))
            var toHole = Path(); toHole.move(to: release); toHole.addLine(to: holePoint)
            context.stroke(toHole, with: .color(.primary.opacity(0.45)), style: StrokeStyle(lineWidth: 1, dash: [5, 4]))
            var line = Path(); line.move(to: release); line.addLine(to: end)
            context.stroke(line, with: .color(measuredInk.opacity(frame == nil ? 0.9 : 0.35)), style: StrokeStyle(lineWidth: 2, lineCap: .round))
            if let frame, let r0f = releaseFrame, frame >= r0f {
                let reach = reachedContact ? endA : (bag(at: frame, sideAlong: sideAlong)?.a ?? 0)
                var travelled = Path(); travelled.move(to: release); travelled.addLine(to: map.point(reach, r0 + slope * reach))
                context.stroke(travelled, with: .color(measuredInk), style: StrokeStyle(lineWidth: 3, lineCap: .round))
            }
            context.fill(Path(ellipseIn: CGRect(x: release.x - 4, y: release.y - 4, width: 8, height: 8)), with: .color(eventColor("release")))
            if detail < 0.5 {
                context.draw(caption("Release"), at: planShift(release, 0, 7), anchor: .top)
                // The launch label on the side the launch line turned to, the reference label on the other side.
                let w = wedgeDeg ?? 0
                let label = abs(w) < 0.25 ? "launched straight at the hole"
                    : "launched \(halfDegrees(w))° \(w > 0 ? "right" : "left") of the line to the hole"
                let at = map.point(endA * 0.45, r0 + slope * endA * 0.45)
                context.draw(Text(label).font(.caption2.weight(.semibold)).foregroundStyle(.primary),
                             at: planShift(at, 0, w > 0 ? 6 : -6), anchor: w > 0 ? .top : .bottom)
                context.draw(caption("line to the hole"), at: planShift(map.point(hole.a * 0.75, r0 * 0.25), 0, w > 0 ? -6 : 6),
                             anchor: w > 0 ? .bottom : .top)
            }
        }

        // First contact (hollow, bag-sized), the slide (arrow) and where it stopped (filled bag) or the hole.
        let bagSide = CGFloat(max(6, 6 * map.scale))
        if let contact {
            let g = ground(contact), c = map.point(g.a, g.r)
            if let rest, (reachedContact || frame == nil) {
                let s = ground(rest)
                let stop = inHole ? holePoint : map.point(s.a, s.r)
                drawArrow(context, from: c, to: stop, stopShort: Double(inHole ? holeRadius : bagSide / 2), opacity: reachedEnd ? 1 : 0.45)
                if boardLabels, let length = slideLength, abs(length) >= 1 {
                    let mid = CGPoint(x: (c.x + stop.x) / 2, y: (c.y + stop.y) / 2)
                    context.draw(Text("slid \(number(abs(length), digits: 0)) in").font(.caption2.weight(.semibold)),
                                 at: planShift(mid, 0, Double(-bagSide / 2 - 3)), anchor: .bottom)
                }
            }
            let radius = bagSide / 2
            let ring = Path(ellipseIn: CGRect(x: c.x - radius, y: c.y - radius, width: 2 * radius, height: 2 * radius))
            context.fill(ring, with: .color(Color(nsColor: .windowBackgroundColor).opacity(0.85)))
            context.stroke(ring, with: .color(Color.accentColor.opacity(reachedContact ? 1 : 0.45)), lineWidth: 2)
            if boardLabels {
                let restIsRight = rest.map { ground($0).a >= g.a } ?? true
                context.draw(Text("first contact").font(.caption2.weight(.semibold)),
                             at: planShift(c, Double(restIsRight ? -radius - 4 : radius + 4), 0), anchor: restIsRight ? .trailing : .leading)
            }
        }
        if inHole {
            if reachedEnd {
                for radius in [holeRadius + 5, holeRadius + 1] {
                    context.stroke(Path(ellipseIn: CGRect(x: holePoint.x - radius, y: holePoint.y - radius, width: 2 * radius, height: 2 * radius)),
                                   with: .color(eventColor("into_hole")), lineWidth: 2.2)
                }
                if boardLabels {
                    context.draw(Text("In the hole").font(.caption.weight(.semibold)).foregroundStyle(eventColor("into_hole")),
                                 at: planShift(holePoint, 0, Double(-holeRadius - 8)), anchor: .bottom)
                }
            }
        } else if let rest {
            let g = ground(rest)
            let raw = map.point(g.a, g.r)
            let shown = Self.inside(raw, from: holePoint, size: size, inset: Double(max(10, bagSide / 2 + 2)))
            let opacity: Double = reachedEnd ? 1.0 : 0.4
            if boardLabels || frame == nil {
                var vector = Path(); vector.move(to: holePoint); vector.addLine(to: shown.point)
                context.stroke(vector, with: .color(.primary.opacity(0.6 * opacity)), style: StrokeStyle(lineWidth: 1.1, dash: [3, 3]))
            }
            if shown.moved {
                drawHead(context, at: shown.point, from: holePoint, size: 12, color: Color.accentColor.opacity(opacity))
            } else {
                let bag = Path(roundedRect: CGRect(x: raw.x - bagSide / 2, y: raw.y - bagSide / 2, width: bagSide, height: bagSide),
                               cornerRadius: bagSide * 0.18)
                context.fill(bag, with: .color(Color.accentColor.opacity(0.9 * opacity)))
                context.stroke(bag, with: .color(.white.opacity(0.9)), lineWidth: 1.2)
                // Measurement precision of the rest point: ±across (front camera) × ±along (side camera).
                let w = CGFloat(2 * precisionAlong * map.scale), h = CGFloat(2 * precisionAcross * map.scale)
                context.stroke(Path(ellipseIn: CGRect(x: raw.x - w / 2, y: raw.y - h / 2, width: w, height: h)),
                               with: .color(.primary.opacity(0.85 * opacity)), lineWidth: 1)
            }
            if (boardLabels || frame == nil), let missText {
                drawMissLabel(context, (offBoard ? "Off the board: " : "") + missText, at: shown.point, from: holePoint,
                              gap: Double(bagSide / 2 + 6), size: size)
            }
        }

        // The bag now.
        if let frame, let now = bag(at: frame, sideAlong: sideAlong) {
            let p = map.point(now.a, now.r), radius = CGFloat(max(6, 3.6 * map.scale))
            context.stroke(Path(ellipseIn: CGRect(x: p.x - radius, y: p.y - radius, width: 2 * radius, height: 2 * radius)),
                           with: .color(.primary), lineWidth: 2)
        }

        // Orientation and a scale bar.
        context.draw(caption("Thrower's left"), at: CGPoint(x: 6, y: 3), anchor: .topLeading)
        context.draw(caption("Thrower's right"), at: CGPoint(x: 6, y: size.height - 3), anchor: .bottomLeading)
        drawScaleBar(context, size: size, scale: map.scale)
    }

    /// `p`, or the point where the line from `origin` to it leaves the canvas (inset), when it lies outside.
    static func inside(_ p: CGPoint, from origin: CGPoint, size: CGSize, inset: Double) -> (point: CGPoint, moved: Bool) {
        let x0 = inset, x1 = Double(size.width) - inset, y0 = inset, y1 = Double(size.height) - inset
        let px = Double(p.x), py = Double(p.y)
        if px >= x0 && px <= x1 && py >= y0 && py <= y1 { return (p, false) }
        let ox = min(max(Double(origin.x), x0), x1), oy = min(max(Double(origin.y), y0), y1)
        let dx = px - ox, dy = py - oy
        var t = 1.0
        if dx > 0 { t = min(t, (x1 - ox) / dx) }
        if dx < 0 { t = min(t, (x0 - ox) / dx) }
        if dy > 0 { t = min(t, (y1 - oy) / dy) }
        if dy < 0 { t = min(t, (y0 - oy) / dy) }
        return (CGPoint(x: ox + dx * max(t, 0), y: oy + dy * max(t, 0)), true)
    }

    private func drawArrow(_ context: GraphicsContext, from a: CGPoint, to b: CGPoint, stopShort: Double, opacity: Double) {
        let dx = Double(b.x - a.x), dy = Double(b.y - a.y)
        let length = (dx * dx + dy * dy).squareRoot()
        guard length > 1 else { return }
        let ux = dx / length, uy = dy / length
        let tip = CGPoint(x: Double(b.x) - ux * stopShort, y: Double(b.y) - uy * stopShort)
        var line = Path(); line.move(to: a); line.addLine(to: tip)
        context.stroke(line, with: .color(.primary.opacity(0.25 * opacity)), style: StrokeStyle(lineWidth: 4.5, lineCap: .round))
        context.stroke(line, with: .color(slideInk.opacity(opacity)), style: StrokeStyle(lineWidth: 2.6, lineCap: .round))
        if length - stopShort > 8 { drawHead(context, at: tip, from: a, size: 8, color: slideInk.opacity(opacity)) }
    }

    /// A filled arrowhead at `tip` pointing away from `from`.
    private func drawHead(_ context: GraphicsContext, at tip: CGPoint, from: CGPoint, size: Double, color: Color) {
        let dx = Double(tip.x - from.x), dy = Double(tip.y - from.y)
        let length = max((dx * dx + dy * dy).squareRoot(), 0.001)
        let ux = dx / length, uy = dy / length
        let bx = Double(tip.x) - size * ux, by = Double(tip.y) - size * uy
        var head = Path()
        head.move(to: tip)
        head.addLine(to: CGPoint(x: bx - size * 0.5 * uy, y: by + size * 0.5 * ux))
        head.addLine(to: CGPoint(x: bx + size * 0.5 * uy, y: by - size * 0.5 * ux))
        head.closeSubpath()
        context.fill(head, with: .color(color))
    }

    /// The miss label beyond the bag, away from the hole, kept inside the canvas.
    private func drawMissLabel(_ context: GraphicsContext, _ text: String, at end: CGPoint, from hole: CGPoint, gap: Double, size: CGSize) {
        let resolved = context.resolve(Text(text).font(.caption.weight(.semibold)).foregroundStyle(.primary))
        let measured = resolved.measure(in: CGSize(width: 400, height: 40))
        let w = Double(measured.width) + 10, h = Double(measured.height) + 4
        let dx = Double(end.x - hole.x), dy = Double(end.y - hole.y)
        let length = max((dx * dx + dy * dy).squareRoot(), 0.001)
        let ux = dx / length, uy = dy / length
        var cx = Double(end.x) + ux * (gap + w / 2), cy = Double(end.y) + uy * (gap + h / 2)
        if abs(uy) < 0.6 { cx = Double(end.x); cy = Double(end.y) + (Double(end.y) >= Double(hole.y) ? gap + h / 2 : -gap - h / 2) }
        cx = min(max(cx, w / 2 + 2), Double(size.width) - w / 2 - 2)
        cy = min(max(cy, h / 2 + 2), Double(size.height) - h / 2 - 2)
        let box = CGRect(x: cx - w / 2, y: cy - h / 2, width: w, height: h)
        context.fill(Path(roundedRect: box, cornerRadius: 4), with: .color(Color(nsColor: .textBackgroundColor).opacity(0.88)))
        context.stroke(Path(roundedRect: box, cornerRadius: 4), with: .color(.primary.opacity(0.15)), lineWidth: 0.8)
        context.draw(resolved, at: CGPoint(x: box.midX, y: box.midY))
    }

    /// 6 in, 1 ft, 2 ft, 1 m or 2 m: the shortest that is at least 36 points long.
    private func drawScaleBar(_ context: GraphicsContext, size: CGSize, scale: Double) {
        let options: [(inches: Double, label: String)] = [(6, "6 in"), (12, "1 ft"), (24, "2 ft"), (39.37, "1 m"), (78.74, "2 m")]
        let pick = options.first { $0.inches * scale >= 36 } ?? options[options.count - 1]
        let length = pick.inches * scale
        let x1 = Double(size.width) - 10, x0 = x1 - length, y = Double(size.height) - 8
        var bar = Path()
        bar.move(to: CGPoint(x: x0, y: y)); bar.addLine(to: CGPoint(x: x1, y: y))
        bar.move(to: CGPoint(x: x0, y: y - 3)); bar.addLine(to: CGPoint(x: x0, y: y + 3))
        bar.move(to: CGPoint(x: x1, y: y - 3)); bar.addLine(to: CGPoint(x: x1, y: y + 3))
        context.stroke(bar, with: .color(.secondary), lineWidth: 1.2)
        context.draw(Text(pick.label).font(.caption2).foregroundStyle(.secondary), at: CGPoint(x: x0 - 4, y: y), anchor: .trailing)
    }
}

/// `p` moved by (dx, dy) points.
private func planShift(_ p: CGPoint, _ dx: Double, _ dy: Double) -> CGPoint { CGPoint(x: Double(p.x) + dx, y: Double(p.y) + dy) }

// MARK: - Views

/// The top view on a canvas. `zoom` 0 frames the whole throw (aligned with the side panel when `align` is given),
/// 1 the board enlarged; values between blend the two framings, still to scale.
struct PlanCanvas: View {
    let scene: TopDownScene
    /// Side frame shown; nil = the end state (no moving bag).
    var frame: Int? = nil
    var zoom: Double = 1
    /// Side panel: points per metre and the screen x of the release point.
    var align: (scale: Double, left: Double)? = nil
    /// Side camera: the bag's distance along the throw at `frame` (in), while in the air.
    var sideAlong: Double? = nil
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        Canvas { context, size in
            let board = scene.boardMap(in: size)
            let map = scene.flightMap(in: size, align: align).map { $0.blended(with: board, zoom) } ?? board
            scene.draw(context, size: size, map: map, detail: scene.boardFront == nil ? 1 : zoom, frame: frame,
                       sideAlong: sideAlong, dark: colorScheme == .dark)
        }
        .clipped()
        .accessibilityElement()
        .accessibilityLabel("The throw seen from above, to scale")
        .accessibilityValue(scene.accessibilityText)
    }
}

/// Block 2 of the throw screen (council §1): the board from above as the hero — first contact (hollow) → slide arrow →
/// where it stopped (filled bag, with its ±0.5 × ±2 in precision ellipse), the hole, and a ghost of the athlete's usual
/// group. Exportable as a PNG figure.
struct BoardHeroCard: View {
    let scene: TopDownScene
    var title = "Where it ended"
    var figureName = "board"
    /// Extra content under the drawing (the front camera's result suggestion).
    var footer: AnyView? = nil

    var body: some View {
        Card(title, symbol: "flag.checkered", subtitle: "From above and to scale: the 2 × 4 ft board with its front edge at the left, the thrower's left at the top.") {
            PlanCanvas(scene: scene).frame(height: 300)
            legend
            ForEach(scene.notes, id: \.self) { note in
                Label(note, systemImage: "info.circle").font(.caption).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack(alignment: .center) {
                if let footer { footer }
                Spacer(minLength: Space.m)
                Button("Export Figure…", systemImage: "square.and.arrow.down") {
                    FigureExport.savePNG(PlanCanvas(scene: scene).padding(12), size: CGSize(width: 1200, height: 640),
                                         suggestedName: figureName)
                }
                .help("Save this drawing as a PNG figure")
            }
        }
    }

    private var legend: some View {
        HStack(spacing: Space.l) {
            if scene.contact != nil {
                item(Circle().strokeBorder(Color.accentColor, lineWidth: 2).frame(width: 11, height: 11), "first contact")
            }
            if scene.contact != nil && scene.rest != nil && !scene.inHole {
                item(Capsule().fill(slideInk).frame(width: 18, height: 4), "slide")
            }
            if !scene.inHole && scene.rest != nil {
                item(RoundedRectangle(cornerRadius: 2).fill(Color.accentColor).frame(width: 11, height: 11),
                     "where it stopped (±\(number(scene.precisionAcross, digits: 1)) × ±\(number(scene.precisionAlong, digits: 0)) in)")
            }
            if let group = scene.usualGroup {
                item(Ellipse().stroke(Color.secondary, style: StrokeStyle(lineWidth: 1.2, dash: [4, 3])).frame(width: 18, height: 10),
                     "your usual group (\(group.throwCount) throws)")
            }
            if scene.usualContactV != nil {
                item(Rectangle().fill(Color.secondary).frame(width: 2, height: 11), "usual landing")
            }
            Spacer(minLength: 0)
        }
        .font(.caption).foregroundStyle(.secondary)
    }

    private func item(_ swatch: some View, _ text: String) -> some View {
        HStack(spacing: 5) { swatch; Text(text) }
    }
}

/// The Animation view's two synchronised orthographic panels (council §5): side on (measured arc solid, untracked gap
/// dotted, drag-free model dashed) above the top view from release to first contact along the measured launch line, then
/// the slide to rest. The top panel shares the side panel's along-the-throw axis during the flight; from first contact
/// it enlarges to the board (animated unless Reduce Motion is on; never while exporting).
struct SyncedThrowPanels: View {
    let scene: SideScene
    let replay: ReplayDocument
    let pose: PoseDocument?
    let side: ThrowingSide
    let frame: Int
    var plan: TopDownScene? = nil
    var showModel = true
    var showTrail = true
    /// Draw the settled state (figure export): no time-driven zoom.
    var still = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var stageChange = Date.distantPast
    @State private var zooming = false

    /// From first contact the top panel shows the board enlarged.
    private var boardStage: Bool {
        guard let contact = plan?.contactFrame else { return false }
        return frame >= contact
    }

    var body: some View {
        GeometryReader { geometry in
            let width = geometry.size.width, height = geometry.size.height
            let planHeight: CGFloat = plan == nil ? 0 : max(120, height * 0.36)
            let sideHeight = max(80, height - planHeight - (plan == nil ? 0 : Space.s))
            let fit = scene.fit(in: CGSize(width: width, height: sideHeight))
            VStack(spacing: Space.s) {
                SideViewReplay(scene: scene, replay: replay, pose: pose, side: side, frame: frame,
                               showModel: showModel, showTrail: showTrail, usualContactV: plan?.usualContactV)
                    .frame(width: width, height: sideHeight)
                if let plan {
                    TimelineView(.animation(minimumInterval: nil, paused: !zooming)) { timeline in
                        PlanCanvas(scene: plan, frame: frame, zoom: zoom(at: timeline.date), align: (scale: fit.scale, left: fit.left),
                                   sideAlong: sideAlong(plan))
                    }
                    .frame(width: width, height: planHeight)
                    .overlay(RoundedRectangle(cornerRadius: 6).strokeBorder(.separator.opacity(0.5)))
                }
            }
        }
        .onChange(of: boardStage) { _, _ in
            stageChange = Date()
            zooming = !(reduceMotion || still)
        }
        .task(id: stageChange) {
            guard zooming else { return }
            try? await Task.sleep(for: .milliseconds(650))
            if !Task.isCancelled { zooming = false }
        }
    }

    /// The side camera's distance along the throw (in) for the top panel, while the bag is in the air.
    private func sideAlong(_ plan: TopDownScene) -> Double? {
        guard let contact = plan.contactFrame, frame < contact, let now = scene.bag(at: frame) else { return nil }
        return now.x / TopDownScene.inch
    }

    private func zoom(at date: Date) -> Double {
        let target = boardStage ? 1.0 : 0.0
        guard zooming, !still, !reduceMotion else { return target }
        let t = min(max(date.timeIntervalSince(stageChange) / 0.6, 0), 1)
        let eased = t * t * (3 - 2 * t)
        return boardStage ? eased : 1 - eased
    }
}

// MARK: - Pauses and callouts

/// Where the animation pauses (release, first contact, rest) and the one callout each pause carries, tied to the
/// throw's sentence: the named part when the attribution names one, else the measured fact at that moment.
struct ReplayStory: Equatable {
    struct Stop: Equatable {
        var frame: Int
        /// Event key for the colour: "release", "first_contact", "final_rest" or "into_hole".
        var key: String
        var title: String
        var text: String
    }

    var stops: [Stop]
    var frames: [Int] { stops.map(\.frame) }
    func stop(at frame: Int) -> Stop? { stops.first { $0.frame == frame } }

    static func make(replay: ReplayDocument, phase: BoardPhase?, document: TwoViewDocument?, plan: TopDownScene?,
                     speed: Double?, angle: Double?) -> ReplayStory? {
        let attribution = document?.attribution
        var stops: [Stop] = []
        func inches(_ value: Double) -> String { "\(number(abs(value), digits: 0)) in" }

        if let release = replay.events["release"]?.frame {
            let text: String
            if let a = attribution, a.lateralComponent("aim")?.named == true, let d = a.driver("launch_direction")?.delta, abs(d) >= 0.25 {
                text = "Launched about \(halfDegrees(d))° \(d > 0 ? "right" : "left") of your usual line."
            } else if let a = attribution, let part = a.lateralComponent("release_position"), part.named == true,
                      let vs = part.vs_usual_in ?? part.inches {
                text = "Released \(inches(vs)) \(vs > 0 ? "right" : "left") of your usual release point."
            } else if let a = attribution, let driver = a.driver("release_speed"), driver.named == true, let d = driver.delta {
                text = "Released about \(number(abs(d), digits: 1)) m/s \(d > 0 ? "faster" : "slower") than usual."
            } else if let w = plan?.wedgeDeg {
                text = abs(w) < 0.25 ? "Launched straight along the line to the hole."
                    : "Launched \(halfDegrees(w))° \(w > 0 ? "right" : "left") of the line to the hole."
            } else if let speed, let angle {
                text = "Released at \(number(speed, digits: 1)) m/s and \(number(angle, digits: 0))°."
            } else {
                text = "The bag leaves the hand."
            }
            stops.append(Stop(frame: release, key: "release", title: "Release", text: text))
        }

        if let contact = plan?.contactFrame ?? phase?.touchdown?.frame {
            let text: String
            if let carry = attribution?.depthComponent("carry"), let vs = carry.vs_usual_in {
                text = abs(vs) < 1 ? "Landed at your usual landing spot."
                    : "Landed \(inches(vs)) \(vs > 0 ? "further" : "shorter") than your usual landing spot."
            } else if let touchdown = phase?.touchdown {
                text = "First contact \(BoardPhase.whereText(touchdown.from_hole_in))."
            } else {
                text = "First contact."
            }
            stops.append(Stop(frame: contact, key: "first_contact", title: "First contact", text: text))
        }

        if let end = phase?.end, let frame = end.frame, ["rest", "fell_in_hole", "left_deck"].contains(end.kind) {
            let inHole = plan?.inHole ?? (end.kind == "fell_in_hole")
            let text: String
            if inHole {
                text = "In the hole. Nothing to change."
            } else {
                var parts: [String] = []
                if let length = plan?.slideLength {
                    var slid = "Slid \(inches(length))"
                    if let usual = attribution?.depthComponent("slide")?.usual_in { slid += " (usually \(inches(usual)))" }
                    parts.append(slid + ".")
                }
                if let miss = document?.miss {
                    let words = [distanceText(miss.short_long_in), sidewaysText(miss.left_right_in)].compactMap { $0 }
                    if !words.isEmpty { parts.append("Ended \(words.joined(separator: " and ")) of the hole.") }
                } else if end.kind == "rest", let from = end.from_hole_in {
                    parts.append("Stopped \(BoardPhase.whereText(from)).")
                } else if end.kind == "left_deck" {
                    parts.append("Left the board.")
                }
                text = parts.isEmpty ? "Where it stopped." : parts.joined(separator: " ")
            }
            stops.append(Stop(frame: frame, key: inHole ? "into_hole" : "final_rest", title: inHole ? "In the hole" : "Stopped", text: text))
        }
        // Strictly increasing frames (a stop that would come before the previous one is dropped).
        var ordered: [Stop] = []
        for stop in stops where stop.frame > (ordered.last?.frame ?? Int.min) { ordered.append(stop) }
        return ordered.isEmpty ? nil : ReplayStory(stops: ordered)
    }
}

// MARK: - Figure export

/// Saves a SwiftUI drawing as a PNG figure (ImageRenderer, 2× pixels, light appearance on white).
@MainActor enum FigureExport {
    static func savePNG<Content: View>(_ content: Content, size: CGSize, suggestedName: String) {
        let renderer = ImageRenderer(content: content
            .frame(width: size.width, height: size.height)
            .background(Color.white)
            .environment(\.colorScheme, .light))
        renderer.scale = 2
        guard let image = renderer.cgImage,
              let data = NSBitmapImageRep(cgImage: image).representation(using: .png, properties: [:]) else {
            NSSound.beep()
            return
        }
        let panel = NSSavePanel()
        panel.title = "Export Figure"
        panel.allowedContentTypes = [.png]
        panel.canCreateDirectories = true
        panel.nameFieldStringValue = suggestedName.hasSuffix(".png") ? suggestedName : suggestedName + ".png"
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            try data.write(to: url, options: .atomic)
        } catch {
            NSAlert(error: error).runModal()
        }
    }
}
