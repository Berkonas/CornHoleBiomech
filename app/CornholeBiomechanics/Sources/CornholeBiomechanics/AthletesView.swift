import SwiftUI

struct AthletesView: View {
    @EnvironmentObject private var store: ProjectStore
    @Binding var showsAddSheet: Bool

    var body: some View {
        HSplitView {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text("Athlete profiles").font(.headline)
                    Spacer()
                    Button { showsAddSheet = true } label: { Image(systemName: "plus") }
                        .help("Add athlete")
                }
                List(store.project?.athletes ?? [], selection: $store.selectedAthleteID) { athlete in
                    VStack(alignment: .leading, spacing: 3) {
                        Text(athlete.displayName).font(.headline).lineLimit(2)
                        Text("\(athlete.dominantHand.label)-handed · \(trialCount(athlete.id)) trials")
                            .font(.caption).foregroundStyle(.secondary)
                    }.tag(athlete.id)
                }
            }
            .padding().frame(minWidth: 200, idealWidth: 230, maxWidth: 280)

            if let athlete = store.selectedAthlete {
                AthleteProfile(athlete: athlete)
            } else {
                ContentUnavailableView {
                    Label("Start with an athlete", systemImage: "person.2")
                } description: { Text("Add a profile, then import that athlete’s recorded throws. Your library saves automatically; there is no project setup step.") }
                actions: { Button("Add athlete") { showsAddSheet = true }.buttonStyle(.borderedProminent) }
            }
        }
    }

    private func trialCount(_ athleteID: UUID) -> Int {
        store.project?.trials.filter { $0.athleteID == athleteID }.count ?? 0
    }
}

struct AthleteProfile: View {
    @EnvironmentObject private var store: ProjectStore
    let athlete: Athlete
    @State private var editing = false
    @State private var confirmingDelete = false
    @State private var addingSession = false
    @State private var editingSession: RecordingSession?
    @State private var deletingSession: RecordingSession?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                HStack(alignment: .firstTextBaseline) {
                    VStack(alignment: .leading) {
                        Text(athlete.displayName).font(.largeTitle.weight(.semibold))
                        Text("Individual profile · \(athlete.dominantHand.label)-hand dominant")
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button("Reveal in Finder") { store.revealAthlete(athlete) }
                    Button("Edit…") { editing = true }
                    Button("Delete…", role: .destructive) { confirmingDelete = true }
                    Button("Import throw") { NotificationCenter.default.post(name: .importTrialVideo, object: nil) }.buttonStyle(.borderedProminent)
                    Button("View Results") { store.selectedAthleteID = athlete.id; store.selectedTrialID = trials.first(where: { $0.analysisRelativePath != nil })?.id; store.selectedSection = .results }
                }
                HStack(spacing: 14) {
                    profileMetric("Height", athlete.heightCentimeters.map { "\($0.formatted()) cm" } ?? "Not required")
                    profileMetric("Upper arm / forearm", "\(number(athlete.upperArmCentimeters)) / \(number(athlete.forearmCentimeters)) cm")
                    profileMetric("Trials", "\(trials.count)")
                    profileMetric("With outcomes", "\(trials.filter { $0.outcome != nil }.count)")
                }
                GroupBox("Recording session (optional)") {
                    VStack(alignment: .leading, spacing: 10) {
                        HStack {
                            Picker("Session", selection: $store.selectedSessionID) {
                                Text("Ungrouped throws").tag(UUID?.none)
                                ForEach(sessions) { Text($0.name).tag(Optional($0.id)) }
                            }
                            Button("New session…") { addingSession = true }
                        }
                        if let session = sessions.first(where: { $0.id == store.selectedSessionID }) {
                            Text("\(session.cameraSetup) · \(session.cameraView.label) view").font(.caption).foregroundStyle(.secondary)
                            HStack {
                                Button("Edit session…") { editingSession = session }
                                Button("Delete session…", role: .destructive) { deletingSession = session }
                            }
                        }
                        Text("Group throws recorded with the same camera setup. Selected session settings carry into the next import.").font(.caption).foregroundStyle(.secondary)
                    }.padding(6)
                }
                ResearchCard(title: "Interpret this athlete in context", symbol: "person.text.rectangle") {
                    Text("Ask what this athlete usually does, how variable the motion is, which features change on better throws, and whether reference differences are actually related to outcome. Height is optional because Stage 1 paths use arm-length normalization.")
                }
                if !athlete.notes.isEmpty {
                    ResearchCard(title: "Notes", symbol: "note.text") { Text(athlete.notes) }
                }
                Text("Trials").font(.title2.weight(.semibold))
                ForEach(trials) { trial in
                    Button {
                        store.selectedTrialID = trial.id
                        store.selectedSection = .trials
                    } label: {
                        HStack {
                            Image(systemName: "video")
                            VStack(alignment: .leading) {
                                Text(trial.displayName)
                                Text("\(trial.cameraView.label) · \(trial.analysisStatus)").font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                            if trial.outcome != nil { Image(systemName: "scope").foregroundStyle(.tint) }
                            Image(systemName: "chevron.right").foregroundStyle(.tertiary)
                        }.contentShape(Rectangle())
                    }.buttonStyle(.plain)
                }
            }
            .padding(28).frame(maxWidth: 900, alignment: .leading)
        }
        .sheet(isPresented: $editing) { AthleteForm(existing: athlete) }
        .sheet(isPresented: $addingSession) { SessionForm() }
        .sheet(item: $editingSession) { SessionForm(existing: $0) }
        .confirmationDialog("Delete session?", isPresented: Binding(get: { deletingSession != nil }, set: { if !$0 { deletingSession = nil } }), titleVisibility: .visible) {
            Button("Delete session record", role: .destructive) {
                if let session = deletingSession {
                    do { try store.deleteSession(session) } catch { store.errorMessage = error.localizedDescription }
                }
                deletingSession = nil
            }
            Button("Cancel", role: .cancel) { deletingSession = nil }
        } message: { Text("The session grouping is removed. Its athlete, throws, original videos, and analyses remain.") }
        .confirmationDialog(
            "Delete \(athlete.displayName)?", isPresented: $confirmingDelete, titleVisibility: .visible
        ) {
            Button("Delete Athlete and Managed Data", role: .destructive) {
                do { try store.deleteAthlete(athlete) }
                catch { store.errorMessage = error.localizedDescription }
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("This affects \(sessions.count) sessions, \(trials.count) source videos, and \(trials.filter { $0.analysisRelativePath != nil }.count) analyses. Managed files are moved to Trash when possible.")
        }
    }

    private var trials: [Trial] { store.project?.trials.filter { $0.athleteID == athlete.id } ?? [] }
    private var sessions: [RecordingSession] { store.project?.sessions?.filter { $0.athleteID == athlete.id } ?? [] }

    private func profileMetric(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(value).font(.title3.weight(.semibold))
            Text(title).font(.caption).foregroundStyle(.secondary)
        }.padding(14).frame(maxWidth: .infinity, alignment: .leading)
            .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 10))
    }
}

struct AthleteForm: View {
    @EnvironmentObject private var store: ProjectStore
    @Environment(\.dismiss) private var dismiss
    let existing: Athlete?
    @State private var draft: NewAthleteDraft

    init(existing: Athlete? = nil) {
        self.existing = existing
        _draft = State(initialValue: NewAthleteDraft(
            participantCode: existing?.participantCode ?? "",
            dominantHand: existing?.dominantHand ?? .right,
            height: existing?.heightCentimeters.map { String($0) } ?? "",
            armSpan: existing?.armSpanCentimeters.map { String($0) } ?? "",
            upperArm: existing?.upperArmCentimeters.map { String($0) } ?? "",
            forearm: existing?.forearmCentimeters.map { String($0) } ?? "",
            notes: existing?.notes ?? ""
        ))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text(existing == nil ? "Add Athlete" : "Edit Athlete").font(.title2.weight(.semibold))
            Form {
                TextField("Participant code or name", text: $draft.participantCode)
                Picker("Dominant throwing hand", selection: $draft.dominantHand) {
                    ForEach(ThrowingSide.allCases) { Text($0.label).tag($0) }
                }
                TextField("Height (cm, optional)", text: $draft.height)
                DisclosureGroup("Optional anthropometry · measured with a tape") {
                    TextField("Upper arm: shoulder–elbow (cm)", text: $draft.upperArm)
                    TextField("Forearm: elbow–wrist (cm)", text: $draft.forearm)
                    TextField("Arm span (cm)", text: $draft.armSpan)
                }
                TextField("Notes", text: $draft.notes, axis: .vertical).lineLimit(3...6)
            }.formStyle(.grouped)
            Text("Body normalization uses median projected shoulder–elbow plus elbow–wrist length from tracked frames. Tape measurements provide context; they do not calibrate pixels or remove foreshortening.")
                .font(.caption).foregroundStyle(.secondary)
            HStack {
                Spacer()
                Button("Cancel", role: .cancel) { dismiss() }
                Button(existing == nil ? "Add Athlete" : "Save Changes") {
                    do {
                        if var changed = existing {
                            changed.participantCode = draft.participantCode.trimmingCharacters(in: .whitespacesAndNewlines)
                            changed.dominantHand = draft.dominantHand
                            changed.heightCentimeters = Double(draft.height)
                            changed.armSpanCentimeters = Double(draft.armSpan)
                            changed.upperArmCentimeters = Double(draft.upperArm)
                            changed.forearmCentimeters = Double(draft.forearm)
                            changed.notes = draft.notes
                            try store.updateAthlete(changed)
                        } else {
                            try store.addAthlete(draft)
                        }
                        dismiss()
                    }
                    catch { store.errorMessage = error.localizedDescription }
                }.buttonStyle(.borderedProminent).disabled(draft.participantCode.trimmingCharacters(in: .whitespaces).isEmpty || [draft.height, draft.armSpan, draft.upperArm, draft.forearm].contains { !$0.isEmpty && !(Double($0).map { $0.isFinite && $0 > 0 } ?? false) })
            }
        }.padding(24).frame(width: 520)
    }
}
