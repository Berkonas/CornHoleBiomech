import Foundation

/// Locate the checkout that owns this app, even when Finder opens a Desktop symlink.
/// Bundle ancestry takes priority over the build machine's source path so a moved
/// checkout uses its own engine, environment and data.
enum RepositoryLocation {
    static func resolve(
        environment: [String: String] = ProcessInfo.processInfo.environment,
        bundleURL: URL = Bundle.main.bundleURL,
        workingDirectory: String = FileManager.default.currentDirectoryPath,
        sourceFile: String = #filePath
    ) -> URL? {
        var candidates: [URL] = []
        if let explicit = environment["CORNHOLE_BIOMECH_ROOT"] {
            candidates.append(URL(fileURLWithPath: explicit, isDirectory: true))
        }
        var bundle = bundleURL.resolvingSymlinksInPath()
        for _ in 0..<8 {
            candidates.append(bundle)
            bundle.deleteLastPathComponent()
        }
        candidates.append(URL(fileURLWithPath: workingDirectory, isDirectory: true))
        var source = URL(fileURLWithPath: sourceFile)
        for _ in 0..<5 { source.deleteLastPathComponent() }
        candidates.append(source)
        return candidates.first {
            FileManager.default.fileExists(atPath: $0.appendingPathComponent("pyproject.toml").path)
                && FileManager.default.fileExists(atPath: $0.appendingPathComponent("python/cornhole_biomech").path)
        }?.standardizedFileURL
    }
}
