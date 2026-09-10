import SwiftUI

struct SessionForm: View {
    @EnvironmentObject private var store: ProjectStore
    @Environment(\.dismiss) private var dismiss
    let existing: RecordingSession?
    @State private var athleteID: UUID?
    @State private var name: String
    @State private var camera: String
    @State private var view: CameraView
    @State private var side: ThrowingSide
    @State private var direction: TargetDirection
    @State private var notes: String

    init(existing: RecordingSession? = nil) {
        self.existing = existing
        _athleteID = State(initialValue: existing?.athleteID)
        _name = State(initialValue: existing?.name ?? "Practice session")
        _camera = State(initialValue: existing?.cameraSetup ?? "Tripod, fixed side view")
        _view = State(initialValue: existing?.cameraView ?? .side)
        _side = State(initialValue: existing?.throwingSide ?? .right)
        _direction = State(initialValue: existing?.targetDirection ?? .leftToRight)
        _notes = State(initialValue: existing?.notes ?? "")
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text(existing == nil ? "Start a recording session" : "Edit recording session").font(.title2.weight(.semibold))
            Text("Keep the camera and reference consistent across repeated throws. These settings carry into each import.").foregroundStyle(.secondary)
            Form {
                TextField("Session name", text: $name)
                Picker("Athlete", selection: $athleteID) { ForEach(store.project?.athletes ?? []) { Text($0.displayName).tag(Optional($0.id)) } }
                TextField("Camera setup", text: $camera)
                Picker("Camera view", selection: $view) { ForEach(CameraView.allCases) { Text($0.label).tag($0) } }
                Picker("Throwing hand", selection: $side) { ForEach(ThrowingSide.allCases) { Text($0.label).tag($0) } }
                Picker("Target direction", selection: $direction) { ForEach(TargetDirection.allCases) { Text($0.label).tag($0) } }
                TextField("Notes", text: $notes, axis: .vertical).lineLimit(2...4)
            }.formStyle(.grouped)
            HStack { Spacer(); Button("Cancel") { dismiss() }; Button(existing == nil ? "Start session" : "Save changes") {
                guard let athleteID else { return }
                do {
                    if var changed = existing {
                        changed.athleteID = athleteID; changed.name = name; changed.cameraSetup = camera
                        changed.cameraView = view; changed.throwingSide = side; changed.targetDirection = direction
                        changed.notes = notes
                        try store.updateSession(changed)
                    } else {
                        try store.addSession(RecordingSession(athleteID: athleteID, name: name, cameraSetup: camera, cameraView: view, throwingSide: side, targetDirection: direction, notes: notes, referenceTrialIDs: store.analyzedTrials.filter(\.isReference).map(\.id)))
                    }
                    dismiss()
                } catch { store.errorMessage = error.localizedDescription }
            }.buttonStyle(.borderedProminent).disabled(athleteID == nil || name.trimmingCharacters(in: .whitespaces).isEmpty) }
        }.padding(24).frame(width: 560)
        .onAppear {
            guard existing == nil else { return }
            athleteID = store.selectedAthleteID ?? store.project?.athletes.first?.id
            side = store.selectedAthlete?.dominantHand ?? .right
        }
    }
}
