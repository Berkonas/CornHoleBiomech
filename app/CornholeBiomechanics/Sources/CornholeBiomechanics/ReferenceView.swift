import SwiftUI

struct ReferenceView: View {
    @EnvironmentObject private var store: ProjectStore

    var body: some View {
        SectionContainer(
            title: "Coach-Selected Reference",
            subtitle: "Represent a comparison target without declaring one universal perfect technique."
        ) {
            ResearchCard(title: "How references are interpreted", symbol: "bookmark") {
                Text("A reference trial answers “how similar?” It does not, by itself, answer “how good?” Skilled throwers may use different successful motor strategies. Several high-quality reference trials are preferable because their mean and variability envelope represent natural execution variability.")
                Text("Only analyzed trials with the same camera-view label can be compared.").font(.caption).foregroundStyle(.secondary)
            }
            if analyzed.isEmpty {
                ContentUnavailableView("No analyzed trials", systemImage: "bookmark.slash", description: Text("Analyze a well-recorded, rights-cleared side-view trial before marking it as a reference."))
            } else {
                ForEach(analyzed) { trial in
                    HStack(spacing: 14) {
                        Image(systemName: trial.isReference ? "bookmark.fill" : "bookmark").font(.title2).foregroundStyle(trial.isReference ? Color.accentColor : Color.secondary)
                        VStack(alignment: .leading, spacing: 3) {
                            Text(trial.originalFilename).font(.headline)
                            Text("\(athleteName(trial.athleteID)) · \(trial.cameraView.label) view · Trial \(trial.shortID)")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer()
                        Toggle("Use in reference set", isOn: referenceBinding(trial)).toggleStyle(.switch)
                    }
                    .padding(14).background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 10))
                }
            }
            if references.count == 1 {
                Label("Comparisons will be labeled “Prototype reference similarity – single reference trial.”", systemImage: "info.circle").foregroundStyle(.secondary)
            } else if references.count > 1 {
                Label("Reference set contains \(references.count) trials. Comparisons use the pointwise mean and show variability where available.", systemImage: "checkmark.circle").foregroundStyle(.green)
            }
        }
    }

    private var analyzed: [Trial] { store.analyzedTrials }
    private var references: [Trial] { analyzed.filter(\.isReference) }
    private func athleteName(_ id: UUID) -> String { store.project?.athletes.first { $0.id == id }?.displayName ?? "Unknown athlete" }
    private func referenceBinding(_ trial: Trial) -> Binding<Bool> {
        Binding(get: { store.project?.trials.first { $0.id == trial.id }?.isReference ?? false }, set: { value in
            var changed = trial; changed.isReference = value
            do { try store.updateTrial(changed) } catch { store.errorMessage = error.localizedDescription }
        })
    }
}
