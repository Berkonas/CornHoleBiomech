import XCTest
@testable import CornholeBiomechanics

final class BagSelectionTests: XCTestCase {
    func testBoxMapsZoomedPreviewToSourcePixelsInBothDragDirections() {
        let a = CGPoint(x: 210, y: 140), b = CGPoint(x: 252, y: 168)
        for (from, to) in [(a,b),(b,a)] {
            let result = BagSelectionGeometry.rectangle(from: from, to: to, scale: 0.7, width: 1920, height: 1080)!
            for (actual, expected) in zip(result, [300.0, 200.0, 60.0, 40.0]) { XCTAssertEqual(actual, expected, accuracy: 1e-9) }
        }
    }
    func testBoxClipsAtImageAndRejectsEmptySelections() {
        XCTAssertEqual(BagSelectionGeometry.rectangle(from: .init(x: -3, y: -8), to: .init(x: 120, y: 130), scale: 1, width: 100, height: 100), [0, 0, 100, 100])
        XCTAssertNil(BagSelectionGeometry.rectangle(from: .zero, to: .zero, scale: 1, width: 100, height: 100))
        XCTAssertNil(BagSelectionGeometry.rectangle(from: .zero, to: .init(x: 4,y: 4), scale: 0, width: 100, height: 100))
    }
}
