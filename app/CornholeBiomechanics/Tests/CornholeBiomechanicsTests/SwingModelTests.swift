import XCTest
@testable import CornholeBiomechanics

final class SwingModelTests: XCTestCase {
    func testPurePendulumReleaseAngleEqualsArmAngle() throws {
        var s = SwingParameters()
        s.stepSpeed = 0
        for arm in [20.0, 35.0, 50.0] {
            s.releaseArmDeg = arm
            let r = try XCTUnwrap(SwingModel(s).release())
            XCTAssertEqual(r.angleDegrees, arm, accuracy: 1e-6)
        }
    }

    func testReleaseSpeedIsOmegaTimesRadiusPlusStep() throws {
        var s = SwingParameters()
        s.stepSpeed = 0
        let m = SwingModel(s)
        let r = try XCTUnwrap(m.release())
        XCTAssertEqual(r.speed, r.armAngularSpeed * m.radius, accuracy: 1e-9)
        s.stepSpeed = 0.5
        let stepped = try XCTUnwrap(SwingModel(s).release())
        XCTAssertGreaterThan(stepped.speed, r.speed)
        XCTAssertLessThan(stepped.angleDegrees, s.releaseArmDeg)      // forward step flattens the launch
    }

    func testReleaseHeightFromShoulderGeometry() throws {
        var s = SwingParameters()
        s.crouch = 0
        s.releaseArmDeg = 30
        let m = SwingModel(s)
        let r = try XCTUnwrap(m.release())
        XCTAssertEqual(r.height, m.shoulderHeight - m.radius * cos(30 * .pi / 180), accuracy: 1e-9)
        XCTAssertEqual(m.shoulderHeight, 0.818 * s.bodyHeight, accuracy: 1e-9)
    }

    func testMinimumJerkPeakAngularSpeed() {
        let s = SwingParameters()
        let m = SwingModel(s)
        let expected = 1.875 * (s.followThroughDeg - s.backswingDeg) * .pi / 180 / s.forwardSwingTime
        XCTAssertEqual(m.peakAngularSpeed, expected, accuracy: 1e-9)
        XCTAssertEqual(m.armAngle(at: 0), s.backswingDeg * .pi / 180, accuracy: 1e-12)
        XCTAssertEqual(m.armAngle(at: s.forwardSwingTime), s.followThroughDeg * .pi / 180, accuracy: 1e-12)
    }

    func testFasterSwingThrowsFurther() throws {
        var slow = SwingParameters(); slow.forwardSwingTime = 0.55
        var fast = slow; fast.forwardSwingTime = 0.45
        let a = try XCTUnwrap(SwingModel(slow).launch()), b = try XCTUnwrap(SwingModel(fast).launch())
        XCTAssertGreaterThan(LaunchModel(b).landing().horizontal, LaunchModel(a).landing().horizontal)
    }

    func testReleaseOutsideSwingRangeIsInvalid() {
        var s = SwingParameters()
        s.releaseArmDeg = s.followThroughDeg + 5
        XCTAssertNil(SwingModel(s).release())
    }

    func testSolvedSwingTimeLandsOnTheHole() throws {
        var s = SwingParameters()
        s.forwardSwingTime = try XCTUnwrap(SwingModel(s).swingTimeToHitHole())
        let r = LaunchModel(try XCTUnwrap(SwingModel(s).launch())).landing()
        XCTAssertEqual(r.kind, .onBoard)
        XCTAssertEqual(try XCTUnwrap(r.distanceToHole), 0, accuracy: 0.005)
    }
}
