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
    func testAllWorkOnItemsUpToTwoThenOneNoteAndOneGoodRestBehindMore() {
        let items = [Verdict.Item(kind: "fix", text: "a"), Verdict.Item(kind: "fix", text: "b"), Verdict.Item(kind: "fix", text: "e"),
                     Verdict.Item(kind: "good", text: "c"), Verdict.Item(kind: "note", text: "d"), Verdict.Item(kind: "good", text: "f")]
        let split = VerdictCard.split(items)
        XCTAssertEqual(split.shown.map(\.text), ["a", "b", "c", "d"])
        XCTAssertEqual(split.more.map(\.text), ["e", "f"])
        XCTAssertTrue(VerdictCard.split([Verdict.Item(kind: "fix", text: "a")]).more.isEmpty)
    }
}

final class FlightChartDataTests: XCTestCase {
    /// The measured path starts before release (hand-held bag); the chart must start at release and stop at first contact.
    func testFlightIsAnchoredAtReleaseAndEndsAtFirstContact() throws {
        let points = (0...10).map { #"{"frame": \#($0), "x": \#(Double($0) * 10), "y": \#(50 - Double($0))}"# }.joined(separator: ",")
        let model = (3...12).map { #"{"frame": \#($0), "x": \#(Double($0) * 10), "y": 47}"# }.joined(separator: ",")
        let json = """
        {"fps": 60, "frame_count": 20, "width": 100, "height": 100, "coordinates": "release_frame_pixels",
         "measured": [\(points)], "filtered": [], "model": [\(model)], "after_contact": [],
         "events": {"release": {"frame": 3, "label": "Release", "position": {"x": 30, "y": 47}},
                    "first_contact": {"frame": 8, "label": "First contact"}},
         "grades": {}}
        """
        let replay = try JSONDecoder().decode(ReplayDocument.self, from: Data(json.utf8))
        let flight = try XCTUnwrap(FlightChartData.make(replay: replay, scale: nil, releaseHeight: nil, boardDistance: nil))
        XCTAssertEqual(flight.measured.map(\.id), Array(3...8))
        XCTAssertEqual(flight.measured.first?.x, 0); XCTAssertEqual(flight.measured.first?.y, 0)
        XCTAssertEqual(try XCTUnwrap(flight.measured.last?.x), 50, accuracy: 1e-9)
        XCTAssertEqual(try XCTUnwrap(flight.measured.last?.y), 5, accuracy: 1e-9)
        XCTAssertEqual(flight.model.map(\.id), Array(3...8))
        XCTAssertFalse(flight.metres)
    }

    func testJointAngleDomainKeepsNegativeValues() {
        let domain = JointAngleChart.domain([-15, 170])
        XCTAssertLessThan(domain.lowerBound, -15); XCTAssertGreaterThan(domain.upperBound, 170)
    }
}

final class ReportStateTests: XCTestCase {
    func testStaleReasonReadsMarkerFile() throws {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("stale-\(UUID().uuidString).json")
        defer { try? FileManager.default.removeItem(at: url) }
        XCTAssertNil(ThrowReportView.staleReason(url))
        try Data(#"{"reason":"bag_seed_changed"}"#.utf8).write(to: url)
        XCTAssertEqual(ThrowReportView.staleReason(url), "bag_seed_changed")
        XCTAssertEqual(ThrowReportContent.staleText("bag_seed_changed"), "The bag track was corrected after this analysis.")
    }
}

final class NoPoseBagEditingTests: XCTestCase {
    /// Without pose_raw.json the bag and flight editors take the clip geometry from replay.json,
    /// so a first-contact frame can still be saved.
    @MainActor func testGeometryFromReplayEnablesFirstContactWithoutPose() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("nopose-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: dir) }
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let replay = """
        {"fps": 60, "frame_count": 120, "width": 1920, "height": 1080, "coordinates": "release_frame_pixels",
         "measured": [], "filtered": [], "model": [], "after_contact": [], "events": {}, "grades": {}}
        """
        try Data(replay.utf8).write(to: dir.appendingPathComponent("replay.json"))
        let data = TrialDataController()
        data.load(analysisURL: dir)
        XCTAssertNil(data.pose)
        XCTAssertEqual(data.geometry, VideoGeometry(width: 1920, height: 1080, frameCount: 120, fps: 60))
        XCTAssertTrue(FlightReviewEditor.isValidContact("80", frameCount: data.geometry?.frameCount))
        XCTAssertTrue(FlightReviewEditor.isValidContact("", frameCount: data.geometry?.frameCount))
        XCTAssertFalse(FlightReviewEditor.isValidContact("120", frameCount: data.geometry?.frameCount))
        XCTAssertFalse(FlightReviewEditor.isValidContact("80", frameCount: nil))
    }
}
