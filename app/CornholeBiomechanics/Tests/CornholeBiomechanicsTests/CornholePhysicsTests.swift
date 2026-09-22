import XCTest
@testable import CornholeBiomechanics

final class CornholePhysicsTests: XCTestCase {
    func testVacuumFlightAgainstAnalyticGroundTimeAndRange() throws {
        var p = TossParameters(); p.speed = 4; p.aim = 8; p.lateral = -0.2; p.distance = 15
        let result = CornholePhysics(parameters: p).simulate()
        let t = (p.velocity.z+sqrt(p.velocity.z*p.velocity.z+2*9.81*p.height))/9.81
        let final = try XCTUnwrap(result.samples.last)
        XCTAssertEqual(final.time, t, accuracy: 1e-8)
        XCTAssertEqual(final.position.x, p.velocity.x*t, accuracy: 1e-7)
        XCTAssertEqual(final.position.y, p.lateral+p.velocity.y*t, accuracy: 1e-7)
        XCTAssertEqual(final.position.z, 0)
        XCTAssertEqual(result.score, 0)
        for s in result.samples.dropLast() {
            XCTAssertEqual(s.position.z, p.height+p.velocity.z*s.time-4.905*s.time*s.time, accuracy: 1e-9)
        }
    }

    func testVacuumMassIndependenceAndEnergyConservation() {
        var p = TossParameters(); p.speed = 4; p.distance = 15
        let first = CornholePhysics(parameters: p).simulate()
        let initialEnergy = 0.5*p.mass*p.speed*p.speed+p.mass*9.81*p.height
        for sample in first.samples.dropLast() {
            let energy = 0.5*p.mass*pow(sample.velocity.length, 2)+p.mass*9.81*sample.position.z
            XCTAssertEqual(energy, initialEnergy, accuracy: 1e-8)
        }
        p.mass = 1.3
        let second = CornholePhysics(parameters: p).simulate()
        XCTAssertEqual(first.samples.last!.position.x, second.samples.last!.position.x, accuracy: 1e-10)
    }

    func testCenterPresetsMeetHoleAtIndependentAnalyticTime() throws {
        for name in ["Center flight", "High arc"] {
            let p = TossParameters.example(name), model = CornholePhysics(parameters: p)
            let result = model.simulate(), event = try XCTUnwrap(result.firstContact)
            XCTAssertEqual(result.score, 3, name)
            XCTAssertEqual(event.time, model.board.hole.x/p.velocity.x, accuracy: 1e-7)
            XCTAssertEqual(event.position.x, model.board.hole.x, accuracy: 1e-7)
            XCTAssertEqual(event.position.z, model.board.hole.z, accuracy: 1e-7)
            XCTAssertGreaterThan(event.velocity.length, 0, "Keep incoming speed at entry")
        }
    }

    func testDragOpposesRelativeAirVelocityAndMassScalesAcceleration() {
        var p = TossParameters(); p.airEnabled = true; p.windRight = 3
        let velocity = TossVector(x: 8, y: -1, z: 4)
        let m = CornholePhysics(parameters: p)
        let drag = m.acceleration(velocity)-m.gravityVector
        XCTAssertLessThan(drag.dot(velocity-p.wind), 0)
        XCTAssertGreaterThan(drag.y, 0)
        p.mass *= 2
        let heavy = CornholePhysics(parameters: p)
        XCTAssertEqual((heavy.acceleration(velocity)-heavy.gravityVector).length, drag.length/2, accuracy: 1e-12)
        XCTAssertEqual(m.acceleration(p.wind), m.gravityVector)
    }

    func testWindSymmetryDragRangeAndRefinement() throws {
        var p = TossParameters(); p.distance = 15; p.speed = 8; p.airEnabled = true
        let still = CornholePhysics(parameters: p).simulate()
        p.airEnabled = false
        let vacuum = CornholePhysics(parameters: p).simulate()
        XCTAssertLessThan(still.samples.last!.position.x, vacuum.samples.last!.position.x)
        p.airEnabled = true; p.windRight = 4
        let right = CornholePhysics(parameters: p).simulate()
        p.windRight = -4
        let left = CornholePhysics(parameters: p).simulate()
        XCTAssertEqual(left.samples.last!.position.y, -right.samples.last!.position.y, accuracy: 1e-10)
        let fine = CornholePhysics(parameters: p).simulate(dt: 1.0/960)
        XCTAssertEqual(left.duration, fine.duration, accuracy: 1e-7)
        XCTAssertEqual(left.samples.last!.position.x, fine.samples.last!.position.x, accuracy: 1e-7)
    }

    func testImpactRestitutionTangentialImpulseAndDissipation() {
        var p = TossParameters(); p.restitution = 0.4; p.friction = 0.2
        let m = CornholePhysics(parameters: p)
        let incoming = m.board.tangent*3+m.board.normal*(-5)
        let outgoing = m.impactVelocity(incoming)
        XCTAssertEqual(outgoing.dot(m.board.normal), 2, accuracy: 1e-12)
        XCTAssertEqual(outgoing.dot(m.board.tangent), 3-0.2*1.4*5, accuracy: 1e-12)
        XCTAssertLessThan(outgoing.length, incoming.length)
        p.friction = 1
        XCTAssertEqual(CornholePhysics(parameters: p).impactVelocity(incoming).dot(m.board.tangent), 0, accuracy: 1e-12)
    }

    func testBoardRestFrictionAndEdgeExit() {
        var p = TossParameters.example("Slide approach"); p.friction = 0.8; p.restitution = 0
        let resting = CornholePhysics(parameters: p).simulate()
        XCTAssertEqual(resting.score, 1)
        XCTAssertEqual(resting.samples.last?.phase, .rest)
        p.friction = 0; p.aim = 1.3 // miss hole and run off the rear edge
        let sliding = CornholePhysics(parameters: p).simulate()
        XCTAssertTrue(sliding.events.contains { $0.label == "Left board edge" })
        XCTAssertEqual(sliding.score, 0)
        XCTAssertTrue(sliding.samples.allSatisfy { $0.position.z >= -1e-8 })
    }

    func testSlideStoppingDistanceAgainstIndependentInclineEquation() throws {
        var p = TossParameters.example("Slide approach"); p.lateral = 0.15
        let m = CornholePhysics(parameters: p), result = m.simulate()
        let contact = try XCTUnwrap(result.firstContact)
        let incoming = contact.velocity
        let vn = incoming.dot(m.board.normal)
        let tangentSpeed = incoming.dot(m.board.tangent)-p.friction*abs(vn)
        let deceleration = 9.81*(sin(m.board.angle)+p.friction*cos(m.board.angle))
        let predictedStopU = m.board.u(contact.position)+pow(tangentSpeed, 2)/(2*deceleration)
        XCTAssertEqual(result.score, 1)
        XCTAssertEqual(m.board.u(result.samples.last!.position), predictedStopU, accuracy: 2e-5)
        XCTAssertEqual(result.samples.last!.position.y, p.lateral, accuracy: 1e-10)
        XCTAssertEqual(Set(result.events.map(\.id)).count, result.events.count)
    }

    func testLateralMissIsNotMistakenForAnInfiniteBoardPlaneHit() {
        var p = TossParameters.example("Center flight"); p.lateral = 0.6
        let result = CornholePhysics(parameters: p).simulate()
        XCTAssertEqual(result.score, 0)
        XCTAssertEqual(result.events.count, 1)
        XCTAssertEqual(result.firstContact?.position.z, 0)
    }

    func testSlidingHoleSegmentDoesNotTunnelAndNearMissStaysOutside() throws {
        let m = CornholePhysics(parameters: .init()), b = m.board
        let a = b.point(u: 0.5, y: 0), end = b.point(u: 1.2, y: 0)
        let f = try XCTUnwrap(m.holeFraction(from: a, to: end))
        XCTAssertEqual(f, (b.holeU-b.holeRadius-0.5)/0.7, accuracy: 1e-12)
        XCTAssertNil(m.holeFraction(from: b.point(u: 0.5, y: 0.08), to: b.point(u: 1.2, y: 0.08)))
    }

    func testControlExtremesFiniteChronologicalAndResolvedScoresHonest() {
        for speed in [4.0, 14] { for angle in [10.0, 75] { for mu in [0.0, 0.8] { for wind in [-6.0, 6] {
            var p = TossParameters(); p.speed = speed; p.elevation = angle; p.friction = mu
            p.airEnabled = true; p.windForward = wind; p.windRight = -wind; p.restitution = 0.6
            let result = CornholePhysics(parameters: p).simulate()
            XCTAssertFalse(result.samples.isEmpty)
            XCTAssertTrue(result.samples.allSatisfy { $0.position.length.isFinite && $0.velocity.length.isFinite })
            XCTAssertTrue(zip(result.samples, result.samples.dropFirst()).allSatisfy { $0.time < $1.time })
            if result.score == 1 { XCTAssertEqual(result.samples.last?.phase, .rest) }
            if result.score == nil { XCTAssertGreaterThanOrEqual(result.duration, 10) }
        } } } }
    }

    func testInvalidInputsAreRejected() {
        var p = TossParameters(); p.mass = 0
        XCTAssertTrue(CornholePhysics(parameters: p).simulate().samples.isEmpty)
        p = .init(); p.speed = .nan
        XCTAssertNil(CornholePhysics(parameters: p).simulate().score)
        XCTAssertTrue(CornholePhysics(parameters: .init()).simulate(dt: 0).samples.isEmpty)
    }
}
