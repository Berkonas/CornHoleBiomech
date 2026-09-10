import SwiftUI

enum ComparisonMode: String, CaseIterable, Identifiable {
    case reference = "Reference set vs trial"
    case single = "Reference vs trial"
    case own = "Athlete vs own mean"
    case trial = "Trial vs trial"
    var id: String { rawValue }
    var folder: String { switch self { case .reference: "reference"; case .single: "single"; case .own: "own"; case .trial: "trial" } }
}

struct CompareView: View {
    @EnvironmentObject private var store: ProjectStore
    @EnvironmentObject private var analysis: AnalysisService
    @StateObject private var data = TrialDataController()
    @StateObject private var referenceData = TrialDataController()
    @State private var mode: ComparisonMode = .reference
    @State private var referenceID: UUID?
    @State private var fraction = 0.5
    @State private var failure: String?
    @State private var comparisonURL: URL?
    @State private var showReferenceVideo = false

    var body: some View {
        SectionContainer(title: "Compare Movement", subtitle: "Choose the question, then compare body-normalized movement on the same timeline.") {
            Picker("Comparison", selection: $mode) { ForEach(ComparisonMode.allCases) { Text($0.rawValue).tag($0) } }.pickerStyle(.segmented).disabled(analysis.isRunning)
            Picker("Athlete throw", selection: $store.selectedTrialID) {
                Text("Choose an analyzed throw…").tag(UUID?.none)
                ForEach(store.analyzedTrials) { Text(label($0)).tag(Optional($0.id)) }
            }.frame(maxWidth: 680).disabled(analysis.isRunning)
            if mode == .reference {
                Picker("Reference set", selection: $store.selectedReferenceSetID) {
                    Text("Choose a reference set…").tag(UUID?.none)
                    ForEach(store.project?.referenceSets ?? []) { set in
                        Text("\(set.name) · \(set.trialIDs.count) throw\(set.trialIDs.count == 1 ? "" : "s")")
                            .tag(Optional(set.id))
                    }
                }.frame(maxWidth: 680).disabled(analysis.isRunning)
            }
            if mode == .single || mode == .trial {
                Picker(mode == .single ? "Reference throw" : "Other throw", selection: $referenceID) {
                    Text("Choose comparison throw…").tag(UUID?.none)
                    ForEach(candidates) { Text(label($0)).tag(Optional($0.id)) }
                }.frame(maxWidth: 680).disabled(analysis.isRunning)
            }
            HStack {
                Button("Compare movement") { run() }.buttonStyle(.borderedProminent).disabled(references.isEmpty || data.normalized == nil || analysis.isRunning || (mode == .own && references.count < 4))
                Text("\(references.count) comparison throw\(references.count == 1 ? "" : "s")").font(.caption).foregroundStyle(.secondary)
                Spacer()
                if data.comparison != nil { Button("View throw results") { store.selectedSection = .results } }
            }
            if mode == .own { Text("The athlete’s mean excludes this throw. At least four other throws from the same session, camera view and throwing side, with at least 80% usable frames, are required. Processing settings must match.").font(.callout).foregroundStyle(.secondary) }
            if candidates.isEmpty { Label("No compatible comparison throws. Analyze another throw with the same camera view\(mode == .reference || mode == .single ? " and mark it in Reference" : "").", systemImage: "info.circle").foregroundStyle(.secondary) }
            if let failure { Label(failure, systemImage: "exclamationmark.triangle").foregroundStyle(.orange) }
            if let comparison = data.comparison, let normalized = data.normalized, let trial = store.selectedTrial {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(number(comparison.similarity.overall, digits: 0)).font(.system(size: 42, weight: .semibold)).foregroundStyle(athleteInk).monospacedDigit()
                    Text("/ 100").foregroundStyle(.secondary)
                    VStack(alignment: .leading) { Text(mode == .own ? "Similarity to athlete’s other throws" : mode == .trial ? "Similarity between these throws" : "Reference Similarity").font(.headline); Text("Pilot index · \(comparison.referenceTrialIDs.count) comparison throws").font(.caption).foregroundStyle(.secondary) }
                    Spacer()
                }.padding(.vertical, 6)
                Text("A high similarity does not imply a better outcome. Review both recordings and tracking quality before interpreting differences.").font(.callout).foregroundStyle(.secondary)
                if let q = data.results?.quality { Label("Tracking Quality: \(number(q.score, digits: 0))/100 · \(q.warnings.count) measurement warnings", systemImage: "viewfinder").foregroundStyle(q.warnings.isEmpty ? Color.secondary : Color.orange) }
                MovementWorkspace(normalized: normalized, comparison: comparison, videoURL: store.videoURL(for: trial), events: data.events, fps: data.pose?.fps ?? 30, fraction: $fraction)
                if let reference = references.first, let video = store.videoURL(for: reference) {
                    DisclosureGroup("Reference video\(references.count > 1 ? " — first member of the set, not the mean" : "")", isExpanded: $showReferenceVideo) {
                        CycleVideo(url: video, events: referenceData.events, fps: referenceData.pose?.fps ?? 30, fraction: $fraction, interactive: false).id(reference.id)
                        Text("This video shares the movement-cycle cursor with the athlete and plots above.").font(.caption).foregroundStyle(.secondary)
                    }
                }
                SimilarityBreakdown(similarity: comparison.similarity)
                DisclosureGroup("Raw errors and waveform agreement") {
                    ForEach(comparison.rawMetrics.keys.sorted(), id: \.self) { key in
                        LabeledContent(metricLabel(key), value: number(comparison.rawMetrics[key] ?? nil, digits: 3)).font(.callout)
                    }
                }
                if let comparisonURL { Button("Export comparison…") { store.exportFolder(at: comparisonURL, suggestedName: "Comparison-\(trial.shortID)") } }
            } else {
                Text("Choose a comparison and select Compare movement to see synchronized video, joint angles, aligned skeletons, and wrist paths.").foregroundStyle(.secondary).padding(.vertical, 25)
                NormalizationGuide().frame(maxWidth: 660, alignment: .leading)
            }
        }
        .onAppear { if store.selectedTrialID == nil { store.selectedTrialID = store.analyzedTrials.first?.id }; reset() }
        .onChange(of: store.selectedTrialID) { _, _ in reset() }
        .onChange(of: mode) { _, _ in reset() }
        .onChange(of: store.selectedReferenceSetID) { _, _ in
            if mode == .reference { reset() }
        }
        .onChange(of: referenceID) { _, _ in data.loadComparison(at: nil) }
    }
    private var candidates: [Trial] {
        guard let test = store.selectedTrial else { return [] }
        return store.analyzedTrials.filter { t in
            guard t.id != test.id && t.cameraView == test.cameraView else { return false }
            switch mode {
            case .reference: return store.selectedReferenceSet?.trialIDs.contains(t.id) == true
            case .single: return t.isReference
            case .own:
                guard t.athleteID == test.athleteID && t.throwingSide == test.throwingSide && t.sessionID == test.sessionID,
                      let directory = store.analysisURL(for: t),
                      !FileManager.default.fileExists(atPath: directory.appendingPathComponent("needs_reanalysis.json").path),
                      let bytes = try? Data(contentsOf: directory.appendingPathComponent("results.json")),
                      let result = try? JSONDecoder.projectDecoder.decode(AnalysisResults.self, from: bytes) else { return false }
                return result.quality.usableFramePercentage >= 80
            case .trial: return true
            }
        }
    }
    private var references: [Trial] { (mode == .single || mode == .trial) ? candidates.filter { $0.id == referenceID } : candidates }
    private func reset() {
        data.load(analysisURL: store.selectedTrial.flatMap(store.analysisURL(for:)))
        data.loadComparison(at: nil); failure = nil
        if !candidates.contains(where: { $0.id == referenceID }) { referenceID = candidates.first?.id }
    }
    private func run() {
        guard let trial = store.selectedTrial else { return }
        failure = nil
        Task {
            do {
                let url = try await analysis.compare(test: trial, references: references, store: store, mode: mode.folder)
                comparisonURL = url; data.loadComparison(at: url)
                referenceData.load(analysisURL: references.first.flatMap(store.analysisURL(for:)))
                fraction = (data.normalized?.eventTiming["release"] ?? nil) ?? 0.5
            } catch { failure = error.localizedDescription }
        }
    }
    private func label(_ trial: Trial) -> String { "\(store.project?.athletes.first { $0.id == trial.athleteID }?.displayName ?? "Athlete") · \(trial.originalFilename)" }
}
