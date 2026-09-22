import SwiftUI

struct PhysicsFlightCanvas: View {
    var parameters: TossParameters
    var result: TossResult
    var referenceParameters: TossParameters?
    var reference: TossResult?
    var time: Double
    var prediction: Bool
    var swing: SwingParameters? = nil

    var body: some View {
        Canvas { context, size in
            let board = TossBoard(distance: parameters.distance, angleDegrees: parameters.boardAngle)
            let all = result.samples + (reference?.samples ?? [])
            let maxX = max(board.point(u: board.length, y: 0).x+0.8, all.map(\.position.x).max() ?? 10)
            let minX = min(swing == nil ? -0.35 : -1.5, all.map(\.position.x).min() ?? 0)
            let maxZ = max(3, (all.map(\.position.z).max() ?? 3)+0.35)
            let scale = min((size.width-60)/(maxX-minX), (size.height-40)/maxZ)
            let base = size.height-25.0
            func point(_ v: TossVector) -> CGPoint { .init(x: 40+(v.x-minX)*scale, y: base-v.z*scale) }
            for z in 0...Int(maxZ) {
                var line = Path(); line.move(to: point(.init(x: minX, z: Double(z))))
                line.addLine(to: point(.init(x: maxX, z: Double(z))))
                context.stroke(line, with: .color(.secondary.opacity(0.16)), lineWidth: 1)
                context.draw(Text("\(z)m").font(.caption2).foregroundStyle(.secondary), at: CGPoint(x: 17, y: base-Double(z)*scale))
            }
            for x in stride(from: 0, through: Int(maxX), by: 2) {
                context.draw(Text("\(x)m").font(.caption2).foregroundStyle(.secondary), at: CGPoint(x: point(.init(x: Double(x))).x, y: base+13))
            }
            func drawBoard(_ b: TossBoard, color: Color) {
                var path = Path(); path.move(to: point(b.origin)); path.addLine(to: point(b.point(u: b.length, y: 0)))
                context.stroke(path, with: .color(color), style: StrokeStyle(lineWidth: 5, lineCap: .round))
                let hole = point(b.hole)
                context.fill(Path(ellipseIn: CGRect(x: hole.x-3, y: hole.y-3, width: 6, height: 6)), with: .color(.primary))
            }
            if let rp = referenceParameters, (rp.distance != parameters.distance || rp.boardAngle != parameters.boardAngle) {
                drawBoard(TossBoard(distance: rp.distance, angleDegrees: rp.boardAngle), color: .orange.opacity(0.5))
            }
            drawBoard(board, color: .brown)
            func trajectory(_ samples: [TossSample], color: Color, dashed: Bool) {
                guard let first = samples.first else { return }
                var path = Path(); path.move(to: point(first.position))
                for s in samples.dropFirst() { path.addLine(to: point(s.position)) }
                context.stroke(path, with: .color(color), style: StrokeStyle(lineWidth: 2, dash: dashed ? [5, 4] : []))
            }
            if prediction, let ref = reference { trajectory(ref.samples, color: .orange.opacity(0.8), dashed: true) }
            if prediction { trajectory(result.samples, color: .blue.opacity(0.25), dashed: true) }
            trajectory(result.samples.filter { $0.time <= time }, color: .blue, dashed: false)
            if let swing {
                let model = SwingMechanics(parameters: swing)
                let pose = model.pose(at: min(swing.duration, max(0, swing.releaseTime+time)))
                let shift = TossVector(x: model.release.wrist.x)
                func limb(_ a: TossVector, _ b: TossVector, color: Color, width: Double = 3) {
                    var line = Path(); line.move(to: point(a-shift)); line.addLine(to: point(b-shift))
                    context.stroke(line, with: .color(color), style: .init(lineWidth: width, lineCap: .round))
                }
                let hip = swing.bodyBase+TossVector(z: swing.bodyHeight*0.51)
                limb(hip, swing.bodyBase+TossVector(z: swing.bodyHeight*0.88), color: .secondary)
                limb(hip, swing.bodyBase+TossVector(x: -0.2), color: .secondary)
                limb(hip, swing.bodyBase+TossVector(x: 0.2), color: .secondary)
                let head = point(swing.bodyBase+TossVector(z: swing.bodyHeight*0.94)-shift)
                let r = swing.bodyHeight*0.06*scale
                context.stroke(Path(ellipseIn: .init(x: head.x-r,y: head.y-r,width: 2*r,height: 2*r)), with: .color(.secondary), lineWidth: 2)
                limb(pose.shoulder, pose.elbow, color: .blue)
                limb(pose.elbow, pose.wrist, color: .cyan)
                if time < 0 {
                    let bag = point(pose.wrist-shift)
                    context.fill(Path(roundedRect: .init(x: bag.x-5,y: bag.y-5,width: 10,height: 10),cornerRadius: 2), with: .color(.orange))
                }
            }
            if time >= 0, let sample = result.sample(at: time) {
                let p = point(sample.position)
                context.fill(Path(roundedRect: CGRect(x: p.x-6, y: p.y-6, width: 12, height: 12), cornerRadius: 3), with: .color(.blue))
                // A velocity arrow with a fixed time scale (0.08 s), not another path.
                if sample.velocity.length > 0 {
                    let end = point(sample.position+sample.velocity*0.08)
                    var arrow = Path(); arrow.move(to: p); arrow.addLine(to: end)
                    context.stroke(arrow, with: .color(.blue), lineWidth: 2)
                    context.fill(Path(ellipseIn: CGRect(x: end.x-2, y: end.y-2, width: 4, height: 4)), with: .color(.blue))
                }
            }
            context.draw(Text("SIDE VIEW · equal distance scale · velocity vector × 0.08 s").font(.caption2).foregroundStyle(.secondary),
                         at: CGPoint(x: 42, y: 8), anchor: .topLeading)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Side view of the simulated throw at \(number(time, digits: 2)) seconds. Horizontal axis forward distance; vertical axis height, in meters.")
    }
}

struct PhysicsBoardCanvas: View {
    var parameters: TossParameters
    var result: TossResult
    var reference: TossResult?
    var time: Double
    var prediction: Bool

    var body: some View {
        Canvas { context, size in
            let board = TossBoard(distance: parameters.distance, angleDegrees: parameters.boardAngle)
            let scale = min((size.width-65)/(board.width+0.2), (size.height-55)/(board.length+0.16))
            func point(_ p: TossVector) -> CGPoint {
                // Top projection: convert horizontal x to along-deck coordinate at its plane height.
                let u = (p.x-board.distance)/cos(board.angle)
                return .init(x: size.width/2+p.y*scale, y: size.height-30-u*scale)
            }
            let front = point(board.origin), back = point(board.point(u: board.length, y: 0))
            let rect = CGRect(x: front.x-board.width*scale/2, y: back.y, width: board.width*scale, height: board.length*scale)
            context.fill(Path(CGRect(x: 0, y: 22, width: size.width, height: size.height-44)), with: .color(.red.opacity(0.05)))
            context.fill(Path(roundedRect: rect, cornerRadius: 4), with: .color(.yellow.opacity(0.22)))
            context.stroke(Path(roundedRect: rect, cornerRadius: 4), with: .color(.brown), lineWidth: 2)
            let center = point(board.hole), radius = board.holeRadius*scale
            context.fill(Path(ellipseIn: CGRect(x: center.x-radius, y: center.y-radius, width: 2*radius, height: 2*radius)), with: .color(.green.opacity(0.7)))
            context.draw(Text("BOARD · top projection").font(.caption2).foregroundStyle(.secondary), at: CGPoint(x: size.width/2, y: 8))
            context.draw(Text("← left       right →").font(.caption2).foregroundStyle(.secondary), at: CGPoint(x: size.width/2, y: size.height-9))
            context.draw(Text("far").font(.caption2).foregroundStyle(.secondary), at: CGPoint(x: rect.maxX+15, y: rect.minY))
            context.draw(Text("front").font(.caption2).foregroundStyle(.secondary), at: CGPoint(x: rect.maxX+19, y: rect.maxY))
            context.clip(to: Path(CGRect(x: 0, y: 22, width: size.width, height: size.height-44)))
            func trajectory(_ r: TossResult, color: Color, limit: Double) {
                let samples = r.samples.filter { $0.time <= limit }
                guard let first = samples.first else { return }
                var path = Path(); path.move(to: point(first.position))
                for s in samples.dropFirst() { path.addLine(to: point(s.position)) }
                context.stroke(path, with: .color(color.opacity(0.55)), style: StrokeStyle(lineWidth: 2, dash: [3,3]))
                if let contact = r.firstContact, contact.time <= limit {
                    let p = point(contact.position)
                    context.stroke(Path(ellipseIn: CGRect(x: p.x-5, y: p.y-5, width: 10, height: 10)), with: .color(color), lineWidth: 2)
                }
            }
            if prediction, let ref = reference { trajectory(ref, color: .orange, limit: .infinity) }
            trajectory(result, color: .blue, limit: prediction ? .infinity : time)
            if let sample = result.sample(at: time) {
                let p = point(sample.position)
                context.fill(Path(roundedRect: CGRect(x: p.x-5, y: p.y-5, width: 10, height: 10), cornerRadius: 2), with: .color(.blue))
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Board close-up, looking down. Right is positive lateral position; the far edge is at the top. Open circles mark first contact or hole entry.")
    }
}
