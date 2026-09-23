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
    @State private var feature = "bag_release_angle_deg"
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
                if insight.needs_reanalysis { Label("Corrections changed. Reanalyze before interpreting these measurements.", systemImage: "arrow.triangle.2.circlepath").foregroundStyle(.orange) }
                if !insight.needs_reanalysis {
                reviewReadiness
                if let summary = insight.performance?.summary { AthleteSummaryCard(summary: summary) }
                measurementStrip(insight)
                if let summary = insight.performance?.summary { ScoredVersusMissedPanel(summary: summary, currentTrialID: trial.id.uuidString) }
                FlightPathPanel(flight: data.results?.flight)
                board(insight, trial: trial)
                if let performance = insight.performance { landingGrouping(performance) }
                if !insight.warnings.isEmpty {
                    DisclosureGroup("\(insight.warnings.count) measurement warning\(insight.warnings.count == 1 ? "" : "s") — review before interpreting") {
                        ForEach(Array(insight.warnings.enumerated()), id: \.offset) { _, warning in Text(warning).font(.callout).frame(maxWidth: .infinity, alignment: .leading) }
                    }.foregroundStyle(.orange)
                }
                DisclosureGroup("Advanced · release components, body mechanics & research") {
                if let bag = data.results?.bag {
                    Divider()
                    bagLaunchPanel(bag, summaries: data.results?.summaries ?? [:])
                }
                Divider()
                if let normalized = data.normalized {
                    MovementWorkspace(normalized: normalized, comparison: insight.comparison_available == true ? data.comparison : nil,
                                      videoURL: store.videoURL(for: trial), events: data.events, fps: insight.quality.frameRateFPS, fraction: $fraction)
                }
                ArmMotionPanel(result: data.results?.armMotion, normalized: data.normalized, stale: insight.needs_reanalysis, fraction: $fraction)
                if !insight.differences.isEmpty { differences(insight) }
                }
                DisclosureGroup("Within-athlete movement repeatability") { consistency(insight.consistency) }
                Divider()
                if let relationships = insight.relationships {
                    DisclosureGroup("Explore movement and task performance") { relationshipPanel(relationships) }
                }
                qualityPanel(insight)
                HStack {
                    Button("Open local report") { openReport(trial) }
                    Button("Export research package…") { store.exportAnalysis(for: trial) }
                    Spacer()
                    Text("Projected 2D · pilot metrics").font(.caption).foregroundStyle(.secondary)
                }
                } else { Button("Review and reanalyze this throw") { store.selectedSection = .trials } }
            } else if !refreshing {
                ContentUnavailableView("Choose an analyzed throw", systemImage: "figure.disc.sports", description: Text("Import and analyze a video, review its tracking, then return here to see the movement and outcome together."))
                Button("Open Throws") { store.selectedSection = .trials }
            }
        }
        .task(id: store.selectedTrialID) { await refresh() }
        .sheet(isPresented: $showOutcome, onDismiss: { Task { await refresh() } }) { if let trial = store.selectedTrial { OutcomeEditor(trial: trial) } }
    }
    @ViewBuilder private var reviewReadiness: some View {
        let bag = data.results?.bag
        let releaseReviewed = data.results?.events["release"]?.isConfirmed == true
        if bag == nil || !releaseReviewed || bag?.review?.coversLaunchFit != true {
            ResearchCard(title: "Complete the throw review", symbol: "checklist") {
                Text("Body processing has finished. The remaining steps unlock bag and release measurements.").font(.callout)
                if bag == nil { Label("Select & track the thrown bag in the video.", systemImage: "1.circle") }
                if !releaseReviewed { Label("Pause at visible hand separation and confirm release in Flight & scale.", systemImage: "2.circle") }
                if bag?.review?.coversLaunchFit != true { Label("Inspect the bag marker frame by frame, then confirm the path through flight.", systemImage: "3.circle") }
                Text("Use Flight & scale to mark first contact when visible, then reanalyze after event edits. Record hole, board or miss with Add outcome. Unknown measurements stay blank.")
                    .font(.caption).foregroundStyle(.secondary)
                Button("Review video & bag") { store.selectedSection = .trials }.buttonStyle(.borderedProminent)
            }
        }
    }

    private var trialPicker: some View {
        Picker("Throw", selection: $store.selectedTrialID) {
            Text("Choose a throw…").tag(UUID?.none)
            ForEach(store.analyzedTrials.filter { store.selectedAthleteID == nil || $0.athleteID == store.selectedAthleteID }) { trial in Text(trial.displayName).tag(Optional(trial.id)) }
        }.frame(maxWidth: 520).disabled(analysis.isRunning)
    }
    private var actions: some View {
        HStack {
            Button("Review video") { store.selectedSection = .trials }.disabled(analysis.isRunning)
            Button("Refresh results") { Task { await refresh() } }.disabled(analysis.isRunning || store.selectedTrial?.analysisRelativePath == nil)
            Button("Compare…") { store.selectedSection = .compare }.disabled(store.selectedTrial?.analysisRelativePath == nil)
        }
    }
    private func measurementStrip(_ value: TrialInsights) -> some View {
        let summaries = data.results?.summaries ?? [:]
        let hasMeters = (summaries["bag_release_speed_m_s"] ?? nil) != nil
        let hasHeightMeters = (summaries["bag_release_height_m"] ?? nil) != nil
        return VStack(alignment: .leading, spacing: 10) {
            Text("This throw").font(.title2.weight(.semibold))
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 170), alignment: .leading)], spacing: 16) {
                resultNumber(title: "OUTCOME", value: value.outcome?.score_category.map(String.init) ?? "—", unit: "points",
                             explanation: value.outcome.map { $0.score_category == 3 ? "In the hole" : $0.score_category == 1 ? "On the board" : $0.score_category == 0 ? "Missed" : "Not recorded" } ?? "Not recorded", color: .primary)
                measurement("Release angle", key: "bag_release_angle_deg", unit: "°", digits: 0,
                            note: plusMinus(summaries["bag_release_angle_se_deg"] ?? nil, "°") ?? "Above horizontal, toward the board")
                measurement("Release speed", key: hasMeters ? "bag_release_speed_m_s" : "bag_release_speed_arm_lengths_s",
                            unit: hasMeters ? "m/s" : "arm lengths/s", digits: 2,
                            note: hasMeters ? (plusMinus(summaries["bag_release_speed_se_m_s"] ?? nil, " m/s") ?? "Scaled") : "No scale yet: add a meter stick or review the full flight")
                measurement("Release height", key: hasHeightMeters ? "bag_release_height_m" : "bag_release_height_arm_lengths",
                            unit: hasHeightMeters ? "m" : "arm lengths", digits: 2, note: "Bag above the lowest foot point")
                measurement("Elbow at release", key: "elbow_angle_deg_at_release", unit: "°", digits: 0, note: "180° = straight (as seen by the camera)")
            }
            Text("Release values need a confirmed release frame. — means not measured, never zero. Recorded at \(number(value.quality.frameRateFPS, digits: 0)) fps · \(trialViewLabel)")
                .font(.caption).foregroundStyle(.secondary)
        }.padding(.vertical, 8)
    }
    private func plusMinus(_ value: Double?, _ unit: String) -> String? {
        value.map { "± \(number($0, digits: unit == "°" ? 1 : 2))\(unit) tracking uncertainty" }
    }
    private var trialViewLabel: String { store.selectedTrial?.cameraView == .side ? "side view" : "non-side view: treat as exploratory" }
    private func measurement(_ title: String, key: String, unit: String, digits: Int, note: String) -> some View {
        let releaseConfirmed = data.results?.events["release"]?.isConfirmed == true
        let value: Double? = releaseConfirmed ? (data.results?.summaries[key] ?? nil) : nil
        return VStack(alignment: .leading, spacing: 6) {
            Text(title).font(.callout.weight(.medium))
            HStack(alignment: .firstTextBaseline) { Text(number(value, digits: digits)).font(.title).monospacedDigit(); Text(unit).font(.caption).foregroundStyle(.secondary) }
            Text(note).font(.caption).foregroundStyle(.secondary)
        }.frame(maxWidth: .infinity, alignment: .leading)
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
    private func bagLaunchPanel(_ bag: AnalysisResults.BagAnalysis, summaries: [String: Double?]) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Bag path & projected launch").font(.title2.weight(.semibold))
            Text("Derived from the reviewed bag centroid in the video plane. Velocity is reported in pixels/s and body-normalized arm lengths/s; m/s remains unavailable unless an explicit calibration is valid in the athlete’s release-motion plane.")
                .foregroundStyle(.secondary)
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 190))], spacing: 12) {
                bagMetric("Projected speed", summaries["bag_release_speed_arm_lengths_s"] ?? nil, "arm lengths/s", digits: 3)
                bagMetric("Projected launch angle", summaries["bag_release_angle_deg"] ?? nil, "°", digits: 1)
                bagMetric("Forward velocity", summaries["bag_release_forward_velocity_arm_lengths_s"] ?? nil, "arm lengths/s", digits: 3)
                bagMetric("Vertical velocity", summaries["bag_release_vertical_velocity_arm_lengths_s"] ?? nil, "arm lengths/s", digits: 3)
                bagMetric("Forward release position", summaries["bag_release_position_forward_arm_lengths"] ?? nil, "arm lengths", digits: 3)
                bagMetric("Vertical release position", summaries["bag_release_position_vertical_arm_lengths"] ?? nil, "arm lengths", digits: 3)
            }
            HStack {
                Text("Release frame: \(bag.launch.releaseFrame.map(String.init) ?? "unavailable")")
                Text("·")
                Text("effective coverage \(number(bag.effectiveTrackingCoveragePercent, digits: 1))%")
                Text("·")
                Text(bag.tracker.status.replacingOccurrences(of: "_", with: " ").capitalized)
            }.font(.caption).foregroundStyle(.secondary)
            if bag.launch.status != "estimated" {
                Label("Launch fit status: \(bag.launch.status.replacingOccurrences(of: "_", with: " ")). Review the track and post-release visibility before interpretation.", systemImage: "exclamationmark.triangle")
                    .font(.callout).foregroundStyle(.orange)
            }
        }
    }

    private func bagMetric(_ title: String, _ value: Double?, _ unit: String, digits: Int) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(title).font(.caption).foregroundStyle(.secondary)
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                Text(number(value, digits: digits)).font(.title3.weight(.semibold)).monospacedDigit()
                Text(unit).font(.caption).foregroundStyle(.secondary)
            }
        }.padding(12).frame(maxWidth: .infinity, alignment: .leading)
            .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 9))
    }
    private func board(_ value: TrialInsights, trial: Trial) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack { Text("First contact & final rest").font(.title2.weight(.semibold)); Spacer();Toggle("Overlay comparable throws", isOn: $allThrows).toggleStyle(.checkbox) }
            HStack(alignment: .top, spacing: 26) {
                BoardMap(trials: allThrows ? value.board_trials : value.board_trials.filter { $0.trial_id == trial.id.uuidString }, selectedID: trial.id.uuidString).frame(width: 235, height: 450)
                VStack(alignment: .leading, spacing: 16) {
                    Text(allThrows ? "\(value.board_trials.count) throws with outcomes" : "This throw").font(.headline)
                    if let error = value.outcome?.spatial_error {
                        LabeledContent("Target error", value: "\(number(error.radial_error_inches)) in")
                        LabeledContent("Lateral", value: "\(number(abs(error.lateral_error_inches))) in \(error.lateral_error_inches < 0 ? "left" : "right")")
                        LabeledContent("Longitudinal", value: "\(number(abs(error.longitudinal_error_inches))) in \(error.longitudinal_error_inches < 0 ? "short" : "long")")
                    } else { Text("Add an observed first-contact point and intended target to calculate landing error. Final rest is kept separate.").foregroundStyle(.secondary) }
                    Divider()
                    Label("Intended target", systemImage: "plus").foregroundStyle(.blue)
                    Label("First contact", systemImage: "circle.fill").foregroundStyle(.orange)
                    Label("Final resting point", systemImage: "square.fill").foregroundStyle(athleteInk)
                    Text("24 × 48 inch regulation board. Hole: 6 inch diameter, center 9 inches from the back. Locations are approximate manual observations.").font(.caption).foregroundStyle(.secondary)
                    Text("Target error uses first contact only. Final rest describes board interaction; an unseen landing stays unknown.").font(.caption).foregroundStyle(.secondary)
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
        }
    }
    private func relationshipPanel(_ value: RelationshipDocument) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Movement and task performance").font(.title2.weight(.semibold))
            Picker("Movement feature", selection: $feature) { ForEach(["bag_release_angle_deg", "bag_release_speed_arm_lengths_s", "elbow_angle_deg_at_release", "trunk_inclination_deg_at_release", "bag_release_position_forward_arm_lengths"].filter { value.relationships[$0] != nil }, id: \.self) { Text(metricLabel($0)).tag($0) } }.frame(maxWidth: 580)
            RelationshipScatter(rows: value.dataRows ?? [], feature: feature, outcome: value.outcomeVariable).frame(height: 250)
            if let estimate = value.relationships[feature] {
                HStack { Text("n = \(estimate.n)").monospacedDigit(); if let rho = estimate.spearmanRho { Text("Spearman ρ = \(number(rho, digits: 2))") }; if let ci = estimate.confidenceInterval, ci.count == 2 { Text("95% bootstrap CI: \(number(ci[0])) to \(number(ci[1]))") } }.font(.callout)
                Text(estimate.message).font(.callout).foregroundStyle(.secondary)
            }
            Text(value.outcomeVariable == "radial_error_inches" ? "Response: first-contact distance from intended target (in)." : "Response: observed 0/1/3 per-bag value. No landing distances are available.").font(.caption).foregroundStyle(.secondary)
            Text("At least eight complete pairs and variation in both variables are required. This within-athlete association does not establish causation.").font(.caption).foregroundStyle(.secondary)
        }
    }
    private func landingGrouping(_ value: PerformanceSummary) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("First-contact grouping: \(number(value.first_contact.rms_radius_inches)) in RMS radius around the group centre · n = \(value.first_contact.n) · \(value.first_contact.missing) without a board location")
                .font(.callout).monospacedDigit()
            Text(value.first_contact.note).font(.caption).foregroundStyle(.secondary)
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
