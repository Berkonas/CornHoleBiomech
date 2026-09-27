import SwiftUI

/// Every correction tool for one throw in one sheet (spec §1.4): body landmarks, the bag track,
/// the flight review (release, first contact, scale) and events & quality. All tabs share one frame
/// (`data.inspectionFrame`). Corrections are saved as they are made; re-analysis applies them.
struct FixTrackingSheet: View {
    enum Tab: String, CaseIterable, Identifiable {
        case body = "Body landmarks", bag = "Bag", flight = "Bag flight", events = "Events & quality"
        var id: String { rawValue }
    }

    @EnvironmentObject private var store: ProjectStore
    @EnvironmentObject private var analysis: AnalysisService
    @Environment(\.dismiss) private var dismiss
    let trial: Trial
    @ObservedObject var data: TrialDataController
    /// Closes the sheet and re-analyzes the throw with the saved corrections.
    let reanalyze: () -> Void
    @State private var tab: Tab

    init(trial: Trial, data: TrialDataController, initialTab: Tab = .body, reanalyze: @escaping () -> Void) {
        self.trial = trial; self.data = data; self.reanalyze = reanalyze
        _tab = State(initialValue: initialTab)
    }

    var body: some View {
        VStack(spacing: 0) {
            TabView(selection: $tab) {
                ForEach(Tab.allCases) { tab in
                    content(tab).tabItem { Text(tab.rawValue) }.tag(tab)
                }
            }
            .padding([.horizontal, .top], Space.l)
            Divider()
            footer.padding(Space.l)
        }
        .frame(width: 1100, height: 760)
        .disabled(analysis.isRunning)
    }

    @ViewBuilder private func content(_ tab: Tab) -> some View {
        switch tab {
        case .body, .bag:
            if let videoURL = store.videoURL(for: trial), data.pose != nil {
                ScrollView {
                    VideoPoseEditor(videoURL: videoURL, data: data,
                                    confidenceThreshold: store.project?.analysisSettings.confidenceThreshold ?? 0.35,
                                    mode: tab == .body ? .body : .bag, reanalyze: runAnalysis)
                        .id("\(trial.id)-\(tab.rawValue)")
                }
            } else if store.videoURL(for: trial) == nil {
                EmptyState("Video Not Found", symbol: "exclamationmark.triangle",
                           message: "The recording for this throw is missing. Locate it to correct the tracking.",
                           action: ("Locate Video…", { store.locateAndRelinkVideo(for: trial) }))
            } else {
                EmptyState("No Tracking Yet", symbol: "figure.walk", message: "Analyze this throw first; its tracking can then be corrected here.")
            }
        case .flight:
            if data.analysisURL != nil, data.pose != nil {
                VStack(alignment: .leading, spacing: 0) {
                    HStack(spacing: Space.m) {
                        Stepper("Selected frame: \(data.inspectionFrame)", value: $data.inspectionFrame,
                                in: 0...max(0, (data.pose?.frameCount ?? 1) - 1))
                            .monospacedDigit().fixedSize()
                        Text("Choose frames while watching the video in the Body landmarks or Bag tab.")
                            .font(.caption).foregroundStyle(.secondary)
                        Spacer()
                    }
                    .padding([.horizontal, .top], Space.xl)
                    FlightReviewEditor(data: data, frame: data.inspectionFrame)
                }
            } else {
                EmptyState("No Flight Yet", symbol: "point.topleft.down.to.point.bottomright.curvepath",
                           message: "Analyze this throw first; its release and first contact can then be reviewed here.")
            }
        case .events:
            QualityEventsView(data: data)
        }
    }

    private var footer: some View {
        HStack(spacing: Space.m) {
            if let error = data.loadError {
                Label(error, systemImage: "exclamationmark.triangle.fill").foregroundStyle(.orange).lineLimit(2)
            } else {
                Text("Corrections are saved as you make them. Re-analyze to apply them to the report.")
                    .font(.callout).foregroundStyle(.secondary)
            }
            Spacer()
            Button("Close") { dismiss() }.keyboardShortcut(.cancelAction)
            Button("Re-analyze with corrections", action: runAnalysis)
                .buttonStyle(.borderedProminent)
                .keyboardShortcut(.defaultAction)
                .disabled(analysis.isRunning || !store.videoState(for: trial).isAvailable)
        }
    }

    private func runAnalysis() {
        dismiss()
        reanalyze()
    }
}
