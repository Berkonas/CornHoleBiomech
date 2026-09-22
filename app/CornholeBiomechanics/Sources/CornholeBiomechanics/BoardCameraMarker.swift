import AVFoundation
import AppKit
import SwiftUI

enum LandingMark: String, CaseIterable, Identifiable {
    case corners = "Board corners"
    case contact = "First contact"
    case rest = "Final rest"
    var id: String { rawValue }
}

/// Measures landing positions in deck inches from the session's board-camera clip.
struct BoardCameraMarker: View {
    @EnvironmentObject private var store: ProjectStore
    @Environment(\.dismiss) private var dismiss
    let sessionID: UUID
    var onPoint: (LandingMark, BoardPoint) -> Void

    @State private var time = 0.0
    @State private var duration = 1.0
    @State private var fps = 30.0
    @State private var image: CGImage?
    @State private var corners: [ImagePoint] = []
    @State private var mode: LandingMark = .corners
    @State private var zoom = 1.0
    @State private var message: String?

    private var session: RecordingSession? { store.project?.sessions?.first { $0.id == sessionID } }
    private var videoURL: URL? { session?.boardVideoRelativePath.flatMap(store.url(for:)) }
    private var homography: BoardHomography? { corners.count == 4 ? BoardHomography(imageCorners: corners.map(\.cgPoint)) : nil }
    private var width: Double { Double(image?.width ?? 1920) }
    private var height: Double { Double(image?.height ?? 1080) }
    private var scale: Double { min(820 / width, 460 / height) * zoom }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Measure landing on the board camera").font(.title2.bold())
            if videoURL == nil {
                Text("This session has no board-camera clip yet. Choose the video from the camera aimed at the receiving board (all four corners visible).")
                    .foregroundStyle(.secondary)
                Button("Choose board video…", action: chooseVideo).buttonStyle(.borderedProminent)
            } else {
                instructions
                HStack {
                    Picker("Mark", selection: $mode) { ForEach(LandingMark.allCases) { Text($0.rawValue).tag($0) } }
                        .pickerStyle(.segmented).frame(width: 380)
                        .disabled(homography == nil)
                    Picker("Zoom", selection: $zoom) { Text("Fit").tag(1.0); Text("2×").tag(2.0); Text("4×").tag(4.0) }
                        .pickerStyle(.segmented).frame(width: 180)
                    Spacer()
                    Button("Redo corners") { corners = []; mode = .corners }
                }
                frameView
                scrubber
            }
            if let h = homography, let sensitivity = h.inchesPerPixel(atBoardInches: CGPoint(x: 12, y: 39)) {
                Label("Precision of this view at the hole: a 1-pixel click error moves the point up to \(number(sensitivity, digits: 2)) in."
                      + (sensitivity > 0.5 ? " The camera sees the deck too edge-on for reliable positions; raise it or move it behind the board." : ""),
                      systemImage: sensitivity > 0.5 ? "exclamationmark.triangle" : "ruler")
                    .font(.callout).foregroundStyle(sensitivity > 0.5 ? Color.orange : Color.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let message { Text(message).font(.callout).foregroundStyle(.orange) }
            Text("The mapping is exact only on the flat deck. Points on the floor are a different plane and are refused. The hole ring is drawn from the corners: if it does not sit on the real hole, redo the corners.")
                .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            HStack {
                Button("Choose a different board video…", action: chooseVideo).disabled(videoURL == nil)
                Spacer()
                Button("Done") { dismiss() }.keyboardShortcut(.defaultAction)
            }
        }
        .padding(20).frame(width: 880)
        .task(id: videoURL) { await loadVideo() }
        .task(id: time) { await loadFrame() }
    }

    private var instructions: some View {
        let text: String
        if homography == nil {
            let next = BoardHomography.cornerNames[min(corners.count, 3)]
            text = "Step 1: click the four deck corners in order. Next: \(next) (front = the end nearest the thrower)."
        } else if mode == .corners {
            text = "Corners saved. Choose First contact or Final rest, scrub to that moment, and click the bag's centre."
        } else {
            text = "Scrub to the \(mode == .contact ? "first frame the bag touches the deck" : "moment the bag stops"), then click the bag's centre."
        }
        return Text(text).font(.callout)
    }

    private var frameView: some View {
        ScrollView([.horizontal, .vertical]) {
            if let image {
                Image(decorative: image, scale: 1).resizable()
                    .frame(width: width * scale, height: height * scale)
                    .overlay(alignment: .topLeading) { overlay.allowsHitTesting(false) }
                    .contentShape(Rectangle())
                    .onTapGesture(coordinateSpace: .local) { click(ImagePoint(x: $0.x / scale, y: $0.y / scale)) }
                    .accessibilityLabel("Board camera frame. Click to place the \(mode.rawValue.lowercased()).")
            } else { ProgressView("Loading frame…").frame(width: 820, height: 460) }
        }.frame(width: 820, height: 460).background(.black)
    }

    private var overlay: some View {
        Canvas { context, _ in
            func p(_ q: CGPoint) -> CGPoint { CGPoint(x: q.x * scale, y: q.y * scale) }
            var outline = Path()
            for (i, c) in corners.enumerated() {
                let q = p(c.cgPoint)
                if i == 0 { outline.move(to: q) } else { outline.addLine(to: q) }
                context.fill(Path(ellipseIn: CGRect(x: q.x - 5, y: q.y - 5, width: 10, height: 10)), with: .color(.cyan))
                context.draw(Text("\(i + 1)").font(.caption.bold()).foregroundColor(.cyan), at: CGPoint(x: q.x + 10, y: q.y - 10))
            }
            if corners.count == 4 { outline.closeSubpath() }
            context.stroke(outline, with: .color(.cyan), lineWidth: 2)
            if let h = homography {
                // Project the real 3 in-radius hole outline; perspective turns it into an ellipse.
                let ring = (0...36).compactMap { i -> CGPoint? in
                    let a = Double(i) / 36 * 2 * .pi
                    return h.image(fromBoardInches: CGPoint(x: 12 + 3 * cos(a), y: 39 + 3 * sin(a))).map(p)
                }
                var hole = Path(); hole.addLines(ring)
                context.stroke(hole, with: .color(.yellow), lineWidth: 2)
            }
        }
        .frame(width: width * scale, height: height * scale)
    }

    private var scrubber: some View {
        HStack {
            Button { time = max(0, time - 1 / fps) } label: { Image(systemName: "backward.frame") }.help("Previous frame")
            Slider(value: $time, in: 0...max(duration, 0.01))
            Button { time = min(duration, time + 1 / fps) } label: { Image(systemName: "forward.frame") }.help("Next frame")
            Text("frame \(Int((time * fps).rounded()))").monospacedDigit().frame(width: 90, alignment: .trailing)
        }
    }

    private func click(_ point: ImagePoint) {
        message = nil
        if homography == nil {
            corners.append(point)
            guard corners.count == 4 else { return }
            do { try store.setBoardCorners(corners, for: sessionID); mode = .contact }
            catch { message = error.localizedDescription; corners = [] }
            return
        }
        guard mode != .corners, let h = homography, let inches = h.boardInches(fromImage: point.cgPoint) else { return }
        guard h.isOnBoard(inches) else {
            message = "That point is off the deck. A floor landing is a miss with no board location; record it as 0 points instead."
            return
        }
        onPoint(mode, BoardPoint(xInches: inches.x, yInches: inches.y, precision: "board_camera_homography"))
        message = nil
        mode = mode == .contact ? .rest : .contact
    }

    private func chooseVideo() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.movie]
        panel.title = "Choose the board-camera video for this session"
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do { try store.setBoardVideo(url, for: sessionID); corners = [] }
        catch { message = error.localizedDescription }
    }

    private func loadVideo() async {
        corners = session?.boardCorners ?? []
        mode = corners.count == 4 ? .contact : .corners
        guard let url = videoURL else { return }
        let asset = AVURLAsset(url: url)
        if let seconds = try? await asset.load(.duration).seconds, seconds.isFinite { duration = seconds }
        if let track = try? await asset.loadTracks(withMediaType: .video).first,
           let rate = try? await track.load(.nominalFrameRate), rate > 0 { fps = Double(rate) }
        await loadFrame()
    }

    private func loadFrame() async {
        guard let url = videoURL else { return }
        let generator = AVAssetImageGenerator(asset: AVURLAsset(url: url))
        generator.appliesPreferredTrackTransform = true
        generator.requestedTimeToleranceBefore = .zero
        generator.requestedTimeToleranceAfter = .zero
        do { image = try await generator.image(at: CMTime(seconds: time, preferredTimescale: 60000)).image }
        catch { message = "Could not load this frame: \(error.localizedDescription)" }
    }
}
