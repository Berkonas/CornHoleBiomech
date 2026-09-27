import XCTest
@testable import CornholeBiomechanics

final class ThrowReportTests: XCTestCase {
    private func zone(speed: Double, angle: Double, height: Double = 0.8, distance: Double = 7.7) -> LandingZone {
        LaunchModel(LaunchParameters(speed: speed, angleDegrees: angle, releaseHeight: height, distanceToBoard: distance)).zone()
    }

    func testSpeedWindowIsTheContiguousHoleRunInHundredths() throws {
        let window = try XCTUnwrap(HoleWindow.speed(angle: 35, height: 0.8, distance: 7.7, near: 8))
        // Every 0.01 m/s step inside is a hole; one step outside on either side is not.
        for v in stride(from: window.lowerBound, through: window.upperBound + 1e-9, by: 0.01) {
            XCTAssertEqual(zone(speed: v, angle: 35), .hole, "speed \(v)")
        }
        XCTAssertNotEqual(zone(speed: window.lowerBound - 0.01, angle: 35), .hole)
        XCTAssertNotEqual(zone(speed: window.upperBound + 0.01, angle: 35), .hole)
        // The speed that puts first contact on the hole centre lies inside the window.
        let centre = try XCTUnwrap(LaunchModel(LaunchParameters(speed: 8, angleDegrees: 35, releaseHeight: 0.8, distanceToBoard: 7.7)).speedToHitHole())
        XCTAssertTrue(window.contains(centre))
    }

    func testAngleWindowIsTheContiguousHoleRunInTenths() throws {
        let speed = try XCTUnwrap(LaunchModel(LaunchParameters(speed: 8, angleDegrees: 35, releaseHeight: 0.8, distanceToBoard: 7.7)).speedToHitHole())
        let window = try XCTUnwrap(HoleWindow.angle(speed: speed, height: 0.8, distance: 7.7, near: 35))
        XCTAssertTrue(window.contains(35))
        XCTAssertEqual(zone(speed: speed, angle: window.lowerBound), .hole)
        XCTAssertEqual(zone(speed: speed, angle: window.upperBound), .hole)
        XCTAssertNotEqual(zone(speed: speed, angle: window.lowerBound - 0.1), .hole)
        XCTAssertNotEqual(zone(speed: speed, angle: window.upperBound + 0.1), .hole)
    }

    func testNoWindowWhenNoSpeedReachesTheHole() {
        // Straight down: no speed puts the bag in the hole window.
        XCTAssertNil(HoleWindow.speed(angle: -89, height: 0.8, distance: 7.7, near: 8))
    }

    func testTimeFromReleaseUsesKinematicsTimeColumn() {
        let rows = [["frame": "0", "time_seconds": "0.0", "elbow_angle_deg": "150", "trunk_inclination_deg": "10"],
                    ["frame": "1", "time_seconds": "0.02", "elbow_angle_deg": "", "trunk_inclination_deg": "12"],
                    ["frame": "2", "time_seconds": "0.04", "elbow_angle_deg": "170", "trunk_inclination_deg": "14"]]
        let series = JointAngleSeries(rows: rows, releaseFrame: 2)
        XCTAssertEqual(series.points.filter { $0.series == "Elbow angle" }.map { $0.ms.rounded() }, [-40, 0])
        XCTAssertEqual(series.points.filter { $0.series == "Trunk inclination" }.map(\.value), [10, 12, 14])
        XCTAssertEqual(series.points.first { $0.series == "Elbow angle" }?.ms ?? .nan, -40, accuracy: 1e-9)
    }
}

final class VerdictCardTests: XCTestCase {
    func testAtMostThreeRowsKeepingOneOfEachKind() {
        let items = [Verdict.Item(kind: "fix", text: "a"), Verdict.Item(kind: "fix", text: "b"),
                     Verdict.Item(kind: "good", text: "c"), Verdict.Item(kind: "note", text: "d")]
        XCTAssertEqual(VerdictCard.shown(items).map(\.text), ["a", "c", "d"])
        XCTAssertEqual(VerdictCard.shown(Array(items.prefix(2))).map(\.text), ["a", "b"])
    }
}
