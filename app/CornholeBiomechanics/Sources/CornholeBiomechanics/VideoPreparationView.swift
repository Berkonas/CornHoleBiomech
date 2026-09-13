import AVFoundation
import AVKit
import SwiftUI

/// Edits are always expressed in original decoded pixels and original frame indices.
struct VideoPreparationView: View {
    @EnvironmentObject private var store: ProjectStore
    @EnvironmentObject private var analysis: AnalysisService
    @Environment(\.dismiss) private var dismiss
    let trial: Trial
    @State private var player: AVPlayer?
    @State private var frame = 0.0
    @State private var frames = 1
    @State private var fps = 30.0
    @State private var sourceWidth = 0
    @State private var sourceHeight = 0
    @State private var start = 0
    @State private var end = 1
    @State private var x = 0
    @State private var y = 0
    @State private var width = 0
    @State private var height = 0
    @State private var rotation = 0
    @State private var failure: String?
    @State private var loaded = false
    @State private var saving = false
    @State private var timeObserver: Any?

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Prepare this throw").font(.title2.bold())
            Text("Trim one complete throw, keep the athlete and bag in view, and correct camera rotation. All edits start from your original recording.").foregroundStyle(.secondary)
            if let player, sourceWidth > 0 {
                GeometryReader { geometry in
                    ZStack(alignment: .topLeading) {
                        NativeVideoPlayer(player: player, showsControls: false)
                        Color.clear.contentShape(Rectangle()).gesture(DragGesture(minimumDistance: 5).onChanged { drag in
                            player.pause()
                            let sx = Double(sourceWidth) / geometry.size.width
                            let sy = Double(sourceHeight) / geometry.size.height
                            let left = max(0, min(sourceWidth - 16, Int(min(drag.startLocation.x, drag.location.x) * sx)))
                            let top = max(0, min(sourceHeight - 16, Int(min(drag.startLocation.y, drag.location.y) * sy)))
                            let right = min(sourceWidth, max(left + 16, Int(max(drag.startLocation.x, drag.location.x) * sx)))
                            let bottom = min(sourceHeight, max(top + 16, Int(max(drag.startLocation.y, drag.location.y) * sy)))
                            x = left; y = top; width = (right - left) / 2 * 2; height = (bottom - top) / 2 * 2
                        })
                        Rectangle().stroke(.yellow, lineWidth: 2)
                            .frame(width: geometry.size.width * Double(width) / Double(sourceWidth), height: geometry.size.height * Double(height) / Double(sourceHeight))
                            .offset(x: geometry.size.width * Double(x) / Double(sourceWidth), y: geometry.size.height * Double(y) / Double(sourceHeight))
                            .allowsHitTesting(false)
                    }
                }.aspectRatio(Double(sourceWidth) / Double(sourceHeight), contentMode: .fit).frame(maxHeight: 300).frame(maxWidth: .infinity)
                HStack {
                    Button("Play / Pause") { player.timeControlStatus == .playing ? player.pause() : player.play() }
                    Text("Source frame \(Int(frame)) / \(frames - 1)").monospacedDigit().frame(width: 190, alignment: .leading)
                    Slider(value: Binding(get: { frame }, set: { value in
                            frame = value
                            player.pause()
                            player.seek(to: CMTime(seconds: value / fps, preferredTimescale: 60000), toleranceBefore: .zero, toleranceAfter: .zero)
                        }), in: 0...Double(max(1, frames - 1)), step: 1)
                }
            } else { ProgressView("Reading original recording…").frame(height: 200) }
            HStack {
                coordinateField("First frame", value: $start)
                Button("Start here") { start = Int(frame) }
                coordinateField("Last frame + 1", value: $end)
                Button("End here") { end = Int(frame) + 1 }
            }
            Text("Keep frames \(start)…\(max(start, end - 1)) · \((Double(max(0, end - start)) / fps).formatted(.number.precision(.fractionLength(2)))) s. Include preparation, backswing, release, and follow-through.").font(.caption).foregroundStyle(.secondary)
            HStack {
                coordinateField("Crop X (px)", value: $x)
                coordinateField("Crop Y (px)", value: $y)
                coordinateField("Width (px)", value: $width)
                coordinateField("Height (px)", value: $height)
            }
            HStack {
                Picker("Rotate clockwise", selection: $rotation) {
                    ForEach([0, 90, 180, 270], id: \.self) { Text("\($0)°").tag($0) }
                }.frame(width: 270)
                Button("Reset adjustments") { start = 0; end = frames; x = 0; y = 0; width = sourceWidth - sourceWidth % 2; height = sourceHeight - sourceHeight % 2; rotation = 0 }
            }
            Text("Drag on the preview to crop, or enter pixel coordinates from the top-left. Yellow box = retained area before rotation. Width and height must be even. No stretching, mirroring, stabilization, or speed change. The derived clip is silent and uses the source’s nominal frame rate; use constant-frame-rate recordings for timing measurements.").font(.caption).foregroundStyle(.secondary)
            Label("Saving archives previous analysis and corrections. Analyze again and review landmarks, release, and calibration on the new clip.", systemImage: "info.circle").font(.callout)
            if let failure { Text(failure).foregroundStyle(.red).textSelection(.enabled) }
            HStack {
                if trial.preparedVideoRelativePath != nil {
                    Button("Use original again") {
                        do { try store.usePreparedVideo(nil, for: trial); dismiss() }
                        catch { failure = error.localizedDescription }
                    }.disabled(saving || analysis.isRunning)
                }
                Spacer()
                Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction).disabled(saving)
                Button(saving ? "Saving…" : "Save analysis copy") {
                    saving = true; failure = nil; player?.pause()
                    Task {
                        do { try await analysis.prepareVideo(trial: trial, store: store, start: start, end: end, crop: [x, y, width, height], rotation: rotation); dismiss() }
                        catch { failure = error.localizedDescription }
                        saving = false
                    }
                }.buttonStyle(.borderedProminent).disabled(!loaded || saving || analysis.isRunning)
            }
        }.padding(24).frame(width: 740).task {
            guard let source = store.originalVideoURL(for: trial) else { failure = "Original recording missing. Relink it first."; return }
            do {
                let info = try await analysis.videoInfo(source)
                guard let w = info["width"] as? Int, let h = info["height"] as? Int,
                      let n = info["frame_count"] as? Int, let rate = info["fps"] as? Double else { throw AnalysisServiceError.invalidResponse }
                sourceWidth = w; sourceHeight = h; width = w - w % 2; height = h - h % 2
                frames = n; end = n; fps = rate
                let currentPlayer = AVPlayer(url: source)
                player = currentPlayer
                timeObserver = currentPlayer.addPeriodicTimeObserver(forInterval: CMTime(seconds: 1 / rate, preferredTimescale: 60000), queue: .main) { time in
                    frame = min(Double(n - 1), max(0, (time.seconds * rate).rounded()))
                }
                loaded = true
            } catch { failure = error.localizedDescription }
        }.onDisappear { player?.pause(); if let timeObserver { player?.removeTimeObserver(timeObserver) }; timeObserver = nil }
    }
    private func coordinateField(_ label: String, value: Binding<Int>) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label).font(.caption).foregroundStyle(.secondary)
            TextField(label, value: value, format: .number).labelsHidden()
        }
    }
}
