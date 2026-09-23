import SwiftUI

/// Animated stick figure: body parameters → pendulum swing → release → flight → first contact.
struct SwingExplorerPanel: View {
    @State private var p = SwingParameters()
    @State private var ghost: SwingParameters?
    @State private var playStart: Date?
    @State private var scrub = 0.0          // 0…1 of the whole animation when paused

    private var model: SwingModel { SwingModel(p) }

    var body: some View {
        HStack(alignment: .top, spacing: 26) {
            controls.frame(width: 320)
            VStack(alignment: .leading, spacing: 12) {
                TimelineView(.animation(minimumInterval: nil, paused: playStart == nil)) { context in
                    scene(time: animationTime(now: context.date))
                }
                .frame(height: 300)
                .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 10))
                HStack {
                    Button { playStart = playStart == nil ? Date() : nil } label: {
                        Label(playStart == nil ? "Play throw" : "Pause", systemImage: playStart == nil ? "play.fill" : "pause.fill")
                    }
                    Slider(value: $scrub, in: 0...1).disabled(playStart != nil)
                    Button("Keep as comparison") { ghost = p }
                    if ghost != nil { Button("Clear") { ghost = nil } }
                }
                readout
            }
        }
        .onAppear { if let t = model.swingTimeToHitHole() { p.forwardSwingTime = t } }
    }

    // MARK: controls
    private var controls: some View {
        VStack(alignment: .leading, spacing: 12) {
            slider("Arm angle at release", $p.releaseArmDeg, 5...80, 0.5, "°", 1, help: "0° = arm straight down, 90° = pointing at the board")
            slider("Backswing height", $p.backswingDeg, -110...(-10), 1, "°", 0, help: "negative = arm behind the body")
            slider("Forward-swing time", $p.forwardSwingTime, 0.2...1.0, 0.005, "s", 3, help: "shorter = faster arm")
            slider("Step speed at release", $p.stepSpeed, 0...1.2, 0.01, "m/s", 2, help: "body moving toward the board")
            slider("Knee bend", $p.crouch, 0...0.35, 0.005, "m", 2, help: "how much the shoulder is lowered")
            slider("Body height", $p.bodyHeight, 1.4...2.1, 0.01, "m", 2, help: "sets arm length and shoulder height")
            slider("Shoulder to board front", $p.shoulderToBoard, 6...9.5, 0.05, "m", 2, help: "measure this at your setup")
            Button("Find swing speed that reaches the hole") { if let t = model.swingTimeToHitHole() { p.forwardSwingTime = t } }
        }
    }

    private func slider(_ title: String, _ value: Binding<Double>, _ range: ClosedRange<Double>, _ step: Double,
                        _ unit: String, _ digits: Int, help: String) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            HStack { Text(title); Spacer(); Text("\(number(value.wrappedValue, digits: digits)) \(unit)").monospacedDigit() }
            Slider(value: value, in: range, step: step)
            Text(help).font(.caption2).foregroundStyle(.secondary)
        }
    }

    // MARK: readout
    private var readout: some View {
        Group {
            if let r = model.release(), let launch = model.launch() {
                let landing = LaunchModel(launch).landing()
                VStack(alignment: .leading, spacing: 6) {
                    Text("Release: \(number(r.angleDegrees, digits: 1))° at \(number(r.speed, digits: 2)) m/s from \(number(r.height, digits: 2)) m")
                        .font(.headline).monospacedDigit()
                    Text("Arm speed at release \(number(r.armAngularSpeed * 180 / .pi, digits: 0))°/s × arm radius \(number(model.radius, digits: 2)) m = \(number(r.armAngularSpeed * model.radius, digits: 2)) m/s, plus the step. With no step the launch angle equals the arm angle (\(number(p.releaseArmDeg, digits: 1))°).")
                        .font(.callout).foregroundStyle(.secondary)
                    let zone = zoneName(landing)
                    Label("\(landing.kind.rawValue)\(landing.distanceToHole.map { " · \(number(abs($0) * 100, digits: 0)) cm \($0 > 0 ? "past" : "short of") the hole centre" } ?? "")",
                          systemImage: ZoneStyle.symbol(zone)).foregroundStyle(ZoneStyle.color(zone)).font(.callout.weight(.semibold))
                    sensitivity
                }
            } else {
                Label("The arm never reaches this release angle: it must lie between the backswing and the end of the follow-through.", systemImage: "exclamationmark.triangle")
                    .foregroundStyle(.orange)
            }
        }
    }

    private var sensitivity: some View {
        let base = landingX(p)
        func change(_ label: String, _ edit: (inout SwingParameters) -> Void) -> (String, Double?) {
            var q = p; edit(&q); let x = landingX(q)
            return (label, base.flatMap { b in x.map { ($0 - b) * 100 } })
        }
        let rows = [change("Release 5° later (arm higher)") { $0.releaseArmDeg += 5 },
                    change("Swing 10 % faster") { $0.forwardSwingTime *= 0.9 },
                    change("Backswing 10° higher") { $0.backswingDeg -= 10 },
                    change("Step 0.2 m/s faster") { $0.stepSpeed += 0.2 },
                    change("Bend knees 5 cm more") { $0.crouch += 0.05 }]
        return VStack(alignment: .leading, spacing: 3) {
            Text("What moves the landing? (first-contact change)").font(.subheadline.weight(.semibold))
            ForEach(rows, id: \.0) { row in
                HStack { Text(row.0); Spacer(); Text(row.1.map { "\($0 >= 0 ? "+" : "")\(number($0, digits: 0)) cm" } ?? "—").monospacedDigit() }
                    .font(.callout)
            }
        }.frame(maxWidth: 420)
    }

    private func landingX(_ q: SwingParameters) -> Double? {
        let m = SwingModel(q)
        guard let r = m.release(), let launch = m.launch() else { return nil }
        return r.x(stepSpeed: q.stepSpeed) + LaunchModel(launch).landing().horizontal
    }

    private func zoneName(_ landing: LaunchModel.Landing) -> String {
        switch landing.kind {
        case .onBoard: return (landing.distanceToHole.map { $0 >= -0.45 && $0 <= 0.0762 } ?? false) ? "green" : "yellow"
        case .shortOfBoard: return landing.horizontal >= (model.launch()?.distanceToBoard ?? 0) - 0.30 ? "yellow" : "red"
        default: return "red"
        }
    }

    // MARK: animation
    private var totalDuration: Double {
        guard let r = model.release(), let launch = model.launch() else { return p.forwardSwingTime }
        return r.time + LaunchModel(launch).landing().time + 0.4
    }

    private func animationTime(now: Date) -> Double {
        guard let start = playStart else { return scrub * totalDuration }
        let t = now.timeIntervalSince(start)
        if t > totalDuration { DispatchQueue.main.async { playStart = nil; scrub = 1 } }
        return min(t, totalDuration)
    }

    private func scene(time: Double) -> some View {
        Canvas { context, size in
            let board = BoardGeometry.regulation
            let xMin = -1.0, xMax = p.shoulderToBoard + board.length * cos(board.angle) + 0.4
            let yMax = 2.6
            let scale = min(size.width / (xMax - xMin), size.height / yMax)   // equal metres on both axes
            func pt(_ x: Double, _ y: Double) -> CGPoint { CGPoint(x: (x - xMin) * scale, y: size.height - 8 - y * scale) }
            // Floor and board.
            var floor = Path(); floor.move(to: pt(xMin, 0)); floor.addLine(to: pt(xMax, 0))
            context.stroke(floor, with: .color(.secondary), lineWidth: 1)
            var deck = Path()
            deck.move(to: pt(p.shoulderToBoard, 0)); deck.addLine(to: pt(p.shoulderToBoard, board.frontHeight))
            deck.addLine(to: pt(p.shoulderToBoard + board.length * cos(board.angle), board.frontHeight + board.length * sin(board.angle)))
            context.stroke(deck, with: .color(.primary), lineWidth: 3)
            let hole = pt(p.shoulderToBoard + board.holeAlong * cos(board.angle), board.frontHeight + board.holeAlong * sin(board.angle))
            context.stroke(Path(ellipseIn: CGRect(x: hole.x - 4, y: hole.y - 4, width: 8, height: 8)), with: .color(.primary), lineWidth: 1.5)
            if let ghost { drawPath(context, SwingModel(ghost), pt, dashed: true) }
            drawPath(context, model, pt, dashed: false)
            drawFigure(context, time: time, pt: pt, scale: scale)
        }
        .accessibilityLabel("Animated throw: stick figure swings, releases the bag, and the bag flies to the board")
    }

    private func drawPath(_ context: GraphicsContext, _ m: SwingModel, _ pt: (Double, Double) -> CGPoint, dashed: Bool) {
        guard let r = m.release(), let launch = m.launch() else { return }
        let x0 = r.x(stepSpeed: m.p.stepSpeed)
        var path = Path()
        for (i, q) in LaunchModel(launch).trajectory(samples: 80).enumerated() {
            let point = pt(x0 + q.x, q.y)
            if i == 0 { path.move(to: point) } else { path.addLine(to: point) }
        }
        context.stroke(path, with: .color(dashed ? Color.secondary : scoredInk),
                       style: StrokeStyle(lineWidth: dashed ? 1.5 : 2, dash: dashed ? [5, 4] : []))
    }

    private func drawFigure(_ context: GraphicsContext, time: Double, pt: (Double, Double) -> CGPoint, scale: Double) {
        let release = model.release()
        let swingTime = min(time, p.forwardSwingTime)
        let j = model.figure(at: swingTime)
        func P(_ k: String) -> CGPoint { pt(j[k]!.x, j[k]!.y) }
        var body = Path()
        for (a, b) in [("head", "shoulder"), ("shoulder", "hip"), ("hip", "front_knee"), ("front_knee", "front_foot"),
                       ("hip", "back_knee"), ("back_knee", "back_foot"), ("shoulder", "elbow"), ("elbow", "hand")] {
            body.move(to: P(a)); body.addLine(to: P(b))
        }
        context.stroke(body, with: .color(.primary), style: StrokeStyle(lineWidth: 3, lineCap: .round))
        let head = P("head")
        context.fill(Path(ellipseIn: CGRect(x: head.x - 0.1 * scale, y: head.y - 0.2 * scale, width: 0.2 * scale, height: 0.2 * scale)), with: .color(.primary))
        // Bag: in the hand until release, then on the flight path until first contact.
        var bag = P("hand")
        if let r = release, let launch = model.launch(), time >= r.time {
            let flight = LaunchModel(launch)
            let tf = min(time - r.time, flight.landing().time)
            bag = pt(r.x(stepSpeed: p.stepSpeed) + launch.vx * tf, launch.releaseHeight + launch.vy * tf - 0.5 * LaunchModel.gravity * tf * tf)
        }
        context.fill(Path(CGRect(x: bag.x - 5, y: bag.y - 5, width: 10, height: 10)), with: .color(missInk))
    }
}
