import AppKit
import SwiftUI

// MARK: - Hole windows

/// Release speeds / angles whose drag-free first contact lands in the hole window (`LaunchModel.zone() == .hole`),
/// holding the other release variables at this throw's values.
enum HoleWindow {
    /// Contiguous run of speeds (0.01 m/s steps, 1–15 m/s) that reach the hole at `angle`, `height`, `distance`;
    /// the run nearest `near` if there is more than one.
    static func speed(angle: Double, height: Double, distance: Double, near: Double, slide: Double = 0.45) -> ClosedRange<Double>? {
        run(steps: 100...1500, step: 0.01, near: near) { v in
            LaunchModel(LaunchParameters(speed: v, angleDegrees: angle, releaseHeight: height, distanceToBoard: distance,
                                         slideAllowance: slide)).zone() == .hole
        }
    }

    /// Contiguous run of angles (0.1° steps, −10–80°) that reach the hole at `speed`, `height`, `distance`.
    static func angle(speed: Double, height: Double, distance: Double, near: Double, slide: Double = 0.45) -> ClosedRange<Double>? {
        run(steps: -100...800, step: 0.1, near: near) { a in
            LaunchModel(LaunchParameters(speed: speed, angleDegrees: a, releaseHeight: height, distanceToBoard: distance,
                                         slideAllowance: slide)).zone() == .hole
        }
    }

    private static func run(steps: ClosedRange<Int>, step: Double, near: Double, isHole: (Double) -> Bool) -> ClosedRange<Double>? {
        var runs: [ClosedRange<Int>] = []
        var start: Int?
        for i in steps {
            let hole = isHole(Double(i) * step)
            if hole, start == nil { start = i }
            if !hole, let s = start { runs.append(s...(i - 1)); start = nil }
        }
        if let s = start { runs.append(s...steps.upperBound) }
        func gap(_ r: ClosedRange<Int>) -> Double {
            let lo = Double(r.lowerBound) * step, hi = Double(r.upperBound) * step
            return near < lo ? lo - near : near > hi ? near - hi : 0
        }
        guard let best = runs.min(by: { gap($0) < gap($1) }) else { return nil }
        return (Double(best.lowerBound) * step)...(Double(best.upperBound) * step)
    }
}

// MARK: - Data

/// Everything the report reads from one analysis folder, plus the athlete's other throws.
struct ThrowReportData {
    var insight: TrialInsights?
    var coach: CoachMetricsDocument?
    var replay: ReplayDocument?
    var pose: PoseDocument?
    var results: AnalysisResults?
    var kinematics: [[String: String]] = []
    var scale: FlightScale?
    var launchFit: LaunchFitSummary?
    /// Metric key → the same metric on this athlete's other analysed throws.
    var history: [String: [Double]] = [:]
    var analysisURL: URL?
    /// Why the saved analysis is out of date (`needs_reanalysis.json` reason); nil when current.
    var staleReason: String?
    var manifest: ManifestInfo?
    /// Where the bag landed, slid and ended (results.json → board_phase).
    var boardPhase: BoardPhase?
    /// This athlete's green zone and measured releases (from the athlete summary's dashboard).
    var personalZone: PersonalZone?
    var athleteReleases: [MeasuredRelease] = []
    var distanceNote: String?
    var lateralNote: String?

    // Derived once per load by `derive()`, never per replay frame.
    var timeline = EventTimeline(fps: 30, frames: [:])
    var jointAngles = JointAngleSeries(rows: [], releaseFrame: nil)
    var flight: FlightChartData?
    var targets: [String: ClosedRange<Double>] = [:]
    var allMetrics: [CoachMetricRow] = []

    /// Usable (not unreliable or unavailable, finite) value of a coach metric.
    func value(_ key: String) -> Double? { coach?.coach_metrics[key]?.usableValue }

    /// Fill the derived fields (hole windows, chart series, table rows) from the loaded documents.
    mutating func derive() {
        var frames = (coach?.event_frames ?? [:]).compactMapValues { $0 }
        for (key, event) in replay?.events ?? [:] where frames[key] == nil { frames[key] = event.frame }
        timeline = EventTimeline(fps: replay?.fps ?? results?.quality.frameRateFPS ?? 30, frames: frames)
        jointAngles = JointAngleSeries(rows: kinematics, releaseFrame: timeline.release)
        let physics = insight?.verdict?.physics
        flight = replay.flatMap {
            FlightChartData.make(replay: $0, scale: scale, releaseHeight: physics?.height_m ?? value("bag_release_height_m"),
                                 boardDistance: physics?.distance_m)
        }
        targets = [:]
        if let physics, let height = physics.height_m ?? value("bag_release_height_m") {
            let speed = physics.speed_m_s ?? value("bag_release_speed_m_s")
            let angle = physics.angle_deg ?? value("bag_release_angle_deg")
            let slide = personalZone?.slide_allowance_m ?? 0.45
            if let angle {
                targets["bag_release_speed_m_s"] = HoleWindow.speed(angle: angle, height: height, distance: physics.distance_m,
                                                                    near: speed ?? 8, slide: slide)
            }
            if let speed {
                targets["bag_release_angle_deg"] = HoleWindow.angle(speed: speed, height: height, distance: physics.distance_m,
                                                                    near: angle ?? 35, slide: slide)
            }
        }
        if let metrics = coach?.coach_metrics {
            allMetrics = coachMetricOrder.compactMap { metrics[$0] }
                + metrics.keys.filter { !coachMetricOrder.contains($0) }.sorted().compactMap { metrics[$0] }
        } else {
            allMetrics = []
        }
    }
}

/// Engine versions from the analysis folder's manifest.json (read loosely).
struct ManifestInfo: Equatable {
    var methodVersion: String?
    var packageVersion: String?
    var engineHash: String?
    var poseModelVersion: String?

    static func load(_ url: URL) -> ManifestInfo? {
        guard let data = try? Data(contentsOf: url),
              let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
        return ManifestInfo(methodVersion: root["method_version"] as? String, packageVersion: root["python_package_version"] as? String,
                            engineHash: root["engine_source_sha256"] as? String, poseModelVersion: root["pose_model_version"] as? String)
    }
}

/// Progress of an analysis of the throw on screen.
struct ReportProgress: Equatable {
    var stage: String
    var detail: String
    var fraction: Double
}

/// The bag's launch fit as written in results.json → bag.launch (read loosely; older files lack fields).
struct LaunchFitSummary: Equatable {
    var model: String?
    var method: String?
    var samples: Int?
    var windowSeconds: Double?
    var rmsePixels: Double?
    var status: String?

    static func load(results url: URL) -> LaunchFitSummary? {
        guard let data = try? Data(contentsOf: url),
              let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let launch = (root["bag"] as? [String: Any])?["launch"] as? [String: Any] else { return nil }
        let gravity = launch["gravity_constrained"] as? [String: Any]
        let primary = launch["primary_model"] as? String
        return LaunchFitSummary(
            model: primary, method: launch["fit_method"] as? String,
            samples: launch["sample_count"] as? Int, windowSeconds: launch["fit_window_seconds"] as? Double,
            rmsePixels: primary == "gravity_constrained_linear" ? (gravity?["fit_rmse_px"] as? Double) : (launch["fit_rmse_pixels"] as? Double),
            status: launch["status"] as? String)
    }
}

/// This athlete's headline metrics from every analysed throw, read once per athlete and reused until a
/// results.json changes.
@MainActor enum AthleteHistory {
    private struct Source: Sendable { var id: UUID; var url: URL }
    private static var cache: [UUID: (key: String, values: [UUID: [String: Double]])] = [:]

    /// Per throw: metric key → value (reliable or caution only).
    static func values(athleteID: UUID, store: ProjectStore) async -> [UUID: [String: Double]] {
        let sources = (store.project?.trials ?? []).filter { $0.athleteID == athleteID }.compactMap { trial in
            store.analysisURL(for: trial).map { Source(id: trial.id, url: $0.appendingPathComponent("results.json")) }
        }
        let key = sources.map { source in
            let date = (try? FileManager.default.attributesOfItem(atPath: source.url.path)[.modificationDate] as? Date) ?? .distantPast
            return "\(source.id)|\(date.timeIntervalSince1970)"
        }.joined(separator: ",")
        if let hit = cache[athleteID], hit.key == key { return hit.values }
        let keys = ThrowReportContent.headlineKeys.map(\.key)
        let values = await Task.detached(priority: .userInitiated) {
            var out: [UUID: [String: Double]] = [:]
            for source in sources {
                guard let document = CoachMetricsDocument.load(source.url) else { continue }
                var row: [String: Double] = [:]
                for key in keys {
                    if let v = document.coach_metrics[key]?.usableValue { row[key] = v }
                }
                out[source.id] = row
            }
            return out
        }.value
        cache[athleteID] = (key, values)
        return values
    }
}

/// What the page can ask its host to do.
struct ThrowReportActions {
    var canEdit = true
    var setScore: (ScoreCategory?) -> Void = { _ in }
    var reanalyze: () -> Void = {}
    /// Rebuild insights.json (verdict, consistency) from the saved results; no pose re-run.
    var refreshSummary: () -> Void = {}
    var fixTracking: () -> Void = {}
    var trim: () -> Void = {}
    var locateVideo: () -> Void = {}
    var export: () -> Void = {}
    var openReport: () -> Void = {}
}

// MARK: - Report (connected to the library)

/// One throw's report (detail column): loads the analysis, refreshes insights, hosts the toolbar and sheets.
struct ThrowReportView: View {
    @EnvironmentObject private var store: ProjectStore
    @EnvironmentObject private var analysis: AnalysisService
    let trial: Trial
    @StateObject private var data = TrialDataController()
    @State private var report = ThrowReportData()
    @State private var failure: String?
    @State private var refreshing = false
    @State private var history: [UUID: [String: Double]] = [:]
    /// The Fix Tracking sheet closed to re-analyze: its dismissal must not start a competing refresh.
    @State private var skipDismissRefresh = false
    @State private var replayFrame = 0
    @State private var seekRequest: Int?
    @State private var sheet: ReportSheet?
    @State private var confirmsDelete = false
    /// Insights could not be refreshed because the worker was busy: refresh when it is free.
    @State private var pendingRefresh = false
    /// insights.json predates the verdict and was rebuilt once in this view (never loops).
    @State private var triedVerdictRefresh = false
    @State private var loadedOnce = false

    private enum ReportSheet: String, Identifiable { case fixTracking, trim, edit; var id: String { rawValue } }

    var body: some View {
        ThrowReportContent(trial: trial, athleteName: athleteName, data: report,
                           videoURL: store.videoURL(for: trial), videoAvailable: store.videoState(for: trial).isAvailable,
                           canTrim: store.originalVideoURL(for: trial) != nil,
                           loading: refreshing && report.insight == nil, failure: failure, progress: progress,
                           currentFrame: $replayFrame, seekRequest: $seekRequest, actions: actions)
            .navigationTitle(trial.displayName)
            .toolbar { toolbar }
            // Keyed on this throw's analysis state, not on isRunning transitions: a batch ends one run and
            // starts the next in the same main-actor turn, so onChange(isRunning) never sees `false`.
            .task(id: reloadKey) { await refresh(); await loadHistory() }
            .onChange(of: analysis.isRunning) { _, running in
                guard !running else { return }
                let refreshNow = pendingRefresh
                pendingRefresh = false
                Task {
                    if refreshNow { await refresh() }
                    await loadHistory()
                }
            }
            .sheet(item: $sheet, onDismiss: {
                if skipDismissRefresh { skipDismissRefresh = false; return }
                if !analysis.isRunning { Task { await refresh() } }
            }) { sheet in
                switch sheet {
                case .fixTracking: FixTrackingSheet(trial: trial, data: data, reanalyze: { skipDismissRefresh = true; reanalyze() })
                case .trim: VideoPreparationView(trial: trial)
                case .edit: TrialEditForm(trial: trial)
                }
            }
            .confirmationDialog("Delete \(trial.displayName)?", isPresented: $confirmsDelete, titleVisibility: .visible) {
                Button("Delete", role: .destructive) { deleteThrow() }
                Button("Cancel", role: .cancel) {}
            } message: { Text("The video and its analysis move to the Trash.") }
    }

    private var busy: Bool { analysis.isRunning }

    /// Changes when this throw is (re)analysed, starts or stops being the throw the worker is analysing,
    /// or moves to another athlete.
    private var reloadKey: String {
        Self.reloadKey(trial: trial, analysingThis: analysis.activeTrialID == trial.id)
    }

    static func reloadKey(trial: Trial, analysingThis: Bool) -> String {
        "\(trial.id)|\(trial.athleteID)|\(trial.analysisRelativePath ?? "")|\(trial.analysisStatus)|\(analysingThis)"
    }

    /// Progress when the worker is analysing this throw (not while it only refreshes insights).
    private var progress: ReportProgress? {
        guard analysis.isRunning, analysis.activeTrialID == trial.id else { return nil }
        return ReportProgress(stage: analysis.stage, detail: analysis.detail, fraction: analysis.progress)
    }
    private var analyzed: Bool { trial.analysisRelativePath != nil }

    @ToolbarContentBuilder private var toolbar: some ToolbarContent {
        ToolbarItemGroup(placement: .primaryAction) {
            Button("Fix Tracking…", systemImage: "wrench.and.screwdriver") { sheet = .fixTracking }
                .help("Correct body landmarks, the bag track, release, first contact and events")
                .disabled(busy || !analyzed)
            Button("Re-analyze", systemImage: "arrow.clockwise", action: reanalyze)
                .help("Analyze this throw again with the saved corrections")
                .disabled(busy || !store.videoState(for: trial).isAvailable)
            Menu("More", systemImage: "ellipsis.circle") {
                Button("Trim / Crop…") { sheet = .trim }.disabled(store.originalVideoURL(for: trial) == nil)
                Button("Edit Throw…") { sheet = .edit }
                Button("Record Landing Spot…") { NotificationCenter.default.post(name: .addTrialOutcome, object: nil) }
                Divider()
                Button("Reveal Video") { store.revealVideo(for: trial) }
                Button("Locate / Relink Video…") { store.locateAndRelinkVideo(for: trial) }
                Button("Export Package…") { store.exportAnalysis(for: trial) }.disabled(!analyzed)
                Divider()
                Button("Delete Throw…", role: .destructive) { confirmsDelete = true }
            }
            .help("More actions for this throw")
            .disabled(busy)
        }
    }

    private var actions: ThrowReportActions {
        ThrowReportActions(
            canEdit: !busy,
            setScore: { score in
                guard !analysis.isRunning else { return }
                do { try store.setScore(score, for: trial) } catch { store.errorMessage = error.localizedDescription }
            },
            reanalyze: reanalyze,
            refreshSummary: { if !analysis.isRunning { Task { await refresh(force: true) } } },
            fixTracking: { if !analysis.isRunning { sheet = .fixTracking } },
            trim: { if !analysis.isRunning { sheet = .trim } },
            locateVideo: { store.locateAndRelinkVideo(for: trial) },
            export: { store.exportAnalysis(for: trial) },
            openReport: { if let url = store.analysisURL(for: trial)?.appendingPathComponent("report.html") { NSWorkspace.shared.open(url) } })
    }

    /// Metric key → values on this athlete's other throws.
    private func historyByMetric() -> [String: [Double]] {
        let others = history.filter { $0.key != trial.id }.map(\.value)
        var byMetric: [String: [Double]] = [:]
        for key in ThrowReportContent.headlineKeys.map(\.key) { byMetric[key] = others.compactMap { $0[key] } }
        return byMetric
    }

    private var athleteName: String {
        store.project?.athletes.first { $0.id == trial.athleteID }?.displayName ?? "Unknown athlete"
    }

    private func reanalyze() {
        guard !analysis.isRunning, store.videoState(for: trial).isAvailable else { return }
        Task { await analysis.analyze(trial: trial, store: store) }
    }

    private func deleteThrow() {
        guard !analysis.isRunning else { return }
        let athleteID = trial.athleteID
        do {
            try store.deleteTrial(trial)
            store.destination = .summary(athleteID)
        } catch { store.errorMessage = error.localizedDescription }
    }

    private func loadHistory() async {
        let values = await AthleteHistory.values(athleteID: trial.athleteID, store: store)
        if !Task.isCancelled { history = values; report.history = historyByMetric() }
        let releases = await MeasuredRelease.load(athleteID: trial.athleteID, store: store)
        if !Task.isCancelled { report.athleteReleases = releases }
    }

    /// Show the saved results at once; re-run the insights step (moved from the old Results page) only when
    /// insights.json is missing, older than its inputs or written before verdicts existed (or when `force`),
    /// then reload.
    private func refresh(force: Bool = false) async {
        guard trial.analysisRelativePath != nil else { report = ThrowReportData(); return }
        loadFiles()
        var needed = force || insightsNeedRefresh()
        if !needed, !triedVerdictRefresh, Self.lacksVerdict(report) {
            triedVerdictRefresh = true
            needed = true
        }
        guard needed else { return }
        guard !analysis.isRunning else {
            // A run of this throw reloads through `reloadKey` when it ends; anything else waits for the worker.
            if analysis.activeTrialID != trial.id { pendingRefresh = true }
            return
        }
        refreshing = true; failure = nil
        defer { refreshing = false }
        do {
            try await analysis.refreshInsights(trial: trial, store: store)
            guard store.selectedTrialID == trial.id else { return }
            loadFiles()
        } catch { failure = error.localizedDescription }
    }

    /// insights.json from before the verdict existed, for a current analysis that has coach metrics:
    /// rebuilding insights (seconds) adds the verdict without re-running pose tracking.
    static func lacksVerdict(_ data: ThrowReportData) -> Bool {
        data.insight != nil && data.insight?.verdict == nil && data.staleReason == nil
            && !(data.coach?.coach_metrics.isEmpty ?? true)
    }

    /// Insights depend on this throw's results, the library's outcomes (project.json) and the athlete's other throws.
    private func insightsNeedRefresh() -> Bool {
        guard let url = store.analysisURL(for: trial) else { return false }
        func modified(_ file: URL) -> Date? {
            try? FileManager.default.attributesOfItem(atPath: file.path)[.modificationDate] as? Date
        }
        guard let insights = modified(url.appendingPathComponent("insights.json")) else { return true }
        var inputs: [URL] = [url.appendingPathComponent("results.json")]
        if let root = store.projectURL { inputs.append(root.appendingPathComponent("project.json")) }
        for other in store.project?.trials ?? [] where other.athleteID == trial.athleteID && other.id != trial.id {
            if let otherURL = store.analysisURL(for: other) { inputs.append(otherURL.appendingPathComponent("results.json")) }
        }
        return inputs.contains { (modified($0) ?? .distantPast) > insights }
    }

    private func loadFiles() {
        guard let url = store.analysisURL(for: trial) else { return }
        var next = ThrowReportData()
        let insightsURL = url.appendingPathComponent("insights.json")
        if FileManager.default.fileExists(atPath: insightsURL.path) {
            do { next.insight = try JSONDecoder.projectDecoder.decode(TrialInsights.self, from: Data(contentsOf: insightsURL)) }
            catch { failure = "Could not read the throw summary: \(error.localizedDescription)" }
        }
        data.load(analysisURL: url)
        let resultsURL = url.appendingPathComponent("results.json")
        next.coach = CoachMetricsDocument.load(resultsURL)
        next.replay = ReplayDocument.load(url.appendingPathComponent("replay.json"))
        next.pose = data.pose
        next.results = data.results
        next.kinematics = data.kinematicRows
        next.scale = FlightScale.load(results: resultsURL)
        next.launchFit = LaunchFitSummary.load(results: resultsURL)
        next.manifest = ManifestInfo.load(url.appendingPathComponent("manifest.json"))
        next.analysisURL = url
        next.history = historyByMetric()
        next.staleReason = Self.staleReason(url.appendingPathComponent("needs_reanalysis.json"))
        next.boardPhase = BoardPhase.load(results: resultsURL)
        next.athleteReleases = report.athleteReleases
        if let root = store.projectURL,
           let dashboard = AthleteDashboard.load(root.appendingPathComponent("dashboards/\(trial.athleteID.uuidString).json")) {
            next.personalZone = dashboard.personal_zone
            next.distanceNote = dashboard.distance?.note
            next.lateralNote = dashboard.lateral?.note
        }
        next.derive()
        report = next
        if !loadedOnce {
            replayFrame = next.replay?.events["release"]?.frame ?? 0
            loadedOnce = true
        }
    }

    /// The reason in needs_reanalysis.json, or nil when the file is absent.
    static func staleReason(_ url: URL) -> String? {
        guard let data = try? Data(contentsOf: url) else { return nil }
        let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        return (object?["reason"] as? String) ?? "changed"
    }
}

// MARK: - Report page (pure: data in, actions out)

/// The throw report page (spec §3). Pure so it can be rendered offscreen for visual review.
struct ThrowReportContent: View {
    let trial: Trial
    let athleteName: String
    let data: ThrowReportData
    var videoURL: URL?
    var videoAvailable = true
    var canTrim = true
    var loading = false
    var failure: String?
    /// Set while this throw is being analysed: the page shows progress instead of results.
    var progress: ReportProgress?
    @Binding var currentFrame: Int
    @Binding var seekRequest: Int?
    var actions = ThrowReportActions()
    /// Scientific details start closed (spec §3.6); visual review opens them.
    @State var showsDetails = false

    /// The eight headline numbers (spec §1.3): three release, five body.
    static let releaseKeys: [(key: String, label: String, unit: String)] = [
        ("bag_release_speed_m_s", "Release speed", "m/s"), ("bag_release_angle_deg", "Release angle", "°"),
        ("bag_release_height_m", "Release height", "m")]
    static let bodyKeys: [(key: String, label: String, unit: String)] = [
        ("elbow_angle_deg_at_release", "Elbow angle at release", "°"), ("trunk_inclination_deg_at_release", "Trunk lean at release", "°"),
        ("wrist_peak_speed_arm_lengths_s", "Peak wrist speed", "arm lengths/s"), ("swing_backswing_angle_deg", "Backswing", "°"),
        ("swing_tempo_ratio", "Tempo", "back ÷ forward")]
    static var headlineKeys: [(key: String, label: String, unit: String)] { releaseKeys + bodyKeys }

    var body: some View {
        Page {
            header
            if let progress {
                // Analysing this throw: the saved numbers are about to be replaced, so only the video is shown.
                runningBanner(progress)
                if trial.analysisRelativePath != nil { replayCard }
            } else if trial.analysisRelativePath == nil {
                notAnalyzed
            } else {
                if let failure {
                    Label(failure, systemImage: "exclamationmark.triangle.fill").foregroundStyle(.orange).textSelection(.enabled)
                }
                if loading {
                    HStack(spacing: Space.s) { ProgressView().controlSize(.small); Text("Preparing this throw's report…").foregroundStyle(.secondary) }
                }
                if let reason = staleReason {
                    // Out of date: numbers from the old analysis would mislead, so only the video is shown.
                    staleBanner(reason)
                    replayCard
                } else {
                    VerdictCard(verdict: data.insight?.verdict,
                                frameFor: { data.coach?.coach_metrics[$0]?.frame }, seek: { seekRequest = $0 },
                                refresh: data.coach?.coach_metrics.isEmpty == false ? actions.refreshSummary : nil,
                                canRefresh: actions.canEdit && !loading)
                    if let phase = data.boardPhase {
                        WhereItEndedCard(phase: phase, recorded: trial.outcome?.scoreCategory, canEdit: actions.canEdit,
                                         accept: { actions.setScore($0) }, seek: { seekRequest = $0 })
                    }
                    replayCard
                    keyNumbers
                    ReportPlots(data: data, currentFrame: $currentFrame, seekRequest: $seekRequest)
                    if let zone = data.personalZone {
                        PersonalZoneCard(zone: zone, releases: data.athleteReleases, highlight: trial.id,
                                         distanceNote: data.distanceNote, lateralNote: data.lateralNote)
                    }
                    scientificDetails
                }
            }
        }
    }

    // MARK: Status banners

    private var staleReason: String? {
        data.staleReason ?? (data.insight?.needs_reanalysis == true ? "changed" : nil)
    }

    /// Plain-English reason for a stale analysis (codes written by the app, or a sentence).
    static func staleText(_ reason: String) -> String {
        switch reason {
        case "corrections_changed": "Body landmarks or events were corrected after this analysis."
        case "bag_seed_changed", "bag_corrections_changed": "The bag track was corrected after this analysis."
        case "flight_review_changed": "Release, first contact or the scale were reviewed after this analysis."
        case "analysis_in_progress": "The last analysis did not finish (it was cancelled or failed)."
        case "changed", "": "Tracking or settings changed after this analysis."
        default: reason
        }
    }

    private func staleBanner(_ reason: String) -> some View {
        Card {
            HStack(alignment: .center, spacing: Space.m) {
                Image(systemName: "arrow.triangle.2.circlepath").font(.title2).foregroundStyle(.orange)
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: Space.xs) {
                    Text("Analysis out of date").font(.title3.weight(.semibold))
                    Text("\(Self.staleText(reason)) Re-analyze to see the verdict, numbers and plots.")
                        .font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: Space.m)
                Button("Re-analyze", systemImage: "arrow.clockwise", action: actions.reanalyze)
                    .buttonStyle(.borderedProminent).disabled(!actions.canEdit || !videoAvailable)
            }
        }
    }

    private func runningBanner(_ progress: ReportProgress) -> some View {
        Card {
            VStack(alignment: .leading, spacing: Space.s) {
                HStack(spacing: Space.m) {
                    ProgressView().controlSize(.small)
                    Text("Analyzing this throw").font(.title3.weight(.semibold))
                    Spacer()
                    Text(progress.fraction, format: .percent.precision(.fractionLength(0))).monospacedDigit().foregroundStyle(.secondary)
                }
                ProgressView(value: progress.fraction)
                Text("\(progress.stage) · \(progress.detail)").font(.callout).foregroundStyle(.secondary).lineLimit(2)
            }
        }
    }

    // MARK: Header

    private var header: some View {
        HStack(alignment: .top, spacing: Space.l) {
            VStack(alignment: .leading, spacing: Space.xs) {
                Text(trial.displayName).font(.largeTitle.weight(.bold)).lineLimit(1)
                Text(subtitle).font(.title3).foregroundStyle(.secondary)
            }
            Spacer(minLength: Space.l)
            VStack(alignment: .trailing, spacing: Space.xs) {
                Text("Result").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                Picker("Result", selection: Binding(get: { trial.outcome?.scoreCategory }, set: { actions.setScore($0) })) {
                    Text("Hole · 3").tag(ScoreCategory?.some(.throughHole))
                    Text("Board · 1").tag(ScoreCategory?.some(.onBoard))
                    Text("Miss · 0").tag(ScoreCategory?.some(.offBoard))
                    Text("None").tag(ScoreCategory?.none)
                }
                .pickerStyle(.segmented).labelsHidden().fixedSize()
                .disabled(!actions.canEdit)
                .help("Record where this bag ended up; one click saves")
            }
        }
    }

    private var subtitle: String {
        var parts = [athleteName, trial.createdAt.formatted(.dateTime.day().month(.abbreviated).year()),
                     "\(trial.cameraView.label.lowercased()) view"]
        if let fps = data.replay?.fps ?? data.results?.quality.frameRateFPS { parts.append("\(number(fps, digits: 0)) fps") }
        return parts.joined(separator: " · ")
    }

    // MARK: Not analyzed

    private var notAnalyzed: some View {
        Card("Not analyzed yet", symbol: "waveform.path.ecg",
             subtitle: "Analyze the video to measure the release, the body and the bag's flight.") {
            if videoAvailable, let videoURL {
                UnanalyzedVideoPreview(url: videoURL).id(videoURL).frame(height: 380)
                    .clipShape(RoundedRectangle(cornerRadius: Radius.card))
                HStack {
                    Button("Analyze Throw", systemImage: "play.fill", action: actions.reanalyze).buttonStyle(.borderedProminent)
                    Button("Trim / Crop…", action: actions.trim).disabled(!canTrim)
                }
                .disabled(!actions.canEdit)
                Text("One throw per clip. Keep the athlete, the whole flight and the board in view.").font(.caption).foregroundStyle(.secondary)
            } else {
                Label("The recording for this throw could not be found.", systemImage: "exclamationmark.triangle.fill").foregroundStyle(.orange)
                Button("Locate Video…", action: actions.locateVideo).disabled(!actions.canEdit)
            }
        }
    }

    // MARK: Replay

    private var replayCard: some View {
        Card("Replay", symbol: "play.rectangle") {
            if let replay = data.replay {
                ThrowReplayView(videoURL: videoAvailable ? videoURL : nil, replay: replay, pose: data.pose, throwingSide: trial.throwingSide,
                                currentFrame: $currentFrame, seekRequest: $seekRequest)
                    .id(trial.id)
                if let note = replay.model_note {
                    Text("Dashed line: drag-free model fitted to the measured flight, shown as a reference only. \(note)")
                        .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                }
            } else {
                Label("The replay appears after this throw is re-analyzed with the current version.", systemImage: "play.slash")
                    .foregroundStyle(.secondary)
            }
        }
    }

    // MARK: Key numbers

    private func row(_ spec: (key: String, label: String, unit: String), group: String) -> CoachMetricRow {
        data.coach?.coach_metrics[spec.key] ?? .notMeasured(key: spec.key, label: spec.label, unit: spec.unit, group: group)
    }

    private func uncertainty(_ row: CoachMetricRow) -> MetricUncertainty? {
        let seKey = ["bag_release_speed_m_s": "bag_release_speed_se_m_s", "bag_release_angle_deg": "bag_release_angle_se_deg"][row.key ?? ""]
        if let seKey, let se = data.results?.summaries[seKey] ?? nil, se.isFinite, se > 0 { return MetricUncertainty(value: se, kind: .standardError) }
        if let floor = row.noise_floor, floor.isFinite, floor > 0 { return MetricUncertainty(value: floor, kind: .noiseFloor) }
        return nil
    }

    private func tiles(_ specs: [(key: String, label: String, unit: String)], group: String) -> some View {
        let rows = specs.map { row($0, group: group) }
        func tile(_ row: CoachMetricRow) -> some View {
            MetricTile(row: row, history: data.history[row.key ?? ""] ?? [], target: data.targets[row.key ?? ""],
                       uncertainty: uncertainty(row), seek: { seekRequest = $0 })
        }
        return ViewThatFits(in: .horizontal) {
            HStack(alignment: .top, spacing: Space.m) {
                ForEach(rows) { tile($0).frame(minWidth: 180) }
            }
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 180), spacing: Space.m, alignment: .top)], spacing: Space.m) {
                ForEach(rows) { tile($0) }
            }
        }
    }

    private var keyNumbers: some View {
        VStack(alignment: .leading, spacing: Space.xl) {
            Card("Release", symbol: "arrow.up.right", subtitle: "How the bag left the hand.") {
                tiles(Self.releaseKeys, group: "Release")
                Text(releaseCaption).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
            Card("Body", symbol: "figure.disc.sports", subtitle: "The arm and trunk around release.") {
                tiles(Self.bodyKeys, group: "Body")
                Text("Grey dots: this athlete's other throws; shaded box: their usual middle half; tall mark: this throw. Angles are measured in the camera's view.")
                    .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var releaseCaption: String {
        guard let physics = data.insight?.verdict?.physics else {
            return "Grey dots: this athlete's other throws. — means not measured or not reliable enough to show."
        }
        let board = physics.distance_source == "assumed"
            ? "the \(number(physics.distance_m, digits: 1)) m distance assumed in Settings" : "\(number(physics.distance_m, digits: 1)) m to the board"
        return "Green band: speeds (at this angle) or angles (at this speed) that would land in the hole zone, with this release height and \(board). Grey dots: this athlete's other throws."
    }

    // MARK: Scientific details

    private var scientificDetails: some View {
        Card {
            DisclosureGroup(isExpanded: $showsDetails) {
                VStack(alignment: .leading, spacing: Space.xl) {
                    metricsTable
                    qualitySection
                    launchSection
                    warningsSection
                    provenanceSection
                    HStack {
                        Button("Export Package…", systemImage: "square.and.arrow.up", action: actions.export).disabled(!actions.canEdit)
                        Button("Open Local Report", action: actions.openReport)
                        if let url = data.analysisURL {
                            Button("Inspect Saved Settings") { NSWorkspace.shared.open(url.appendingPathComponent("manifest.json")) }
                        }
                        Spacer()
                        Text("Projected 2D measurements from one side-view camera.").font(.caption).foregroundStyle(.secondary)
                    }
                }
                .padding(.top, Space.m)
            } label: {
                Label("Scientific details", systemImage: "flask").font(.title2.weight(.semibold))
            }
        }
    }

    private func section(_ title: String) -> some View {
        Text(title).font(.headline).accessibilityAddTraits(.isHeader)
    }

    @ViewBuilder private var metricsTable: some View {
        let rows = data.allMetrics
        VStack(alignment: .leading, spacing: Space.s) {
            section("All measurements")
            if rows.isEmpty {
                Text("No measurements were saved for this throw.").foregroundStyle(.secondary)
            } else {
                Table(rows) {
                    TableColumn("Metric") { row in Text(row.label).help(row.label) }.width(min: 150, ideal: 180)
                    TableColumn("Value") { row in
                        Text(formatValue(row.usableValue, unit: row.unit)).monospacedDigit()
                    }.width(min: 80, ideal: 100)
                    TableColumn("Uncertainty") { row in
                        Text(uncertainty(row).map { "± \(number($0.value, digits: $0.value >= 10 ? 0 : $0.value < 1 ? 2 : 1)) (\($0.kind == .standardError ? "SE" : "noise"))" } ?? "—")
                            .monospacedDigit().foregroundStyle(.secondary)
                    }.width(min: 90, ideal: 110)
                    TableColumn("Status") { row in
                        HStack(spacing: Space.xs) { ReliabilityGlyph(status: row.status); Text(row.statusText) }
                            .help(row.reasons.joined(separator: " "))
                    }.width(min: 120, ideal: 140)
                    TableColumn("Definition") { row in Text(row.definition).help(row.definition) }
                }
                .frame(height: min(CGFloat(rows.count) * 24 + 32, 460))
                Text("SE = standard error of the fit. Noise = the smallest change this measurement can resolve. — = not measured or not reliable enough to show.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    @ViewBuilder private var qualitySection: some View {
        VStack(alignment: .leading, spacing: Space.s) {
            section("Data quality")
            if let grades = data.replay?.grades {
                TrustStrip(grades: grades, showsTitle: false)
                Grid(alignment: .leading, horizontalSpacing: Space.l, verticalSpacing: Space.xs) {
                    ForEach(TrustStrip.stages, id: \.self) { stage in
                        GridRow {
                            Text(TrustStrip.title(stage)).font(.callout.weight(.medium))
                            Text(TrustStrip.rule(stage)).font(.callout).foregroundStyle(.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
            } else {
                Text("Quality grades appear after re-analysis with the current version.").foregroundStyle(.secondary)
            }
        }
    }

    @ViewBuilder private var launchSection: some View {
        VStack(alignment: .leading, spacing: Space.s) {
            section("Bag launch fit")
            let summaries = data.results?.summaries ?? [:]
            Grid(alignment: .leading, horizontalSpacing: Space.xl, verticalSpacing: Space.xs) {
                if let fit = data.launchFit {
                    GridRow { Text("Model"); Text(readable(fit.model) ?? "—") }
                    GridRow { Text("Method"); Text(readable(fit.method) ?? "—") }
                    GridRow { Text("Samples"); Text(fit.samples.map { "\($0) frames" + (fit.windowSeconds.map { " over \(number($0 * 1000, digits: 0)) ms" } ?? "") } ?? "—") }
                    GridRow { Text("Fit RMSE"); Text(fit.rmsePixels.map { "\(number($0, digits: 2)) px" } ?? "—").monospacedDigit() }
                    GridRow { Text("Status"); Text(readable(fit.status) ?? "—") }
                }
                GridRow { Text("Speed SE"); Text(formatSE(summaries["bag_release_speed_se_m_s"] ?? nil, unit: "m/s")).monospacedDigit() }
                GridRow { Text("Angle SE"); Text(formatSE(summaries["bag_release_angle_se_deg"] ?? nil, unit: "°")).monospacedDigit() }
                if let rmse = data.replay?.model_rmse_px {
                    GridRow { Text("Drag-free flight fit"); Text("RMSE \(number(rmse, digits: 1)) px over the whole flight").monospacedDigit() }
                }
                if let scale = data.scale {
                    GridRow { Text("Scale"); Text("\(number(scale.pixelsPerMeter, digits: 1)) px/m from the \(scale.source)").monospacedDigit() }
                }
                if let physics = data.insight?.verdict?.physics {
                    physicsRows(physics)
                }
            }
            .font(.callout)
            if let method = data.insight?.verdict?.method {
                Text(method).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    /// Rows of the launch-fit grid, so both share one label column.
    @ViewBuilder private func physicsRows(_ physics: Verdict.Physics) -> some View {
        Group {
            GridRow { Text("Physics check").font(.callout.weight(.semibold)).gridCellColumns(2).padding(.top, Space.s) }
            GridRow { Text("Board distance"); Text("\(number(physics.distance_m, digits: 2)) m (\(physics.distance_source.replacingOccurrences(of: "_", with: " ")))") }
            GridRow { Text("Predicted first contact"); Text("\(physics.landing.replacingOccurrences(of: "_", with: " ")) · \(physics.zone) zone") }
            if let from = physics.from_hole_m { GridRow { Text("From hole centre"); Text("\(from >= 0 ? "+" : "−")\(number(abs(from), digits: 2)) m along the board") } }
            if let v = physics.required_speed_m_s { GridRow { Text("Speed to hit the hole v*"); Text("\(number(v, digits: 2)) m/s") } }
            if let dv = physics.delta_speed_m_s { GridRow { Text("Δv = v − v*"); Text("\(dv >= 0 ? "+" : "−")\(number(abs(dv), digits: 2)) m/s") } }
            if let k = physics.sensitivity_m_per_m_s { GridRow { Text("∂x/∂v"); Text("\(number(k, digits: 2)) m per m/s") } }
        }
        .monospacedDigit()
    }

    private func formatSE(_ value: Double?, unit: String) -> String {
        guard let value else { return "—" }
        return "± \(number(value, digits: value < 1 ? 2 : 1)) \(unit)"
    }

    private func readable(_ raw: String?) -> String? {
        raw.map { $0.replacingOccurrences(of: "_", with: " ").capitalized(with: nil) }
    }

    @ViewBuilder private var warningsSection: some View {
        let warnings = Array(NSOrderedSet(array: (data.insight?.warnings ?? []) + (data.results?.warnings ?? []))) as? [String] ?? []
        if !warnings.isEmpty {
            VStack(alignment: .leading, spacing: Space.s) {
                section("Measurement notes")
                ForEach(warnings, id: \.self) { warning in
                    Label(warning, systemImage: "exclamationmark.triangle").font(.callout)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    @ViewBuilder private var provenanceSection: some View {
        VStack(alignment: .leading, spacing: Space.s) {
            section("Provenance")
            if let insight = data.insight {
                let q = insight.quality
                Grid(alignment: .leading, horizontalSpacing: Space.xl, verticalSpacing: Space.xs) {
                    GridRow { Text("Camera"); Text("\(insight.provenance.camera_view.capitalized) · \(q.resolutionPixels.width) × \(q.resolutionPixels.height) · \(number(q.frameRateFPS, digits: 2)) fps") }
                    GridRow { Text("Engine / model"); Text("\(insight.provenance.backend) · \(insight.provenance.model)") }
                    if let version = insight.provenance.sports2d_version { GridRow { Text("Sports2D version"); Text(version) } }
                    if let manifest = data.manifest {
                        if let method = manifest.methodVersion { GridRow { Text("Method version"); Text(method) } }
                        if let package = manifest.packageVersion { GridRow { Text("Engine package"); Text("cornhole-biomech \(package)") } }
                        if let hash = manifest.engineHash { GridRow { Text("Engine source"); Text(String(hash.prefix(12))).textSelection(.enabled) } }
                    }
                    if let id = insight.provenance.analysis_id { GridRow { Text("Analysis"); Text(id).textSelection(.enabled) } }
                    GridRow { Text("Usable frames"); Text("\(number(q.usableFramePercentage))%") }
                    GridRow { Text("Mean pose confidence"); Text(number(q.averagePoseConfidence, digits: 3)) }
                    GridRow { Text("Corrections / interpolation"); Text("\(q.manualCorrectionCount) manual points · \(q.interpolatedSampleCount) interpolated samples") }
                    GridRow { Text("Release confidence"); Text(number(q.releaseConfidence, digits: 3)) }
                    if let config = insight.provenance.configuration {
                        if let filter = config.filter {
                            GridRow { Text("Filter"); Text(filter.enabled ? "Butterworth · order \(filter.order) · \(number(filter.cutoff_hz)) Hz · zero phase" : "Filtering disabled") }
                        }
                        GridRow { Text("Confidence threshold"); Text(number(config.confidence_threshold, digits: 2)) }
                        GridRow { Text("Gap interpolation"); Text("At most \(config.max_interpolation_gap_frames ?? 0) consecutive frames") }
                    }
                }
                .font(.callout).monospacedDigit()
                if let hash = insight.provenance.model_hash {
                    Text("Model SHA-256: \(hash)").font(.caption.monospaced()).foregroundStyle(.secondary).textSelection(.enabled)
                }
                Text("Model confidence is not a calibrated position or angle error.").font(.caption).foregroundStyle(.secondary)
            } else if let method = data.manifest?.methodVersion {
                Text("Method version \(method)").font(.callout).monospacedDigit()
            } else {
                Text("Provenance appears once the throw summary has been prepared.").foregroundStyle(.secondary)
            }
        }
    }
}

/// The four plots. The only part of the page besides the replay that follows the playing frame, so
/// the rest of the report is not re-evaluated on every frame.
private struct ReportPlots: View {
    let data: ThrowReportData
    @Binding var currentFrame: Int
    @Binding var seekRequest: Int?

    var body: some View {
        let timeline = data.timeline
        let seek: (Int) -> Void = { seekRequest = $0 }
        ThrowPlots {
            if data.jointAngles.points.isEmpty {
                unavailable("Joint angles appear once the release is found.")
            } else {
                JointAngleChart(series: data.jointAngles, timeline: timeline, currentFrame: currentFrame, seek: seek)
            }
        } speed: {
            if let speed = data.coach?.wrist_speed_arm_lengths_s, timeline.release != nil {
                WristSpeedChart(speed: speed, fps: timeline.fps, events: timeline.frames, currentFrame: currentFrame, seek: seek)
            } else {
                unavailable("Wrist speed appears once the release is found.")
            }
        } flight: {
            if let flight = data.flight {
                FlightChart(data: flight, scaleSource: data.scale?.source,
                            distanceNote: data.insight?.verdict?.physics.map(VerdictCard.distanceNote))
            } else {
                unavailable("The bag's flight between release and first contact was not measured for this throw.")
            }
        } timing: {
            TimingStrip(timeline: timeline, currentFrame: currentFrame, seek: seek)
        }
    }

    private func unavailable(_ text: String) -> some View {
        Text(text).font(.callout).foregroundStyle(.secondary).frame(maxWidth: .infinity, minHeight: 120)
    }
}
