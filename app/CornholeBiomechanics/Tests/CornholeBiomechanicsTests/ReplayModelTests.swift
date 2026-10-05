import XCTest
@testable import CornholeBiomechanics

/// The JSON contract between replay.py / coaching.py / reliability.py and the app.
final class ReplayModelTests: XCTestCase {
    func testReplayDecodesAndMapsReleaseFramePointsOntoAFrame() throws {
        let json = """
        {"schema_version":1,"revision":"replay_v1","fps":60,"frame_count":10,"width":640,"height":480,
         "coordinates":"release_frame_pixels","reference_frame":2,
         "release_to_frame":{"5":[[1,0,-10],[0,1,4]]},
         "measured":[{"frame":2,"x":100,"y":200}],"filtered":[{"frame":2,"x":100,"y":200,"status":"measured"}],
         "model":[],"after_contact":[],"model_note":null,"model_rmse_px":null,
         "events":{"release":{"frame":2,"label":"Release","position":{"x":100,"y":200},"window":[1,2],
                   "values":[{"key":"bag_release_angle_deg","label":"Release angle","unit":"°","value":41.5,"status":"reliable"}]},
                   "final_rest":{"frame":8,"label":"Final rest","position":null,"status":"lost_after_contact","note":"n"}},
         "grades":{"bag":"GOOD"}}
        """
        let replay = try JSONDecoder().decode(ReplayDocument.self, from: Data(json.utf8))
        XCTAssertEqual(replay.toFrame(100, 200, frame: 5), CGPoint(x: 90, y: 204))
        XCTAssertEqual(replay.toFrame(100, 200, frame: 7), CGPoint(x: 100, y: 200))   // no transform: unchanged
        XCTAssertEqual(replay.orderedEvents.map(\.key), ["release", "final_rest"])
        XCTAssertEqual(replay.events["release"]?.values?.first?.value, 41.5)
    }

    /// An analysis from the board-phase version wrote the slide summary into after_contact; the replay
    /// (and so the video) must still load, with no slide points.
    func testReplayWithSlideSummaryInAfterContactStillDecodes() throws {
        let json = """
        {"fps":59.94,"frame_count":330,"width":1920,"height":1080,"coordinates":"raw_video_pixels",
         "measured":[{"frame":2,"x":100,"y":200}],"filtered":[],"model":[],
         "after_contact":{"distance_in":0.1,"duration_s":0.13,"state":"unavailable","samples":7},
         "events":{"release":{"frame":2,"label":"Release"}},"grades":{"bag":"good","scale":null}}
        """
        let replay = try JSONDecoder().decode(ReplayDocument.self, from: Data(json.utf8))
        XCTAssertTrue(replay.after_contact.isEmpty)
        XCTAssertEqual(replay.grades, ["bag": "good"])
        XCTAssertEqual(replay.measured.count, 1)
    }

    func testCoachMetricsKeepWithheldValuesEmpty() throws {
        let json = """
        {"coach_metrics":{
          "elbow_angle_deg_at_release":{"label":"Elbow angle at release","unit":"°","group":"Arm","definition":"d",
            "event":"release","frame":12,"status":"unreliable","reasons":["foreshortened"],"value":null,"noise_floor":10,"exploratory":false},
          "bag_release_angle_deg":{"label":"Release angle","unit":"°","group":"Release","definition":"d",
            "event":"release","frame":12,"status":"reliable","reasons":[],"value":41.0,"noise_floor":3,"exploratory":false}},
         "release_window":[11,12],"event_frames":{"release":12,"apex":null},"wrist_speed_arm_lengths_s":[null,1.5]}
        """
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("coach-\(UUID()).json")
        try Data(json.utf8).write(to: url)
        let document = try XCTUnwrap(CoachMetricsDocument.load(url))
        XCTAssertNil(document.coach_metrics["elbow_angle_deg_at_release"]?.value)
        XCTAssertEqual(document.coach_metrics["elbow_angle_deg_at_release"]?.statusText, "Insufficient tracking quality")
        XCTAssertEqual(document.rows(group: "Release").map(\.label), ["Release angle"])
        XCTAssertEqual(formatRange(9.75, 10.18, unit: "arm lengths/s"), "9.8–10.2 arm lengths/s")
        XCTAssertEqual(formatRange(40, 46, unit: "°"), "40–46°")
        XCTAssertEqual(formatRange(-63, -54, unit: "°"), "-63 to -54°")
        XCTAssertEqual(formatRange(-2, 2, unit: "°"), "-2 to 2°")
        XCTAssertEqual(number(-0.2, digits: 0), "0")
        XCTAssertEqual(number(-0.004, digits: 2), "0.00")
        XCTAssertEqual(number(-0.6, digits: 0), "-1")
    }
}
