import Foundation

enum AnalysisServiceError: LocalizedError {
    case repositoryNotFound
    case pythonNotReady(String)
    case invalidResponse
    case processFailed(String)

    var errorDescription: String? {
        switch self {
        case .repositoryNotFound:
            "The analysis engine could not be located. Run setup.sh from the repository first."
        case .pythonNotReady(let path):
            "The local Python environment was not found at \(path). Run ./setup.sh first."
        case .invalidResponse:
            "The analysis engine returned an unreadable response."
        case .processFailed(let message):
            message
        }
    }
}

/// One take found in a folder: its front and side videos (camera roles already checked).
struct DiscoveredTake: Identifiable, Hashable, Sendable {
    let take: Int
    let front: String?
    let side: String?
    let notes: [String]
    var id: Int { take }
}

struct TakeDiscovery: Identifiable, Sendable {
    let folder: URL
    let takes: [DiscoveredTake]
    /// Why camera roles could not be checked (nil when they were).
    let rolesNote: String?
    let swappedTakes: [Int]
    var id: String { folder.path }
}

/// One take waiting to be prepared: synchronised from the sound of both cameras and cut into one clip per
/// throw for each camera. Paths are the original recordings, which are never changed.
struct TakeImportJob: Codable, Hashable, Sendable {
    var take: Int
    var side: String
    var front: String?
    var athleteID: UUID
    var throwingSide: ThrowingSide
    var targetDirection: TargetDirection
}

/// One unit of work in the analysis queue. The queue runs ONE job at a time and is saved in the library
/// (analysis-queue.json) so it resumes after the app is quit or restarted.
enum QueueJob: Codable, Hashable, Sendable {
    case analyze(UUID)
    case prepareTake(TakeImportJob)
    case poolFrontCamera

    var trialID: UUID? {
        if case .analyze(let id) = self { return id }
        return nil
    }

    var isTakePreparation: Bool {
        if case .prepareTake = self { return true }
        return false
    }
}

/// Something in the queue that did not work, shown in the queue panel instead of interrupting with an alert.
struct QueueFailure: Identifiable, Hashable, Sendable {
    let id = UUID()
    let title: String
    let message: String
}

/// The queue as saved in the library (analysis-queue.json). The active job is saved first so it runs again.
private struct PersistedQueue: Codable {
    var schemaVersion: Int
    var jobs: [QueueJob]
    var paused: Bool
}

/// `auto_outcome` from two_view.json (decoded here so the queue does not depend on the report's model).
private struct AutomaticOutcomeFile: Decodable {
    var auto_outcome: TrialOutcome?
}

@MainActor
final class AnalysisService: ObservableObject {
    @Published private(set) var isRunning = false
    @Published private(set) var progress = 0.0
    @Published private(set) var stage = "Ready"
    /// The engine's stage key ("tracking_bag", …) of the running analysis; "" for other work.
    @Published private(set) var rawStage = ""
    @Published private(set) var detail = "Analysis stays on this Mac."
    @Published var errorMessage: String?
    private var activeProcess: Process?
    private var cancelled = false
    /// The throw being analysed (published so a report can reload when its own run starts or ends).
    @Published private(set) var activeTrialID: UUID?

    // MARK: Queue state
    // Analyses always run ONE AT A TIME: each decodes a whole clip into memory (about 2 GB for a 1080p clip), so
    // running several together can freeze the Mac. Take preparation goes through the same queue.

    /// Jobs waiting (the running one is `activeJob`).
    @Published private(set) var jobs: [QueueJob] = []
    @Published private(set) var activeJob: QueueJob?
    /// When the running job started (for the time left).
    @Published private(set) var jobStartedAt: Date?
    /// Paused: the running job finishes, then the queue waits.
    @Published private(set) var isPaused = false
    /// Problems collected while the queue ran (a failed throw does not stop the others).
    @Published private(set) var failures: [QueueFailure] = []
    /// Every throw queued since the queue was last empty, in order (for "Take 3/6 · Throw 2/4").
    @Published private(set) var batchTrialIDs: [UUID] = []
    /// Takes queued for preparation since the queue was last empty.
    @Published private(set) var batchTakeCount = 0
    /// The queue was restored from the library after a restart.
    @Published private(set) var resumedFromLastTime = false

    private weak var store: ProjectStore?
    /// The library the queued jobs belong to (the queue file lives there).
    private var queueLibraryURL: URL?
    private var workerTask: Task<Void, Never>?
    private var showLastWhenDone = false
    private var lastFinishedTrialID: UUID?
    private var openedTakeThisBatch = false
    /// Wall-clock seconds of recently finished throws and take preparations (rolling median for the time left).
    private var throwSeconds: [Double] = UserDefaults.standard.array(forKey: "analysisQueue.throwSeconds") as? [Double] ?? []
    private var prepareSeconds: [Double] = UserDefaults.standard.array(forKey: "analysisQueue.prepareSeconds") as? [Double] ?? []

    /// Throws waiting for analysis, in order.
    var queuedTrialIDs: [UUID] { jobs.compactMap(\.trialID) }

    /// True while anything is queued, running from the queue, or paused with work left.
    var hasQueue: Bool { activeJob != nil || !jobs.isEmpty }

    /// 1-based place in the waiting line of a queued throw, or nil.
    func queuePosition(of trialID: UUID) -> Int? {
        queuedTrialIDs.firstIndex(of: trialID).map { $0 + 1 }
    }

    /// Engine stages in their order, with coach-facing names ("Bag tracking (5/10)").
    static let engineStages: [(key: String, label: String)] = [
        ("loading_video", "Reading the video"), ("detecting_pose", "Body tracking"), ("applying_corrections", "Corrections"),
        ("filtering", "Smoothing"), ("tracking_bag", "Bag tracking"), ("calculating_kinematics", "Body measures"),
        ("detecting_events", "Finding the release"), ("normalizing", "Normalising"), ("saving_results", "Saving results"),
        ("annotating_video", "Overlay video"),
    ]

    /// "Bag tracking (5/10)" for an engine stage, else the current stage text.
    var stageLabel: String {
        if let index = Self.engineStages.firstIndex(where: { $0.key == rawStage }) {
            return "\(Self.engineStages[index].label) (\(index + 1)/\(Self.engineStages.count))"
        }
        return stage
    }

    /// Seconds of work left in the queue: rolling median of recently finished throws (about 2 min before any has
    /// finished on this Mac) for each throw still to come, plus the rest of the running job. A take still to be
    /// prepared counts as its preparation plus four throws.
    var secondsLeft: Double? {
        guard hasQueue else { return nil }
        let perThrow = Self.median(throwSeconds) ?? 120
        let perPrepare = Self.median(prepareSeconds) ?? 60
        var total = 0.0
        for job in jobs {
            switch job {
            case .analyze: total += perThrow
            case .prepareTake: total += perPrepare + 4 * perThrow
            case .poolFrontCamera: total += 15
            }
        }
        if let active = activeJob {
            let elapsed = jobStartedAt.map { Date().timeIntervalSince($0) } ?? 0
            switch active {
            case .analyze: total += max(0.1 * perThrow, perThrow - elapsed)
            case .prepareTake: total += max(5, perPrepare - elapsed) + 4 * perThrow
            case .poolFrontCamera: total += 10
            }
        }
        return total
    }

    /// "about 6 min left", "under a minute left", "about 1 h 20 min left".
    var timeLeftText: String? {
        guard let seconds = secondsLeft else { return nil }
        let minutes = Int((seconds / 60).rounded())
        if minutes < 1 { return "under a minute left" }
        if minutes < 90 { return "about \(minutes) min left" }
        return "about \(minutes / 60) h \(minutes % 60) min left"
    }

    nonisolated static func median(_ values: [Double]) -> Double? {
        let recent = values.suffix(10).filter { $0.isFinite && $0 > 0 }.sorted()
        guard !recent.isEmpty else { return nil }
        let middle = recent.count / 2
        return recent.count % 2 == 1 ? recent[middle] : (recent[middle - 1] + recent[middle]) / 2
    }

    // MARK: Queue control

    /// Add throws to the queue; they are analysed one after another, never at the same time.
    /// `showLastWhenDone`: open the last throw's report when the queue empties (single-video import flow).
    func enqueue(_ trials: [Trial], store: ProjectStore, showLastWhenDone: Bool = false) {
        attach(store)
        let waiting = Set(queuedTrialIDs)
        let ids = trials.map(\.id).filter { !waiting.contains($0) && $0 != activeTrialID && activeJob?.trialID != $0 }
        guard !ids.isEmpty else { return }
        jobs += ids.map { QueueJob.analyze($0) }
        batchTrialIDs += ids
        if showLastWhenDone { self.showLastWhenDone = true }
        isPaused = false
        persistQueue()
        startWorker()
    }

    /// Import takes and analyse them: each take is prepared in turn (sync, one clip per throw per camera) and
    /// registered, the front camera's field of view is pooled over all takes, then every new throw is analysed,
    /// one at a time. Analysis always follows import.
    func enqueueTakeImport(_ takes: [DiscoveredTake], athleteID: UUID, throwingSide: ThrowingSide,
                           targetDirection: TargetDirection, store: ProjectStore) {
        let preparations = takes.compactMap { take -> QueueJob? in
            guard let side = take.side else { return nil }
            return .prepareTake(TakeImportJob(take: take.take, side: side, front: take.front, athleteID: athleteID,
                                              throwingSide: throwingSide, targetDirection: targetDirection))
        }
        guard !preparations.isEmpty else { return }
        attach(store)
        // One pooling pass after the last take to prepare (it pools every take in the library).
        jobs.removeAll { $0 == .poolFrontCamera }
        jobs += preparations + [.poolFrontCamera]
        batchTakeCount += preparations.count
        openedTakeThisBatch = false
        isPaused = false
        persistQueue()
        startWorker()
    }

    /// Finish the running job, then wait.
    func pause() {
        guard hasQueue else { return }
        isPaused = true
        persistQueue()
        if !isRunning { stage = "Paused" }
    }

    func resume() {
        guard isPaused else { return }
        isPaused = false
        resumedFromLastTime = false
        persistQueue()
        startWorker()
    }

    func clearFailures() { failures = [] }

    /// Reload a queue saved in this library (after a quit or restart) and carry on after a short pause. A queue
    /// that was paused stays paused.
    func restoreQueue(store: ProjectStore) {
        guard !hasQueue, workerTask == nil, let root = store.projectURL else { return }
        let url = root.appendingPathComponent(Self.queueFileName)
        guard let data = try? Data(contentsOf: url),
              let saved = try? JSONDecoder.projectDecoder.decode(PersistedQueue.self, from: data) else { return }
        let known = Set((store.project?.trials ?? []).map(\.id))
        let restored = saved.jobs.filter { job in
            switch job {
            case .analyze(let id): return known.contains(id)
            case .prepareTake(let take): return FileManager.default.fileExists(atPath: take.side)
            case .poolFrontCamera: return true
            }
        }
        self.store = store
        queueLibraryURL = root
        guard restored.contains(where: { $0 != .poolFrontCamera }) else {
            try? FileManager.default.removeItem(at: url)
            return
        }
        jobs = restored
        batchTrialIDs = restored.compactMap(\.trialID)
        batchTakeCount = restored.filter(\.isTakePreparation).count
        isPaused = saved.paused
        resumedFromLastTime = true
        let count = restored.filter { $0 != .poolFrontCamera }.count
        stage = isPaused ? "Paused" : "Resuming"
        detail = "\(count) job\(count == 1 ? "" : "s") left from last time"
        if !isPaused {
            Task { [weak self] in
                try? await Task.sleep(for: .seconds(2))
                self?.startWorker()
            }
        }
    }

    private static let queueFileName = "analysis-queue.json"

    private func attach(_ store: ProjectStore) {
        self.store = store
        if !hasQueue || queueLibraryURL == nil { queueLibraryURL = store.projectURL }
    }

    private func startWorker() {
        guard workerTask == nil, !isPaused, !jobs.isEmpty, let store else { return }
        workerTask = Task { [weak self] in
            await self?.drain(store: store)
        }
    }

    private func drain(store: ProjectStore) async {
        while !isPaused, let job = jobs.first {
            // A single analysis started by hand finishes first.
            while isRunning { try? await Task.sleep(for: .milliseconds(300)) }
            guard !isPaused, jobs.first == job else { continue }
            if let library = queueLibraryURL, store.projectURL?.standardizedFileURL != library.standardizedFileURL {
                // Another library is open; its jobs wait in their own library's queue file.
                isPaused = true
                break
            }
            jobs.removeFirst()
            activeJob = job
            let started = Date()
            jobStartedAt = started
            persistQueue()
            switch job {
            case .analyze(let id):
                if let trial = store.project?.trials.first(where: { $0.id == id }) {
                    if store.videoState(for: trial).isAvailable {
                        await analyze(trial: trial, store: store, selectWhenDone: false, reportErrors: false)
                        if store.project?.trials.first(where: { $0.id == id })?.analysisStatus == "Analyzed" {
                            Self.remember(Date().timeIntervalSince(started), in: &throwSeconds, key: "analysisQueue.throwSeconds")
                            lastFinishedTrialID = id
                        }
                    } else {
                        failures.append(QueueFailure(title: trial.displayName,
                                                     message: "The video is missing. Use Locate / Relink Video…, then analyse it again."))
                    }
                }
            case .prepareTake(let take):
                if await prepareTake(take, store: store) {
                    Self.remember(Date().timeIntervalSince(started), in: &prepareSeconds, key: "analysisQueue.prepareSeconds")
                }
            case .poolFrontCamera:
                await poolFrontCamera(store: store)
            }
            activeJob = nil
            jobStartedAt = nil
            persistQueue()
        }
        workerTask = nil
        if !hasQueue { finishBatch(store: store) }
    }

    private func finishBatch(store: ProjectStore) {
        if showLastWhenDone, let last = lastFinishedTrialID,
           let trial = store.project?.trials.first(where: { $0.id == last }),
           trial.analysisStatus == "Analyzed", trial.takeKey == nil {
            store.showAnalyzedThrow(trial, batch: Set(batchTrialIDs))
        }
        resetBatch()
    }

    private func resetBatch() {
        batchTrialIDs = []
        batchTakeCount = 0
        showLastWhenDone = false
        lastFinishedTrialID = nil
        openedTakeThisBatch = false
        resumedFromLastTime = false
        persistQueue()
    }

    private static func remember(_ seconds: Double, in values: inout [Double], key: String) {
        guard seconds.isFinite, seconds > 1 else { return }
        values.append(seconds)
        values = Array(values.suffix(20))
        UserDefaults.standard.set(values, forKey: key)
    }

    /// Save the queue (running job first) in its library; remove the file when nothing is left.
    private func persistQueue() {
        guard let url = queueLibraryURL?.appendingPathComponent(Self.queueFileName) else { return }
        let all = (activeJob.map { [$0] } ?? []) + jobs
        guard all.contains(where: { $0 != .poolFrontCamera }) else {
            try? FileManager.default.removeItem(at: url)
            return
        }
        let saved = PersistedQueue(schemaVersion: 1, jobs: all, paused: isPaused)
        // A failed write only loses the restart copy; the queue itself keeps running.
        try? JSONEncoder.projectEncoder.encode(saved).write(to: url, options: .atomic)
    }

    // MARK: Take preparation

    /// Prepare one take and register its throws, which join the end of the queue (after any takes still to be
    /// prepared and the front-camera pooling). Returns whether throws were added.
    private func prepareTake(_ job: TakeImportJob, store: ProjectStore) async -> Bool {
        let title = "Take \(job.take)"
        guard let root = store.projectURL else { return false }
        guard store.project?.athletes.contains(where: { $0.id == job.athleteID }) == true else {
            failures.append(QueueFailure(title: title, message: "The athlete was deleted before this take was imported."))
            return false
        }
        guard FileManager.default.fileExists(atPath: job.side) else {
            failures.append(QueueFailure(title: title, message: "The side video is no longer at \(job.side)."))
            return false
        }
        isRunning = true
        defer { isRunning = false }
        progress = 0
        rawStage = ""
        stage = "Preparing take \(job.take)"
        detail = "Synchronising the two cameras from the sound and finding the throws"
        let relative = store.newTakeRelativeDirectory(athleteID: job.athleteID, takeNumber: job.take)
        let output = root.appendingPathComponent(relative, isDirectory: true)
        do {
            try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
            var arguments = ["prepare-take", "--side", job.side, "--output", output.path,
                             "--take-number", String(job.take), "--target-direction", job.targetDirection.rawValue,
                             "--expected-throws", "4"]
            if let front = job.front { arguments += ["--front", front] }
            let result = try await run(arguments)
            let found = result["throws"] as? Int ?? 0
            guard found > 0 else {
                failures.append(QueueFailure(title: title, message: "No throws were found in the side video."))
                try? FileManager.default.removeItem(at: output)
                return false
            }
            let added = try store.registerTake(athleteID: job.athleteID, takeRelativeDirectory: relative,
                                               throwingSide: job.throwingSide, targetDirection: job.targetDirection)
            if found != 4 {
                failures.append(QueueFailure(title: title, message: "\(found) throw\(found == 1 ? "" : "s") found instead of 4."))
            }
            let ids = added.map(\.id)
            jobs += ids.map { QueueJob.analyze($0) }
            batchTrialIDs += ids
            persistQueue()
            if !openedTakeThisBatch, let key = added.first?.takeKey {
                openedTakeThisBatch = true
                store.showImportedTake(key)
            }
            return !added.isEmpty
        } catch {
            if !cancelled { failures.append(QueueFailure(title: title, message: error.localizedDescription)) }
            try? FileManager.default.removeItem(at: output)
            return false
        }
    }

    /// Pool the front camera's field of view over every take the same phone recorded that day (all athletes;
    /// the engine groups the takes by camera and date).
    private func poolFrontCamera(store: ProjectStore) async {
        guard let root = store.projectURL else { return }
        let records = Set((store.project?.trials ?? []).compactMap(\.takeRecordRelativePath))
            .sorted().map { root.appendingPathComponent($0).path }
        guard !records.isEmpty else { return }
        isRunning = true
        defer { isRunning = false }
        progress = 0
        rawStage = ""
        stage = "Calibrating the front camera"
        detail = "Pooling the board's shape over \(records.count) take\(records.count == 1 ? "" : "s")"
        do { _ = try await run(["pool-front-camera", "--takes"] + records, updateProgress: false) }
        catch { if !cancelled { failures.append(QueueFailure(title: "Front camera calibration", message: error.localizedDescription)) } }
    }

    // MARK: One analysis

    /// `selectWhenDone`: show the throw's report afterwards if the user is still looking at this throw or its athlete.
    /// `reportErrors`: false inside the queue, where a failure is listed in the queue panel instead of an alert.
    func analyze(trial: Trial, store: ProjectStore, backend: String? = nil, selectWhenDone: Bool = true,
                 reportErrors: Bool = true) async {
        guard let video = store.videoURL(for: trial) else {
            errorMessage = "The source video is missing. Use Locate / Relink before analysis."
            return
        }
        guard let settings = store.project?.analysisSettings else { return }
        guard !isRunning else { return }
        cancelled = false
        activeTrialID = trial.id
        isRunning = true
        progress = 0
        rawStage = ""
        stage = "Preparing"
        detail = "Validating the local analysis environment"
        if reportErrors { errorMessage = nil }
        do {
            let destination = try store.analysisOutput(for: trial)
            let relativeOutput = destination.relativePath
            let output = destination.url
            try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
            // A failed/cancelled run must not leave old measurements looking current.
            try Data("{\"reason\":\"analysis_in_progress\"}".utf8)
                .write(to: output.appendingPathComponent("needs_reanalysis.json"), options: .atomic)
            let configURL = output.appendingPathComponent("app-analysis-config.json")
            let configData = try JSONSerialization.data(withJSONObject: settings.pythonPayload, options: [.prettyPrinted, .sortedKeys])
            try configData.write(to: configURL, options: .atomic)
            var arguments = [
                "analyze", video.path,
                "--output", output.path,
                "--trial-id", trial.id.uuidString,
                "--athlete-id", trial.athleteID.uuidString,
                "--view", trial.cameraView.rawValue,
                "--throwing-side", trial.throwingSide.rawValue,
                "--target-direction", trial.targetDirection.rawValue,
                "--backend", backend ?? settings.poseBackend ?? "sports2d",
                "--device", "cpu",
                "--config", configURL.path,
                "--app-version", applicationVersion,
            ]
            if let sourceURL = trial.sourceURL { arguments += ["--source-url", sourceURL] }
            if let recorded = trial.recordingDate { arguments += ["--recording-date", recorded] }
            if let attribution = trial.sourceAttribution { arguments += ["--source-attribution", attribution] }
            let corrections = output.appendingPathComponent("corrections.json")
            if FileManager.default.fileExists(atPath: corrections.path) {
                arguments += ["--corrections", corrections.path]
            }
            let events = output.appendingPathComponent("events.json")
            if FileManager.default.fileExists(atPath: events.path) {
                arguments += ["--events", events.path]
            }
            let bagSeed = output.appendingPathComponent("bag_seed.json")
            if FileManager.default.fileExists(atPath: bagSeed.path) {
                arguments += ["--bag-seed", bagSeed.path]
            }
            let bagCorrections = output.appendingPathComponent("bag_corrections.json")
            if FileManager.default.fileExists(atPath: bagCorrections.path) {
                arguments += ["--bag-corrections", bagCorrections.path]
            }
            let calibration = output.appendingPathComponent("calibration.json")
            if FileManager.default.fileExists(atPath: calibration.path) {
                arguments += ["--calibration", calibration.path]
            }
            _ = try await run(arguments, diagnosticURL: output.appendingPathComponent("analysis-worker.log"))
            if let outcome = trial.outcome {
                try await summarizeOutcome(outcome, analysisURL: output)
            }
            try store.markAnalysisComplete(trialID: trial.id, relativePath: relativeOutput)
            // Two-camera throws: record the front camera's result when it is confident and nobody entered one
            // (an automatic result is replaced; a person's entry never is).
            if let current = store.project?.trials.first(where: { $0.id == trial.id }),
               current.outcome == nil || current.outcome?.isAutomatic == true,
               let data = try? Data(contentsOf: output.appendingPathComponent("two_view.json")),
               let automatic = (try? JSONDecoder().decode(AutomaticOutcomeFile.self, from: data))?.auto_outcome,
               automatic != current.outcome {
                try? store.saveOutcome(automatic, for: current)
            }
            let dirty = output.appendingPathComponent("needs_reanalysis.json")
            if FileManager.default.fileExists(atPath: dirty.path) { try FileManager.default.removeItem(at: dirty) }
            if selectWhenDone { store.showAnalyzedThrow(trial) }
            stage = "Complete"
            rawStage = ""
            let resultsURL = output.appendingPathComponent("results.json")
            let payload = (try? Data(contentsOf: resultsURL)).flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }
            detail = (payload?["bag"] as? [String: Any]) == nil
                ? "Body analysis ready. Select & track the bag in the video to complete the throw analysis."
                : "Body and bag processed. Review tracking and release before interpreting Results."
            progress = 1
        } catch {
            if cancelled {
                errorMessage = nil
            } else if reportErrors {
                errorMessage = error.localizedDescription
            } else {
                failures.append(QueueFailure(title: trial.displayName, message: error.localizedDescription))
            }
            try? store.markAnalysisStatus(trialID: trial.id, status: cancelled ? "Analysis cancelled" : "Analysis failed")
            stage = "Analysis failed"
            rawStage = ""
            detail = error.localizedDescription
        }
        activeTrialID = nil
        isRunning = false
    }

    func compare(test: Trial, references: [Trial], store: ProjectStore, mode: String = "reference") async throws -> URL {
        guard !isRunning else { throw AnalysisServiceError.processFailed("Wait for the current analysis to finish.") }
        guard let root = store.projectURL, let testURL = store.analysisURL(for: test) else {
            throw ProjectStoreError.noOpenProject
        }
        let compatible = references.filter { $0.cameraView == test.cameraView }
        guard !compatible.isEmpty else {
            throw AnalysisServiceError.processFailed("Choose at least one analyzed reference with the same camera-view label.")
        }
        let referenceURLs = compatible.compactMap(store.analysisURL(for:))
        guard referenceURLs.count == compatible.count else {
            throw AnalysisServiceError.processFailed("Every reference must be analyzed before comparison.")
        }
        let output = root.appendingPathComponent("comparisons/\(mode == "reference" ? "" : mode + "/")\(test.id.uuidString)")
        try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
        var arguments = ["compare", "--test", testURL.path]
        for url in referenceURLs { arguments += ["--reference", url.path] }
        arguments += ["--output", output.path]
        isRunning = true
        progress = 0.15
        stage = "Comparing"
        detail = "Using time-preserving, body-normalized trajectories"
        defer { isRunning = false }
        _ = try await run(arguments)
        progress = 1
        stage = "Comparison complete"
        detail = "Resemblance to a reference is kept separate from performance."
        return output
    }

    func relationships(for athleteID: UUID, store: ProjectStore) async throws -> URL {
        guard let project = store.project, let root = store.projectURL else { throw ProjectStoreError.noOpenProject }
        let trials = project.trials.filter { $0.athleteID == athleteID && $0.analysisRelativePath != nil }
        guard !trials.isEmpty else {
            throw AnalysisServiceError.processFailed("Analyze at least one trial for this athlete first.")
        }
        var outcomes: [String: Any] = [:]
        for trial in trials where trial.outcome != nil {
            let data = try JSONEncoder.projectEncoder.encode(trial.outcome)
            outcomes[trial.id.uuidString] = try JSONSerialization.jsonObject(with: data)
        }
        let directory = root.appendingPathComponent("relationships/\(athleteID.uuidString)")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let outcomesURL = directory.appendingPathComponent("outcomes.json")
        try JSONSerialization.data(withJSONObject: outcomes, options: [.prettyPrinted, .sortedKeys])
            .write(to: outcomesURL, options: .atomic)
        var arguments = ["relationships"]
        for trial in trials {
            if let analysis = store.analysisURL(for: trial) { arguments += ["--analysis", analysis.path] }
            let comparison = root.appendingPathComponent("comparisons/\(trial.id.uuidString)/comparison.json")
            if FileManager.default.fileExists(atPath: comparison.path) {
                arguments += ["--comparison", comparison.deletingLastPathComponent().path]
            }
        }
        let output = directory.appendingPathComponent("relationships.json")
        arguments += [
            "--outcomes", outcomesURL.path,
            "--output", output.path,
            "--minimum-trials", String(project.analysisSettings.minimumRelationshipTrials),
        ]
        isRunning = true
        progress = 0.2
        stage = "Estimating relationships"
        detail = "Within-athlete observational analysis only"
        defer { isRunning = false }
        _ = try await run(arguments)
        progress = 1
        stage = "Relationship analysis complete"
        return output
    }

    func summarizeOutcome(_ outcome: TrialOutcome, analysisURL: URL?) async throws {
        guard let analysisURL else { return }
        let output = analysisURL.appendingPathComponent("outcome.json")
        try JSONEncoder.projectEncoder.encode(outcome).write(to: output, options: .atomic)
        let summary = try await run(["outcome", output.path], updateProgress: false)
        let data = try JSONSerialization.data(withJSONObject: summary, options: [.prettyPrinted, .sortedKeys])
        try data.write(to: output, options: .atomic)
    }

    func cancel() {
        // Cancelling stops the whole queue, not only the throw being analysed.
        jobs.removeAll()
        isPaused = false
        cancelled = true
        activeProcess?.terminate()
        stage = "Cancelling"
        detail = "Stopping the worker. Original video and corrections are preserved."
        persistQueue()
        if workerTask == nil { resetBatch() }
    }

    func refreshInsights(trial: Trial, store: ProjectStore) async throws {
        guard !isRunning, let root = store.projectURL else { return }
        isRunning = true; stage = "Preparing results"; detail = "Summarizing comparable throws and rendering the local report"; progress = 0.25
        defer { isRunning = false }
        _ = try await run(["insights", "--project", root.path, "--trial-id", trial.id.uuidString])
        progress = 1; stage = "Results ready"
    }

    /// Recompute one athlete's coaching dashboard (Python `athlete-dashboard`).
    func refreshDashboard(athleteID: UUID, store: ProjectStore) async throws {
        guard !isRunning, let root = store.projectURL else { return }
        isRunning = true; stage = "Preparing dashboard"; detail = "Summarizing this athlete's throws"; progress = 0.3
        defer { isRunning = false }
        _ = try await run(["athlete-dashboard", "--project", root.path, "--athlete-id", athleteID.uuidString])
        progress = 1; stage = "Dashboard ready"
    }

    // MARK: Two-camera takes

    /// Pair the Take_<n>_Front / Take_<n>_Side videos in a folder and check which camera recorded each file.
    func discoverTakes(in folder: URL) async throws -> TakeDiscovery {
        // Reading the files' headers is light, so it runs beside a queued analysis (not exclusive).
        let result = try await run(["discover-takes", folder.path], updateProgress: false, exclusive: false)
        let takes = ((result["takes"] as? [[String: Any]]) ?? []).compactMap { item -> DiscoveredTake? in
            guard let number = item["take"] as? Int else { return nil }
            return DiscoveredTake(take: number, front: item["front"] as? String, side: item["side"] as? String,
                                  notes: item["notes"] as? [String] ?? [])
        }
        let roles = result["roles"] as? [String: Any]
        return TakeDiscovery(folder: folder, takes: takes, rolesNote: roles?["reason"] as? String,
                             swappedTakes: roles?["swapped_takes"] as? [Int] ?? [])
    }

    func probe() async throws -> [String: Any] { try await run(["probe"], updateProgress: false) }

    func videoInfo(_ url: URL) async throws -> [String: Any] {
        try await run(["video-info", url.path], updateProgress: false)
    }

    func prepareVideo(trial: Trial, store: ProjectStore, start: Int, end: Int, crop: [Int], rotation: Int) async throws {
        guard !isRunning, let source = store.originalVideoURL(for: trial) else {
            throw AnalysisServiceError.processFailed("Wait for the worker, or relink the original recording first.")
        }
        let output = try store.preparationOutput(for: trial)
        isRunning = true; stage = "Preparing video"; detail = "Creating a separate analysis copy; preserving the original"; progress = 0.2
        defer { isRunning = false }
        _ = try await run(["prepare-video", source.path, "--output", output.path,
            "--start-frame", String(start), "--end-frame", String(end), "--crop"] + crop.map(String.init) + ["--rotation", String(rotation)])
        try store.usePreparedVideo(output, for: trial)
        progress = 1; stage = "Video ready"; detail = "Analyze this version before reviewing measurements."
    }

    @discardableResult
    /// `exclusive`: the one heavy worker slot (analysis, take preparation); a light helper (reading file headers)
    /// passes false and runs beside it, without progress and without being cancelled by Cancel.
    private func run(_ arguments: [String], updateProgress: Bool = true, diagnosticURL: URL? = nil,
                     exclusive: Bool = true) async throws -> [String: Any] {
        if exclusive {
            guard activeProcess == nil else { throw AnalysisServiceError.processFailed("Wait for the current worker to finish, then try again.") }
            cancelled = false
        }
        let manager = FileManager.default
        let resources = Bundle.main.resourceURL?.appendingPathComponent("python")
        let engine: URL
        let python: URL
        let installedRuntime = manager.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/Cornhole Biomechanics Lab/Runtime/bin/python")
        // A repository build always runs the checked-out engine and its runtime.
        // Keep the bundled fallback for older standalone installations.
        if let repository = RepositoryLocation.resolve() {
            engine = repository.appendingPathComponent("python")
            python = repository.appendingPathComponent(".venv/bin/python")
        } else if let resources, manager.fileExists(atPath: resources.appendingPathComponent("cornhole_biomech").path) {
            engine = resources
            python = installedRuntime
        } else {
            let repository = try repositoryRoot()
            engine = repository.appendingPathComponent("python")
            python = repository.appendingPathComponent(".venv/bin/python")
        }
        guard manager.isExecutableFile(atPath: python.path) else {
            throw AnalysisServiceError.pythonNotReady(python.path)
        }
        var diagnosticLog: FileHandle?
        if let diagnosticURL {
            manager.createFile(atPath: diagnosticURL.path, contents: nil)
            diagnosticLog = try? FileHandle(forWritingTo: diagnosticURL)
        }
        defer { try? diagnosticLog?.close() }
        let process = Process()
        if exclusive { activeProcess = process }
        defer { if activeProcess === process { activeProcess = nil } }
        let standardOutput = Pipe()
        let standardError = Pipe()
        process.executableURL = python
        process.arguments = ["-m", "cornhole_biomech"] + arguments
        process.currentDirectoryURL = engine
        var environment = ProcessInfo.processInfo.environment
        environment["PYTHONPATH"] = engine.path
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        if let model = Bundle.main.resourceURL?.appendingPathComponent("models/pose_landmarker_heavy.task"), manager.fileExists(atPath: model.path) { environment["CORNHOLE_MEDIAPIPE_MODEL"] = model.path }
        if let helper = Bundle.main.executableURL?.deletingLastPathComponent().appendingPathComponent("scene-vision"),
           manager.fileExists(atPath: helper.path) { environment["CORNHOLE_SCENE_VISION"] = helper.path }
        environment["PYTHONUNBUFFERED"] = "1"
        let plottingCache = manager.temporaryDirectory.appendingPathComponent("cornhole-matplotlib", isDirectory: true)
        try manager.createDirectory(at: plottingCache, withIntermediateDirectories: true)
        environment["MPLCONFIGDIR"] = plottingCache.path
        process.environment = environment
        process.standardOutput = standardOutput
        process.standardError = standardError
        try process.run()

        async let errorData = readAll(from: standardError.fileHandleForReading)
        var finalData: [String: Any]?
        var engineError: String?
        var buffered = Data()
        for try await byte in standardOutput.fileHandleForReading.bytes {
            if byte == 10 {
                try? diagnosticLog?.write(contentsOf: buffered + Data([10]))
                if !buffered.isEmpty,
                   let object = try? JSONSerialization.jsonObject(with: buffered) as? [String: Any] {
                    if object["type"] as? String == "progress", updateProgress, exclusive {
                        let engineStage = object["stage"] as? String ?? "working"
                        let rawFraction = object["fraction"] as? Double ?? progress
                        progress = engineStage == "detecting_pose" ? 0.04 + 0.40 * rawFraction : rawFraction
                        rawStage = engineStage
                        stage = humanize(engineStage)
                        detail = object["message"] as? String ?? detail
                    } else if object["type"] as? String == "result" {
                        finalData = object["data"] as? [String: Any]
                    } else if object["type"] as? String == "error" {
                        engineError = object["message"] as? String ?? "Analysis failed."
                    }
                }
                buffered.removeAll(keepingCapacity: true)
            } else {
                buffered.append(byte)
            }
        }
        await Task.detached { process.waitUntilExit() }.value
        let diagnosticData = try await errorData
        try? diagnosticLog?.write(contentsOf: diagnosticData)
        let diagnostic = String(data: diagnosticData, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if let engineError { throw AnalysisServiceError.processFailed(engineError) }
        if exclusive && cancelled { throw AnalysisServiceError.processFailed("Analysis cancelled. You can run it again when ready.") }
        guard process.terminationStatus == 0 else {
            throw AnalysisServiceError.processFailed(diagnostic.isEmpty ? "The analysis process exited with code \(process.terminationStatus)." : diagnostic)
        }
        guard let finalData else { throw AnalysisServiceError.invalidResponse }
        return finalData
    }

    nonisolated private func readAll(from handle: FileHandle) async throws -> Data {
        try await Task.detached { try handle.readToEnd() ?? Data() }.value
    }

    private func repositoryRoot() throws -> URL {
        if let repository = RepositoryLocation.resolve() { return repository }
        throw AnalysisServiceError.repositoryNotFound
    }

    private func humanize(_ value: String) -> String {
        value.replacingOccurrences(of: "_", with: " ").capitalized
    }
}
