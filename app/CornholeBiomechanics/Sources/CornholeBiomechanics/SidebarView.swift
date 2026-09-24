import SwiftUI

/// Sidebar rows: an athlete or a tool.
enum SidebarItem: Hashable {
    case athlete(UUID)
    case launchLab
}

/// Leading column: the athletes in the library, then the tools.
struct SidebarView: View {
    @EnvironmentObject private var store: ProjectStore
    @EnvironmentObject private var analysis: AnalysisService
    @Binding var selection: SidebarItem?
    let addAthlete: () -> Void
    @State private var editing: Athlete?
    @State private var deleting: Athlete?

    var body: some View {
        List(selection: $selection) {
            Section {
                ForEach(store.project?.athletes ?? []) { athlete in
                    Label(athlete.displayName, systemImage: "person")
                        .badge(throwCount(athlete.id))
                        .tag(SidebarItem.athlete(athlete.id))
                        .contextMenu {
                            Button("Edit…") { editing = athlete }
                            Button("Reveal in Finder") { store.revealAthlete(athlete) }
                            Divider()
                            Button("Delete…") { deleting = athlete }
                                .disabled(analysis.isRunning)
                        }
                }
            } header: {
                HStack {
                    Text("Athletes")
                    Spacer()
                    Button("Add Athlete", systemImage: "plus", action: addAthlete)
                        .labelStyle(.iconOnly).buttonStyle(.borderless)
                        .help("Add Athlete")
                        .disabled(store.project == nil)
                }
            }
            Section("Tools") {
                Label("Launch Lab", systemImage: launchLabSymbol).tag(SidebarItem.launchLab)
            }
        }
        .listStyle(.sidebar)
        .navigationSplitViewColumnWidth(min: 170, ideal: 200, max: 260)
        .sheet(item: $editing) { AthleteForm(existing: $0) }
        .confirmationDialog(deletionTitle, isPresented: deletionPresented, titleVisibility: .visible, presenting: deleting) { athlete in
            Button("Delete", role: .destructive) {
                do { try store.deleteAthlete(athlete) } catch { store.errorMessage = error.localizedDescription }
            }
            Button("Cancel", role: .cancel) {}
        } message: { athlete in
            let count = throwCount(athlete.id)
            Text("\(count) \(count == 1 ? "throw" : "throws"), their videos and analyses move to the Trash.")
        }
    }

    private func throwCount(_ athleteID: UUID) -> Int {
        store.project?.trials.filter { $0.athleteID == athleteID }.count ?? 0
    }

    private var deletionTitle: String { "Delete \(deleting?.displayName ?? "athlete")?" }
    private var deletionPresented: Binding<Bool> {
        Binding(get: { deleting != nil }, set: { if !$0 { deleting = nil } })
    }
}
