import Foundation

/// Educational SI point-mass model. Not a deformable-bag or athlete predictor.
struct TossVector: Equatable {
    var x: Double = 0
    var y: Double = 0
    var z: Double = 0
    static let zero = TossVector()
    static func + (a: Self, b: Self) -> Self { .init(x: a.x+b.x, y: a.y+b.y, z: a.z+b.z) }
    static func - (a: Self, b: Self) -> Self { .init(x: a.x-b.x, y: a.y-b.y, z: a.z-b.z) }
    static func * (a: Self, b: Double) -> Self { .init(x: a.x*b, y: a.y*b, z: a.z*b) }
    func dot(_ b: Self) -> Double { x*b.x+y*b.y+z*b.z }
    var length: Double { sqrt(dot(self)) }
}

struct TossParameters: Equatable {
    var speed = 9.1
    var elevation = 45.0
    var aim = 0.0
    var height = 0.9
    var lateral = 0.0
    // Horizontal distance from release to receiving board front, NOT court spacing.
    var distance = 8.23
    var boardAngle = 11.0
    var mass = 0.454
    var airEnabled = false
    var dragArea = 0.012 // C_D A, illustrative; no bag-specific calibration
    var windForward = 0.0
    var windRight = 0.0
    var friction = 0.35 // same coefficient for sliding and static threshold
    var restitution = 0.08

    var velocity: TossVector {
        let theta = elevation * .pi/180, phi = aim * .pi/180
        return .init(x: speed*cos(theta)*cos(phi), y: speed*cos(theta)*sin(phi), z: speed*sin(theta))
    }
    var wind: TossVector { .init(x: windForward, y: windRight) }
    var valid: Bool {
        let values = [speed, elevation, aim, height, lateral, distance, boardAngle, mass, dragArea,
                      windForward, windRight, friction, restitution]
        return values.allSatisfy(\.isFinite) && (0...20).contains(speed) && (-85...85).contains(elevation)
            && (-45...45).contains(aim) && (0.1...3).contains(height) && (-3...3).contains(lateral)
            && (0...25).contains(boardAngle) && (2...15).contains(distance) && (0.1...2).contains(mass) && (0...0.06).contains(dragArea)
            && abs(windForward) <= 15 && abs(windRight) <= 15
            && (0...1).contains(friction) && (0...0.9).contains(restitution)
    }

    static func example(_ name: String) -> Self {
        var p = Self()
        let board = TossBoard(distance: p.distance)
        let u = name == "Slide approach" ? 0.24 : board.holeU
        p.elevation = name == "High arc" ? 60 : name == "Slide approach" ? 35 : 45
        p.friction = name == "Slide approach" ? 0.45 : 0.35
        p.restitution = name == "Slide approach" ? 0 : 0.08
        let target = board.point(u: u, y: 0)
        let theta = p.elevation * .pi/180
        p.speed = sqrt(CornholePhysics.gravity*target.x*target.x /
                       (2*pow(cos(theta), 2)*(p.height+target.x*tan(theta)-target.z)))
        if name == "Crosswind" { p.airEnabled = true; p.windRight = 3; p.speed += 0.4 }
        return p
    }
}

struct TossBoard {
    var distance: Double
    let length = 1.2192
    let width = 0.6096
    let frontHeight = 0.07112 // 2.8 inches
    var angleDegrees = 11.0
    var angle: Double { angleDegrees * Double.pi/180 }
    let holeU = 0.9906 // 39 inches from front, along deck
    let holeRadius = 0.0762
    var tangent: TossVector { .init(x: cos(angle), z: sin(angle)) }
    var normal: TossVector { .init(x: -sin(angle), z: cos(angle)) }
    var origin: TossVector { .init(x: distance, z: frontHeight) }
    var hole: TossVector { point(u: holeU, y: 0) }
    func point(u: Double, y: Double) -> TossVector { origin + tangent*u + .init(y: y) }
    func u(_ p: TossVector) -> Double { (p-origin).dot(tangent) }
    func signedHeight(_ p: TossVector) -> Double { (p-origin).dot(normal) }
    func contains(_ p: TossVector) -> Bool { (0...length).contains(u(p)) && abs(p.y) <= width/2 }
    func inHole(_ p: TossVector) -> Bool { pow(u(p)-holeU, 2)+p.y*p.y <= holeRadius*holeRadius }
}

enum TossPhase: String { case swing = "Arm swing", flight = "Flight", sliding = "Sliding", hole = "Hole capture", rest = "Board rest", ground = "Ground" }
struct TossSample: Identifiable {
    var time: Double
    var position: TossVector
    var velocity: TossVector
    var phase: TossPhase
    var id: Double { time }
}
struct TossEvent: Identifiable {
    var sample: TossSample
    var label: String
    let id = UUID()
}
struct TossResult {
    var samples: [TossSample] = []
    var events: [TossEvent] = []
    var score: Int?
    var outcome = "Unresolved"
    var duration: Double { samples.last?.time ?? 0 }
    var apex: Double { samples.map(\.position.z).max() ?? 0 }
    var firstContact: TossSample? { events.first?.sample }
    func sample(at time: Double) -> TossSample? {
        guard let first = samples.first, let last = samples.last else { return nil }
        if time <= first.time { return first }
        if time >= last.time { return last }
        // Binary search followed by interpolation; no integration during animation.
        var low = 0, high = samples.count-1
        while high-low > 1 { let mid = (low+high)/2; if samples[mid].time <= time { low = mid } else { high = mid } }
        let a = samples[low], b = samples[high], f = (time-a.time)/(b.time-a.time)
        return .init(time: time, position: a.position+(b.position-a.position)*f,
                     velocity: a.velocity+(b.velocity-a.velocity)*f, phase: a.phase)
    }
}

struct CornholePhysics {
    static let gravity = 9.81
    static let density = 1.225
    var parameters: TossParameters
    var board: TossBoard { .init(distance: parameters.distance, angleDegrees: parameters.boardAngle) }
    var gravityVector: TossVector { .init(z: -Self.gravity) }

    func acceleration(_ velocity: TossVector) -> TossVector {
        guard parameters.airEnabled else { return gravityVector }
        let relative = velocity-parameters.wind
        return gravityVector-relative*(0.5*Self.density*parameters.dragArea/parameters.mass*relative.length)
    }

    /// Classical RK4 for coupled position/velocity in flight.
    func flightStep(_ s: TossSample, dt: Double) -> TossSample {
        let a1 = acceleration(s.velocity)
        let v2 = s.velocity+a1*(dt/2), a2 = acceleration(v2)
        let v3 = s.velocity+a2*(dt/2), a3 = acceleration(v3)
        let v4 = s.velocity+a3*dt, a4 = acceleration(v4)
        return .init(time: s.time+dt,
                     position: s.position+(s.velocity+v2*2+v3*2+v4)*(dt/6),
                     velocity: s.velocity+(a1+a2*2+a3*2+a4)*(dt/6), phase: .flight)
    }

    func impactVelocity(_ v: TossVector) -> TossVector {
        let vn = v.dot(board.normal), tangent = v-board.normal*vn
        let speed = tangent.length
        let reduction = parameters.friction*(1+parameters.restitution)*max(0, -vn)
        let tangential = speed > 0 ? tangent*(max(0, speed-reduction)/speed) : .zero
        return tangential + board.normal*(-parameters.restitution*vn)
    }

    /// Segment-circle entry in board coordinates avoids skipping the hole between samples.
    func holeFraction(from a: TossVector, to b: TossVector) -> Double? {
        let x = board.u(a)-board.holeU, y = a.y
        let dx = board.u(b)-board.u(a), dy = b.y-a.y
        let c = x*x+y*y-board.holeRadius*board.holeRadius
        if c <= 0 { return 0 }
        let aa = dx*dx+dy*dy, bb = 2*(x*dx+y*dy), discriminant = bb*bb-4*aa*c
        guard aa > 0, discriminant >= 0 else { return nil }
        let f = (-bb-sqrt(discriminant))/(2*aa)
        return (0...1).contains(f) ? f : nil
    }

    func simulate(dt: Double = 1.0/480) -> TossResult {
        guard parameters.valid, dt.isFinite, (0.0001...1.0/60).contains(dt) else {
            return TossResult(outcome: "Invalid parameters")
        }
        var s = TossSample(time: 0, position: .init(y: parameters.lateral, z: parameters.height),
                           velocity: parameters.velocity, phase: .flight)
        var result = TossResult(samples: [s])
        let n = board.normal
        var step = 0
        func record(_ label: String) { result.events.append(.init(sample: s, label: label)) }
        func save() {
            if result.samples.last?.time == s.time { result.samples[result.samples.count-1] = s }
            else { result.samples.append(s) }
        }
        func finish(_ phase: TossPhase, _ label: String, _ score: Int) {
            s.phase = phase; record(label); s.velocity = .zero; save()
            result.score = score; result.outcome = label
        }
        while s.time < 10 {
            step += 1
            if s.phase == .flight {
                let next = flightStep(s, dt: dt)
                var hit: TossSample?
                // Locate a downward plane crossing by bisection using the flight integrator.
                if board.signedHeight(s.position) > 1e-10 && board.signedHeight(next.position) <= 0 {
                    var lo = 0.0, hi = dt
                    for _ in 0..<24 {
                        let mid = (lo+hi)/2
                        if board.signedHeight(flightStep(s, dt: mid).position) > 0 { lo = mid } else { hi = mid }
                    }
                    var crossing = flightStep(s, dt: (lo+hi)/2)
                    crossing.position = crossing.position-n*board.signedHeight(crossing.position)
                    if board.contains(crossing.position) { hit = crossing }
                }
                if let collision = hit {
                    s = collision
                    if board.inHole(s.position) { finish(.hole, "Hole · model capture", 3); return result }
                    record(result.events.isEmpty ? "First board contact" : "Board bounce")
                    s.velocity = impactVelocity(s.velocity)
                    if s.velocity.dot(n) < 0.18 {
                        s.velocity = s.velocity-n*s.velocity.dot(n); s.phase = .sliding
                    }
                    save()
                } else if next.position.z <= 0 {
                    var lo = 0.0, hi = dt
                    for _ in 0..<24 {
                        let mid = (lo+hi)/2
                        if flightStep(s, dt: mid).position.z > 0 { lo = mid } else { hi = mid }
                    }
                    s = flightStep(s, dt: (lo+hi)/2); s.position.z = 0
                    finish(.ground, "Miss · ground", 0); return result
                } else { s = next }
            } else {
                // Coulomb friction via a velocity projection. The same μ sets static hold.
                let tangentGravity = gravityVector-n*gravityVector.dot(n)
                let free = s.velocity+tangentGravity*dt
                let frictionStep = parameters.friction*Self.gravity*cos(board.angle)*dt
                let v = free.length <= frictionStep ? TossVector.zero : free*(1-frictionStep/free.length)
                if v.length < 1e-10 && s.velocity.length < 1e-10 {
                    finish(.rest, "Board · at rest", 1); return result
                }
                let end = s.position+(s.velocity+v)*(dt/2)
                var edgeFraction = 1.0
                let u0 = board.u(s.position), u1 = board.u(end)
                if u1 < 0 { edgeFraction = min(edgeFraction, (0-u0)/(u1-u0)) }
                if u1 > board.length { edgeFraction = min(edgeFraction, (board.length-u0)/(u1-u0)) }
                if end.y < -board.width/2 { edgeFraction = min(edgeFraction, (-board.width/2-s.position.y)/(end.y-s.position.y)) }
                if end.y > board.width/2 { edgeFraction = min(edgeFraction, (board.width/2-s.position.y)/(end.y-s.position.y)) }
                if let f = holeFraction(from: s.position, to: end), f <= edgeFraction {
                    s.position = s.position+(end-s.position)*f; s.time += dt*f
                    finish(.hole, "Hole · model capture", 3); return result
                }
                let f = max(0, edgeFraction)
                s.position = s.position+(end-s.position)*f
                s.velocity = s.velocity+(v-s.velocity)*f; s.time += dt*f
                if edgeFraction < 1 { s.phase = .flight; record("Left board edge") }
            }
            if step % 4 == 0 { save() }
        }
        save() // Never label a still-moving bag as a board score.
        result.outcome = "Still moving at 10 s"; return result
    }
}
