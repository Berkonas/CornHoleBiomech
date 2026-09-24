import SwiftUI

/// All of one athlete's throws (detail column). Placeholder until the athlete summary task replaces it.
struct AthleteSummaryView: View {
    @EnvironmentObject private var store: ProjectStore
    let athleteID: UUID

    var body: some View {
        EmptyState(store.project?.athletes.first { $0.id == athleteID }?.displayName ?? "Athlete Summary",
                   symbol: "chart.bar.xaxis",
                   message: "The summary of this athlete's throws will appear here.")
    }
}
