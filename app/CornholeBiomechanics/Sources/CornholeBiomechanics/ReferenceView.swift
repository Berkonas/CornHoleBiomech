import SwiftUI

struct ReferenceView: View {
    @EnvironmentObject private var store: ProjectStore
    @State private var addingSet = false
    @State private var editingSet: ReferenceSet?
    @State private var deletingSet: ReferenceSet?

    var body: some View {
        SectionContainer(
            title: "References",
            subtitle: "Coach-selected comparisons, athlete-specific baselines, and multi-throw reference sets."
        ) {
            ResearchCard(title: "Reference is not technique quality", symbol: "bookmark") {
                Text("Reference Similarity answers how closely a throw resembles the selected pattern. It does not determine whether the movement is good, correct, or universally optimal.")
                Text("Reference provenance, scope, members, and camera compatibility remain visible. Several throws can represent natural variability better than one throw.")
                    .font(.caption).foregroundStyle(.secondary)
            }

            HStack {
                Picker("Reference set", selection: $store.selectedReferenceSetID) {
                    Text("Choose a reference set…").tag(UUID?.none)
                    ForEach(store.project?.referenceSets ?? []) { set in
                        Text(set.name).tag(Optional(set.id))
                    }
                }.frame(maxWidth: 460)
                Button("New Set…") { addingSet = true }
                Button("Add External Reference…") {
                    NotificationCenter.default.post(name: .importReferenceVideo, object: nil)
                }.disabled(store.project?.athletes.isEmpty != false)
                Spacer()
            }

            if let set = store.selectedReferenceSet {
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 5) {
                        Text(set.name).font(.title2.weight(.semibold))
                        Text(scopeText(set)).foregroundStyle(.secondary)
                        Text("Provenance: \(set.provenance.replacingOccurrences(of: "_", with: " "))")
                            .font(.caption).foregroundStyle(.secondary)
                        if !set.notes.isEmpty { Text(set.notes).font(.callout) }
                    }
                    Spacer()
                    Button("Edit…") { editingSet = set }
                    Button("Delete…", role: .destructive) { deletingSet = set }
                }

                Text("Analyzed throws").font(.headline)
                if analyzed.isEmpty {
                    ContentUnavailableView(
                        "No analyzed throws", systemImage: "bookmark.slash",
                        description: Text("Import and analyze a rights-cleared throw before assigning it to this set.")
                    )
                } else {
                    ForEach(analyzed) { trial in
                        HStack(spacing: 14) {
                            Image(systemName: contains(trial, in: set) ? "bookmark.fill" : "bookmark")
                                .font(.title2)
                                .foregroundStyle(contains(trial, in: set) ? Color.accentColor : Color.secondary)
                            VStack(alignment: .leading, spacing: 3) {
                                Text(trial.displayName).font(.headline)
                                Text("\(athleteName(trial.athleteID)) · \(trial.cameraView.label) view · Throw \(trial.shortID)")
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                            Toggle("Member", isOn: membership(trial, set: set)).toggleStyle(.switch)
                                .disabled(set.scope == .athlete && set.athleteID != trial.athleteID)
                        }
                        .padding(14)
                        .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 10))
                    }
                }
                let memberCount = set.trialIDs.count
                Label(
                    memberCount == 0
                        ? "Assign at least one compatible analyzed throw before comparing."
                        : memberCount == 1
                            ? "Single-trial comparisons are labeled Prototype Reference Similarity."
                            : "Reference set contains \(memberCount) throws; comparisons use the pointwise mean and retain variability.",
                    systemImage: memberCount > 1 ? "checkmark.circle" : "info.circle"
                ).foregroundStyle(memberCount > 1 ? .green : .secondary)
            } else {
                ContentUnavailableView(
                    "Create a reference set", systemImage: "bookmark",
                    description: Text("Use a global coach reference or an athlete-specific personal baseline.")
                )
            }
        }
        .onAppear {
            if store.selectedReferenceSetID == nil {
                store.selectedReferenceSetID = store.project?.referenceSets.first?.id
            }
        }
        .sheet(isPresented: $addingSet) { ReferenceSetForm() }
        .sheet(item: $editingSet) { ReferenceSetForm(existing: $0) }
        .confirmationDialog(
            "Delete reference set?",
            isPresented: Binding(get: { deletingSet != nil }, set: { if !$0 { deletingSet = nil } }),
            titleVisibility: .visible
        ) {
            Button("Delete Reference Set", role: .destructive) {
                guard let set = deletingSet else { return }
                do { try store.deleteReferenceSet(set) }
                catch { store.errorMessage = error.localizedDescription }
                deletingSet = nil
            }
            Button("Cancel", role: .cancel) { deletingSet = nil }
        } message: {
            Text("The set and its assignments will be removed. Source athlete throws, videos, and analyses will remain.")
        }
    }

    private var analyzed: [Trial] { store.analyzedTrials }
    private func contains(_ trial: Trial, in set: ReferenceSet) -> Bool { set.trialIDs.contains(trial.id) }
    private func athleteName(_ id: UUID) -> String {
        store.project?.athletes.first { $0.id == id }?.displayName ?? "Unknown athlete"
    }
    private func scopeText(_ set: ReferenceSet) -> String {
        guard set.scope == .athlete, let athleteID = set.athleteID else { return "Global reference" }
        return "Athlete-specific · \(athleteName(athleteID))"
    }
    private func membership(_ trial: Trial, set: ReferenceSet) -> Binding<Bool> {
        Binding(
            get: { store.project?.referenceSets.first(where: { $0.id == set.id })?.trialIDs.contains(trial.id) == true },
            set: { selected in
                do {
                    if selected { try store.assign(trial, to: set) }
                    else { try store.remove(trial, from: set) }
                } catch { store.errorMessage = error.localizedDescription }
            }
        )
    }
}

private struct ReferenceSetForm: View {
    @EnvironmentObject private var store: ProjectStore
    @Environment(\.dismiss) private var dismiss
    let existing: ReferenceSet?
    @State private var name: String
    @State private var scope: ReferenceScope
    @State private var athleteID: UUID?
    @State private var provenance: String
    @State private var notes: String

    init(existing: ReferenceSet? = nil) {
        self.existing = existing
        _name = State(initialValue: existing?.name ?? "")
        _scope = State(initialValue: existing?.scope ?? .global)
        _athleteID = State(initialValue: existing?.athleteID)
        _provenance = State(initialValue: existing?.provenance ?? "coach_selected")
        _notes = State(initialValue: existing?.notes ?? "")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text(existing == nil ? "New Reference Set" : "Edit Reference Set").font(.title2.weight(.semibold))
            Form {
                TextField("Name", text: $name)
                Picker("Scope", selection: $scope) {
                    ForEach(ReferenceScope.allCases) { Text($0.label).tag($0) }
                }
                if scope == .athlete {
                    Picker("Athlete", selection: $athleteID) {
                        Text("Choose…").tag(UUID?.none)
                        ForEach(store.project?.athletes ?? []) { Text($0.displayName).tag(Optional($0.id)) }
                    }
                }
                TextField("Provenance", text: $provenance)
                TextField("Notes", text: $notes, axis: .vertical).lineLimit(2...5)
            }.formStyle(.grouped)
            Text("Changing or deleting a reference assignment never deletes its source throw.")
                .font(.caption).foregroundStyle(.secondary)
            HStack {
                Spacer()
                Button("Cancel", role: .cancel) { dismiss() }
                Button("Save") { save() }
                    .buttonStyle(.borderedProminent)
                    .disabled(name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || (scope == .athlete && athleteID == nil))
            }
        }.padding(24).frame(width: 540)
    }

    private func save() {
        do {
            if var changed = existing {
                changed.name = name.trimmingCharacters(in: .whitespacesAndNewlines)
                changed.scope = scope
                changed.athleteID = scope == .athlete ? athleteID : nil
                changed.provenance = provenance.trimmingCharacters(in: .whitespacesAndNewlines)
                changed.notes = notes
                try store.updateReferenceSet(changed)
            } else {
                _ = try store.addReferenceSet(
                    name: name, scope: scope, athleteID: athleteID,
                    provenance: provenance.trimmingCharacters(in: .whitespacesAndNewlines), notes: notes
                )
            }
            dismiss()
        } catch { store.errorMessage = error.localizedDescription }
    }
}
