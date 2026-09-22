import XCTest
@testable import CornholeBiomechanics

final class ThrowComparisonTests: XCTestCase {
    static func flight(_ points: [(Int, Double?, Double?)]) -> FlightSummary {
        FlightSummary(status: "reviewed_track", message: "", time_of_flight_seconds: 1, observed_rise_pixels: nil,
                      horizontal_travel_pixels: nil, coverage: 1,
                      trajectory: points.map { .init(frame: $0.0, x: $0.1, y: $0.2) }, frame_interval_seconds: 1 / 60)
    }

    func testFlightIsReleaseCentredScaledFlippedAndSplitAtGaps() throws {
        let f = Self.flight([(10, 500, 400), (11, 480, 380), (12, nil, nil), (13, 440, 370)])
        let n = try XCTUnwrap(NormalizedFlight(name: "A", flight: f, armLengthPixels: 100, direction: .rightToLeft))
        XCTAssertEqual(n.samples.map(\.forward), [0, 0.2, 0.6])       // right-to-left: moving left is forward
        XCTAssertEqual(n.samples.map(\.up), [0, 0.2, 0.3])            // image y down → up positive
        XCTAssertEqual(n.samples.map(\.segment), [0, 0, 1])           // gap starts a new segment
    }

    func testFlightNeedsScaleAndTwoPoints() {
        XCTAssertNil(NormalizedFlight(name: "A", flight: Self.flight([(1, 1, 1), (2, 2, 2)]), armLengthPixels: nil, direction: .leftToRight))
        XCTAssertNil(NormalizedFlight(name: "A", flight: Self.flight([(1, 1, 1)]), armLengthPixels: 100, direction: .leftToRight))
    }

    func testPythonThrowComparisonDecodes() throws {
        let json = #"{"a":"T0","b":"T6","summary":"Compared with Throw 1, Throw 7 had a lower release angle (26° vs 35°).","differences":[{"key":"bag_release_angle_deg","label":"Release angle","unit":"°","a":35,"b":26,"difference":-9,"athlete_sd":4.4,"standardized":-2.0,"meaningful":true,"word":"lower","decimals":0}]}"#
        let value = try JSONDecoder.projectDecoder.decode(ThrowComparison.self, from: Data(json.utf8))
        XCTAssertTrue(value.differences[0].meaningful)
        XCTAssertEqual(value.differences[0].difference, -9)
    }
}
