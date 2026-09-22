import XCTest
@testable import CornholeBiomechanics

final class BoardHomographyTests: XCTestCase {
    /// A foreshortened board as a camera behind and above it might see it.
    let corners = [CGPoint(x: 700, y: 900), CGPoint(x: 1220, y: 910),   // front-left, front-right
                   CGPoint(x: 1080, y: 520), CGPoint(x: 820, y: 515)]   // back-right, back-left

    func testCornersMapExactlyToBoardInches() throws {
        let h = try XCTUnwrap(BoardHomography(imageCorners: corners))
        let expected = [(0.0, 0.0), (24.0, 0.0), (24.0, 48.0), (0.0, 48.0)]
        for (c, e) in zip(corners, expected) {
            let p = try XCTUnwrap(h.boardInches(fromImage: c))
            XCTAssertEqual(p.x, e.0, accuracy: 1e-6); XCTAssertEqual(p.y, e.1, accuracy: 1e-6)
        }
    }

    func testImageToBoardAndBackRoundTrips() throws {
        let h = try XCTUnwrap(BoardHomography(imageCorners: corners))
        let hole = try XCTUnwrap(h.image(fromBoardInches: CGPoint(x: 12, y: 39)))
        let back = try XCTUnwrap(h.boardInches(fromImage: hole))
        XCTAssertEqual(back.x, 12, accuracy: 1e-6); XCTAssertEqual(back.y, 39, accuracy: 1e-6)
    }

    func testPerspectiveIsNotAffine() throws {
        // The board's midpoint is not the image midpoint of the corners under perspective.
        let h = try XCTUnwrap(BoardHomography(imageCorners: corners))
        let middle = try XCTUnwrap(h.image(fromBoardInches: CGPoint(x: 12, y: 24)))
        let naive = CGPoint(x: corners.map(\.x).reduce(0, +) / 4, y: corners.map(\.y).reduce(0, +) / 4)
        XCTAssertGreaterThan(hypot(middle.x - naive.x, middle.y - naive.y), 5)
    }

    func testDegenerateOrNonConvexCornersAreRejected() {
        XCTAssertNil(BoardHomography(imageCorners: [CGPoint(x: 0, y: 0), CGPoint(x: 10, y: 0), CGPoint(x: 20, y: 0), CGPoint(x: 30, y: 0)]))
        XCTAssertNil(BoardHomography(imageCorners: [corners[0], corners[2], corners[1], corners[3]]))   // crossed order
        XCTAssertNil(BoardHomography(imageCorners: Array(corners.prefix(3))))
    }

    func testConditioningFlagsEdgeOnViews() throws {
        // Top-down view: 10 px per inch everywhere → 0.1 in/px.
        let topDown = try XCTUnwrap(BoardHomography(imageCorners: [CGPoint(x: 0, y: 480), CGPoint(x: 240, y: 480), CGPoint(x: 240, y: 0), CGPoint(x: 0, y: 0)]))
        XCTAssertEqual(try XCTUnwrap(topDown.inchesPerPixel(atBoardInches: CGPoint(x: 12, y: 39))), 0.1, accuracy: 1e-6)
        // Pilot-style side view: 24 in of width squeezed into ~15 px.
        let edgeOn = try XCTUnwrap(BoardHomography(imageCorners: [CGPoint(x: 1560, y: 690), CGPoint(x: 1548, y: 676), CGPoint(x: 1835, y: 638), CGPoint(x: 1845, y: 652)]))
        XCTAssertGreaterThan(try XCTUnwrap(edgeOn.inchesPerPixel(atBoardInches: CGPoint(x: 12, y: 39))), 0.5)
    }

    func testPointsOffTheDeckAreFlagged() throws {
        let h = try XCTUnwrap(BoardHomography(imageCorners: corners))
        XCTAssertTrue(h.isOnBoard(CGPoint(x: 12, y: 39)))
        XCTAssertFalse(h.isOnBoard(CGPoint(x: -2, y: 10)))
        XCTAssertFalse(h.isOnBoard(CGPoint(x: 12, y: 49)))
    }

    func testSessionBoardFieldsDecodeFromOlderLibraries() throws {
        let json = #"{"id":"6F9619FF-8B86-D011-B42D-00CF4FC964FF","athleteID":"6F9619FF-8B86-D011-B42D-00CF4FC964FE","name":"S","date":0,"cameraSetup":"tripod","cameraView":"side","throwingSide":"right","targetDirection":"left_to_right","notes":"","referenceTrialIDs":[]}"#
        let session = try JSONDecoder().decode(RecordingSession.self, from: Data(json.utf8))
        XCTAssertNil(session.boardVideoRelativePath)
        XCTAssertNil(session.boardCorners)
    }

    @MainActor
    func testStoreCopiesBoardVideoPersistsCornersAndRejectsBadOnes() throws {
        let base = FileManager.default.temporaryDirectory.appendingPathComponent("board-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: base) }
        let paths = LibraryPaths(applicationSupportURL: base.appendingPathComponent("S"), defaultLibraryURL: base.appendingPathComponent("D"), libraryRootWasOverridden: false)
        let store = ProjectStore(paths: paths, trashHandler: { _ in })
        try store.addAthlete(NewAthleteDraft(participantCode: "B1", dominantHand: .right))
        let athleteID = try XCTUnwrap(store.selectedAthleteID)
        let session = RecordingSession(athleteID: athleteID, name: "Day 1", cameraSetup: "tripod")
        try store.addSession(session)
        let clip = base.appendingPathComponent("board.mov")
        try FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
        try Data("video".utf8).write(to: clip)
        try store.setBoardVideo(clip, for: session.id)
        let saved = try XCTUnwrap(store.project?.sessions?.first?.boardVideoRelativePath)
        XCTAssertEqual(try Data(contentsOf: XCTUnwrap(store.url(for: saved))), Data("video".utf8))
        XCTAssertThrowsError(try store.setBoardCorners([ImagePoint(x: 0, y: 0), ImagePoint(x: 1, y: 0), ImagePoint(x: 2, y: 0), ImagePoint(x: 3, y: 0)], for: session.id))
        let good = corners.map { ImagePoint(x: $0.x, y: $0.y) }
        try store.setBoardCorners(good, for: session.id)
        let reopened = ProjectStore(paths: paths, trashHandler: { _ in })
        XCTAssertEqual(reopened.project?.sessions?.first?.boardCorners, good)
        try store.setBoardVideo(clip, for: session.id)       // new framing clears old corners
        XCTAssertNil(store.project?.sessions?.first?.boardCorners)
    }
}
