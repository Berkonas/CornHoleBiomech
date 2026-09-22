import AppKit
import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var store: ProjectStore
    @EnvironmentObject private var analysis: AnalysisService
    @AppStorage("appearance") private var appearance = "system"
    @State private var showsAthleteSheet = false
    @State private var importURL: URL?
    @State private var importAsReference = false
    @State private var showsOutcomeSheet = false
    @State private var showsSettings = false

    var body: some View {
        NavigationSplitView {
            List(selection: $store.selectedSection) {
                Section("Workspace") {
                    ForEach([AppSection.athletes, .trials, .results, .physics]) { section in
                        Label(section.rawValue, systemImage: section.symbol).tag(section)
                    }
                }
                DisclosureGroup("Research tools") {
                    ForEach([AppSection.compare, .reference, .mechanics, .overview]) { section in
                        Label(section.rawValue, systemImage: section.symbol).tag(section)
                    }
                }
            }
            .navigationSplitViewColumnWidth(min: 155, ideal: 175, max: 230)
            .disabled(analysis.isRunning)
            .navigationTitle(store.project?.name ?? applicationName)
            .safeAreaInset(edge: .bottom) { projectStatus }
        } detail: {
            Group {
                if store.project == nil && store.selectedSection != .physics {
                    LibraryRecoveryView()
                } else {
                    destination
                }
            }
            .disabled(analysis.isRunning)
            .navigationTitle(store.selectedSection?.rawValue ?? applicationName)
            .toolbar { if store.selectedSection != .physics { toolbar } }
        }
        .tint(Color.accentColor)
        .preferredColorScheme(appearance == "dark" ? .dark : appearance == "light" ? .light : nil)
        .sheet(isPresented: $showsAthleteSheet) { AthleteForm() }
        .sheet(item: $importURL) { ImportTrialForm(videoURL: $0, markAsReference: importAsReference) }
        .sheet(isPresented: $showsOutcomeSheet) {
            if let trial = store.selectedTrial { OutcomeEditor(trial: trial) }
        }
        .sheet(isPresented: $showsSettings) { AnalysisSettingsView() }
        .alert("Cornhole Biomechanics Lab", isPresented: errorPresented) {
            Button("OK") { store.errorMessage = nil; analysis.errorMessage = nil }
        } message: { Text(store.errorMessage ?? analysis.errorMessage ?? "Unknown error") }
        .safeAreaInset(edge: .bottom) { analysisProgress }
        .onChange(of: store.selectedAthleteID) { _, id in
            if store.project?.sessions?.first(where: { $0.id == store.selectedSessionID })?.athleteID != id {
                store.selectedSessionID = nil
            }
            if store.selectedTrial?.athleteID != id {
                store.selectedTrialID = store.project?.trials.first(where: { $0.athleteID == id })?.id
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .createStudyProject)) { _ in store.createProject() }
        .onReceive(NotificationCenter.default.publisher(for: .openStudyProject)) { _ in store.openProject() }
        .onReceive(NotificationCenter.default.publisher(for: .importLegacyProject)) { _ in store.importLegacyProject() }
        .onReceive(NotificationCenter.default.publisher(for: .addAthlete)) { _ in store.selectedSection = .athletes; showsAthleteSheet = true }
        .onReceive(NotificationCenter.default.publisher(for: .importTrialVideo)) { _ in beginImport(asReference: false) }
        .onReceive(NotificationCenter.default.publisher(for: .importReferenceVideo)) { _ in beginImport(asReference: true) }
        .onReceive(NotificationCenter.default.publisher(for: .analyzeSelectedTrial)) { _ in analyzeSelected() }
        .onReceive(NotificationCenter.default.publisher(for: .addTrialOutcome)) { _ in showsOutcomeSheet = store.selectedTrial != nil }
        .onReceive(NotificationCenter.default.publisher(for: .exportSelectedTrial)) { _ in
            if let trial = store.selectedTrial { store.exportAnalysis(for: trial) }
        }
    }

    @ViewBuilder private var destination: some View {
        switch store.selectedSection ?? .overview {
        case .overview: OverviewView(showsSettings: $showsSettings)
        case .athletes: AthletesView(showsAddSheet: $showsAthleteSheet)
        case .reference: ReferenceView()
        case .trials: TrialsView(beginImport: beginImport)
        case .compare: CompareView()
        case .results: ResultsView()
        case .mechanics: PendulumLabView()
        case .physics: CornholePhysicsView()
        }
    }

    @ToolbarContentBuilder private var toolbar: some ToolbarContent {
        ToolbarItemGroup {
            Picker("Athlete", selection: $store.selectedAthleteID) {
                Text("Choose athlete").tag(UUID?.none)
                ForEach(store.project?.athletes ?? []) { Text($0.displayName).tag(Optional($0.id)) }
            }.frame(maxWidth: 220).disabled(analysis.isRunning)
            Button { store.selectedSection = .athletes; showsAthleteSheet = true } label: { Label("Add Athlete", systemImage: "person.badge.plus") }
                .labelStyle(.titleAndIcon).disabled(store.project == nil || analysis.isRunning)
            Button { beginImport(asReference: false) } label: { Label("Import Throw", systemImage: "square.and.arrow.down") }
                .labelStyle(.titleAndIcon).disabled(store.project == nil || store.project?.athletes.isEmpty == true || analysis.isRunning)
        }
    }

    private var projectStatus: some View {
        VStack(alignment: .leading, spacing: 5) {
            if let project = store.project {
                Label("Local athlete library", systemImage: "externaldrive")
                    .font(.caption.weight(.semibold))
                Text("\(project.athletes.count) athletes · \(project.trials.count) throws")
                    .font(.caption).foregroundStyle(.secondary)
            } else {
                Text("Library needs attention").font(.caption).foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
    }

    @ViewBuilder private var analysisProgress: some View {
        if analysis.isRunning {
            HStack(spacing: 12) {
                ProgressView(value: analysis.progress).frame(width: 140)
                VStack(alignment: .leading, spacing: 2) {
                    Text(analysis.stage).font(.subheadline.weight(.semibold))
                    Text(analysis.detail).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                }
                Spacer()
                Button("Cancel") { analysis.cancel() }
                Text(analysis.progress, format: .percent.precision(.fractionLength(0))).monospacedDigit()
            }
            .padding(12)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
            .shadow(radius: 10, y: 3)
            .padding()
        }
    }

    private var errorPresented: Binding<Bool> {
        Binding(get: { store.errorMessage != nil || analysis.errorMessage != nil }, set: { value in
            if !value { store.errorMessage = nil; analysis.errorMessage = nil }
        })
    }

    private func beginImport() { beginImport(asReference: false) }

    private func beginImport(asReference: Bool) {
        guard store.project?.athletes.isEmpty == false else {
            store.selectedSection = .athletes
            showsAthleteSheet = true
            return
        }
        importAsReference = asReference
        store.chooseAndImportVideo(athleteID: store.selectedAthleteID) { importURL = $0 }
    }

    private func analyzeSelected() {
        guard let trial = store.selectedTrial else { return }
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

struct SectionContainer<Content: View>: View {
    let title: String
    let subtitle: String
    @ViewBuilder var content: Content

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                VStack(alignment: .leading, spacing: 5) {
                    Text(title).font(.largeTitle.weight(.semibold))
                    Text(subtitle).font(.title3).foregroundStyle(.secondary)
                }
                content
            }
            .frame(maxWidth: 1100, alignment: .leading)
            .padding(28)
        }
        .background(Color(nsColor: .windowBackgroundColor))
    }
}

struct ResearchCard<Content: View>: View {
    let title: String
    let symbol: String
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label(title, systemImage: symbol).font(.headline)
            content
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(.separator.opacity(0.6)))
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
