import AVFoundation
import AVKit
import SwiftUI

// The Take screen (council decisions §2): the take — four bags — is the main feedback unit after import.
// Top to bottom: points and in/on/off; the take's side + front video as one synchronised video with a
// four-segment throw scrubber; the board from above with the four bags numbered and the group centre; four
// throw chips (result, short sentence, needs-check badge, In / On / Off when the engine was unsure); and a
// mini strip of release speed, angle and heading for bags 1–4 against the athlete's usual band.
// Four bags give a snapshot: ranges only, never an SD.

struct TakeView: View {
    @EnvironmentObject private var store: ProjectStore
    @EnvironmentObject private var analysis: AnalysisService
    @EnvironmentObject private var glances: ThrowGlanceStore
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let key: TakeKey
    @StateObject private var video = TakePlayerModel()
    @State private var undo: OutcomeUndo?

    var body: some View {
        let trials = store.trials(in: key)
        Group {
            if trials.isEmpty {
                EmptyState("Take Not Found", symbol: "questionmark.video", message: "This take is no longer in the library.")
            } else {
                Page {
                    header(trials)
                    videoCard(trials)
                    ViewThatFits(in: .horizontal) {
                        HStack(alignment: .top, spacing: Space.xl) {
                            mapCard(trials).frame(width: 360)
                            VStack(alignment: .leading, spacing: Space.xl) {
                                chips(trials)
                                stripCard(trials)
                            }
                            .frame(minWidth: 520)
                        }
                        VStack(alignment: .leading, spacing: Space.xl) {
                            mapCard(trials)
                            chips(trials)
                            stripCard(trials)
                        }
                    }
                }
            }
        }
        .navigationTitle(title(trials))
        .task(id: clips(trials)) { await video.load(clips(trials), autoplay: false) }
        .onAppear { video.resumeObserving() }
        .onDisappear { video.tearDown() }
        .safeAreaInset(edge: .top) { undoBanner }
    }

    // MARK: Header

    private func title(_ trials: [Trial]) -> String {
        trials.first?.takeNumber.map { "Take \($0)" } ?? "Take"
    }

    private func header(_ trials: [Trial]) -> some View {
        let tally = TakeTally(trials)
        let athlete = store.project?.athletes.first { $0.id == key.athleteID }?.displayName ?? "Athlete"
        let keys = store.takeKeys(athleteID: key.athleteID)
        let index = keys.firstIndex(of: key)
        return HStack(alignment: .firstTextBaseline, spacing: Space.l) {
            VStack(alignment: .leading, spacing: Space.xs) {
                Text("\(title(trials)) · \(athlete)").font(.largeTitle.weight(.semibold))
                Text(subtitle(trials, tally: tally)).font(.callout).foregroundStyle(.secondary)
            }
            Spacer(minLength: Space.m)
            VStack(alignment: .trailing, spacing: 2) {
                Text(tally.pointsText).font(.system(size: 34, weight: .semibold).monospacedDigit())
                Text("points · \(tally.countsText)").font(.callout).foregroundStyle(.secondary).monospacedDigit()
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("\(tally.points) of \(tally.possible) points. \(tally.inHole) in the hole, \(tally.onBoard) on the board, \(tally.offBoard) off.")
            ControlGroup {
                Button { if let index, index > 0 { store.destination = .take(keys[index - 1]) } } label: {
                    Label("Previous Take", systemImage: "chevron.left")
                }
                .disabled(index == nil || index == 0)
                Button { if let index, index + 1 < keys.count { store.destination = .take(keys[index + 1]) } } label: {
                    Label("Next Take", systemImage: "chevron.right")
                }
                .disabled(index == nil || (index ?? 0) + 1 >= keys.count)
            }
            .labelStyle(.iconOnly)
            .fixedSize()
        }
    }

    private func subtitle(_ trials: [Trial], tally: TakeTally) -> String {
        var parts: [String] = []
        if let date = trials.first?.recordingDate.flatMap(Self.formattedDate) { parts.append(date) }
        parts.append("\(trials.count) bag\(trials.count == 1 ? "" : "s"): a snapshot")
        if tally.analysed < trials.count { parts.append("\(tally.analysed) of \(trials.count) analysed") }
        if tally.unscored > 0 { parts.append("\(tally.unscored) without a result yet") }
        return parts.joined(separator: " · ")
    }

    static func formattedDate(_ text: String) -> String? {
        let parser = DateFormatter()
        parser.locale = Locale(identifier: "en_US_POSIX")
        parser.dateFormat = "yyyy-MM-dd"
        return parser.date(from: text)?.formatted(date: .abbreviated, time: .omitted)
    }

    // MARK: Video

    private func clips(_ trials: [Trial]) -> [TakeClip] {
        trials.compactMap { trial -> TakeClip? in
            guard let side = store.videoURL(for: trial) else { return nil }
            let front = trial.frontVideoRelativePath.flatMap { store.url(for: $0) }
                .flatMap { FileManager.default.fileExists(atPath: $0.path) ? $0 : nil }
            let glance = glances.glance(trial.id)
            var release: Double?
            if let frame = glance?.releaseSide, let fps = glance?.sideFPS, fps > 0 { release = Double(frame) / fps }
            return TakeClip(number: trial.throwInTake ?? 0, side: side, front: front,
                            frontOffset: glance?.frontOffsetSeconds, release: release)
        }
    }

    private func videoCard(_ trials: [Trial]) -> some View {
        Card {
            ZStack {
                Color.black
                if video.isReady {
                    NativeVideoPlayer(player: video.player, showsControls: false)
                }
                if let message = video.message {
                    VStack(spacing: Space.s) {
                        if video.isLoading { ProgressView().controlSize(.small) }
                        Text(message).font(.callout).foregroundStyle(.white.opacity(0.8)).multilineTextAlignment(.center)
                    }
                    .padding()
                }
            }
            .aspectRatio(video.aspectRatio, contentMode: .fit)
            .frame(maxWidth: .infinity)
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(video.showsFront ? "Take video: side camera on the left, front camera on the right" : "Take video: side camera")
            HStack(spacing: Space.m) {
                Button {
                    video.togglePlay()
                } label: {
                    Image(systemName: video.isPlaying ? "pause.fill" : "play.fill").frame(width: 18)
                }
                .help(video.isPlaying ? "Pause" : "Play the take")
                .accessibilityLabel(video.isPlaying ? "Pause" : "Play")
                .disabled(!video.isReady)
                TakeScrubber(model: video, clock: video.clock, results: Dictionary(trials.map { ($0.throwInTake ?? 0, $0.outcome?.scoreCategory) },
                                                               uniquingKeysWith: { first, _ in first }))
                    .frame(height: 44)
            }
            Text(video.showsFront
                 ? "Side camera (left) and front camera (right) in step, synchronised from the sound. Each segment is one throw; click a number to jump to that throw's release."
                 : "Side camera. Each segment is one throw; click a number to jump to that throw's release.")
                .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: Board map

    private func mapCard(_ trials: [Trial]) -> some View {
        let bags = trials.map { trial in
            TakeBag(number: trial.throwInTake ?? 0, glance: glances.glance(trial.id), score: trial.outcome?.scoreCategory)
        }
        let group = TakeGroup(bags: bags)
        return Card("From above", symbol: "square.dashed",
                    subtitle: "To scale. Hollow: where it landed; filled: where it stopped.") {
            TakeBoardMap(bags: bags, group: group, highlight: video.isPlaying ? video.currentThrow : nil)
                .frame(height: 470)
            Text(group.sentence).font(.callout.weight(.semibold)).fixedSize(horizontal: false, vertical: true)
            if let range = group.rangeText {
                Text(range).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    // MARK: Chips

    private func chips(_ trials: [Trial]) -> some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 240), spacing: Space.m)], alignment: .leading, spacing: Space.m) {
            ForEach(trials) { trial in
                TakeThrowChip(trial: trial, glance: glances.glance(trial.id),
                              needsEye: !glances.needsEye([trial]).isEmpty,
                              open: { store.destination = .throwReport(trial.id) },
                              record: { score, note in record(score, for: trial, note: note) },
                              analyse: { analysis.enqueue([trial], store: store) })
            }
        }
    }

    private func record(_ score: ScoreCategory, for trial: Trial, note: String) {
        let points = glances.glance(trial.id)?.measuredBoardPoints
        do {
            if let done = try store.confirmResult(score, trialID: trial.id, contact: points?.contact, rest: points?.rest, note: note) {
                undo = done
            }
        } catch { store.errorMessage = error.localizedDescription }
    }

    @ViewBuilder private var undoBanner: some View {
        if let undo, let trial = store.project?.trials.first(where: { $0.id == undo.trialID }) {
            HStack(spacing: Space.m) {
                Image(systemName: "checkmark.circle.fill").foregroundStyle(.green).accessibilityHidden(true)
                Text("Bag \(trial.throwInTake ?? 0): \(undo.recorded.plainLabel) recorded.")
                Spacer()
                Button("Undo") {
                    do { try store.restoreOutcome(undo.previous, trialID: undo.trialID) } catch { store.errorMessage = error.localizedDescription }
                    self.undo = nil
                }
                Button("Done") { self.undo = nil }
            }
            .font(.callout)
            .padding(.horizontal, Space.l).padding(.vertical, Space.s)
            .background(.regularMaterial)
            .transition(reduceMotion ? AnyTransition.identity : AnyTransition.move(edge: .top).combined(with: .opacity))
        }
    }

    // MARK: Release strip

    private func stripCard(_ trials: [Trial]) -> some View {
        let usual = store.project?.trials.filter { $0.athleteID == key.athleteID && $0.takeKey != key && $0.analysisRelativePath != nil }
            .compactMap { glances.glance($0.id) } ?? []
        let mine = trials.map { (number: $0.throwInTake ?? 0, glance: glances.glance($0.id)) }
        let rows: [TakeStripRow] = [
            TakeStripRow(label: "Release speed", unit: "m/s", digits: 1, minimumSpan: 0.6,
                         values: mine.map { ($0.number, $0.glance?.speed) }, usual: usual.compactMap(\.speed)),
            TakeStripRow(label: "Release angle", unit: "°", digits: 0, minimumSpan: 6,
                         values: mine.map { ($0.number, $0.glance?.angle) }, usual: usual.compactMap(\.angle)),
            TakeStripRow(label: "Heading", unit: "°", digits: 1, minimumSpan: 3, halfSteps: true,
                         values: mine.map { ($0.number, $0.glance?.heading) }, usual: usual.compactMap(\.heading),
                         lowLabel: "left", highLabel: "right"),
        ]
        return Card("Release, bag by bag", symbol: "chart.dots.scatter",
                    subtitle: "Bags 1–4 against this athlete's usual (middle half of their other throws, after \(TakeStripRow.minimumUsual)).") {
            Grid(alignment: .leading, horizontalSpacing: Space.l, verticalSpacing: Space.m) {
                ForEach(rows) { row in
                    GridRow {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(row.label).font(.callout.weight(.semibold))
                            Text(row.valuesText).font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                        }
                        .frame(width: 170, alignment: .leading)
                        TakeStrip(row: row).frame(height: 40)
                    }
                }
            }
        }
    }
}

// MARK: - Video model

/// The take video's playhead.
@MainActor
final class TakeClock: ObservableObject {
    @Published var time: Double = 0
}

/// One throw's clips for the take video: side clip, front clip and how they line up.
struct TakeClip: Equatable, Sendable {
    var number: Int
    var side: URL
    var front: URL?
    /// Front-clip time at side-clip time 0 (s); nil = unknown, the clips start together.
    var frontOffset: Double?
    /// Release, seconds into the side clip.
    var release: Double?
}

enum TakeVideoError: LocalizedError {
    case noVideo
    var errorDescription: String? { "No readable video track." }
}

/// The take's throws joined into one video: the side clips one after another, the front clips beside them on
/// the same clock (each placed by the sound sync), drawn side by side by a video composition.
@MainActor
final class TakePlayerModel: ObservableObject {
    struct Segment: Identifiable, Equatable {
        let number: Int
        /// Start and length in the joined video (s).
        let start: Double
        let duration: Double
        /// Release, seconds after the segment start.
        let release: Double?
        var id: Int { number }
    }

    let player = AVPlayer()
    /// The playhead, published separately so only the scrubber redraws while the video plays.
    let clock = TakeClock()
    @Published private(set) var segments: [Segment] = []
    /// The throw under the playhead (changes only when the playhead crosses into another throw).
    @Published private(set) var currentThrow: Int?
    @Published private(set) var isPlaying = false
    @Published private(set) var message: String? = "Loading the take…"
    @Published private(set) var isLoading = true
    @Published private(set) var showsFront = false
    @Published private(set) var aspectRatio: CGFloat = 16 / 9
    private var observer: Any?
    private var loaded: [TakeClip] = []

    var isReady: Bool { !segments.isEmpty }
    var duration: Double { segments.last.map { $0.start + $0.duration } ?? 0 }
    var time: Double { clock.time }

    private func setTime(_ seconds: Double) {
        clock.time = seconds
        let now = segments.last(where: { seconds >= $0.start - 0.001 })?.number
        if now != currentThrow { currentThrow = now }
    }

    func load(_ clips: [TakeClip], autoplay: Bool) async {
        guard clips != loaded else { return }
        let hadVideo = !segments.isEmpty
        let previousTime = time
        loaded = clips
        guard !clips.isEmpty else {
            player.replaceCurrentItem(with: nil)
            segments = []
            isLoading = false
            message = "No video for this take."
            return
        }
        isLoading = true
        if !hadVideo { message = "Loading the take…" }
        do {
            let built = try await Self.build(clips)
            guard clips == loaded else { return }   // a newer load has started
            player.replaceCurrentItem(with: built.item)
            player.isMuted = true
            segments = built.segments
            showsFront = built.hasFront
            aspectRatio = built.aspectRatio
            message = nil
            isLoading = false
            resumeObserving()
            if hadVideo {
                seek(to: previousTime)
            } else if let first = built.segments.first {
                seek(to: first.start + (first.release ?? 0))
            }
            if autoplay { player.play() }
        } catch {
            isLoading = false
            message = "The take's video could not be opened (\(error.localizedDescription))."
        }
    }

    func resumeObserving() {
        guard observer == nil else { return }
        observer = player.addPeriodicTimeObserver(forInterval: CMTime(value: 1, timescale: 30), queue: .main) { [weak self] time in
            MainActor.assumeIsolated {
                guard let self else { return }
                self.tick(time.seconds)
            }
        }
    }

    func tearDown() {
        player.pause()
        isPlaying = false
        if let observer { player.removeTimeObserver(observer) }
        observer = nil
    }

    private func tick(_ seconds: Double) {
        if seconds.isFinite { setTime(seconds) }
        let playing = player.timeControlStatus == .playing
        if playing != isPlaying { isPlaying = playing }
    }

    func togglePlay() {
        guard isReady else { return }
        if player.timeControlStatus == .playing {
            player.pause()
            isPlaying = false
        } else {
            if time >= duration - 0.05 { seek(to: 0) }
            player.play()
            isPlaying = true
        }
    }

    func seek(to seconds: Double) {
        let clamped = min(max(0, seconds), max(0, duration - 0.02))
        setTime(clamped)
        player.seek(to: CMTime(seconds: clamped, preferredTimescale: 600), toleranceBefore: .zero, toleranceAfter: .zero)
    }

    /// Jump to a throw's release (its start when the release was not found).
    func jump(toThrow number: Int) {
        guard let segment = segments.first(where: { $0.number == number }) else { return }
        player.pause()
        isPlaying = false
        seek(to: segment.start + (segment.release ?? 0))
    }

    private struct Built {
        let item: AVPlayerItem
        let segments: [Segment]
        let hasFront: Bool
        let aspectRatio: CGFloat
    }

    private static func build(_ clips: [TakeClip]) async throws -> Built {
        let composition = AVMutableComposition()
        guard let sideTrack = composition.addMutableTrack(withMediaType: .video, preferredTrackID: kCMPersistentTrackID_Invalid) else {
            throw TakeVideoError.noVideo
        }
        let frontTrack = clips.contains(where: { $0.front != nil })
            ? composition.addMutableTrack(withMediaType: .video, preferredTrackID: kCMPersistentTrackID_Invalid) : nil
        var cursor = CMTime.zero
        var frontCursor = CMTime.zero
        var segments: [Segment] = []
        var sideLook: (size: CGSize, transform: CGAffineTransform)?
        var frontLook: (size: CGSize, transform: CGAffineTransform)?
        var frontUsed = false
        for clip in clips {
            let asset = AVURLAsset(url: clip.side)
            guard let source = try await asset.loadTracks(withMediaType: .video).first else { continue }
            let range = try await source.load(.timeRange)
            if sideLook == nil {
                let size = try await source.load(.naturalSize)
                let transform = try await source.load(.preferredTransform)
                sideLook = (size, transform)
            }
            try sideTrack.insertTimeRange(range, of: source, at: cursor)
            let length = range.duration
            let segmentStart = cursor.seconds
            let segmentEnd = segmentStart + length.seconds

            // The front clip on the same clock: front time = side time + offset.
            if let frontTrack, let frontURL = clip.front {
                let frontAsset = AVURLAsset(url: frontURL)
                if let frontSource = try? await frontAsset.loadTracks(withMediaType: .video).first,
                   let frontRange = try? await frontSource.load(.timeRange) {
                    var frontStart = clip.frontOffset ?? 0
                    var placeAt = segmentStart
                    if frontStart < 0 { placeAt -= frontStart; frontStart = 0 }
                    var at = CMTime(seconds: placeAt, preferredTimescale: 600)
                    if CMTimeCompare(at, frontCursor) < 0 { at = frontCursor }
                    let span = min(frontRange.duration.seconds - frontStart, segmentEnd - at.seconds)
                    if span > 0.05 {
                        if CMTimeCompare(frontCursor, at) < 0 {
                            frontTrack.insertEmptyTimeRange(CMTimeRange(start: frontCursor, end: at))
                        }
                        let sourceRange = CMTimeRange(start: CMTimeAdd(frontRange.start, CMTime(seconds: frontStart, preferredTimescale: 600)),
                                                      duration: CMTime(seconds: span, preferredTimescale: 600))
                        if (try? frontTrack.insertTimeRange(sourceRange, of: frontSource, at: at)) != nil {
                            frontCursor = CMTimeAdd(at, sourceRange.duration)
                            frontUsed = true
                            if frontLook == nil, let size = try? await frontSource.load(.naturalSize),
                               let transform = try? await frontSource.load(.preferredTransform) {
                                frontLook = (size, transform)
                            }
                        }
                    }
                }
            }
            let release = clip.release.map { min(max(0, $0), length.seconds) }
            segments.append(Segment(number: clip.number, start: segmentStart, duration: length.seconds, release: release))
            cursor = CMTimeAdd(cursor, length)
        }
        guard let side = sideLook, !segments.isEmpty else { throw TakeVideoError.noVideo }

        // Side by side at a common height: side camera left, front camera right.
        let height: CGFloat = 540
        var layers: [AVMutableVideoCompositionLayerInstruction] = []
        let sidePlace = placement(size: side.size, transform: side.transform, height: height, x: 0)
        let sideLayer = AVMutableVideoCompositionLayerInstruction(assetTrack: sideTrack)
        sideLayer.setTransform(sidePlace.transform, at: .zero)
        layers.append(sideLayer)
        var width = sidePlace.width
        var hasFront = false
        if frontUsed, let frontTrack, let front = frontLook {
            let gap: CGFloat = 8
            let frontPlace = placement(size: front.size, transform: front.transform, height: height, x: width + gap)
            let frontLayer = AVMutableVideoCompositionLayerInstruction(assetTrack: frontTrack)
            frontLayer.setTransform(frontPlace.transform, at: .zero)
            layers.append(frontLayer)
            width += gap + frontPlace.width
            hasFront = true
        } else if let frontTrack {
            composition.removeTrack(frontTrack)
        }
        let instruction = AVMutableVideoCompositionInstruction()
        instruction.timeRange = CMTimeRange(start: .zero, duration: cursor)
        instruction.layerInstructions = layers
        instruction.backgroundColor = CGColor(gray: 0, alpha: 1)
        let videoComposition = AVMutableVideoComposition()
        let renderWidth = max(2, (width / 2).rounded() * 2)
        videoComposition.renderSize = CGSize(width: renderWidth, height: height)
        videoComposition.frameDuration = CMTime(value: 1, timescale: 60)
        videoComposition.instructions = [instruction]
        let item = AVPlayerItem(asset: composition)
        item.videoComposition = videoComposition
        return Built(item: item, segments: segments, hasFront: hasFront, aspectRatio: renderWidth / height)
    }

    /// Scale a track to `height`, honouring its orientation, and move it to `x`.
    private static func placement(size: CGSize, transform: CGAffineTransform, height: CGFloat, x: CGFloat)
        -> (transform: CGAffineTransform, width: CGFloat) {
        let bounds = CGRect(origin: .zero, size: size).applying(transform)
        let scale = height / max(abs(bounds.height), 1)
        let placed = transform
            .concatenating(CGAffineTransform(translationX: -bounds.minX, y: -bounds.minY))
            .concatenating(CGAffineTransform(scaleX: scale, y: scale))
            .concatenating(CGAffineTransform(translationX: x, y: 0))
        return (placed, abs(bounds.width) * scale)
    }
}

// MARK: - Throw scrubber

/// Four segments, one per throw (widths follow the clips' lengths), a tick at each release, the playhead, and the
/// throw numbers as buttons that jump to the release. Dragging along the bar scrubs.
struct TakeScrubber: View {
    @ObservedObject var model: TakePlayerModel
    @ObservedObject var clock: TakeClock
    /// Recorded result per throw number (for the glyph under each segment).
    let results: [Int: ScoreCategory?]

    var body: some View {
        GeometryReader { geometry in
            let layout = Layout(segments: model.segments, width: geometry.size.width)
            ZStack(alignment: .topLeading) {
                Canvas { context, _ in
                    for (segment, rect) in zip(model.segments, layout.rects) {
                        let bar = CGRect(x: rect.minX, y: 4, width: rect.width, height: 10)
                        context.fill(Path(roundedRect: bar, cornerRadius: 3), with: .color(.secondary.opacity(0.18)))
                        let played = min(max(clock.time - segment.start, 0), segment.duration)
                        if played > 0, segment.duration > 0 {
                            let fill = CGRect(x: bar.minX, y: bar.minY, width: bar.width * CGFloat(played / segment.duration), height: bar.height)
                            context.fill(Path(roundedRect: fill, cornerRadius: 3), with: .color(Color.accentColor.opacity(0.45)))
                        }
                        if let release = segment.release, segment.duration > 0 {
                            let x = bar.minX + bar.width * CGFloat(release / segment.duration)
                            var tick = Path(); tick.move(to: CGPoint(x: x, y: 1)); tick.addLine(to: CGPoint(x: x, y: 17))
                            context.stroke(tick, with: .color(eventColor("release")), lineWidth: 2)
                        }
                    }
                    if let x = layout.x(for: clock.time, segments: model.segments) {
                        var head = Path(); head.move(to: CGPoint(x: x, y: 0)); head.addLine(to: CGPoint(x: x, y: 18))
                        context.stroke(head, with: .color(.primary), style: StrokeStyle(lineWidth: 2, lineCap: .round))
                    }
                }
                .frame(height: 18)
                .contentShape(Rectangle())
                .gesture(DragGesture(minimumDistance: 0).onChanged { value in
                    if let time = layout.time(at: value.location.x, segments: model.segments) { model.seek(to: time) }
                })
                ForEach(Array(model.segments.indices), id: \.self) { index in
                    let segment = model.segments[index]
                    let rect = index < layout.rects.count ? layout.rects[index] : .zero
                    Button {
                        model.jump(toThrow: segment.number)
                    } label: {
                        HStack(spacing: 3) {
                            Text("\(segment.number)").font(.caption.weight(.bold).monospacedDigit())
                            if let score = results[segment.number] ?? nil {
                                Text(score.shortWord).font(.caption2).foregroundStyle(.secondary)
                            }
                        }
                        .padding(.horizontal, 6).padding(.vertical, 1)
                        .background(model.currentThrow == segment.number ? Color.accentColor.opacity(0.18) : Color.clear, in: Capsule())
                    }
                    .buttonStyle(.plain)
                    .help("Jump to the release of throw \(segment.number)")
                    .accessibilityLabel("Throw \(segment.number), jump to release")
                    .position(x: rect.midX, y: 32)
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Throw scrubber")
        .accessibilityValue(model.currentThrow.map { "Throw \($0)" } ?? "")
        .accessibilityAdjustableAction { direction in
            let numbers = model.segments.map(\.number)
            guard let current = model.currentThrow, let index = numbers.firstIndex(of: current) else {
                if let first = numbers.first { model.jump(toThrow: first) }
                return
            }
            switch direction {
            case .increment: if index + 1 < numbers.count { model.jump(toThrow: numbers[index + 1]) }
            case .decrement: if index > 0 { model.jump(toThrow: numbers[index - 1]) }
            @unknown default: break
            }
        }
    }

    /// Segment rectangles across the width, 4 pt apart, widths proportional to duration.
    struct Layout {
        let rects: [CGRect]

        init(segments: [TakePlayerModel.Segment], width: CGFloat) {
            let gap: CGFloat = 4
            let total = segments.reduce(0) { $0 + max($1.duration, 0.01) }
            let usable = max(1, width - gap * CGFloat(max(0, segments.count - 1)))
            var x: CGFloat = 0
            var rects: [CGRect] = []
            for segment in segments {
                let w = usable * CGFloat(max(segment.duration, 0.01) / max(total, 0.01))
                rects.append(CGRect(x: x, y: 0, width: w, height: 18))
                x += w + gap
            }
            self.rects = rects
        }

        func x(for time: Double, segments: [TakePlayerModel.Segment]) -> CGFloat? {
            for (segment, rect) in zip(segments, rects) where time <= segment.start + segment.duration + 0.001 {
                let t = segment.duration > 0 ? min(max((time - segment.start) / segment.duration, 0), 1) : 0
                return rect.minX + rect.width * CGFloat(t)
            }
            return rects.last?.maxX
        }

        func time(at x: CGFloat, segments: [TakePlayerModel.Segment]) -> Double? {
            for (segment, rect) in zip(segments, rects) where x <= rect.maxX + 2 {
                let t = rect.width > 0 ? min(max((x - rect.minX) / rect.width, 0), 1) : 0
                return segment.start + segment.duration * Double(t)
            }
            return segments.last.map { $0.start + $0.duration }
        }
    }
}

// MARK: - Board map

/// Floor shown around the board on the take map (in); bags further out are drawn as arrows at the edge.
private let takeMapApron = 12.0

/// One bag of the take on the map.
struct TakeBag: Equatable {
    let number: Int
    let glance: ThrowGlance?
    let score: ScoreCategory?

    var contact: BoardXY? { glance?.contact }
    var rest: BoardXY? { glance?.rest }
    var inHole: Bool { glance?.whereEnded == "hole" }

    /// "Bag 2: on the board, 5 in long and 6 in left of the hole."
    var spoken: String {
        var text = "Bag \(number): "
        if inHole { return text + "in the hole." }
        if let rest {
            let place = rest.isOnDeck ? "on the board" : "off the board"
            let miss = [GlanceText.depth(rest.y - 39), GlanceText.sideways(rest.x - 12)].compactMap { $0 }.joined(separator: " and ")
            text += "\(place), \(miss) of the hole."
        } else {
            text += "where it stopped was not measured."
        }
        return text
    }
}

/// The group of rests: centre (mean) and range. With four bags this is a snapshot, so no SD.
struct TakeGroup: Equatable {
    let count: Int
    let centre: BoardXY?
    let across: Double?
    let along: Double?

    init(bags: [TakeBag]) {
        let rests = bags.compactMap(\.rest)
        count = rests.count
        if rests.count >= 2 {
            centre = BoardXY(x: rests.map(\.x).reduce(0, +) / Double(rests.count), y: rests.map(\.y).reduce(0, +) / Double(rests.count))
            across = (rests.map(\.x).max() ?? 0) - (rests.map(\.x).min() ?? 0)
            along = (rests.map(\.y).max() ?? 0) - (rests.map(\.y).min() ?? 0)
        } else {
            centre = nil; across = nil; along = nil
        }
    }

    /// "Group 6 in right, 4 in short (4 bags)."
    var sentence: String {
        guard let centre else {
            return count == 0 ? "Where the bags stopped is not measured yet." : "One bag located: not enough for a group."
        }
        let parts = [GlanceText.sideways(centre.x - 12), GlanceText.depth(centre.y - 39)].compactMap { $0 }
        return "Group \(parts.joined(separator: ", ")) (\(count) bags)."
    }

    /// "Range 14 in across, 20 in along. Four bags give a snapshot, not a spread."
    var rangeText: String? {
        guard let across, let along else { return nil }
        return "Range \(number(across, digits: 0)) in across, \(number(along, digits: 0)) in along the board. \(count) bags give a snapshot, not a spread."
    }
}

/// The board from above, to scale, thrower at the bottom looking up the board: x across (thrower's left on the
/// left), y up the board. Each bag: landing (hollow ring) → slide (line) → where it stopped (the 6 in bag, filled,
/// numbered); a bag that stopped beyond the view is an arrow at the edge; bags in the hole are numbered around
/// it. The cross is the group centre, with a dashed line from the hole.
struct TakeBoardMap: View {
    let bags: [TakeBag]
    let group: TakeGroup
    /// The bag being played in the video (others fade).
    var highlight: Int? = nil
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        Canvas { context, size in
            let map = MapGeometry(size: size)
            drawBoard(context, map)
            for bag in bags { drawPath(context, map, bag) }
            drawGroup(context, map)
            var holeIndex = 0
            let holeCount = bags.filter(\.inHole).count
            for bag in bags {
                if bag.inHole {
                    drawHoleBag(context, map, bag, index: holeIndex, of: holeCount)
                    holeIndex += 1
                } else {
                    drawRest(context, map, bag)
                }
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("The take from above, to scale")
        .accessibilityValue((bags.map(\.spoken) + [group.sentence]).joined(separator: " "))
    }

    struct MapGeometry {
        let ppi: CGFloat
        let origin: CGPoint   // screen point of board (x 0, y 0): front-left corner

        init(size: CGSize) {
            let a = CGFloat(takeMapApron)
            ppi = max(0.5, min(size.width / (24 + 2 * a), size.height / (48 + 2 * a)))
            let top = (size.height - (48 + 2 * a) * ppi) / 2
            origin = CGPoint(x: (size.width - 24 * ppi) / 2, y: top + (48 + a) * ppi)
        }

        func point(_ p: BoardXY) -> CGPoint {
            CGPoint(x: origin.x + CGFloat(p.x) * ppi, y: origin.y - CGFloat(p.y) * ppi)
        }

        /// The point if it is inside the view, else moved in along the line from the hole (outside = true).
        func shown(_ p: BoardXY) -> (point: BoardXY, outside: Bool) {
            let a = takeMapApron
            let lowX = -a, highX = 24 + a, lowY = -a, highY = 48 + a
            if p.x >= lowX && p.x <= highX && p.y >= lowY && p.y <= highY { return (p, false) }
            let dx = p.x - 12, dy = p.y - 39
            var t = 1.0
            if dx > 0 { t = min(t, (highX - 12) / dx) }
            if dx < 0 { t = min(t, (lowX - 12) / dx) }
            if dy > 0 { t = min(t, (highY - 39) / dy) }
            if dy < 0 { t = min(t, (lowY - 39) / dy) }
            return (BoardXY(x: 12 + dx * t, y: 39 + dy * t), true)
        }
    }

    private var dark: Bool { colorScheme == .dark }

    private func alpha(_ bag: TakeBag) -> Double {
        guard let highlight else { return 1 }
        return bag.number == highlight ? 1 : 0.35
    }

    private func bagInk(_ bag: TakeBag) -> Color {
        switch bag.score {
        case .throughHole?, .onBoard?: scoredInk
        case .offBoard?: missInk
        case nil: Color.gray
        }
    }

    private func caption(_ text: String) -> Text { Text(text).font(.caption2).foregroundStyle(.secondary) }

    private func drawBoard(_ context: GraphicsContext, _ map: MapGeometry) {
        let a = map.point(BoardXY(x: 0, y: 48)), b = map.point(BoardXY(x: 24, y: 0))
        let deck = CGRect(x: a.x, y: a.y, width: b.x - a.x, height: b.y - a.y)
        let board = Path(roundedRect: deck, cornerRadius: 3)
        context.fill(board, with: .color(Color.red.opacity(dark ? 0.30 : 0.16)))
        context.stroke(board, with: .color(.primary.opacity(0.5)), lineWidth: 1.2)
        // Front (low) edge, nearest the thrower.
        var front = Path(); front.move(to: CGPoint(x: deck.minX, y: deck.maxY)); front.addLine(to: CGPoint(x: deck.maxX, y: deck.maxY))
        context.stroke(front, with: .color(.primary.opacity(0.8)), style: StrokeStyle(lineWidth: 3, lineCap: .round))
        var centre = Path(); centre.move(to: CGPoint(x: deck.midX, y: deck.minY)); centre.addLine(to: CGPoint(x: deck.midX, y: deck.maxY))
        context.stroke(centre, with: .color(.primary.opacity(0.15)), style: StrokeStyle(lineWidth: 1, dash: [4, 4]))
        let hole = map.point(.hole), r = 3 * map.ppi
        context.fill(Path(ellipseIn: CGRect(x: hole.x - r, y: hole.y - r, width: 2 * r, height: 2 * r)), with: .color(.primary.opacity(0.85)))
        context.draw(caption("Back"), at: CGPoint(x: deck.midX, y: deck.minY - 3), anchor: .bottom)
        context.draw(caption("Front edge · thrower here ↓"), at: CGPoint(x: deck.midX, y: deck.maxY + 5), anchor: .top)
        context.draw(caption("left"), at: CGPoint(x: deck.minX - 4, y: deck.maxY), anchor: .bottomTrailing)
        context.draw(caption("right"), at: CGPoint(x: deck.maxX + 4, y: deck.maxY), anchor: .bottomLeading)
        // 6 in scale bar beside the back edge.
        let sx = deck.maxX + 6, sy = deck.minY + 2
        var bar = Path()
        bar.move(to: CGPoint(x: sx, y: sy)); bar.addLine(to: CGPoint(x: sx, y: sy + 6 * map.ppi))
        bar.move(to: CGPoint(x: sx - 3, y: sy)); bar.addLine(to: CGPoint(x: sx + 3, y: sy))
        bar.move(to: CGPoint(x: sx - 3, y: sy + 6 * map.ppi)); bar.addLine(to: CGPoint(x: sx + 3, y: sy + 6 * map.ppi))
        context.stroke(bar, with: .color(.secondary), lineWidth: 1.2)
        context.draw(caption("6 in"), at: CGPoint(x: sx + 5, y: sy + 3 * map.ppi), anchor: .leading)
    }

    /// Landing ring and the slide to where the bag stopped.
    private func drawPath(_ context: GraphicsContext, _ map: MapGeometry, _ bag: TakeBag) {
        let opacity = alpha(bag)
        let ink = bagInk(bag)
        let contact = bag.contact.map { map.shown($0).point }
        let rest = bag.rest.map { map.shown($0).point }
        if let contact, let rest {
            var slide = Path(); slide.move(to: map.point(contact)); slide.addLine(to: map.point(rest))
            context.stroke(slide, with: .color(ink.opacity(0.55 * opacity)), style: StrokeStyle(lineWidth: 2, lineCap: .round))
        }
        if let contact {
            let p = map.point(contact)
            let ring = Path(ellipseIn: CGRect(x: p.x - 5, y: p.y - 5, width: 10, height: 10))
            context.fill(ring, with: .color(Color(nsColor: .controlBackgroundColor).opacity(opacity)))
            context.stroke(ring, with: .color(ink.opacity(opacity)), lineWidth: 1.8)
            if bag.rest == nil {
                context.draw(Text("\(bag.number)").font(.caption2.weight(.bold)).foregroundStyle(ink.opacity(opacity)),
                             at: CGPoint(x: p.x + 8, y: p.y), anchor: .leading)
            }
        }
    }

    /// Where the bag stopped: the 6 in bag to scale with its number, or an arrow at the edge of the view.
    private func drawRest(_ context: GraphicsContext, _ map: MapGeometry, _ bag: TakeBag) {
        guard let rest = bag.rest else { return }
        let opacity = alpha(bag)
        let ink = bagInk(bag)
        let shown = map.shown(rest)
        let p = map.point(shown.point)
        if shown.outside {
            let hole = map.point(.hole)
            let dx = p.x - hole.x, dy = p.y - hole.y
            let length = max(hypot(dx, dy), 0.001)
            let ux = dx / length, uy = dy / length
            let base = CGPoint(x: p.x - 12 * ux, y: p.y - 12 * uy)
            var arrow = Path()
            arrow.move(to: p)
            arrow.addLine(to: CGPoint(x: base.x - 6 * uy, y: base.y + 6 * ux))
            arrow.addLine(to: CGPoint(x: base.x + 6 * uy, y: base.y - 6 * ux))
            arrow.closeSubpath()
            context.fill(arrow, with: .color(ink.opacity(opacity)))
            context.draw(Text("\(bag.number)").font(.caption.weight(.bold)).foregroundStyle(ink.opacity(opacity)),
                         at: CGPoint(x: base.x - 10 * ux, y: base.y - 10 * uy))
        } else {
            let side = max(14, 6 * map.ppi)
            let square = Path(roundedRect: CGRect(x: p.x - side / 2, y: p.y - side / 2, width: side, height: side), cornerRadius: side * 0.2)
            context.fill(square, with: .color(ink.opacity(0.92 * opacity)))
            context.stroke(square, with: .color(.white.opacity(0.9 * opacity)), lineWidth: 1.2)
            context.draw(Text("\(bag.number)").font(.system(size: max(10, side * 0.55), weight: .bold)).foregroundStyle(.white.opacity(opacity)), at: p)
        }
    }

    /// Bags in the hole: numbered discs around the hole's rim.
    private func drawHoleBag(_ context: GraphicsContext, _ map: MapGeometry, _ bag: TakeBag, index: Int, of count: Int) {
        let hole = map.point(.hole)
        let opacity = alpha(bag)
        let rim = 3 * map.ppi + 9
        let angle = -Double.pi / 2 + (count <= 1 ? 0 : 2 * Double.pi * Double(index) / Double(count))
        let p = CGPoint(x: hole.x + CGFloat(cos(angle)) * rim, y: hole.y + CGFloat(sin(angle)) * rim)
        let disc = Path(ellipseIn: CGRect(x: p.x - 8, y: p.y - 8, width: 16, height: 16))
        context.fill(disc, with: .color(scoredInk.opacity(opacity)))
        context.stroke(disc, with: .color(.white.opacity(0.9 * opacity)), lineWidth: 1.2)
        context.draw(Text("\(bag.number)").font(.system(size: 10, weight: .bold)).foregroundStyle(.white.opacity(opacity)), at: p)
        let ring = Path(ellipseIn: CGRect(x: hole.x - 3 * map.ppi - 2, y: hole.y - 3 * map.ppi - 2, width: 6 * map.ppi + 4, height: 6 * map.ppi + 4))
        context.stroke(ring, with: .color(eventColor("into_hole").opacity(opacity)), lineWidth: 2)
    }

    /// The group centre (cross) and the dashed line from the hole to it.
    private func drawGroup(_ context: GraphicsContext, _ map: MapGeometry) {
        guard let centre = group.centre else { return }
        let hole = map.point(.hole)
        let shown = map.shown(centre)
        let c = map.point(shown.point)
        var line = Path(); line.move(to: hole); line.addLine(to: c)
        context.stroke(line, with: .color(.primary.opacity(0.6)), style: StrokeStyle(lineWidth: 1.2, dash: [3, 3]))
        var cross = Path()
        cross.move(to: CGPoint(x: c.x - 7, y: c.y)); cross.addLine(to: CGPoint(x: c.x + 7, y: c.y))
        cross.move(to: CGPoint(x: c.x, y: c.y - 7)); cross.addLine(to: CGPoint(x: c.x, y: c.y + 7))
        context.stroke(cross, with: .color(Color(nsColor: .controlBackgroundColor)), style: StrokeStyle(lineWidth: 5, lineCap: .round))
        context.stroke(cross, with: .color(.primary), style: StrokeStyle(lineWidth: 2.2, lineCap: .round))
    }
}

// MARK: - Throw chip

/// One bag of the take: result (with "auto" when the app recorded it), the engine's short sentence, a
/// needs-check badge and In / On / Off when the engine was unsure, and the analysis state while it runs.
/// Clicking the chip opens the throw report.
struct TakeThrowChip: View {
    @EnvironmentObject private var analysis: AnalysisService
    let trial: Trial
    let glance: ThrowGlance?
    let needsEye: Bool
    let open: () -> Void
    let record: (ScoreCategory, String) -> Void
    let analyse: () -> Void
    @State private var hovering = false

    private var isAnalysing: Bool { analysis.isRunning && analysis.activeTrialID == trial.id }
    private var isPersonEntry: Bool {
        guard let outcome = trial.outcome, outcome.scoreCategory != nil else { return false }
        return !outcome.isAutomatic
    }

    var body: some View {
        VStack(alignment: .leading, spacing: Space.s) {
            HStack(spacing: Space.s) {
                Text("Bag \(trial.throwInTake ?? 0)").font(.headline)
                ResultBadge(score: trial.outcome?.scoreCategory)
                if trial.outcome?.isAutomatic == true, trial.outcome?.scoreCategory != nil {
                    Text("auto").font(.caption2.weight(.semibold)).foregroundStyle(.secondary)
                        .padding(.horizontal, 5).padding(.vertical, 1)
                        .overlay(Capsule().strokeBorder(.secondary.opacity(0.5)))
                        .help("Recorded automatically from the front camera. Change it in the report if it is wrong.")
                        .accessibilityLabel("recorded automatically")
                }
                Spacer(minLength: 0)
                if needsEye {
                    Label("Needs your eye", systemImage: "eye").font(.caption.weight(.semibold)).foregroundStyle(.orange)
                        .labelStyle(.titleAndIcon)
                }
            }
            content
            if needsEye {
                HStack(spacing: Space.s) {
                    ForEach([ScoreCategory.throughHole, .onBoard, .offBoard]) { score in
                        Button(score.shortWord) { record(score, TrialOutcome.confirmedByEyeNote) }
                            .help("Record: \(score.plainLabel.lowercased())")
                            .accessibilityLabel("Record \(score.plainLabel)")
                    }
                    Spacer(minLength: 0)
                }
                .controlSize(.small)
            }
        }
        .padding(Space.m)
        .frame(maxWidth: .infinity, minHeight: 112, alignment: .topLeading)
        .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: Radius.card))
        .overlay(RoundedRectangle(cornerRadius: Radius.card)
            .strokeBorder(needsEye ? Color.orange.opacity(0.7) : hovering ? Color.accentColor.opacity(0.6) : Color(nsColor: .separatorColor).opacity(0.6),
                          lineWidth: needsEye ? 1.5 : 1))
        .contentShape(RoundedRectangle(cornerRadius: Radius.card))
        .onTapGesture(perform: open)
        .onHover { hovering = $0 }
        .help("Open the report for bag \(trial.throwInTake ?? 0)")
        .accessibilityElement(children: .contain)
        .accessibilityAddTraits(.isButton)
        .accessibilityAction(named: "Open report", open)
        .contextMenu {
            Button("Open Report", action: open)
            if !isPersonEntry && trial.analysisRelativePath != nil {
                Divider()
                ForEach([ScoreCategory.throughHole, .onBoard, .offBoard]) { score in
                    Button("Record \(score.plainLabel)") {
                        record(score, needsEye ? TrialOutcome.confirmedByEyeNote : "Entered by eye on the Take screen.")
                    }
                }
            }
        }
    }

    @ViewBuilder private var content: some View {
        if isAnalysing {
            VStack(alignment: .leading, spacing: 4) {
                Text("Analysing · \(analysis.stageLabel)").font(.callout).foregroundStyle(.secondary)
                ProgressView(value: analysis.progress).progressViewStyle(.linear)
            }
        } else if let place = analysis.queuePosition(of: trial.id) {
            let waiting: String = place == 1 ? "Next in the queue" : "Waiting in the queue · \(place - 1) ahead"
            Label(waiting, systemImage: "clock")
                .font(.callout).foregroundStyle(.secondary)
        } else if trial.analysisRelativePath == nil {
            HStack {
                Text(trial.analysisStatus).font(.callout).foregroundStyle(.secondary)
                Spacer()
                Button("Analyse", action: analyse).controlSize(.small)
            }
        } else if let sentence = glance?.shortSentence {
            Text(sentence).font(.callout).fixedSize(horizontal: false, vertical: true).lineLimit(3)
                .help(glance?.sentence ?? sentence)
        } else if needsEye, let glance {
            Text(glance.unsureReason).font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        } else {
            Text(glance?.hasTwoView == true ? "No sentence for this throw." : "No front-camera reading for this throw.")
                .font(.callout).foregroundStyle(.secondary)
        }
    }
}

// MARK: - Release strip

/// One measure for bags 1–4 with the athlete's usual band.
struct TakeStripRow: Identifiable {
    /// Throws needed before a usual band is drawn.
    static let minimumUsual = 8

    let label: String
    let unit: String
    let digits: Int
    let minimumSpan: Double
    var halfSteps = false
    let values: [(Int, Double?)]
    let usual: [Double]
    var lowLabel: String? = nil
    var highLabel: String? = nil
    var id: String { label }

    init(label: String, unit: String, digits: Int, minimumSpan: Double, halfSteps: Bool = false,
         values: [(Int, Double?)], usual: [Double], lowLabel: String? = nil, highLabel: String? = nil) {
        self.label = label; self.unit = unit; self.digits = digits; self.minimumSpan = minimumSpan
        self.halfSteps = halfSteps; self.values = values; self.usual = usual
        self.lowLabel = lowLabel; self.highLabel = highLabel
    }

    /// Middle half of the athlete's other throws (needs `minimumUsual`).
    var band: ClosedRange<Double>? {
        guard usual.count >= Self.minimumUsual, let (q1, q3) = RangeBarModel(values: usual, current: nil, target: nil).quartiles,
              q3 >= q1 else { return nil }
        return q1...q3
    }

    func format(_ value: Double) -> String {
        let shown = halfSteps ? (value * 2).rounded() / 2 : value
        let digitsShown = halfSteps ? (shown == shown.rounded() ? 0 : 1) : digits
        return number(shown, digits: digitsShown) + (unit == "°" ? "°" : "")
    }

    /// "7.5 · 7.4 · — · 6.9 m/s".
    var valuesText: String {
        let parts = values.map { $0.1.map(format) ?? "—" }
        return parts.joined(separator: " · ") + (unit == "°" ? "" : " \(unit)")
    }

    var domain: ClosedRange<Double> {
        var points = values.compactMap { $0.1 }
        if let band { points += [band.lowerBound, band.upperBound] }
        guard var lo = points.min(), var hi = points.max() else { return 0...1 }
        if hi - lo < minimumSpan { let mid = (lo + hi) / 2; lo = mid - minimumSpan / 2; hi = mid + minimumSpan / 2 }
        let pad = 0.12 * (hi - lo)
        return (lo - pad)...(hi + pad)
    }
}

struct TakeStrip: View {
    let row: TakeStripRow

    var body: some View {
        Canvas { context, size in
            let domain = row.domain
            let span = max(domain.upperBound - domain.lowerBound, 1e-9)
            let inset: CGFloat = 10
            func x(_ v: Double) -> CGFloat { inset + CGFloat((v - domain.lowerBound) / span) * (size.width - 2 * inset) }
            let mid = size.height * 0.42
            var axis = Path(); axis.move(to: CGPoint(x: inset, y: mid)); axis.addLine(to: CGPoint(x: size.width - inset, y: mid))
            context.stroke(axis, with: .color(.primary.opacity(0.15)), lineWidth: 1)
            if let band = row.band {
                let rect = CGRect(x: x(band.lowerBound), y: mid - 9, width: max(3, x(band.upperBound) - x(band.lowerBound)), height: 18)
                context.fill(Path(roundedRect: rect, cornerRadius: 4), with: .color(athleteInk.opacity(0.22)))
                context.draw(Text("usual").font(.caption2).foregroundStyle(.secondary), at: CGPoint(x: rect.midX, y: size.height), anchor: .bottom)
            }
            if row.lowLabel != nil, domain.contains(0) {
                var zero = Path(); zero.move(to: CGPoint(x: x(0), y: mid - 11)); zero.addLine(to: CGPoint(x: x(0), y: mid + 11))
                context.stroke(zero, with: .color(.primary.opacity(0.4)), lineWidth: 1)
            }
            // Numbered dots; a dot too close to the previous one moves up or down so both stay readable.
            var placed: [CGPoint] = []
            for (number, value) in row.values {
                guard let value else { continue }
                var p = CGPoint(x: x(value), y: mid)
                let crowded = placed.filter { abs($0.x - p.x) < 15 }.count
                if crowded > 0 { p.y += (crowded % 2 == 1 ? -1 : 1) * CGFloat(7 * ((crowded + 1) / 2)) }
                placed.append(p)
                let disc = Path(ellipseIn: CGRect(x: p.x - 8, y: p.y - 8, width: 16, height: 16))
                context.fill(disc, with: .color(Color.primary.opacity(0.85)))
                context.draw(Text("\(number)").font(.system(size: 10, weight: .bold)).foregroundStyle(Color(nsColor: .controlBackgroundColor)), at: p)
            }
            if let low = row.lowLabel { context.draw(Text("← \(low)").font(.caption2).foregroundStyle(.secondary), at: CGPoint(x: inset, y: size.height), anchor: .bottomLeading) }
            if let high = row.highLabel { context.draw(Text("\(high) →").font(.caption2).foregroundStyle(.secondary), at: CGPoint(x: size.width - inset, y: size.height), anchor: .bottomTrailing) }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(row.label)
        .accessibilityValue(accessibilityText)
    }

    private var accessibilityText: String {
        var parts = row.values.map { "bag \($0.0) \($0.1.map(row.format) ?? "not measured")" }
        if let band = row.band { parts.append("usual \(row.format(band.lowerBound)) to \(row.format(band.upperBound))") }
        return parts.joined(separator: ", ")
    }
}
