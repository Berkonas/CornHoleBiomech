import SwiftUI

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
