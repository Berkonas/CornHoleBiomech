import AppKit
import SwiftUI
import XCTest
@testable import CornholeBiomechanics

/// Opt-in rendering of the Launch Lab to PNG for visual review.
/// Runs only when CORNHOLE_LAUNCH_QA names an output folder.
final class LaunchLabVisualQATests: XCTestCase {
    @MainActor func testRenderLaunchLab() throws {
        guard let folder = ProcessInfo.processInfo.environment["CORNHOLE_LAUNCH_QA"] else {
            throw XCTSkip("Set CORNHOLE_LAUNCH_QA to an output folder to render the Launch Lab.")
        }
        let dir = URL(fileURLWithPath: folder)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        func render<V: View>(_ view: V, _ name: String, width: CGFloat, height: CGFloat, dark: Bool = false) throws {
            let root = view.frame(width: width, height: height, alignment: .topLeading)
                .background(Color(nsColor: .windowBackgroundColor))
                .environment(\.colorScheme, dark ? .dark : .light)
            let hosting = NSHostingView(rootView: root)
            hosting.appearance = NSAppearance(named: dark ? .darkAqua : .aqua)
            hosting.frame = NSRect(x: 0, y: 0, width: width, height: height)
            hosting.layoutSubtreeIfNeeded()
            RunLoop.main.run(until: Date().addingTimeInterval(0.3))
            let bitmap = try XCTUnwrap(hosting.bitmapImageRepForCachingDisplay(in: hosting.bounds))
            hosting.cacheDisplay(in: hosting.bounds, to: bitmap)
            try XCTUnwrap(bitmap.representation(using: .png, properties: [:])).write(to: dir.appendingPathComponent("\(name).png"))
        }
        let base = LaunchLabContent.defaultParameters
        var high = base; high.angleDegrees = 55; high.speed = 8.4
        var low = base; low.angleDegrees = 22; low.speed = 8.9
        let ghosts = [high, low]
        let athlete: [MeasuredRelease] = [
            .init(id: UUID(), label: "Throw 1", speed: 7.4, angle: 33, height: 0.82, score: .throughHole),
            .init(id: UUID(), label: "Throw 2", speed: 7.9, angle: 36, height: 0.85, score: .onBoard),
            .init(id: UUID(), label: "Throw 3", speed: 6.6, angle: 30, height: 0.80, score: .offBoard),
            .init(id: UUID(), label: "Throw 4", speed: 8.6, angle: 38, height: 0.78, score: .offBoard),
            .init(id: UUID(), label: "Throw 5", speed: 7.6, angle: 41, height: 0.9, score: nil),
            .init(id: UUID(), label: "Throw 6", speed: 7.2, angle: 35, height: 0.8, score: .onBoard),
        ]
        for dark in [false, true] {
            let suffix = dark ? "_dark" : ""
            try render(LaunchLabContent(measured: athlete, athleteSelected: true, ghosts: ghosts, animateOnAppear: false),
                       "launch_lab\(suffix)", width: 1180, height: 1900, dark: dark)
            for t in [0.0, 0.2, 0.35, 0.6, 0.9, 1.6] {
                try render(LaunchScene(params: base, ghosts: ghosts, frozenTime: t).padding(16).background(Color(nsColor: .controlBackgroundColor)),
                           "scene_t\(Int(t * 100))\(suffix)", width: 760, height: 380, dark: dark)
            }
        }
        var long = base; long.speed += 2
        var short = base; short.speed -= 1.2
        var steep = base; steep.angleDegrees = 62; steep.releaseHeight = 1.4
        steep.speed = LaunchModel(steep).speedToHitHole() ?? 9
        var tall = base; tall.releaseHeight = 1.8; tall.angleDegrees = 5
        tall.speed = LaunchModel(tall).speedToHitHole() ?? 9
        for (name, p) in [("long", long), ("short", short), ("steep", steep), ("tall", tall)] {
            try render(LaunchScene(params: p, frozenTime: 10).padding(16).background(Color(nsColor: .controlBackgroundColor)),
                       "scene_\(name)", width: 760, height: 380)
        }
        for t in [0.0, 0.2, 0.35, 0.6] {
            try render(LaunchScene(params: base, frozenTime: t).frame(width: 1900, height: 950).scaleEffect(1)
                .padding(16).background(Color(nsColor: .controlBackgroundColor)), "zoom_t\(Int(t * 100))", width: 1932, height: 982)
        }
        try render(LaunchLabContent(measured: [], athleteSelected: false, animateOnAppear: false),
                   "launch_lab_no_athlete", width: 1180, height: 900)
    }
}
