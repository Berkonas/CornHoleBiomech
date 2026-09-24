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
}
