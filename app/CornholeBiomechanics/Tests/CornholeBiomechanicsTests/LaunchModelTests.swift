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

    // MARK: - Zones (mirror python zones.ZoneSettings.zone_for)

    private func holeThrow() throws -> LaunchParameters {
        var p = LaunchParameters(speed: 5, angleDegrees: 35, releaseHeight: 0.8, distanceToBoard: 7.7)
        p.speed = try XCTUnwrap(LaunchModel(p).speedToHitHole())
        return p
    }

    func testHoleCentreIsHoleZone() throws {
        XCTAssertEqual(LaunchModel(try holeThrow()).zone(), .hole)
    }

    func testTwoMetresPerSecondFasterIsLongAndOff() throws {
        var p = try holeThrow(); p.speed += 2
        XCTAssertEqual(LaunchModel(p).landing().kind, .pastBoard)
        XCTAssertEqual(LaunchModel(p).zone(), .off)
    }

    func testTwoMetresPerSecondSlowerIsShortAndOff() throws {
        var p = try holeThrow(); p.speed -= 2
        XCTAssertEqual(LaunchModel(p).landing().kind, .shortOfBoard)
        XCTAssertEqual(LaunchModel(p).zone(), .off)
    }

    func testBoardLandingOutsideHoleWindowIsBoard() throws {
        var p = try holeThrow(); p.distanceToBoard += 0.7     // board moved back: lands near the front edge
        let hit = LaunchModel(p).landing()
        XCTAssertEqual(hit.kind, .onBoard)
        XCTAssertLessThan(try XCTUnwrap(hit.alongBoard), p.board.holeAlong - 0.45)
        XCTAssertEqual(LaunchModel(p).zone(), .board)
    }

    func testShortBySlideUpOrLessIsBoardFurtherIsOff() throws {
        var p = try holeThrow(); p.distanceToBoard = 100
        let floor = LaunchModel(p).landing().horizontal
        p.distanceToBoard = floor + 0.29
        XCTAssertEqual(LaunchModel(p).landing().kind, .shortOfBoard)
        XCTAssertEqual(LaunchModel(p).zone(), .board)
        p.distanceToBoard = floor + 0.31
        XCTAssertEqual(LaunchModel(p).zone(), .off)
        XCTAssertEqual(LaunchModel(p).zone(slideUp: 0.40), .board)
    }

    func testFrontFaceIsOff() {
        let p = LaunchParameters(speed: 10, angleDegrees: 0, releaseHeight: 0.05, distanceToBoard: 0.5)
        XCTAssertEqual(LaunchModel(p).landing().kind, .frontOfBoard)
        XCTAssertEqual(LaunchModel(p).zone(), .off)
    }

    func testHoleWindowBoundariesAreInclusive() {
        let b = BoardGeometry.regulation
        func board(_ along: Double) -> LaunchModel.Landing {
            LaunchModel.Landing(kind: .onBoard, time: 1, horizontal: 8, alongBoard: along, distanceToHole: along - b.holeAlong)
        }
        XCTAssertEqual(LaunchModel.zone(for: board(b.holeAlong - 0.45), distance: 7.7, board: b), .hole)
        XCTAssertEqual(LaunchModel.zone(for: board(b.holeAlong + b.holeRadius), distance: 7.7, board: b), .hole)
        XCTAssertEqual(LaunchModel.zone(for: board(b.holeAlong - 0.4501), distance: 7.7, board: b), .board)
        XCTAssertEqual(LaunchModel.zone(for: board(b.holeAlong + b.holeRadius + 0.0001), distance: 7.7, board: b), .board)
        XCTAssertEqual(LaunchModel.zone(for: board(0.2), distance: 7.7, board: b, slideAllowance: 0.9), .hole)
        let short = LaunchModel.Landing(kind: .shortOfBoard, time: 1, horizontal: 7.401)
        XCTAssertEqual(LaunchModel.zone(for: short, distance: 7.7, board: b), .board)   // 0.299 m short
        let farShort = LaunchModel.Landing(kind: .shortOfBoard, time: 1, horizontal: 7.399)
        XCTAssertEqual(LaunchModel.zone(for: farShort, distance: 7.7, board: b), .off)
    }

    // MARK: - Success map and scene geometry

    func testSuccessMapMatchesModelZoneInEveryCell() {
        for (height, distance) in [(0.8, 7.7), (0.5, 5.0), (1.3, 9.0), (0.25, 7.7)] {
            let grid = SuccessMapGrid.compute(height: height, distance: distance)
            XCTAssertEqual(grid.runs.count, SuccessMapGrid.columns)
            var mismatches = 0
            for column in 0..<SuccessMapGrid.columns {
                for row in 0..<SuccessMapGrid.rows {
                    let p = LaunchParameters(speed: SuccessMapGrid.speed(row: row), angleDegrees: SuccessMapGrid.angle(column: column),
                                             releaseHeight: height, distanceToBoard: distance)
                    if grid.zone(column: column, row: row) != LaunchModel(p).zone() { mismatches += 1 }
                }
            }
            XCTAssertEqual(mismatches, 0, "h \(height) D \(distance)")
        }
    }

    func testSuccessMapGridIs120By160HalfDegreeByFiveCentimetreCells() {
        XCTAssertEqual(SuccessMapGrid.columns, 120)
        XCTAssertEqual(SuccessMapGrid.rows, 160)
        XCTAssertEqual(SuccessMapGrid.angle(column: 0), 10.25, accuracy: 1e-12)
        XCTAssertEqual(SuccessMapGrid.speed(row: 159), 10.975, accuracy: 1e-12)
    }

    func testThrowerHandIsAtReleasePointAtRelease() {
        for (h, angle) in [(0.8, 35.0), (0.3, 10.0), (1.8, 60.0), (0.2, 0.0), (1.1, -5.0)] {
            let p = LaunchParameters(speed: 6, angleDegrees: angle, releaseHeight: h, distanceToBoard: 7.7)
            let pose = ThrowerPose.at(p, time: ThrowTimeline.swing)
            XCTAssertEqual(pose.hand.x, 0, accuracy: 1e-9, "h \(h) angle \(angle)")
            XCTAssertEqual(pose.hand.y, h, accuracy: 1e-9, "h \(h) angle \(angle)")
            // Segments keep their lengths (the elbow joint closes the arm).
            XCTAssertEqual(hypot(pose.elbow.x - pose.shoulder.x, pose.elbow.y - pose.shoulder.y), ThrowerPose.upperArm, accuracy: 1e-6)
            XCTAssertEqual(hypot(pose.hand.x - pose.elbow.x, pose.hand.y - pose.elbow.y), ThrowerPose.forearm, accuracy: 1e-6)
            XCTAssertEqual(pose.frontAnkle.y, ThrowerPose.ankleHeight, accuracy: 1e-12)
        }
    }

    func testTimelineIsFlightPlusSixTenths() {
        let p = LaunchParameters(speed: 7, angleDegrees: 35, releaseHeight: 0.9, distanceToBoard: 7.7)
        XCTAssertEqual(ThrowTimeline.total(p), LaunchModel(p).landing().time + 0.6, accuracy: 1e-12)
    }

    func testSceneDrawsFinalStateWithReduceMotionOrStaleRun() {
        let p = LaunchParameters(speed: 7, angleDegrees: 35, releaseHeight: 0.9, distanceToBoard: 7.7)
        let start = Date(timeIntervalSinceReferenceDate: 1000)
        let run = LaunchRun(params: p, start: start)
        let now = start.addingTimeInterval(0.4)
        // Live run: elapsed time × rate.
        XCTAssertNotNil(LaunchScene.activeRun(run, params: p, reduceMotion: false, frozenTime: nil))
        XCTAssertEqual(LaunchScene.sceneTime(run: run, params: p, reduceMotion: false, frozenTime: nil, rate: 0.25, now: now), 0.1, accuracy: 1e-9)
        // Reduce Motion: no active run, final state (∞).
        XCTAssertNil(LaunchScene.activeRun(run, params: p, reduceMotion: true, frozenTime: nil))
        XCTAssertEqual(LaunchScene.sceneTime(run: run, params: p, reduceMotion: true, frozenTime: nil, rate: 1, now: now), .infinity)
        // Parameters changed since the throw (slider drag): final state for the new parameters.
        var moved = p; moved.speed += 0.5
        XCTAssertEqual(LaunchScene.sceneTime(run: run, params: moved, reduceMotion: false, frozenTime: nil, rate: 1, now: now), .infinity)
        XCTAssertEqual(LaunchScene.sceneTime(run: nil, params: p, reduceMotion: false, frozenTime: nil, rate: 1, now: now), .infinity)
    }
}
