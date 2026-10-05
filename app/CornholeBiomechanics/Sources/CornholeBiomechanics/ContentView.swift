import AppKit
import SwiftUI

/// Three columns: athletes (sidebar) → the athlete's throws → throw report or athlete summary.
/// Launch Lab is a tool, not an athlete view, so it uses a two-column split with no throw list.
struct ContentView: View {
    @EnvironmentObject private var store: ProjectStore
    @EnvironmentObject private var analysis: AnalysisService
    @AppStorage("appearance") private var appearance = "system"
    @State private var columnVisibility = NavigationSplitViewVisibility.all
    @State private var showsAthleteSheet = false
    @State private var importBatch: ImportBatch?
    @State private var takeFolder: URL?
    @State private var outcomeTrial: Trial?
    @State private var showsRecordingGuide = false

    var body: some View {
        Group {
            if store.destination == .launchLab {
                NavigationSplitView(columnVisibility: $columnVisibility) {
                    sidebar
                } detail: {
                    LaunchLabView().navigationTitle("Launch Lab")
                }
            } else {
                NavigationSplitView(columnVisibility: $columnVisibility) {
                    sidebar
                } content: {
                    throwList
                } detail: {
                    detail
                }
            }
        }
        .tint(Color.accentColor)
        .preferredColorScheme(appearance == "dark" ? .dark : appearance == "light" ? .light : nil)
        .sheet(isPresented: $showsAthleteSheet) { AthleteForm() }
        .sheet(item: $importBatch) { ImportTrialForm(videoURLs: $0.urls) }
        .sheet(item: $takeFolder) { TakeImportForm(folder: $0) }
        .sheet(item: $outcomeTrial) { OutcomeEditor(trial: $0) }
        .sheet(isPresented: $showsRecordingGuide) { RecordingGuideSheet() }
        .alert(applicationName, isPresented: errorPresented) {
            Button("OK") { store.errorMessage = nil; analysis.errorMessage = nil }
        } message: { Text(store.errorMessage ?? analysis.errorMessage ?? "Unknown error") }
        .safeAreaInset(edge: .bottom) { analysisProgress }
        .onChange(of: store.selectedAthleteID) { _, id in
            if store.project?.sessions?.first(where: { $0.id == store.selectedSessionID })?.athleteID != id {
                store.selectedSessionID = nil
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .createStudyProject)) { _ in store.createProject() }
        .onReceive(NotificationCenter.default.publisher(for: .openStudyProject)) { _ in store.openProject() }
        .onReceive(NotificationCenter.default.publisher(for: .importLegacyProject)) { _ in store.importLegacyProject() }
        .onReceive(NotificationCenter.default.publisher(for: .addAthlete)) { _ in addAthlete() }
        .onReceive(NotificationCenter.default.publisher(for: .importTrialVideo)) { _ in beginImport() }
        .onReceive(NotificationCenter.default.publisher(for: .importTakes)) { _ in beginTakeImport() }
        .onReceive(NotificationCenter.default.publisher(for: .analyzeSelectedTrial)) { _ in analyzeSelected() }
        .onReceive(NotificationCenter.default.publisher(for: .addTrialOutcome)) { _ in outcomeTrial = shownTrial }
        .onReceive(NotificationCenter.default.publisher(for: .exportSelectedTrial)) { _ in
            if let trial = shownTrial { store.exportAnalysis(for: trial) }
        }
        .onReceive(NotificationCenter.default.publisher(for: .showRecordingGuide)) { _ in showsRecordingGuide = true }
    }

    private var sidebar: some View {
        SidebarView(selection: sidebarSelection, addAthlete: addAthlete)
    }

    @ViewBuilder private var throwList: some View {
        if store.project == nil {
            EmptyState("No Library", symbol: "externaldrive.badge.questionmark", message: "Choose or create an athlete library.")
        } else if let athleteID = store.selectedAthleteID, store.selectedAthlete != nil {
            ThrowListView(athleteID: athleteID, beginImport: beginImport, beginTakeImport: beginTakeImport)
        } else if store.project?.athletes.isEmpty == true {
            EmptyState("No Athletes", symbol: "person.2", message: "Add an athlete, then import videos of their throws.",
                       action: ("Add Athlete", addAthlete))
        } else {
            EmptyState("No Athlete Selected", symbol: "person.2", message: "Choose an athlete in the sidebar.")
        }
    }

    @ViewBuilder private var detail: some View {
        if store.project == nil {
            LibraryRecoveryView()
        } else {
            switch store.destination {
            case .summary(let athleteID):
                AthleteSummaryView(athleteID: athleteID).id(athleteID)
            case .throwReport(let trialID):
                if let trial = store.project?.trials.first(where: { $0.id == trialID }) {
                    ThrowReportView(trial: trial).id(trial.id)
                } else {
                    EmptyState("Throw Not Found", symbol: "questionmark.video", message: "This throw is no longer in the library.")
                }
            case .launchLab:
                LaunchLabView()
            case nil:
                EmptyState("No Throw Selected", symbol: "video", message: "Choose a throw or the athlete summary.")
            }
        }
    }

    /// Sidebar rows map onto the detail destination; picking an athlete opens their summary
    /// unless one of their throws is already showing.
    private var sidebarSelection: Binding<SidebarItem?> {
        Binding(get: {
            if store.destination == .launchLab { return .launchLab }
            return store.selectedAthleteID.map { .athlete($0) }
        }, set: { item in
            switch item {
            case .launchLab: store.destination = .launchLab
            case .athlete(let id):
                if case .throwReport(let trialID) = store.destination,
                   store.project?.trials.first(where: { $0.id == trialID })?.athleteID == id { return }
                store.destination = .summary(id)
            case nil: break
            }
        })
    }

    @ViewBuilder private var analysisProgress: some View {
        if analysis.isRunning {
            HStack(spacing: Space.m) {
                ProgressView(value: analysis.progress).frame(width: 140)
                VStack(alignment: .leading, spacing: 2) {
                    Text(analysis.batchPosition.map { "\($0) · \(analysis.stage)" } ?? analysis.stage).font(.subheadline.weight(.semibold))
                    Text(analysis.detail).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                }
                Spacer()
                Button(analysis.batchTotal > 1 ? "Cancel All" : "Cancel") { analysis.cancel() }
                Text(analysis.progress, format: .percent.precision(.fractionLength(0))).monospacedDigit()
            }
            .padding(Space.m)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: Radius.card))
            .shadow(radius: 10, y: 3)
            .padding()
        }
    }

    private var errorPresented: Binding<Bool> {
        Binding(get: { store.errorMessage != nil || analysis.errorMessage != nil }, set: { value in
            if !value { store.errorMessage = nil; analysis.errorMessage = nil }
        })
    }

    /// The throw in the detail column; Throw menu commands act on it.
    private var shownTrial: Trial? {
        guard case .throwReport(let id) = store.destination else { return nil }
        return store.project?.trials.first { $0.id == id }
    }

    private func addAthlete() {
        guard store.project != nil, !analysis.isRunning else { return }
        showsAthleteSheet = true
    }

    private func beginImport() {
        guard store.project != nil, !analysis.isRunning else { return }
        guard store.project?.athletes.isEmpty == false else { showsAthleteSheet = true; return }
        store.chooseVideos { importBatch = ImportBatch(urls: $0) }
    }

    private func beginTakeImport() {
        guard store.project != nil, !analysis.isRunning else { return }
        guard store.project?.athletes.isEmpty == false else { showsAthleteSheet = true; return }
        store.chooseTakeFolder { takeFolder = $0 }
    }

    private func analyzeSelected() {
        guard let trial = shownTrial, !analysis.isRunning else { return }
        Task { await analysis.analyze(trial: trial, store: store) }
    }
}

struct LibraryRecoveryView: View {
    @EnvironmentObject private var store: ProjectStore

    var body: some View {
        VStack(spacing: 24) {
            if let icon = NSImage(named: NSImage.applicationIconName) {
                Image(nsImage: icon).resizable().frame(width: 100, height: 100).accessibilityLabel("Cornhole Biomechanics Lab")
            }
            VStack(spacing: 8) {
                Text("Athlete Library").font(.largeTitle.weight(.semibold))
                Text(store.missingLibraryURL == nil
                     ? "Choose a visible data folder for athletes, throws, and biomechanics results."
                     : "The saved athlete library could not be found. Locate it without losing its records.")
                    .foregroundStyle(.secondary).multilineTextAlignment(.center).frame(maxWidth: 580)
            }
            HStack {
                Button(store.missingLibraryURL == nil ? "Create Athlete Library…" : "Locate Library…") {
                    if store.missingLibraryURL == nil { store.createProject() } else { store.openProject() }
                }.buttonStyle(.borderedProminent)
                if store.missingLibraryURL == nil { Button("Choose Existing Library…") { store.openProject() } }
                Button("Import Legacy Project…") { store.importLegacyProject() }
            }
            if let missing = store.missingLibraryURL {
                Text("Expected location: \(missing.path)").font(.caption.monospaced()).textSelection(.enabled)
            }
            Text("Videos and scientific results remain in the visible library folder; only its location and app preferences are kept in Application Support.")
                .font(.caption).foregroundStyle(.secondary).multilineTextAlignment(.center).frame(maxWidth: 540)
        }
        .padding(50)
    }
}

struct StatusPill: View {
    let text: String
    var color: Color = .secondary
    var body: some View {
        Text(text).font(.caption.weight(.medium)).padding(.horizontal, 8).padding(.vertical, 4)
            .background(color.opacity(0.13), in: Capsule()).foregroundStyle(color)
    }
}

extension URL: @retroactive Identifiable {
    public var id: String { absoluteString }
}
