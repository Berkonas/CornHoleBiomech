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

final class FrontContactTimingTests: XCTestCase {
    func testFrameClockSeeksIntoTheFrameAndMapsBackToIt() {
        for fps in [29.97, 30.0, 59.94, 60.0] {
            for frame in [0, 1, 121, 122, 123, 899] {
                let seconds = FrameClock.time(of: frame, fps: fps).seconds
                XCTAssertEqual(FrameClock.frame(at: seconds, fps: fps, count: 10_000), frame, "fps \(fps) frame \(frame)")
            }
        }
        XCTAssertNil(FrameClock.frame(at: .nan, fps: 30, count: 10))
        XCTAssertEqual(FrameClock.frame(at: 99, fps: 30, count: 10), 9)
    }

    func testDeckTrackBeforeFirstContactIsDrawnAsFlightNotSlide() {
        typealias P = TwoViewDocument.FrontPathPoint
        let untagged = (120...126).map { P(frame: $0, px: [0, 0], deck_in: nil, phase: nil) }
        let byFrame = FrontReplayOverlay.splitAtContact(untagged, contactFrame: 123)
        XCTAssertEqual(byFrame.air.map(\.frame), [120, 121, 122, 123])     // joins the slide at the contact point
        XCTAssertEqual(byFrame.deck.map(\.frame), [123, 124, 125, 126])
        let tagged = (120...123).map { P(frame: $0, px: [0, 0], deck_in: nil, phase: $0 < 122 ? "air" : "deck") }
        XCTAssertEqual(FrontReplayOverlay.splitAtContact(tagged, contactFrame: nil).deck.map(\.frame), [122, 123])
        XCTAssertEqual(FrontReplayOverlay.splitAtContact(untagged, contactFrame: nil).deck.count, untagged.count)
    }
}

final class InboxClipWindowTests: XCTestCase {
    func testClipCoversTheWholeThrowFromBeforeReleaseToAfterRest() {
        // Release at frame 85, contact 120, rest 140 of 175 at 30 fps (a typical library throw).
        let w = ReviewInboxView.clipWindow(fps: 30, frameCount: 175, release: 85, contact: 120, rest: 140)
        XCTAssertEqual(w.start!, 85.0 / 30 - 0.5, accuracy: 1e-9)          // the swing and release are in the clip
        XCTAssertEqual(w.end!, 175.0 / 30, accuracy: 1e-9)                 // runs to the clip's end after the rest
        XCTAssertEqual(w.still!, 140.0 / 30, accuracy: 1e-9)
        let noRelease = ReviewInboxView.clipWindow(fps: 30, frameCount: 175, release: nil, contact: 120, rest: nil)
        XCTAssertEqual(noRelease.start!, 4.0 - 1.2, accuracy: 1e-9)
        XCTAssertNil(ReviewInboxView.clipWindow(fps: 30, frameCount: 175, release: nil, contact: nil, rest: nil).start)
    }
}

final class MissStoryTests: XCTestCase {
    func testShortThrowThatLandedEarlyIsAFlightMiss() {
        let s = MissStory(contact: (12, 21), rest: (12, 23), made: false, offBoard: false, launchVsHoleDeg: nil)
        XCTAssertEqual(s.headline, "16 in short, on line")
        XCTAssertEqual(s.reasons.map(\.part), [.flightDistance])
        XCTAssertTrue(s.reasons[0].why.contains("landed 18 in before the hole and slid only 2 in"))
        XCTAssertTrue(s.reasons[0].fix.contains("16 in further up the board"))
    }

    func testLongThrowThatSlidPastIsASlideMissAndSidewaysAimIsNamed() {
        let s = MissStory(contact: (19, 30), rest: (19, 47), made: false, offBoard: false, launchVsHoleDeg: 1.5)
        XCTAssertEqual(s.reasons.map(\.part), [.slideDistance, .aim])          // 8 in long, 7 in right
        XCTAssertTrue(s.reasons[1].why.contains("launched 1.5° right of the line to the hole"))
        XCTAssertTrue(s.reasons[1].fix.contains("further left"))
    }

    func testSidewaysSlideAfterLandingOnLineIsNotCalledAim() {
        let s = MissStory(contact: (12, 36), rest: (18, 38), made: false, offBoard: false, launchVsHoleDeg: 0)
        XCTAssertEqual(s.reasons.map(\.part), [.sideSlide])
    }

    func testMadeAndUnmeasuredThrowsNameNothing() {
        XCTAssertTrue(MissStory(contact: (12, 33), rest: nil, made: true, offBoard: false, launchVsHoleDeg: nil).reasons.isEmpty)
        let unknown = MissStory(contact: nil, rest: nil, made: false, offBoard: true, launchVsHoleDeg: nil)
        XCTAssertEqual(unknown.headline, "Off the board")
        XCTAssertTrue(unknown.reasons.isEmpty)
        XCTAssertTrue(MissStory(contact: (13, 37), rest: (13, 40), made: false, offBoard: false, launchVsHoleDeg: nil).reasons.isEmpty)
    }
}

final class BodyCueTests: XCTestCase {
    typealias Change = ThrowAttribution.Fix.BodyChange
    func testSlowerSwingOnAShortThrowFitsTheMiss() {
        let c = Change(key: "swing_forward_duration_s", label: "Forward swing time", unit: "s", value: 0.57, target: 0.48,
                       change: -0.09, noise: 0.035, camera: "side camera", beyond_noise: true)
        let cue = BodyCue.make(c, missAlong: -13, missAcross: 0)!
        XCTAssertTrue(cue.reason.contains("slower arm swing gives less release speed"))
        XCTAssertTrue(cue.fix.contains("quicker"))
        XCTAssertTrue(cue.fitsMiss)
        XCTAssertFalse(BodyCue.make(c, missAlong: 13, missAcross: 0)!.fitsMiss)    // a slower swing does not explain long
    }

    func testHandAcrossTheBodyFitsOnlyASidewaysMiss() {
        let c = Change(key: "arm_across_body_sw", label: "Hand across the body", unit: "shoulder widths", value: 0.4,
                       target: 0.1, change: -0.3, noise: 0.15, camera: "front camera", beyond_noise: true)
        XCTAssertTrue(BodyCue.make(c, missAlong: 0, missAcross: 8)!.fitsMiss)
        XCTAssertFalse(BodyCue.make(c, missAlong: -10, missAcross: 1)!.fitsMiss)
        XCTAssertTrue(BodyCue.make(c, missAlong: 0, missAcross: 8)!.fix.contains("straight at the hole"))
    }
}
