import AppKit
import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var store: ProjectStore
    @EnvironmentObject private var analysis: AnalysisService
    @AppStorage("appearance") private var appearance = "system"
    @State private var showsAthleteSheet = false
    @State private var importURL: URL?
    @State private var showsOutcomeSheet = false
    @State private var showsSettings = false

    var body: some View {
        NavigationSplitView {
            List(AppSection.allCases, selection: $store.selectedSection) { section in
                Label(section.rawValue, systemImage: section.symbol).tag(section)
            }
            .navigationSplitViewColumnWidth(min: 155, ideal: 175, max: 230)
            .navigationTitle(store.project?.name ?? applicationName)
            .safeAreaInset(edge: .bottom) { projectStatus }
        } detail: {
            Group {
                if store.project == nil {
                    WelcomeView()
                } else {
                    destination
                }
            }
            .navigationTitle(store.selectedSection?.rawValue ?? applicationName)
            .toolbar { toolbar }
        }
        .tint(Color.accentColor)
        .preferredColorScheme(appearance == "dark" ? .dark : appearance == "light" ? .light : nil)
        .sheet(isPresented: $showsAthleteSheet) { AthleteForm() }
        .sheet(item: $importURL) { ImportTrialForm(videoURL: $0) }
        .sheet(isPresented: $showsOutcomeSheet) {
            if let trial = store.selectedTrial { OutcomeEditor(trial: trial) }
        }
        .sheet(isPresented: $showsSettings) { AnalysisSettingsView() }
        .alert("Cornhole Biomechanics Lab", isPresented: errorPresented) {
            Button("OK") { store.errorMessage = nil; analysis.errorMessage = nil }
        } message: { Text(store.errorMessage ?? analysis.errorMessage ?? "Unknown error") }
        .safeAreaInset(edge: .bottom) { analysisProgress }
        .onReceive(NotificationCenter.default.publisher(for: .createStudyProject)) { _ in store.createProject() }
        .onReceive(NotificationCenter.default.publisher(for: .openStudyProject)) { _ in store.openProject() }
        .onReceive(NotificationCenter.default.publisher(for: .importTrialVideo)) { _ in beginImport() }
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
        }
    }

    @ToolbarContentBuilder private var toolbar: some ToolbarContent {
        ToolbarItemGroup {
            Button(action: beginImport) { Label("Import Video", systemImage: "square.and.arrow.down") }
                .disabled(store.project == nil || store.project?.athletes.isEmpty == true)
            Button(action: analyzeSelected) { Label("Analyze", systemImage: "waveform.path.ecg") }
                .disabled(store.selectedTrial == nil || analysis.isRunning)
            Button { showsOutcomeSheet = true } label: { Label("Add Outcome", systemImage: "scope") }
                .disabled(store.selectedTrial == nil || analysis.isRunning)
            Button { store.selectedSection = .compare } label: { Label("Compare", systemImage: "rectangle.split.2x1") }
                .disabled(store.analyzedTrials.isEmpty)
            Button {
                if let trial = store.selectedTrial { store.exportAnalysis(for: trial) }
            } label: { Label("Export", systemImage: "square.and.arrow.up") }
            .disabled(store.selectedTrial?.analysisRelativePath == nil)
        }
    }

    private var projectStatus: some View {
        VStack(alignment: .leading, spacing: 5) {
            if let project = store.project {
                Label("Local project", systemImage: "externaldrive")
                    .font(.caption.weight(.semibold))
                Text("\(project.athletes.count) athletes · \(project.trials.count) trials")
                    .font(.caption).foregroundStyle(.secondary)
            } else {
                Text("No project open").font(.caption).foregroundStyle(.secondary)
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

    private func beginImport() {
        guard store.project?.athletes.isEmpty == false else {
            store.selectedSection = .athletes
            showsAthleteSheet = true
            return
        }
        store.chooseAndImportVideo(athleteID: store.selectedAthleteID) { importURL = $0 }
    }

    private func analyzeSelected() {
        guard let trial = store.selectedTrial else { return }
        Task { await analysis.analyze(trial: trial, store: store) }
    }
}

struct WelcomeView: View {
    @EnvironmentObject private var store: ProjectStore

    var body: some View {
        VStack(spacing: 24) {
            if let icon = NSImage(named: NSImage.applicationIconName) {
                Image(nsImage: icon).resizable().frame(width: 100, height: 100).accessibilityLabel("Cornhole Biomechanics Lab")
            }
            VStack(spacing: 8) {
                Text(applicationName).font(.largeTitle.weight(.semibold))
                Text("A local research instrument for transparent, single-camera projected 2D kinematics.")
                    .foregroundStyle(.secondary).multilineTextAlignment(.center).frame(maxWidth: 580)
            }
            HStack {
                Button("Create Project…") { store.createProject() }.buttonStyle(.borderedProminent)
                Button("Open Project…") { store.openProject() }
            }
            Text("No accounts, analytics, cloud database, or generative interpretation. Videos and results remain in the project folder you choose.")
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
