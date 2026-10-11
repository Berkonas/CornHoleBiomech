import AppKit
import SwiftUI

/// Opens the take import, with a folder already chosen (menu, drop) or not (the sheet asks for one).
struct TakeImportRequest: Identifiable {
    let id = UUID()
    var folder: URL?
}

/// Import an athlete's two-camera takes in three steps: choose or drop the folder → check the automatic pairing
/// (Take_N_Front / Take_N_Side, any capitalisation; camera roles checked from each file's device, size and frame
/// rate) → confirm athlete, throwing side and board direction (remembered per athlete). One button imports and
/// analyses: the takes are prepared one at a time, then every throw is analysed in the queue, one at a time.
struct TakeImportForm: View {
    @EnvironmentObject private var store: ProjectStore
    @EnvironmentObject private var analysis: AnalysisService
    @Environment(\.dismiss) private var dismiss
    @State private var folder: URL?
    @State private var discovery: TakeDiscovery?
    @State private var failure: String?
    @State private var chosen: Set<Int> = []
    @State private var athleteID: UUID?
    @State private var throwingSide: ThrowingSide = .right
    @State private var targetDirection: TargetDirection = .leftToRight
    @State private var dropTargeted = false

    init(folder: URL? = nil) {
        _folder = State(initialValue: folder)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: Space.l) {
            header
            if let folder {
                folderRow(folder)
                if let discovery {
                    takeList(discovery)
                    settingsForm
                } else if let failure {
                    Label(failure, systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
                        .fixedSize(horizontal: false, vertical: true)
                } else {
                    HStack(spacing: Space.s) {
                        ProgressView().controlSize(.small)
                        Text("Pairing the videos and checking which camera recorded each file…").foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, minHeight: 120)
                }
            } else {
                dropZone
            }
            footer
        }
        .padding(Space.xl)
        .frame(width: 640)
        .task(id: folder) { await discover() }
        .onChange(of: athleteID) { _, id in
            applyRememberedSettings(for: id)
            preselect()
        }
    }

    // MARK: Steps

    private var header: some View {
        VStack(alignment: .leading, spacing: Space.xs) {
            Text("Import Takes").font(.title2.weight(.semibold))
            Text("Side and front videos named Take_1_Side, Take_1_Front, … for one athlete. Each throw is analysed automatically after import.")
                .font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }
    }

    private var dropZone: some View {
        VStack(spacing: Space.m) {
            Image(systemName: "folder.badge.plus").font(.system(size: 34, weight: .light)).foregroundStyle(.secondary)
                .accessibilityHidden(true)
            Text("Drop the folder of takes here").font(.headline)
            Button("Choose Folder…") { store.chooseTakeFolder { folder = $0 } }
        }
        .frame(maxWidth: .infinity, minHeight: 180)
        .background(RoundedRectangle(cornerRadius: Radius.card)
            .fill(dropTargeted ? Color.accentColor.opacity(0.10) : Color.secondary.opacity(0.05)))
        .overlay(RoundedRectangle(cornerRadius: Radius.card)
            .strokeBorder(dropTargeted ? Color.accentColor : Color.secondary.opacity(0.35), style: StrokeStyle(lineWidth: 1.5, dash: [6, 4])))
        .dropDestination(for: URL.self) { urls, _ in
            guard let url = urls.first else { return false }
            folder = Self.folderURL(for: url)
            return true
        } isTargeted: { dropTargeted = $0 }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Drop a folder of take videos, or choose one")
    }

    private func folderRow(_ url: URL) -> some View {
        HStack(spacing: Space.s) {
            Label(url.lastPathComponent, systemImage: "folder").font(.body.weight(.medium))
            Spacer()
            Button("Change…") { store.chooseTakeFolder { folder = $0 } }
        }
        .dropDestination(for: URL.self) { urls, _ in
            guard let url = urls.first else { return false }
            folder = Self.folderURL(for: url)
            return true
        }
    }

    private func takeList(_ discovery: TakeDiscovery) -> some View {
        GroupBox {
            if discovery.takes.isEmpty {
                Text("No Take_N_Front / Take_N_Side videos in this folder.").foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: Space.s) {
                        ForEach(discovery.takes) { take in
                            VStack(alignment: .leading, spacing: 2) {
                                Toggle(isOn: binding(for: take)) {
                                    HStack(spacing: Space.s) {
                                        Text("Take \(take.take)").font(.body.weight(.medium))
                                        Text(cameras(take)).font(.caption).foregroundStyle(.secondary)
                                        if existing.contains(take.take) { StatusPill(text: "Already in library", color: .orange) }
                                        if discovery.swappedTakes.contains(take.take) { StatusPill(text: "Labels swapped", color: .blue) }
                                    }
                                }
                                .disabled(take.side == nil)
                                ForEach(take.notes, id: \.self) { note in
                                    Text(note).font(.caption).foregroundStyle(.secondary).padding(.leading, 22)
                                        .fixedSize(horizontal: false, vertical: true)
                                }
                            }
                        }
                        if let note = discovery.rolesNote {
                            Label(note, systemImage: "info.circle").font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .frame(maxHeight: 220)
            }
        } label: {
            HStack {
                Text("Takes found")
                Spacer()
                if !discovery.takes.isEmpty {
                    Button(chosen.count == selectableTakes(discovery).count ? "Select None" : "Select All") {
                        chosen = chosen.count == selectableTakes(discovery).count ? [] : Set(selectableTakes(discovery))
                    }
                    .buttonStyle(.link).font(.caption)
                }
            }
        }
    }

    private var settingsForm: some View {
        Form {
            Picker("Athlete", selection: $athleteID) {
                Text("Choose…").tag(UUID?.none)
                ForEach(store.project?.athletes ?? []) { Text($0.displayName).tag(Optional($0.id)) }
            }
            Picker("Throwing side", selection: $throwingSide) {
                ForEach(ThrowingSide.allCases) { Text($0.label).tag($0) }
            }
            .pickerStyle(.segmented)
            Picker("Board direction in the side video", selection: $targetDirection) {
                ForEach(TargetDirection.allCases) { Text($0.label).tag($0) }
            }
            .pickerStyle(.segmented)
        }
        .formStyle(.grouped)
        .frame(height: 150)
    }

    private var footer: some View {
        HStack(alignment: .center, spacing: Space.m) {
            Text(estimate).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: Space.m)
            Button("Cancel", role: .cancel) { dismiss() }
                .keyboardShortcut(.cancelAction)
            Button("Import & Analyse") { start() }
                .buttonStyle(.borderedProminent)
                .keyboardShortcut(.defaultAction)
                .disabled(athleteID == nil || chosen.isEmpty || discovery == nil)
        }
    }

    // MARK: Logic

    /// "4 takes · 16 throws · about 35 min of analysis, one throw at a time. You can keep working; the queue
    /// carries on after a restart."
    private var estimate: String {
        guard discovery != nil, !chosen.isEmpty else {
            return "The original videos are never changed. Analysis runs one throw at a time and carries on after a restart."
        }
        let throwsCount = chosen.count * 4
        let perThrow = AnalysisService.median(UserDefaults.standard.array(forKey: "analysisQueue.throwSeconds") as? [Double] ?? []) ?? 120
        let minutes = max(1, Int((Double(throwsCount) * perThrow / 60 + Double(chosen.count)).rounded()))
        let queued = analysis.hasQueue ? " after the work already in the queue" : ""
        return "\(chosen.count) take\(chosen.count == 1 ? "" : "s") · \(throwsCount) throws · about \(minutes) min\(queued), one throw at a time. "
            + "You can keep working; the original videos are not changed."
    }

    private var existing: Set<Int> {
        guard let athleteID else { return [] }
        return store.takeNumbers(athleteID: athleteID)
    }

    private func selectableTakes(_ discovery: TakeDiscovery) -> [Int] {
        discovery.takes.filter { $0.side != nil }.map(\.take)
    }

    private func cameras(_ take: DiscoveredTake) -> String {
        switch (take.front != nil, take.side != nil) {
        case (true, true): "side + front"
        case (false, true): "side only"
        case (true, false): "front only — cannot be analysed"
        default: ""
        }
    }

    private func binding(for take: DiscoveredTake) -> Binding<Bool> {
        Binding(get: { chosen.contains(take.take) }, set: { on in
            if on { chosen.insert(take.take) } else { chosen.remove(take.take) }
        })
    }

    private func preselect() {
        guard let discovery else { return }
        chosen = Set(discovery.takes.filter { $0.side != nil && !existing.contains($0.take) }.map(\.take))
    }

    /// The athlete's remembered side and direction; else their dominant hand and the direction of their last throw.
    private func applyRememberedSettings(for id: UUID?) {
        guard let athlete = store.project?.athletes.first(where: { $0.id == id }) else { return }
        if let remembered = athlete.takeImportDefaults {
            throwingSide = remembered.throwingSide
            targetDirection = remembered.targetDirection
            return
        }
        throwingSide = athlete.dominantHand
        if let previous = store.project?.trials.last(where: { $0.athleteID == athlete.id }) { targetDirection = previous.targetDirection }
    }

    private func discover() async {
        if athleteID == nil {
            athleteID = store.selectedAthleteID ?? store.project?.athletes.first?.id
            applyRememberedSettings(for: athleteID)
        }
        guard let folder else { return }
        discovery = nil
        failure = nil
        do {
            discovery = try await analysis.discoverTakes(in: folder)
            preselect()
        } catch { failure = error.localizedDescription }
    }

    private func start() {
        guard let discovery, let athleteID else { return }
        let takes = discovery.takes.filter { chosen.contains($0.take) }
        store.rememberTakeImportDefaults(athleteID: athleteID, throwingSide: throwingSide, targetDirection: targetDirection)
        analysis.enqueueTakeImport(takes, athleteID: athleteID, throwingSide: throwingSide, targetDirection: targetDirection,
                                   store: store)
        dismiss()
    }

    /// A dropped file stands for the folder it is in.
    nonisolated static func folderURL(for url: URL) -> URL {
        let isDirectory = (try? url.resourceValues(forKeys: [.isDirectoryKey]))?.isDirectory ?? false
        return isDirectory ? url : url.deletingLastPathComponent()
    }
}

// MARK: - Queue panel

/// The persistent queue panel at the bottom of the window: what is running, where it is in the import
/// ("Take 3/6 · Throw 2/4 · Bag tracking (5/10) · about 6 min left"), pause / resume / cancel, and anything
/// that needs attention. Shown while anything is queued, running or paused, and while problems are listed.
struct QueuePanel: View {
    @EnvironmentObject private var store: ProjectStore
    @EnvironmentObject private var analysis: AnalysisService
    @State private var showsFailures = false
    @State private var confirmsCancel = false

    var body: some View {
        if analysis.isRunning || analysis.hasQueue || !analysis.failures.isEmpty {
            // Refresh the time left every 15 s even when the engine is quiet.
            TimelineView(.periodic(from: .now, by: 15)) { _ in
                panel
            }
            .padding(.horizontal, Space.l)
            .padding(.bottom, Space.m)
        }
    }

    private var panel: some View {
        HStack(spacing: Space.m) {
            statusIcon
            VStack(alignment: .leading, spacing: 3) {
                Text(headline).font(.subheadline.weight(.semibold)).lineLimit(1).monospacedDigit()
                if let fraction = overallFraction {
                    ProgressView(value: fraction).progressViewStyle(.linear).frame(maxWidth: 360)
                        .accessibilityLabel("Queue progress")
                }
                Text(subline).font(.caption).foregroundStyle(.secondary).lineLimit(1)
            }
            Spacer(minLength: Space.s)
            if !analysis.failures.isEmpty {
                Button {
                    showsFailures = true
                } label: {
                    Label("\(analysis.failures.count) need\(analysis.failures.count == 1 ? "s" : "") attention", systemImage: "exclamationmark.triangle.fill")
                        .foregroundStyle(.orange)
                }
                .buttonStyle(.borderless)
                .popover(isPresented: $showsFailures, arrowEdge: .top) { failureList }
            }
            if analysis.hasQueue {
                if analysis.isPaused {
                    Button("Resume", systemImage: "play.fill") { analysis.resume() }
                        .help("Carry on with the queue")
                } else {
                    Button("Pause", systemImage: "pause.fill") { analysis.pause() }
                        .help("Finish the throw being analysed, then wait")
                }
            }
            if analysis.isRunning || analysis.hasQueue {
                Button(analysis.hasQueue ? "Cancel All" : "Cancel", role: .destructive) {
                    if waitingCount > 1 { confirmsCancel = true } else { analysis.cancel() }
                }
                .confirmationDialog("Cancel the whole queue?", isPresented: $confirmsCancel, titleVisibility: .visible) {
                    Button("Cancel \(waitingCount) Jobs", role: .destructive) { analysis.cancel() }
                    Button("Keep Going", role: .cancel) {}
                } message: {
                    Text("Throws already analysed keep their results. The others can be analysed later from the throw list.")
                }
            } else {
                Button("Dismiss") { analysis.clearFailures() }
            }
        }
        .labelStyle(.titleAndIcon)
        .controlSize(.small)
        .padding(.horizontal, Space.l)
        .padding(.vertical, Space.m)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: Radius.card))
        .overlay(RoundedRectangle(cornerRadius: Radius.card).strokeBorder(.separator.opacity(0.6)))
        .shadow(color: .black.opacity(0.12), radius: 8, y: 2)
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Analysis queue")
    }

    @ViewBuilder private var statusIcon: some View {
        if analysis.isRunning {
            ProgressView().controlSize(.small).accessibilityHidden(true)
        } else if analysis.isPaused {
            Image(systemName: "pause.circle.fill").foregroundStyle(.secondary).imageScale(.large).accessibilityHidden(true)
        } else if analysis.hasQueue {
            Image(systemName: "clock").foregroundStyle(.secondary).imageScale(.large).accessibilityHidden(true)
        } else {
            Image(systemName: "checkmark.circle.fill").foregroundStyle(.green).imageScale(.large).accessibilityHidden(true)
        }
    }

    private var failureList: some View {
        VStack(alignment: .leading, spacing: Space.s) {
            Text("Needs attention").font(.headline)
            ScrollView {
                VStack(alignment: .leading, spacing: Space.s) {
                    ForEach(analysis.failures) { failure in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(failure.title).font(.callout.weight(.semibold))
                            Text(failure.message).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
            }
            .frame(maxHeight: 260)
            HStack { Spacer(); Button("Clear") { analysis.clearFailures(); showsFailures = false } }
        }
        .padding(Space.l)
        .frame(width: 380)
    }

    // MARK: Text

    private var waitingCount: Int { analysis.jobs.filter { $0 != .poolFrontCamera }.count + (analysis.activeJob == nil ? 0 : 1) }

    /// "Take 3/6 · Throw 2/4 · Bag tracking (5/10) · about 6 min left".
    private var headline: String {
        var parts: [String] = []
        switch analysis.activeJob {
        case .analyze(let id)?:
            parts += position(of: id)
            parts.append(analysis.stageLabel)
        case .prepareTake(let job)?:
            parts.append("Preparing take \(job.take)")
            let left = analysis.jobs.filter(\.isTakePreparation).count
            if left > 0 { parts.append("\(left) more to prepare") }
        case .poolFrontCamera?:
            parts.append("Calibrating the front camera")
        case nil:
            if analysis.isPaused {
                parts.append("Paused")
                let throwsLeft = analysis.queuedTrialIDs.count
                if throwsLeft > 0 { parts.append("\(throwsLeft) throw\(throwsLeft == 1 ? "" : "s") waiting") }
                let takesLeft = analysis.jobs.filter(\.isTakePreparation).count
                if takesLeft > 0 { parts.append("\(takesLeft) take\(takesLeft == 1 ? "" : "s") to prepare") }
            } else if analysis.isRunning {
                parts.append(analysis.stageLabel)
            } else if analysis.hasQueue {
                parts.append(analysis.resumedFromLastTime ? "Resuming the queue from last time" : "Starting")
            } else {
                parts.append("Queue finished")
            }
        }
        if analysis.hasQueue, let left = analysis.timeLeftText { parts.append(left) }
        return parts.joined(separator: " · ")
    }

    private var subline: String {
        if analysis.isRunning { return analysis.detail }
        if analysis.isPaused { return "The queue is saved in the library and waits until you resume it." }
        if analysis.hasQueue { return analysis.detail }
        return "\(analysis.failures.count) item\(analysis.failures.count == 1 ? "" : "s") could not be completed."
    }

    /// "Take 3/6", "Throw 2/4" for a queued take throw, or "Throw 5/12" for single videos.
    private func position(of trialID: UUID) -> [String] {
        let trials = store.project?.trials ?? []
        let byID = Dictionary(trials.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        guard let trial = byID[trialID] else { return ["Throw"] }
        let batch = analysis.batchTrialIDs.compactMap { byID[$0] }
        guard let key = trial.takeKey else {
            let index = (analysis.batchTrialIDs.firstIndex(of: trialID) ?? 0) + 1
            return ["Throw \(index)/\(max(index, analysis.batchTrialIDs.count))"]
        }
        var keys: [TakeKey] = []
        for item in batch { if let k = item.takeKey, !keys.contains(k) { keys.append(k) } }
        let place = (keys.firstIndex(of: key) ?? 0) + 1
        let total = max(place, keys.count + analysis.jobs.filter(\.isTakePreparation).count)
        let take = trial.takeNumber.map { $0 == place ? "Take \(place)/\(total)" : "Take \($0) (\(place) of \(total))" }
            ?? "Take \(place)/\(total)"
        let inTake = batch.filter { $0.takeKey == key }
        let throwNumber = trial.throwInTake ?? ((inTake.firstIndex { $0.id == trialID } ?? 0) + 1)
        return [take, "Throw \(throwNumber)/\(max(throwNumber, inTake.count))"]
    }

    /// Share of the queued work done (throws count once; the running throw counts by its progress).
    private var overallFraction: Double? {
        guard analysis.hasQueue || analysis.isRunning else { return nil }
        let total = analysis.batchTrialIDs.count
        guard total > 0 else { return analysis.isRunning ? analysis.progress : nil }
        let waiting = analysis.queuedTrialIDs.count
        let running = analysis.activeJob?.trialID == nil ? 0 : 1
        let done = Double(total - waiting - running) + (running == 1 ? analysis.progress : 0)
        return min(max(done / Double(total), 0), 1)
    }
}
