import XCTest
@testable import CornholeBiomechanics

final class AthleteSummaryTests: XCTestCase {
    func testMedianAndSampleSD() throws {
        let odd = try XCTUnwrap(MedianSD.of([7.0, 9.0, 8.0]))
        XCTAssertEqual(odd.median, 8.0)
        XCTAssertEqual(try XCTUnwrap(odd.sd), 1.0, accuracy: 1e-12)   // sample SD (n − 1)
        XCTAssertEqual(odd.n, 3)

        let even = try XCTUnwrap(MedianSD.of([1, 2, 3, 10]))
        XCTAssertEqual(even.median, 2.5)
        XCTAssertEqual(try XCTUnwrap(even.sd), 4.08248, accuracy: 1e-5)   // √(50 / 3)

        let single = try XCTUnwrap(MedianSD.of([5, .nan]))
        XCTAssertEqual(single.median, 5)
        XCTAssertNil(single.sd)
        XCTAssertEqual(single.n, 1)

        XCTAssertNil(MedianSD.of([]))
        XCTAssertNil(MedianSD.of([.infinity]))
    }

    func testFooterTextShowsMedianDotSDWithUnitAndN() {
        let speed = ThrowComparisonTable.columns[0], angle = ThrowComparisonTable.columns[1]
        XCTAssertEqual(ThrowComparisonTable.footerText([7, 8, 9, 7.5, 8.5], column: speed), "8.0 · 0.79 m/s (n 5)")
        XCTAssertEqual(ThrowComparisonTable.footerText([30, 40, 30, 40, 35, 35], column: angle), "35 · 4.5° (n 6)")
        XCTAssertEqual(ThrowComparisonTable.footerText([], column: speed), "—")
    }

    func testFooterTextWithholdsSDBelowTheMinimum() {
        let speed = ThrowComparisonTable.columns[0], tempo = ThrowComparisonTable.columns[5]
        XCTAssertEqual(ThrowComparisonTable.footerText([7, 9], column: speed), "8.0 m/s · SD —, too few (n 2)")
        XCTAssertEqual(ThrowComparisonTable.footerText([1.8], column: tempo), "1.80 · SD —, too few (n 1)")
        XCTAssertEqual(ThrowComparisonTable.footerText([7, 8, 9, 10], column: speed), "8.5 m/s · SD —, too few (n 4)")
    }

    func testRowReadsReliableValuesWithholdsUnreliableAndFindsGrades() throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        func metric(_ value: Double, _ status: String, reason: String = "") -> [String: Any] {
            ["label": "x", "unit": "", "group": "Release", "definition": "", "status": status,
             "reasons": reason.isEmpty ? [] : [reason], "value": value]
        }
        let results: [String: Any] = [
            "coach_metrics": ["bag_release_speed_m_s": metric(7.8, "reliable"), "bag_release_angle_deg": metric(41, "caution"),
                              "elbow_angle_deg_at_release": metric(150, "unreliable", reason: "Elbow hidden at release.")],
            "summaries": ["release_to_board_front_m": 7.3],
        ]
        try JSONSerialization.data(withJSONObject: results).write(to: folder.appendingPathComponent("results.json"))
        try JSONSerialization.data(withJSONObject: ["grades": ["pose": "GOOD", "bag": "POOR", "release": "WARNING"]])
            .write(to: folder.appendingPathComponent("replay.json"))

        let row = SummaryThrowRow.read(.init(id: UUID(), number: 2, label: "Throw 2", score: .onBoard, analysisURL: folder))
        XCTAssertEqual(row.speed, 7.8)
        XCTAssertEqual(row.angle, 41)
        XCTAssertNil(row.elbow)
        XCTAssertEqual(row.withheld["elbow_angle_deg_at_release"], "Elbow hidden at release.")
        XCTAssertNil(row.height)
        XCTAssertNil(row.release, "no release on the map without a height")
        XCTAssertEqual(row.worstGrade, "POOR")
        XCTAssertFalse(row.isStale)
        XCTAssertEqual(row.distance, 7.3)
        // Missing values sort after measured ones.
        XCTAssertEqual(row[sortValue: "bag_release_height_m"], .infinity)
    }

    func testTypicalReleaseUsesMediansAndMeasuredDistanceOnlyFromThreeThrows() throws {
        func release(_ v: Double, _ a: Double, _ h: Double, _ d: Double?) -> MeasuredRelease {
            MeasuredRelease(id: UUID(), label: "", speed: v, angle: a, height: h, score: nil, distance: d)
        }
        let two = [release(7, 30, 0.8, 7.0), release(9, 40, 1.0, 7.2)]
        let typical = try XCTUnwrap(AthleteSummaryContent.typicalRelease(two))
        XCTAssertEqual(typical.params.speed, 8)
        XCTAssertEqual(typical.params.angleDegrees, 35)
        XCTAssertEqual(typical.params.releaseHeight, 0.9, accuracy: 1e-12)
        XCTAssertFalse(typical.measuredDistance)
        XCTAssertEqual(typical.params.distanceToBoard, 7.7)

        let three = try XCTUnwrap(AthleteSummaryContent.typicalRelease(two + [release(8, 36, 0.9, 7.6)]))
        XCTAssertTrue(three.measuredDistance)
        XCTAssertEqual(three.params.distanceToBoard, 7.2, accuracy: 1e-12)
        XCTAssertNil(AthleteSummaryContent.typicalRelease([]))
    }

    func testElbowCurvesBreakAtGapsAndReadTheBand() throws {
        let json = """
        {"n": 2, "minimum_trials": 2, "message": "", "components": [],
         "curves": {"elbow_angle_deg": {"mean": [100, 120, 140], "sd": [5, null, 5]}},
         "traces": [{"trial_id": "\(UUID().uuidString)", "wrist": [], "elbow": [100, null, 140]},
                    {"trial_id": "not-a-uuid", "wrist": [], "elbow": [100, 120, 140]}],
         "tau": [0, 0.5, 1]}
        """
        let consistency = try JSONDecoder().decode(TrialInsights.Consistency.self, from: Data(json.utf8))
        let curves = ElbowCurves(consistency: consistency)
        XCTAssertEqual(curves.throwCount, 2)
        XCTAssertEqual(curves.lines.count, 5)
        XCTAssertEqual(Set(curves.lines.map(\.series)).count, 3, "the gap splits the first throw into two runs")
        XCTAssertEqual(curves.lines.map(\.x).max(), 100)
        XCTAssertEqual(curves.band.map(\.x), [0, 100], "points without an SD are left out of the band")
        XCTAssertEqual(curves.band.first?.low, 95)
    }
}
