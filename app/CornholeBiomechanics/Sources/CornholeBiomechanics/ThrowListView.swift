import SwiftUI

/// Middle column: a pinned Summary row, then the athlete's throws, oldest first. Two-camera throws are grouped by
/// take; each take starts with a selectable take row (points, in/on/off, needs-your-eye count) that opens the
/// Take screen. A folder of takes dropped on the list opens the import.
struct ThrowListView: View {
    @EnvironmentObject private var store: ProjectStore
    @EnvironmentObject private var analysis: AnalysisService
    @EnvironmentObject private var glances: ThrowGlanceStore
    let athleteID: UUID
    let beginImport: () -> Void
    var beginTakeImport: () -> Void = {}
    /// Open the take import with a dropped folder.
    var importFolder: (URL) -> Void = { _ in }
    @State private var summaries: [UUID: ThrowRowSummary] = [:]
    @State private var deleting: Trial?
    @State private var dropTargeted = false

    var body: some View {
        Group {
            if trials.isEmpty {
                ScrollView {
                    VStack(spacing: Space.l) {
                        EmptyState("No Throws Yet", symbol: "video.badge.plus",
                                   message: "Import this athlete's two-camera takes (Take_N_Front and Take_N_Side), or single side-view videos.",
                                   action: store.project == nil ? nil : ("Import Takes", beginTakeImport))
                        RecordingGuide().padding(.horizontal, Space.l)
                    }
                    .padding(.vertical, Space.xl)
                }
            } else {
                List(selection: $store.destination) {
                    Label {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Summary")
                            Text("All throws").font(.caption).foregroundStyle(.secondary)
                        }
                    } icon: { Image(systemName: "chart.bar.xaxis") }
                        .tag(Destination.summary(athleteID))
                    ForEach(groups, id: \.id) { group in
                        Section {
                            if let key = group.key {
                                TakeListRow(title: group.title, trials: group.trials,
                                            needsEye: glances.needsEye(group.trials).count,
                                            analysing: group.trials.contains { analysis.activeTrialID == $0.id && analysis.isRunning },
                                            waiting: group.trials.filter { analysis.queuePosition(of: $0.id) != nil }.count)
                                    .tag(Destination.take(key))
                            }
                            ForEach(group.trials) { trial in
                                ThrowRow(trial: trial, summary: summaries[trial.id],
                                         isAnalyzing: analysis.activeTrialID == trial.id && analysis.isRunning,
                                         isQueued: analysis.queuePosition(of: trial.id) != nil,
                                         needsEye: !glances.needsEye([trial]).isEmpty,
                                         videoMissing: !store.videoState(for: trial).isAvailable,
                                         canAnalyze: !analysis.isRunning && store.videoState(for: trial).isAvailable,
                                         analyze: { analyze(trial) })
                                    .tag(Destination.throwReport(trial.id))
                                    .contextMenu { menu(for: trial) }
                            }
                        } header: {
                            if group.key == nil { Text(group.title) }
                        }
                    }
                }
            }
        }
        .overlay {
            if dropTargeted {
                RoundedRectangle(cornerRadius: Radius.card).strokeBorder(Color.accentColor, lineWidth: 2).padding(4)
                    .allowsHitTesting(false)
            }
        }
        .dropDestination(for: URL.self) { urls, _ in
            guard store.project != nil, let url = urls.first else { return false }
            importFolder(TakeImportForm.folderURL(for: url))
            return true
        } isTargeted: { dropTargeted = $0 }
        .navigationSplitViewColumnWidth(min: 240, ideal: 270, max: 360)
        .navigationTitle(store.project?.athletes.first { $0.id == athleteID }?.displayName ?? "Throws")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Menu {
                    Button("Import Takes… (⇧⌘T)", action: beginTakeImport)
                    Button("Import Single Videos… (⇧⌘I)", action: beginImport)
                        .disabled(analysis.isRunning)
                } label: { Label("Import", systemImage: "plus") }
                    .help("Import throws; they are analysed automatically, one at a time")
                    .disabled(store.project == nil)
            }
        }
        .task(id: reloadKey) { await loadSummaries() }
        .confirmationDialog("Delete \(deleting?.displayName ?? "throw")?", isPresented: deletionPresented,
                            titleVisibility: .visible, presenting: deleting) { trial in
            Button("Delete", role: .destructive) {
                do { try store.deleteTrial(trial) } catch { store.errorMessage = error.localizedDescription }
            }
            Button("Cancel", role: .cancel) {}
        } message: { _ in Text("The video and its analysis move to the Trash.") }
    }

    private var trials: [Trial] {
        (store.project?.trials ?? []).filter { $0.athleteID == athleteID }.sorted { a, b in
            switch (a.takeNumber, b.takeNumber) {
            case let (x?, y?) where x != y: return x < y
            case let (x?, y?) where x == y: return (a.throwInTake ?? 0) < (b.throwInTake ?? 0)
            case (_?, nil): return true
            case (nil, _?): return false
            default: return a.createdAt < b.createdAt
            }
        }
    }

    /// Two-camera throws are grouped by take (its record, so two takes with one number stay apart); single videos
    /// stay together under "Throws".
    private var groups: [(id: String, key: TakeKey?, title: String, trials: [Trial])] {
        var result: [(id: String, key: TakeKey?, title: String, trials: [Trial])] = []
        for trial in trials {
            let key = trial.takeKey
            let id = key?.record ?? "single-videos"
            if let index = result.firstIndex(where: { $0.id == id }) {
                result[index].trials.append(trial)
            } else {
                result.append((id, key, trial.takeNumber.map { "Take \($0)" } ?? "Throws", [trial]))
            }
        }
        // Two takes with the same number (different days) carry their date.
        let numbers = result.map(\.title)
        for index in result.indices where result[index].key != nil && numbers.filter({ $0 == result[index].title }).count > 1 {
            if let date = result[index].trials.first?.recordingDate { result[index].title += " · \(date)" }
        }
        return result
    }

    /// Reload row summaries whenever an analysis finishes or a throw's analysis changes.
    private var reloadKey: String {
        trials.map { "\($0.id)|\($0.analysisRelativePath ?? "")|\($0.analysisStatus)" }.joined(separator: ",") + "|\(analysis.isRunning)"
    }

    @ViewBuilder private func menu(for trial: Trial) -> some View {
        Button(trial.analysisRelativePath == nil ? "Analyze" : "Re-analyze") { analyze(trial) }
            .disabled(analysis.isRunning || !store.videoState(for: trial).isAvailable)
        Button("Reveal Video") { store.revealVideo(for: trial) }
        Button("Locate / Relink Video…") { store.locateAndRelinkVideo(for: trial) }
            .disabled(analysis.isRunning)
        Divider()
        Button("Delete Throw…") { deleting = trial }
            .disabled(analysis.isRunning)
    }

    private func analyze(_ trial: Trial) {
        Task { await analysis.analyze(trial: trial, store: store) }
    }

    private var deletionPresented: Binding<Bool> {
        Binding(get: { deleting != nil }, set: { if !$0 { deleting = nil } })
    }

    private func loadSummaries() async {
        let folders = trials.compactMap { trial in store.analysisURL(for: trial).map { (trial.id, $0) } }
        let loaded = await Task.detached(priority: .userInitiated) {
            Dictionary(uniqueKeysWithValues: folders.map { ($0.0, ThrowRowSummary.load(analysisURL: $0.1)) })
        }.value
        summaries = loaded
    }
}

/// Release numbers and data-quality flag for one list row (results.json + replay.json).
struct ThrowRowSummary: Sendable {
    var speed: Double?
    var angle: Double?
    var hasQualityWarning = false
    /// Corrections or metadata changed after this analysis (needs_reanalysis.json present).
    var isStale = false

    static func load(analysisURL: URL) -> ThrowRowSummary {
        let metrics = CoachMetricsDocument.load(analysisURL.appendingPathComponent("results.json"))?.coach_metrics
        var summary = ThrowRowSummary(speed: metrics?["bag_release_speed_m_s"]?.value, angle: metrics?["bag_release_angle_deg"]?.value)
        struct Grades: Decodable { var grades: [String: String]? }
        if let data = try? Data(contentsOf: analysisURL.appendingPathComponent("replay.json")),
           let grades = try? JSONDecoder().decode(Grades.self, from: data).grades {
            summary.hasQualityWarning = grades.values.contains { $0 == "WARNING" || $0 == "POOR" }
        }
        summary.isStale = FileManager.default.fileExists(atPath: analysisURL.appendingPathComponent("needs_reanalysis.json").path)
        return summary
    }

    /// "7.8 m/s · 41°", or nil when neither value was measured.
    var releaseText: String? {
        guard speed != nil || angle != nil else { return nil }
        return [speed.map { "\(number($0)) m/s" }, angle.map { "\(number($0, digits: 0))°" }].compactMap { $0 }.joined(separator: " · ")
    }
}

private struct ThrowRow: View {
    let trial: Trial
    let summary: ThrowRowSummary?
    let isAnalyzing: Bool
    var isQueued = false
    var needsEye = false
    let videoMissing: Bool
    let canAnalyze: Bool
    let analyze: () -> Void

    private var isStale: Bool {
        summary?.isStale == true || trial.analysisStatus.localizedCaseInsensitiveContains("reanalyze")
    }

    var body: some View {
        HStack(spacing: Space.s) {
            VStack(alignment: .leading, spacing: 2) {
                Text(trial.displayName).lineLimit(1)
                Group {
                    if isAnalyzing {
                        Text("Analyzing…")
                    } else if isQueued {
                        Label("In the queue", systemImage: "clock")
                    } else if videoMissing {
                        Label("Missing video", systemImage: "questionmark.video").foregroundStyle(.orange)
                            .help("The video was moved or deleted. Use Locate / Relink Video… in the context menu.")
                    } else if trial.analysisRelativePath == nil {
                        Text(trial.analysisStatus)
                    } else if isStale {
                        Label("Re-analyze", systemImage: "arrow.triangle.2.circlepath").foregroundStyle(.orange)
                            .help("Corrections or throw details changed after this analysis.")
                    } else {
                        Text(summary?.releaseText ?? "—").monospacedDigit()
                    }
                }
                .font(.caption).foregroundStyle(.secondary)
            }
            Spacer(minLength: Space.xs)
            if isAnalyzing {
                ProgressView().controlSize(.small)
            } else if isQueued {
                EmptyView()
            } else if trial.analysisRelativePath == nil {
                Button("Analyze", action: analyze).controlSize(.small).disabled(!canAnalyze)
            } else if needsEye {
                Image(systemName: "eye").foregroundStyle(.orange)
                    .help("The cameras could not tell the result: choose In, On or Off in Needs Your Eye")
                    .accessibilityLabel("Needs your eye")
            } else if summary?.hasQualityWarning == true {
                Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(.orange)
                    .help("Some tracking quality checks were WARNING or POOR")
                    .accessibilityLabel("Tracking quality warning")
            }
            if trial.outcome?.isAutomatic == true, trial.outcome?.scoreCategory != nil {
                Text("auto").font(.caption2).foregroundStyle(.secondary)
                    .help("Recorded automatically from the front camera; a result you enter replaces it")
                    .accessibilityLabel("recorded automatically")
            }
            ResultBadge(score: trial.outcome?.scoreCategory)
        }
        .padding(.vertical, 2)
    }
}

/// The first row of a take: "Take 3", points and in/on/off, and how many bags need a person's eye. Selecting it
/// opens the Take screen.
private struct TakeListRow: View {
    let title: String
    let trials: [Trial]
    let needsEye: Int
    let analysing: Bool
    let waiting: Int

    var body: some View {
        let tally = TakeTally(trials)
        HStack(spacing: Space.s) {
            Image(systemName: "square.grid.2x2").foregroundStyle(.secondary).accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.headline)
                Group {
                    if analysing || waiting > 0 {
                        Text("Analysing · \(tally.analysed) of \(tally.throwsCount) done")
                    } else {
                        Text("\(tally.pointsText) · \(tally.countsText)").monospacedDigit()
                    }
                }
                .font(.caption).foregroundStyle(.secondary)
            }
            Spacer(minLength: Space.xs)
            if analysing { ProgressView().controlSize(.small) }
            if needsEye > 0 {
                Label("\(needsEye)", systemImage: "eye").font(.caption.weight(.semibold)).foregroundStyle(.orange)
                    .help("\(needsEye) bag\(needsEye == 1 ? "" : "s") need your eye")
                    .accessibilityLabel("\(needsEye) need your eye")
            }
        }
        .padding(.vertical, 3)
        .accessibilityElement(children: .combine)
    }
}

/// How to film a throw the app can measure (empty throw list and Help → Recording Guide).
struct RecordingGuide: View {
    var body: some View {
        VStack(alignment: .leading, spacing: Space.s) {
            Label("Record a useful side-view video", systemImage: "camera").font(.headline)
            Text("Fix the phone on a tripod. Film perpendicular to the throwing plane, without panning or changing zoom.")
            Text("Keep both shoulders, both hips and the whole throwing arm visible. Use clear lighting and 60 fps or higher when available.")
            Text("Keep the board in view and the same setup across the session. Different camera views cannot be treated as equivalent measurements.")
        }
        .font(.callout)
        .foregroundStyle(.secondary)
        .frame(maxWidth: 420, alignment: .leading)
    }
}

struct RecordingGuideSheet: View {
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        VStack(alignment: .leading, spacing: Space.l) {
            Text("Recording Guide").font(.title2.weight(.semibold))
            RecordingGuide()
            HStack { Spacer(); Button("Done") { dismiss() }.keyboardShortcut(.defaultAction) }
        }
        .padding(Space.xl)
        .frame(width: 480)
    }
}
