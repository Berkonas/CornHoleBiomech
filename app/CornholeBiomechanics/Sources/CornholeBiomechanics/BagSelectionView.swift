import AVFoundation
import SwiftUI

/// Source-pixel geometry is shared by the preview and saved tracker seed.
struct BagSelectionGeometry {
    static func rectangle(from a: CGPoint, to b: CGPoint, scale: Double, width: Int, height: Int) -> [Double]? {
        guard scale.isFinite, scale > 0, width > 1, height > 1,
              [a.x, a.y, b.x, b.y].allSatisfy(\.isFinite) else { return nil }
        let x0 = max(0, min(Double(width), min(a.x, b.x)/scale))
        let y0 = max(0, min(Double(height), min(a.y, b.y)/scale))
        let x1 = max(0, min(Double(width), max(a.x, b.x)/scale))
        let y1 = max(0, min(Double(height), max(a.y, b.y)/scale))
        guard x1-x0 > 1, y1-y0 > 1 else { return nil }
        return [x0, y0, x1-x0, y1-y0]
    }
}

struct BagSelectionView: View {
    @Environment(\.dismiss) private var dismiss
    @ObservedObject var data: TrialDataController
    let videoURL: URL
    let frame: Int
    var onTrack: () -> Void
    @State private var image: CGImage?
    @State private var rectangle: [Double]?
    @State private var zoom = 1.0
    @State private var error: String?
    private var width: Int { data.pose?.width ?? 1920 }
    private var height: Int { data.pose?.height ?? 1080 }
    private var scale: Double { min(780/Double(width), 430/Double(height))*zoom }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Select the thrown bag").font(.title2.bold())
            Text("Frame \(frame). Drag a tight box around the bag. Choose a frame at or just before release so tracking includes the launch. Tracking will start as soon as you confirm.")
                .font(.callout).foregroundStyle(.secondary)
            HStack {
                Picker("Zoom", selection: $zoom) {
                    Text("Fit").tag(1.0); Text("2×").tag(2.0); Text("4×").tag(4.0)
                }.pickerStyle(.segmented).frame(width: 260)
                Text("Zoom in and scroll to locate a small bag.").font(.caption).foregroundStyle(.secondary)
            }
            ScrollView([.horizontal, .vertical]) {
                if let image {
                    Image(decorative: image, scale: 1).resizable()
                        .frame(width: Double(width)*scale, height: Double(height)*scale)
                        .overlay(alignment: .topLeading) {
                            if let r = rectangle {
                                Rectangle().stroke(.cyan, lineWidth: 2).background(.cyan.opacity(0.12))
                                    .frame(width: r[2]*scale, height: r[3]*scale)
                                    .offset(x: r[0]*scale, y: r[1]*scale).allowsHitTesting(false)
                            }
                        }
                        .contentShape(Rectangle())
                        .gesture(DragGesture(minimumDistance: 0).onChanged { drag in
                            rectangle = BagSelectionGeometry.rectangle(from: drag.startLocation, to: drag.location,
                                scale: scale, width: width, height: height)
                        })
                        .accessibilityLabel("Video frame \(frame). Draw a box around the thrown bag.")
                } else if error == nil { ProgressView("Loading the selected frame…") }
            }.frame(width: 780, height: 430).background(.black)
            if let r = rectangle {
                Text("Selected source pixels: x \(Int(r[0])), y \(Int(r[1])), width \(Int(r[2])), height \(Int(r[3]))")
                    .font(.caption).monospacedDigit()
            }
            if let message = error ?? data.loadError { Text(message).font(.callout).foregroundStyle(.orange) }
            Text("The tracker follows appearance, not a bag recognition model. Review its cyan marker throughout flight; correct gaps or identity switches before using release metrics.")
                .font(.caption).foregroundStyle(.secondary)
            HStack {
                Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
                Spacer()
                Button("Track selected bag") {
                    guard let rectangle, data.setBagSeed(frame: frame, bboxXYWH: rectangle) else { return }
                    dismiss(); onTrack()
                }.buttonStyle(.borderedProminent).disabled(rectangle == nil || image == nil)
            }
        }.padding(20).task {
            do {
                let generator = AVAssetImageGenerator(asset: AVURLAsset(url: videoURL))
                generator.appliesPreferredTrackTransform = true
                generator.requestedTimeToleranceBefore = .zero
                generator.requestedTimeToleranceAfter = .zero
                let (cg, _) = try await generator.image(at: CMTime(seconds: Double(frame)/(data.pose?.fps ?? 30), preferredTimescale: 60000))
                guard abs(Double(cg.width)/Double(cg.height)-Double(width)/Double(height)) < 0.01 else {
                    error = "Video orientation differs from the analysis. Prepare a rotated copy and analyze it before selecting the bag."; return
                }
                image = cg
            } catch { self.error = "Could not load frame: \(error.localizedDescription)" }
        }
    }
}
