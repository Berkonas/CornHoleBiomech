import XCTest
@testable import CornholeBiomechanics

final class SwingMechanicsTests: XCTestCase {
    func testHandVelocityAndAccelerationMatchIndependentFiniteDifferences() {
        var p = SwingParameters(); p.yaw = 17; p.elbowStart = 65; p.elbowEnd = 8
        let m = SwingMechanics(parameters: p), h = 1e-6
        for fraction in [0.2,0.5,0.72] {
            let t = p.duration*fraction, s = m.pose(at: t)
            let plus = m.pose(at: t+h), minus = m.pose(at: t-h)
            let v = (plus.wrist-minus.wrist)*(1/(2*h))
            let a = (plus.velocity-minus.velocity)*(1/(2*h))
            XCTAssertLessThan((v-s.velocity).length, 1e-7)
            XCTAssertLessThan((a-s.acceleration).length, 1e-5)
            XCTAssertEqual((s.elbow-s.shoulder).length, p.upperLength, accuracy: 1e-12)
            XCTAssertEqual((s.wrist-s.elbow).length, p.distalLength, accuracy: 1e-12)
        }
    }

    func testComputedReleaseIsContinuousWithFlight() throws {
        let m = SwingMechanics(parameters: .init()), s = m.release
        let p = try XCTUnwrap(m.launch(using: .init()))
        let flight = CornholePhysics(parameters: p).simulate()
        let initial = try XCTUnwrap(flight.samples.first)
        XCTAssertEqual(initial.position.z, s.wrist.z, accuracy: 1e-12)
        XCTAssertEqual(initial.position.y, s.wrist.y, accuracy: 1e-12)
        XCTAssertEqual(initial.position.x, 0)
        XCTAssertLessThan((initial.velocity-s.velocity).length, 1e-12)
        XCTAssertEqual(p.distance, m.parameters.boardFront-s.wrist.x, accuracy: 1e-12)
        XCTAssertEqual(p.elevation, atan2(s.velocity.z, hypot(s.velocity.x,s.velocity.y))*180 / .pi, accuracy: 1e-12)
    }

    func testTimingAndBodyGeometryHaveTheirActualKinematicEffects() throws {
        let p = SwingParameters(), base = SwingMechanics(parameters: p), s = base.release
        var slow = p; slow.duration *= 2
        let slower = SwingMechanics(parameters: slow).release
        XCTAssertLessThan((slower.wrist-s.wrist).length, 1e-12)
        XCTAssertLessThan((slower.velocity-s.velocity*0.5).length, 1e-12)
        XCTAssertLessThan((slower.acceleration-s.acceleration*0.25).length, 1e-10)
        var tall = p; tall.bodyHeight += 0.1
        let taller = SwingMechanics(parameters: tall).release
        XCTAssertEqual(taller.wrist.z-s.wrist.z, 0.1*p.shoulderFraction, accuracy: 1e-12)
        XCTAssertEqual(taller.velocity, s.velocity)
        var moved = p; moved.stanceForward += 0.2; moved.stanceRight += 0.3
        let a = try XCTUnwrap(base.launch(using: .init()))
        let b = try XCTUnwrap(SwingMechanics(parameters: moved).launch(using: .init()))
        XCTAssertEqual(b.distance-a.distance, -0.2, accuracy: 1e-12)
        XCTAssertEqual(b.lateral-a.lateral, 0.3, accuracy: 1e-12)
        XCTAssertEqual(a.speed,b.speed)
    }

    func testHandednessChangesShoulderLocationNotArtificialPower() {
        var p = SwingParameters(); p.yaw = 0; p.stanceRight = 0
        let right = SwingMechanics(parameters: p).release
        p.rightHanded = false
        let left = SwingMechanics(parameters: p).release
        XCTAssertEqual(right.wrist.y, p.shoulderWidth/2, accuracy: 1e-12)
        XCTAssertEqual(left.wrist.y, -p.shoulderWidth/2, accuracy: 1e-12)
        XCTAssertEqual(right.velocity, left.velocity)
    }

    func testInverseDynamicsReproducesPrescribedAngularAcceleration() {
        let p = SwingParameters(), m = SwingMechanics(parameters: p)
        for f in [0.1,0.4,0.62,0.8] {
            let time = f*p.duration, s = m.pose(at: time)
            let torque = m.torques(at: time, bagMass: 0.454)
            var links = PendulumParameters()
            links.l1 = p.upperLength; links.l2 = p.distalLength
            links.m1 = p.upperMass; links.m2 = p.distalMass; links.bag = 0.454
            let dynamics = PendulumMechanics(kind: .doubleCompound, p: links)
            let rate = dynamics.rate(.init(q1:s.q1,q2:s.q2,w1:s.w1,w2:s.w2), shoulderTorque:torque.shoulder, elbowTorque:torque.elbow)
            XCTAssertEqual(rate.w1, s.a1, accuracy: 1e-9)
            XCTAssertEqual(rate.w2, s.a2, accuracy: 1e-9)
        }
    }

    func testStaticGravityMomentsAndBagWeightIndependentOfMassMatrix() {
        let p = SwingParameters(), m = SwingMechanics(parameters: p), s = m.pose(at: 0), bag = 0.454
        let torque = m.torques(at: 0, bagMass: bag)
        let upperCOMx = p.upperLength/2*sin(s.q1)
        let elbowX = p.upperLength*sin(s.q1)
        let distalCOMx = elbowX+p.distalLength/2*sin(s.q2)
        let bagX = elbowX+p.distalLength*sin(s.q2)
        XCTAssertEqual(torque.gripForce, bag*9.81, accuracy: 1e-12)
        XCTAssertEqual(torque.shoulder, 9.81*(p.upperMass*upperCOMx+p.distalMass*distalCOMx+bag*bagX), accuracy: 1e-10)
        XCTAssertEqual(torque.elbow, 9.81*(p.distalMass*(distalCOMx-elbowX)+bag*(bagX-elbowX)), accuracy: 1e-10)
        XCTAssertEqual(m.torques(at: p.releaseTime,bagMass: 2*bag).gripForce, 2*m.torques(at: p.releaseTime,bagMass: bag).gripForce, accuracy: 1e-10)
    }

    func testEarlyReleaseFallsDownwardRatherThanInventingPositiveLaunchAngle() throws {
        var p = SwingParameters(); p.releaseFraction = 0.3
        let launch = try XCTUnwrap(SwingMechanics(parameters: p).launch(using: .init()))
        XCTAssertLessThan(launch.elevation, 0)
        XCTAssertEqual(CornholePhysics(parameters: launch).simulate().score, 0)
        p.upperLength = .nan
        XCTAssertNil(SwingMechanics(parameters: p).launch(using: .init()))
    }

    func testBoardInclineChangesGeometryAndRemainsConsistentWithItsPlane() {
        for angle in [0.0,11,25] {
            var p = TossParameters(); p.boardAngle = angle
            let b = CornholePhysics(parameters:p).board
            XCTAssertEqual(b.point(u:b.length,y:0).z, b.frontHeight+b.length*sin(angle * .pi/180), accuracy:1e-12)
            XCTAssertEqual(b.signedHeight(b.hole),0,accuracy:1e-12)
            XCTAssertEqual(b.u(b.hole),b.holeU,accuracy:1e-12)
        }
    }
    func testFeedbackPayloadDecodesWithoutInventingMissingMedian() throws {
        let json = #"{"metric":"bag_release_angle_deg","groups":{},"minimum":5,"note":"descriptive","feedback":{"zone":"green","explanation":"hole group only","minimum_per_group":10,"meaning":"not causal","ranges":{"hole":{"n":10,"low":22.25,"high":26.75}}}}"#
        let evidence = try JSONDecoder().decode(PerformanceSummary.Evidence.self,from:Data(json.utf8))
        XCTAssertEqual(evidence.feedback?.zone,"green")
        XCTAssertNil(evidence.feedback?.ranges["hole"]?.median)
        XCTAssertEqual(FeedbackZone(score:nil),.neutral)
        XCTAssertEqual(FeedbackZone(score:0),.red)
    }

}
