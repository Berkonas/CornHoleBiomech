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

@MainActor
final class AnalysisService: ObservableObject {
    @Published private(set) var isRunning = false
    @Published private(set) var progress = 0.0
    @Published private(set) var stage = "Ready"
    @Published private(set) var detail = "Analysis stays on this Mac."
    @Published var errorMessage: String?
    private var activeProcess: Process?
    private var cancelled = false
    /// The throw being analysed (published so a report can reload when its own run starts or ends).
    @Published private(set) var activeTrialID: UUID?
    /// Throws waiting for analysis. Analyses always run ONE AT A TIME: each decodes a whole clip into
    /// memory (about 2 GB for a 1080p clip), so running several together can freeze the Mac.
    @Published private(set) var queue: [UUID] = []
    /// Size of the current batch (for "throw 3 of 12"); 0 when no batch is running.
    @Published private(set) var batchTotal = 0
    @Published private(set) var batchDone = 0
    private var queueTask: Task<Void, Never>?

    /// "Throw 3 of 12" while a batch runs, else nil.
    var batchPosition: String? {
        batchTotal > 1 ? "Throw \(min(batchDone + 1, batchTotal)) of \(batchTotal)" : nil
    }

    /// Add throws to the queue; they are analyzed one after another, never at the same time.
    /// `showLastWhenDone`: open the last throw's report when the batch ends (import flow).
    func enqueue(_ trials: [Trial], store: ProjectStore, showLastWhenDone: Bool = false) {
        let ids = trials.map(\.id).filter { !queue.contains($0) && $0 != activeTrialID }
        guard !ids.isEmpty else { return }
        queue += ids
        batchTotal += ids.count
        guard queueTask == nil else { return }
        let batch = Set(ids)
        queueTask = Task { [weak self] in
            guard let self else { return }
            var last: Trial?
            while let next = self.queue.first {
                // A single analysis started by hand finishes first.
                while self.isRunning { try? await Task.sleep(for: .milliseconds(300)) }
                guard self.queue.first == next else { continue }
                self.queue.removeFirst()
                // Skip throws deleted while the batch was waiting; use the current record.
                guard let trial = store.project?.trials.first(where: { $0.id == next }) else { self.batchDone += 1; continue }
                await self.analyze(trial: trial, store: store, selectWhenDone: false)
                self.batchDone += 1
                last = trial
            }
            self.batchTotal = 0
            self.batchDone = 0
            self.queueTask = nil
            if showLastWhenDone, let last, store.project?.trials.first(where: { $0.id == last.id })?.analysisStatus == "Analyzed" {
                store.showAnalyzedThrow(last, batch: batch)
            }
        }
    }

    /// `selectWhenDone`: show the throw's report afterwards if the user is still looking at this throw or its athlete.
    func analyze(trial: Trial, store: ProjectStore, backend: String? = nil, selectWhenDone: Bool = true) async {
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
        stage = "Preparing"
        detail = "Validating the local analysis environment"
        errorMessage = nil
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
            let dirty = output.appendingPathComponent("needs_reanalysis.json")
            if FileManager.default.fileExists(atPath: dirty.path) { try FileManager.default.removeItem(at: dirty) }
            if selectWhenDone { store.showAnalyzedThrow(trial) }
            stage = "Complete"
            let resultsURL = output.appendingPathComponent("results.json")
            let payload = (try? Data(contentsOf: resultsURL)).flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }
            detail = (payload?["bag"] as? [String: Any]) == nil
                ? "Body analysis ready. Select & track the bag in the video to complete the throw analysis."
                : "Body and bag processed. Review tracking and release before interpreting Results."
            progress = 1
        } catch {
            errorMessage = cancelled ? nil : error.localizedDescription
            try? store.markAnalysisStatus(trialID: trial.id, status: cancelled ? "Analysis cancelled" : "Analysis failed")
            stage = "Analysis failed"
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
        // Cancelling stops the whole batch, not only the throw being analysed.
        queue.removeAll()
        cancelled = true
        activeProcess?.terminate()
        stage = "Cancelling"
        detail = "Stopping the worker. Original video and corrections are preserved."
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
    private func run(_ arguments: [String], updateProgress: Bool = true, diagnosticURL: URL? = nil) async throws -> [String: Any] {
        guard activeProcess == nil else { throw AnalysisServiceError.processFailed("Wait for the current worker to finish, then try again.") }
        cancelled = false
        let manager = FileManager.default
        let resources = Bundle.main.resourceURL?.appendingPathComponent("python")
        let engine: URL
        let python: URL
        let installedRuntime = manager.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/Cornhole Biomechanics Lab/Runtime/bin/python")
        if let resources, manager.fileExists(atPath: resources.appendingPathComponent("cornhole_biomech").path) {
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
        activeProcess = process
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
                    if object["type"] as? String == "progress", updateProgress {
                        let rawStage = object["stage"] as? String ?? "working"
                        let rawFraction = object["fraction"] as? Double ?? progress
                        progress = rawStage == "detecting_pose" ? 0.04 + 0.40 * rawFraction : rawFraction
                        stage = humanize(rawStage)
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
        if cancelled { throw AnalysisServiceError.processFailed("Analysis cancelled. You can run it again when ready.") }
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
        let manager = FileManager.default
        var candidates: [URL] = []
        if let explicit = ProcessInfo.processInfo.environment["CORNHOLE_BIOMECH_ROOT"] {
            candidates.append(URL(fileURLWithPath: explicit))
        }
        candidates.append(URL(fileURLWithPath: manager.currentDirectoryPath))
        var source = URL(fileURLWithPath: #filePath)
        for _ in 0..<5 { source.deleteLastPathComponent() }
        candidates.append(source)
        var bundle = Bundle.main.bundleURL
        for _ in 0..<7 {
            candidates.append(bundle)
            bundle.deleteLastPathComponent()
        }
        for candidate in candidates {
            if manager.fileExists(atPath: candidate.appendingPathComponent("python/cornhole_biomech").path) {
                return candidate
            }
        }
        throw AnalysisServiceError.repositoryNotFound
    }

    private func humanize(_ value: String) -> String {
        value.replacingOccurrences(of: "_", with: " ").capitalized
    }
}
