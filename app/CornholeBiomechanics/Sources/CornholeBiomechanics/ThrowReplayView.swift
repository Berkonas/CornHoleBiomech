import AVFoundation
import AVKit
import SwiftUI

let measuredInk = Color(red: 0.98, green: 0.55, blue: 0.13)   // measured bag path
let slideInk = Color(red: 0.99, green: 0.83, blue: 0.25)      // after first contact
let modelInk = Color.white.opacity(0.7)                       // fitted model (secondary)

/// Measured throw replay. View = Video (video + skeleton + measured bag path + fitted model + events)
/// or Animation (stick figure and bag path on a clean canvas; with a metric scale, side on and to scale with the
/// board, first contact, the slide and where the bag ended). Both share one timeline and `currentFrame`.
/// The measured path dominates; the drag-free model is a thin dashed reference.
struct ThrowReplayView: View {
    enum Mode: String, CaseIterable, Identifiable {
        case video = "Side", front = "Front", both = "Both", animation = "Animation"
        var id: String { rawValue }
    }

    let videoURL: URL?
    let replay: ReplayDocument
    let pose: PoseDocument?
    let throwingSide: ThrowingSide
    @Binding var currentFrame: Int
    @Binding var seekRequest: Int?
    /// The synchronised front-camera clip (two-camera takes).
    var front: FrontReplaySource? = nil
    /// Scale, release height, board distance and board phase: the animation is then drawn to scale with the board.
    var stage: ReplayStage? = nil
    @State private var player: AVPlayer
    @State private var frontPlayer: AVPlayer
    @State private var timeObserver: Any?
    @State private var playing = false
    @State private var rate: Float = 0.5
    @State private var mode: Mode
    @State private var figureBounds: CGRect?
    @State private var scene: SideScene?
    @State private var clock: (start: Date, frame: Int)?
    @AppStorage("replayShowSkeleton") private var showSkeleton = true
    @AppStorage("replayShowModel") private var showModel = true
    @AppStorage("replayShowTrail") private var showTrail = true

    init(videoURL: URL?, replay: ReplayDocument, pose: PoseDocument?, throwingSide: ThrowingSide,
         currentFrame: Binding<Int>, seekRequest: Binding<Int?>, mode: Mode = .video, front: FrontReplaySource? = nil,
         stage: ReplayStage? = nil) {
        self.videoURL = videoURL; self.replay = replay; self.pose = pose; self.throwingSide = throwingSide
        _currentFrame = currentFrame; _seekRequest = seekRequest
        self.front = front
        self.stage = stage
        _player = State(initialValue: videoURL.map { AVPlayer(url: $0) } ?? AVPlayer())
        _frontPlayer = State(initialValue: front.map { AVPlayer(url: $0.url) } ?? AVPlayer())
        _mode = State(initialValue: videoURL == nil ? .animation : (front != nil && mode == .video ? .both : mode))
    }

    private var availableModes: [Mode] {
        front == nil ? [.video, .animation] : Mode.allCases
    }

    /// Front-clip frame showing the same instant as side frame `frame`.
    private func frontFrame(_ frame: Int) -> Int? { front?.document.frontFrame(forSide: frame) }

    var body: some View {
        VStack(alignment: .leading, spacing: Space.m) {
            HStack(spacing: Space.m) {
                Picker("View", selection: $mode) {
                    ForEach(availableModes) { Text($0.rawValue).tag($0) }
                }
                .pickerStyle(.segmented).labelsHidden().fixedSize()
                .disabled(videoURL == nil)
                .help(videoURL == nil ? "The video file is not available; the animation is drawn from the tracking." : "Show the video or a clean animation")
                Spacer()
                showMenu
            }
            Group {
                if mode == .both, let front {
                    HStack(spacing: Space.s) {
                        sideVideo
                        frontVideo(front)
                    }
                    .aspectRatio(2 * CGFloat(replay.width) / CGFloat(max(replay.height, 1)), contentMode: .fit)
                } else if mode == .front, let front {
                    frontVideo(front)
                        .aspectRatio(CGFloat(front.document.frontWidth / max(front.document.frontHeight, 1)), contentMode: .fit)
                } else {
                    sideVideo
                        .aspectRatio(CGFloat(replay.width) / CGFloat(max(replay.height, 1)), contentMode: .fit)
                }
            }
            .frame(maxHeight: 520)
            timeline
            controls
        }
        .onAppear {
            installObserver()
            if figureBounds == nil { figureBounds = StickFigureReplay.bounds(pose: pose, replay: replay) }
            if scene == nil, let stage { scene = SideScene(replay: replay, pose: pose, stage: stage) }
            seek(to: seekRequest ?? replay.events["release"]?.frame ?? currentFrame)
            seekRequest = nil
        }
        .onDisappear { removeObserver(); player.pause(); frontPlayer.pause() }
        .onChange(of: seekRequest) { _, frame in
            if let frame { seek(to: frame); seekRequest = nil }
        }
        .onChange(of: mode) { _, _ in pause(); seek(to: currentFrame) }
        .onChange(of: stage) { _, value in scene = value.flatMap { SideScene(replay: replay, pose: pose, stage: $0) } }
        .task(id: mode == .animation && playing) {
            // Animation playback runs on its own clock, at the chosen rate.
            guard mode == .animation, playing else { return }
            while !Task.isCancelled {
                guard let clock else { return }
                let frame = clock.frame + Int((Date().timeIntervalSince(clock.start) * replay.fps * Double(rate)).rounded())
                if frame >= replay.frame_count - 1 { currentFrame = replay.frame_count - 1; playing = false; return }
                currentFrame = frame
                try? await Task.sleep(for: .milliseconds(16))
            }
        }
    }

    /// The side camera (video or animation) with its overlay.
    private var sideVideo: some View {
        GeometryReader { geometry in
            ZStack {
                if mode == .animation {
                    Color(nsColor: .textBackgroundColor)
                } else {
                    Color.black
                    NativeVideoPlayer(player: player, showsControls: false)
                }
                TimelineView(.animation(minimumInterval: nil, paused: !playing)) { _ in
                    if mode == .animation, let scene {
                        SideViewReplay(scene: scene, replay: replay, pose: pose, side: throwingSide, frame: displayedFrame,
                                       showModel: showModel, showTrail: showTrail)
                    } else if mode == .animation {
                        StickFigureReplay(replay: replay, pose: pose, side: throwingSide, frame: displayedFrame,
                                          bounds: figureBounds ?? CGRect(x: 0, y: 0, width: replay.width, height: replay.height),
                                          showModel: showModel, showTrail: showTrail)
                    } else {
                        ReplayOverlay(replay: replay, pose: pose, side: throwingSide, frame: displayedFrame,
                                      size: geometry.size, showSkeleton: showSkeleton, showModel: showModel, showTrail: showTrail)
                    }
                }.allowsHitTesting(false)
                if mode == .video {
                    legend.padding(Space.s).frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                }
                if mode == .both {
                    viewLabel("Side camera")
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: Radius.card))
            .overlay(RoundedRectangle(cornerRadius: Radius.card).strokeBorder(.separator.opacity(mode == .animation ? 0.6 : 0)))
        }
    }

    /// The front camera (behind the board) at the same instant, with the deck, the bag's path and the landing.
    private func frontVideo(_ front: FrontReplaySource) -> some View {
        GeometryReader { geometry in
            ZStack {
                Color.black
                NativeVideoPlayer(player: frontPlayer, showsControls: false)
                TimelineView(.animation(minimumInterval: nil, paused: !playing)) { _ in
                    FrontReplayOverlay(document: front.document, frontFrame: frontFrame(displayedFrame) ?? 0, size: geometry.size)
                }.allowsHitTesting(false)
                viewLabel("Front camera (behind the board)")
            }
            .clipShape(RoundedRectangle(cornerRadius: Radius.card))
        }
    }

    private func viewLabel(_ text: String) -> some View {
        Text(text).font(.caption.weight(.semibold)).foregroundStyle(.white)
            .padding(.horizontal, 8).padding(.vertical, 3)
            .background(.black.opacity(0.55), in: Capsule())
            .padding(Space.s)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topTrailing)
    }

    // MARK: overlay legend and controls
    private var showMenu: some View {
        Menu {
            Toggle("Skeleton", isOn: $showSkeleton).disabled(mode == .animation)
            Toggle("Drag-free model", isOn: $showModel)
            Toggle("Full bag path", isOn: $showTrail)
        } label: {
            Label("Show", systemImage: "eye")
        }
        .menuStyle(.borderlessButton).fixedSize()
        .help("Choose what is drawn over the replay")
    }

    private var legend: some View {
        VStack(alignment: .leading, spacing: 4) {
            legendRow(Rectangle().fill(measuredInk).frame(width: 22, height: 3), "Measured bag path")
            if showModel && !replay.model.isEmpty {
                legendRow(DashedLine().stroke(modelInk, style: StrokeStyle(lineWidth: 1.5, dash: [5, 4])).frame(width: 22, height: 3),
                          "Drag-free model (reference)")
            }
            if !replay.after_contact.isEmpty { legendRow(Rectangle().fill(slideInk).frame(width: 22, height: 3), "After first contact") }
        }
        .font(.caption2).foregroundStyle(.white)
        .padding(8).background(.black.opacity(0.55), in: RoundedRectangle(cornerRadius: 7))
    }
    private func legendRow(_ swatch: some View, _ text: String) -> some View {
        HStack(spacing: 6) { swatch; Text(text) }
    }

    private var timeline: some View {
        VStack(alignment: .leading, spacing: 6) {
            GeometryReader { geometry in
                let width = geometry.size.width
                let last = Double(max(replay.frame_count - 1, 1))
                ZStack(alignment: .leading) {
                    Slider(value: Binding(get: { Double(currentFrame) }, set: { seek(to: Int($0)) }), in: 0...last)
                        .accessibilityLabel("Video frame")
                    ForEach(replay.orderedEvents, id: \.key) { item in
                        Rectangle().fill(eventColor(item.key)).frame(width: 2, height: 12)
                            .position(x: 8 + (width - 16) * Double(item.event.frame) / last, y: -4)
                            .allowsHitTesting(false)
                    }
                }
            }.frame(height: 26)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(replay.orderedEvents.filter { Self.chipEvents.contains($0.key) }, id: \.key) { item in
                        Button { seek(to: item.event.frame) } label: {
                            HStack(spacing: 5) {
                                Circle().fill(eventColor(item.key)).frame(width: 8, height: 8)
                                Text(item.event.label).font(.callout.weight(currentEventKey == item.key ? .semibold : .regular))
                                Text(relativeTime(item.event.frame)).font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                            }
                            .padding(.horizontal, 10).padding(.vertical, 5)
                            .background(currentEventKey == item.key ? eventColor(item.key).opacity(0.18) : Color.secondary.opacity(0.08), in: Capsule())
                        }.buttonStyle(.plain).help("Jump to \(item.event.label.lowercased()) (frame \(item.event.frame))")
                    }
                }
            }
        }
    }

    /// Event chips (spec §3.3): backswing, peak wrist speed, release, apex, first contact.
    static let chipEvents: Set<String> = ["peak_backswing", "peak_wrist_speed", "release", "apex", "first_contact"]

    private var controls: some View {
        HStack(spacing: Space.m) {
            Button { step(-1) } label: { Image(systemName: "backward.frame.fill") }.help("Previous frame")
                .accessibilityLabel("Previous frame")
            Button { togglePlay() } label: { Image(systemName: playing ? "pause.fill" : "play.fill").frame(width: 18) }
                .keyboardShortcut(.space, modifiers: []).help("Play / pause (space)")
                .accessibilityLabel(playing ? "Pause" : "Play")
            Button { step(1) } label: { Image(systemName: "forward.frame.fill") }.help("Next frame")
                .accessibilityLabel("Next frame")
            Picker("Speed", selection: $rate) {
                Text("¼×").tag(Float(0.25)); Text("½×").tag(Float(0.5)); Text("1×").tag(Float(1))
            }.pickerStyle(.segmented).frame(width: 130).labelsHidden()
            Text("Frame \(currentFrame) · \(relativeTime(currentFrame))").font(.callout.monospacedDigit()).foregroundStyle(.secondary)
            Spacer()
        }
        .onChange(of: rate) { _, value in
            if playing && mode != .animation { player.rate = value; if front != nil { frontPlayer.rate = value } }
            if playing && mode == .animation { clock = (Date(), currentFrame) }
        }
    }

    // MARK: playback
    private var displayedFrame: Int {
        guard playing, mode != .animation else { return currentFrame }
        return min(max(0, Int((player.currentTime().seconds * replay.fps).rounded())), replay.frame_count - 1)
    }
    private var currentEventKey: String? {
        replay.orderedEvents.min { abs($0.event.frame - currentFrame) < abs($1.event.frame - currentFrame) }
            .flatMap { abs($0.event.frame - currentFrame) <= 2 ? $0.key : nil }
    }
    private func relativeTime(_ frame: Int) -> String {
        guard let release = replay.events["release"]?.frame else { return "\(number(Double(frame) / replay.fps, digits: 2)) s" }
        let ms = 1000 * Double(frame - release) / replay.fps
        return ms == 0 ? "release" : "\(ms > 0 ? "+" : "−")\(number(abs(ms), digits: 0)) ms"
    }
    private func pause() { player.pause(); frontPlayer.pause(); playing = false; clock = nil }
    private func seek(to frame: Int) {
        pause()
        currentFrame = min(max(0, frame), replay.frame_count - 1)
        if videoURL != nil {
            player.seek(to: CMTime(seconds: Double(currentFrame) / replay.fps, preferredTimescale: 60000), toleranceBefore: .zero, toleranceAfter: .zero)
        }
        seekFront(currentFrame)
    }
    /// Put the front clip on the same instant as side frame `frame`.
    private func seekFront(_ frame: Int) {
        guard let front, let target = frontFrame(frame) else { return }
        frontPlayer.seek(to: CMTime(seconds: Double(target) / front.document.frontFPS, preferredTimescale: 60000),
                         toleranceBefore: .zero, toleranceAfter: .zero)
    }
    private func step(_ amount: Int) { seek(to: currentFrame + amount) }
    private func togglePlay() {
        if playing { pause(); return }
        if currentFrame >= replay.frame_count - 2 { seek(to: 0) }
        if mode == .animation {
            clock = (Date(), currentFrame)
        } else {
            player.playImmediately(atRate: rate)
            if front != nil { frontPlayer.playImmediately(atRate: rate) }
        }
        playing = true
    }
    private func installObserver() {
        guard timeObserver == nil else { return }
        let fps = replay.fps, last = replay.frame_count - 1
        timeObserver = player.addPeriodicTimeObserver(forInterval: CMTime(seconds: 1 / max(1, fps), preferredTimescale: 60000), queue: .main) { time in
            guard playing, mode != .animation else { return }
            currentFrame = min(max(0, Int((time.seconds * fps).rounded())), last)
            if currentFrame >= last { playing = false; frontPlayer.pause() }
            // Keep the front clip on the side clip's clock (two players drift apart slowly).
            if let front, let target = frontFrame(currentFrame) {
                let frontNow = frontPlayer.currentTime().seconds * front.document.frontFPS
                if abs(frontNow - Double(target)) > 2 {
                    frontPlayer.seek(to: CMTime(seconds: Double(target) / front.document.frontFPS, preferredTimescale: 60000),
                                     toleranceBefore: .zero, toleranceAfter: .zero)
                }
            }
        }
    }
    private func removeObserver() { if let timeObserver { player.removeTimeObserver(timeObserver); self.timeObserver = nil } }
}

func eventColor(_ key: String) -> Color {
    switch key {
    case "release": .red
    case "apex": .purple
    case "first_contact": .blue
    case "final_rest": Color(red: 0.2, green: 0.6, blue: 0.3)
    case "into_hole": Color(red: 0.1, green: 0.65, blue: 0.2)
    case "peak_wrist_speed": .teal
    case "peak_elbow_extension": .indigo
    default: .gray
    }
}

private struct DashedLine: Shape {
    func path(in rect: CGRect) -> Path { var p = Path(); p.move(to: CGPoint(x: 0, y: rect.midY)); p.addLine(to: CGPoint(x: rect.maxX, y: rect.midY)); return p }
}

/// Everything drawn over the video for one frame. Paths are mapped from release-frame
/// pixels into this frame's pixels, then into the aspect-fitted video rectangle.
struct ReplayOverlay: View {
    let replay: ReplayDocument
    let pose: PoseDocument?
    let side: ThrowingSide
    let frame: Int
    let size: CGSize
    let showSkeleton: Bool
    let showModel: Bool
    let showTrail: Bool

    var body: some View {
        Canvas { context, _ in
            let rect = videoRect
            func screen(_ p: CGPoint) -> CGPoint {
                CGPoint(x: rect.minX + rect.width * p.x / Double(replay.width), y: rect.minY + rect.height * p.y / Double(replay.height))
            }
            func mapped(_ point: ReplayDocument.Point) -> CGPoint { screen(replay.toFrame(point.x, point.y, frame: frame)) }
            func polyline(_ points: [ReplayDocument.Point]) -> Path {
                var path = Path(); var previous: Int?
                for point in points {
                    let p = mapped(point)
                    if let previous, point.frame - previous <= 4 { path.addLine(to: p) } else { path.move(to: p) }
                    previous = point.frame
                }
                return path
            }
            if showSkeleton { drawSkeleton(context, screen: screen) }
            if showModel && !replay.model.isEmpty {
                context.stroke(polyline(replay.model), with: .color(modelInk), style: StrokeStyle(lineWidth: 1.5, dash: [6, 5]))
            }
            let path = replay.filtered.isEmpty ? replay.measured : replay.filtered
            if showTrail {
                context.stroke(polyline(path), with: .color(measuredInk.opacity(0.35)), style: StrokeStyle(lineWidth: 2, lineCap: .round))
            }
            let travelled = path.filter { $0.frame <= frame }
            context.stroke(polyline(travelled), with: .color(.black.opacity(0.45)), style: StrokeStyle(lineWidth: 5.5, lineCap: .round, lineJoin: .round))
            context.stroke(polyline(travelled), with: .color(measuredInk), style: StrokeStyle(lineWidth: 3, lineCap: .round, lineJoin: .round))
            let slide = replay.after_contact.filter { $0.frame <= frame || showTrail }
            context.stroke(polyline(slide), with: .color(slideInk), style: StrokeStyle(lineWidth: 3, lineCap: .round))
            // The bag now, when it was measured in this frame.
            if let now = (path + replay.after_contact).first(where: { $0.frame == frame }) {
                let p = mapped(now)
                context.stroke(Path(ellipseIn: CGRect(x: p.x - 9, y: p.y - 9, width: 18, height: 18)), with: .color(.white), lineWidth: 2.5)
            }
            for item in replay.orderedEvents {
                guard let position = item.event.position else { continue }
                let p = screen(replay.toFrame(position.x, position.y, frame: frame))
                let past = item.event.frame <= frame
                let color = eventColor(item.key)
                context.fill(Path(ellipseIn: CGRect(x: p.x - 6, y: p.y - 6, width: 12, height: 12)), with: .color(color.opacity(past ? 1 : 0.45)))
                context.stroke(Path(ellipseIn: CGRect(x: p.x - 6, y: p.y - 6, width: 12, height: 12)), with: .color(.white), lineWidth: 1.5)
                let label = Text(item.event.label).font(.system(size: 11, weight: .semibold)).foregroundColor(.white)
                let resolved = context.resolve(label)
                let textSize = resolved.measure(in: CGSize(width: 200, height: 30))
                let box = CGRect(x: p.x + 9, y: p.y - textSize.height - 8, width: textSize.width + 10, height: textSize.height + 4)
                context.fill(Path(roundedRect: box, cornerRadius: 4), with: .color(color.opacity(past ? 0.9 : 0.45)))
                context.draw(resolved, at: CGPoint(x: box.midX, y: box.midY))
            }
        }
    }

    private var videoRect: CGRect {
        let scale = min(size.width / Double(replay.width), size.height / Double(replay.height))
        let fitted = CGSize(width: Double(replay.width) * scale, height: Double(replay.height) * scale)
        return CGRect(x: (size.width - fitted.width) / 2, y: (size.height - fitted.height) / 2, width: fitted.width, height: fitted.height)
    }

    private func drawSkeleton(_ context: GraphicsContext, screen: (CGPoint) -> CGPoint) {
        guard let landmarks = pose?.frames[safe: frame]?.landmarks else { return }
        let s = side.rawValue, o = side == .right ? "left" : "right"
        let bones: [(String, String, Bool)] = [
            ("\(s)_shoulder", "\(s)_elbow", true), ("\(s)_elbow", "\(s)_wrist", true),
            ("left_shoulder", "right_shoulder", false), ("left_hip", "right_hip", false),
            ("left_shoulder", "left_hip", false), ("right_shoulder", "right_hip", false),
            ("\(o)_shoulder", "\(o)_elbow", false), ("\(o)_elbow", "\(o)_wrist", false),
        ]
        for (a, b, throwing) in bones {
            guard let pa = landmarks[a], let pb = landmarks[b], let ax = pa.x, let ay = pa.y, let bx = pb.x, let by = pb.y,
                  pa.confidence >= 0.3, pb.confidence >= 0.3 else { continue }
            var path = Path(); path.move(to: screen(CGPoint(x: ax, y: ay))); path.addLine(to: screen(CGPoint(x: bx, y: by)))
            context.stroke(path, with: .color(throwing ? Color.cyan : Color.white.opacity(0.7)), lineWidth: throwing ? 3 : 2)
        }
        if let wrist = landmarks["\(s)_wrist"], let x = wrist.x, let y = wrist.y {
            let p = screen(CGPoint(x: x, y: y))
            context.fill(Path(ellipseIn: CGRect(x: p.x - 4, y: p.y - 4, width: 8, height: 8)), with: .color(.cyan))
        }
    }
}
