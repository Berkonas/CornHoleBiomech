import SwiftUI

struct SessionForm: View {
    @EnvironmentObject private var store: ProjectStore
    @Environment(\.dismiss) private var dismiss
    @State private var athleteID: UUID?
    @State private var name = "Practice session"
    @State private var camera = "Tripod, fixed side view"
    @State private var view: CameraView = .side
    @State private var side: ThrowingSide = .right
    @State private var direction: TargetDirection = .leftToRight
    @State private var notes = ""
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("Start a recording session").font(.title2.weight(.semibold))
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
            HStack { Spacer(); Button("Cancel") { dismiss() }; Button("Start session") {
                guard let athleteID else { return }
                do {
                    try store.addSession(RecordingSession(athleteID: athleteID, name: name, cameraSetup: camera, cameraView: view, throwingSide: side, targetDirection: direction, notes: notes, referenceTrialIDs: store.analyzedTrials.filter(\.isReference).map(\.id)))
                    dismiss()
                } catch { store.errorMessage = error.localizedDescription }
            }.buttonStyle(.borderedProminent).disabled(athleteID == nil || name.trimmingCharacters(in: .whitespaces).isEmpty) }
        }.padding(24).frame(width: 560)
        .onAppear { athleteID = store.selectedAthleteID ?? store.project?.athletes.first?.id; side = store.selectedAthlete?.dominantHand ?? .right }
    }
}
