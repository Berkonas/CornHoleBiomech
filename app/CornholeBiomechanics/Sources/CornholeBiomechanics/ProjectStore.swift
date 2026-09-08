import AppKit
import Foundation
import UniformTypeIdentifiers

enum ProjectStoreError: LocalizedError {
    case noOpenProject
    case invalidProjectFolder
    case athleteRequired
    case fileAlreadyExists(String)

    var errorDescription: String? {
        switch self {
        case .noOpenProject: "Create or open a project first."
        case .invalidProjectFolder: "That folder does not contain a readable project.json file."
        case .athleteRequired: "Add and select an athlete before importing a trial."
        case .fileAlreadyExists(let name): "A project file named \(name) already exists; the source was not overwritten."
        }
    }
}

@MainActor
final class ProjectStore: ObservableObject {
    @Published private(set) var project: StudyProject?
    @Published private(set) var projectURL: URL?
    @Published var selectedSection: AppSection? = .overview
    @Published var selectedAthleteID: UUID?
    @Published var selectedTrialID: UUID?
    @Published var selectedSessionID: UUID?
    @Published var notice: String?
    @Published var errorMessage: String?

    private let fileManager = FileManager.default

    var selectedAthlete: Athlete? {
        project?.athletes.first { $0.id == selectedAthleteID }
    }

    var selectedTrial: Trial? {
        project?.trials.first { $0.id == selectedTrialID }
    }

    var analyzedTrials: [Trial] {
        project?.trials.filter { $0.analysisRelativePath != nil } ?? []
    }

    func createProject() {
        let panel = NSSavePanel()
        panel.title = "Create Research Project"
        panel.nameFieldStringValue = "Cornhole Study.cornholeproject"
        panel.canCreateDirectories = true
        panel.isExtensionHidden = false
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            guard !fileManager.fileExists(atPath: url.path) else {
                throw ProjectStoreError.fileAlreadyExists(url.lastPathComponent)
            }
            try fileManager.createDirectory(at: url, withIntermediateDirectories: true)
            for child in ["videos", "analyses", "comparisons", "relationships", "exports"] {
                try fileManager.createDirectory(at: url.appendingPathComponent(child), withIntermediateDirectories: true)
            }
            projectURL = url
            project = StudyProject(name: url.deletingPathExtension().lastPathComponent)
            selectedSection = .overview
            try save()
            notice = "Created \(project?.name ?? "project")."
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func openProject() {
        let panel = NSOpenPanel()
        panel.title = "Open Research Project"
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do { try open(url) } catch { errorMessage = error.localizedDescription }
    }

    func open(_ url: URL) throws {
        let dataURL = url.appendingPathComponent("project.json")
        guard fileManager.fileExists(atPath: dataURL.path) else { throw ProjectStoreError.invalidProjectFolder }
        let decoded = try JSONDecoder.projectDecoder.decode(StudyProject.self, from: Data(contentsOf: dataURL))
        projectURL = url
        project = decoded
        selectedAthleteID = decoded.athletes.first?.id
        selectedTrialID = decoded.trials.first?.id
        selectedSection = .overview
        notice = "Opened \(decoded.name)."
    }

    func save() throws {
        guard var value = project, let root = projectURL else { throw ProjectStoreError.noOpenProject }
        value.updatedAt = Date()
        let data = try JSONEncoder.projectEncoder.encode(value)
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
            notes: draft.notes
        )
        project?.athletes.append(athlete)
        selectedAthleteID = athlete.id
        try save()
    }

    func importVideo(_ draft: ImportDraft) throws -> Trial {
        guard var value = project, let root = projectURL else { throw ProjectStoreError.noOpenProject }
        guard let athleteID = draft.athleteID else { throw ProjectStoreError.athleteRequired }
        let trialID = UUID()
        let safeName = draft.videoURL.lastPathComponent.replacingOccurrences(of: "/", with: "-")
        let relative = "videos/\(trialID.uuidString)_\(safeName)"
        let destination = root.appendingPathComponent(relative)
        guard !fileManager.fileExists(atPath: destination.path) else {
            throw ProjectStoreError.fileAlreadyExists(destination.lastPathComponent)
        }
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
            sessionID: draft.sessionID
        )
        value.trials.append(trial)
        project = value
        selectedTrialID = trial.id
        selectedAthleteID = athleteID
        try save()
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
        guard let index = project?.trials.firstIndex(where: { $0.id == changed.id }) else { return }
        project?.trials[index] = changed
        try save()
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
        projectURL?.appendingPathComponent(relativePath)
    }

    func videoURL(for trial: Trial) -> URL? { url(for: trial.sourceVideoRelativePath) }

    func analysisURL(for trial: Trial) -> URL? {
        trial.analysisRelativePath.flatMap(url(for:))
    }

    func revealProject() {
        if let projectURL { NSWorkspace.shared.activateFileViewerSelecting([projectURL]) }
    }
}

private extension String {
    var nilIfBlank: String? {
        let trimmed = trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
}
