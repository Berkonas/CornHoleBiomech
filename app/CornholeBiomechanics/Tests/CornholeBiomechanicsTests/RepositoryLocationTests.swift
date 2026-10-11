import XCTest
@testable import CornholeBiomechanics

final class RepositoryLocationTests: XCTestCase {
    func testMovedBundleWinsOverOldBuildSource() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let old = root.appendingPathComponent("old")
        let moved = root.appendingPathComponent("moved checkout")
        for repo in [old, moved] {
            try FileManager.default.createDirectory(at: repo.appendingPathComponent("python/cornhole_biomech"), withIntermediateDirectories: true)
            try Data().write(to: repo.appendingPathComponent("pyproject.toml"))
        }
        let source = old.appendingPathComponent("app/CornholeBiomechanics/Sources/CornholeBiomechanics/RepositoryLocation.swift")
        let found = RepositoryLocation.resolve(environment: [:], bundleURL: moved.appendingPathComponent("dist/Lab.app"), workingDirectory: old.path, sourceFile: source.path)
        XCTAssertEqual(found?.resolvingSymlinksInPath(), moved.resolvingSymlinksInPath())
        let explicit = RepositoryLocation.resolve(environment: ["CORNHOLE_BIOMECH_ROOT": old.path], bundleURL: moved.appendingPathComponent("dist/Lab.app"), workingDirectory: moved.path, sourceFile: source.path)
        XCTAssertEqual(explicit?.resolvingSymlinksInPath(), old.resolvingSymlinksInPath())
    }

    @MainActor
    func testRepositoryRuntimeCanProbe() async throws {
        guard let repo = RepositoryLocation.resolve(), FileManager.default.isExecutableFile(atPath: repo.appendingPathComponent(".venv/bin/python").path) else {
            throw XCTSkip("Run setup.sh to install a repository runtime")
        }
        let result = try await AnalysisService().probe()
        XCTAssertFalse(result.isEmpty)
    }
}
