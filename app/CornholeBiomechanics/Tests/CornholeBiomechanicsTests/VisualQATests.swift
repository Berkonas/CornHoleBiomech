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
            try render(VStack(alignment: .leading, spacing: 16) {
                TrustStrip(grades: replay.grades)
                CoachMetricsPanel(document: coach, groups: ["Release", "Hand & wrist", "Arm", "Trunk", "Timing"]) { _ in }
                if let speed = coach.wrist_speed_arm_lengths_s, let events = coach.event_frames {
                    WristSpeedChart(speed: speed, fps: replay.fps, events: events, currentFrame: replay.events["release"]?.frame ?? 0) { _ in }
                }
            }.padding(24), "coach_metrics", width: 1100, height: 1500)
        }
        for name in ["dashboard", "demo_dashboard"] {
            if let dashboard = AthleteDashboard.load(dir.appendingPathComponent("\(name).json")) {
                try render(ScrollView { DashboardContent(dashboard: dashboard, trials: [], open: { _ in }, recordResults: {}).padding(24) },
                           name, width: 1100, height: 2300)
                try render(ScrollView { DashboardContent(dashboard: dashboard, trials: [], open: { _ in }, recordResults: {}).padding(24) },
                           "\(name)_dark", width: 1100, height: 1300, dark: true)
            } else if FileManager.default.fileExists(atPath: dir.appendingPathComponent("\(name).json").path) {
                XCTFail("\(name).json did not decode")
            }
        }
    }
}
