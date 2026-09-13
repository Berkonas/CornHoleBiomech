import Charts
import SwiftUI

private struct ScatterSample: Identifiable {
    let id: String; let x: Double; let y: Double
}

struct RelationshipScatter: View {
    let rows: [RelationshipDocument.DataRow]
    let feature: String
    let outcome: String
    var body: some View {
        if samples.isEmpty {
            ContentUnavailableView("No complete pairs", systemImage: "chart.dots.scatter", description: Text("Record outcomes and re-run this analysis."))
        } else {
            Chart(samples) { sample in
                PointMark(x: .value(featureLabel, sample.x), y: .value(outcomeLabel, sample.y))
                    .symbolSize(65).foregroundStyle(.blue)
            }
            .chartXAxisLabel(featureLabel)
            .chartXScale(domain: .automatic(includesZero: false))
            .chartYAxisLabel(outcomeLabel)
            .accessibilityLabel("Movement feature versus performance scatter plot with \(samples.count) observations")
        }
    }
    private var samples: [ScatterSample] {
        rows.compactMap { row in
            guard let x = featureValue(row), let y = outcome == "radial_error_inches" ? row.radialErrorInches : row.scoreCategory else { return nil }
            return ScatterSample(id: row.trialID, x: x, y: y)
        }
    }
    private func featureValue(_ row: RelationshipDocument.DataRow) -> Double? {
        row.numericFeatures[feature]
    }
    private var featureLabel: String { metricLabel(feature) }
    private var outcomeLabel: String { outcome == "radial_error_inches" ? "Approximate radial target error (in)" : "Cornhole score (0, 1, 3)" }
}
