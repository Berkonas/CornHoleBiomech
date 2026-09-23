import Foundation

/// Coach-facing body parameters for a straight-arm underhand swing, side view.
struct SwingParameters: Equatable {
    var bodyHeight = 1.75            // m
    var backswingDeg = -55.0         // arm angle from straight down at the top of the backswing (negative = behind)
    var releaseArmDeg = 35.0         // arm angle when the bag leaves the hand
    var followThroughDeg = 95.0      // where the swing ends
    var forwardSwingTime = 0.50      // s, backswing top → end of follow-through
    var stepSpeed = 0.3              // m/s, forward body (shoulder) speed at release
    var crouch = 0.05                // m, shoulder lowered by knee bend
    var shoulderToBoard = 8.1        // m, horizontal: shoulder to the board's front edge
}

/// Pendulum-arm swing → release conditions → the same drag-free flight as `LaunchModel`.
///
/// Anthropometry (Drillis & Contini, tabulated in Winter, *Biomechanics and Motor
/// Control of Human Movement*): shoulder (acromion) height 0.818 H; upper arm
/// 0.186 H, forearm 0.146 H, half hand to the grip 0.054 H, so the shoulder-to-bag
/// radius R ≈ 0.386 H. The arm is a straight rigid pendulum about the shoulder;
/// its angle follows a minimum-jerk profile φ(s) = φ_b + Δφ(10s³ − 15s⁴ + 6s⁵),
/// s = t/T, whose peak angular speed is 1.875 Δφ/T. At release the bag moves on the
/// arm's tangent: v = ω R (cos φ, sin φ) + (step, 0), so with no step the launch angle
/// equals the arm angle from vertical.
struct SwingModel {
    struct Release {
        var speed: Double; var angleDegrees: Double; var height: Double
        var armAngularSpeed: Double      // rad/s
        var time: Double                 // s after the top of the backswing
        var forwardOfShoulder: Double    // m, bag ahead of the (moving) shoulder
        /// Release point relative to the shoulder's starting position (includes the step).
        func x(stepSpeed: Double) -> Double { stepSpeed * time + forwardOfShoulder }
    }

    let p: SwingParameters
    init(_ p: SwingParameters) { self.p = p }

    var shoulderHeight: Double { 0.818 * p.bodyHeight - p.crouch }
    var radius: Double { 0.386 * p.bodyHeight }
    private var delta: Double { (p.followThroughDeg - p.backswingDeg) * .pi / 180 }
    var peakAngularSpeed: Double { 1.875 * delta / p.forwardSwingTime }

    func armAngle(at t: Double) -> Double {
        let s = min(max(t / p.forwardSwingTime, 0), 1)
        return p.backswingDeg * .pi / 180 + delta * (10 * pow(s, 3) - 15 * pow(s, 4) + 6 * pow(s, 5))
    }

    func armAngularSpeed(at t: Double) -> Double {
        let s = min(max(t / p.forwardSwingTime, 0), 1)
        return delta * (30 * s * s - 60 * pow(s, 3) + 30 * pow(s, 4)) / p.forwardSwingTime
    }

    /// Nil when the chosen release angle is outside the swing (never reached).
    func release() -> Release? {
        let target = p.releaseArmDeg * .pi / 180
        guard p.forwardSwingTime > 0, target > armAngle(at: 0), target < armAngle(at: p.forwardSwingTime) else { return nil }
        var lo = 0.0, hi = p.forwardSwingTime      // φ(t) is monotonic, so bisect for the release time
        for _ in 0..<60 {
            let mid = 0.5 * (lo + hi)
            if armAngle(at: mid) < target { lo = mid } else { hi = mid }
        }
        let t = 0.5 * (lo + hi), w = armAngularSpeed(at: t)
        let vx = w * radius * cos(target) + p.stepSpeed, vy = w * radius * sin(target)
        return Release(speed: hypot(vx, vy), angleDegrees: atan2(vy, vx) * 180 / .pi,
                       height: shoulderHeight - radius * cos(target), armAngularSpeed: w, time: t,
                       forwardOfShoulder: radius * sin(target))
    }

    /// Release conditions for the flight model; distance is measured from the release point.
    func launch() -> LaunchParameters? {
        // The shoulder has also stepped forward by stepSpeed × release time.
        release().map { LaunchParameters(speed: $0.speed, angleDegrees: $0.angleDegrees, releaseHeight: $0.height,
                                         distanceToBoard: p.shoulderToBoard - p.stepSpeed * $0.time - $0.forwardOfShoulder) }
    }

    /// Forward-swing time whose release lands first contact on the hole centre (bisection);
    /// shorter time = faster swing = longer throw.
    func swingTimeToHitHole() -> Double? {
        func error(_ T: Double) -> Double? {
            var q = p; q.forwardSwingTime = T
            guard let launch = SwingModel(q).launch() else { return nil }
            let r = LaunchModel(launch).landing()
            switch r.kind {
            case .onBoard: return r.distanceToHole
            case .shortOfBoard, .frontOfBoard: return -1
            case .pastBoard: return 1
            }
        }
        var fast = 0.12, slow = 1.5
        guard let f = error(fast), let s = error(slow), f > 0, s < 0 else { return nil }
        for _ in 0..<60 {
            let mid = 0.5 * (fast + slow)
            guard let e = error(mid) else { return nil }
            if e > 0 { fast = mid } else { slow = mid }
        }
        return 0.5 * (fast + slow)
    }

    /// Stick-figure joints at time t (metres; x forward from the shoulder's start, y up).
    /// The body translates at `stepSpeed` during the swing; legs are drawn from the hip.
    func figure(at t: Double) -> [String: CGPoint] {
        let shift = p.stepSpeed * min(max(t, 0), p.forwardSwingTime)
        let shoulder = CGPoint(x: shift, y: shoulderHeight)
        let hip = CGPoint(x: shift - 0.03, y: 0.53 * p.bodyHeight - p.crouch)
        let phi = armAngle(at: t)
        let elbow = CGPoint(x: shoulder.x + 0.186 * p.bodyHeight * sin(phi), y: shoulder.y - 0.186 * p.bodyHeight * cos(phi))
        let hand = CGPoint(x: shoulder.x + radius * sin(phi), y: shoulder.y - radius * cos(phi))
        let knee = CGPoint(x: hip.x + 0.06 + p.crouch, y: 0.285 * p.bodyHeight)
        return ["head": CGPoint(x: shoulder.x + 0.02, y: 0.93 * p.bodyHeight - p.crouch), "shoulder": shoulder, "hip": hip,
                "elbow": elbow, "hand": hand, "front_knee": knee, "front_foot": CGPoint(x: hip.x + 0.25, y: 0),
                "back_knee": CGPoint(x: hip.x - 0.08, y: 0.285 * p.bodyHeight), "back_foot": CGPoint(x: hip.x - 0.25, y: 0)]
    }
}
