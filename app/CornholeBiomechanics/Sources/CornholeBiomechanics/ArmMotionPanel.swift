import Charts
import SwiftUI

struct ArmMotionAnalysis: Codable {
    var status: String
    var summaries: [String: Double?]
    var start_frame: Int?
    var release_frame: Int?
    var sample_count: Int
    var valid_sample_count: Int
    var coverage: Double?
    var radius_coverage: Double?
    var message: String
}

struct ArmMotionPanel: View {
    let result: ArmMotionAnalysis?
    let normalized: NormalizedDocument?
    let stale: Bool
    @Binding var fraction: Double

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text("Elbow motion during the forward swing").font(.title2.weight(.semibold))
                Spacer()
            }
            if stale {
                Label("Reanalyze this throw after corrections to update arm-motion measurements.", systemImage: "arrow.triangle.2.circlepath").foregroundStyle(.orange)
            } else if let result {
                Text(result.message).font(.callout).foregroundStyle(.secondary)
                if result.status == "available" {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 180))], alignment: .leading, spacing: 18) {
                        metric("Mean elbow flexion", key: "arm_motion_mean_flexion_deg", unit: "°", note: "0° = straight in this projection")
                        metric("Elbow excursion", key: "arm_motion_flexion_rom_deg", unit: "°", note: "Maximum − minimum flexion")
                        metric("Within-swing flexion SD", key: "arm_motion_flexion_sd_deg", unit: "°", note: "Sample SD; variation within this throw")
                        metric("Wrist-radius variability", key: "arm_motion_radius_cv_ratio", unit: "%", note: "100 × sample SD / mean radius", multiplier: 100)
                    }
                    if let normalized, let angles = normalized.values["elbow_angle_deg"]?.scalars {
                        ArmFlexionChart(tau: normalized.tau, angles: angles,
                            start: normalized.eventTiming["forward_swing"] ?? nil,
                            release: normalized.eventTiming["release"] ?? nil, fraction: $fraction)
                        Text("Shaded interval: forward swing → release. Flexion = 180° − included elbow angle. Chart uses the normalized cycle; summary metrics use the original filtered frame samples. Gaps remain disconnected.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
                if let coverage = result.coverage {
                    Text("Frames \(result.start_frame.map(String.init) ?? "—")–\(result.release_frame.map(String.init) ?? "—") (zero-based, inclusive) · \(result.valid_sample_count)/\(result.sample_count) usable elbow samples (\(number(coverage*100))%) · radius coverage \(result.radius_coverage.map { number($0*100) + "%" } ?? "unavailable")")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Text("Availability requires a side view, ≥5 usable samples and ≥80% phase coverage. These are practical data gates, not validated accuracy thresholds. Review automatic event candidates before interpretation. Remaining gaps can hide motion peaks.")
                    .font(.caption).foregroundStyle(.secondary)
            } else {
                Text("Analyze or reanalyze this throw to calculate the new arm-motion metrics. The model explorer is available now.").foregroundStyle(.secondary)
            }
            Text("Low excursion describes a more fixed elbow within this throw. It does not by itself mean better performance; compare scored and missed throws to see whether it matters for this athlete.")
                .font(.caption).foregroundStyle(.secondary)
        }.padding(18).background(.quaternary.opacity(0.45), in: RoundedRectangle(cornerRadius: 12))
    }

    private func metric(_ title: String, key: String, unit: String, note: String, multiplier: Double = 1) -> some View {
        let value = (result?.summaries[key] ?? nil).map { $0 * multiplier }
        return VStack(alignment: .leading, spacing: 5) {
            Text(title).font(.callout.weight(.medium))
            Text("\(number(value, digits: 1)) \(unit)").font(.title2.monospacedDigit())
            Text(note).font(.caption).foregroundStyle(.secondary)
        }
    }
}

private struct ArmFlexionChart: View {
    struct Sample: Identifiable { let id: Int; let x: Double; let y: Double; let segment: Int }
    let tau: [Double]
    let angles: [Double?]
    let start: Double?
    let release: Double?
    @Binding var fraction: Double
    var samples: [Sample] {
        var segment = 0
        return tau.enumerated().compactMap { i, t in
            guard i < angles.count, let a = angles[i], a.isFinite, (0...180).contains(a) else { segment += 1; return nil }
            return Sample(id: i, x: t*100, y: 180-a, segment: segment)
        }
    }
    var body: some View {
        Chart {
            if let start, let release, start < release {
                RectangleMark(xStart: .value("Forward swing", start*100), xEnd: .value("Release", release*100), yStart: .value("Min", 0), yEnd: .value("Max", 180))
                    .foregroundStyle(athleteInk.opacity(0.08))
                RuleMark(x: .value("Release", release*100)).foregroundStyle(.orange)
                    .annotation(position: .top) { Text("Release").font(.caption) }
            }
            ForEach(samples) { p in
                LineMark(x: .value("Cycle", p.x), y: .value("Flexion", p.y), series: .value("Run", p.segment))
                    .foregroundStyle(athleteInk).lineStyle(StrokeStyle(lineWidth: 2.5))
            }
            RuleMark(x: .value("Video cursor", fraction*100)).foregroundStyle(.secondary).lineStyle(StrokeStyle(dash: [3,3]))
        }.chartXScale(domain: 0...100).chartYScale(domain: 0...180)
            .chartXAxisLabel("Movement cycle (%)").chartYAxisLabel("Projected elbow flexion (°)")
            .frame(height: 210)
            .chartOverlay { proxy in
                GeometryReader { geometry in
                    Rectangle().fill(.clear).contentShape(Rectangle()).gesture(DragGesture(minimumDistance: 0).onChanged { value in
                        guard let frame = proxy.plotFrame else { return }
                        if let x: Double = proxy.value(atX: value.location.x - geometry[frame].origin.x) { fraction = min(1, max(0, x/100)) }
                    })
                }
            }.accessibilityLabel("Projected elbow flexion, zero is straight; shaded forward-swing interval. Drag to seek the synchronized video below.")
    }
}
