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

/// Final-review fixes: report reload key, old insights without a verdict, the shared usable-value rule,
/// and out-of-date throws in the athlete summary.
final class FinalReviewFixTests: XCTestCase {
    private func metricsDocument(_ rows: [String: (Double, String)]) throws -> CoachMetricsDocument {
        let metrics = rows.mapValues { ["label": "x", "unit": "", "group": "Release", "definition": "", "status": $0.1,
                                        "reasons": [String](), "value": $0.0] as [String: Any] }
        let data = try JSONSerialization.data(withJSONObject: ["coach_metrics": metrics])
        return try JSONDecoder().decode(CoachMetricsDocument.self, from: data)
    }

    func testReloadKeyChangesWhenThisThrowsAnalysisStartsOrFinishes() {
        var trial = Trial(athleteID: UUID(), sourceVideoRelativePath: "videos/a.mov", originalFilename: "a.mov",
                          cameraView: .side, throwingSide: .right, targetDirection: .leftToRight)
        let idle = ThrowReportView.reloadKey(trial: trial, analysingThis: false)
        let running = ThrowReportView.reloadKey(trial: trial, analysingThis: true)
        XCTAssertNotEqual(idle, running, "the run of this throw starting must reload the page")
        trial.analysisRelativePath = "analysis/a"
        trial.analysisStatus = "Analyzed"
        let done = ThrowReportView.reloadKey(trial: trial, analysingThis: false)
        XCTAssertNotEqual(done, running, "the run finishing must reload the page even inside a batch")
        XCTAssertNotEqual(done, idle, "a never-analysed throw that is now analysed must reload")
    }

    func testInsightsWithoutVerdictAreRefreshedNotReanalysed() throws {
        let url = try XCTUnwrap(Bundle.module.url(forResource: "insights", withExtension: "json", subdirectory: "Fixtures"))
        var data = ThrowReportData()
        data.insight = try JSONDecoder.projectDecoder.decode(TrialInsights.self, from: Data(contentsOf: url))
        XCTAssertNil(data.insight?.verdict, "fixture is a pre-verdict insights.json")
        XCTAssertFalse(ThrowReportView.lacksVerdict(data), "no coach metrics: a refresh cannot add a verdict")
        data.coach = try metricsDocument(["bag_release_speed_m_s": (7.8, "reliable")])
        XCTAssertTrue(ThrowReportView.lacksVerdict(data))
        data.staleReason = "corrections_changed"
        XCTAssertFalse(ThrowReportView.lacksVerdict(data), "an out-of-date analysis needs re-analysis, not a refresh")
        XCTAssertTrue(VerdictCard.missingText(canRefresh: true).contains("Refresh"))
        XCTAssertFalse(VerdictCard.missingText(canRefresh: true).contains("Re-analyze"))
        XCTAssertTrue(VerdictCard.missingText(canRefresh: false).contains("Re-analyze"))
    }

    func testUnavailableValuesAreNotUsedLikePython() throws {
        let document = try metricsDocument(["bag_release_speed_m_s": (7.8, "unavailable"), "bag_release_angle_deg": (40, "caution"),
                                            "bag_release_height_m": (0.9, "unreliable")])
        XCTAssertNil(document.coach_metrics["bag_release_speed_m_s"]?.usableValue)
        XCTAssertEqual(document.coach_metrics["bag_release_angle_deg"]?.usableValue, 40)
        XCTAssertNil(document.coach_metrics["bag_release_height_m"]?.usableValue)
        var data = ThrowReportData()
        data.coach = document
        XCTAssertNil(data.value("bag_release_speed_m_s"))
    }

    func testStaleThrowsAreLeftOutOfFooterStatsAndReleaseMap() throws {
        func row(_ n: Int, _ speed: Double, stale: Bool) -> SummaryThrowRow {
            var r = SummaryThrowRow(id: UUID(), number: n, label: "Throw \(n)", score: nil,
                                    values: [SummaryThrowRow.speedKey: speed, SummaryThrowRow.angleKey: 40, SummaryThrowRow.heightKey: 0.9])
            r.isStale = stale
            return r
        }
        let rows = [row(1, 7, stale: false), row(2, 8, stale: false), row(3, 20, stale: true)]
        XCTAssertEqual(ThrowComparisonTable.footerValues(rows, column: ThrowComparisonTable.columns[0]), [7, 8])
        XCTAssertEqual(rows.compactMap(\.release).count, 2)
        XCTAssertEqual(AthleteSummaryContent.staleNote(rows), "; 1 out-of-date throw is not plotted")
        XCTAssertEqual(AthleteSummaryContent.staleNote(Array(rows.prefix(2))), "")
    }

    func testSummaryRowAndMeasuredReleaseSkipUnavailableAndStale() throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        func metric(_ value: Double, _ status: String) -> [String: Any] {
            ["label": "x", "unit": "", "group": "Release", "definition": "", "status": status, "reasons": [String](), "value": value]
        }
        let results: [String: Any] = ["coach_metrics": [
            "bag_release_speed_m_s": metric(7.8, "reliable"), "bag_release_angle_deg": metric(41, "reliable"),
            "bag_release_height_m": metric(0.9, "reliable"), "elbow_angle_deg_at_release": metric(150, "unavailable")]]
        let resultsURL = folder.appendingPathComponent("results.json")
        try JSONSerialization.data(withJSONObject: results).write(to: resultsURL)
        let row = SummaryThrowRow.read(.init(id: UUID(), number: 1, label: "Throw 1", score: nil, analysisURL: folder))
        XCTAssertNil(row.elbow)
        XCTAssertNotNil(row.withheld["elbow_angle_deg_at_release"])
        let source = MeasuredRelease.Source(id: UUID(), label: "Throw 1", score: nil, results: resultsURL)
        XCTAssertNotNil(MeasuredRelease.read(source))
        try Data("{\"reason\":\"corrections_changed\"}".utf8).write(to: folder.appendingPathComponent("needs_reanalysis.json"))
        XCTAssertNil(MeasuredRelease.read(source), "an out-of-date throw is not a mark on the map")
    }
}
