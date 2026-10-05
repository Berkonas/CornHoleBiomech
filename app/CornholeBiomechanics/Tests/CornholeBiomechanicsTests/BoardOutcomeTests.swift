import XCTest
@testable import CornholeBiomechanics

/// results.json → board_phase, and the board drawn from above.
final class BoardOutcomeTests: XCTestCase {
    private func phase(right: Double?) throws -> BoardPhase {
        let rightJSON = right.map { "\($0)" } ?? "null"
        let json = """
        {"board_phase":{"status":"measured",
          "touchdown":{"frame":270,"u_in":14,"v_in":30,"from_hole_in":-9,"on_deck":true,"right_of_centre_in":\(rightJSON)},
          "end":{"kind":"rest","frame":300,"u_in":18,"v_in":37,"from_hole_in":-2,"right_of_centre_in":\(rightJSON)},
          "slide":{"distance_in":7,"duration_s":0.2},
          "path":[{"frame":270,"v_in":30,"right_of_centre_in":\(rightJSON)},{"frame":300,"v_in":37}],
          "lateral":{"state":"approximate","precision_in":3.2}}}
        """
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("results-\(UUID()).json")
        try Data(json.utf8).write(to: url)
        return try XCTUnwrap(BoardPhase.load(results: url))
    }

    func testLeftRightIsReadAndNamedFromTheThrowersSide() throws {
        let right = try phase(right: 6)
        XCTAssertTrue(right.measuresLeftRight)
        XCTAssertEqual(right.lateralPrecision, 3.2, accuracy: 1e-9)
        XCTAssertEqual(right.sentence, "Landed 9 in short of the hole, slid 7 in, stopped at the hole and 6 in to the thrower's right.")
        XCTAssertEqual(BoardPhase.sideText(-5), "5 in to the thrower's left")
        XCTAssertNil(BoardPhase.sideText(2), "within the side camera's precision it is not called left or right")
    }

    func testOlderAnalysesWithoutLeftRightStayOnTheCentreline() throws {
        let old = try phase(right: nil)
        XCTAssertFalse(old.measuresLeftRight)
        XCTAssertEqual(old.sentence, "Landed 9 in short of the hole, slid 7 in, stopped at the hole.")
    }

    func testDeckLayoutIsToScaleWithTheThrowersRightDown() {
        let layout = DeckLayout(size: CGSize(width: 620, height: 240))
        XCTAssertEqual(layout.deck.width / layout.deck.height, 2, accuracy: 1e-9)
        let centre = layout.point(v: 39, right: 0), right = layout.point(v: 39, right: 6), left = layout.point(v: 39, right: -6)
        XCTAssertEqual(centre, layout.hole)
        XCTAssertGreaterThan(right.y, centre.y)
        XCTAssertLessThan(left.y, centre.y)
        XCTAssertEqual(right.y - centre.y, 6 * layout.ppi, accuracy: 1e-9)
        // Bags far off the board are drawn at the edge of the apron, not off the canvas.
        XCTAssertEqual(layout.point(v: 200, right: 0).x, layout.deck.maxX + DeckLayout.apron * layout.ppi, accuracy: 1e-9)
    }
}
