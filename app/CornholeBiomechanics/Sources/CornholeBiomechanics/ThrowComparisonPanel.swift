import Charts
import SwiftUI

/// Output of Python `compare-throws`: B relative to A, scaled by the athlete's own variation.
struct ThrowComparison: Decodable {
    struct Difference: Decodable, Identifiable {
        var key: String; var label: String; var unit: String
        var a: Double; var b: Double; var difference: Double
        var athlete_sd: Double?; var standardized: Double?; var meaningful: Bool; var decimals: Int
        var id: String { key }
    }
    var a: String; var b: String; var summary: String; var differences: [Difference]
}

/// One bag flight in release-centred, arm-length-normalized, target-forward coordinates.
struct NormalizedFlight {
    struct Sample: Identifiable { var frame: Int; var forward: Double; var up: Double; var segment: Int; var id: Int { frame } }
    var name: String
    var samples: [Sample]

    /// Returns nil when there is no reviewed trajectory or no body scale.
    init?(name: String, flight: FlightSummary?, armLengthPixels: Double?, direction: TargetDirection) {
        guard let flight, let arm = armLengthPixels, arm > 0,
              let origin = flight.trajectory.first(where: { $0.x != nil && $0.y != nil }),
              let x0 = origin.x, let y0 = origin.y else { return nil }
        let sign = direction == .leftToRight ? 1.0 : -1.0
        // Image y points down; flip so up is positive. A missing frame starts a new
        // segment so the plotted line never bridges an unobserved interval.
        var segment = 0, previousMissing = false
        samples = flight.trajectory.compactMap { p in
            guard let x = p.x, let y = p.y else { previousMissing = true; return nil }
            if previousMissing { segment += 1; previousMissing = false }
            return Sample(frame: p.frame, forward: sign * (x - x0) / arm, up: (y0 - y) / arm, segment: segment)
        }
        guard samples.count > 1 else { return nil }
        self.name = name
    }
}

struct ThrowComparisonPanel: View {
    let comparison: ThrowComparison
    let nameA: String
    let nameB: String
    let outcomeA: Int?
    let outcomeB: Int?
    let flights: [NormalizedFlight]

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("\(nameA) vs \(nameB)").font(.title2.weight(.semibold))
            Text("Outcome: \(outcomeText(outcomeA)) vs \(outcomeText(outcomeB))").font(.headline)
            Text(comparison.summary).font(.body).textSelection(.enabled)
            Grid(alignment: .leading, horizontalSpacing: 22, verticalSpacing: 6) {
                GridRow {
                    Text("Measure").fontWeight(.semibold); Text(nameA).fontWeight(.semibold); Text(nameB).fontWeight(.semibold)
                    Text("Difference").fontWeight(.semibold); Text("Athlete's usual spread (SD)").fontWeight(.semibold)
                }
                ForEach(comparison.differences) { d in
                    GridRow {
                        Label(d.label, systemImage: d.meaningful ? "arrow.left.arrow.right.circle.fill" : "circle")
                            .labelStyle(.titleAndIcon).foregroundStyle(d.meaningful ? .primary : .secondary)
                        Text(value(d.a, d)); Text(value(d.b, d))
                        Text((d.difference >= 0 ? "+" : "") + value(d.difference, d)).fontWeight(d.meaningful ? .semibold : .regular)
                        Text(d.athlete_sd.map { value($0, d) } ?? "—").foregroundStyle(.secondary)
                    }.monospacedDigit()
                }
            }.font(.callout)
            Text("Filled icon = larger than this athlete's usual throw-to-throw spread and larger than measurement error.")
                .font(.caption).foregroundStyle(.secondary)
            if flights.count == 2 { flightOverlay }
        }
    }

    private var flightOverlay: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Bag flight paths from release").font(.headline)
            Chart {
                ForEach(flights, id: \.name) { flight in
                    ForEach(flight.samples) { s in
                        LineMark(x: .value("Forward (arm lengths)", s.forward), y: .value("Up (arm lengths)", s.up),
                                 series: .value("Segment", "\(flight.name)#\(s.segment)"))
                            .foregroundStyle(by: .value("Throw", flight.name))
                            .lineStyle(by: .value("Throw", flight.name))
                    }
                    if let last = flight.samples.last {
                        PointMark(x: .value("Forward (arm lengths)", last.forward), y: .value("Up (arm lengths)", last.up))
                            .foregroundStyle(by: .value("Throw", flight.name))
                            .annotation(position: .top) { Text(flight.name).font(.caption2).foregroundStyle(.secondary) }
                    }
                }
            }
            // A = dashed neutral, B = solid blue: identity never relies on hue alone.
            .chartForegroundStyleScale([flights[0].name: Color.secondary, flights[1].name: scoredInk])
            .chartLineStyleScale([flights[0].name: StrokeStyle(lineWidth: 2, dash: [6, 4]), flights[1].name: StrokeStyle(lineWidth: 2)])
            .chartXAxisLabel("Forward from release (arm lengths)")
            .chartYAxisLabel("Height above release (arm lengths)")
            .chartLegend(position: .top, alignment: .leading)
            .chartXScale(domain: xDomain)
            .chartYScale(domain: yDomain)
            // Equal units on both axes so the drawn launch angle is the true image angle.
            .aspectRatio((xDomain.upperBound - xDomain.lowerBound) / (yDomain.upperBound - yDomain.lowerBound), contentMode: .fit)
            .frame(maxHeight: 420)
            Text("Equal scale on both axes. Reviewed bag centres, starting at each throw's release point and scaled by each athlete's arm length so zoom differences cancel. Assumes the same fixed side-camera setup; gaps are not joined.")
                .font(.caption).foregroundStyle(.secondary)
        }
    }

    private var allSamples: [NormalizedFlight.Sample] { flights.flatMap(\.samples) }
    private var xDomain: ClosedRange<Double> { padded(allSamples.map(\.forward)) }
    private var yDomain: ClosedRange<Double> { padded(allSamples.map(\.up)) }
    private func padded(_ values: [Double]) -> ClosedRange<Double> {
        let low = min(values.min() ?? 0, 0), high = max(values.max() ?? 1, 0)
        let pad = max((high - low) * 0.08, 0.2)
        return (low - pad)...(high + pad)
    }

    private func value(_ x: Double, _ d: ThrowComparison.Difference) -> String {
        number(x, digits: d.decimals) + (d.unit == "°" ? "°" : " \(d.unit)")
    }
    private func outcomeText(_ score: Int?) -> String {
        switch score { case 3: "hole (3)"; case 1: "board (1)"; case 0: "miss (0)"; default: "not recorded" }
    }
}
