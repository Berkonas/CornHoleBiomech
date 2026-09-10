import Foundation

struct LibraryPaths {
    var applicationSupportURL: URL
    var defaultLibraryURL: URL
    var libraryRootWasOverridden: Bool

    static var live: LibraryPaths {
        let manager = FileManager.default
        let environment = ProcessInfo.processInfo.environment
        let support = environment["CORNHOLE_APP_SUPPORT_ROOT"].map { URL(fileURLWithPath: $0, isDirectory: true) }
            ?? manager.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
                .appendingPathComponent(applicationName, isDirectory: true)
        let overriddenLibrary = environment["CORNHOLE_LIBRARY_ROOT"].map { URL(fileURLWithPath: $0, isDirectory: true) }
        let documents = manager.urls(for: .documentDirectory, in: .userDomainMask).first
            ?? manager.homeDirectoryForCurrentUser.appendingPathComponent("Documents", isDirectory: true)
        return LibraryPaths(
            applicationSupportURL: support,
            defaultLibraryURL: overriddenLibrary
                ?? documents.appendingPathComponent("Cornhole Biomechanics Lab Data", isDirectory: true),
            libraryRootWasOverridden: overriddenLibrary != nil
        )
    }
}

struct LibraryLocationIndex: Codable {
    var schemaVersion = 1
    var projectID: UUID
    var dataRootPath: String
    var bookmarkData: Data?
    var savedAt = Date()
    var selectedAthleteID: UUID?
    var selectedTrialID: UUID?
    var selectedSessionID: UUID?
    var selectedReferenceSetID: UUID?
}

struct MigrationLog: Codable {
    var schemaVersion = 1
    var entries: [MigrationEntry] = []
}

struct MigrationEntry: Codable, Identifiable {
    var id = UUID()
    var sourceProjectID: UUID
    var sourcePath: String
    var sourceSchemaVersion: Int
    var sourceUpdatedAt: Date
    var lastCheckedAt = Date()
    var importedAthleteIDs: [UUID]
    var importedSessionIDs: [UUID]
    var importedTrialIDs: [UUID]
    var warnings: [String]
}

enum LibraryFileState: Equatable {
    case available(URL)
    case missing(URL)
    case unassigned

    var url: URL? {
        switch self {
        case .available(let url), .missing(let url): url
        case .unassigned: nil
        }
    }

    var isAvailable: Bool {
        if case .available = self { return true }
        return false
    }
}

struct MigrationSummary: Equatable {
    var athletesImported: Int
    var sessionsImported: Int
    var trialsImported: Int
    var warnings: [String]
    var wasAlreadyImported: Bool
}
