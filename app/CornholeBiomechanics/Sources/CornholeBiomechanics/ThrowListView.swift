import SwiftUI

/// Middle column: a pinned Summary row, then the athlete's throws, oldest first.
struct ThrowListView: View {
    @EnvironmentObject private var store: ProjectStore
    @EnvironmentObject private var analysis: AnalysisService
    let athleteID: UUID
    let beginImport: () -> Void
    var beginTakeImport: () -> Void = {}
    @State private var summaries: [UUID: ThrowRowSummary] = [:]
    @State private var deleting: Trial?

    var body: some View {
        Group {
            if trials.isEmpty {
                ScrollView {
                    VStack(spacing: Space.l) {
                        EmptyState("No Throws Yet", symbol: "video.badge.plus",
                                   message: "Import this athlete's two-camera takes (Take_N_Front and Take_N_Side), or single side-view videos.",
                                   action: store.project == nil || analysis.isRunning ? nil : ("Import Two-Camera Takes", beginTakeImport))
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
                    ForEach(groups, id: \.title) { group in
                        Section(group.title) {
                            ForEach(group.trials) { trial in
                                ThrowRow(trial: trial, summary: summaries[trial.id],
                                         isAnalyzing: analysis.activeTrialID == trial.id && analysis.isRunning,
                                         videoMissing: !store.videoState(for: trial).isAvailable,
                                         canAnalyze: !analysis.isRunning && store.videoState(for: trial).isAvailable,
                                         analyze: { analyze(trial) })
                                    .tag(Destination.throwReport(trial.id))
                                    .contextMenu { menu(for: trial) }
                            }
                        }
                    }
                }
            }
        }
        .navigationSplitViewColumnWidth(min: 240, ideal: 270, max: 360)
        .navigationTitle(store.project?.athletes.first { $0.id == athleteID }?.displayName ?? "Throws")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Menu {
                    Button("Import Two-Camera Takes… (⇧⌘T)", action: beginTakeImport)
                    Button("Import Single Videos… (⇧⌘I)", action: beginImport)
                } label: { Label("Import", systemImage: "plus") }
                    .help("Import throws")
                    .disabled(store.project == nil || analysis.isRunning)
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

    /// Two-camera throws are grouped by take; single videos stay together under "Throws".
    private var groups: [(title: String, trials: [Trial])] {
        var result: [(title: String, trials: [Trial])] = []
        for trial in trials {
            let title = trial.takeNumber.map { "Take \($0)" } ?? "Throws"
            if let last = result.indices.last, result[last].title == title { result[last].trials.append(trial) }
            else { result.append((title, [trial])) }
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
            } else if trial.analysisRelativePath == nil {
                Button("Analyze", action: analyze).controlSize(.small).disabled(!canAnalyze)
            } else if summary?.hasQualityWarning == true {
                Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(.orange)
                    .help("Some tracking quality checks were WARNING or POOR")
                    .accessibilityLabel("Tracking quality warning")
            }
            ResultBadge(score: trial.outcome?.scoreCategory)
        }
        .padding(.vertical, 2)
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
