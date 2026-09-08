import SwiftUI
import AVKit

/// Use AppKit's player directly to avoid the system SwiftUI AVKit metadata crash.
struct NativeVideoPlayer: NSViewRepresentable {
    let player: AVPlayer
    var showsControls = true

    func makeNSView(context: Context) -> AVPlayerView {
        let view = AVPlayerView()
        view.player = player
        view.controlsStyle = showsControls ? .floating : .none
        view.videoGravity = .resizeAspect
        view.showsFullScreenToggleButton = false
        return view
    }

    func updateNSView(_ view: AVPlayerView, context: Context) {
        if view.player !== player { view.player = player }
    }

    static func dismantleNSView(_ view: AVPlayerView, coordinator: ()) {
        view.player?.pause()
        view.player = nil
    }
}
