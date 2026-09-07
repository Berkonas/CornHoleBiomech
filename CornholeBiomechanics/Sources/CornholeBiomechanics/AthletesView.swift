import SwiftUI

struct AthletesView: View {
    @EnvironmentObject private var store: ProjectStore
    @Binding var showsAddSheet: Bool

    var body: some View {
        HSplitView {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text("Participants").font(.headline)
                    Spacer()
                    Button { showsAddSheet = true } label: { Image(systemName: "plus") }
                        .help("Add athlete")
                }
                List(store.project?.athletes ?? [], selection: $store.selectedAthleteID) { athlete in
                    VStack(alignment: .leading, spacing: 3) {
                        Text(athlete.displayName).font(.headline)
                        Text("\(athlete.dominantHand.label)-handed · \(trialCount(athlete.id)) trials")
                            .font(.caption).foregroundStyle(.secondary)
                    }.tag(athlete.id)
                }
            }
            .padding().frame(minWidth: 250, idealWidth: 290)

            if let athlete = store.selectedAthlete {
                AthleteProfile(athlete: athlete)
            } else {
                ContentUnavailableView("Select an athlete", systemImage: "person.2", description: Text("Athlete-specific analysis keeps body proportions and strategy in context."))
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
                    Button("View Results") { store.selectedAthleteID = athlete.id; store.selectedSection = .results }
                }
                HStack(spacing: 14) {
                    profileMetric("Height", athlete.heightCentimeters.map { "\($0.formatted()) cm" } ?? "Not required")
                    profileMetric("Arm span", athlete.armSpanCentimeters.map { "\($0.formatted()) cm" } ?? "Not required")
                    profileMetric("Trials", "\(trials.count)")
                    profileMetric("With outcomes", "\(trials.filter { $0.outcome != nil }.count)")
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
                                Text(trial.originalFilename)
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
    }

    private var trials: [Trial] { store.project?.trials.filter { $0.athleteID == athlete.id } ?? [] }

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
    @State private var draft = NewAthleteDraft()

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("Add Athlete").font(.title2.weight(.semibold))
            Form {
                TextField("Participant code or name", text: $draft.participantCode)
                Picker("Dominant throwing hand", selection: $draft.dominantHand) {
                    ForEach(ThrowingSide.allCases) { Text($0.label).tag($0) }
                }
                TextField("Height (cm, optional)", text: $draft.height)
                TextField("Arm span (cm, optional)", text: $draft.armSpan)
                TextField("Notes", text: $draft.notes, axis: .vertical).lineLimit(3...6)
            }.formStyle(.grouped)
            Text("Height and arm span are contextual metadata; neither is required for normalized Stage 1 analysis.")
                .font(.caption).foregroundStyle(.secondary)
            HStack {
                Spacer()
                Button("Cancel", role: .cancel) { dismiss() }
                Button("Add Athlete") {
                    do { try store.addAthlete(draft); dismiss() }
                    catch { store.errorMessage = error.localizedDescription }
                }.buttonStyle(.borderedProminent).disabled(draft.participantCode.trimmingCharacters(in: .whitespaces).isEmpty)
            }
        }.padding(24).frame(width: 520)
    }
}
