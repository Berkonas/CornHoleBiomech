import Foundation

/// Prescribed two-link motion + inverse dynamics, not a muscle-control prediction.
struct SwingParameters: Equatable {
    var bodyHeight = 1.78
    var shoulderFraction = 0.82 // editable geometric assumption, not anthropometry measured from video
    var shoulderWidth = 0.40
    var upperLength = 0.32
    var distalLength = 0.38 // elbow to bag center: includes the hand/grip offset
    var upperMass = 2.0
    var distalMass = 1.2
    var shoulderStart = -65.0
    var shoulderEnd = 95.0
    var elbowStart = 12.0 // flexion: q2-q1
    var elbowEnd = 0.0
    var duration = 0.34
    var releaseFraction = 0.62
    var yaw = -1.5
    var stanceForward = -0.40 // shoulder/body axis relative to the throwing foul line
    var stanceRight = 0.0
    var rightHanded = true
    var boardFront = 8.23 // target board front relative to throwing foul line

    var shoulderHeight: Double { bodyHeight*shoulderFraction }
    var releaseTime: Double { duration*releaseFraction }
    var direction: TossVector { .init(x: cos(yaw * .pi/180), y: sin(yaw * .pi/180)) }
    var rightDirection: TossVector { .init(x: -sin(yaw * .pi/180), y: cos(yaw * .pi/180)) }
    var bodyBase: TossVector { .init(x: stanceForward, y: stanceRight) }
    var shoulder: TossVector { bodyBase + .init(z: shoulderHeight) + rightDirection*(shoulderWidth/2*(rightHanded ? 1 : -1)) }
    var valid: Bool {
        [bodyHeight, shoulderFraction, shoulderWidth, upperLength, distalLength, upperMass, distalMass,
         shoulderStart, shoulderEnd, elbowStart, elbowEnd, duration, releaseFraction, yaw,
         stanceForward, stanceRight, boardFront].allSatisfy(\.isFinite)
        && (1.2...2.3).contains(bodyHeight) && (0.65...0.9).contains(shoulderFraction)
        && (0.2...0.65).contains(shoulderWidth) && (0.15...0.6).contains(upperLength)
        && (0.15...0.65).contains(distalLength) && (0.1...8).contains(upperMass) && (0.1...8).contains(distalMass)
        && (-100...0).contains(shoulderStart) && (20...120).contains(shoulderEnd)
        && (0...100).contains(elbowStart) && (0...100).contains(elbowEnd)
        && (0.15...1.5).contains(duration) && (0.1...0.95).contains(releaseFraction)
        && (-30...30).contains(yaw) && (-2...1).contains(stanceForward) && (-2...2).contains(stanceRight)
        && (3...12).contains(boardFront)
    }
}

struct SwingPose {
    var time: Double
    var q1: Double; var q2: Double
    var w1: Double; var w2: Double
    var a1: Double; var a2: Double
    var shoulder: TossVector; var elbow: TossVector; var wrist: TossVector
    var velocity: TossVector; var acceleration: TossVector
    var elbowIncluded: Double { 180-abs((q2-q1)*180 / .pi) }
}

struct SwingMechanics {
    var parameters: SwingParameters
    /// C2 endpoint interpolation: starts and ends at rest, not a claimed human motor law.
    func pose(at time: Double) -> SwingPose {
        let p = parameters
        let u = min(1, max(0, time/p.duration))
        let f = 10*pow(u,3)-15*pow(u,4)+6*pow(u,5)
        let df = (30*u*u-60*pow(u,3)+30*pow(u,4))/p.duration
        let ddf = (60*u-180*u*u+120*pow(u,3))/(p.duration*p.duration)
        let scale = Double.pi/180
        let start2 = p.shoulderStart+p.elbowStart, end2 = p.shoulderEnd+p.elbowEnd
        let q1 = (p.shoulderStart+(p.shoulderEnd-p.shoulderStart)*f)*scale
        let q2 = (start2+(end2-start2)*f)*scale
        let w1 = (p.shoulderEnd-p.shoulderStart)*df*scale, w2 = (end2-start2)*df*scale
        let a1 = (p.shoulderEnd-p.shoulderStart)*ddf*scale, a2 = (end2-start2)*ddf*scale
        let d = p.direction
        func offset(_ l: Double, _ q: Double) -> TossVector { d*(l*sin(q)) + .init(z: -l*cos(q)) }
        func velocity(_ l: Double, _ q: Double, _ w: Double) -> TossVector { d*(l*cos(q)*w) + .init(z: l*sin(q)*w) }
        func acceleration(_ l: Double, _ q: Double, _ w: Double, _ a: Double) -> TossVector {
            d*(l*(cos(q)*a-sin(q)*w*w)) + .init(z: l*(sin(q)*a+cos(q)*w*w))
        }
        let elbow = p.shoulder+offset(p.upperLength, q1)
        return .init(time: time, q1: q1, q2: q2, w1: w1, w2: w2, a1: a1, a2: a2,
                     shoulder: p.shoulder, elbow: elbow, wrist: elbow+offset(p.distalLength, q2),
                     velocity: velocity(p.upperLength,q1,w1)+velocity(p.distalLength,q2,w2),
                     acceleration: acceleration(p.upperLength,q1,w1,a1)+acceleration(p.distalLength,q2,w2,a2))
    }
    var release: SwingPose { pose(at: parameters.releaseTime) }

    func launch(using environment: TossParameters) -> TossParameters? {
        guard parameters.valid else { return nil }
        let r = release
        // Do not silently turn backward or underground releases into valid forward throws.
        guard r.velocity.x > 0.01,
              (0...100).allSatisfy({ pose(at: parameters.releaseTime*Double($0)/100).wrist.z > 0 }) else { return nil }
        var p = environment
        p.height = r.wrist.z; p.lateral = r.wrist.y; p.distance = parameters.boardFront-r.wrist.x
        p.speed = r.velocity.length
        p.elevation = atan2(r.velocity.z, hypot(r.velocity.x,r.velocity.y))*180 / .pi
        p.aim = atan2(r.velocity.y,r.velocity.x)*180 / .pi
        return p.valid ? p : nil
    }

    /// Net joint torques required by the prescribed motion of two uniform rods.
    /// No muscle forces, co-contraction, tissue loads, or physiological limits inferred.
    func torques(at time: Double, bagMass: Double) -> (shoulder: Double, elbow: Double, gripForce: Double) {
        let p = parameters, s = pose(at: time)
        var mechanical = PendulumParameters()
        mechanical.l1 = p.upperLength; mechanical.l2 = p.distalLength
        mechanical.m1 = p.upperMass; mechanical.m2 = p.distalMass; mechanical.bag = bagMass
        let c = PendulumMechanics(kind: .doubleCompound, p: mechanical).coefficients
        let delta = s.q1-s.q2
        let q1 = c.a*s.a1+c.c*cos(delta)*s.a2+c.c*sin(delta)*s.w2*s.w2+c.g1*sin(s.q1)
        let q2 = c.b*s.a2+c.c*cos(delta)*s.a1-c.c*sin(delta)*s.w1*s.w1+c.g2*sin(s.q2)
        return (q1+q2, q2, (s.acceleration + TossVector(z: CornholePhysics.gravity)).length*bagMass)
    }
}
