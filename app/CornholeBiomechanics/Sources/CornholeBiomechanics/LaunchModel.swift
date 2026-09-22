import Foundation

/// Regulation board side profile (ACL: 48 in deck, 12 in back height, 6 in hole
/// centred 9 in from the back). Front height varies by board (2.5–4 in); 3 in default.
struct BoardGeometry: Equatable {
    var length = 1.2192          // m along the deck
    var frontHeight = 0.0762     // m
    var backHeight = 0.3048      // m
    var holeFromBack = 0.2286    // m, hole centre along the deck from the back edge
    var holeRadius = 0.0762      // m

    static let regulation = BoardGeometry()
    var angle: Double { asin((backHeight - frontHeight) / length) }
    var holeAlong: Double { length - holeFromBack }
}

/// Release conditions in the throwing plane: x forward from release, y up from the floor.
struct LaunchParameters: Equatable {
    var speed: Double            // m/s
    var angleDegrees: Double     // above horizontal
    var releaseHeight: Double    // m above the floor
    var distanceToBoard: Double  // m, horizontal from release point to the board's front edge
    var board = BoardGeometry.regulation

    var vx: Double { speed * cos(angleDegrees * .pi / 180) }
    var vy: Double { speed * sin(angleDegrees * .pi / 180) }
}

/// Drag-free 2D point-mass flight to first contact. A teaching model, not a
/// prediction of a real bag: it ignores air drag (<1.5 % effect on the arc in
/// our simulations), spin, lateral aim, bounce and sliding after contact.
struct LaunchModel {
    static let gravity = 9.80665

    enum LandingKind: String { case shortOfBoard = "Short: lands on the floor before the board"
        case frontOfBoard = "Short: hits the front of the board"
        case onBoard = "Lands on the board"
        case pastBoard = "Long: flies past the board" }

    struct Landing {
        var kind: LandingKind
        var time: Double
        var horizontal: Double        // m from release
        var alongBoard: Double? = nil        // m up the deck from the front edge, board landings only
        var distanceToHole: Double? = nil    // m along the deck, + beyond the hole centre
    }

    struct Sensitivity {
        /// Change in first-contact position (m) per unit change in each release variable.
        var perSpeed: Double?          // per 1 m/s
        var perAngle: Double?          // per 1°
        var perHeight: Double?         // per 1 m
    }

    let p: LaunchParameters
    init(_ p: LaunchParameters) { self.p = p }

    /// Smallest positive root of a t² + b t + c = 0 (a ≠ 0).
    private static func firstPositiveRoot(_ a: Double, _ b: Double, _ c: Double) -> Double? {
        let disc = b * b - 4 * a * c
        guard disc >= 0 else { return nil }
        let roots = [(-b - sqrt(disc)) / (2 * a), (-b + sqrt(disc)) / (2 * a)].filter { $0 > 1e-12 }.sorted()
        return roots.first
    }

    func landing() -> Landing {
        let g = Self.gravity, b = p.board
        // Floor: h + vy t − ½ g t² = 0.
        let tFloor = Self.firstPositiveRoot(-0.5 * g, p.vy, p.releaseHeight) ?? 0
        let xFloor = p.vx * tFloor
        if xFloor < p.distanceToBoard { return Landing(kind: .shortOfBoard, time: tFloor, horizontal: xFloor) }
        // Height when the bag passes the front edge; below the edge means it strikes the front face.
        let tFront = p.distanceToBoard / p.vx
        if p.releaseHeight + p.vy * tFront - 0.5 * g * tFront * tFront < b.frontHeight {
            return Landing(kind: .frontOfBoard, time: tFront, horizontal: p.distanceToBoard)
        }
        // Deck plane: y = hf + (x − D) tanα  ⇒  −½ g t² + (vy − vx tanα) t + (h − hf + D tanα) = 0.
        let tanA = tan(b.angle)
        if let t = Self.firstPositiveRoot(-0.5 * g, p.vy - p.vx * tanA, p.releaseHeight - b.frontHeight + p.distanceToBoard * tanA) {
            let along = (p.vx * t - p.distanceToBoard) / cos(b.angle)
            if along >= 0 && along <= b.length {
                return Landing(kind: .onBoard, time: t, horizontal: p.vx * t, alongBoard: along,
                               distanceToHole: along - b.holeAlong)
            }
        }
        return Landing(kind: .pastBoard, time: tFloor, horizontal: xFloor)
    }

    /// Release speed that puts first contact on the hole centre, by bisection
    /// on board landings (landing distance increases with speed below ~45°).
    func speedToHitHole() -> Double? {
        var low = 0.5, high = 20.0
        func along(_ v: Double) -> Double? {
            var q = p; q.speed = v
            let r = LaunchModel(q).landing()
            switch r.kind {
            case .onBoard: return r.alongBoard! - p.board.holeAlong
            case .shortOfBoard, .frontOfBoard: return -1
            case .pastBoard: return 1
            }
        }
        guard let lo = along(low), let hi = along(high), lo < 0, hi > 0 else { return nil }
        for _ in 0..<80 {
            let mid = 0.5 * (low + high)
            if (along(mid) ?? 0) < 0 { low = mid } else { high = mid }
        }
        return 0.5 * (low + high)
    }

    /// Central-difference sensitivities of the first-contact horizontal position.
    /// Only reported when both perturbed throws still land on the board.
    func sensitivity() -> Sensitivity {
        func derivative(_ step: Double, _ change: (inout LaunchParameters, Double) -> Void) -> Double? {
            var up = p, down = p
            change(&up, step); change(&down, -step)
            let a = LaunchModel(up).landing(), b = LaunchModel(down).landing()
            guard a.kind == .onBoard, b.kind == .onBoard else { return nil }
            return (a.horizontal - b.horizontal) / (2 * step)
        }
        return Sensitivity(
            perSpeed: derivative(0.01) { $0.speed += $1 },
            perAngle: derivative(0.05) { $0.angleDegrees += $1 },
            perHeight: derivative(0.005) { $0.releaseHeight += $1 })
    }

    func trajectory(samples: Int = 80) -> [(x: Double, y: Double)] {
        let end = landing().time
        return (0...samples).map { i in
            let t = end * Double(i) / Double(samples)
            return (p.vx * t, p.releaseHeight + p.vy * t - 0.5 * Self.gravity * t * t)
        }
    }
}
