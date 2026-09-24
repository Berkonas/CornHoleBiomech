import SwiftUI

/// App settings (⌘,): appearance, analysis parameters and library location.
struct SettingsView: View {
    @AppStorage("settingsTab") private var tab = "general"

    var body: some View {
        TabView(selection: $tab) {
            GeneralSettings()
                .tabItem { Label("General", systemImage: "gearshape") }.tag("general")
            AnalysisSettingsView(embedded: true)
                .tabItem { Label("Analysis", systemImage: "waveform.path.ecg") }.tag("analysis")
            LibrarySettings()
                .tabItem { Label("Library", systemImage: "externaldrive") }.tag("library")
        }
        .scenePadding()
    }
}

private struct GeneralSettings: View {
    @AppStorage("appearance") private var appearance = "system"

    var body: some View {
        Form {
            Picker("Appearance", selection: $appearance) {
                Text("Follow System").tag("system")
                Text("Light").tag("light")
                Text("Dark").tag("dark")
            }
            .pickerStyle(.radioGroup)
        }
        .frame(width: 420)
        .padding(Space.xl)
    }
}

private struct LibrarySettings: View {
    @EnvironmentObject private var store: ProjectStore
    @EnvironmentObject private var analysis: AnalysisService

    var body: some View {
        Form {
            LabeledContent("Athlete library") {
                VStack(alignment: .leading, spacing: Space.xs) {
                    Text(store.projectURL?.path ?? "No library open")
                        .font(.callout.monospaced()).textSelection(.enabled).lineLimit(3)
                    if let project = store.project {
                        Text("\(project.athletes.count) athletes · \(project.trials.count) throws")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
            LabeledContent("") {
                HStack {
                    Button("Choose…") { store.openProject() }
                    Button("New…") { store.createProject() }
                    Button("Reveal in Finder") { store.revealProject() }.disabled(store.projectURL == nil)
                }
            }
            LabeledContent("") {
                Button("Import Legacy .cornholeproject…") { store.importLegacyProject() }
            }
            Text("Videos and results stay in this visible folder; only its location and preferences are kept in Application Support.")
                .font(.caption).foregroundStyle(.secondary)
        }
        .disabled(analysis.isRunning)
        .frame(width: 520)
        .padding(Space.xl)
    }
}
