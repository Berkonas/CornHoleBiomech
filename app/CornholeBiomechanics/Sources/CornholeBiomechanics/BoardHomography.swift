import CoreGraphics
import Foundation

/// Planar mapping between board-camera pixels and deck inches.
///
/// The deck is a flat 24 × 48 in rectangle, so four clicked corners define an
/// exact projective mapping (homography) for points *on the deck plane*.
/// Board coordinates: x 0–24 in left→right seen from the pitcher, y 0–48 in
/// from the front (pitcher) edge to the back; hole centre (12, 39).
/// Floor points lie in a different plane and must not be mapped with it.
struct BoardHomography {
    /// Board-inch positions of the corners, in the order the user clicks them.
    static let boardCorners = [CGPoint(x: 0, y: 0), CGPoint(x: 24, y: 0), CGPoint(x: 24, y: 48), CGPoint(x: 0, y: 48)]
    static let cornerNames = ["front-left", "front-right", "back-right", "back-left"]

    private let toBoard: [Double]   // 3×3 row-major, h33 = 1
    private let toImage: [Double]

    /// Nil when the four points are missing, collinear, or not a convex quadrilateral
    /// in the clicked order (usually a corner clicked out of order).
    init?(imageCorners: [CGPoint]) {
        guard imageCorners.count == 4, Self.isConvex(imageCorners),
              let forward = Self.solve(from: imageCorners, to: Self.boardCorners),
              let inverse = Self.solve(from: Self.boardCorners, to: imageCorners) else { return nil }
        toBoard = forward; toImage = inverse
    }

    func boardInches(fromImage p: CGPoint) -> CGPoint? { Self.apply(toBoard, p) }
    func image(fromBoardInches p: CGPoint) -> CGPoint? { Self.apply(toImage, p) }
    func isOnBoard(_ inches: CGPoint) -> Bool { (0...24).contains(inches.x) && (0...48).contains(inches.y) }

    /// Worst-case board error (inches) caused by a 1-pixel click error at a deck
    /// point: the largest singular value of the image→board Jacobian there.
    /// A camera looking along the deck edge-on gives large values in one direction.
    func inchesPerPixel(atBoardInches point: CGPoint) -> Double? {
        guard let c = image(fromBoardInches: point) else { return nil }
        let e = 0.5
        guard let px = boardInches(fromImage: CGPoint(x: c.x + e, y: c.y)), let mx = boardInches(fromImage: CGPoint(x: c.x - e, y: c.y)),
              let py = boardInches(fromImage: CGPoint(x: c.x, y: c.y + e)), let my = boardInches(fromImage: CGPoint(x: c.x, y: c.y - e)) else { return nil }
        let a = (px.x - mx.x) / (2 * e), b = (py.x - my.x) / (2 * e)
        let c2 = (px.y - mx.y) / (2 * e), d = (py.y - my.y) / (2 * e)
        // Largest singular value of [[a, b], [c2, d]].
        let t = a * a + b * b + c2 * c2 + d * d, det = a * d - b * c2
        return sqrt((t + sqrt(max(0, t * t - 4 * det * det))) / 2)
    }

    private static func apply(_ h: [Double], _ p: CGPoint) -> CGPoint? {
        let w = h[6] * p.x + h[7] * p.y + h[8]
        guard abs(w) > 1e-12 else { return nil }
        return CGPoint(x: (h[0] * p.x + h[1] * p.y + h[2]) / w, y: (h[3] * p.x + h[4] * p.y + h[5]) / w)
    }

    /// Direct linear transform for exactly four correspondences (8 equations, h33 = 1).
    private static func solve(from src: [CGPoint], to dst: [CGPoint]) -> [Double]? {
        var a = [[Double]]()
        for (s, d) in zip(src, dst) {
            a.append([s.x, s.y, 1, 0, 0, 0, -d.x * s.x, -d.x * s.y, d.x])
            a.append([0, 0, 0, s.x, s.y, 1, -d.y * s.x, -d.y * s.y, d.y])
        }
        // Gaussian elimination with partial pivoting on the 8×9 augmented matrix.
        for col in 0..<8 {
            guard let pivot = (col..<8).max(by: { abs(a[$0][col]) < abs(a[$1][col]) }), abs(a[pivot][col]) > 1e-9 else { return nil }
            a.swapAt(col, pivot)
            for row in 0..<8 where row != col {
                let f = a[row][col] / a[col][col]
                if f != 0 { for k in col..<9 { a[row][k] -= f * a[col][k] } }
            }
        }
        return (0..<8).map { a[$0][8] / a[$0][$0] } + [1]
    }

    private static func isConvex(_ p: [CGPoint]) -> Bool {
        var sign = 0.0
        for i in 0..<4 {
            let a = p[i], b = p[(i + 1) % 4], c = p[(i + 2) % 4]
            let cross = (b.x - a.x) * (c.y - b.y) - (b.y - a.y) * (c.x - b.x)
            guard abs(cross) > 1e-6 else { return false }
            if sign == 0 { sign = cross } else if (cross > 0) != (sign > 0) { return false }
        }
        return true
    }
}
