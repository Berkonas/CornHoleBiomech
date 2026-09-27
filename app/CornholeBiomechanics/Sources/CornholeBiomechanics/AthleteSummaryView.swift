import SwiftUI

// Athlete summary (spec §4): scoring, coach focus, throw comparison, consistency, release map and
// research details for one athlete's throws.

// MARK: - Summary (connected to the library)

/// One athlete's summary (detail column): loads rows, the dashboard and consistency; hosts Refresh.
struct AthleteSummaryView: View {
    @EnvironmentObject private var store: ProjectStore
    @EnvironmentObject private var analysis: AnalysisService
    let athleteID: UUID

    @State private var dashboard: AthleteDashboard?
    @State private var rows: [SummaryThrowRow] = []
    @State private var consistency: TrialInsights.Consistency?
    @State private var failure: String?
    @State private var loading = false
    /// Inputs key of the last automatic dashboard rebuild, so a failing rebuild is not retried in a loop.
    @State private var autoRefreshedKey: String?

    var body: some View {
        AthleteSummaryContent(dashboard: dashboard, rows: rows, consistency: consistency, open: open,
                              athleteName: athlete?.displayName ?? "Athlete", throwCount: trials.count,
                              resultCount: trials.filter { $0.outcome?.scoreCategory != nil }.count,
                              loading: loading, failure: failure, actions: actions)
            .navigationTitle(athlete?.displayName ?? "Summary")
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button("Refresh", systemImage: "arrow.clockwise") { Task { await load(forceDashboard: true) } }
                        .help("Rebuild this athlete's summary from the latest analyses and results")
                        .disabled(analysis.isRunning || analysedTrials.isEmpty)
                }
            }
            .task(id: reloadKey) { await load(forceDashboard: false) }
            .onChange(of: analysis.isRunning) { _, running in
                if !running { Task { await load(forceDashboard: false) } }
            }
    }

    private var athlete: Athlete? { store.project?.athletes.first { $0.id == athleteID } }

    /// The athlete's throws, oldest first.
    private var trials: [Trial] {
        (store.project?.trials ?? []).filter { $0.athleteID == athleteID }.sorted { $0.createdAt < $1.createdAt }
    }
    private var analysedTrials: [Trial] { trials.filter { $0.analysisRelativePath != nil } }

    /// Reload when a throw is added, removed, analysed or scored.
    private var reloadKey: String {
        trials.map { "\($0.id)|\($0.analysisRelativePath ?? "")|\($0.analysisStatus)|\($0.outcome?.scoreCategory?.rawValue ?? -1)" }
            .joined(separator: ",")
    }

    private var actions: SummaryActions {
        let busy = analysis.isRunning
        let unanalysed = trials.first { $0.analysisRelativePath == nil && store.videoState(for: $0).isAvailable }
        let unscored = trials.first { $0.outcome?.scoreCategory == nil }
        let newestAnalysed = analysedTrials.last
        return SummaryActions(
            canEdit: !busy,
            importVideos: { NotificationCenter.default.post(name: .importTrialVideo, object: nil) },
            analyzeFirst: unanalysed.map { trial in
                (label: "Analyze \(trial.displayName)", run: { analyze(trial) })
            },
            recordResults: unscored.map { trial in { open(trial.id) } },
            refresh: { Task { await load(forceDashboard: true) } },
            prepareConsistency: newestAnalysed.map { trial in
                {
                    Task {
                        do { try await analysis.refreshInsights(trial: trial, store: store) }
                        catch { failure = error.localizedDescription }
                        await load(forceDashboard: false)
                    }
                }
            })
    }

    private func open(_ id: UUID) { store.destination = .throwReport(id) }

    private func analyze(_ trial: Trial) {
        Task { await analysis.analyze(trial: trial, store: store) }
    }

    private func load(forceDashboard: Bool) async {
        let sources = trials.enumerated().compactMap { index, trial -> SummaryThrowRow.Source? in
            store.analysisURL(for: trial).map {
                SummaryThrowRow.Source(id: trial.id, number: index + 1, label: trial.displayName,
                                       score: trial.outcome?.scoreCategory, analysisURL: $0)
            }
        }
        loading = rows.isEmpty && !sources.isEmpty
        defer { loading = false }
        let loadedRows = await SummaryThrowRow.load(sources)
        let loadedConsistency = await Self.newestConsistency(sources.map(\.analysisURL))
        guard !Task.isCancelled else { return }
        rows = loadedRows
        consistency = loadedConsistency

        guard let root = store.projectURL else { dashboard = nil; return }
        let url = root.appendingPathComponent("dashboards/\(athleteID.uuidString).json")
        let inputs = [root.appendingPathComponent("project.json")] + sources.map { $0.analysisURL.appendingPathComponent("results.json") }
        let inputsKey = Self.modificationKey(inputs)
        let stale = Self.isOlder(url, than: inputs)
        let auto = stale && autoRefreshedKey != inputsKey
        if !sources.isEmpty, !analysis.isRunning, forceDashboard || auto {
            autoRefreshedKey = inputsKey
            failure = nil
            do { try await analysis.refreshDashboard(athleteID: athleteID, store: store) }
            catch { failure = "The summary could not be rebuilt: \(error.localizedDescription)" }
        }
        dashboard = AthleteDashboard.load(url)
        if dashboard == nil, failure == nil, FileManager.default.fileExists(atPath: url.path) {
            failure = "The summary file could not be read. Press Refresh to rebuild it."
        }
    }

    /// Consistency from the most recently written insights.json among the athlete's throws.
    static func newestConsistency(_ folders: [URL]) async -> TrialInsights.Consistency? {
        await Task.detached(priority: .userInitiated) {
            struct Wrapper: Decodable { var consistency: TrialInsights.Consistency }
            let newest = folders.map { $0.appendingPathComponent("insights.json") }
                .compactMap { url in modified(url).map { (url, $0) } }
                .max { $0.1 < $1.1 }?.0
            guard let newest, let data = try? Data(contentsOf: newest) else { return nil }
            return try? JSONDecoder.projectDecoder.decode(Wrapper.self, from: data).consistency
        }.value
    }

    nonisolated static func modified(_ url: URL) -> Date? {
        try? FileManager.default.attributesOfItem(atPath: url.path)[.modificationDate] as? Date
    }

    /// True when `file` is missing or older than any existing input.
    static func isOlder(_ file: URL, than inputs: [URL]) -> Bool {
        guard let date = modified(file) else { return true }
        return inputs.contains { (modified($0) ?? .distantPast) > date }
    }

    private static func modificationKey(_ urls: [URL]) -> String {
        urls.map { "\($0.lastPathComponent)|\(modified($0)?.timeIntervalSince1970 ?? 0)" }.joined(separator: ",")
    }
}

/// What the summary page can ask its host to do. A nil action means it is not available.
struct SummaryActions {
    var canEdit = true
    var importVideos: () -> Void = {}
    /// Analyse the first throw that has not been analysed yet.
    var analyzeFirst: (label: String, run: () -> Void)? = nil
    /// Open the first throw without a result.
    var recordResults: (() -> Void)? = nil
    var refresh: () -> Void = {}
    /// Prepare the cross-throw consistency data (insights) for the newest analysed throw.
    var prepareConsistency: (() -> Void)? = nil
}

// MARK: - Summary page (pure: data in, actions out)

/// The athlete summary page. Pure so it can be rendered offscreen for visual review.
struct AthleteSummaryContent: View {
    let dashboard: AthleteDashboard?
    let rows: [SummaryThrowRow]
    let consistency: TrialInsights.Consistency?
    let open: (UUID) -> Void
    var athleteName: String?
    /// All the athlete's throws, analysed or not (defaults to the analysed rows).
    var throwCount: Int?
    var resultCount: Int?
    var loading = false
    var failure: String?
    var actions = SummaryActions()
    /// Research details start closed; visual review opens them.
    @State var showsDetails = false

    private let curves: ElbowCurves?
    private let scores: [UUID: ScoreCategory]

    init(dashboard: AthleteDashboard?, rows: [SummaryThrowRow], consistency: TrialInsights.Consistency?, open: @escaping (UUID) -> Void,
         athleteName: String? = nil, throwCount: Int? = nil, resultCount: Int? = nil, loading: Bool = false, failure: String? = nil,
         actions: SummaryActions = SummaryActions(), showsDetails: Bool = false) {
        self.dashboard = dashboard; self.rows = rows; self.consistency = consistency; self.open = open
        self.athleteName = athleteName; self.throwCount = throwCount; self.resultCount = resultCount
        self.loading = loading; self.failure = failure; self.actions = actions
        _showsDetails = State(initialValue: showsDetails)
        curves = consistency.map(ElbowCurves.init)
        scores = Dictionary(rows.compactMap { row in row.score.map { (row.id, $0) } }, uniquingKeysWith: { a, _ in a })
    }

    private var total: Int { throwCount ?? rows.count }
    private var analysed: Int { rows.count }
    private var results: Int { resultCount ?? rows.filter { $0.score != nil }.count }

    var body: some View {
        if total == 0 {
            // Nothing to summarise: every section would need the same first step.
            EmptyState("No Throws Yet", symbol: "video.badge.plus",
                       message: "Import side-view videos of \(athleteName ?? "this athlete")'s throws. The summary compares them once they are analysed.",
                       action: actions.canEdit ? ("Import Videos", actions.importVideos) : nil)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            Page {
                header
                if let failure {
                    Label(failure, systemImage: "exclamationmark.triangle.fill").foregroundStyle(.orange).textSelection(.enabled)
                }
                if loading {
                    HStack(spacing: Space.s) { ProgressView().controlSize(.small); Text("Reading this athlete's throws…").foregroundStyle(.secondary) }
                }
                scoringCard
                focusCard
                tableCard
                consistencyCard
                releaseMapCard
                researchDetails
            }
        }
    }

    // MARK: Header

    private var header: some View {
        VStack(alignment: .leading, spacing: Space.xs) {
            Text(athleteName ?? dashboard?.athlete ?? "Athlete").font(.largeTitle.weight(.bold)).lineLimit(1)
            Text(subtitle).font(.title3).foregroundStyle(.secondary)
        }
    }

    private var subtitle: String {
        return "\(total) \(total == 1 ? "throw" : "throws") · \(analysed) analysed · \(results) with a result"
    }

    // MARK: Empty states

    /// A section's empty state: what is missing, and the one action that unblocks it.
    private func sectionEmpty(_ symbol: String, _ message: String, action: (label: String, run: () -> Void)?) -> some View {
        HStack(alignment: .center, spacing: Space.m) {
            Image(systemName: symbol).font(.title2).foregroundStyle(.secondary).frame(width: 28).accessibilityHidden(true)
            Text(message).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: Space.m)
            if let action { Button(action.label, action: action.run).disabled(!actions.canEdit) }
        }
        .padding(.vertical, Space.xs)
    }

    /// No analysed throw yet: analyse one (or, with every video missing, nothing to press).
    private var notAnalysedEmpty: some View {
        sectionEmpty("waveform.path.ecg", actions.analyzeFirst == nil
                     ? "No throw has been analysed yet, and the videos need relinking first (throw list → Locate / Relink Video…)."
                     : "No throw has been analysed yet.",
                     action: actions.analyzeFirst)
    }

    /// Dashboard missing although throws are analysed.
    private var noDashboardEmpty: some View {
        sectionEmpty("rectangle.3.group", "The summary has not been built yet.", action: ("Build Summary", actions.refresh))
    }

    @ViewBuilder private var dashboardEmpty: some View {
        if analysed == 0 { notAnalysedEmpty } else { noDashboardEmpty }
    }

    // MARK: Scoring

    private var scoringCard: some View {
        Card("Scoring", symbol: "target", subtitle: "Where the bags ended up, from the results recorded on each throw.") {
            if analysed > 0, results == 0 || dashboard?.throws_with_outcome == 0 {
                // Results are the missing input whether or not the summary has been built.
                sectionEmpty("hand.tap", "No results recorded yet. Open each throw and click Hole, Board or Miss — one click per throw.",
                             action: actions.recordResults.map { ("Record Results", $0) })
            } else if let dashboard {
                let sports = dashboard.performance.sports
                if sports?.bags ?? 0 == 0 {
                    sectionEmpty("hand.tap", "No results recorded yet. Open each throw and click Hole, Board or Miss — one click per throw.",
                                 action: actions.recordResults.map { ("Record Results", $0) })
                } else {
                    tiles(sports)
                    let missing = dashboard.performance.counts?["unknown"] ?? 0
                    if missing > 0 {
                        HStack(spacing: Space.s) {
                            Text("\(missing) analysed \(missing == 1 ? "throw has" : "throws have") no result yet.").foregroundStyle(.secondary)
                            if let record = actions.recordResults { Button("Record Results", action: record).buttonStyle(.link) }
                        }
                        .font(.caption)
                    }
                }
            } else {
                dashboardEmpty
            }
        }
    }

    private func tiles(_ sports: AthleteDashboard.Sports?) -> some View {
        let items: [(String, String, String)] = [
            ("PPR", number(sports?.ppr, digits: 1), "Points per 4-bag round (max 12)"),
            ("In", percent(sports?.in_percent), "In the hole · 3 points"),
            ("On", percent(sports?.on_percent), "On the board · 1 point"),
            ("Off", percent(sports?.off_percent), "Missed · 0 points"),
            ("Bags", sports?.bags.map(String.init) ?? "—", "With a recorded result"),
        ]
        return ViewThatFits(in: .horizontal) {
            HStack(alignment: .top, spacing: Space.m) {
                ForEach(items, id: \.0) { StatTile(label: $0.0, value: $0.1, caption: $0.2).frame(minWidth: 150) }
            }
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 150), spacing: Space.m, alignment: .top)], spacing: Space.m) {
                ForEach(items, id: \.0) { StatTile(label: $0.0, value: $0.1, caption: $0.2) }
            }
        }
    }

    private func percent(_ value: Double?) -> String { value.map { "\(number($0, digits: 0))%" } ?? "—" }

    // MARK: Coach focus

    private var focusCard: some View {
        Card("Coach focus", symbol: "lightbulb", subtitle: "What to look at next with this athlete.") {
            if let dashboard {
                Text(dashboard.headline).font(.title3.weight(.semibold)).fixedSize(horizontal: false, vertical: true)
                if analysed < minimumThrowsToJudge {
                    Label("With fewer than \(minimumThrowsToJudge) analysed throws the summary does not call anything unusual yet.",
                          systemImage: "info.circle")
                        .font(.callout).foregroundStyle(.secondary)
                }
                if dashboard.priorities.isEmpty {
                    Text(dashboard.throws_with_outcome < 10
                         ? "No coaching priority yet. A priority needs at least 5 scored throws and 5 misses, a difference bigger than measurement noise, a repeatable effect and reliable measurements."
                         : "No release or movement feature passed all five checks for a coaching priority. Misses may come from aim, or from the bag's behaviour after landing.")
                        .foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                }
                ForEach(Array(dashboard.priorities.enumerated()), id: \.element.id) { index, priority in
                    PriorityRow(index: index + 1, priority: priority, open: open)
                }
                if !dashboard.observed_differences.isEmpty {
                    DisclosureGroup("Observed differences, not yet advice (\(dashboard.observed_differences.count))") {
                        VStack(alignment: .leading, spacing: Space.s) {
                            ForEach(dashboard.observed_differences) { difference in
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(difference.sentence ?? difference.label).font(.callout).fixedSize(horizontal: false, vertical: true)
                                    if let why = difference.why_not_a_priority, !why.isEmpty {
                                        Text("Not advice yet: not \(why.map(PriorityRow.checkName).joined(separator: ", ").lowercased()).")
                                            .font(.caption).foregroundStyle(.secondary)
                                    }
                                }
                            }
                        }
                        .padding(.top, Space.s)
                    }
                }
            } else {
                dashboardEmpty
            }
        }
    }

    // MARK: Throw comparison

    private var tableCard: some View {
        Card("Throw comparison", symbol: "tablecells", subtitle: "One row per analysed throw. Click a column title to sort.") {
            if rows.isEmpty {
                notAnalysedEmpty
            } else {
                ThrowComparisonTable(rows: rows, open: open)
            }
        }
    }

    // MARK: Consistency

    private var consistencyCard: some View {
        Card("Consistency", symbol: "waveform.path", subtitle: "How much the movement and the release change from throw to throw.") {
            Text("Elbow angle through the throw").font(.headline)
            if analysed == 0 {
                notAnalysedEmpty
            } else if let curves, !curves.lines.isEmpty {
                ElbowConsistencyChart(curves: curves, scores: scores)
            } else if let consistency {
                sectionEmpty("chart.line.flattrend.xyaxis",
                             "\(consistency.message) (\(consistency.n) so far.)",
                             action: ("Import Videos", actions.importVideos))
            } else {
                sectionEmpty("chart.line.flattrend.xyaxis", "The throw-to-throw comparison has not been prepared yet.",
                             action: actions.prepareConsistency.map { ("Prepare Comparison", $0) })
            }
            Divider().padding(.vertical, Space.xs)
            Text("Release and body at a glance").font(.headline)
            if let profile = dashboard?.release_profile, !profile.isEmpty {
                ReleaseProfileStrips(profile: profile)
            } else if dashboard == nil {
                dashboardEmpty
            } else {
                sectionEmpty("chart.dots.scatter", "No measure was reliable on enough throws to compare yet.",
                             action: ("Import Videos", actions.importVideos))
            }
        }
    }

    // MARK: Release map

    /// Median speed, angle and height of the measured throws; distance from their measured median
    /// (at least 3 throws) or the assumed regulation distance.
    static func typicalRelease(_ releases: [MeasuredRelease]) -> (params: LaunchParameters, measuredDistance: Bool)? {
        guard let speed = MedianSD.of(releases.map(\.speed)), let angle = MedianSD.of(releases.map(\.angle)),
              let height = MedianSD.of(releases.map(\.height)) else { return nil }
        let distances = releases.compactMap(\.distance)
        let measured = distances.count >= 3 ? MedianSD.of(distances)?.median : nil
        return (LaunchParameters(speed: speed.median, angleDegrees: angle.median, releaseHeight: height.median,
                                 distanceToBoard: measured ?? LaunchLabContent.defaultParameters.distanceToBoard), measured != nil)
    }

    @ViewBuilder private var releaseMapCard: some View {
        let releases = rows.compactMap(\.release)
        if let typical = Self.typicalRelease(releases) {
            let p = typical.params
            let distance = typical.measuredDistance
                ? "\(number(p.distanceToBoard, digits: 2)) m to the board (this athlete's measured median)"
                : "\(number(p.distanceToBoard, digits: 2)) m to the board (assumed regulation distance)"
            Card("Release map", symbol: "square.grid.3x3.fill",
                 subtitle: "Where a drag-free bag would first land for each speed and angle, at this athlete's typical release height (\(number(p.releaseHeight, digits: 2)) m) and \(distance).") {
                SuccessMap(params: .constant(p), throws: releases, interactive: false)
                Text("Crosshair: this athlete's typical release (median \(number(p.speed, digits: 1)) m/s at \(number(p.angleDegrees, digits: 0))°). \(releases.count) of \(analysed) analysed throws had speed, angle and height measured reliably.")
                    .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
        } else {
            Card("Release map", symbol: "square.grid.3x3.fill", subtitle: "Throws on the release speed × angle success map.") {
                if analysed == 0 {
                    notAnalysedEmpty
                } else {
                    sectionEmpty("ruler", "No throw has release speed, angle and height measured reliably in metres yet. Open a throw and check its scale and release in Fix Tracking.",
                                 action: rows.first.map { row in ("Open \(row.label)", { open(row.id) }) })
                }
            }
        }
    }

    // MARK: Research details

    private var researchDetails: some View {
        Card {
            DisclosureGroup(isExpanded: $showsDetails) {
                VStack(alignment: .leading, spacing: Space.xl) {
                    if let dashboard {
                        EvidenceChainGrid(links: dashboard.evidence_chain)
                        TrustCounts(trust: dashboard.trust)
                        CompensationSection(compensation: dashboard.compensation)
                    } else {
                        dashboardEmpty
                    }
                }
                .padding(.top, Space.m)
            } label: {
                Label("Research details", systemImage: "flask").font(.title2.weight(.semibold))
            }
        }
    }
}

// MARK: - Pieces

/// A large number with a label and a caption, on the tile surface (no history bar).
struct StatTile: View {
    let label: String
    let value: String
    let caption: String

    var body: some View {
        VStack(alignment: .leading, spacing: Space.xs) {
            Text(label).font(.headline)
            Text(value).font(.title.monospacedDigit())
            Text(caption).font(.caption).foregroundStyle(.secondary).lineLimit(2)
        }
        .padding(Space.m)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: Radius.card))
        .overlay(RoundedRectangle(cornerRadius: Radius.card).strokeBorder(.separator.opacity(0.6)))
        .accessibilityElement(children: .combine)
    }
}

/// One coaching priority: what differed, what to practise, typical scored throws, and the five checks.
private struct PriorityRow: View {
    let index: Int
    let priority: AthleteDashboard.Priority
    let open: (UUID) -> Void

    static let checkOrder = ["associated_with_outcome", "larger_than_measurement_uncertainty", "repeatable",
                             "measured_reliably", "interpretable_and_modifiable"]

    static func checkName(_ key: String) -> String {
        switch key {
        case "associated_with_outcome": "Linked to the result"
        case "larger_than_measurement_uncertainty": "Bigger than measurement noise"
        case "repeatable": "Repeatable"
        case "measured_reliably": "Measured reliably"
        case "interpretable_and_modifiable": "Something the athlete can change"
        default: key.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }

    var body: some View {
        HStack(alignment: .top, spacing: Space.m) {
            Text("\(index)").font(.title2.weight(.bold)).foregroundStyle(athleteInk).frame(width: 24)
            VStack(alignment: .leading, spacing: Space.s) {
                Text(priority.label).font(.headline)
                if let sentence = priority.sentence { Text(sentence).fixedSize(horizontal: false, vertical: true) }
                if let practice = priority.practice { Label("Practise \(practice).", systemImage: "figure.run").font(.callout) }
                if let examples = priority.example_throws, !examples.isEmpty {
                    HStack(spacing: Space.s) {
                        Text("Typical scored throws:").font(.caption).foregroundStyle(.secondary)
                        ForEach(examples, id: \.self) { example in
                            Button(example.label) { if let id = UUID(uuidString: example.trial_id) { open(id) } }
                                .buttonStyle(.link).font(.caption)
                        }
                    }
                }
                checks
            }
        }
        .padding(Space.m)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(nsColor: .windowBackgroundColor).opacity(0.6), in: RoundedRectangle(cornerRadius: 10))
    }

    private var checks: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 190), alignment: .leading)], alignment: .leading, spacing: Space.xs) {
            ForEach(Self.checkOrder.filter { priority.checks[$0] != nil }, id: \.self) { key in
                let passed = priority.checks[key] == true
                Label(Self.checkName(key), systemImage: passed ? "checkmark.circle.fill" : "xmark.circle")
                    .font(.caption).foregroundStyle(passed ? .green : .secondary)
                    .accessibilityLabel("\(Self.checkName(key)): \(passed ? "passed" : "not passed")")
            }
        }
    }
}

/// Body → release → flight → outcome links: Spearman ρ, bootstrap 95% CI and n.
private struct EvidenceChainGrid: View {
    let links: [AthleteDashboard.Link]

    var body: some View {
        VStack(alignment: .leading, spacing: Space.s) {
            Text("Evidence chain").font(.headline).accessibilityAddTraits(.isHeader)
            Text("Within-athlete links tested as hypotheses: Spearman ρ with a bootstrap 95% confidence interval (CI), at least 8 throws. Supported = the CI excludes 0. An association, not a cause.")
                .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            if links.isEmpty {
                Text("No links could be tested yet.").foregroundStyle(.secondary)
            } else {
                Grid(alignment: .leading, horizontalSpacing: Space.l, verticalSpacing: Space.xs) {
                    GridRow {
                        Text("Stage"); Text("Link"); Text("ρ"); Text("95% CI"); Text("n"); Text("Supported")
                    }
                    .font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                    Divider()
                    ForEach(links) { link in
                        GridRow {
                            Text(link.stage).foregroundStyle(.secondary)
                            Text("\(link.from_label) → \(link.to_label)")
                            Text(link.status == "estimated" ? number(link.rho, digits: 2) : "—")
                            Text(ciText(link))
                            Text("\(link.n)")
                            if link.status == "estimated" {
                                Label(link.supported ? "Yes" : "No", systemImage: link.supported ? "checkmark.circle.fill" : "minus.circle")
                                    .foregroundStyle(link.supported ? .green : .secondary)
                            } else {
                                Text("Too few throws").foregroundStyle(.secondary)
                            }
                        }
                    }
                }
                .font(.callout).monospacedDigit()
            }
        }
    }

    private func ciText(_ link: AthleteDashboard.Link) -> String {
        guard link.status == "estimated", let ci = link.ci, ci.count == 2, let low = ci[0], let high = ci[1] else { return "—" }
        return "\(number(low, digits: 2)) to \(number(high, digits: 2))"
    }
}

/// GOOD / WARNING / POOR throw counts per tracking stage.
private struct TrustCounts: View {
    let trust: AthleteDashboard.Trust

    var body: some View {
        VStack(alignment: .leading, spacing: Space.s) {
            Text("Data trust").font(.headline).accessibilityAddTraits(.isHeader)
            Grid(alignment: .leading, horizontalSpacing: Space.xl, verticalSpacing: Space.xs) {
                ForEach(TrustStrip.stages, id: \.self) { stage in
                    let counts = trust.grades[stage] ?? [:]
                    GridRow {
                        Text(TrustStrip.title(stage)).font(.callout.weight(.medium))
                        HStack(spacing: Space.m) {
                            ForEach(["GOOD", "WARNING", "POOR"], id: \.self) { grade in
                                HStack(spacing: Space.xs) {
                                    GradeGlyph(grade: grade)
                                    Text("\(counts[grade] ?? 0) \(grade.lowercased())").monospacedDigit()
                                }
                                .help("\(counts[grade] ?? 0) throws graded \(grade.lowercased())")
                            }
                        }
                        .font(.callout)
                        Text(TrustStrip.rule(stage)).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
            if let share = trust.reliable_metric_share {
                Text("\(number(100 * share, digits: 0))% of the measurements across \(trust.throws) throws passed the reliability rules.")
                    .font(.callout)
            }
        }
    }
}

/// Speed–angle compensation (after Müller & Sternad 2004).
private struct CompensationSection: View {
    let compensation: AthleteDashboard.Compensation

    var body: some View {
        VStack(alignment: .leading, spacing: Space.s) {
            Text("Release compensation").font(.headline).accessibilityAddTraits(.isHeader)
            Text(compensation.message).fixedSize(horizontal: false, vertical: true)
            if compensation.status == "estimated" {
                Grid(alignment: .leading, horizontalSpacing: Space.xl, verticalSpacing: Space.xs) {
                    if let observed = compensation.observed_spread_m {
                        GridRow { Text("Landing spread, as thrown"); Text("\(number(observed, digits: 2)) m (SD)") }
                    }
                    if let random = compensation.random_pairing_spread_m {
                        GridRow { Text("Landing spread, speed paired at random"); Text("\(number(random, digits: 2)) m (SD)") }
                    }
                    if let ratio = compensation.ratio { GridRow { Text("Ratio (random ÷ as thrown)"); Text(number(ratio, digits: 2)) } }
                    if let chance = compensation.chance_as_tight {
                        GridRow { Text("Chance a random pairing is as tight"); Text(number(chance, digits: 3)) }
                    }
                    GridRow { Text("Throws"); Text("\(compensation.n)") }
                }
                .font(.callout).monospacedDigit()
            }
            Text(compensation.method ?? "Drag-free first-contact distance; release speed permuted across throws (Müller & Sternad 2004). Model-based and descriptive.")
                .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }
    }
}
