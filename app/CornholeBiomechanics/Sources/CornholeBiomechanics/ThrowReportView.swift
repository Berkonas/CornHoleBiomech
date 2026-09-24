import SwiftUI

/// One throw's report (detail column). Placeholder until the throw report task replaces it.
struct ThrowReportView: View {
    let trial: Trial

    var body: some View {
        EmptyState(trial.displayName, symbol: "doc.text.magnifyingglass",
                   message: trial.analysisRelativePath == nil
                       ? "This throw has not been analyzed yet."
                       : "The throw report will appear here.")
    }
}
