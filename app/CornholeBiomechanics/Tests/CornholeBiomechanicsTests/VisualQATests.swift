import AppKit
import SwiftUI
import XCTest
@testable import CornholeBiomechanics

/// Opt-in rendering of the coach-facing views to PNG for visual review.
/// Runs only when CORNHOLE_VISUAL_QA points to an input/output folder containing
/// replay.json, results.json, pose_raw.json (optional), frame_*.png and dashboard JSON files.
final class VisualQATests: XCTestCase {
    @MainActor func testRenderCoachViews() throws {
        guard let folder = ProcessInfo.processInfo.environment["CORNHOLE_VISUAL_QA"] else {
            throw XCTSkip("Set CORNHOLE_VISUAL_QA to render views for visual review.")
        }
        let dir = URL(fileURLWithPath: folder)
        func render<V: View>(_ view: V, _ name: String, width: CGFloat, height: CGFloat, dark: Bool = false) throws {
            let root = view.frame(width: width, height: height, alignment: .topLeading)
                .background(Color(nsColor: .windowBackgroundColor))
                .environment(\.colorScheme, dark ? .dark : .light)
            let hosting = NSHostingView(rootView: root)
            hosting.appearance = NSAppearance(named: dark ? .darkAqua : .aqua)
            hosting.frame = NSRect(x: 0, y: 0, width: width, height: height)
            hosting.layoutSubtreeIfNeeded()
            let bitmap = try XCTUnwrap(hosting.bitmapImageRepForCachingDisplay(in: hosting.bounds))
            hosting.cacheDisplay(in: hosting.bounds, to: bitmap)
            try XCTUnwrap(bitmap.representation(using: .png, properties: [:])).write(to: dir.appendingPathComponent("\(name).png"))
        }
        let replay = try XCTUnwrap(ReplayDocument.load(dir.appendingPathComponent("replay.json")))
        let pose = try? JSONDecoder().decode(PoseDocument.self, from: Data(contentsOf: dir.appendingPathComponent("pose_raw.json")))
        let frames = try FileManager.default.contentsOfDirectory(atPath: folder).filter { $0.hasPrefix("frame_") && $0.hasSuffix(".png") }
        for file in frames {
            let frame = Int(file.split(separator: "_").last!.dropLast(4))!
            let image = try XCTUnwrap(NSImage(contentsOf: dir.appendingPathComponent(file)))
            let size = CGSize(width: 1280, height: 720)
            try render(ZStack {
                Image(nsImage: image).resizable().aspectRatio(contentMode: .fit)
                ReplayOverlay(replay: replay, pose: pose, side: .right, frame: frame, size: size,
                              showSkeleton: true, showModel: true, showTrail: true)
            }.frame(width: size.width, height: size.height).background(Color.black), "replay_\(file.dropLast(4))", width: 1280, height: 720)
        }
        if let coach = CoachMetricsDocument.load(dir.appendingPathComponent("results.json")) {
            // Throw report page, light and dark, from the same folder (video replaced by the animation view).
            let insight = try? JSONDecoder.projectDecoder.decode(TrialInsights.self, from: Data(contentsOf: dir.appendingPathComponent("insights.json")))
            let results = try? JSONDecoder.projectDecoder.decode(AnalysisResults.self, from: Data(contentsOf: dir.appendingPathComponent("results.json")))
            let kinematics = VisualQATests.csv(dir.appendingPathComponent("kinematics.csv"))
            let trial = Trial(athleteID: UUID(), sourceVideoRelativePath: "throw.mov", originalFilename: "throw.mov",
                              cameraView: .side, throwingSide: .right, targetDirection: .leftToRight,
                              outcome: TrialOutcome(scoreCategory: .onBoard), analysisRelativePath: "analysis", name: "Throw 6")
            let history: [String: [Double]] = [
                "bag_release_speed_m_s": [7.4, 7.9, 6.6, 8.6, 7.6, 7.2], "bag_release_angle_deg": [33, 36, 30, 38, 41, 35],
                "bag_release_height_m": [0.82, 0.85, 0.8, 0.78, 0.9, 0.8], "elbow_angle_deg_at_release": [150, 158, 162, 147, 155],
                "trunk_inclination_deg_at_release": [20, 24, 18, 26, 22], "wrist_peak_speed_arm_lengths_s": [10.5, 11.2, 9.8, 11.9],
                "swing_backswing_angle_deg": [-50, -58, -61, -55], "swing_tempo_ratio": [1.6, 1.9, 1.7, 2.0]]
            var data = ThrowReportData(insight: insight, coach: coach, replay: replay, pose: pose, results: results,
                                       kinematics: kinematics, scale: FlightScale.load(results: dir.appendingPathComponent("results.json")),
                                       launchFit: LaunchFitSummary.load(results: dir.appendingPathComponent("results.json")),
                                       history: history, analysisURL: dir)
            data.manifest = ManifestInfo.load(dir.appendingPathComponent("manifest.json"))
            data.derive()
            var stale = data; stale.staleReason = "corrections_changed"
            try render(ThrowReportContent(trial: trial, athleteName: "Player 1", data: stale, videoURL: nil, videoAvailable: false,
                                          currentFrame: .constant(replay.events["release"]?.frame ?? 0), seekRequest: .constant(nil)),
                       "throw_report_stale", width: 1180, height: 1300)
            try render(ThrowReportContent(trial: trial, athleteName: "Player 1", data: data, videoURL: nil, videoAvailable: false,
                                          progress: ReportProgress(stage: "Tracking the body", detail: "Frame 120 of 343", fraction: 0.42),
                                          currentFrame: .constant(replay.events["release"]?.frame ?? 0), seekRequest: .constant(nil)),
                       "throw_report_running", width: 1180, height: 1300)
            for dark in [false, true] {
                try render(ThrowReportContent(trial: trial, athleteName: "Player 1", data: data, videoURL: nil, videoAvailable: false,
                                              currentFrame: .constant(replay.events["release"]?.frame ?? 0), seekRequest: .constant(nil)),
                           "throw_report\(dark ? "_dark" : "")", width: 1180, height: 3200, dark: dark)
            }
            try render(ThrowReportContent(trial: trial, athleteName: "Player 1", data: data, videoURL: nil, videoAvailable: false,
                                          currentFrame: .constant(replay.events["release"]?.frame ?? 0), seekRequest: .constant(nil)),
                       "throw_report_narrow", width: 820, height: 4200)
            try render(ThrowReportContent(trial: trial, athleteName: "Player 1", data: data, videoURL: nil, videoAvailable: false,
                                          currentFrame: .constant(replay.events["release"]?.frame ?? 0), seekRequest: .constant(nil),
                                          showsDetails: true),
                       "throw_report_details", width: 1180, height: 5200)
        }
        for name in ["dashboard", "demo_dashboard"] {
            let url = dir.appendingPathComponent("\(name).json")
            guard FileManager.default.fileExists(atPath: url.path) else { continue }
            let dashboard = try XCTUnwrap(AthleteDashboard.load(url), "\(name).json did not decode")
            let consistency = (try? JSONDecoder.projectDecoder.decode(TrialInsights.self, from: Data(contentsOf: dir.appendingPathComponent("insights.json"))))?.consistency
            let rows = VisualQATests.summaryRows(dashboard)
            try render(AthleteSummaryContent(dashboard: dashboard, rows: rows, consistency: consistency, open: { _ in },
                                             athleteName: dashboard.athlete, showsDetails: true),
                       "athlete_summary_\(name)", width: 1180, height: 3600)
            // Same throws with results entered (synthetic), light and dark.
            let scored = VisualQATests.withScores(dashboard, rows: rows)
            for dark in [false, true] {
                try render(AthleteSummaryContent(dashboard: scored.dashboard, rows: scored.rows, consistency: consistency, open: { _ in },
                                                 athleteName: dashboard.athlete, showsDetails: true),
                           "athlete_summary_\(name)_scored\(dark ? "_dark" : "")", width: 1180, height: 3600, dark: dark)
            }
            try render(AthleteSummaryContent(dashboard: scored.dashboard, rows: scored.rows, consistency: consistency, open: { _ in },
                                             athleteName: dashboard.athlete),
                       "athlete_summary_\(name)_narrow", width: 820, height: 4200)
            // Only three bags with a result: the scoring tiles carry the early-estimate caption.
            let fewBags = VisualQATests.withScores(dashboard, rows: rows, limit: 3)
            try render(AthleteSummaryContent(dashboard: fewBags.dashboard, rows: fewBags.rows, consistency: consistency, open: { _ in },
                                             athleteName: dashboard.athlete, actions: SummaryActions(recordResults: {})),
                       "athlete_summary_\(name)_few_bags", width: 1180, height: 900)
        }
        // Edge cases: no throws; throws but none analysed; three analysed throws, no dashboard or results.
        try render(AthleteSummaryContent(dashboard: nil, rows: [], consistency: nil, open: { _ in }, athleteName: "Player 4", throwCount: 0),
                   "athlete_summary_empty", width: 1180, height: 700)
        var actions = SummaryActions()
        actions.analyzeFirst = ("Analyze Throw 1", {})
        try render(AthleteSummaryContent(dashboard: nil, rows: [], consistency: nil, open: { _ in }, athleteName: "Player 4", throwCount: 3,
                                         resultCount: 0, actions: actions, showsDetails: true),
                   "athlete_summary_unanalysed", width: 1180, height: 1500)
        let few = (0..<3).map { i in
            SummaryThrowRow(id: UUID(), number: i + 1, label: "Throw \(i + 1)", score: nil,
                            values: ["bag_release_speed_m_s": 7.4 + 0.3 * Double(i), "bag_release_angle_deg": 34 + Double(i),
                                     "bag_release_height_m": 0.82, "swing_tempo_ratio": 1.8],
                            withheld: ["elbow_angle_deg_at_release": "Elbow hidden behind the trunk at release."],
                            grades: ["pose": "GOOD", "bag": "WARNING", "release": "GOOD", "calibration": "WARNING"])
        }
        try render(AthleteSummaryContent(dashboard: nil, rows: few, consistency: nil, open: { _ in }, athleteName: "Player 4", throwCount: 3,
                                         actions: SummaryActions(recordResults: {}, prepareConsistency: {})),
                   "athlete_summary_few", width: 1180, height: 2000)
    }

    /// Table rows rebuilt from the dashboard's release profile (one row per trial it lists).
    static func summaryRows(_ dashboard: AthleteDashboard) -> [SummaryThrowRow] {
        var byTrial: [String: [String: Double]] = [:]
        for profile in dashboard.release_profile {
            for value in profile.values { byTrial[value.trial_id, default: [:]][profile.key] = value.value }
        }
        let ids = (dashboard.trial_labels ?? [:]).keys.sorted { (dashboard.trial_labels?[$0] ?? $0) < (dashboard.trial_labels?[$1] ?? $1) }
        return ids.enumerated().compactMap { index, id in
            guard let uuid = UUID(uuidString: id) else { return nil }
            var row = SummaryThrowRow(id: uuid, number: index + 1, label: dashboard.trial_labels?[id] ?? "Throw \(index + 1)", score: nil,
                                      values: byTrial[id] ?? [:], grades: ["pose": "GOOD", "bag": "GOOD", "release": "GOOD", "calibration": "WARNING"])
            if row.values["elbow_angle_deg_at_release"] == nil { row.withheld["elbow_angle_deg_at_release"] = "Elbow not visible at release." }
            if index == 2 { row.grades["bag"] = "POOR" }
            if index == 4 { row.isStale = true }
            row.distance = 7.4 + 0.05 * Double(index % 3)
            return row
        }
    }

    /// Synthetic results (hole, board, miss, board, none …) on rows and dashboard, for rendering the scored state.
    static func withScores(_ dashboard: AthleteDashboard, rows: [SummaryThrowRow], limit: Int = .max) -> (dashboard: AthleteDashboard, rows: [SummaryThrowRow]) {
        let cycle: [ScoreCategory?] = [.throughHole, .onBoard, .offBoard, .onBoard, nil, .offBoard, .throughHole]
        var scores: [String: ScoreCategory?] = [:]
        let rows = rows.enumerated().map { index, row in
            var row = row; row.score = index < limit ? cycle[index % cycle.count] : nil; scores[row.id.uuidString] = row.score; return row
        }
        var d = dashboard
        for p in d.release_profile.indices {
            for v in d.release_profile[p].values.indices {
                d.release_profile[p].values[v].score = (scores[d.release_profile[p].values[v].trial_id] ?? nil)?.rawValue
            }
        }
        let recorded = rows.compactMap(\.score)
        let points = recorded.map(\.rawValue).reduce(0, +)
        func share(_ s: ScoreCategory) -> Double { 100 * Double(recorded.filter { $0 == s }.count) / Double(max(recorded.count, 1)) }
        d.throws_with_outcome = recorded.count
        d.performance.sports = AthleteDashboard.Sports(bags: recorded.count, points_per_bag: Double(points) / Double(max(recorded.count, 1)),
                                                        ppr: 4 * Double(points) / Double(max(recorded.count, 1)),
                                                        in_percent: share(.throughHole), on_percent: share(.onBoard), off_percent: share(.offBoard))
        d.performance.counts = ["unknown": rows.count - recorded.count]
        return (d, rows)
    }

    static func csv(_ url: URL) -> [[String: String]] {
        guard let content = try? String(contentsOf: url, encoding: .utf8) else { return [] }
        let lines = content.split(whereSeparator: \.isNewline).map(String.init)
        guard let first = lines.first else { return [] }
        let headers = first.split(separator: ",", omittingEmptySubsequences: false).map(String.init)
        return lines.dropFirst().map { Dictionary(uniqueKeysWithValues: zip(headers, $0.split(separator: ",", omittingEmptySubsequences: false).map(String.init))) }
    }
}
