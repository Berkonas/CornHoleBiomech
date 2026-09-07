import Charts
import SwiftUI

struct ResultsView: View {
    @EnvironmentObject private var store: ProjectStore
    @EnvironmentObject private var analysis: AnalysisService
    @StateObject private var data = TrialDataController()
    @State private var athleteID: UUID?
    @State private var selectedFeature = "elbow_angle_deg_at_release"
    @State private var errorMessage: String?

    var body: some View {
        SectionContainer(
            title: "Athlete Results",
            subtitle: "Keep similarity, personal consistency, and performance association separate."
        ) {
            HStack {
                Picker("Athlete", selection: $athleteID) {
                    Text("Choose athlete…").tag(UUID?.none)
                    ForEach(store.project?.athletes ?? []) { Text($0.displayName).tag(Optional($0.id)) }
                }.frame(maxWidth: 360)
                Button("Analyze Movement vs Outcome") { run() }.buttonStyle(.borderedProminent)
                    .disabled(athleteID == nil || analysis.isRunning)
                if let athleteID { Text("\(trials(for: athleteID).count) analyzed trials").font(.caption).foregroundStyle(.secondary) }
            }
            if let errorMessage { Label(errorMessage, systemImage: "xmark.circle").foregroundStyle(.red) }
            if let results = data.relationships {
                ResearchCard(title: "A. Reference similarity", symbol: "arrow.left.and.right") {
                    Text("Reference comparisons are trial-level outputs in Compare. Similarity is not silently folded into the movement–outcome estimate.")
                    Button("Open Compare") { store.selectedSection = .compare }
                }
                consistencySection(results)
                relationshipSection(results)
            } else {
                ResearchCard(title: "Three different questions", symbol: "square.split.2x2") {
                    Text("A. Reference similarity: how close was a trial to the coach-selected pattern?")
                    Text("B. Within-athlete consistency: how repeatable were this athlete’s measured features?")
                    Text("C. Performance relationship: which features were associated with better or worse outcomes?")
                    Text("At least \(store.project?.analysisSettings.minimumRelationshipTrials ?? 8) complete paired trials are required before a correlation is reported.").font(.caption).foregroundStyle(.secondary)
                }
            }
        }
        .onAppear { athleteID = athleteID ?? store.selectedAthleteID ?? store.project?.athletes.first?.id; loadExisting() }
        .onChange(of: athleteID) { _, _ in loadExisting() }
    }

    private func consistencySection(_ results: RelationshipDocument) -> some View {
        ResearchCard(title: "B. Within-athlete consistency", symbol: "repeat") {
            Text("Standard deviation and range summarize between-throw variability for this athlete; lower variability is not automatically better performance.").foregroundStyle(.secondary)
            ForEach(results.withinAthleteConsistency?.keys.sorted() ?? [], id: \.self) { key in
                if let value = results.withinAthleteConsistency?[key] {
                    HStack {
                        VStack(alignment: .leading) {
                            Text(readable(key)).font(.headline)
                            Text("n = \(value.n) · \(value.units)").font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer()
                        Text("Median \(format(value.median))")
                        Text("SD \(format(value.standardDeviation))")
                        Text("Range \(format(value.range))")
                    }.padding(.vertical, 5)
                }
            }
        }
    }

    private func relationshipSection(_ results: RelationshipDocument) -> some View {
        ResearchCard(title: "C. Movement versus performance", symbol: "chart.dots.scatter") {
            Picker("Movement feature", selection: $selectedFeature) {
                ForEach(results.relationships.keys.sorted(), id: \.self) { Text(readable($0)).tag($0) }
            }
            RelationshipScatter(rows: results.dataRows ?? [], feature: selectedFeature, outcome: results.outcomeVariable)
                .frame(height: 300)
            if let estimate = results.relationships[selectedFeature] {
                HStack {
                    StatusPill(text: estimate.status == "estimated" ? "Exploratory estimate" : "Insufficient data", color: estimate.status == "estimated" ? .blue : .orange)
                    Text("n = \(estimate.n)")
                    if let rho = estimate.spearmanRho { Text("Spearman ρ = \(rho.formatted(.number.precision(.fractionLength(3))))") }
                    if let ci = estimate.confidenceInterval, ci.count == 2 { Text("bootstrap 95% CI \(format(ci[0] ?? nil)) to \(format(ci[1] ?? nil))") }
                }
                Text(estimate.message).foregroundStyle(.secondary)
            }
            Text("This is a within-athlete observational association. It does not establish that changing the feature causes a better outcome. Sample size and approximate board-click precision limit interpretation.")
                .font(.caption).foregroundStyle(.secondary)
        }
    }

    private func run() {
        guard let athleteID else { return }
        errorMessage = nil
        Task {
            do { let url = try await analysis.relationships(for: athleteID, store: store); data.loadRelationships(at: url) }
            catch { errorMessage = error.localizedDescription }
        }
    }
    private func loadExisting() {
        guard let root = store.projectURL, let athleteID else { data.loadRelationships(at: nil); return }
        data.loadRelationships(at: root.appendingPathComponent("relationships/\(athleteID.uuidString)/relationships.json"))
    }
    private func trials(for id: UUID) -> [Trial] { store.analyzedTrials.filter { $0.athleteID == id } }
    private func readable(_ value: String) -> String { value.replacingOccurrences(of: "_", with: " ").replacingOccurrences(of: "deg", with: "").capitalized }
    private func format(_ value: Double?) -> String { value?.formatted(.number.precision(.fractionLength(2))) ?? "—" }
}

private struct ScatterSample: Identifiable {
    let id: String; let x: Double; let y: Double
}

private struct RelationshipScatter: View {
    let rows: [RelationshipDocument.DataRow]
    let feature: String
    let outcome: String
    var body: some View {
        if samples.isEmpty {
            ContentUnavailableView("No complete pairs", systemImage: "chart.dots.scatter", description: Text("Record outcomes and re-run this analysis."))
        } else {
            Chart(samples) { sample in
                PointMark(x: .value(featureLabel, sample.x), y: .value(outcomeLabel, sample.y))
                    .symbolSize(65).foregroundStyle(.blue)
            }
            .chartXAxisLabel(featureLabel)
            .chartYAxisLabel(outcomeLabel)
            .accessibilityLabel("Movement feature versus performance scatter plot with \(samples.count) observations")
        }
    }
    private var samples: [ScatterSample] {
        rows.compactMap { row in
            guard let x = featureValue(row), let y = outcome == "radial_error_inches" ? row.radialErrorInches : row.scoreCategory else { return nil }
            return ScatterSample(id: row.trialID, x: x, y: y)
        }
    }
    private func featureValue(_ row: RelationshipDocument.DataRow) -> Double? {
        switch feature {
        case "elbow_angle_deg_at_release": row.elbowAngleAtRelease
        case "elbow_angle_deg_rom": row.elbowROM
        case "trunk_inclination_deg_at_release": row.trunkInclinationAtRelease
        case "movement_duration_seconds": row.movementDuration
        case "release_timing_cycle": row.releaseTimingCycle
        case "reference_similarity_score": row.referenceSimilarityScore
        case "wrist_reference_deviation_arm_lengths": row.wristReferenceDeviation
        case "wrist_path_deviation_from_athlete_mean_arm_lengths": row.wristAthleteMeanDeviation
        default: nil
        }
    }
    private var featureLabel: String { feature.replacingOccurrences(of: "_", with: " ").capitalized }
    private var outcomeLabel: String { outcome == "radial_error_inches" ? "Approximate radial target error (in)" : "Cornhole score (0, 1, 3)" }
}
