import XCTest
@testable import CornholeBiomechanics

final class LaunchModelTests: XCTestCase {
    func testFlatGroundRangeMatchesClosedForm() {
        // Board placed out of reach: the bag lands on the floor at the textbook range.
        var p = LaunchParameters(speed: 7, angleDegrees: 30, releaseHeight: 0, distanceToBoard: 50)
        p.board = BoardGeometry.regulation
        let r = LaunchModel(p).landing()
        let expected = 49 * sin(2 * .pi / 6) / LaunchModel.gravity
        XCTAssertEqual(r.kind, .shortOfBoard)
        XCTAssertEqual(r.horizontal, expected, accuracy: 1e-6)
    }

    func testBoardLandingSolvesInclinedSurfaceIntersection() throws {
        let p = LaunchParameters(speed: 7, angleDegrees: 35, releaseHeight: 0.9, distanceToBoard: 4.5)
        let r = LaunchModel(p).landing()
        XCTAssertEqual(r.kind, .onBoard)
        let along = try XCTUnwrap(r.alongBoard)
        let b = p.board
        // Landing point lies on the board plane.
        let t = r.time, x = p.vx * t, y = p.releaseHeight + p.vy * t - 0.5 * LaunchModel.gravity * t * t
        XCTAssertEqual(x, p.distanceToBoard + along * cos(b.angle), accuracy: 1e-9)
        XCTAssertEqual(y, b.frontHeight + along * sin(b.angle), accuracy: 1e-9)
    }

    func testSolvedSpeedHitsHoleCentre() throws {
        let p = LaunchParameters(speed: 5, angleDegrees: 40, releaseHeight: 0.8, distanceToBoard: 7.7)
        let speed = try XCTUnwrap(LaunchModel(p).speedToHitHole())
        var hit = p; hit.speed = speed
        let r = LaunchModel(hit).landing()
        XCTAssertEqual(r.kind, .onBoard)
        XCTAssertEqual(try XCTUnwrap(r.alongBoard), p.board.holeAlong, accuracy: 1e-4)
    }

    func testTooSlowIsShortAndTooFastIsLong() {
        var p = LaunchParameters(speed: 3, angleDegrees: 35, releaseHeight: 0.8, distanceToBoard: 7.7)
        XCTAssertEqual(LaunchModel(p).landing().kind, .shortOfBoard)
        p.speed = 14
        XCTAssertEqual(LaunchModel(p).landing().kind, .pastBoard)
    }

    func testSensitivityHasPhysicalSignsNearHole() throws {
        var p = LaunchParameters(speed: 5, angleDegrees: 35, releaseHeight: 0.8, distanceToBoard: 7.7)
        p.speed = try XCTUnwrap(LaunchModel(p).speedToHitHole())
        let s = LaunchModel(p).sensitivity()
        // Below 45°, more speed, more angle and more height all carry the bag further.
        XCTAssertGreaterThan(try XCTUnwrap(s.perSpeed), 0)
        XCTAssertGreaterThan(try XCTUnwrap(s.perAngle), 0)
        XCTAssertGreaterThan(try XCTUnwrap(s.perHeight), 0)
    }

    func testTrajectoryEndsAtLanding() throws {
        let p = LaunchParameters(speed: 7, angleDegrees: 35, releaseHeight: 0.9, distanceToBoard: 4.5)
        let m = LaunchModel(p)
        let path = m.trajectory(samples: 50)
        XCTAssertEqual(try XCTUnwrap(path.last).x, p.vx * m.landing().time, accuracy: 1e-9)
    }
}
