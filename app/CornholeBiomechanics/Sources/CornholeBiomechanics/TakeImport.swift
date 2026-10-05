import SwiftUI

/// Import an athlete's two-camera takes: the folder is scanned for Take_N_Front / Take_N_Side pairs
/// (any capitalisation), camera roles are checked from each file's device, size and frame rate, and the
/// chosen takes are prepared one at a time (sync, one clip per throw per camera), then analysed in turn.
struct TakeImportForm: View {
    @EnvironmentObject private var store: ProjectStore
    @EnvironmentObject private var analysis: AnalysisService
    @Environment(\.dismiss) private var dismiss
    let folder: URL
    @State private var discovery: TakeDiscovery?
    @State private var failure: String?
    @State private var chosen: Set<Int> = []
    @State private var athleteID: UUID?
    @State private var throwingSide: ThrowingSide = .right
    @State private var targetDirection: TargetDirection = .leftToRight
    @State private var analyzeAutomatically = true

    var body: some View {
        VStack(alignment: .leading, spacing: Space.l) {
            VStack(alignment: .leading, spacing: Space.xs) {
                Text("Import Two-Camera Takes").font(.title2.weight(.semibold))
                Label(folder.lastPathComponent, systemImage: "folder").foregroundStyle(.secondary)
            }
            if let discovery {
                takeList(discovery)
                settingsForm
                Text(footnote).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            } else if let failure {
                Label(failure, systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
            } else {
                HStack(spacing: Space.s) {
                    ProgressView().controlSize(.small)
                    Text("Pairing videos and checking which camera recorded each file…").foregroundStyle(.secondary)
                }.frame(maxWidth: .infinity, minHeight: 120)
            }
            HStack {
                Spacer()
                Button("Cancel", role: .cancel) { dismiss() }
                Button(chosen.count == 1 ? "Import 1 Take" : "Import \(chosen.count) Takes") { start() }
                    .buttonStyle(.borderedProminent)
                    .disabled(athleteID == nil || chosen.isEmpty || discovery == nil || analysis.isRunning)
            }
        }
        .padding(Space.xl).frame(width: 620)
        .task { await discover() }
        .onChange(of: athleteID) { _, id in
            if let athlete = store.project?.athletes.first(where: { $0.id == id }) { throwingSide = athlete.dominantHand }
            preselect()
        }
    }

    private func takeList(_ discovery: TakeDiscovery) -> some View {
        GroupBox {
            if discovery.takes.isEmpty {
                Text("No Take_N_Front / Take_N_Side videos in this folder.").foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            } else {
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
                            }.disabled(take.side == nil)
                            ForEach(take.notes, id: \.self) { note in
                                Text(note).font(.caption).foregroundStyle(.secondary).padding(.leading, 22)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }
                    if let note = discovery.rolesNote {
                        Label(note, systemImage: "info.circle").font(.caption).foregroundStyle(.secondary)
                    }
                }.frame(maxWidth: .infinity, alignment: .leading)
            }
        } label: { Text("Takes") }
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
            Picker("Board direction in the side video", selection: $targetDirection) {
                ForEach(TargetDirection.allCases) { Text($0.label).tag($0) }
            }
            Toggle("Analyze the throws afterwards (one at a time)", isOn: $analyzeAutomatically)
        }.formStyle(.grouped).frame(height: 190)
    }

    private var footnote: String {
        let throwsCount = chosen.count * 4
        let minutes = max(1, Int((Double(throwsCount) * 2.1).rounded()))
        return "Each take is synchronised from the sound of both cameras, then cut into one clip per throw for each camera. "
            + "The original videos are not changed. Analysis runs one throw at a time, about 2 minutes per throw "
            + "(≈ \(minutes) min for \(throwsCount) throws); you can keep reviewing while it runs."
    }

    private var existing: Set<Int> {
        guard let athleteID else { return [] }
        return store.takeNumbers(athleteID: athleteID)
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

    private func discover() async {
        athleteID = store.selectedAthleteID ?? store.project?.athletes.first?.id
        if let athlete = store.project?.athletes.first(where: { $0.id == athleteID }) { throwingSide = athlete.dominantHand }
        if let previous = store.project?.trials.last(where: { $0.athleteID == athleteID }) { targetDirection = previous.targetDirection }
        do {
            discovery = try await analysis.discoverTakes(in: folder)
            preselect()
        } catch { failure = error.localizedDescription }
    }

    private func start() {
        guard let discovery, let athleteID else { return }
        let takes = discovery.takes.filter { chosen.contains($0.take) }
        let side = throwingSide, direction = targetDirection, analyze = analyzeAutomatically
        dismiss()
        Task { await analysis.importTakes(takes, athleteID: athleteID, throwingSide: side, targetDirection: direction,
                                          analyzeAfter: analyze, store: store) }
    }
}
