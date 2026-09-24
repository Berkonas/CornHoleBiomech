import SwiftUI

/// One launched throw: the parameters it was thrown with and when its animation started.
struct LaunchRun: Equatable {
    var params: LaunchParameters
    var start: Date
}

/// Scene clock (seconds): arm swing, flight, then a short settle for the landing marker.
enum ThrowTimeline {
    static let swing = 0.35
    static let settle = 0.25
    static func total(_ p: LaunchParameters) -> Double { swing + LaunchModel(p).landing().time + settle }
}

// MARK: - Thrower

/// Stick-figure pose for a 1.75 m adult (segment proportions after Winter, *Biomechanics and Motor
/// Control of Human Movement*). The throwing arm swings like a pendulum about the shoulder, so at
/// release it is perpendicular to the release velocity and the hand is exactly at the release point.
struct ThrowerPose {
    static let upperArm = 0.32, forearm = 0.34           // forearm measured to the bag in the hand
    static let trunk = 0.50, neckToHead = 0.19, headRadius = 0.105
    static let thigh = 0.44, shank = 0.43, ankleHeight = 0.07, footLength = 0.22
    static let reach = 0.97 * (upperArm + forearm)       // slightly bent elbow at release
    static let backswing = -60.0 * .pi / 180             // arm angle from straight down at the start of the swing
    static let followThrough = 35.0 * .pi / 180

    var shoulder, elbow, hand, hip, head: CGPoint
    var frontKnee, frontAnkle, backKnee, backAnkle: CGPoint
    var otherElbow, otherHand: CGPoint
    var lean: Double                                     // trunk lean forward from vertical, radians

    /// Body placement at the moment of release.
    private struct Setup { var shoulder: CGPoint; var hip: CGPoint; var lean: Double; var frontAnkle: CGPoint; var backAnkle: CGPoint }

    private static func setup(_ p: LaunchParameters) -> Setup {
        let theta = p.angleDegrees * .pi / 180
        let release = CGPoint(x: 0, y: p.releaseHeight)
        // Preferred shoulder: one reach behind the hand, perpendicular to the release direction.
        var shoulder = CGPoint(x: -reach * sin(theta), y: p.releaseHeight + reach * cos(theta))
        // Crouch or stand tall within what the legs allow; bend the elbow if the hand is closer.
        shoulder.y = min(max(shoulder.y, min(0.80, p.releaseHeight + 0.95 * reach)), 1.39)
        let dy = shoulder.y - release.y
        if hypot(shoulder.x - release.x, dy) > reach { shoulder.x = release.x - sqrt(max(reach * reach - dy * dy, 0)) }
        let lean = min(max((12 + (1.39 - shoulder.y) * 60) * .pi / 180, 8 * .pi / 180), 50 * .pi / 180)
        let hip = CGPoint(x: shoulder.x - trunk * sin(lean), y: shoulder.y - trunk * cos(lean))
        let legRise = hip.y - ankleHeight
        let maxStride = sqrt(max(pow(0.985 * (thigh + shank), 2) - legRise * legRise, 0))
        return Setup(shoulder: shoulder, hip: hip, lean: lean,
                     frontAnkle: CGPoint(x: hip.x + min(0.40, maxStride), y: ankleHeight),
                     backAnkle: CGPoint(x: hip.x - min(0.36, maxStride), y: ankleHeight))
    }

    /// Pose at scene time `t` (0 = start of the swing, `ThrowTimeline.swing` = release).
    static func at(_ p: LaunchParameters, time t: Double) -> ThrowerPose {
        let s = setup(p)
        let release = CGPoint(x: 0, y: p.releaseHeight)
        let radius = hypot(release.x - s.shoulder.x, release.y - s.shoulder.y)
        let releaseArm = atan2(release.x - s.shoulder.x, s.shoulder.y - release.y)
        let u = min(max(t / ThrowTimeline.swing, 0), 1)
        let f = min(max((t - ThrowTimeline.swing) / 0.3, 0), 1)
        let easeIn = 1 - cos(u * .pi / 2)                  // arm accelerates into release
        let easeOut = 1 - (1 - f) * (1 - f)                // and decelerates through the follow-through
        let smooth = u * u * (3 - 2 * u)
        let arm = backswing + (releaseArm - backswing) * easeIn + followThrough * easeOut
        // The body drifts forward into the release, then a little further.
        let shift = -0.08 * (1 - smooth) + 0.03 * easeOut
        let shoulder = CGPoint(x: s.shoulder.x + shift, y: s.shoulder.y)
        let hip = CGPoint(x: s.hip.x + shift, y: s.hip.y)
        let hand = CGPoint(x: shoulder.x + radius * sin(arm), y: shoulder.y - radius * cos(arm))
        let elbow = joint(shoulder, hand, upperArm, forearm, bend: -1)
        // Non-throwing arm counter-swings for balance.
        let other = 0.25 - 0.25 * (arm - releaseArm)
        let otherElbow = CGPoint(x: shoulder.x + upperArm * sin(other), y: shoulder.y - upperArm * cos(other))
        let otherHand = CGPoint(x: otherElbow.x + 0.85 * forearm * sin(other + 0.45), y: otherElbow.y - 0.85 * forearm * cos(other + 0.45))
        return ThrowerPose(
            shoulder: shoulder, elbow: elbow, hand: hand, hip: hip,
            head: CGPoint(x: shoulder.x + neckToHead * sin(s.lean), y: shoulder.y + neckToHead * cos(s.lean)),
            frontKnee: joint(hip, s.frontAnkle, thigh, shank, bend: 1), frontAnkle: s.frontAnkle,
            backKnee: joint(hip, s.backAnkle, thigh, shank, bend: 1), backAnkle: s.backAnkle,
            otherElbow: otherElbow, otherHand: otherHand, lean: s.lean)
    }

    /// Two-link inverse kinematics: the middle joint between `a` and `b`, bent to the left of a→b (bend +1) or right (−1).
    static func joint(_ a: CGPoint, _ b: CGPoint, _ l1: Double, _ l2: Double, bend: Double) -> CGPoint {
        let dx = b.x - a.x, dy = b.y - a.y
        let length = hypot(dx, dy)
        guard length > 1e-9 else { return CGPoint(x: a.x, y: a.y - l1) }
        let ux = dx / length, uy = dy / length
        let d = min(max(length, abs(l1 - l2) + 1e-6), l1 + l2 - 1e-6)
        let along = (l1 * l1 - l2 * l2 + d * d) / (2 * d)
        let off = sqrt(max(l1 * l1 - along * along, 0))
        return CGPoint(x: a.x + ux * along - uy * off * bend, y: a.y + uy * along + ux * off * bend)
    }
}

// MARK: - Scene view

/// To-scale side view of one throw: thrower, bag flight, regulation board, 1 m grid.
struct LaunchScene: View {
    let params: LaunchParameters
    var ghosts: [LaunchParameters] = []
    var run: LaunchRun? = nil
    /// Playback rate (0.25 = slow motion).
    var rate: Double = 1
    /// Fixed scene time for offscreen rendering; nil = live.
    var frozenTime: Double? = nil

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.colorScheme) private var colorScheme
    @State private var finished: Date?

    /// Animate only a run that matches the parameters on screen, with Reduce Motion off; otherwise nil.
    static func activeRun(_ run: LaunchRun?, params: LaunchParameters, reduceMotion: Bool, frozenTime: Double?) -> LaunchRun? {
        guard frozenTime == nil, !reduceMotion, let run, run.params == params else { return nil }
        return run
    }

    /// Scene time to draw: the frozen time, the elapsed run time × rate, or ∞ (= final state) without an active run.
    static func sceneTime(run: LaunchRun?, params: LaunchParameters, reduceMotion: Bool, frozenTime: Double?, rate: Double, now: Date) -> Double {
        if let frozenTime { return frozenTime }
        guard let active = activeRun(run, params: params, reduceMotion: reduceMotion, frozenTime: nil) else { return .infinity }
        return now.timeIntervalSince(active.start) * rate
    }

    private var activeRun: LaunchRun? { Self.activeRun(run, params: params, reduceMotion: reduceMotion, frozenTime: frozenTime) }

    var body: some View {
        let run = activeRun
        TimelineView(.animation(minimumInterval: nil, paused: run == nil || finished == run?.start)) { timeline in
            Canvas { context, size in
                let time = Self.sceneTime(run: run, params: params, reduceMotion: reduceMotion, frozenTime: frozenTime, rate: rate, now: timeline.date)
                LaunchSceneRenderer(params: params, ghosts: ghosts, time: time, dark: colorScheme == .dark)
                    .draw(in: &context, size: size)
            }
        }
        .task(id: run.map { "\($0.start.timeIntervalSinceReferenceDate)/\(rate)" }) {
            guard let run else { return }
            let remaining = ThrowTimeline.total(run.params) / rate - Date().timeIntervalSince(run.start)
            if remaining > 0 { try? await Task.sleep(for: .seconds(remaining + 0.05)) }
            if !Task.isCancelled { finished = run.start }
        }
        .accessibilityElement()
        .accessibilityLabel("Side view of the throw, drawn to scale")
        .accessibilityValue(accessibilityDescription)
    }

    private var accessibilityDescription: String {
        let model = LaunchModel(params), hit = model.landing()
        return "Released at \(number(params.speed, digits: 2)) metres per second, \(number(params.angleDegrees, digits: 1)) degrees, from \(number(params.releaseHeight, digits: 2)) metres, \(number(params.distanceToBoard, digits: 2)) metres from the board. \(hit.kind.rawValue). \(model.zone().label)."
    }
}

// MARK: - Renderer

/// Draws one frame of the scene at scene time `time` (∞ = final state).
struct LaunchSceneRenderer {
    let params: LaunchParameters
    let ghosts: [LaunchParameters]
    let time: Double
    let dark: Bool

    private var wood: Color { dark ? Color(red: 0.60, green: 0.46, blue: 0.31) : Color(red: 0.86, green: 0.71, blue: 0.51) }
    private var woodEdge: Color { dark ? Color(red: 0.80, green: 0.64, blue: 0.44) : Color(red: 0.55, green: 0.39, blue: 0.22) }
    private var surface: Color { Color(nsColor: .controlBackgroundColor) }

    /// World (m) → view (pt) with equal scale on both axes, floor along the bottom margin.
    struct Transform {
        static let left: CGFloat = 40, right: CGFloat = 14, top: CGFloat = 12, bottom: CGFloat = 48
        let scale: CGFloat, xMin: Double, size: CGSize
        var floorY: CGFloat { size.height - Self.bottom }
        var visibleXMax: Double { xMin + Double((size.width - Self.left - Self.right) / scale) }
        var visibleYMax: Double { Double((size.height - Self.top - Self.bottom) / scale) }
        func callAsFunction(_ x: Double, _ y: Double) -> CGPoint {
            CGPoint(x: Self.left + CGFloat(x - xMin) * scale, y: floorY - CGFloat(y) * scale)
        }
        func callAsFunction(_ p: CGPoint) -> CGPoint { self(p.x, p.y) }
    }

    static func transform(for p: LaunchParameters, size: CGSize) -> Transform {
        let model = LaunchModel(p), hit = model.landing()
        let apex = p.vy > 0 ? p.releaseHeight + p.vy * p.vy / (2 * LaunchModel.gravity) : p.releaseHeight
        let xMin = -0.8
        // Fit [−0.8, D + 1.6] m; widen only when a long throw would land off screen.
        let xMax = max(p.distanceToBoard + 1.6, hit.horizontal + 0.5)
        let yMax = max(apex, 1.9) + 0.2
        let scale = min((size.width - Transform.left - Transform.right) / CGFloat(xMax - xMin),
                        (size.height - Transform.top - Transform.bottom) / CGFloat(yMax))
        return Transform(scale: max(scale, 1), xMin: xMin, size: size)
    }

    func draw(in ctx: inout GraphicsContext, size: CGSize) {
        guard size.width > 80, size.height > 80 else { return }
        let w = Self.transform(for: params, size: size)
        let model = LaunchModel(params), hit = model.landing()
        let flight = hit.time
        let tau = time - ThrowTimeline.swing                 // flight clock; < 0 during the swing
        let line = min(max(0.055 * w.scale, 2.5), 6)          // limb width, pt

        drawGrid(&ctx, w)
        drawDistance(&ctx, w)
        drawBoard(&ctx, w)
        for ghost in ghosts { drawGhost(&ctx, w, ghost) }

        // Model path (dashed) and what the bag has travelled so far.
        let path = model.trajectory(samples: 90)
        ctx.stroke(polyline(path.map { w($0.x, $0.y) }), with: .color(.primary.opacity(0.32)),
                   style: StrokeStyle(lineWidth: 1.2, lineCap: .round, dash: [4, 4]))
        drawReleaseAnnotations(&ctx, w)
        if tau > 0 {
            let end = min(tau, flight)
            let travelled = (0...60).map { i -> CGPoint in let t = end * Double(i) / 60; return w(position(t)) }
            ctx.stroke(polyline(travelled), with: .color(measuredInk.opacity(0.55)), style: StrokeStyle(lineWidth: 1.8, lineCap: .round, lineJoin: .round))
        }
        if tau >= 0, params.vy > 0 {
            let tApex = params.vy / LaunchModel.gravity
            if tApex < flight, tau >= tApex { drawApex(&ctx, w, tApex) }
        }

        // Thrower; the bag is in the hand until release.
        let pose = ThrowerPose.at(params, time: time.isFinite ? time : 10)
        drawFigure(&ctx, w, pose, line: line, near: false)
        if tau < 0 { drawBag(&ctx, w, center: pose.hand, angle: 0, alpha: 1) }
        drawFigure(&ctx, w, pose, line: line, near: true)

        if tau >= 0 {
            drawTrail(&ctx, w, tau: tau, flight: flight)
            let (center, angle) = bagState(tau: tau, hit: hit)
            drawBag(&ctx, w, center: center, angle: angle, alpha: 1)
        }
        if tau >= flight { drawLanding(&ctx, w, hit: hit, progress: min((tau - flight) / 0.3, 1)) }
        drawClock(&ctx, w, tau: tau, flight: flight)
    }

    // MARK: Kinematics

    private func position(_ t: Double) -> CGPoint {
        CGPoint(x: params.vx * t, y: params.releaseHeight + params.vy * t - 0.5 * LaunchModel.gravity * t * t)
    }

    /// Bag centre and orientation: along the velocity in flight, lying on the surface after first contact.
    private func bagState(tau: Double, hit: LaunchModel.Landing) -> (CGPoint, Double) {
        if tau < hit.time {
            return (position(tau), atan2(params.vy - LaunchModel.gravity * tau, params.vx))
        }
        let half = 0.06
        let contact = landingPoint(hit)
        switch hit.kind {
        case .onBoard:
            let a = params.board.angle
            return (CGPoint(x: contact.x - half * sin(a), y: contact.y + half * cos(a)), a)
        case .frontOfBoard:
            return (CGPoint(x: contact.x - half, y: max(contact.y, half)), .pi / 2)
        case .shortOfBoard, .pastBoard:
            return (CGPoint(x: contact.x, y: half), 0)
        }
    }

    private func landingPoint(_ hit: LaunchModel.Landing) -> CGPoint {
        let p = position(hit.time)
        return CGPoint(x: hit.horizontal, y: hit.kind == .shortOfBoard || hit.kind == .pastBoard ? 0 : p.y)
    }

    // MARK: Layers

    private func drawGrid(_ ctx: inout GraphicsContext, _ w: Transform) {
        let gridColor = Color.primary.opacity(dark ? 0.10 : 0.07)
        var grid = Path()
        let right = w.size.width - Transform.right
        for i in Int(ceil(w.xMin))...max(Int(floor(w.visibleXMax)), 0) {
            let x = w(Double(i), 0).x
            grid.move(to: CGPoint(x: x, y: w.floorY)); grid.addLine(to: CGPoint(x: x, y: Transform.top))
            ctx.draw(Text(i == 0 ? "0 m" : "\(i)").font(.caption2).monospacedDigit().foregroundStyle(.secondary),
                     at: CGPoint(x: x, y: w.floorY + 38), anchor: .center)
        }
        for j in 1...max(Int(floor(w.visibleYMax)), 1) {
            let y = w(0, Double(j)).y
            grid.move(to: CGPoint(x: Transform.left, y: y)); grid.addLine(to: CGPoint(x: right, y: y))
            ctx.draw(Text("\(j) m").font(.caption2).monospacedDigit().foregroundStyle(.secondary),
                     at: CGPoint(x: Transform.left - 6, y: y), anchor: .trailing)
        }
        ctx.stroke(grid, with: .color(gridColor), lineWidth: 1)
        // Ground: a soft band and a crisp floor line.
        ctx.fill(Path(CGRect(x: Transform.left, y: w.floorY, width: right - Transform.left, height: 7)),
                 with: .linearGradient(Gradient(colors: [.primary.opacity(0.10), .primary.opacity(0)]),
                                       startPoint: CGPoint(x: 0, y: w.floorY), endPoint: CGPoint(x: 0, y: w.floorY + 7)))
        var floor = Path(); floor.move(to: CGPoint(x: Transform.left, y: w.floorY)); floor.addLine(to: CGPoint(x: right, y: w.floorY))
        ctx.stroke(floor, with: .color(.primary.opacity(0.55)), lineWidth: 1.5)
    }

    /// Horizontal dimension: release point to the board's front edge.
    private func drawDistance(_ ctx: inout GraphicsContext, _ w: Transform) {
        let y = w.floorY + 19
        let a = w(0, 0).x, b = w(params.distanceToBoard, 0).x
        var dim = Path()
        dim.move(to: CGPoint(x: a, y: y)); dim.addLine(to: CGPoint(x: b, y: y))
        for x in [a, b] { dim.move(to: CGPoint(x: x, y: y - 4)); dim.addLine(to: CGPoint(x: x, y: y + 4)) }
        ctx.stroke(dim, with: .color(.secondary.opacity(0.8)), lineWidth: 1)
        label(&ctx, "\(number(params.distanceToBoard, digits: 2)) m release → board", at: CGPoint(x: (a + b) / 2, y: y), anchor: .center, knockout: true)
    }

    private func deckPoint(_ along: Double) -> CGPoint {
        let b = params.board
        return CGPoint(x: params.distanceToBoard + along * cos(b.angle), y: b.frontHeight + along * sin(b.angle))
    }

    private func drawBoard(_ ctx: inout GraphicsContext, _ w: Transform) {
        let b = params.board, d = params.distanceToBoard
        let back = deckPoint(b.length)
        var apron = Path()
        apron.move(to: w(d, 0)); apron.addLine(to: w(d, b.frontHeight)); apron.addLine(to: w(back))
        apron.addLine(to: w(back.x, 0)); apron.closeSubpath()
        ctx.fill(apron, with: .color(wood.opacity(0.75)))
        ctx.stroke(apron, with: .color(woodEdge.opacity(0.7)), lineWidth: 1)

        // Deck surface with the hole as a gap.
        let holeStart = b.holeAlong - b.holeRadius, holeEnd = b.holeAlong + b.holeRadius
        var deck = Path()
        deck.move(to: w(deckPoint(0))); deck.addLine(to: w(deckPoint(holeStart)))
        deck.move(to: w(deckPoint(holeEnd))); deck.addLine(to: w(deckPoint(b.length)))
        ctx.stroke(deck, with: .color(woodEdge), style: StrokeStyle(lineWidth: max(2, 0.03 * w.scale), lineCap: .butt))
        var hole = Path()
        let depth = 0.035
        hole.move(to: w(deckPoint(holeStart))); hole.addLine(to: w(deckPoint(holeEnd)))
        hole.addLine(to: w(deckPoint(holeEnd).x, deckPoint(holeEnd).y - depth))
        hole.addLine(to: w(deckPoint(holeStart).x, deckPoint(holeStart).y - depth)); hole.closeSubpath()
        ctx.fill(hole, with: .color(.black.opacity(dark ? 0.7 : 0.55)))

        // Where first contact scores: hole window (green) and board (yellow), 3 pt strips just above the surface.
        let slideAllowance = 0.45, slideUp = 0.30
        func strip(_ from: CGPoint, _ to: CGPoint, _ zone: LandingZone) {
            var p = Path()
            let a = w(from), c = w(to)
            let dx = c.x - a.x, dy = c.y - a.y, len = max(hypot(dx, dy), 1e-6)
            let nx = dy / len * 4, ny = -dx / len * 4       // 4 pt above the surface
            p.move(to: CGPoint(x: a.x + nx, y: a.y + ny)); p.addLine(to: CGPoint(x: c.x + nx, y: c.y + ny))
            ctx.stroke(p, with: .color(zone.color.opacity(0.9)), style: StrokeStyle(lineWidth: 3, lineCap: .butt))
        }
        let windowStart = max(b.holeAlong - slideAllowance, 0)
        strip(CGPoint(x: d - slideUp, y: 0), CGPoint(x: d, y: 0), .board)
        strip(deckPoint(0), deckPoint(windowStart), .board)
        strip(deckPoint(windowStart), deckPoint(holeEnd), .hole)
        strip(deckPoint(holeEnd), deckPoint(b.length), .board)
    }

    private func drawGhost(_ ctx: inout GraphicsContext, _ w: Transform, _ ghost: LaunchParameters) {
        var g = ghost; g.distanceToBoard = params.distanceToBoard; g.board = params.board
        let model = LaunchModel(g)
        let points = model.trajectory(samples: 60).map { w($0.x, $0.y) }
        ctx.stroke(polyline(points), with: .color(.primary.opacity(0.25)), style: StrokeStyle(lineWidth: 1.5, lineCap: .round, lineJoin: .round))
        if let last = points.last {
            ctx.fill(Path(ellipseIn: CGRect(x: last.x - 3, y: last.y - 3, width: 6, height: 6)), with: .color(.primary.opacity(0.25)))
        }
    }

    /// Release height, release angle and velocity vector at the release point.
    private func drawReleaseAnnotations(_ ctx: inout GraphicsContext, _ w: Transform) {
        let h = params.releaseHeight, theta = params.angleDegrees * .pi / 180
        let release = w(0, h), floor = w(0, 0)
        let ink = Color.secondary

        var height = Path()
        height.move(to: floor); height.addLine(to: release)
        ctx.stroke(height, with: .color(ink.opacity(0.8)), style: StrokeStyle(lineWidth: 1, dash: [2, 3]))
        var ticks = Path()
        ticks.move(to: CGPoint(x: floor.x - 4, y: floor.y)); ticks.addLine(to: CGPoint(x: floor.x + 4, y: floor.y))
        ctx.stroke(ticks, with: .color(ink), lineWidth: 1)
        label(&ctx, "h \(number(h, digits: 2)) m", at: CGPoint(x: release.x + 6, y: (release.y + floor.y) / 2), anchor: .leading)

        // Angle: horizontal reference and an arc from 0 to θ.
        let r = max(0.42 * w.scale, 22)
        var reference = Path()
        reference.move(to: release); reference.addLine(to: CGPoint(x: release.x + r * 1.35, y: release.y))
        ctx.stroke(reference, with: .color(ink.opacity(0.8)), style: StrokeStyle(lineWidth: 1, dash: [2, 3]))
        var arc = Path()
        arc.addArc(center: release, radius: r, startAngle: .zero, endAngle: .radians(-theta), clockwise: theta > 0)
        ctx.stroke(arc, with: .color(ink), lineWidth: 1)
        let mid = abs(theta) < 0.3 ? (theta >= 0 ? -0.22 : 0.22) : theta / 2
        label(&ctx, "\(number(params.angleDegrees, digits: 1))°",
              at: CGPoint(x: release.x + (r + 5) * cos(mid), y: release.y - (r + 5) * sin(mid)), anchor: .leading)

        // Velocity vector, 0.09 m per m/s.
        let length = CGFloat(params.speed * 0.09) * w.scale
        let tip = CGPoint(x: release.x + length * cos(theta), y: release.y - length * sin(theta))
        var arrow = Path()
        arrow.move(to: release); arrow.addLine(to: tip)
        let head: CGFloat = 7
        for side in [-0.45, 0.45] {
            arrow.move(to: tip)
            arrow.addLine(to: CGPoint(x: tip.x - head * cos(theta + side), y: tip.y + head * sin(theta + side)))
        }
        ctx.stroke(arrow, with: .color(.primary.opacity(0.8)), style: StrokeStyle(lineWidth: 1.6, lineCap: .round, lineJoin: .round))
        // Just beyond the tip, clear of the thrower and the angle label; the knockout masks the path beneath.
        label(&ctx, "\(number(params.speed, digits: 2)) m/s", at: CGPoint(x: tip.x + 6 * cos(theta) + 3, y: tip.y - 6 * sin(theta) - 3),
              anchor: .leading, knockout: true)
    }

    private func drawApex(_ ctx: inout GraphicsContext, _ w: Transform, _ tApex: Double) {
        let apex = position(tApex)
        let p = w(apex)
        ctx.stroke(Path(ellipseIn: CGRect(x: p.x - 3.5, y: p.y - 3.5, width: 7, height: 7)), with: .color(.primary.opacity(0.7)), lineWidth: 1.2)
        // A flat throw peaks right beside the hand, where the release labels already sit.
        if apex.x > params.speed * 0.09 * cos(params.angleDegrees * .pi / 180) + 1.1 { label(&ctx, "apex \(number(apex.y, digits: 2)) m", at: CGPoint(x: p.x, y: p.y - 8), anchor: .bottom) }
    }

    private func drawFigure(_ ctx: inout GraphicsContext, _ w: Transform, _ pose: ThrowerPose, line: CGFloat, near: Bool) {
        func limb(_ points: [CGPoint], width: CGFloat, color: Color) {
            ctx.stroke(polyline(points.map { w($0) }), with: .color(color), style: StrokeStyle(lineWidth: width, lineCap: .round, lineJoin: .round))
        }
        func foot(_ ankle: CGPoint) -> [CGPoint] {
            [ankle, CGPoint(x: ankle.x + ThrowerPose.footLength * 0.85, y: 0.02)]
        }
        let ink = Color.primary.opacity(dark ? 0.9 : 0.82)
        if near {
            // Throwing side (nearest the camera): back leg, trunk, head, throwing arm.
            limb([pose.hip, pose.backKnee, pose.backAnkle] + foot(pose.backAnkle).dropFirst(), width: line, color: ink)
            let neck = CGPoint(x: pose.shoulder.x + 0.05 * sin(pose.lean), y: pose.shoulder.y + 0.05 * cos(pose.lean))
            limb([pose.hip, pose.shoulder, neck], width: line * 1.45, color: ink)
            let head = w(pose.head)
            let r = CGFloat(ThrowerPose.headRadius) * w.scale
            ctx.fill(Path(ellipseIn: CGRect(x: head.x - r, y: head.y - r, width: 2 * r, height: 2 * r)), with: .color(ink))
            limb([pose.shoulder, pose.elbow, pose.hand], width: line, color: ink)
        } else {
            // Far side, drawn lighter: stepping leg and the balancing arm.
            let far = Color.primary.opacity(dark ? 0.38 : 0.30)
            limb([pose.hip, pose.frontKnee, pose.frontAnkle] + foot(pose.frontAnkle).dropFirst(), width: line, color: far)
            limb([pose.shoulder, pose.otherElbow, pose.otherHand], width: line, color: far)
        }
    }

    private func drawBag(_ ctx: inout GraphicsContext, _ w: Transform, center: CGPoint, angle: Double, alpha: Double) {
        let side = max(CGFloat(0.12) * w.scale, 7)
        let c = w(center)
        let rect = CGRect(x: -side / 2, y: -side / 2, width: side, height: side)
        let shape = Path(roundedRect: rect, cornerRadius: side * 0.28)
            .applying(CGAffineTransform(translationX: c.x, y: c.y).rotated(by: -angle))
        ctx.fill(shape, with: .color(measuredInk.opacity(alpha)))
        ctx.stroke(shape, with: .color(.black.opacity(0.35 * alpha)), lineWidth: 0.8)
    }

    /// The last 0.25 s of flight as a tapering, fading ribbon; it fades out after first contact.
    private func drawTrail(_ ctx: inout GraphicsContext, _ w: Transform, tau: Double, flight: Double) {
        let fade = tau <= flight ? 1 : max(0, 1 - (tau - flight) / 0.25)
        guard fade > 0 else { return }
        let end = min(tau, flight), start = max(end - 0.25, 0)
        let n = 20
        var previous = w(position(start))
        for i in 1...n {
            let t = start + (end - start) * Double(i) / Double(n)
            let point = w(position(t))
            var seg = Path(); seg.move(to: previous); seg.addLine(to: point)
            let k = Double(i) / Double(n)
            ctx.stroke(seg, with: .color(measuredInk.opacity(0.75 * k * fade)),
                       style: StrokeStyle(lineWidth: 1.5 + 4.5 * k, lineCap: .round))
            previous = point
        }
    }

    private func drawLanding(_ ctx: inout GraphicsContext, _ w: Transform, hit: LaunchModel.Landing, progress: Double) {
        let zone = LaunchModel.zone(for: hit, distance: params.distanceToBoard, board: params.board)
        let p = w(landingPoint(hit))
        // Ease-out-back "pop".
        let c1 = 1.70158, c3 = c1 + 1, u = progress - 1
        let pop = CGFloat(1 + c3 * u * u * u + c1 * u * u)
        let r = 8 * pop
        let ring = Path(ellipseIn: CGRect(x: p.x - r, y: p.y - r, width: 2 * r, height: 2 * r))
        ctx.fill(ring, with: .color(zone.color.opacity(0.22)))
        ctx.stroke(ring, with: .color(zone.color), lineWidth: 2)

        let text = Text(Image(systemName: zone.symbol)) + Text(" \(zone.label)").fontWeight(.semibold) + Text(" · \(landingDetail(hit, zone: zone))")
        let resolved = ctx.resolve(text.font(.caption).foregroundStyle(zone.color))
        let size = resolved.measure(in: CGSize(width: 400, height: 40))
        let top = min(p.y, w(deckPoint(params.board.length)).y) - 16
        let x = min(max(p.x, Transform.left + size.width / 2 + 4), w.size.width - Transform.right - size.width / 2 - 4)
        var labelContext = ctx
        labelContext.opacity = min(progress * 1.6, 1)
        let box = CGRect(x: x - size.width / 2 - 5, y: top - size.height - 3, width: size.width + 10, height: size.height + 6)
        labelContext.fill(Path(roundedRect: box, cornerRadius: 6), with: .color(surface.opacity(0.92)))
        labelContext.stroke(Path(roundedRect: box, cornerRadius: 6), with: .color(zone.color.opacity(0.5)), lineWidth: 1)
        labelContext.draw(resolved, at: CGPoint(x: x, y: top), anchor: .bottom)
    }

    private func landingDetail(_ hit: LaunchModel.Landing, zone: LandingZone) -> String {
        switch hit.kind {
        case .onBoard:
            let cm = (hit.distanceToHole ?? 0) * 100
            return abs(cm) < 0.5 ? "on the hole centre" : "\(number(abs(cm), digits: 0)) cm \(cm < 0 ? "short of" : "past") the hole centre"
        case .shortOfBoard:
            let short = params.distanceToBoard - hit.horizontal
            return "\(number(short * 100, digits: 0)) cm short of the board"
        case .frontOfBoard: return "hits the front face"
        case .pastBoard: return "flies past the board"
        }
    }

    private func drawClock(_ ctx: inout GraphicsContext, _ w: Transform, tau: Double, flight: Double) {
        let text = tau < 0 ? "swing" : "t = \(number(min(tau, flight), digits: 2)) s"
        ctx.draw(Text(text).font(.caption.monospacedDigit()).foregroundStyle(.secondary),
                 at: CGPoint(x: w.size.width - Transform.right - 2, y: Transform.top + 2), anchor: .topTrailing)
    }

    // MARK: Helpers

    private func label(_ ctx: inout GraphicsContext, _ string: String, at point: CGPoint, anchor: UnitPoint, knockout: Bool = false) {
        let resolved = ctx.resolve(Text(string).font(.caption2).monospacedDigit().foregroundStyle(.secondary))
        if knockout {
            let size = resolved.measure(in: CGSize(width: 300, height: 30))
            let origin = CGPoint(x: point.x - anchor.x * size.width, y: point.y - anchor.y * size.height)
            ctx.fill(Path(roundedRect: CGRect(origin: origin, size: size).insetBy(dx: -4, dy: -1), cornerRadius: 3), with: .color(surface))
        }
        ctx.draw(resolved, at: point, anchor: anchor)
    }

    private func polyline(_ points: [CGPoint]) -> Path {
        var p = Path()
        guard let first = points.first else { return p }
        p.move(to: first)
        for point in points.dropFirst() { p.addLine(to: point) }
        return p
    }
}
