import AppKit
import SwiftUI

// MARK: - Hole windows

/// Release speeds / angles whose drag-free first contact lands in the hole window (`LaunchModel.zone() == .hole`),
/// holding the other release variables at this throw's values.
enum HoleWindow {
    /// Contiguous run of speeds (0.01 m/s steps, 1–15 m/s) that reach the hole at `angle`, `height`, `distance`;
    /// the run nearest `near` if there is more than one.
    static func speed(angle: Double, height: Double, distance: Double, near: Double) -> ClosedRange<Double>? {
        run(steps: 100...1500, step: 0.01, near: near) { v in
            LaunchModel(LaunchParameters(speed: v, angleDegrees: angle, releaseHeight: height, distanceToBoard: distance)).zone() == .hole
        }
    }

    /// Contiguous run of angles (0.1° steps, −10–80°) that reach the hole at `speed`, `height`, `distance`.
    static func angle(speed: Double, height: Double, distance: Double, near: Double) -> ClosedRange<Double>? {
        run(steps: -100...800, step: 0.1, near: near) { a in
            LaunchModel(LaunchParameters(speed: speed, angleDegrees: a, releaseHeight: height, distanceToBoard: distance)).zone() == .hole
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
                    if let metric = document.coach_metrics[key], metric.status != "unreliable", let v = metric.value, v.isFinite { row[key] = v }
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
    @State private var insight: TrialInsights?
    @State private var failure: String?
    @State private var refreshing = false
    @State private var replay: ReplayDocument?
    @State private var coach: CoachMetricsDocument?
    @State private var scale: FlightScale?
    @State private var launchFit: LaunchFitSummary?
    @State private var history: [UUID: [String: Double]] = [:]
    @State private var replayFrame = 0
    @State private var seekRequest: Int?
    @State private var sheet: ReportSheet?
    @State private var confirmsDelete = false
    /// An analysis of this throw is running (started here or elsewhere): refresh when it ends.
    @State private var watchingRun = false
    /// Insights could not be refreshed because the worker was busy: refresh when it is free.
    @State private var pendingRefresh = false
    @State private var loadedOnce = false

    private enum ReportSheet: String, Identifiable { case fixTracking, trim, edit; var id: String { rawValue } }

    var body: some View {
        ThrowReportContent(trial: trial, athleteName: athleteName, data: reportData,
                           videoURL: store.videoURL(for: trial), videoAvailable: store.videoState(for: trial).isAvailable,
                           canTrim: store.originalVideoURL(for: trial) != nil,
                           loading: refreshing && insight == nil, failure: failure,
                           currentFrame: $replayFrame, seekRequest: $seekRequest, actions: actions)
            .navigationTitle(trial.displayName)
            .toolbar { toolbar }
            .task(id: trial.id) { await refresh() }
            .task(id: trial.athleteID) { await loadHistory() }
            .onChange(of: analysis.isRunning) { _, running in
                if running {
                    if analysis.activeTrialID == trial.id { watchingRun = true }
                } else if watchingRun || pendingRefresh {
                    watchingRun = false; pendingRefresh = false
                    Task { await refresh(); await loadHistory() }
                }
            }
            .sheet(item: $sheet, onDismiss: { if !analysis.isRunning { Task { await refresh() } } }) { sheet in
                switch sheet {
                case .fixTracking: FixTrackingSheet(trial: trial, data: data, reanalyze: reanalyze)
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
            fixTracking: { if !analysis.isRunning { sheet = .fixTracking } },
            trim: { if !analysis.isRunning { sheet = .trim } },
            locateVideo: { store.locateAndRelinkVideo(for: trial) },
            export: { store.exportAnalysis(for: trial) },
            openReport: { if let url = store.analysisURL(for: trial)?.appendingPathComponent("report.html") { NSWorkspace.shared.open(url) } })
    }

    private var reportData: ThrowReportData {
        let others = history.filter { $0.key != trial.id }.map(\.value)
        var byMetric: [String: [Double]] = [:]
        for key in ThrowReportContent.headlineKeys.map(\.key) { byMetric[key] = others.compactMap { $0[key] } }
        return ThrowReportData(insight: insight, coach: coach, replay: replay, pose: data.pose, results: data.results,
                               kinematics: data.kinematicRows, scale: scale, launchFit: launchFit, history: byMetric,
                               analysisURL: data.analysisURL)
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
        if !Task.isCancelled { history = values }
    }

    /// Show the saved results at once, then re-run the insights step (moved from the old Results page) and reload.
    private func refresh() async {
        guard trial.analysisRelativePath != nil else { insight = nil; return }
        loadFiles()
        guard !analysis.isRunning else { pendingRefresh = true; return }
        refreshing = true; failure = nil
        defer { refreshing = false }
        do {
            try await analysis.refreshInsights(trial: trial, store: store)
            guard store.selectedTrialID == trial.id else { return }
            loadFiles()
        } catch { failure = error.localizedDescription }
    }

    private func loadFiles() {
        guard let url = store.analysisURL(for: trial) else { return }
        let insightsURL = url.appendingPathComponent("insights.json")
        if FileManager.default.fileExists(atPath: insightsURL.path) {
            do { insight = try JSONDecoder.projectDecoder.decode(TrialInsights.self, from: Data(contentsOf: insightsURL)) }
            catch { insight = nil; failure = "Could not read the throw summary: \(error.localizedDescription)" }
        } else { insight = nil }
        data.load(analysisURL: url)
        replay = ReplayDocument.load(url.appendingPathComponent("replay.json"))
        coach = CoachMetricsDocument.load(url.appendingPathComponent("results.json"))
        scale = FlightScale.load(results: url.appendingPathComponent("results.json"))
        launchFit = LaunchFitSummary.load(results: url.appendingPathComponent("results.json"))
        if !loadedOnce {
            replayFrame = replay?.events["release"]?.frame ?? 0
            loadedOnce = true
        }
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
            if trial.analysisRelativePath == nil {
                notAnalyzed
            } else {
                if let failure {
                    Label(failure, systemImage: "exclamationmark.triangle.fill").foregroundStyle(.orange).textSelection(.enabled)
                }
                if loading {
                    HStack(spacing: Space.s) { ProgressView().controlSize(.small); Text("Preparing this throw's report…").foregroundStyle(.secondary) }
                }
                VerdictCard(verdict: data.insight?.verdict, stale: data.insight?.needs_reanalysis == true,
                            canReanalyze: actions.canEdit && videoAvailable, reanalyze: actions.reanalyze,
                            frameFor: { data.coach?.coach_metrics[$0]?.frame }, seek: { seekRequest = $0 })
                replayCard
                keyNumbers
                plots
                scientificDetails
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
                    .clipShape(RoundedRectangle(cornerRadius: 10))
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

    private func value(_ key: String) -> Double? {
        guard let row = data.coach?.coach_metrics[key], row.status != "unreliable", let v = row.value, v.isFinite else { return nil }
        return v
    }

    /// Hole window for speed (at this angle, height and board distance) or angle (at this speed).
    private func target(_ key: String) -> ClosedRange<Double>? {
        guard let physics = data.insight?.verdict?.physics else { return nil }
        let speed = physics.speed_m_s ?? value("bag_release_speed_m_s")
        let angle = physics.angle_deg ?? value("bag_release_angle_deg")
        guard let height = physics.height_m ?? value("bag_release_height_m") else { return nil }
        switch key {
        case "bag_release_speed_m_s":
            guard let angle else { return nil }
            return HoleWindow.speed(angle: angle, height: height, distance: physics.distance_m, near: speed ?? 8)
        case "bag_release_angle_deg":
            guard let speed else { return nil }
            return HoleWindow.angle(speed: speed, height: height, distance: physics.distance_m, near: angle ?? 35)
        default: return nil
        }
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
            MetricTile(row: row, history: data.history[row.key ?? ""] ?? [], target: target(row.key ?? ""),
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
        let board = physics.distance_source == "assumed" ? "the assumed regulation distance" : "\(number(physics.distance_m, digits: 1)) m to the board"
        return "Green band: speeds (at this angle) or angles (at this speed) that would land in the hole zone, with this release height and \(board). Grey dots: this athlete's other throws."
    }

    // MARK: Plots

    private var timeline: EventTimeline {
        var frames = (data.coach?.event_frames ?? [:]).compactMapValues { $0 }
        for (key, event) in data.replay?.events ?? [:] where frames[key] == nil { frames[key] = event.frame }
        return EventTimeline(fps: data.replay?.fps ?? data.results?.quality.frameRateFPS ?? 30, frames: frames)
    }

    private var plots: some View {
        let timeline = timeline
        let seek: (Int) -> Void = { seekRequest = $0 }
        let angles = JointAngleSeries(rows: data.kinematics, releaseFrame: timeline.release)
        let physics = data.insight?.verdict?.physics
        let flight = data.replay.flatMap {
            FlightChartData.make(replay: $0, scale: data.scale, releaseHeight: physics?.height_m ?? value("bag_release_height_m"),
                                 boardDistance: physics?.distance_m)
        }
        return ThrowPlots {
            if angles.points.isEmpty {
                unavailable("Joint angles appear once the release is found.")
            } else {
                JointAngleChart(series: angles, timeline: timeline, currentFrame: currentFrame, seek: seek)
            }
        } speed: {
            if let speed = data.coach?.wrist_speed_arm_lengths_s, timeline.release != nil {
                WristSpeedChart(speed: speed, fps: timeline.fps, events: timeline.frames, currentFrame: currentFrame, seek: seek)
            } else {
                unavailable("Wrist speed appears once the release is found.")
            }
        } flight: {
            if let flight {
                FlightChart(data: flight, scaleSource: data.scale?.source, distanceNote: physics.map(VerdictCard.distanceNote))
            } else {
                unavailable("The bag's flight was not measured for this throw.")
            }
        } timing: {
            TimingStrip(timeline: timeline, currentFrame: currentFrame, seek: seek)
        }
    }

    private func unavailable(_ text: String) -> some View {
        Text(text).font(.callout).foregroundStyle(.secondary).frame(maxWidth: .infinity, minHeight: 120)
    }

    // MARK: Scientific details

    private var allMetrics: [CoachMetricRow] {
        guard let metrics = data.coach?.coach_metrics else { return [] }
        let ordered = coachMetricOrder.compactMap { metrics[$0] }
        let rest = metrics.keys.filter { !coachMetricOrder.contains($0) }.sorted().compactMap { metrics[$0] }
        return ordered + rest
    }

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
        let rows = allMetrics
        VStack(alignment: .leading, spacing: Space.s) {
            section("All measurements")
            if rows.isEmpty {
                Text("No measurements were saved for this throw.").foregroundStyle(.secondary)
            } else {
                Table(rows) {
                    TableColumn("Metric") { row in Text(row.label).help(row.label) }.width(min: 150, ideal: 190)
                    TableColumn("Value") { row in
                        Text(row.status == "unreliable" ? "—" : formatValue(row.value, unit: row.unit)).monospacedDigit()
                    }.width(min: 80, ideal: 100)
                    TableColumn("Uncertainty") { row in
                        Text(uncertainty(row).map { "± \(number($0.value, digits: $0.value < 1 ? 2 : 1)) (\($0.kind == .standardError ? "SE" : "noise"))" } ?? "—")
                            .monospacedDigit().foregroundStyle(.secondary)
                    }.width(min: 90, ideal: 120)
                    TableColumn("Status") { row in
                        HStack(spacing: Space.xs) { ReliabilityGlyph(status: row.status); Text(row.statusText) }
                            .help(row.reasons.joined(separator: " "))
                    }.width(min: 120, ideal: 170)
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
                TrustStrip(grades: grades)
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
            }
            .font(.callout)
            if let physics = data.insight?.verdict?.physics {
                physicsGrid(physics)
            }
            if let method = data.insight?.verdict?.method {
                Text(method).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private func physicsGrid(_ physics: Verdict.Physics) -> some View {
        Grid(alignment: .leading, horizontalSpacing: Space.xl, verticalSpacing: Space.xs) {
            GridRow { Text("Physics check").font(.callout.weight(.medium)); Text("") }
            GridRow { Text("Board distance"); Text("\(number(physics.distance_m, digits: 2)) m (\(physics.distance_source.replacingOccurrences(of: "_", with: " ")))") }
            GridRow { Text("Predicted first contact"); Text("\(physics.landing.replacingOccurrences(of: "_", with: " ")) · \(physics.zone) zone") }
            if let from = physics.from_hole_m { GridRow { Text("From hole centre"); Text("\(from >= 0 ? "+" : "−")\(number(abs(from), digits: 2)) m along the board") } }
            if let v = physics.required_speed_m_s { GridRow { Text("Speed to hit the hole v*"); Text("\(number(v, digits: 2)) m/s") } }
            if let dv = physics.delta_speed_m_s { GridRow { Text("Δv = v − v*"); Text("\(dv >= 0 ? "+" : "−")\(number(abs(dv), digits: 2)) m/s") } }
            if let k = physics.sensitivity_m_per_m_s { GridRow { Text("∂x/∂v"); Text("\(number(k, digits: 2)) m per m/s") } }
        }
        .font(.callout).monospacedDigit()
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
            } else {
                Text("Provenance appears once the throw summary has been prepared.").foregroundStyle(.secondary)
            }
        }
    }
}
