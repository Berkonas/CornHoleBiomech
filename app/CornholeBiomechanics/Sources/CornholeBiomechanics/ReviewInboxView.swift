import AVFoundation
import AVKit
import SwiftUI

// "Needs your eye" (council decisions §6): throws whose result the engine could not decide on its own (the front
// camera asked for confirmation, or gave no category) wait here for a person's In / On / Off. One throw at a time:
// the front camera's clip around the moment the bag came to rest (looping), the front and side readings in one
// line, and three buttons (keys 1 / 2 / 3). The answer is recorded through ProjectStore.confirmResult, which
// never replaces a person's entry; Undo puts back what was there. Landing and rest stay automatic.

/// Keyboard keys for the three answers (council: 1 / 2 / 3 for In / On / Off).
enum ReviewKeys {
    static func key(for score: ScoreCategory) -> KeyEquivalent {
        switch score {
        case .throughHole: KeyEquivalent("1")
        case .onBoard: KeyEquivalent("2")
        case .offBoard: KeyEquivalent("3")
        }
    }
}

struct ReviewInboxView: View {
    @EnvironmentObject private var store: ProjectStore
    @EnvironmentObject private var analysis: AnalysisService
    @EnvironmentObject private var glances: ThrowGlanceStore
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @StateObject private var clip = InboxClipModel()
    @State private var selectedID: UUID?
    /// Throws put back with "Later" (shown after the others).
    @State private var later: [UUID] = []
    @State private var undo: OutcomeUndo?

    var body: some View {
        let items = orderedItems
        let current = items.first { $0.id == selectedID } ?? items.first
        Group {
            if let current {
                Page {
                    header(count: items.count)
                    reviewCard(current, next: nextID(after: current.id, in: items))
                    if items.count > 1 { queueList(items, current: current.id) }
                }
            } else {
                EmptyState("Nothing Needs Your Eye", symbol: "checkmark.circle",
                           message: analysis.hasQueue
                               ? "Throws the cameras are unsure about will appear here as the queue analyses them."
                               : "Every analysed throw has a result the cameras were sure of, or one a person entered.")
            }
        }
        .navigationTitle("Needs Your Eye")
        .safeAreaInset(edge: .top) { undoBanner }
        .task(id: clipRequest(current)) { clip.load(clipRequest(current), autoplay: !reduceMotion) }
        .onDisappear { clip.stop() }
    }

    // MARK: Items

    /// Unsure throws without a person's result, oldest athlete/take/bag first; "Later" ones at the end.
    private var orderedItems: [Trial] {
        let trials = store.project?.trials ?? []
        let athletes = store.project?.athletes ?? []
        let athleteOrder = Dictionary(athletes.enumerated().map { ($0.element.id, $0.offset) }, uniquingKeysWith: { first, _ in first })
        let items = glances.needsEye(trials).sorted { a, b in
            let la = later.firstIndex(of: a.id) ?? -1, lb = later.firstIndex(of: b.id) ?? -1
            if la != lb { return la < lb }
            let aa = athleteOrder[a.athleteID] ?? 0, ab = athleteOrder[b.athleteID] ?? 0
            if aa != ab { return aa < ab }
            if (a.takeNumber ?? 0) != (b.takeNumber ?? 0) { return (a.takeNumber ?? 0) < (b.takeNumber ?? 0) }
            if (a.recordingDate ?? "") != (b.recordingDate ?? "") { return (a.recordingDate ?? "") < (b.recordingDate ?? "") }
            return (a.throwInTake ?? 0) < (b.throwInTake ?? 0)
        }
        return items
    }

    private func nextID(after id: UUID, in items: [Trial]) -> UUID? {
        guard let index = items.firstIndex(where: { $0.id == id }) else { return nil }
        if index + 1 < items.count { return items[index + 1].id }
        return index > 0 ? items[0].id : nil
    }

    private func athleteName(_ trial: Trial) -> String {
        store.project?.athletes.first { $0.id == trial.athleteID }?.displayName ?? "Athlete"
    }

    private func place(_ trial: Trial) -> String {
        var parts = [athleteName(trial)]
        if let take = trial.takeNumber { parts.append("Take \(take)") }
        if let bag = trial.throwInTake { parts.append("Bag \(bag)") } else { parts.append(trial.displayName) }
        return parts.joined(separator: " · ")
    }

    // MARK: Header

    private func header(count: Int) -> some View {
        VStack(alignment: .leading, spacing: Space.xs) {
            Text("Needs your eye").font(.largeTitle.weight(.semibold))
            Text("\(count) throw\(count == 1 ? "" : "s") where the cameras could not tell the result. Watch the front camera and choose In, On or Off (keys 1, 2, 3). Where the bag landed and stopped stays measured automatically.")
                .font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: Review card

    private func reviewCard(_ trial: Trial, next: UUID?) -> some View {
        let glance = glances.glance(trial.id)
        return Card {
            HStack(alignment: .firstTextBaseline) {
                Text(place(trial)).font(.title2.weight(.semibold))
                Spacer()
                if let key = trial.takeKey {
                    Button("Open Take") { store.destination = .take(key) }.buttonStyle(.link)
                }
                Button("Open Report") { store.destination = .throwReport(trial.id) }.buttonStyle(.link)
            }
            ZStack(alignment: .bottomLeading) {
                Color.black
                if clip.hasVideo {
                    NativeVideoPlayer(player: clip.player, showsControls: false)
                } else {
                    Text("The front camera clip is missing for this throw.").foregroundStyle(.white.opacity(0.8))
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
                if clip.hasVideo {
                    Button {
                        clip.togglePlay()
                    } label: {
                        Label(clip.isPlaying ? "Pause" : "Play the landing", systemImage: clip.isPlaying ? "pause.fill" : "play.fill")
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
                    .padding(Space.s)
                }
            }
            .aspectRatio(16 / 9, contentMode: .fit)
            .frame(maxWidth: 760)
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .accessibilityElement(children: .contain)
            .accessibilityLabel("Front camera, around the moment the bag came to rest")

            if let glance {
                Text(GlanceText.readings(glance)).font(.callout.weight(.semibold)).fixedSize(horizontal: false, vertical: true)
                let miss = [GlanceText.depth(glance.shortLong), GlanceText.sideways(glance.leftRight)].compactMap { $0 }
                Text(glance.unsureReason + (miss.isEmpty ? "" : " Measured miss: \(miss.joined(separator: ", ")) of the hole."))
                    .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
            if let outcome = trial.outcome, outcome.isAutomatic, let score = outcome.scoreCategory {
                Label("Recorded automatically as \(score.plainLabel.lowercased()); your answer replaces it.", systemImage: "info.circle")
                    .font(.caption).foregroundStyle(.secondary)
            }
            HStack(spacing: Space.m) {
                ForEach([ScoreCategory.throughHole, .onBoard, .offBoard]) { score in
                    Button {
                        answer(score, trial: trial, glance: glance, next: next)
                    } label: {
                        VStack(spacing: 2) {
                            Text(score.shortWord).font(.title3.weight(.semibold))
                            Text("\(score.plainLabel) · key \(String(ReviewKeys.key(for: score).character))")
                                .font(.caption2).foregroundStyle(.secondary)
                        }
                        .frame(minWidth: 120)
                        .padding(.vertical, 4)
                    }
                    .keyboardShortcut(ReviewKeys.key(for: score), modifiers: [])
                    .accessibilityLabel("\(score.plainLabel), key \(String(ReviewKeys.key(for: score).character))")
                }
                Spacer(minLength: Space.m)
                Button("Later") {
                    later.removeAll { $0 == trial.id }
                    later.append(trial.id)
                    selectedID = next
                }
                .help("Put this throw at the end of the list")
                .disabled(next == nil)
            }
            .controlSize(.large)
        }
    }

    private func answer(_ score: ScoreCategory, trial: Trial, glance: ThrowGlance?, next: UUID?) {
        let points = glance?.measuredBoardPoints
        do {
            if let done = try store.confirmResult(score, trialID: trial.id, contact: points?.contact, rest: points?.rest) {
                undo = done
                later.removeAll { $0 == trial.id }
                selectedID = next == trial.id ? nil : next
            }
        } catch { store.errorMessage = error.localizedDescription }
    }

    @ViewBuilder private var undoBanner: some View {
        if let undo, let trial = store.project?.trials.first(where: { $0.id == undo.trialID }) {
            HStack(spacing: Space.m) {
                Image(systemName: "checkmark.circle.fill").foregroundStyle(.green).accessibilityHidden(true)
                Text("\(place(trial)): \(undo.recorded.plainLabel.lowercased()) recorded.")
                Spacer()
                Button("Undo") {
                    do { try store.restoreOutcome(undo.previous, trialID: undo.trialID) } catch { store.errorMessage = error.localizedDescription }
                    selectedID = undo.trialID
                    self.undo = nil
                }
                Button("Done") { self.undo = nil }
            }
            .font(.callout)
            .padding(.horizontal, Space.l).padding(.vertical, Space.s)
            .background(.regularMaterial)
        }
    }

    // MARK: Up next

    private func queueList(_ items: [Trial], current: UUID) -> some View {
        Card("Up next", symbol: "list.bullet") {
            VStack(alignment: .leading, spacing: 0) {
                ForEach(items.filter { $0.id != current }) { trial in
                    Button {
                        selectedID = trial.id
                    } label: {
                        HStack(spacing: Space.m) {
                            Image(systemName: "eye").foregroundStyle(.orange).accessibilityHidden(true)
                            Text(place(trial))
                            Spacer()
                            if let glance = glances.glance(trial.id) {
                                Text(glance.category.map { "front: \($0.shortWord.lowercased())" } ?? "front: ?")
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                            if later.contains(trial.id) { Text("later").font(.caption).foregroundStyle(.secondary) }
                        }
                        .padding(.vertical, 6)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    Divider()
                }
            }
        }
    }

    // MARK: Clip

    private func clipRequest(_ trial: Trial?) -> InboxClipRequest? {
        guard let trial, let relative = trial.frontVideoRelativePath, let url = store.url(for: relative),
              FileManager.default.fileExists(atPath: url.path) else { return nil }
        let glance = glances.glance(trial.id)
        guard let fps = glance?.frontFPS, fps > 0 else { return InboxClipRequest(url: url, start: nil, end: nil, still: nil) }
        let clipEnd = glance?.frontFrameCount.map { Double($0) / fps }
        let window = Self.clipWindow(fps: fps, frameCount: glance?.frontFrameCount, release: glance?.releaseFront,
                                     contact: glance?.contactFront, rest: glance?.restFront)
        return InboxClipRequest(url: url, start: window.start, end: window.end, still: window.still)
    }

    /// The whole throw, not just the landing: from half a second before release (the swing and the bag leaving the
    /// hand) to a second after the bag stopped. Starting just before first contact, as before, cut the clip mid-flight.
    /// Without a release frame the clip starts 1.2 s before first contact (a flight is about 0.9–1.2 s).
    static func clipWindow(fps: Double, frameCount: Int?, release: Int?, contact: Int?, rest: Int?)
        -> (start: Double?, end: Double?, still: Double?) {
        guard fps > 0 else { return (nil, nil, nil) }
        let t = { (frame: Int?) in frame.map { Double($0) / fps } }
        let clipEnd = t(frameCount)
        let releaseT = t(release), contactT = t(contact), restT = t(rest)
        guard releaseT != nil || contactT != nil || restT != nil else { return (nil, nil, nil) }
        let start = max(0, (releaseT.map { $0 - 0.5 }) ?? ((contactT ?? restT ?? 0) - 1.2))
        var end = max(restT ?? 0, (contactT ?? releaseT.map { $0 + 1.0 } ?? start) + 1.5) + 1.0
        if let clipEnd { end = min(end, clipEnd) }
        return (start, max(end, start + 1), restT ?? contactT)
    }
}

/// Which part of the front clip to loop.
struct InboxClipRequest: Equatable {
    var url: URL
    var start: Double?
    var end: Double?
    /// Shown when paused (the bag at rest).
    var still: Double?
}

/// Loops a short stretch of the front clip (paused on the rest frame when Reduce Motion is on).
@MainActor
final class InboxClipModel: ObservableObject {
    let player = AVQueuePlayer()
    @Published private(set) var isPlaying = false
    @Published private(set) var hasVideo = false
    private var looper: AVPlayerLooper?
    private var current: InboxClipRequest?

    func load(_ request: InboxClipRequest?, autoplay: Bool) {
        guard request != current else { return }
        current = request
        looper?.disableLooping()
        looper = nil
        player.pause()
        player.removeAllItems()
        isPlaying = false
        guard let request else { hasVideo = false; return }
        hasVideo = true
        player.isMuted = true
        let item = AVPlayerItem(url: request.url)
        if let start = request.start, let end = request.end, end > start {
            let range = CMTimeRange(start: CMTime(seconds: start, preferredTimescale: 600),
                                    end: CMTime(seconds: end, preferredTimescale: 600))
            looper = AVPlayerLooper(player: player, templateItem: item, timeRange: range)
        } else {
            looper = AVPlayerLooper(player: player, templateItem: item)
        }
        if autoplay {
            player.play()
            isPlaying = true
        } else {
            showStill()
        }
    }

    func togglePlay() {
        if isPlaying {
            player.pause()
            isPlaying = false
            showStill()
        } else {
            player.play()
            isPlaying = true
        }
    }

    func stop() {
        player.pause()
        isPlaying = false
    }

    private func showStill() {
        guard let still = current?.still else { return }
        player.seek(to: CMTime(seconds: still, preferredTimescale: 600), toleranceBefore: .zero, toleranceAfter: .zero)
    }
}
