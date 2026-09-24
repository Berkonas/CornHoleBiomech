import Charts
import SwiftUI

/// Coach-facing athlete overview (coaching.py → dashboards/<athlete>.json).
/// Order follows the coach's questions: performance → release → what differed →
/// evidence → data trust → the throws themselves.
struct AthleteDashboardView: View {
    @EnvironmentObject private var store: ProjectStore
    @EnvironmentObject private var analysis: AnalysisService
    @State private var dashboard: AthleteDashboard?
    @State private var failure: String?

    var body: some View {
        SectionContainer(title: "Coach Dashboard", subtitle: subtitle) {
            HStack {
                Picker("Athlete", selection: $store.selectedAthleteID) {
                    Text("Choose athlete").tag(UUID?.none)
                    ForEach(store.project?.athletes ?? []) { Text($0.displayName).tag(Optional($0.id)) }
                }.frame(maxWidth: 320)
                Button("Refresh") { Task { await refresh(force: true) } }
                    .disabled(analysis.isRunning || store.selectedAthleteID == nil)
                Spacer()
            }
            if let failure { Label(failure, systemImage: "exclamationmark.triangle").foregroundStyle(.orange) }
            if let dashboard {
                let trials = (store.project?.trials ?? []).filter { $0.athleteID == store.selectedAthleteID && $0.analysisRelativePath != nil }
                DashboardContent(dashboard: dashboard, trials: trials, open: open) { if let id = store.selectedTrialID { store.destination = .throwReport(id) } }
            } else if store.selectedAthleteID == nil {
                ContentUnavailableView("Choose an athlete", systemImage: "person.crop.circle",
                                       description: Text("The dashboard summarizes one athlete's analyzed throws."))
            } else if !analysis.isRunning {
                ContentUnavailableView("No dashboard yet", systemImage: "rectangle.3.group",
                                       description: Text("Analyze this athlete's throws, then press Refresh."))
            }
        }
        .task(id: store.selectedAthleteID) { await refresh(force: false) }
    }

    private var subtitle: String {
        "What the athlete scored, how they released the bag, what differed on better throws, and how far to trust it."
    }

    private func open(_ trialID: String) {
        guard let id = UUID(uuidString: trialID) else { return }
        store.destination = .throwReport(id)
    }
    private func refresh(force: Bool) async {
        guard let athleteID = store.selectedAthleteID, let root = store.projectURL else { dashboard = nil; return }
        let url = root.appendingPathComponent("dashboards/\(athleteID.uuidString).json")
        failure = nil
        if force || !FileManager.default.fileExists(atPath: url.path) {
            do { try await analysis.refreshDashboard(athleteID: athleteID, store: store) }
            catch { failure = error.localizedDescription }
        }
        dashboard = AthleteDashboard.load(url)
        if dashboard == nil && failure == nil && FileManager.default.fileExists(atPath: url.path) {
            failure = "The dashboard file could not be read. Press Refresh to rebuild it."
        }
    }
}

/// The dashboard itself, independent of loading (also rendered in visual QA tests).
struct DashboardContent: View {
    let dashboard: AthleteDashboard
    let trials: [Trial]
    let open: (String) -> Void
    let recordResults: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            headline(dashboard)
            performance(dashboard)
            priorities(dashboard)
            releaseProfile(dashboard)
            evidence(dashboard)
            trust(dashboard)
            if !trials.isEmpty { throwList }
        }
    }

    // MARK: sections
    private func headline(_ d: AthleteDashboard) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("\(d.athlete ?? "Athlete") · \(d.throws) analyzed throws · \(d.throws_with_outcome) with a recorded result")
                .font(.callout).foregroundStyle(.secondary)
            Text(d.headline).font(.title3.weight(.semibold)).fixedSize(horizontal: false, vertical: true)
        }
        .padding(16).frame(maxWidth: .infinity, alignment: .leading)
        .background(athleteInk.opacity(0.09), in: RoundedRectangle(cornerRadius: 12))
    }

    private func performance(_ d: AthleteDashboard) -> some View {
        card("How did the athlete perform?", "target") {
            if d.throws_with_outcome == 0 {
                Label("No results recorded yet. Open each throw and click Hole, Board or Miss (one click per throw).", systemImage: "hand.tap")
                    .foregroundStyle(.secondary)
                Button("Record results in Throw Replay") { recordResults() }
            } else {
                let p = d.performance
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 140), alignment: .leading)], spacing: 14) {
                    stat("Points per bag", number(p.sports?.points_per_bag, digits: 2), "PPR \(number(p.sports?.ppr, digits: 1)) (4 bags)")
                    stat("In the hole", percent(p.sports?.in_percent), "3 points")
                    stat("On the board", percent(p.sports?.on_percent), "1 point")
                    stat("Missed", percent(p.sports?.off_percent), "0 points")
                    stat("Landing grouping", p.landing_dispersion?.rms_radius_inches.map { "\(number($0, digits: 1)) in" } ?? "—",
                         "RMS radius of first contacts")
                    stat("Target error", p.mean_target_error_inches.map { "\(number($0, digits: 1)) in" } ?? "—",
                         "Mean first-contact distance from the aim point")
                }
            }
        }
    }

    private func priorities(_ d: AthleteDashboard) -> some View {
        card("What should the coach look at?", "lightbulb") {
            if d.priorities.isEmpty {
                Text(d.throws_with_outcome < 10
                     ? "No coaching priority yet. A priority needs at least 5 scored throws and 5 misses, a difference larger than measurement noise, a repeatable effect and reliable measurements."
                     : "No release or movement feature passed all five checks for a coaching priority. Misses may come from aim or bag behaviour after landing.")
                    .foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
            ForEach(Array(d.priorities.enumerated()), id: \.element.id) { index, p in
                HStack(alignment: .top, spacing: 12) {
                    Text("\(index + 1)").font(.title2.weight(.bold)).foregroundStyle(athleteInk).frame(width: 24)
                    VStack(alignment: .leading, spacing: 6) {
                        Text(p.label).font(.headline)
                        if let sentence = p.sentence { Text(sentence).fixedSize(horizontal: false, vertical: true) }
                        if let practice = p.practice { Label("Practise \(practice).", systemImage: "figure.run").font(.callout) }
                        if let examples = p.example_throws, !examples.isEmpty {
                            HStack {
                                Text("Typical scored throws:").font(.caption).foregroundStyle(.secondary)
                                ForEach(examples, id: \.self) { example in
                                    Button(example.label) { open(example.trial_id) }.buttonStyle(.link).font(.caption)
                                }
                            }
                        }
                        checklist(p.checks)
                    }
                }
                .padding(12).frame(maxWidth: .infinity, alignment: .leading)
                .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 10))
            }
            if !d.observed_differences.isEmpty {
                DisclosureGroup("Observed differences, not yet advice (\(d.observed_differences.count))") {
                    ForEach(d.observed_differences) { p in
                        VStack(alignment: .leading, spacing: 3) {
                            Text(p.sentence ?? p.label).font(.callout)
                            if let why = p.why_not_a_priority, !why.isEmpty {
                                Text("Not a priority because it is not: \(why.joined(separator: ", ")).").font(.caption).foregroundStyle(.secondary)
                            }
                        }.padding(.vertical, 4)
                    }
                }
            }
            if d.compensation.status == "estimated" {
                Label(d.compensation.message, systemImage: "arrow.left.arrow.right").font(.callout)
                    .help("Model-based: drag-free landing distance with release speed paired at random across throws (Müller & Sternad 2004).")
            }
        }
    }

    private func checklist(_ checks: [String: Bool]) -> some View {
        let order = ["associated_with_outcome", "larger_than_measurement_uncertainty", "repeatable", "measured_reliably", "interpretable_and_modifiable"]
        return HStack(spacing: 10) {
            ForEach(order.filter { checks[$0] != nil }, id: \.self) { key in
                Label(key.replacingOccurrences(of: "_", with: " "), systemImage: checks[key] == true ? "checkmark.circle.fill" : "xmark.circle")
                    .font(.caption2).foregroundStyle(checks[key] == true ? .green : .secondary)
            }
        }
    }

    private func releaseProfile(_ d: AthleteDashboard) -> some View {
        card("Release and movement profile", "chart.dots.scatter") {
            Text("Typical value (median), the middle half of throws, and how consistent it is compared with measurement noise. Each dot is one throw: blue scored, orange missed, grey no result.")
                .font(.callout).foregroundStyle(.secondary)
            ForEach(d.release_profile) { row in
                HStack(alignment: .center, spacing: 14) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(row.label).font(.callout.weight(.medium))
                        Text("\(formatValue(row.median, unit: row.unit)) · middle half \(formatRange(row.q25, row.q75, unit: row.unit))")
                            .font(.caption).monospacedDigit().foregroundStyle(.secondary)
                    }.frame(width: 250, alignment: .leading)
                    Chart(row.values) { value in
                        PointMark(x: .value(row.label, value.value), y: .value("Throws", 0))
                            .foregroundStyle(value.score == nil ? Color.gray : value.score == 0 ? missInk : scoredInk)
                            .symbolSize(40)
                    }
                    .chartYAxis(.hidden).chartXAxis { AxisMarks(values: .automatic(desiredCount: 4)) }
                    .chartXScale(domain: stripDomain(row.values.map(\.value)))
                    .frame(height: 38)
                    consistencyBadge(row).frame(width: 170, alignment: .leading)
                }
                .padding(.vertical, 2)
                Divider()
            }
        }
    }

    private func consistencyBadge(_ row: AthleteDashboard.Profile) -> some View {
        let color: Color = row.consistency == "within measurement noise" ? .green : row.consistency == "variable" ? .orange : .secondary
        return VStack(alignment: .leading, spacing: 2) {
            Text(row.consistency.prefix(1).uppercased() + row.consistency.dropFirst()).font(.caption.weight(.semibold)).foregroundStyle(color)
            Text("SD \(formatValue(row.sd, unit: row.unit))\(row.cv_percent.map { " · CV \(number($0, digits: 0))%" } ?? "")")
                .font(.caption2).monospacedDigit().foregroundStyle(.secondary)
        }
        .help("Throw-to-throw SD compared with this metric's measurement noise floor (\(formatValue(row.noise_floor, unit: row.unit))). Within noise = as consistent as the camera can tell.")
    }

    private func evidence(_ d: AthleteDashboard) -> some View {
        card("Body → release → flight → outcome", "arrow.triangle.branch") {
            Text("Within-athlete links, tested as hypotheses (Spearman ρ with a bootstrap 95% CI, ≥ 8 throws). Supported means the CI excludes zero; it is still an association, not a cause.")
                .font(.callout).foregroundStyle(.secondary)
            ForEach(["Body → release", "Release → flight", "Release → outcome", "Body → outcome"], id: \.self) { stage in
                let links = d.evidence_chain.filter { $0.stage == stage }
                if !links.isEmpty {
                    Text(stage.uppercased()).font(.system(size: 10, weight: .semibold)).tracking(0.8).foregroundStyle(.secondary).padding(.top, 4)
                    ForEach(links) { link in
                        HStack {
                            Text(link.from_label).frame(width: 190, alignment: .leading)
                            Image(systemName: "arrow.right").foregroundStyle(.secondary)
                            Text(link.to_label).frame(width: 150, alignment: .leading)
                            if link.status == "estimated", let rho = link.rho {
                                Text("ρ = \(number(rho, digits: 2)) · n = \(link.n)").monospacedDigit().frame(width: 130, alignment: .leading)
                                StatusPill(text: link.supported ? "Supported" : "Not supported", color: link.supported ? .green : .secondary)
                            } else {
                                Text("n = \(link.n): not enough throws").foregroundStyle(.secondary)
                            }
                            Spacer()
                        }.font(.callout)
                    }
                }
            }
        }
    }

    private func trust(_ d: AthleteDashboard) -> some View {
        card("How trustworthy are the data?", "checkmark.shield") {
            HStack(alignment: .top, spacing: 26) {
                ForEach(["pose", "bag", "release", "calibration"], id: \.self) { stage in
                    let counts = d.trust.grades[stage] ?? [:]
                    VStack(alignment: .leading, spacing: 4) {
                        Text(["pose": "Body tracking", "bag": "Bag tracking", "release": "Release", "calibration": "Scale"][stage] ?? stage)
                            .font(.callout.weight(.medium))
                        HStack(spacing: 6) {
                            ForEach(["GOOD", "WARNING", "POOR"], id: \.self) { grade in
                                Text("\(counts[grade] ?? 0)").font(.caption.monospacedDigit().weight(.semibold))
                                    .padding(.horizontal, 6).padding(.vertical, 2)
                                    .background(gradeColor(grade).opacity(0.15), in: Capsule()).foregroundStyle(gradeColor(grade))
                                    .help("\(counts[grade] ?? 0) throws graded \(grade.lowercased())")
                            }
                        }
                    }
                }
                VStack(alignment: .leading, spacing: 4) {
                    Text("Metrics shown").font(.callout.weight(.medium))
                    Text(percent(d.trust.reliable_metric_share.map { 100 * $0 })).font(.title3.weight(.semibold))
                    Text("passed the reliability rules").font(.caption).foregroundStyle(.secondary)
                }
            }
            Text("Scale is WARNING when metres come only from the bag's fall under gravity; add a meter stick in the throwing plane for GOOD. See Light Validation in the docs for what has been checked by eye.")
                .font(.caption).foregroundStyle(.secondary)
        }
    }

    private var throwList: some View {
        card("Throws", "list.bullet") {
            ForEach(trials) { trial in
                Button { open(trial.id.uuidString) } label: {
                    HStack {
                        Text(trial.displayName)
                        Spacer()
                        Text(outcomeText(trial)).foregroundStyle(.secondary)
                        Image(systemName: "play.rectangle")
                    }.contentShape(Rectangle())
                }.buttonStyle(.plain).padding(.vertical, 3)
                Divider()
            }
        }
    }

    // MARK: helpers
    private func card<Content: View>(_ title: String, _ symbol: String, @ViewBuilder content: () -> Content) -> some View {
        ResearchCard(title: title, symbol: symbol) { content() }
    }
    private func stat(_ title: String, _ value: String, _ note: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title).font(.caption).foregroundStyle(.secondary)
            Text(value).font(.title.weight(.semibold)).monospacedDigit()
            Text(note).font(.caption2).foregroundStyle(.secondary)
        }
    }
    /// Data range plus padding so the dots use the strip's width.
    private func stripDomain(_ values: [Double]) -> ClosedRange<Double> {
        guard let low = values.min(), let high = values.max() else { return 0...1 }
        let pad = max((high - low) * 0.15, abs(high) * 0.02, 1e-3)
        return (low - pad)...(high + pad)
    }
    private func percent(_ value: Double?) -> String { value.map { "\(number($0, digits: 0))%" } ?? "—" }
    private func outcomeText(_ trial: Trial) -> String {
        switch trial.outcome?.scoreCategory {
        case .throughHole: "Hole · 3"
        case .onBoard: "Board · 1"
        case .offBoard: "Miss · 0"
        default: "No result"
        }
    }
}
