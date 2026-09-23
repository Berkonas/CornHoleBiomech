// app/CornholeBiomechanics/Sources/SceneVision/main.swift
// Person masks for the analysis engine (Apple Vision, on-device, no downloads).
import AVFoundation
import CoreImage
import Foundation
import ImageIO
import UniformTypeIdentifiers
import Vision

struct Options {
    var input: URL
    var output: URL
    var step = 2
    var scale = 0.5
}

enum SceneError: Error, CustomStringConvertible {
    case usage, noVideoTrack, readerFailed(String), writeFailed(String)
    var description: String {
        switch self {
        case .usage: return "usage: scene-vision --input <video> --output <dir> [--step N] [--scale S]"
        case .noVideoTrack: return "the file has no video track"
        case .readerFailed(let m): return "could not read video: \(m)"
        case .writeFailed(let m): return "could not write mask: \(m)"
        }
    }
}

func parse(_ args: [String]) throws -> Options {
    var input: URL?, output: URL?, step = 2, scale = 0.5
    var i = 1
    while i < args.count {
        let key = args[i]
        guard i + 1 < args.count else { throw SceneError.usage }
        let value = args[i + 1]
        switch key {
        case "--input": input = URL(fileURLWithPath: value)
        case "--output": output = URL(fileURLWithPath: value)
        case "--step": step = max(1, Int(value) ?? 2)
        case "--scale": scale = min(1, max(0.1, Double(value) ?? 0.5))
        default: throw SceneError.usage
        }
        i += 2
    }
    guard let input, let output else { throw SceneError.usage }
    return Options(input: input, output: output, step: step, scale: scale)
}

func writePNG(_ image: CGImage, to url: URL) throws {
    guard let dest = CGImageDestinationCreateWithURL(url as CFURL, UTType.png.identifier as CFString, 1, nil) else {
        throw SceneError.writeFailed(url.path)
    }
    CGImageDestinationAddImage(dest, image, nil)
    if !CGImageDestinationFinalize(dest) { throw SceneError.writeFailed(url.path) }
}

func run(_ o: Options) async throws {
    let asset = AVURLAsset(url: o.input)
    guard let track = try await asset.loadTracks(withMediaType: .video).first else { throw SceneError.noVideoTrack }
    let natural = try await track.load(.naturalSize)
    let transform = try await track.load(.preferredTransform)
    let fps = try await track.load(.nominalFrameRate)
    let oriented = CGRect(origin: .zero, size: natural).applying(transform)
    let width = Int(abs(oriented.width).rounded()), height = Int(abs(oriented.height).rounded())
    let maskW = Int((Double(width) * o.scale).rounded()), maskH = Int((Double(height) * o.scale).rounded())
    let reader = try AVAssetReader(asset: asset)
    let output = AVAssetReaderTrackOutput(track: track, outputSettings: [
        kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA])
    reader.add(output)
    guard reader.startReading() else { throw SceneError.readerFailed(reader.error?.localizedDescription ?? "unknown") }
    try FileManager.default.createDirectory(at: o.output, withIntermediateDirectories: true)
    let request = VNGeneratePersonSegmentationRequest()
    request.qualityLevel = .accurate
    request.outputPixelFormat = kCVPixelFormatType_OneComponent8
    let context = CIContext()
    var index = 0
    var written: [Int] = []
    while let sample = output.copyNextSampleBuffer() {
        defer { index += 1 }
        guard index % o.step == 0, let pixels = CMSampleBufferGetImageBuffer(sample) else { continue }
        try VNImageRequestHandler(cvPixelBuffer: pixels, orientation: .up).perform([request])
        guard let mask = request.results?.first?.pixelBuffer else { continue }
        var image = CIImage(cvPixelBuffer: mask)
        let maskNatural = image.extent.size
        // Mask → video natural size → preferred orientation → output scale.
        image = image.transformed(by: CGAffineTransform(scaleX: natural.width / maskNatural.width,
                                                        y: natural.height / maskNatural.height))
        image = image.transformed(by: transform)
        image = image.transformed(by: CGAffineTransform(translationX: -image.extent.minX, y: -image.extent.minY))
        image = image.transformed(by: CGAffineTransform(scaleX: CGFloat(maskW) / image.extent.width,
                                                        y: CGFloat(maskH) / image.extent.height))
        guard let cg = context.createCGImage(image, from: CGRect(x: 0, y: 0, width: maskW, height: maskH),
                                             format: .L8, colorSpace: CGColorSpaceCreateDeviceGray()) else { continue }
        try writePNG(cg, to: o.output.appendingPathComponent(String(format: "mask_%06d.png", index)))
        written.append(index)
    }
    if reader.status == .failed { throw SceneError.readerFailed(reader.error?.localizedDescription ?? "unknown") }
    let payload: [String: Any] = ["fps": Double(fps), "width": width, "height": height, "mask_width": maskW,
                                  "mask_height": maskH, "step": o.step, "frames": written]
    let data = try JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys])
    try data.write(to: o.output.appendingPathComponent("index.json"))
}

let options: Options
do {
    options = try parse(CommandLine.arguments)
} catch {
    FileHandle.standardError.write(Data("scene-vision: \(error)\n".utf8))
    exit(1)
}

let semaphore = DispatchSemaphore(value: 0)
var caughtError: Error?
Task {
    do {
        try await run(options)
    } catch {
        caughtError = error
    }
    semaphore.signal()
}
semaphore.wait()
if let caughtError {
    FileHandle.standardError.write(Data("scene-vision: \(caughtError)\n".utf8))
    exit(1)
}
