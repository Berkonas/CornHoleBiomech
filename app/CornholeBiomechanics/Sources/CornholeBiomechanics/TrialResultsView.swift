import AppKit
import Charts
import SwiftUI

struct ResultsView: View {
    @EnvironmentObject private var store: ProjectStore
    @EnvironmentObject private var analysis: AnalysisService
    @StateObject private var data = TrialDataController()
    @State private var insight: TrialInsights?
    @State private var failure: String?
    @State private var fraction = 0.5
    @State private var refreshing = false
    @State private var feature = "elbow_angle_deg_at_release"
    @State private var allThrows = false
    @State private var showOutcome = false

    var body: some View {
        SectionContainer(title: "Throw Results", subtitle: "What happened, how the athlete moved, and how much to trust the measurement.") {
            ViewThatFits(in: .horizontal) {
                HStack { trialPicker; actions }
                VStack(alignment: .leading, spacing: 10) { trialPicker; actions }
            }
            if let failure { Label(failure, systemImage: "exclamationmark.triangle").foregroundStyle(.orange).textSelection(.enabled) }
            if refreshing { HStack { ProgressView().controlSize(.small); Text("Preparing the latest trial results…").foregroundStyle(.secondary) } }
            if let trial = store.selectedTrial, let insight, insight.trial_id == trial.id.uuidString {
                scoreStrip(insight)
                if insight.needs_reanalysis { Label("Corrections changed. Reanalyze before interpreting these measurements.", systemImage: "arrow.triangle.2.circlepath").foregroundStyle(.orange) }
                if !insight.warnings.isEmpty {
                    DisclosureGroup("\(insight.warnings.count) measurement warning\(insight.warnings.count == 1 ? "" : "s") — review before interpreting") {
                        ForEach(Array(insight.warnings.enumerated()), id: \.offset) { _, warning in Text(warning).font(.callout).frame(maxWidth: .infinity, alignment: .leading) }
                    }.foregroundStyle(.orange)
                }
                Text(insight.coach_summary).font(.body).textSelection(.enabled).padding(.vertical, 6)
                if !insight.differences.isEmpty { differences(insight) }
                Divider()
                if let normalized = data.normalized {
                    MovementWorkspace(normalized: normalized, comparison: insight.similarity == nil ? nil : data.comparison,
                                      videoURL: store.videoURL(for: trial), events: data.events, fps: insight.quality.frameRateFPS, fraction: $fraction)
                }
                Divider()
                board(insight, trial: trial)
                Divider()
                consistency(insight.consistency)
                Divider()
                if let relationships = insight.relationships { relationshipPanel(relationships) }
                qualityPanel(insight)
                if let similarity = insight.similarity { SimilarityBreakdown(similarity: similarity) }
                HStack {
                    Button("Open local report") { openReport(trial) }
                    Button("Export research package…") { store.exportAnalysis(for: trial) }
                    Spacer()
                    Text("Projected 2D · pilot metrics").font(.caption).foregroundStyle(.secondary)
                }
            } else if !refreshing {
                ContentUnavailableView("Choose an analyzed throw", systemImage: "figure.disc.sports", description: Text("Import and analyze a video, review its tracking, then return here to see the movement and outcome together."))
                Button("Open Trials") { store.selectedSection = .trials }
            }
        }
        .task(id: store.selectedTrialID) { await refresh() }
        .sheet(isPresented: $showOutcome, onDismiss: { Task { await refresh() } }) { if let trial = store.selectedTrial { OutcomeEditor(trial: trial) } }
    }
    private var trialPicker: some View {
        Picker("Throw", selection: $store.selectedTrialID) {
            Text("Choose a throw…").tag(UUID?.none)
            ForEach(store.analyzedTrials) { trial in Text("\(name(trial.athleteID)) · \(trial.originalFilename)").tag(Optional(trial.id)) }
        }.frame(maxWidth: 520).disabled(analysis.isRunning)
    }
    private var actions: some View {
        HStack {
            Button("Refresh results") { Task { await refresh() } }.disabled(analysis.isRunning || store.selectedTrial?.analysisRelativePath == nil)
            Button("Compare…") { store.selectedSection = .compare }.disabled(store.selectedTrial?.analysisRelativePath == nil)
        }
    }
    private func scoreStrip(_ value: TrialInsights) -> some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 165), alignment: .leading)], alignment: .leading, spacing: 18) {
            resultNumber(title: "ACL BAG RESULT", value: value.outcome.map { "\($0.score_category)" } ?? "—", unit: "points", explanation: value.outcome.map { $0.score_category == 3 ? "Bag through the hole" : $0.score_category == 1 ? "Bag on the board" : "Off board / foul" } ?? "Outcome not recorded", color: .primary)
            resultNumber(title: "REFERENCE SIMILARITY", value: number(value.similarity?.overall, digits: 0), unit: "/ 100", explanation: value.similarity == nil ? "Run a reference comparison" : "Resemblance to selected throws", color: athleteInk)
            resultNumber(title: "TRACKING QUALITY", value: number(value.quality.score, digits: 0), unit: "/ 100", explanation: value.quality.score == nil ? "Reanalyze to calculate" : "Raw tracking visibility and confidence", color: value.quality.score ?? 0 < 65 ? .orange : .primary)
            resultNumber(title: "ATHLETE CONSISTENCY", value: number(value.consistency.score, digits: 0), unit: "/ 100", explanation: value.consistency.score == nil ? "More trials needed · \(value.consistency.n)/\(value.consistency.minimum_trials)" : "Repeatability · \(value.consistency.n) throws", color: .primary)
        }.padding(.vertical, 16)
    }
    private func resultNumber(title: String, value: String, unit: String, explanation: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title).font(.system(size: 10, weight: .semibold)).tracking(0.7).foregroundStyle(.secondary)
            HStack(alignment: .firstTextBaseline, spacing: 5) { Text(value).font(.system(size: 40, weight: .semibold)).monospacedDigit().foregroundStyle(color); Text(unit).font(.callout).foregroundStyle(.secondary) }
            Text(explanation).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
    private func differences(_ value: TrialInsights) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Largest differences from reference").font(.headline)
            ForEach(Array(value.differences.prefix(3).enumerated()), id: \.element.id) { index, difference in
                Button {
                    fraction = difference.percent / 100
                } label: {
                    HStack(alignment: .top, spacing: 14) {
                        Text("\(index + 1)").font(.title3.monospacedDigit()).foregroundStyle(.secondary).frame(width: 18)
                        VStack(alignment: .leading, spacing: 3) {
                            Text(difference.name).font(.subheadline.weight(.semibold))
                            Text(difference.explanation).font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer(minLength: 12)
                        VStack(alignment: .trailing) { Text("\(number(difference.signed_difference ?? difference.amount, digits: difference.units == "degrees" ? 1 : 3)) \(difference.units == "degrees" ? "°" : "arm lengths")").monospacedDigit();Text("Seek to \(number(difference.percent, digits: 0))%").font(.caption).foregroundStyle(athleteInk) }
                    }.contentShape(Rectangle()).padding(.vertical, 5)
                }.buttonStyle(.plain)
            }
            Text("Ranked by peak difference relative to pilot tolerance; these are pointwise differences, not whole-curve errors.").font(.caption).foregroundStyle(.secondary)
        }
    }
    private func board(_ value: TrialInsights, trial: Trial) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack { Text("Where the bag landed").font(.title2.weight(.semibold)); Spacer();Toggle("Overlay comparable throws", isOn: $allThrows).toggleStyle(.checkbox) }
            HStack(alignment: .top, spacing: 26) {
                BoardMap(trials: allThrows ? value.board_trials : value.board_trials.filter { $0.trial_id == trial.id.uuidString }, selectedID: trial.id.uuidString).frame(width: 235, height: 450)
                VStack(alignment: .leading, spacing: 16) {
                    Text(allThrows ? "\(value.board_trials.count) throws with outcomes" : "This throw").font(.headline)
                    if let error = value.outcome?.spatial_error {
                        LabeledContent("Target error", value: "\(number(error.radial_error_inches)) in")
                        LabeledContent("Lateral", value: "\(number(abs(error.lateral_error_inches))) in \(error.lateral_error_inches < 0 ? "left" : "right")")
                        LabeledContent("Longitudinal", value: "\(number(abs(error.longitudinal_error_inches))) in \(error.longitudinal_error_inches < 0 ? "short" : "long")")
                    } else { Text("Add a target and a first-contact or final-rest point to calculate spatial error.").foregroundStyle(.secondary) }
                    Divider()
                    Label("Intended target", systemImage: "plus").foregroundStyle(.blue)
                    Label("First contact", systemImage: "circle.fill").foregroundStyle(.orange)
                    Label("Final resting point", systemImage: "square.fill").foregroundStyle(athleteInk)
                    Text("24 × 48 inch regulation board. Hole: 6 inch diameter, center 9 inches from the back. Locations are approximate manual observations.").font(.caption).foregroundStyle(.secondary)
                    Text("Target error uses first contact when recorded, otherwise final rest. The two locations remain distinct on the map.").font(.caption).foregroundStyle(.secondary)
                    Button(value.outcome == nil ? "Add outcome…" : "Edit outcome…") { showOutcome = true }.buttonStyle(.borderedProminent)
                }.frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }
    private func consistency(_ value: TrialInsights.Consistency) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("How repeatable is this athlete?").font(.title2.weight(.semibold))
            Text(value.message).foregroundStyle(.secondary)
            if let curve = value.curves["wrist_path_arm_lengths"], let mean = curve.mean.vectors {
                WristPathPlot(trial: mean, reference: nil, fraction: fraction, timing: data.normalized?.eventTiming ?? [:], traces: value.traces.map(\.wrist)).frame(height: 245)
                Text("Faint paths: individual throws. Strong path: this athlete’s mean. Only matching session, camera view, throwing side, model and processing settings with ≥80% usable frames enter the estimate.").font(.caption).foregroundStyle(.secondary)
            }
            if let elbow = value.curves["elbow_angle_deg"], let mean = elbow.mean.scalars {
                AngleComparisonPlot(tau: value.tau ?? [], trial: mean, reference: mean, sd: elbow.sd.scalars, field: "elbow_angle_deg", fraction: $fraction).frame(height: 200)
                Text("Athlete mean elbow curve with ±1 sample SD. The band describes variability, not confidence in the mean.").font(.caption).foregroundStyle(.secondary)
            }
            if let equation = value.equation {
                DisclosureGroup("How Consistency is calculated") {
                    Text(equation).font(.callout)
                    ForEach(value.components) { c in
                        LabeledContent(c.name, value: "SD \(number(c.variability, digits: 3)) \(c.units) · tolerance \(c.tolerance.formatted()) · weight \(c.weight.formatted()) · score \(number(c.score))")
                    }
                }
            }
        }
    }
    private func relationshipPanel(_ value: RelationshipDocument) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Movement and task performance").font(.title2.weight(.semibold))
            Picker("Movement feature", selection: $feature) { ForEach(value.relationships.keys.sorted(), id: \.self) { Text(metricLabel($0)).tag($0) } }.frame(maxWidth: 580)
            RelationshipScatter(rows: value.dataRows ?? [], feature: feature, outcome: value.outcomeVariable).frame(height: 250)
            if let estimate = value.relationships[feature] {
                HStack { Text("n = \(estimate.n)").monospacedDigit(); if let rho = estimate.spearmanRho { Text("Spearman ρ = \(number(rho, digits: 2))") }; if let ci = estimate.confidenceInterval, ci.count == 2 { Text("95% bootstrap CI: \(number(ci[0])) to \(number(ci[1]))") } }.font(.callout)
                Text(estimate.message).font(.callout).foregroundStyle(.secondary)
            }
            Text("At least eight complete pairs and variation in both variables are required. This within-athlete association does not establish causation.").font(.caption).foregroundStyle(.secondary)
        }
    }
    private func qualityPanel(_ value: TrialInsights) -> some View {
        DisclosureGroup("Measurement quality & analysis provenance") {
            let q = value.quality
            Grid(alignment: .leading, horizontalSpacing: 30, verticalSpacing: 8) {
                GridRow { Text("Camera"); Text("\(value.provenance.camera_view.capitalized) · \(q.resolutionPixels.width) × \(q.resolutionPixels.height) · \(number(q.frameRateFPS, digits: 2)) fps") }
                GridRow { Text("Engine / model"); Text("\(value.provenance.backend) · \(value.provenance.model)") }
                GridRow { Text("Sports2D version"); Text(value.provenance.sports2d_version ?? "Not used for this analysis") }
                GridRow { Text("Usable frames"); Text("\(number(q.usableFramePercentage))%") }
                GridRow { Text("Mean pose confidence"); Text(number(q.averagePoseConfidence, digits: 3)) }
                GridRow { Text("Corrections / interpolation"); Text("\(q.manualCorrectionCount) manual points · \(q.interpolatedSampleCount) interpolated samples") }
                GridRow { Text("Release confidence"); Text(number(q.releaseConfidence, digits: 3)) }
                GridRow { Text("Release visibility"); Text(q.releaseVisibility.map { "\(number($0 * 100))% within ±50 ms" } ?? "Unavailable") }
                if let config = value.provenance.configuration {
                    if let filter = config.filter { GridRow { Text("Saved filter"); Text(filter.enabled ? "Butterworth · order \(filter.order) · \(number(filter.cutoff_hz)) Hz · zero phase" : "Filtering disabled") } }
                    GridRow { Text("Confidence threshold"); Text(number(config.confidence_threshold, digits: 2)) }
                    GridRow { Text("Gap interpolation"); Text("At most \(config.max_interpolation_gap_frames ?? 0) consecutive frames") }
                    GridRow { Text("Normalized cycle"); Text("\(config.normalization_samples ?? 101) samples") }
                }
                ForEach(q.lowConfidenceLandmarkCounts.keys.sorted(), id: \.self) { key in GridRow { Text(key.replacingOccurrences(of: "_", with: " ")); Text("\(q.lowConfidenceLandmarkCounts[key] ?? 0) low-confidence samples") } }
            }.font(.callout).padding(.vertical, 8)
            Text(q.scoreNote ?? "Reanalyze to calculate the transparent tracking index.").font(.caption).foregroundStyle(.secondary)
            Text("Model confidence is not a calibrated position or angle error. Frame rate, camera geometry and corrections remain separate context.").font(.caption).foregroundStyle(.secondary)
            if let hash = value.provenance.model_hash { Text("Model SHA-256: \(hash)").font(.caption.monospaced()).textSelection(.enabled) }
            if let url = data.analysisURL {
                Button("Inspect saved settings") { NSWorkspace.shared.open(url.appendingPathComponent("manifest.json")) }
            }
        }
    }
    private func refresh() async {
        guard let trial = store.selectedTrial, trial.analysisRelativePath != nil else { insight = nil; return }
        guard !analysis.isRunning else { return }
        refreshing = true; failure = nil
        defer { refreshing = false }
        do {
            try await analysis.refreshInsights(trial: trial, store: store)
            guard store.selectedTrialID == trial.id, let url = store.analysisURL(for: trial) else { return }
            insight = try JSONDecoder.projectDecoder.decode(TrialInsights.self, from: Data(contentsOf: url.appendingPathComponent("insights.json")))
            data.load(analysisURL: url)
            data.loadComparison(at: store.projectURL?.appendingPathComponent("comparisons/\(trial.id.uuidString)"))
            fraction = (data.normalized?.eventTiming["release"] ?? nil) ?? 0.5
        } catch { failure = error.localizedDescription; insight = nil }
    }
    private func name(_ id: UUID) -> String { store.project?.athletes.first { $0.id == id }?.displayName ?? "Unknown athlete" }
    private func openReport(_ trial: Trial) { if let url = store.analysisURL(for: trial)?.appendingPathComponent("report.html") { NSWorkspace.shared.open(url) } }
}

struct SimilarityBreakdown: View {
    let similarity: ComparisonDocument.Similarity
    var body: some View {
        DisclosureGroup("Every Reference Similarity component") {
            Text("Score = 100 × max(0, 1 − error / tolerance). Total = weighted mean of available components. Pilot tolerances are not population norms.").font(.callout).foregroundStyle(.secondary)
            ForEach(similarity.components.keys.sorted(), id: \.self) { key in
                if let c = similarity.components[key] {
                    VStack(alignment: .leading, spacing: 5) {
                        HStack { Text(metricLabel(key)).font(.subheadline.weight(.medium)); Spacer(); Text("\(number(c.score)) / 100").monospacedDigit() }
                        ProgressView(value: c.score, total: 100).tint(athleteInk)
                        Text("Error \(number(c.rawError, digits: 3)) \(metricUnits(key)) · tolerance \(c.tolerance.formatted()) · weight \(c.weight.formatted())").font(.caption).foregroundStyle(.secondary)
                    }.padding(.vertical, 7)
                }
            }
            if !similarity.omittedComponents.isEmpty { Text("Unavailable components: \(similarity.omittedComponents.map(metricLabel).joined(separator: ", "))").font(.caption).foregroundStyle(.orange) }
        }
    }
}

struct BoardMap: View {
    let trials: [TrialInsights.BoardTrial]
    let selectedID: String
    var body: some View {
        GeometryReader { geometry in
            let scale = min((geometry.size.width - 30) / 24, (geometry.size.height - 30) / 48)
            let width = 24 * scale, height = 48 * scale
            ZStack {
                Rectangle().fill(Color(red: 0.88, green: 0.82, blue: 0.71)).overlay(Rectangle().stroke(Color(red: 0.16, green: 0.23, blue: 0.29), lineWidth: 2)).frame(width: width, height: height)
                Canvas { context, size in
                    let ox = (size.width - width) / 2, oy = (size.height - height) / 2
                    func location(_ p: BoardPoint) -> CGPoint { CGPoint(x: ox + p.xInches * scale, y: oy + (48 - p.yInches) * scale) }
                    let hole = location(BoardPoint(xInches: 12, yInches: 39))
                    context.fill(Path(ellipseIn: CGRect(x: hole.x-3*scale, y: hole.y-3*scale, width:6*scale,height:6*scale)), with: .color(Color(nsColor: .windowBackgroundColor)))
                    for t in trials {
                        for (kind, p) in [(0,t.outcome.intendedPoint),(1,t.outcome.firstContactPoint),(2,t.outcome.finalRestingPoint)] {
                            guard let p else { continue }; let xy = location(p); let r: CGFloat = t.trial_id == selectedID ? 5 : 3.5
                            let color: Color = kind == 0 ? .blue : kind == 1 ? .orange : athleteInk
                            var shape = Path()
                            if kind == 0 { shape.move(to:CGPoint(x:xy.x-r-2,y:xy.y));shape.addLine(to:CGPoint(x:xy.x+r+2,y:xy.y));shape.move(to:CGPoint(x:xy.x,y:xy.y-r-2));shape.addLine(to:CGPoint(x:xy.x,y:xy.y+r+2));context.stroke(shape,with:.color(color),lineWidth:2) }
                            else { shape = kind == 1 ? Path(ellipseIn:CGRect(x:xy.x-r,y:xy.y-r,width:2*r,height:2*r)) : Path(CGRect(x:xy.x-r,y:xy.y-r,width:2*r,height:2*r));context.fill(shape,with:.color(color.opacity(t.trial_id == selectedID ? 1 : 0.65)));context.stroke(shape,with:.color(.white),lineWidth:1) }
                        }
                    }
                    context.draw(Text("BACK").font(.system(size:9,weight:.semibold)).foregroundColor(.secondary),at:CGPoint(x:size.width/2,y:oy+9))
                    context.draw(Text("PITCHER END").font(.system(size:9,weight:.semibold)).foregroundColor(.secondary),at:CGPoint(x:size.width/2,y:oy+height-10))
                }
            }.frame(maxWidth:.infinity,maxHeight:.infinity)
        }.accessibilityLabel("Regulation cornhole board with \(trials.count) trial outcomes. Plus is target, circle is first contact, square is final rest.")
    }
}
