import Foundation

/// Absolute angles from downward vertical; SI units throughout. Educational
/// planar rigid-body models, with a fixed pivot and no inferred human torques.
enum PendulumKind: String, CaseIterable, Identifiable {
    case singleSimple = "Single simple"
    case singleCompound = "Single compound"
    case doubleSimple = "Double simple"
    case doubleCompound = "Double compound"
    var id: String { rawValue }
    var isDouble: Bool { self == .doubleSimple || self == .doubleCompound }
    var isCompound: Bool { self == .singleCompound || self == .doubleCompound }
    var assumption: String {
        switch self {
        case .singleSimple: "Massless link; all modeled mass at its tip."
        case .singleCompound: "One uniform rod with a point bag mass at its tip."
        case .doubleSimple: "Massless links; m₁ at the elbow and m₂ + bag at the tip."
        case .doubleCompound: "Two uniform rods with center-of-mass inertia and a point bag mass at the tip."
        }
    }
}

struct PendulumParameters {
    var l1 = 0.30, l2 = 0.35, m1 = 2.0, m2 = 1.0, bag = 0.45
    let g = 9.81
    var valid: Bool { [l1, l2, m1, m2].allSatisfy { $0.isFinite && $0 > 0 } && bag.isFinite && bag >= 0 }
}

struct PendulumState {
    var q1: Double, q2: Double, w1: Double, w2: Double
    func adding(_ v: Self, scale: Double) -> Self {
        Self(q1: q1 + v.q1 * scale, q2: q2 + v.q2 * scale, w1: w1 + v.w1 * scale, w2: w2 + v.w2 * scale)
    }
}

struct PendulumSample: Identifiable {
    var id: Int
    var time: Double
    var state: PendulumState
    var energy: Double
}

struct PendulumMechanics {
    let kind: PendulumKind
    var p = PendulumParameters()

    // T = ½ A w₁² + ½ B w₂² + C cos(q₁−q₂) w₁w₂;
    // V = −G₁ cos(q₁) − G₂ cos(q₂). Singles use A and G₁ only.
    var coefficients: (a: Double, b: Double, c: Double, g1: Double, g2: Double) {
        let l = p.l1 + p.l2, m = p.m1 + p.m2
        switch kind {
        case .singleSimple:
            return ((m + p.bag)*l*l, 0, 0, (m + p.bag)*p.g*l, 0)
        case .singleCompound:
            return ((m/3 + p.bag)*l*l, 0, 0, (m/2 + p.bag)*p.g*l, 0)
        case .doubleSimple:
            let distal = p.m2 + p.bag
            return ((p.m1 + distal)*p.l1*p.l1, distal*p.l2*p.l2,
                    distal*p.l1*p.l2, (p.m1 + distal)*p.g*p.l1, distal*p.g*p.l2)
        case .doubleCompound:
            return ((p.m1/3 + p.m2 + p.bag)*p.l1*p.l1,
                    (p.m2/3 + p.bag)*p.l2*p.l2, (p.m2/2 + p.bag)*p.l1*p.l2,
                    (p.m1/2 + p.m2 + p.bag)*p.g*p.l1, (p.m2/2 + p.bag)*p.g*p.l2)
        }
    }

    /// Joint torque mapping is Q = [shoulder − elbow, elbow] for absolute angles.
    func rate(_ s: PendulumState, shoulderTorque: Double = 0, elbowTorque: Double = 0) -> PendulumState {
        let k = coefficients
        if !kind.isDouble {
            let acceleration = (shoulderTorque - k.g1*sin(s.q1))/k.a
            return PendulumState(q1: s.w1, q2: s.w1, w1: acceleration, w2: acceleration)
        }
        let d = s.q1 - s.q2, cross = k.c*cos(d)
        let r1 = shoulderTorque - elbowTorque - k.c*sin(d)*s.w2*s.w2 - k.g1*sin(s.q1)
        let r2 = elbowTorque + k.c*sin(d)*s.w1*s.w1 - k.g2*sin(s.q2)
        let det = k.a*k.b - cross*cross
        return PendulumState(q1: s.w1, q2: s.w2,
            w1: (k.b*r1 - cross*r2)/det, w2: (k.a*r2 - cross*r1)/det)
    }

    func energy(_ s: PendulumState) -> Double {
        let k = coefficients
        return 0.5*k.a*s.w1*s.w1 + 0.5*k.b*s.w2*s.w2 + k.c*cos(s.q1-s.q2)*s.w1*s.w2 - k.g1*cos(s.q1) - k.g2*cos(s.q2)
    }

    func step(_ s: PendulumState, dt: Double) -> PendulumState {
        let k1 = rate(s)
        let k2 = rate(s.adding(k1, scale: dt/2))
        let k3 = rate(s.adding(k2, scale: dt/2))
        let k4 = rate(s.adding(k3, scale: dt))
        return s.adding(k1, scale: dt/6).adding(k2, scale: dt/3).adding(k3, scale: dt/3).adding(k4, scale: dt/6)
    }

    func simulate(angleDegrees: Double, bendDegrees: Double, duration: Double = 4, dt: Double = 1.0/600) -> [PendulumSample] {
        guard p.valid, angleDegrees.isFinite, bendDegrees.isFinite,
              duration.isFinite, dt.isFinite, duration > 0, duration <= 10,
              dt >= 0.0001, dt <= 0.01 else { return [] }
        let angle = angleDegrees * .pi/180
        var s = PendulumState(q1: angle, q2: angle + (kind.isDouble ? bendDegrees * .pi/180 : 0), w1: 0, w2: 0)
        var samples = [PendulumSample(id: 0, time: 0, state: s, energy: energy(s))]
        let count = Int((duration/dt).rounded())
        for i in 1...max(1, count) {
            s = step(s, dt: dt)
            if i % 10 == 0 || i == count {
                samples.append(PendulumSample(id: i, time: Double(i)*dt, state: s, energy: energy(s)))
            }
        }
        return samples
    }

    var smallAnglePeriod: Double? {
        kind.isDouble ? nil : 2 * .pi * sqrt(coefficients.a/coefficients.g1)
    }
}
