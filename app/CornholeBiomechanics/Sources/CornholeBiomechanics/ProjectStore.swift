import AppKit
import Foundation
import UniformTypeIdentifiers

enum ProjectStoreError: LocalizedError {
    case noOpenProject
    case invalidProjectFolder
    case athleteRequired
    case fileAlreadyExists(String)
    case unsupportedSchema(Int)
    case invalidLibraryPath(String)
    case recordNotFound(String)
    case invalidBoardCorners

    var errorDescription: String? {
        switch self {
        case .noOpenProject: "Create or open a project first."
        case .invalidProjectFolder: "That folder does not contain a readable project.json file."
        case .athleteRequired: "Add and select an athlete before importing a trial."
        case .fileAlreadyExists(let name): "A project file named \(name) already exists; the source was not overwritten."
        case .unsupportedSchema(let version): "This library uses schema \(version), which is newer than this version of the app supports."
        case .invalidLibraryPath(let path): "The saved library path is invalid or outside the selected data root: \(path)"
        case .recordNotFound(let kind): "The selected \(kind) no longer exists in the library index."
        case .invalidBoardCorners: "Click the four deck corners in order (front-left, front-right, back-right, back-left) so they outline the board."
        }
    }
}

private func moveToTrash(_ url: URL) throws {
    try FileManager.default.trashItem(at: url, resultingItemURL: nil)
}

@MainActor
final class ProjectStore: ObservableObject {
    @Published private(set) var project: StudyProject?
    @Published private(set) var projectURL: URL?
    @Published var selectedSection: AppSection? = .athletes
    @Published var selectedAthleteID: UUID?
    @Published var selectedTrialID: UUID?
    @Published var selectedSessionID: UUID?
    @Published var selectedReferenceSetID: UUID?
    @Published var notice: String?
    @Published var errorMessage: String?
    @Published private(set) var missingLibraryURL: URL?

    private let fileManager: FileManager
    private let paths: LibraryPaths
    private let trashHandler: (URL) throws -> Void

    init(
        paths: LibraryPaths = .live,
        fileManager: FileManager = .default,
        automaticallyRestore: Bool = true,
        trashHandler: @escaping (URL) throws -> Void = moveToTrash
    ) {
        self.paths = paths
        self.fileManager = fileManager
        self.trashHandler = trashHandler
        if automaticallyRestore {
            do { try restoreOrCreateLibrary() }
            catch { errorMessage = error.localizedDescription }
        }
    }

    var selectedAthlete: Athlete? {
        project?.athletes.first { $0.id == selectedAthleteID }
    }

    var selectedTrial: Trial? {
        project?.trials.first { $0.id == selectedTrialID }
    }

    var selectedReferenceSet: ReferenceSet? {
        project?.referenceSets.first { $0.id == selectedReferenceSetID }
    }

    var analyzedTrials: [Trial] {
        project?.trials.filter { analysisState(for: $0).isAvailable } ?? []
    }

    func createProject() {
        let panel = NSSavePanel()
        panel.title = "Choose a Visible Athlete Library Folder"
        panel.nameFieldStringValue = "Cornhole Biomechanics Lab Data"
        panel.canCreateDirectories = true
        panel.isExtensionHidden = false
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            guard !fileManager.fileExists(atPath: url.path) else {
                throw ProjectStoreError.fileAlreadyExists(url.lastPathComponent)
            }
            try createManagedLibrary(at: url)
            notice = "Created the athlete library at \(url.path)."
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func openProject() {
        let panel = NSOpenPanel()
        panel.title = "Choose an Athlete Library or Legacy .cornholeproject"
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            let source = try decodeProject(at: url)
            if source.schemaVersion < 2 {
                let summary = try importLegacyProject(at: url)
                notice = migrationNotice(summary)
            } else {
                try open(url)
            }
        } catch { errorMessage = error.localizedDescription }
    }

    func importLegacyProject() {
        let panel = NSOpenPanel()
        panel.title = "Import a Legacy Cornhole Project"
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            let summary = try importLegacyProject(at: url)
            notice = migrationNotice(summary)
        } catch { errorMessage = error.localizedDescription }
    }

    func open(_ url: URL) throws {
        var decoded = try decodeProject(at: url)
        guard decoded.schemaVersion >= 2 else {
            throw ProjectStoreError.invalidProjectFolder
        }
        let normalizedLegacyReferences = normalizeLegacyReferences(in: &decoded)
        if decoded.schemaVersion < currentProjectSchemaVersion {
            let backup = url.appendingPathComponent("project.schema\(decoded.schemaVersion).backup.json")
            if !fileManager.fileExists(atPath: backup.path) {
                try fileManager.copyItem(at: url.appendingPathComponent("project.json"), to: backup)
            }
        }
        try beginAccessing(url)
        projectURL = url
        project = decoded
        missingLibraryURL = nil
        selectedAthleteID = decoded.athletes.first?.id
        selectedTrialID = decoded.trials.first?.id
        selectedReferenceSetID = decoded.referenceSets.first?.id
        selectedSection = .athletes
        try ensureDirectoryStructure(at: url)
        if normalizedLegacyReferences { try save() } else { try persistLibraryLocation() }
        notice = "Opened \(decoded.name) athlete library."
    }

    func save() throws {
        guard var value = project, let root = projectURL else { throw ProjectStoreError.noOpenProject }
        value.schemaVersion = currentProjectSchemaVersion
        value.appVersion = applicationVersion
        value.updatedAt = Date()
        let data = try JSONEncoder.projectEncoder.encode(value)
        try writeAthleteProfiles()
        try persistLibraryLocation()
        // Commit the authoritative index last so a failed auxiliary write does
        // not leave a deletion committed on disk while files are rolled back.
        try data.write(to: root.appendingPathComponent("project.json"), options: .atomic)
        project = value
    }

    func addAthlete(_ draft: NewAthleteDraft) throws {
        guard project != nil else { throw ProjectStoreError.noOpenProject }
        let athlete = Athlete(
            participantCode: draft.participantCode.trimmingCharacters(in: .whitespacesAndNewlines),
            dominantHand: draft.dominantHand,
            heightCentimeters: Double(draft.height),
            armSpanCentimeters: Double(draft.armSpan),
            upperArmCentimeters: Double(draft.upperArm),
            forearmCentimeters: Double(draft.forearm),
            notes: draft.notes
        )
        project?.athletes.append(athlete)
        selectedAthleteID = athlete.id
        try save()
    }

    func updateAthlete(_ changed: Athlete) throws {
        guard var value = project, let root = projectURL,
              let index = value.athletes.firstIndex(where: { $0.id == changed.id }) else {
            throw ProjectStoreError.recordNotFound("athlete")
        }
        let original = value.athletes[index]
        let oldRelative = athleteRelativeDirectory(for: original)
        let newRelative = athleteRelativeDirectory(for: changed)
        let oldURL = root.appendingPathComponent(oldRelative, isDirectory: true)
        let newURL = root.appendingPathComponent(newRelative, isDirectory: true)
        var moved = false
        if oldRelative != newRelative, fileManager.fileExists(atPath: oldURL.path) {
            guard !fileManager.fileExists(atPath: newURL.path) else {
                throw ProjectStoreError.fileAlreadyExists(newURL.lastPathComponent)
            }
            try fileManager.createDirectory(at: newURL.deletingLastPathComponent(), withIntermediateDirectories: true)
            try fileManager.moveItem(at: oldURL, to: newURL)
            moved = true
            for trialIndex in value.trials.indices where value.trials[trialIndex].athleteID == changed.id {
                value.trials[trialIndex].sourceVideoRelativePath = replacingPrefix(
                    value.trials[trialIndex].sourceVideoRelativePath, old: oldRelative, new: newRelative
                )
                if let path = value.trials[trialIndex].analysisRelativePath {
                    value.trials[trialIndex].analysisRelativePath = replacingPrefix(path, old: oldRelative, new: newRelative)
                }
                if let path = value.trials[trialIndex].preparedVideoRelativePath {
                    value.trials[trialIndex].preparedVideoRelativePath = replacingPrefix(path, old: oldRelative, new: newRelative)
                }
                if let path = value.trials[trialIndex].preparationDirectoryRelativePath {
                    value.trials[trialIndex].preparationDirectoryRelativePath = replacingPrefix(path, old: oldRelative, new: newRelative)
                }
            }
        }
        value.athletes[index] = changed
        let previous = project
        project = value
        do { try save() }
        catch {
            project = previous
            if moved { try? fileManager.moveItem(at: newURL, to: oldURL) }
            throw error
        }
    }

    func updateSession(_ changed: RecordingSession) throws {
        guard var value = project, let index = value.sessions?.firstIndex(where: { $0.id == changed.id }) else {
            throw ProjectStoreError.recordNotFound("session")
        }
        value.sessions?[index] = changed
        project = value
        try save()
    }

    func updateTrialMetadata(_ changed: Trial) throws {
        guard let current = project?.trials.first(where: { $0.id == changed.id }) else { throw ProjectStoreError.recordNotFound("throw") }
        var updated = changed
        if current.cameraView != changed.cameraView || current.throwingSide != changed.throwingSide || current.targetDirection != changed.targetDirection {
            if let directory = analysisURL(for: current) {
                let marker = ["reason": "Camera view, throwing side, or target direction changed. Reanalyze before interpretation."]
                try JSONEncoder().encode(marker).write(to: directory.appendingPathComponent("needs_reanalysis.json"), options: .atomic)
                updated.analysisStatus = "Metadata changed — reanalyze"
            }
        }
        try updateTrial(updated)
    }

    func setReference(_ isReference: Bool, for trial: Trial) throws {
        guard var value = project, value.trials.contains(where: { $0.id == trial.id }) else {
            throw ProjectStoreError.recordNotFound("throw")
        }
        if isReference {
            var setIndex = value.referenceSets.firstIndex { $0.name == "Coach-selected references" && $0.scope == .global }
            if setIndex == nil {
                value.referenceSets.append(ReferenceSet(name: "Coach-selected references"))
                setIndex = value.referenceSets.indices.last
            }
            if let setIndex, !value.referenceSets[setIndex].trialIDs.contains(trial.id) {
                value.referenceSets[setIndex].trialIDs.append(trial.id)
            }
        } else {
            for index in value.referenceSets.indices {
                value.referenceSets[index].trialIDs.removeAll { $0 == trial.id }
            }
            if value.sessions != nil {
                for index in value.sessions!.indices {
                    value.sessions![index].referenceTrialIDs.removeAll { $0 == trial.id }
                }
            }
        }
        synchronizeReferenceFlags(in: &value)
        project = value
        try save()
    }

    @discardableResult
    func addReferenceSet(
        name: String,
        scope: ReferenceScope,
        athleteID: UUID?,
        provenance: String = "coach_selected",
        notes: String = ""
    ) throws -> ReferenceSet {
        guard var value = project else { throw ProjectStoreError.noOpenProject }
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        let set = ReferenceSet(
            name: trimmed.isEmpty ? "Reference Set" : trimmed,
            scope: scope,
            athleteID: scope == .athlete ? athleteID : nil,
            provenance: provenance,
            notes: notes
        )
        value.referenceSets.append(set)
        project = value
        selectedReferenceSetID = set.id
        try save()
        return set
    }

    func updateReferenceSet(_ changed: ReferenceSet) throws {
        guard var value = project, let index = value.referenceSets.firstIndex(where: { $0.id == changed.id }) else {
            throw ProjectStoreError.recordNotFound("reference set")
        }
        value.referenceSets[index] = changed
        synchronizeReferenceFlags(in: &value)
        project = value
        try save()
    }

    func assign(_ trial: Trial, to referenceSet: ReferenceSet) throws {
        guard var value = project, let index = value.referenceSets.firstIndex(where: { $0.id == referenceSet.id }) else {
            throw ProjectStoreError.recordNotFound("reference set")
        }
        if value.referenceSets[index].scope == .athlete,
           value.referenceSets[index].athleteID != trial.athleteID {
            throw ProjectStoreError.invalidLibraryPath("That reference set belongs to a different athlete.")
        }
        if !value.referenceSets[index].trialIDs.contains(trial.id) {
            value.referenceSets[index].trialIDs.append(trial.id)
        }
        synchronizeReferenceFlags(in: &value)
        project = value
        try save()
    }

    func remove(_ trial: Trial, from referenceSet: ReferenceSet) throws {
        guard var value = project, let index = value.referenceSets.firstIndex(where: { $0.id == referenceSet.id }) else {
            throw ProjectStoreError.recordNotFound("reference set")
        }
        value.referenceSets[index].trialIDs.removeAll { $0 == trial.id }
        synchronizeReferenceFlags(in: &value)
        project = value
        try save()
    }

    func deleteReferenceSet(_ referenceSet: ReferenceSet) throws {
        guard var value = project else { throw ProjectStoreError.noOpenProject }
        value.referenceSets.removeAll { $0.id == referenceSet.id }
        synchronizeReferenceFlags(in: &value)
        project = value
        try save()
        if selectedReferenceSetID == referenceSet.id { selectedReferenceSetID = project?.referenceSets.first?.id }
        notice = "Deleted the reference set. Source throws and videos were preserved."
    }

    func deleteSession(_ session: RecordingSession) throws {
        guard var value = project else { throw ProjectStoreError.noOpenProject }
        value.sessions?.removeAll { $0.id == session.id }
        for index in value.trials.indices where value.trials[index].sessionID == session.id {
            value.trials[index].sessionID = nil
        }
        project = value
        try save()
        if selectedSessionID == session.id { selectedSessionID = nil }
        notice = "Deleted the session record. Its throws and videos were preserved."
    }

    func deleteAnalysis(for trial: Trial) throws {
        var resources: [URL] = []
        if let path = trial.analysisRelativePath, let url = containedURL(for: path) { resources.append(url) }
        resources += comparisonURLs(for: trial.id)
        try performRecoverableMutation(fileURLs: resources) { value in
            guard let index = value.trials.firstIndex(where: { $0.id == trial.id }) else { return }
            value.trials[index].analysisRelativePath = nil
            value.trials[index].analysisStatus = "Not analyzed"
        }
        notice = "Deleted the derived analysis. The source video, throw record, and reference assignments remain."
    }

    func deleteTrial(_ trial: Trial) throws {
        var resources = comparisonURLs(for: trial.id)
        if let path = trial.preparationDirectoryRelativePath, let url = containedURL(for: path) { resources.append(url) }
        if let video = containedURL(for: trial.sourceVideoRelativePath) { resources.append(video) }
        if let path = trial.analysisRelativePath, let analysis = containedURL(for: path) { resources.append(analysis) }
        try performRecoverableMutation(fileURLs: resources) { value in
            value.trials.removeAll { $0.id == trial.id }
            for referenceIndex in value.referenceSets.indices {
                value.referenceSets[referenceIndex].trialIDs.removeAll { $0 == trial.id }
            }
            synchronizeReferenceFlags(in: &value)
            if value.sessions != nil {
                for sessionIndex in value.sessions!.indices {
                    value.sessions![sessionIndex].referenceTrialIDs.removeAll { $0 == trial.id }
                }
            }
        }
        if selectedTrialID == trial.id { selectedTrialID = project?.trials.first?.id }
        notice = "Deleted the throw record. Its managed video and analysis were moved to Trash when available."
    }

    func deleteAthlete(_ athlete: Athlete) throws {
        guard let value = project else { throw ProjectStoreError.noOpenProject }
        let trials = value.trials.filter { $0.athleteID == athlete.id }
        var resources: [URL] = []
        if let root = projectURL {
            resources.append(root.appendingPathComponent(athleteRelativeDirectory(for: athlete), isDirectory: true))
        }
        for trial in trials {
            if let path = trial.preparationDirectoryRelativePath, let url = containedURL(for: path) { resources.append(url) }
            if let video = containedURL(for: trial.sourceVideoRelativePath) { resources.append(video) }
            if let path = trial.analysisRelativePath, let analysis = containedURL(for: path) { resources.append(analysis) }
            resources += comparisonURLs(for: trial.id)
        }
        let trialIDs = Set(trials.map(\.id))
        try performRecoverableMutation(fileURLs: resources) { changed in
            changed.athletes.removeAll { $0.id == athlete.id }
            changed.trials.removeAll { $0.athleteID == athlete.id }
            changed.sessions?.removeAll { $0.athleteID == athlete.id }
            changed.referenceSets.removeAll { $0.scope == .athlete && $0.athleteID == athlete.id }
            for referenceIndex in changed.referenceSets.indices {
                changed.referenceSets[referenceIndex].trialIDs.removeAll { trialIDs.contains($0) }
            }
            synchronizeReferenceFlags(in: &changed)
            if changed.sessions != nil {
                for index in changed.sessions!.indices {
                    changed.sessions![index].referenceTrialIDs.removeAll { trialIDs.contains($0) }
                }
            }
        }
        if selectedAthleteID == athlete.id { selectedAthleteID = project?.athletes.first?.id }
        if let selectedTrialID, trialIDs.contains(selectedTrialID) { self.selectedTrialID = project?.trials.first?.id }
        notice = "Deleted \(athlete.displayName). Managed videos and analyses were moved to Trash when available."
    }

    func relinkVideo(trialID: UUID, to sourceURL: URL) throws {
        if let current = project?.trials.first(where: { $0.id == trialID }),
           fileManager.fileExists(atPath: sourceURL.path),
           current.analysisRelativePath != nil || current.preparedVideoRelativePath != nil {
            // Replacement identity may differ. Never attach old coordinates to it.
            try usePreparedVideo(nil, for: current)
        }
        guard var value = project, let root = projectURL,
              let index = value.trials.firstIndex(where: { $0.id == trialID }) else {
            throw ProjectStoreError.recordNotFound("throw")
        }
        guard fileManager.fileExists(atPath: sourceURL.path) else {
            throw ProjectStoreError.invalidLibraryPath(sourceURL.path)
        }
        let trial = value.trials[index]
        let relative: String
        var copiedURL: URL?
        if let contained = relativePathIfContained(sourceURL, by: root) {
            relative = contained
        } else {
            relative = managedVideoRelativePath(
                athleteID: trial.athleteID, trialID: trial.id, filename: safeFilename(sourceURL.lastPathComponent)
            )
            let destination = root.appendingPathComponent(relative)
            guard !fileManager.fileExists(atPath: destination.path) else {
                throw ProjectStoreError.fileAlreadyExists(destination.lastPathComponent)
            }
            try fileManager.createDirectory(at: destination.deletingLastPathComponent(), withIntermediateDirectories: true)
            try fileManager.copyItem(at: sourceURL, to: destination)
            copiedURL = destination
        }
        value.trials[index].sourceVideoRelativePath = relative
        value.trials[index].originalFilename = sourceURL.lastPathComponent
        let previous = project
        project = value
        do { try save() }
        catch {
            project = previous
            if let copiedURL { try? fileManager.removeItem(at: copiedURL) }
            throw error
        }
        notice = "Relinked \(value.trials[index].displayName)."
    }

    func locateAndRelinkVideo(for trial: Trial) {
        let panel = NSOpenPanel()
        panel.title = "Locate the Missing Source Video"
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        panel.allowedContentTypes = [.movie, .video, .mpeg4Movie, .quickTimeMovie]
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do { try relinkVideo(trialID: trial.id, to: url) }
        catch { errorMessage = error.localizedDescription }
    }

    func importVideo(_ draft: ImportDraft) throws -> Trial {
        guard var value = project, let root = projectURL else { throw ProjectStoreError.noOpenProject }
        guard let athleteID = draft.athleteID else { throw ProjectStoreError.athleteRequired }
        guard value.athletes.contains(where: { $0.id == athleteID }) else { throw ProjectStoreError.recordNotFound("athlete") }
        if let sessionID = draft.sessionID,
           value.sessions?.contains(where: { $0.id == sessionID && $0.athleteID == athleteID }) != true {
            throw ProjectStoreError.recordNotFound("session for this athlete")
        }
        let trialID = UUID()
        let safeName = safeFilename(draft.videoURL.lastPathComponent)
        let relative = managedVideoRelativePath(athleteID: athleteID, trialID: trialID, filename: safeName)
        let destination = root.appendingPathComponent(relative)
        guard !fileManager.fileExists(atPath: destination.path) else {
            throw ProjectStoreError.fileAlreadyExists(destination.lastPathComponent)
        }
        try fileManager.createDirectory(at: destination.deletingLastPathComponent(), withIntermediateDirectories: true)
        try fileManager.copyItem(at: draft.videoURL, to: destination)
        let trial = Trial(
            id: trialID,
            athleteID: athleteID,
            sourceVideoRelativePath: relative,
            originalFilename: draft.videoURL.lastPathComponent,
            sourceURL: draft.sourceURL.nilIfBlank,
            sourceAttribution: draft.sourceAttribution.nilIfBlank,
            cameraView: draft.cameraView,
            throwingSide: draft.throwingSide,
            targetDirection: draft.targetDirection,
            isReference: draft.isReference,
            sessionID: draft.sessionID
        )
        value.trials.append(trial)
        if draft.isReference {
            var referenceIndex = value.referenceSets.firstIndex {
                $0.name == "Coach-selected references" && $0.scope == .global
            }
            if referenceIndex == nil {
                value.referenceSets.append(ReferenceSet(name: "Coach-selected references"))
                referenceIndex = value.referenceSets.indices.last
            }
            if let referenceIndex {
                value.referenceSets[referenceIndex].trialIDs.append(trial.id)
                selectedReferenceSetID = value.referenceSets[referenceIndex].id
            }
            synchronizeReferenceFlags(in: &value)
        }
        project = value
        selectedTrialID = trial.id
        selectedAthleteID = athleteID
        do { try save() }
        catch {
            project = valueWithTrialRemoved(value, trialID: trial.id)
            try? fileManager.removeItem(at: destination)
            throw error
        }
        return trial
    }

    func chooseAndImportVideo(athleteID: UUID?, completion: @escaping (URL) -> Void) {
        let panel = NSOpenPanel()
        panel.title = "Choose a Local Throw Video"
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        panel.allowedContentTypes = [.movie, .video, .mpeg4Movie, .quickTimeMovie]
        guard panel.runModal() == .OK, let url = panel.url else { return }
        completion(url)
    }

    func updateTrial(_ changed: Trial) throws {
        guard let index = project?.trials.firstIndex(where: { $0.id == changed.id }) else {
            throw ProjectStoreError.recordNotFound("throw")
        }
        let previous = project
        project?.trials[index] = changed
        do { try save() } catch { project = previous; throw error }
    }

    func saveOutcome(_ outcome: TrialOutcome, for trial: Trial) throws {
        var changed = trial
        changed.outcome = outcome
        try updateTrial(changed)
        if let analysis = analysisURL(for: changed) {
            try JSONEncoder.projectEncoder.encode(outcome)
                .write(to: analysis.appendingPathComponent("outcome.json"), options: .atomic)
        }
    }

    func exportAnalysis(for trial: Trial) {
        guard let analysis = analysisURL(for: trial) else {
            errorMessage = "Analyze this trial before exporting it."
            return
        }
        exportFolder(at: analysis, suggestedName: "Trial-\(trial.shortID)-export")
    }

    func exportFolder(at source: URL, suggestedName: String) {
        let panel = NSSavePanel()
        panel.title = "Export Research Artifacts"
        panel.nameFieldStringValue = suggestedName
        panel.canCreateDirectories = true
        guard panel.runModal() == .OK, let destination = panel.url else { return }
        do {
            guard !fileManager.fileExists(atPath: destination.path) else {
                throw ProjectStoreError.fileAlreadyExists(destination.lastPathComponent)
            }
            try fileManager.copyItem(at: source, to: destination)
            NSWorkspace.shared.activateFileViewerSelecting([destination])
            notice = "Exported \(source.lastPathComponent)."
        } catch { errorMessage = error.localizedDescription }
    }

    func reveal(_ url: URL) { NSWorkspace.shared.activateFileViewerSelecting([url]) }

    func addSession(_ session: RecordingSession) throws {
        if project?.sessions == nil { project?.sessions = [] }
        project?.sessions?.append(session)
        selectedSessionID = session.id; selectedAthleteID = session.athleteID
        try save()
    }

    /// Copy a board-camera clip into the athlete's library and attach it to a session.
    /// Replacing the clip clears the corners, which belong to the old framing.
    func setBoardVideo(_ source: URL, for sessionID: UUID) throws {
        guard let root = projectURL, var session = project?.sessions?.first(where: { $0.id == sessionID }) else {
            throw ProjectStoreError.recordNotFound("session")
        }
        let relative = "\(athleteRelativeDirectory(for: session.athleteID))/board-camera/\(String(sessionID.uuidString.prefix(8)))-\(UUID().uuidString.prefix(4))-\(safeFilename(source.lastPathComponent))"
        let destination = root.appendingPathComponent(relative)
        try fileManager.createDirectory(at: destination.deletingLastPathComponent(), withIntermediateDirectories: true)
        try fileManager.copyItem(at: source, to: destination)
        session.boardVideoRelativePath = relative
        session.boardCorners = nil
        try updateSession(session)
    }

    func setBoardCorners(_ corners: [ImagePoint]?, for sessionID: UUID) throws {
        guard var session = project?.sessions?.first(where: { $0.id == sessionID }) else {
            throw ProjectStoreError.recordNotFound("session")
        }
        if let corners, BoardHomography(imageCorners: corners.map(\.cgPoint)) == nil {
            throw ProjectStoreError.invalidBoardCorners
        }
        session.boardCorners = corners
        try updateSession(session)
    }

    func updateSettings(_ settings: AnalysisSettings) throws {
        project?.analysisSettings = settings
        try save()
    }

    func markAnalysisComplete(trialID: UUID, relativePath: String) throws {
        guard let index = project?.trials.firstIndex(where: { $0.id == trialID }) else { return }
        project?.trials[index].analysisRelativePath = relativePath
        project?.trials[index].analysisStatus = "Analyzed"
        try save()
    }

    func markAnalysisStatus(trialID: UUID, status: String) throws {
        guard let index = project?.trials.firstIndex(where: { $0.id == trialID }) else { return }
        project?.trials[index].analysisStatus = status
        try save()
    }

    func url(for relativePath: String) -> URL? {
        containedURL(for: relativePath)
    }

    func videoState(for trial: Trial) -> LibraryFileState {
        guard let url = containedURL(for: trial.preparedVideoRelativePath ?? trial.sourceVideoRelativePath) else { return .unassigned }
        return fileManager.fileExists(atPath: url.path) ? .available(url) : .missing(url)
    }

    func analysisState(for trial: Trial) -> LibraryFileState {
        guard let path = trial.analysisRelativePath else { return .unassigned }
        guard let url = containedURL(for: path) else { return .missing(projectURL?.appendingPathComponent(path) ?? URL(fileURLWithPath: path)) }
        var isDirectory: ObjCBool = false
        return fileManager.fileExists(atPath: url.path, isDirectory: &isDirectory) && isDirectory.boolValue
            ? .available(url) : .missing(url)
    }

    func videoURL(for trial: Trial) -> URL? {
        guard case .available(let url) = videoState(for: trial) else { return nil }
        return url
    }

    func originalVideoURL(for trial: Trial) -> URL? {
        guard let url = containedURL(for: trial.sourceVideoRelativePath), fileManager.fileExists(atPath: url.path) else { return nil }
        return url
    }

    func preparationOutput(for trial: Trial) throws -> URL {
        // Keep revisions alongside the managed recording, including legacy libraries.
        let directory = trial.preparationDirectoryRelativePath
            ?? (trial.sourceVideoRelativePath as NSString).deletingLastPathComponent + "/\(trial.id.uuidString)-video-revisions"
        guard let root = containedURL(for: directory) else { throw ProjectStoreError.invalidLibraryPath(directory) }
        return root.appendingPathComponent(UUID().uuidString).appendingPathComponent("prepared.mp4")
    }

    func usePreparedVideo(_ output: URL?, for trial: Trial) throws {
        guard let root = projectURL, let current = project?.trials.first(where: { $0.id == trial.id }) else {
            throw ProjectStoreError.recordNotFound("throw")
        }
        let output = output?.standardizedFileURL
        let relative = output.flatMap { relativePathIfContained($0, by: root) }
        if let output, (relative == nil || !fileManager.fileExists(atPath: output.path)) {
            throw ProjectStoreError.invalidLibraryPath(output.path)
        }
        let revision = try output ?? preparationOutput(for: current)
        let archive = revision.deletingLastPathComponent().appendingPathComponent("previous-analysis")
        let oldAnalysis = analysisURL(for: current)
        if let oldAnalysis {
            try fileManager.createDirectory(at: archive.deletingLastPathComponent(), withIntermediateDirectories: true)
            try fileManager.moveItem(at: oldAnalysis, to: archive)
        }
        do {
            try performRecoverableMutation(fileURLs: comparisonURLs(for: trial.id)) { value in
                guard let index = value.trials.firstIndex(where: { $0.id == trial.id }) else { return }
                value.trials[index].preparedVideoRelativePath = relative
                value.trials[index].preparationDirectoryRelativePath = relativePathIfContained(revision.deletingLastPathComponent().deletingLastPathComponent(), by: root)
                value.trials[index].analysisRelativePath = nil
                value.trials[index].analysisStatus = "Video changed — analyze again"
            }
        } catch {
            if let oldAnalysis { try? fileManager.moveItem(at: archive, to: oldAnalysis) }
            throw error
        }
        notice = "Video updated. The original and previous analysis are preserved in video revisions. Analyze again before reviewing measurements."
    }

    func analysisURL(for trial: Trial) -> URL? {
        guard case .available(let url) = analysisState(for: trial) else { return nil }
        return url
    }

    func analysisOutput(for trial: Trial) throws -> (relativePath: String, url: URL) {
        guard projectURL != nil else { throw ProjectStoreError.noOpenProject }
        let relative = trial.analysisRelativePath
            ?? managedAnalysisRelativePath(athleteID: trial.athleteID, trialID: trial.id)
        guard let url = containedURL(for: relative) else { throw ProjectStoreError.invalidLibraryPath(relative) }
        return (relative, url)
    }

    func athleteDirectory(for athlete: Athlete) -> URL? {
        projectURL?.appendingPathComponent(athleteRelativeDirectory(for: athlete), isDirectory: true)
    }

    func revealProject() {
        if let projectURL { NSWorkspace.shared.activateFileViewerSelecting([projectURL]) }
    }

    func revealAthlete(_ athlete: Athlete) {
        guard let url = athleteDirectory(for: athlete) else { return }
        try? fileManager.createDirectory(at: url, withIntermediateDirectories: true)
        reveal(url)
    }

    func revealVideo(for trial: Trial) {
        switch videoState(for: trial) {
        case .available(let url): reveal(url)
        case .missing: locateAndRelinkVideo(for: trial)
        case .unassigned: errorMessage = "This throw has no source-video association."
        }
    }

    // MARK: - Library lifecycle

    private var locationIndexURL: URL {
        paths.applicationSupportURL.appendingPathComponent("library-location.json")
    }

    private func restoreOrCreateLibrary() throws {
        try fileManager.createDirectory(at: paths.applicationSupportURL, withIntermediateDirectories: true)

        if paths.libraryRootWasOverridden {
            if fileManager.fileExists(atPath: paths.defaultLibraryURL.appendingPathComponent("project.json").path) {
                let candidate = try decodeProject(at: paths.defaultLibraryURL)
                guard candidate.schemaVersion >= 2 else {
                    throw ProjectStoreError.invalidProjectFolder
                }
                try open(paths.defaultLibraryURL)
            } else {
                try createManagedLibrary(at: paths.defaultLibraryURL)
            }
            return
        }

        if fileManager.fileExists(atPath: locationIndexURL.path) {
            let index = try JSONDecoder.projectDecoder.decode(
                LibraryLocationIndex.self, from: Data(contentsOf: locationIndexURL)
            )
            let savedURL = resolvedURL(from: index) ?? URL(fileURLWithPath: index.dataRootPath, isDirectory: true)
            guard fileManager.fileExists(atPath: savedURL.appendingPathComponent("project.json").path) else {
                missingLibraryURL = savedURL
                selectedSection = .overview
                return
            }
            let candidate = try decodeProject(at: savedURL)
            guard candidate.schemaVersion >= 2 else {
                missingLibraryURL = savedURL
                throw ProjectStoreError.invalidProjectFolder
            }
            try open(savedURL)
            selectedAthleteID = index.selectedAthleteID.flatMap { id in project?.athletes.contains(where: { $0.id == id }) == true ? id : nil } ?? selectedAthleteID
            selectedTrialID = index.selectedTrialID.flatMap { id in project?.trials.contains(where: { $0.id == id }) == true ? id : nil } ?? selectedTrialID
            selectedSessionID = index.selectedSessionID.flatMap { id in project?.sessions?.contains(where: { $0.id == id }) == true ? id : nil }
            selectedReferenceSetID = index.selectedReferenceSetID.flatMap { id in project?.referenceSets.contains(where: { $0.id == id }) == true ? id : nil } ?? selectedReferenceSetID
            try persistLibraryLocation()
            return
        }

        try createManagedLibrary(at: paths.defaultLibraryURL)
    }

    func createManagedLibrary(at url: URL) throws {
        if fileManager.fileExists(atPath: url.appendingPathComponent("project.json").path) {
            try open(url)
            return
        }
        try fileManager.createDirectory(at: url, withIntermediateDirectories: true)
        try ensureDirectoryStructure(at: url)
        try beginAccessing(url)
        projectURL = url
        project = StudyProject(name: "Athlete Library")
        missingLibraryURL = nil
        selectedAthleteID = nil
        selectedTrialID = nil
        selectedSessionID = nil
        selectedSection = .athletes
        try save()
    }

    private func decodeProject(at url: URL) throws -> StudyProject {
        let dataURL = url.appendingPathComponent("project.json")
        guard fileManager.fileExists(atPath: dataURL.path) else { throw ProjectStoreError.invalidProjectFolder }
        let decoded = try JSONDecoder.projectDecoder.decode(StudyProject.self, from: Data(contentsOf: dataURL))
        guard decoded.schemaVersion <= currentProjectSchemaVersion else {
            throw ProjectStoreError.unsupportedSchema(decoded.schemaVersion)
        }
        return decoded
    }

    private func ensureDirectoryStructure(at root: URL) throws {
        for child in ["Athletes", "References", "comparisons", "relationships", "exports"] {
            try fileManager.createDirectory(
                at: root.appendingPathComponent(child, isDirectory: true), withIntermediateDirectories: true
            )
        }
    }

    private func persistLibraryLocation() throws {
        guard let root = projectURL, let project else { return }
        try fileManager.createDirectory(at: paths.applicationSupportURL, withIntermediateDirectories: true)
        let bookmark = try? root.bookmarkData(
            options: .withSecurityScope, includingResourceValuesForKeys: nil, relativeTo: nil
        )
        let index = LibraryLocationIndex(
            projectID: project.id,
            dataRootPath: root.standardizedFileURL.path,
            bookmarkData: bookmark,
            selectedAthleteID: selectedAthleteID,
            selectedTrialID: selectedTrialID,
            selectedSessionID: selectedSessionID,
            selectedReferenceSetID: selectedReferenceSetID
        )
        try JSONEncoder.projectEncoder.encode(index).write(to: locationIndexURL, options: .atomic)
    }

    private func resolvedURL(from index: LibraryLocationIndex) -> URL? {
        guard let bookmark = index.bookmarkData else { return nil }
        var stale = false
        return try? URL(
            resolvingBookmarkData: bookmark,
            options: [.withSecurityScope, .withoutUI],
            relativeTo: nil,
            bookmarkDataIsStale: &stale
        )
    }

    private func beginAccessing(_ url: URL) throws {
        _ = url.startAccessingSecurityScopedResource()
    }

    // MARK: - Legacy migration

    @discardableResult
    func importLegacyProject(at sourceRoot: URL) throws -> MigrationSummary {
        var source = try decodeProject(at: sourceRoot)
        _ = normalizeLegacyReferences(in: &source)
        if project == nil { try createManagedLibrary(at: paths.defaultLibraryURL) }
        guard let targetRoot = projectURL, var target = project else { throw ProjectStoreError.noOpenProject }
        guard targetRoot.standardizedFileURL.path != sourceRoot.standardizedFileURL.path else {
            throw ProjectStoreError.invalidLibraryPath("Choose a legacy project other than the active athlete library.")
        }

        let logURL = targetRoot.appendingPathComponent("migration-log.json")
        var log = (try? JSONDecoder.projectDecoder.decode(MigrationLog.self, from: Data(contentsOf: logURL))) ?? MigrationLog()
        let sourcePath = sourceRoot.standardizedFileURL.path
        let existingEntryIndex = log.entries.firstIndex {
            $0.sourceProjectID == source.id && $0.sourcePath == sourcePath
        }
        var warnings: [String] = []
        var importedAthleteIDs: [UUID] = []
        var importedSessionIDs: [UUID] = []
        var importedTrialIDs: [UUID] = []

        for athlete in source.athletes where !target.athletes.contains(where: { $0.id == athlete.id }) {
            target.athletes.append(athlete)
            importedAthleteIDs.append(athlete.id)
        }
        for session in source.sessions ?? [] where !(target.sessions ?? []).contains(where: { $0.id == session.id }) {
            if target.sessions == nil { target.sessions = [] }
            target.sessions?.append(session)
            importedSessionIDs.append(session.id)
        }

        for sourceTrial in source.trials {
            guard !target.trials.contains(where: { $0.id == sourceTrial.id }) else { continue }
            guard target.athletes.contains(where: { $0.id == sourceTrial.athleteID }) else {
                warnings.append("Skipped throw \(sourceTrial.id.uuidString): its athlete record is missing.")
                continue
            }
            var imported = sourceTrial
            let videoRelative = managedVideoRelativePath(
                athleteID: imported.athleteID,
                trialID: imported.id,
                filename: safeFilename(imported.originalFilename)
            )
            let videoDestination = targetRoot.appendingPathComponent(videoRelative)
            if let sourceVideo = legacyResourceURL(imported.sourceVideoRelativePath, root: sourceRoot),
               fileManager.fileExists(atPath: sourceVideo.path) {
                try copyItemPreservingExisting(from: sourceVideo, to: videoDestination)
            } else {
                warnings.append("Missing source video for throw \(imported.id.uuidString); its record was retained for Locate / Relink.")
            }
            imported.sourceVideoRelativePath = videoRelative

            if let oldDirectory = sourceTrial.preparationDirectoryRelativePath,
               let sourceDirectory = legacyResourceURL(oldDirectory, root: sourceRoot) {
                let newDirectory = (videoRelative as NSString).deletingLastPathComponent + "/\(imported.id.uuidString)-video-revisions"
                if fileManager.fileExists(atPath: sourceDirectory.path) {
                    try copyItemPreservingExisting(from: sourceDirectory, to: targetRoot.appendingPathComponent(newDirectory))
                }
                imported.preparationDirectoryRelativePath = newDirectory
                if let prepared = sourceTrial.preparedVideoRelativePath {
                    imported.preparedVideoRelativePath = replacingPrefix(prepared, old: oldDirectory, new: newDirectory)
                }
            }

            if let analysisPath = sourceTrial.analysisRelativePath {
                let analysisRelative = managedAnalysisRelativePath(
                    athleteID: imported.athleteID, trialID: imported.id
                )
                let analysisDestination = targetRoot.appendingPathComponent(analysisRelative)
                if let sourceAnalysis = legacyResourceURL(analysisPath, root: sourceRoot),
                   fileManager.fileExists(atPath: sourceAnalysis.path) {
                    try copyItemPreservingExisting(from: sourceAnalysis, to: analysisDestination)
                } else {
                    warnings.append("Missing analysis for throw \(imported.id.uuidString); reanalysis is available and the source-video record was retained.")
                }
                imported.analysisRelativePath = analysisRelative
            }
            target.trials.append(imported)
            importedTrialIDs.append(imported.id)
        }

        let availableTrialIDs = Set(target.trials.map(\.id))
        for sourceSet in source.referenceSets where !target.referenceSets.contains(where: { $0.id == sourceSet.id }) {
            var importedSet = sourceSet
            importedSet.trialIDs = importedSet.trialIDs.filter { availableTrialIDs.contains($0) }
            target.referenceSets.append(importedSet)
        }
        synchronizeReferenceFlags(in: &target)

        try copyDirectoryContentsPreservingExisting(
            from: sourceRoot.appendingPathComponent("comparisons", isDirectory: true),
            to: targetRoot.appendingPathComponent("comparisons", isDirectory: true)
        )
        try copyDirectoryContentsPreservingExisting(
            from: sourceRoot.appendingPathComponent("relationships", isDirectory: true),
            to: targetRoot.appendingPathComponent("relationships", isDirectory: true)
        )

        target.schemaVersion = currentProjectSchemaVersion
        target.appVersion = applicationVersion
        let previous = project
        project = target
        do { try save() }
        catch { project = previous; throw error }

        if let index = existingEntryIndex {
            log.entries[index].lastCheckedAt = Date()
            log.entries[index].importedAthleteIDs = Array(Set(log.entries[index].importedAthleteIDs + importedAthleteIDs)).sorted { $0.uuidString < $1.uuidString }
            log.entries[index].importedSessionIDs = Array(Set(log.entries[index].importedSessionIDs + importedSessionIDs)).sorted { $0.uuidString < $1.uuidString }
            log.entries[index].importedTrialIDs = Array(Set(log.entries[index].importedTrialIDs + importedTrialIDs)).sorted { $0.uuidString < $1.uuidString }
            log.entries[index].warnings = Array(Set(log.entries[index].warnings + warnings)).sorted()
        } else {
            log.entries.append(MigrationEntry(
                sourceProjectID: source.id,
                sourcePath: sourcePath,
                sourceSchemaVersion: source.schemaVersion,
                sourceUpdatedAt: source.updatedAt,
                importedAthleteIDs: importedAthleteIDs,
                importedSessionIDs: importedSessionIDs,
                importedTrialIDs: importedTrialIDs,
                warnings: warnings
            ))
        }
        try JSONEncoder.projectEncoder.encode(log).write(to: logURL, options: .atomic)
        selectedAthleteID = importedAthleteIDs.first ?? selectedAthleteID
        selectedTrialID = importedTrialIDs.first ?? selectedTrialID
        selectedSection = .athletes
        return MigrationSummary(
            athletesImported: importedAthleteIDs.count,
            sessionsImported: importedSessionIDs.count,
            trialsImported: importedTrialIDs.count,
            warnings: warnings,
            wasAlreadyImported: existingEntryIndex != nil && importedAthleteIDs.isEmpty && importedSessionIDs.isEmpty && importedTrialIDs.isEmpty
        )
    }

    private func migrationNotice(_ summary: MigrationSummary) -> String {
        if summary.wasAlreadyImported { return "That legacy project was already imported; no records were duplicated." }
        return "Imported \(summary.athletesImported) athletes, \(summary.sessionsImported) sessions, and \(summary.trialsImported) throws. The original project was not changed."
    }

    // MARK: - Managed paths

    @discardableResult
    private func normalizeLegacyReferences(in value: inout StudyProject) -> Bool {
        let legacyIDs = value.trials.filter(\.isReference).map(\.id)
        guard value.referenceSets.isEmpty, !legacyIDs.isEmpty else {
            synchronizeReferenceFlags(in: &value)
            return false
        }
        value.referenceSets = [ReferenceSet(
            name: "Imported Legacy References",
            scope: .global,
            trialIDs: legacyIDs,
            provenance: "legacy_isReference_migration",
            notes: "Created from legacy throw reference flags during schema migration."
        )]
        synchronizeReferenceFlags(in: &value)
        return true
    }

    private func synchronizeReferenceFlags(in value: inout StudyProject) {
        let assigned = Set(value.referenceSets.flatMap(\.trialIDs))
        for index in value.trials.indices {
            value.trials[index].isReference = assigned.contains(value.trials[index].id)
        }
    }

    private func athleteRelativeDirectory(for athlete: Athlete) -> String {
        "Athletes/\(slug(athlete.displayName))-\(String(athlete.id.uuidString.prefix(8)))"
    }

    private func athleteRelativeDirectory(for athleteID: UUID) -> String {
        guard let athlete = project?.athletes.first(where: { $0.id == athleteID }) else {
            return "Athletes/Athlete-\(String(athleteID.uuidString.prefix(8)))"
        }
        return athleteRelativeDirectory(for: athlete)
    }

    private func managedVideoRelativePath(athleteID: UUID, trialID: UUID, filename: String) -> String {
        "\(athleteRelativeDirectory(for: athleteID))/throws/\(String(trialID.uuidString.prefix(8)))-\(safeFilename(filename))"
    }

    private func managedAnalysisRelativePath(athleteID: UUID, trialID: UUID) -> String {
        "\(athleteRelativeDirectory(for: athleteID))/analyses/Throw-\(String(trialID.uuidString.prefix(8)))"
    }

    private func safeFilename(_ value: String) -> String {
        let cleaned = value.replacingOccurrences(of: "/", with: "-").replacingOccurrences(of: ":", with: "-")
        return cleaned.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "throw-video" : cleaned
    }

    private func slug(_ value: String) -> String {
        let components = value.components(separatedBy: CharacterSet.alphanumerics.inverted).filter { !$0.isEmpty }
        return String((components.joined(separator: "-").isEmpty ? "Athlete" : components.joined(separator: "-")).prefix(60))
    }

    private func replacingPrefix(_ path: String, old: String, new: String) -> String {
        guard path == old || path.hasPrefix(old + "/") else { return path }
        return new + path.dropFirst(old.count)
    }

    private func containedURL(for relativePath: String) -> URL? {
        guard let root = projectURL else { return nil }
        guard !relativePath.hasPrefix("/") else { return nil }
        let canonicalRoot = root.standardizedFileURL
        let candidate = canonicalRoot.appendingPathComponent(relativePath).standardizedFileURL
        guard candidate.path == canonicalRoot.path || candidate.path.hasPrefix(canonicalRoot.path + "/") else { return nil }
        return candidate
    }

    private func relativePathIfContained(_ candidate: URL, by root: URL) -> String? {
        let rootPath = root.standardizedFileURL.path
        let candidatePath = candidate.standardizedFileURL.path
        guard candidatePath.hasPrefix(rootPath + "/") else { return nil }
        return String(candidatePath.dropFirst(rootPath.count + 1))
    }

    private func legacyResourceURL(_ path: String, root: URL) -> URL? {
        if path.hasPrefix("/") { return URL(fileURLWithPath: path) }
        let candidate = root.appendingPathComponent(path).standardizedFileURL
        let rootPath = root.standardizedFileURL.path
        guard candidate.path == rootPath || candidate.path.hasPrefix(rootPath + "/") else { return nil }
        return candidate
    }

    private func copyItemPreservingExisting(from source: URL, to destination: URL) throws {
        guard !fileManager.fileExists(atPath: destination.path) else { return }
        try fileManager.createDirectory(at: destination.deletingLastPathComponent(), withIntermediateDirectories: true)
        try fileManager.copyItem(at: source, to: destination)
    }

    private func copyDirectoryContentsPreservingExisting(from source: URL, to destination: URL) throws {
        var isDirectory: ObjCBool = false
        guard fileManager.fileExists(atPath: source.path, isDirectory: &isDirectory), isDirectory.boolValue else { return }
        try fileManager.createDirectory(at: destination, withIntermediateDirectories: true)
        for item in try fileManager.contentsOfDirectory(at: source, includingPropertiesForKeys: [.isDirectoryKey]) {
            let target = destination.appendingPathComponent(item.lastPathComponent)
            let directory = (try? item.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) == true
            if directory, fileManager.fileExists(atPath: target.path) {
                try copyDirectoryContentsPreservingExisting(from: item, to: target)
            } else if !fileManager.fileExists(atPath: target.path) {
                try fileManager.copyItem(at: item, to: target)
            }
        }
    }

    private func writeAthleteProfiles() throws {
        guard let root = projectURL, let athletes = project?.athletes else { return }
        for athlete in athletes {
            let directory = root.appendingPathComponent(athleteRelativeDirectory(for: athlete), isDirectory: true)
            try fileManager.createDirectory(at: directory.appendingPathComponent("throws", isDirectory: true), withIntermediateDirectories: true)
            try fileManager.createDirectory(at: directory.appendingPathComponent("analyses", isDirectory: true), withIntermediateDirectories: true)
            try JSONEncoder.projectEncoder.encode(athlete)
                .write(to: directory.appendingPathComponent("profile.json"), options: .atomic)
        }
    }

    // MARK: - Recoverable deletion

    private func comparisonURLs(for trialID: UUID) -> [URL] {
        guard let root = projectURL else { return [] }
        let id = trialID.uuidString
        return [
            root.appendingPathComponent("comparisons/\(id)"),
            root.appendingPathComponent("comparisons/reference/\(id)"),
            root.appendingPathComponent("comparisons/single/\(id)"),
            root.appendingPathComponent("comparisons/own/\(id)"),
            root.appendingPathComponent("comparisons/trial/\(id)")
        ]
    }

    private func performRecoverableMutation(
        fileURLs: [URL],
        mutate: (inout StudyProject) -> Void
    ) throws {
        guard var changed = project, let root = projectURL else { throw ProjectStoreError.noOpenProject }
        let candidates = fileURLs
            .map(\.standardizedFileURL)
            .filter { fileManager.fileExists(atPath: $0.path) }
            .sorted { $0.path.count < $1.path.count }
        var selected: [URL] = []
        for candidate in candidates where !selected.contains(where: { candidate.path == $0.path || candidate.path.hasPrefix($0.path + "/") }) {
            selected.append(candidate)
        }

        let operation = root.appendingPathComponent(".Deletion Staging/\(UUID().uuidString)", isDirectory: true)
        var moves: [(source: URL, destination: URL)] = []
        do {
            if !selected.isEmpty {
                try fileManager.createDirectory(at: operation, withIntermediateDirectories: true)
                for (index, source) in selected.enumerated() {
                    let destination = operation.appendingPathComponent("\(index)-\(source.lastPathComponent)")
                    try fileManager.moveItem(at: source, to: destination)
                    moves.append((source, destination))
                }
            }
        } catch {
            for move in moves.reversed() { try? fileManager.moveItem(at: move.destination, to: move.source) }
            // Keep staging if rollback fails; it contains recoverable user files.
            throw error
        }

        let previous = project
        mutate(&changed)
        project = changed
        do { try save() }
        catch {
            project = previous
            for move in moves.reversed() {
                try? fileManager.createDirectory(at: move.source.deletingLastPathComponent(), withIntermediateDirectories: true)
                try? fileManager.moveItem(at: move.destination, to: move.source)
            }
            // Do not remove staging: a failed rollback must remain recoverable.
            throw error
        }

        guard !moves.isEmpty else { return }
        do { try trashHandler(operation) }
        catch {
            notice = "The records were removed, but recoverable files remain at \(operation.path)."
        }
    }

    private func valueWithTrialRemoved(_ value: StudyProject, trialID: UUID) -> StudyProject {
        var result = value
        result.trials.removeAll { $0.id == trialID }
        return result
    }
}

private extension String {
    var nilIfBlank: String? {
        let trimmed = trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
}
