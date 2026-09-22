import XCTest
@testable import CornholeBiomechanics

final class FullThrowTests: XCTestCase {
    func testUnknownOutcomeRoundTripsWithoutBecomingMiss() throws {
        let outcome = TrialOutcome()
        XCTAssertNil(outcome.scoreCategory)
        let decoded = try JSONDecoder().decode(TrialOutcome.self, from: JSONEncoder().encode(outcome))
        XCTAssertNil(decoded.scoreCategory)
        let legacy = #"{"intended_target":"hole","score_category":0,"throw_type":"Standard","notes":""}"#
        XCTAssertEqual(try JSONDecoder().decode(TrialOutcome.self, from: Data(legacy.utf8)).scoreCategory, .offBoard)
    }

    func testFlightGapsAndUnavailableMetricDecode() throws {
        let json = #"{"status":"events_reviewed","message":"Review track","time_of_flight_seconds":1.25,"observed_rise_pixels":null,"horizontal_travel_pixels":null,"coverage":0.5,"trajectory":[{"frame":198,"x":null,"y":null},{"frame":199,"x":10,"y":20}],"frame_interval_seconds":0.01667}"#
        let flight = try JSONDecoder().decode(FlightSummary.self, from: Data(json.utf8))
        XCTAssertEqual(flight.time_of_flight_seconds, 1.25)
        XCTAssertNil(flight.trajectory[0].x)
        XCTAssertNil(flight.observed_rise_pixels)
    }

    @MainActor
    func testSchema3BackupBeforeWritingUnknownOutcomes() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let old = StudyProject(schemaVersion: 3, name: "Legacy")
        let bytes = try JSONEncoder.projectEncoder.encode(old)
        try bytes.write(to: root.appendingPathComponent("project.json"))
        let paths = LibraryPaths(applicationSupportURL: root.appendingPathComponent("Support"), defaultLibraryURL: root, libraryRootWasOverridden: true)
        let store = ProjectStore(paths: paths, automaticallyRestore: false)
        try store.open(root)
        try store.addAthlete(NewAthleteDraft(participantCode: "P1"))
        XCTAssertEqual(store.project?.schemaVersion, 4)
        XCTAssertEqual(try Data(contentsOf: root.appendingPathComponent("project.schema3.backup.json")), bytes)
    }
}
