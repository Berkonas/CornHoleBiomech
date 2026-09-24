import XCTest
@testable import CornholeBiomechanics

final class DesignSystemTests: XCTestCase {
    func testDomainIncludesTargetAndCurrent() {
        let m = RangeBarModel(values: [7.5, 7.8, 8.0], current: 9.0, target: 6.9...7.2)
        XCTAssertLessThanOrEqual(m.domain.lowerBound, 6.9); XCTAssertGreaterThanOrEqual(m.domain.upperBound, 9.0)
    }
    func testQuartilesNeedThreeValues() {
        XCTAssertNil(RangeBarModel(values: [1, 2], current: nil, target: nil).quartiles)
        let q = RangeBarModel(values: [1, 2, 3, 4, 5], current: nil, target: nil).quartiles!
        XCTAssertEqual(q.0, 2, accuracy: 1e-9); XCTAssertEqual(q.1, 4, accuracy: 1e-9)
    }
    func testDegenerateDomainIsWidened() {
        let m = RangeBarModel(values: [5, 5, 5], current: 5, target: nil)
        XCTAssertGreaterThan(m.domain.upperBound - m.domain.lowerBound, 0)
    }

    /// Verdict physics decodes with nullable fields (a long throw has no from_hole_m).
    func testVerdictDecodesNullablePhysics() throws {
        let json = """
        {"headline": "Released at 38° and 8.4 m/s.", "method": "Drag-free point-mass flight.", "personal": [],
         "items": [{"kind": "fix", "metric_key": "bag_release_speed_m_s", "text": "Release speed: 8.1 m/s reaches the hole."},
                   {"kind": "note", "metric_key": null, "text": "Bag tracking quality is poor."}],
         "physics": {"angle_deg": 37.5, "delta_speed_m_s": 0.37, "distance_m": 6.26, "distance_source": "measured",
                     "from_hole_m": null, "height_m": 0.99, "hole_x_m": 7.23, "landing": "long", "landing_x_m": 8.1,
                     "required_speed_m_s": 8.05, "sensitivity_m_per_m_s": 1.69, "speed_m_s": 8.42, "zone": "red"}}
        """
        let verdict = try JSONDecoder().decode(Verdict.self, from: Data(json.utf8))
        XCTAssertEqual(verdict.items.map(\.kind), ["fix", "note"])
        XCTAssertNil(verdict.items[1].metric_key)
        XCTAssertEqual(verdict.physics?.distance_source, "measured")
        XCTAssertNil(verdict.physics?.from_hole_m)
        XCTAssertEqual(try XCTUnwrap(verdict.physics?.required_speed_m_s), 8.05, accuracy: 1e-9)
        let noPhysics = try JSONDecoder().decode(Verdict.self, from: Data(#"{"headline": "h", "items": [], "physics": null}"#.utf8))
        XCTAssertNil(noPhysics.physics)
    }
}
