import SwiftUI

/// Middle column: a pinned Summary row, then the athlete's throws, oldest first.
struct ThrowListView: View {
    @EnvironmentObject private var store: ProjectStore
    @EnvironmentObject private var analysis: AnalysisService
    let athleteID: UUID
    let beginImport: () -> Void
    @State private var summaries: [UUID: ThrowRowSummary] = [:]
    @State private var deleting: Trial?

    var body: some View {
        Group {
            if trials.isEmpty {
                ScrollView {
                    VStack(spacing: Space.l) {
                        EmptyState("No Throws Yet", symbol: "video.badge.plus",
                                   message: "Import side-view videos of this athlete's throws.",
                                   action: store.project == nil || analysis.isRunning ? nil : ("Import Videos", beginImport))
                        RecordingGuide().padding(.horizontal, Space.l)
                    }
                    .padding(.vertical, Space.xl)
                }
            } else {
                List(selection: $store.destination) {
                    Label("Summary", systemImage: "chart.bar.xaxis")
                        .tag(Destination.summary(athleteID))
                    Section("Throws") {
                        ForEach(trials) { trial in
                            ThrowRow(trial: trial, summary: summaries[trial.id],
                                     isAnalyzing: analysis.activeTrialID == trial.id && analysis.isRunning,
                                     analyze: { analyze(trial) })
                                .tag(Destination.throwReport(trial.id))
                                .contextMenu { menu(for: trial) }
                        }
                    }
                }
            }
        }
        .navigationSplitViewColumnWidth(min: 240, ideal: 270, max: 360)
        .navigationTitle(store.project?.athletes.first { $0.id == athleteID }?.displayName ?? "Throws")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button("Import Videos", systemImage: "plus", action: beginImport)
                    .help("Import throw videos (⇧⌘I)")
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
        (store.project?.trials ?? []).filter { $0.athleteID == athleteID }.sorted { $0.createdAt < $1.createdAt }
    }

    /// Reload row summaries whenever an analysis finishes or a throw's analysis changes.
    private var reloadKey: String {
        trials.map { "\($0.id)|\($0.analysisRelativePath ?? "")|\($0.analysisStatus)" }.joined(separator: ",") + "|\(analysis.isRunning)"
    }

    @ViewBuilder private func menu(for trial: Trial) -> some View {
        Button(trial.analysisRelativePath == nil ? "Analyze" : "Re-analyze") { analyze(trial) }
            .disabled(analysis.isRunning || !store.videoState(for: trial).isAvailable)
        Button("Reveal Video") { store.revealVideo(for: trial) }
        Divider()
        Button("Delete Throw…") { deleting = trial }
            .disabled(analysis.activeTrialID == trial.id && analysis.isRunning)
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

    static func load(analysisURL: URL) -> ThrowRowSummary {
        let metrics = CoachMetricsDocument.load(analysisURL.appendingPathComponent("results.json"))?.coach_metrics
        var summary = ThrowRowSummary(speed: metrics?["bag_release_speed_m_s"]?.value, angle: metrics?["bag_release_angle_deg"]?.value)
        struct Grades: Decodable { var grades: [String: String]? }
        if let data = try? Data(contentsOf: analysisURL.appendingPathComponent("replay.json")),
           let grades = try? JSONDecoder().decode(Grades.self, from: data).grades {
            summary.hasQualityWarning = grades.values.contains { $0 == "WARNING" || $0 == "POOR" }
        }
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
    let analyze: () -> Void

    var body: some View {
        HStack(spacing: Space.s) {
            VStack(alignment: .leading, spacing: 2) {
                Text(trial.displayName).lineLimit(1)
                Group {
                    if isAnalyzing {
                        Text("Analyzing…")
                    } else if trial.analysisRelativePath == nil {
                        Text(trial.analysisStatus)
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
                Button("Analyze", action: analyze).controlSize(.small)
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
