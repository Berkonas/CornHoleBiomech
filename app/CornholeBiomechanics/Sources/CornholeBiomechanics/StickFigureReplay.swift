import SwiftUI

/// The throw on a clean canvas: a stick figure from the pose landmarks of `frame` plus the measured bag
/// path, both in that frame's video pixels (bag paths are mapped with `ReplayDocument.toFrame`),
/// scaled to fit `bounds` (the pixel region the athlete and bag occupy over the whole clip).
struct StickFigureReplay: View {
    let replay: ReplayDocument
    let pose: PoseDocument?
    let side: ThrowingSide
    let frame: Int
    let bounds: CGRect
    var showModel = true
    var showTrail = true

    static let minimumConfidence = 0.3

    var body: some View {
        Canvas { context, size in
            let fit = Self.fit(bounds, in: size)
            func screen(_ p: CGPoint) -> CGPoint { CGPoint(x: fit.origin.x + p.x * fit.scale, y: fit.origin.y + p.y * fit.scale) }
            let landmarks = pose?.frames[safe: frame]?.landmarks ?? [:]
            func point(_ name: String) -> CGPoint? {
                guard let p = landmarks[name], let x = p.x, let y = p.y, p.confidence >= Self.minimumConfidence else { return nil }
                return CGPoint(x: x, y: y)
            }

            // Floor at the lowest foot point of this frame.
            let feet = ["left_ankle", "right_ankle", "LHeel", "RHeel", "LBigToe", "RBigToe", "left_heel", "right_heel",
                        "left_foot_index", "right_foot_index"].compactMap(point)
            if let floor = feet.map(\.y).max() {
                let y = screen(CGPoint(x: 0, y: floor)).y
                var line = Path(); line.move(to: CGPoint(x: 0, y: y)); line.addLine(to: CGPoint(x: size.width, y: y))
                context.stroke(line, with: .color(.secondary.opacity(0.6)), lineWidth: 1.5)
                context.draw(Text("Floor").font(.caption2).foregroundColor(.secondary), at: CGPoint(x: 8, y: y - 8), anchor: .leading)
            }

            // Bag: dashed drag-free model, full path faint, travelled path strong, bag now.
            func mapped(_ p: ReplayDocument.Point) -> CGPoint { screen(replay.toFrame(p.x, p.y, frame: frame)) }
            func polyline(_ points: [ReplayDocument.Point]) -> Path {
                var path = Path(); var previous: Int?
                for p in points {
                    let q = mapped(p)
                    if let previous, p.frame - previous <= 4 { path.addLine(to: q) } else { path.move(to: q) }
                    previous = p.frame
                }
                return path
            }
            if showModel && !replay.model.isEmpty {
                context.stroke(polyline(replay.model), with: .color(.secondary), style: StrokeStyle(lineWidth: 1.5, dash: [6, 5]))
            }
            let path = replay.filtered.isEmpty ? replay.measured : replay.filtered
            if showTrail {
                context.stroke(polyline(path), with: .color(measuredInk.opacity(0.3)), style: StrokeStyle(lineWidth: 2, lineCap: .round))
            }
            context.stroke(polyline(path.filter { $0.frame <= frame }), with: .color(measuredInk),
                           style: StrokeStyle(lineWidth: 3, lineCap: .round, lineJoin: .round))
            if let now = (path + replay.after_contact).first(where: { $0.frame == frame }) {
                let p = mapped(now)
                context.fill(Path(ellipseIn: CGRect(x: p.x - 6, y: p.y - 6, width: 12, height: 12)), with: .color(measuredInk))
                context.stroke(Path(ellipseIn: CGRect(x: p.x - 6, y: p.y - 6, width: 12, height: 12)), with: .color(.primary), lineWidth: 1)
            }

            // Body: other bones first, the throwing arm on top.
            let s = side.rawValue, o = side == .right ? "left" : "right"
            let body: [(String, String)] = [
                ("left_shoulder", "right_shoulder"), ("left_hip", "right_hip"),
                ("left_shoulder", "left_hip"), ("right_shoulder", "right_hip"),
                ("\(o)_shoulder", "\(o)_elbow"), ("\(o)_elbow", "\(o)_wrist"),
                ("left_hip", "left_knee"), ("left_knee", "left_ankle"), ("right_hip", "right_knee"), ("right_knee", "right_ankle"),
            ]
            let arm = [("\(s)_shoulder", "\(s)_elbow"), ("\(s)_elbow", "\(s)_wrist")]
            func bone(_ a: String, _ b: String, _ color: Color, _ width: CGFloat) {
                guard let pa = point(a), let pb = point(b) else { return }
                var line = Path(); line.move(to: screen(pa)); line.addLine(to: screen(pb))
                context.stroke(line, with: .color(color), style: StrokeStyle(lineWidth: width, lineCap: .round))
            }
            for (a, b) in body { bone(a, b, .secondary, 2.5) }
            for (a, b) in arm { bone(a, b, athleteInk, 4) }
            let joints = Set((body + arm).flatMap { [$0.0, $0.1] })
            for name in joints {
                guard let p = point(name) else { continue }
                let q = screen(p), r: CGFloat = name.hasPrefix(s) && !name.contains("hip") && !name.contains("knee") && !name.contains("ankle") ? 3.5 : 2.5
                context.fill(Path(ellipseIn: CGRect(x: q.x - r, y: q.y - r, width: 2 * r, height: 2 * r)),
                             with: .color(r > 3 ? athleteInk : .primary.opacity(0.7)))
            }

            // Head: a circle on the nose / ears / head point, sized from the trunk.
            let headPoints = ["Nose", "nose", "left_ear", "right_ear", "Head"].compactMap(point)
            if !headPoints.isEmpty {
                let centre = CGPoint(x: headPoints.map(\.x).reduce(0, +) / Double(headPoints.count),
                                     y: headPoints.map(\.y).reduce(0, +) / Double(headPoints.count))
                var radius = 0.0
                if let l = point("left_ear"), let r = point("right_ear") { radius = 0.65 * hypot(l.x - r.x, l.y - r.y) }
                if radius < 1, let sh = point("\(s)_shoulder"), let hip = point("\(s)_hip") { radius = 0.18 * hypot(sh.x - hip.x, sh.y - hip.y) }
                let c = screen(centre), rr = max(5, radius * fit.scale)
                context.stroke(Path(ellipseIn: CGRect(x: c.x - rr, y: c.y - rr, width: 2 * rr, height: 2 * rr)), with: .color(.secondary), lineWidth: 2.5)
            }
        }
        .accessibilityLabel("Stick figure of the athlete and the measured bag path, frame \(frame)")
    }

    /// Uniform scale and offset that fit `bounds` into `size` with an 8 % margin, centred.
    static func fit(_ bounds: CGRect, in size: CGSize) -> (scale: Double, origin: CGPoint) {
        guard bounds.width > 0, bounds.height > 0, size.width > 0, size.height > 0 else { return (1, .zero) }
        let scale = min(size.width / bounds.width, size.height / bounds.height) * 0.92
        let origin = CGPoint(x: (size.width - bounds.width * scale) / 2 - bounds.minX * scale,
                             y: (size.height - bounds.height * scale) / 2 - bounds.minY * scale)
        return (scale, origin)
    }

    /// Pixel region covering the athlete's confident landmarks over the clip and the measured bag path
    /// (release-frame pixels); the whole video frame when nothing is known.
    static func bounds(pose: PoseDocument?, replay: ReplayDocument) -> CGRect {
        var xs: [Double] = [], ys: [Double] = []
        for frame in pose?.frames ?? [] {
            for (_, p) in frame.landmarks where p.confidence >= minimumConfidence {
                if let x = p.x, let y = p.y { xs.append(x); ys.append(y) }
            }
        }
        // 1st–99th percentile of the body points, so a stray detection does not shrink the figure.
        func trimmed(_ values: [Double]) -> [Double] {
            guard values.count > 20 else { return values }
            let sorted = values.sorted()
            return [sorted[Int(0.01 * Double(sorted.count - 1))], sorted[Int(0.99 * Double(sorted.count - 1))]]
        }
        xs = trimmed(xs); ys = trimmed(ys)
        for p in replay.measured { xs.append(p.x); ys.append(p.y) }
        guard let minX = xs.min(), let maxX = xs.max(), let minY = ys.min(), let maxY = ys.max(), maxX > minX, maxY > minY else {
            return CGRect(x: 0, y: 0, width: replay.width, height: replay.height)
        }
        let pad = 0.05 * max(maxX - minX, maxY - minY)
        return CGRect(x: minX - pad, y: minY - pad, width: maxX - minX + 2 * pad, height: maxY - minY + 2 * pad)
    }
}
