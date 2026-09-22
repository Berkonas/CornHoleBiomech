import XCTest
@testable import CornholeBiomechanics

final class WorkerIntegrationTests: XCTestCase {
    @MainActor
    func testNativeAnalysisAndResultsWorker() async throws {
        guard let path = ProcessInfo.processInfo.environment["CORNHOLE_INTEGRATION_LIBRARY"] else {
            throw XCTSkip("Set CORNHOLE_INTEGRATION_LIBRARY to a disposable real-video library")
        }
        let root = URL(fileURLWithPath: path)
        let paths = LibraryPaths(applicationSupportURL: root.appendingPathComponent("Support"), defaultLibraryURL: root, libraryRootWasOverridden: true)
        let store = ProjectStore(paths: paths, automaticallyRestore: false)
        try store.open(root)
        let trial = try XCTUnwrap(store.project?.trials.first)
        store.selectedTrialID = trial.id
        let worker = AnalysisService()
        _ = try await worker.probe()
        await worker.analyze(trial: trial, store: store)
        XCTAssertNil(worker.errorMessage, worker.errorMessage ?? "")
        XCTAssertEqual(worker.stage, "Complete")
        let analyzed = try XCTUnwrap(store.selectedTrial)
        let directory = try store.analysisOutput(for: analyzed).url
        XCTAssertTrue(FileManager.default.fileExists(atPath: directory.appendingPathComponent("analysis-worker.log").path))
        XCTAssertFalse(FileManager.default.fileExists(atPath: directory.appendingPathComponent("needs_reanalysis.json").path))
        let seed = directory.appendingPathComponent("bag_seed.json")
        if let saved = try? Data(contentsOf: seed) {
            defer { try? saved.write(to: seed) }
            try Data("{\"frame_index\":999999,\"bbox_xywh\":[10,10,20,20]}".utf8).write(to: seed)
            await worker.analyze(trial: analyzed, store: store)
            XCTAssertNotNil(worker.errorMessage)
            XCTAssertFalse(worker.isRunning)
            XCTAssertTrue(FileManager.default.fileExists(atPath: directory.appendingPathComponent("needs_reanalysis.json").path))
            try saved.write(to: seed)
            await worker.analyze(trial: analyzed, store: store)
            XCTAssertNil(worker.errorMessage)
            XCTAssertFalse(FileManager.default.fileExists(atPath: directory.appendingPathComponent("needs_reanalysis.json").path))
        }
        try await worker.refreshInsights(trial: analyzed, store: store)
        XCTAssertEqual(worker.stage, "Results ready")
        let data = TrialDataController()
        data.load(analysisURL: store.analysisURL(for: analyzed))
        XCTAssertNil(data.loadError)
        XCTAssertNotNil(data.results)
        XCTAssertNotNil(data.pose)
        if FileManager.default.fileExists(atPath: try store.analysisOutput(for: analyzed).url.appendingPathComponent("bag_seed.json").path) {
            XCTAssertNotNil(data.bagTrack)
            XCTAssertNotNil(data.results?.bag)
        }
    }
}
