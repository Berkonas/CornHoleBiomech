import AVFoundation
import AVKit
import Charts
import SwiftUI

struct CompareView: View {
    @EnvironmentObject private var store: ProjectStore
    @EnvironmentObject private var analysis: AnalysisService
    @StateObject private var data = TrialDataController()
    @State private var testTrialID: UUID?
    @State private var comparisonURL: URL?
    @State private var errorMessage: String?

    var body: some View {
        SectionContainer(
            title: "Reference Comparison",
            subtitle: "Raw biomechanical differences first; transparent component scores second."
        ) {
            HStack {
                Picker("Athlete trial", selection: $testTrialID) {
                    Text("Choose analyzed trial…").tag(UUID?.none)
                    ForEach(testTrials) { Text("\(athleteName($0.athleteID)) — \($0.originalFilename)").tag(Optional($0.id)) }
                }.frame(maxWidth: 460)
                Button("Run Comparison") { runComparison() }.buttonStyle(.borderedProminent)
                    .disabled(selectedTest == nil || compatibleReferences.isEmpty || analysis.isRunning)
                Text("\(compatibleReferences.count) compatible reference\(compatibleReferences.count == 1 ? "" : "s")")
                    .font(.caption).foregroundStyle(.secondary)
            }
            if compatibleReferences.isEmpty {
                Label("Mark at least one analyzed trial with the same view label as a reference.", systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
            }
            if let errorMessage { Label(errorMessage, systemImage: "xmark.circle").foregroundStyle(.red) }
            if let comparison = data.comparison, let test = selectedTest, let reference = compatibleReferences.first,
               let testVideo = store.videoURL(for: test), let referenceVideo = store.videoURL(for: reference),
               let testAnalysis = store.analysisURL(for: test), let referenceAnalysis = store.analysisURL(for: reference) {
                SynchronizedVideoPair(
                    referenceURL: referenceVideo, testURL: testVideo,
                    referenceAnalysis: referenceAnalysis, testAnalysis: testAnalysis,
                    referenceLabel: compatibleReferences.count == 1 ? reference.originalFilename : "Reference set lead trial",
                    testLabel: test.originalFilename
                )
                if let curves = comparison.curves { ComparisonCurvesView(curves: curves) }
                HStack {
                    Button("Show Comparison Files") { if let comparisonURL { store.reveal(comparisonURL) } }
                    Button("Export Comparison…") {
                        if let comparisonURL { store.exportFolder(at: comparisonURL, suggestedName: "Comparison-\(test.shortID)-export") }
                    }
                }
                HStack(alignment: .top, spacing: 16) {
                    similarityPanel(comparison)
                    rawMetricsPanel(comparison)
                }
                Text("Reference similarity describes deviation from the selected reference—not performance quality. Time normalization preserves the within-cycle timing comparison; no dynamic time warping is used as the primary result.")
                    .font(.caption).foregroundStyle(.secondary)
            } else {
                ResearchCard(title: "Comparison workflow", symbol: "rectangle.split.2x1") {
                    Text("Choose an analyzed athlete trial, ensure a compatible reference is marked, then run the local comparison. Playback is synchronized by the detected movement interval. The normalized arm graphic aligns throwing shoulders, scales by robust arm length, and reflects target direction into a common forward axis.")
                }
            }
        }
        .onAppear {
            if testTrialID == nil { testTrialID = testTrials.first?.id }
            loadExisting()
        }
        .onChange(of: testTrialID) { _, _ in loadExisting() }
    }

    private var testTrials: [Trial] { store.analyzedTrials.filter { !$0.isReference } }
    private var selectedTest: Trial? { store.analyzedTrials.first { $0.id == testTrialID } }
    private var compatibleReferences: [Trial] {
        guard let selectedTest else { return [] }
        return store.analyzedTrials.filter { $0.isReference && $0.cameraView == selectedTest.cameraView }
    }
    private func athleteName(_ id: UUID) -> String { store.project?.athletes.first { $0.id == id }?.displayName ?? "Unknown athlete" }
    private func runComparison() {
        guard let test = selectedTest else { return }
        errorMessage = nil
        Task {
            do {
                let url = try await analysis.compare(test: test, references: compatibleReferences, store: store)
                comparisonURL = url; data.loadComparison(at: url)
            } catch { errorMessage = error.localizedDescription }
        }
    }
    private func loadExisting() {
        guard let root = store.projectURL, let testTrialID else { data.loadComparison(at: nil); return }
        let url = root.appendingPathComponent("comparisons/\(testTrialID.uuidString)")
        comparisonURL = url
        data.loadComparison(at: url)
    }

    private func similarityPanel(_ comparison: ComparisonDocument) -> some View {
        ResearchCard(title: comparison.label, symbol: "dial.medium") {
            HStack(alignment: .firstTextBaseline) {
                Text(comparison.similarity.overall.map { $0.formatted(.number.precision(.fractionLength(1))) } ?? "Unavailable")
                    .font(.system(size: 40, weight: .semibold, design: .rounded))
                Text("/ 100").foregroundStyle(.secondary)
            }
            ForEach(comparison.similarity.components.keys.sorted(), id: \.self) { key in
                if let component = comparison.similarity.components[key] {
                    DisclosureGroup {
                        Text("Raw error: \(component.rawError.formatted(.number.precision(.fractionLength(3)))) · tolerance: \(component.tolerance.formatted()) · weight: \(component.weight.formatted())")
                        Text(component.formula).font(.caption.monospaced())
                        Text("Tolerance is a provisional pilot setting, not a population norm.").font(.caption).foregroundStyle(.secondary)
                    } label: {
                        HStack { Text(readable(key)); Spacer(); Text(component.score, format: .number.precision(.fractionLength(1))).monospacedDigit() }
                    }
                }
            }
        }
    }
    private func rawMetricsPanel(_ comparison: ComparisonDocument) -> some View {
        ResearchCard(title: "Raw errors", symbol: "ruler") {
            ForEach(comparison.rawMetrics.keys.sorted(), id: \.self) { key in
                HStack {
                    Text(readable(key)).lineLimit(1)
                    Spacer()
                    Text(formatMetric(comparison.rawMetrics[key] ?? nil, key: key)).monospacedDigit()
                }.font(.callout)
            }
        }
    }
    private func readable(_ key: String) -> String { key.replacingOccurrences(of: "_", with: " ").capitalized }
    private func formatMetric(_ value: Double?, key: String) -> String {
        guard let value else { return "—" }
        if key.contains("correlation") { return value.formatted(.number.precision(.fractionLength(3))) }
        if key.contains("cycle") { return value.formatted(.percent.precision(.fractionLength(1))) }
        if key.contains("deg") { return "\(value.formatted(.number.precision(.fractionLength(2))))°" }
        return value.formatted(.number.precision(.fractionLength(3)))
    }
}

private struct SynchronizedVideoPair: View {
    let referenceURL: URL
    let testURL: URL
    let referenceAnalysis: URL
    let testAnalysis: URL
    let referenceLabel: String
    let testLabel: String
    @State private var referencePlayer: AVPlayer
    @State private var testPlayer: AVPlayer
    @State private var movementPercent = 0.0
    @State private var isPlaying = false
    @State private var referenceBounds = 0.0...1.0
    @State private var testBounds = 0.0...1.0
    private let timer = Timer.publish(every: 1.0 / 30.0, on: .main, in: .common).autoconnect()

    init(referenceURL: URL, testURL: URL, referenceAnalysis: URL, testAnalysis: URL, referenceLabel: String, testLabel: String) {
        self.referenceURL = referenceURL; self.testURL = testURL
        self.referenceAnalysis = referenceAnalysis; self.testAnalysis = testAnalysis
        self.referenceLabel = referenceLabel; self.testLabel = testLabel
        _referencePlayer = State(initialValue: AVPlayer(url: referenceURL))
        _testPlayer = State(initialValue: AVPlayer(url: testURL))
    }

    var body: some View {
        VStack(spacing: 10) {
            HStack(spacing: 12) {
                video(referencePlayer, title: "REFERENCE", filename: referenceLabel)
                video(testPlayer, title: "ATHLETE", filename: testLabel)
            }
            HStack {
                Button { isPlaying.toggle() } label: { Label(isPlaying ? "Pause" : "Play synchronized", systemImage: isPlaying ? "pause.fill" : "play.fill") }
                Slider(value: $movementPercent, in: 0...1).onChange(of: movementPercent) { _, _ in seek() }
                Text(movementPercent, format: .percent.precision(.fractionLength(0))).monospacedDigit().frame(width: 48)
            }
            Text("Playback maps 0–100% between each trial’s effective motion start and end; actual video time remains frame-limited.")
                .font(.caption).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading)
        }
        .onAppear { referenceBounds = bounds(referenceAnalysis); testBounds = bounds(testAnalysis); seek() }
        .onReceive(timer) { _ in if isPlaying { movementPercent = min(1, movementPercent + 1.0 / 180.0); if movementPercent >= 1 { isPlaying = false } } }
    }
    private func video(_ player: AVPlayer, title: String, filename: String) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack { Text(title).font(.caption.weight(.bold)).foregroundStyle(.secondary); Spacer(); Text(filename).font(.caption).lineLimit(1) }
            VideoPlayer(player: player).aspectRatio(16 / 9, contentMode: .fit).background(.black)
        }
    }
    private func bounds(_ directory: URL) -> ClosedRange<Double> {
        guard let pose = try? JSONDecoder.projectDecoder.decode(PoseDocument.self, from: Data(contentsOf: directory.appendingPathComponent("pose_raw.json"))),
              let events = try? JSONDecoder.projectDecoder.decode(EventDocument.self, from: Data(contentsOf: directory.appendingPathComponent("events.json"))) else { return 0...1 }
        let start = Double(events.events["motion_start"]?.effectiveFrame ?? 0) / pose.fps
        let end = Double(events.events["motion_end"]?.effectiveFrame ?? max(1, pose.frameCount - 1)) / pose.fps
        return start...max(start + 1 / pose.fps, end)
    }
    private func seek() {
        referencePlayer.seek(to: CMTime(seconds: referenceBounds.lowerBound + movementPercent * (referenceBounds.upperBound - referenceBounds.lowerBound), preferredTimescale: 600), toleranceBefore: .zero, toleranceAfter: .zero)
        testPlayer.seek(to: CMTime(seconds: testBounds.lowerBound + movementPercent * (testBounds.upperBound - testBounds.lowerBound), preferredTimescale: 600), toleranceBefore: .zero, toleranceAfter: .zero)
    }
}

private struct CurveSample: Identifiable {
    let series: String; let percent: Double; let value: Double
    var id: String { "\(series)-\(percent)" }
}

private struct ComparisonCurvesView: View {
    let curves: ComparisonDocument.Curves
    @State private var cursor = 50.0
    var body: some View {
        HStack(alignment: .top, spacing: 16) {
            ResearchCard(title: "Time-normalized 2D projected elbow angle", symbol: "chart.xyaxis.line") {
                Chart(samples) { item in
                    LineMark(x: .value("Movement cycle (%)", item.percent), y: .value("Angle (degrees)", item.value))
                        .foregroundStyle(by: .value("Series", item.series))
                }
                .chartXScale(domain: 0...100)
                .chartXAxisLabel("Movement cycle (%)")
                .chartYAxisLabel("Projected angle (degrees)")
                .frame(height: 260)
                Slider(value: $cursor, in: 0...100)
            }
            ResearchCard(title: "Normalized throwing-arm alignment", symbol: "figure.arms.open") {
                GhostArmView(curves: curves, percent: cursor).frame(height: 260)
                Text("Shoulder-aligned; scale = robust arm length; forward direction reflected to a common axis. Blue is reference mean; red is athlete trial.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }
    private var samples: [CurveSample] {
        let test = curves.test["elbow_angle_deg"]?.scalars ?? []
        let reference = curves.referenceMean["elbow_angle_deg"]?.scalars ?? []
        var values: [CurveSample] = []
        for (index, tau) in curves.tau.enumerated() {
            if let value = test[safe: index] ?? nil { values.append(CurveSample(series: "Athlete", percent: tau * 100, value: value)) }
            if let value = reference[safe: index] ?? nil { values.append(CurveSample(series: "Reference mean", percent: tau * 100, value: value)) }
        }
        return values
    }
}

private struct GhostArmView: View {
    let curves: ComparisonDocument.Curves
    let percent: Double
    var body: some View {
        Canvas { context, size in
            let origin = CGPoint(x: size.width * 0.25, y: size.height * 0.55)
            draw(series: curves.referenceMean, color: .blue, context: &context, size: size, origin: origin)
            draw(series: curves.test, color: .red, context: &context, size: size, origin: origin)
            context.fill(Path(ellipseIn: CGRect(x: origin.x - 5, y: origin.y - 5, width: 10, height: 10)), with: .color(.primary))
        }
    }
    private func draw(series: [String: FlexibleNumericArray], color: Color, context: inout GraphicsContext, size: CGSize, origin: CGPoint) {
        let index = min(max(0, Int((percent / 100 * Double(max(0, curves.tau.count - 1))).rounded())), max(0, curves.tau.count - 1))
        guard let elbow = series["elbow_path_arm_lengths"]?.vectors?[safe: index] ?? nil,
              let wrist = series["wrist_path_arm_lengths"]?.vectors?[safe: index] ?? nil,
              elbow.count >= 2, wrist.count >= 2,
              let ex = elbow[0], let ey = elbow[1], let wx = wrist[0], let wy = wrist[1] else { return }
        let scale = min(size.width, size.height) * 0.32
        let ep = CGPoint(x: origin.x + ex * scale, y: origin.y - ey * scale)
        let wp = CGPoint(x: origin.x + wx * scale, y: origin.y - wy * scale)
        var path = Path(); path.move(to: origin); path.addLine(to: ep); path.addLine(to: wp)
        context.stroke(path, with: .color(color), lineWidth: 5)
        for point in [ep, wp] { context.fill(Path(ellipseIn: CGRect(x: point.x - 5, y: point.y - 5, width: 10, height: 10)), with: .color(color)) }
    }
}
