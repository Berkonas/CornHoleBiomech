import Charts
import SwiftUI

/// GOOD / WARNING / POOR per measurement stage, with the rule in the tooltip.
struct TrustStrip: View {
    let grades: [String: String]
    var body: some View {
        HStack(spacing: 8) {
            Text("Data quality").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
            ForEach(["pose", "bag", "release", "calibration"], id: \.self) { stage in
                let grade = grades[stage]
                HStack(spacing: 4) {
                    Circle().fill(gradeColor(grade)).frame(width: 7, height: 7)
                    Text("\(title(stage)) \(grade.map { $0.capitalized } ?? "—")").font(.caption)
                }
                .padding(.horizontal, 8).padding(.vertical, 3)
                .background(gradeColor(grade).opacity(0.1), in: Capsule())
                .help(help(stage))
            }
        }
    }
    private func title(_ stage: String) -> String {
        ["pose": "Body tracking", "bag": "Bag tracking", "release": "Release", "calibration": "Scale"][stage] ?? stage
    }
    private func help(_ stage: String) -> String {
        switch stage {
        case "pose": "Throwing arm and trunk visible in ≥90% of frames and around release."
        case "bag": "Bag found in ≥90% of flight frames, no gap longer than 3 frames, low noise."
        case "release": "Release confirmed, or the two automatic release cues agree within 3 frames."
        default: "GOOD needs a measured scale (meter stick) that agrees with the bag's fall. WARNING = fall-based scale only: metres are approximate."
        }
    }
}

/// Coach-facing metrics for one throw, grouped, each with its reliability and a jump-to-video button.
struct CoachMetricsPanel: View {
    let document: CoachMetricsDocument
    let groups: [String]
    let seek: (Int) -> Void
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            ForEach(groups, id: \.self) { group in
                let rows = document.rows(group: group)
                if !rows.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(group.uppercased()).font(.system(size: 10, weight: .semibold)).tracking(0.8).foregroundStyle(.secondary)
                        LazyVGrid(columns: [GridItem(.adaptive(minimum: 200), spacing: 12, alignment: .top)], spacing: 12) {
                            ForEach(rows) { row in tile(row) }
                        }
                    }
                }
            }
        }
    }
    private func tile(_ row: CoachMetricRow) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(alignment: .firstTextBaseline) {
                Text(row.label).font(.callout.weight(.medium))
                Spacer(minLength: 4)
                if let frame = row.frame {
                    Button { seek(frame) } label: { Image(systemName: "play.rectangle") }
                        .buttonStyle(.borderless).help("Show this moment in the replay (frame \(frame))")
                }
            }
            if row.status == "unreliable" {
                Text("Insufficient tracking quality").font(.callout).foregroundStyle(.secondary)
            } else {
                Text(formatValue(row.value, unit: row.unit)).font(.title2.weight(.semibold)).monospacedDigit()
            }
            HStack(spacing: 4) {
                Circle().fill(row.statusColor).frame(width: 6, height: 6)
                Text(row.statusText).font(.caption2).foregroundStyle(row.statusColor)
            }
            Text(row.definition).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            if !row.reasons.isEmpty {
                Text(row.reasons.joined(separator: " ")).font(.caption2).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(12).frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(.separator.opacity(0.5)))
        .accessibilityElement(children: .combine)
    }
}

/// Wrist speed through the throw, time relative to release, with the key events marked.
/// Clicking the chart seeks the replay to that moment.
struct WristSpeedChart: View {
    let speed: [Double?]
    let fps: Double
    let events: [String: Int?]
    let currentFrame: Int
    let seek: (Int) -> Void

    private var release: Int? { events["release"] ?? nil }
    private var window: ClosedRange<Int> {
        let r = release ?? speed.count / 2
        return max(0, (events["peak_backswing"] ?? nil).map { $0 - 10 } ?? r - 50)...min(speed.count - 1, r + 20)
    }
    private func ms(_ frame: Int) -> Double { 1000 * Double(frame - (release ?? 0)) / fps }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Wrist speed through the throw").font(.headline)
            Chart {
                ForEach(Array(window), id: \.self) { frame in
                    if let value = speed[safe: frame] ?? nil {
                        LineMark(x: .value("Time from release (ms)", ms(frame)), y: .value("Wrist speed (arm lengths/s)", value))
                            .foregroundStyle(Color.teal).interpolationMethod(.monotone)
                    }
                }
                ForEach([("peak_backswing", "Top of backswing"), ("peak_wrist_speed", "Peak wrist speed"), ("release", "Release")], id: \.0) { key, label in
                    if let frame = events[key] ?? nil {
                        RuleMark(x: .value("Event", ms(frame)))
                            .foregroundStyle(eventColor(key).opacity(0.8))
                            .lineStyle(StrokeStyle(lineWidth: 1.5, dash: key == "release" ? [] : [4, 3]))
                            // Release labels to the right of its line, the others to the left, so neighbours never overlap.
                            .annotation(position: .top, alignment: key == "release" ? .leading : .trailing) {
                                Text(label).font(.caption2).foregroundStyle(.secondary)
                            }
                    }
                }
                RuleMark(x: .value("Now", ms(currentFrame))).foregroundStyle(Color.primary.opacity(0.35)).lineStyle(StrokeStyle(lineWidth: 1))
            }
            .chartXAxisLabel("Time relative to release (ms)")
            .chartYAxisLabel("Wrist speed (arm lengths/s)")
            .chartOverlay { proxy in
                GeometryReader { geometry in
                    Rectangle().fill(.clear).contentShape(Rectangle()).onTapGesture { location in
                        guard let plot = proxy.plotFrame else { return }
                        let x = location.x - geometry[plot].origin.x
                        if let time: Double = proxy.value(atX: x) {
                            seek((release ?? 0) + Int((time / 1000 * fps).rounded()))
                        }
                    }
                }
            }
            .frame(height: 200)
            Text("Camera-steadied wrist speed from the filtered pose (6 Hz), in arm lengths per second so throws from different distances compare. Click the chart to show that moment in the replay.")
                .font(.caption).foregroundStyle(.secondary)
        }
    }
}
