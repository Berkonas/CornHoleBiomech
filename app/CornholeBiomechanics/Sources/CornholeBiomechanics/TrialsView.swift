import AVFoundation
import AVKit
import SwiftUI

struct TrialsView: View {
    @EnvironmentObject private var store: ProjectStore
    let beginImport: () -> Void

    var body: some View {
        HSplitView {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text(store.selectedAthlete?.displayName ?? "Recorded Throws").font(.headline)
                    Spacer()
                    Button(action: beginImport) { Image(systemName: "plus") }.help("Import local video")
                }
                List((store.project?.trials ?? []).filter { store.selectedAthleteID == nil || $0.athleteID == store.selectedAthleteID }, selection: $store.selectedTrialID) { trial in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(trial.displayName).lineLimit(1)
                        HStack {
                            Text(athleteName(trial.athleteID))
                            Text("·")
                            Text(trial.cameraView.label)
                            Spacer()
                            if trial.isReference { Image(systemName: "bookmark.fill").foregroundStyle(.tint) }
                        }.font(.caption).foregroundStyle(.secondary)
                        HStack(spacing: 4) {
                            if case .missing = store.videoState(for: trial) {
                                StatusPill(text: "Missing video", color: .orange)
                            } else if trial.analysisRelativePath == nil {
                                StatusPill(text: trial.analysisStatus, color: .secondary)
                            } else {
                                switch store.flightStatus(for: trial) {
                                case "accepted": StatusPill(text: "Bag ✓ auto", color: .green)
                                case "needs_review": StatusPill(text: "Bag: review", color: .orange)
                                case "not_found": StatusPill(text: "No flight found", color: .secondary)
                                default: StatusPill(text: trial.analysisStatus, color: .green)
                                }
                            }
                            if let score = trial.outcome?.scoreCategory {
                                StatusPill(text: score == .throughHole ? "Hole" : score == .onBoard ? "Board" : "Miss",
                                           color: score == .throughHole ? .green : score == .onBoard ? .orange : .red)
                            }
                        }
                    }.padding(.vertical, 3).tag(trial.id)
                }
            }.padding().frame(minWidth: 210, idealWidth: 240, maxWidth: 280)

            if let trial = store.selectedTrial {
                TrialDetailView(trial: trial)
            } else {
                ContentUnavailableView("Select or import a throw", systemImage: "video", description: Text("Choose an athlete, import a video, then analyze and review the throw. Results brings the measurements and observed outcome together."))
            }
        }
    }

    private func athleteName(_ id: UUID) -> String {
        store.project?.athletes.first { $0.id == id }?.displayName ?? "Unknown athlete"
    }
}

struct TrialDetailView: View {
    @EnvironmentObject private var store: ProjectStore
    @EnvironmentObject private var analysis: AnalysisService
    let trial: Trial
    @StateObject private var data = TrialDataController()
    @State private var selectedTab = "Inspect"
    @State private var editingMetadata = false
    @State private var deletionTarget: String?
    @State private var preparingVideo = false

    var body: some View {
        VStack(spacing: 0) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(trial.displayName).font(.title2.weight(.semibold)).lineLimit(1)
                    Text("\(athleteName) · \(trial.cameraView.label) view · \(trial.throwingSide.label)-hand throw")
                        .foregroundStyle(.secondary)
                }
                Spacer()
                if trial.isReference { StatusPill(text: "Reference", color: .blue) }
                if trial.outcome?.scoreCategory != nil { StatusPill(text: "Outcome recorded", color: .secondary) }
                Menu {
                    Button("Edit Throw…") { editingMetadata = true }
                    Button("Reveal Source Video") { store.revealVideo(for: trial) }
                    Button("Locate / Relink Video…") { store.locateAndRelinkVideo(for: trial) }
                    Divider()
                    Button("Re-run Analysis") { Task { await analysis.analyze(trial: trial, store: store) } }
                        .disabled(!store.videoState(for: trial).isAvailable || analysis.isRunning)
                    Button("Delete Analysis…", role: .destructive) { deletionTarget = "analysis" }
                        .disabled(trial.analysisRelativePath == nil)
                    Button("Delete Throw…", role: .destructive) { deletionTarget = "throw" }
                } label: { Label("Manage", systemImage: "ellipsis.circle") }.disabled(analysis.isRunning)
            }.padding([.horizontal, .top], 20)
            Picker("Trial section", selection: $selectedTab) {
                Text("Inspect & Correct").tag("Inspect")
                Text("Review events & quality").tag("Quality")
                Text("Research data").tag("Measurements")
            }.pickerStyle(.segmented).labelsHidden().padding()
            HStack {
                Button("Trim / Crop / Rotate…") { preparingVideo = true }.disabled(analysis.isRunning || store.originalVideoURL(for: trial) == nil)
                Button(trial.analysisRelativePath == nil ? "Analyze throw" : "Reanalyze") { Task { await analysis.analyze(trial: trial, store: store) } }
                    .disabled(analysis.isRunning || store.videoURL(for: trial) == nil)
                Button("Understand this throw") { store.destination = .throwReport(trial.id) }.buttonStyle(.borderedProminent).disabled(trial.analysisRelativePath == nil)
                Button("Add / edit outcome") { NotificationCenter.default.post(name: .addTrialOutcome, object: nil) }.disabled(analysis.isRunning)
                if let error = data.loadError { Text(error).font(.caption).foregroundStyle(.orange) }
                Spacer()
            }.padding(.horizontal).padding(.bottom, 10)
            Divider()
            Group {
                switch selectedTab {
                case "Measurements": MeasurementsView(data: data)
                case "Quality": QualityEventsView(data: data)
                case "Metadata": TrialMetadataView(trial: trial)
                default:
                    if case .missing = store.videoState(for: trial) {
                        ContentUnavailableView {
                            Label("Recording unavailable", systemImage: "exclamationmark.triangle")
                        } description: {
                            Text(trial.preparedVideoRelativePath == nil ? "The record and analysis were retained. Locate the moved original to relink this throw." : "The prepared copy is missing. Prepare a new copy from the original, or use the original again; fresh analysis will be required.")
                        } actions: {
                            Button(store.originalVideoURL(for: trial) == nil ? "Locate / Relink…" : "Prepare from original…") {
                                if store.originalVideoURL(for: trial) == nil { store.locateAndRelinkVideo(for: trial) }
                                else { preparingVideo = true }
                            }
                                .buttonStyle(.borderedProminent)
                        }
                    } else if let videoURL = store.videoURL(for: trial), data.pose != nil {
                        VideoPoseEditor(videoURL: videoURL, data: data, confidenceThreshold: store.project?.analysisSettings.confidenceThreshold ?? 0.35, reanalyze: { Task { await analysis.analyze(trial: trial, store: store) } }).id(trial.id)
                    } else if analysis.activeTrialID == trial.id {
                        ContentUnavailableView("Analyzing video", systemImage: "waveform.path.ecg", description: Text(analysis.detail))
                    } else {
                        VStack(spacing: 16) {
                            if let url = store.videoURL(for: trial) { UnanalyzedVideoPreview(url: url).id(url) }
                            Text("One throw per clip · Keep athlete, full flight and landing in frame. Trim time only when possible.").font(.callout).foregroundStyle(.secondary)
                        }.padding()
                    }
                }
            }.frame(maxWidth: .infinity, maxHeight: .infinity).disabled(analysis.isRunning)
        }
        .task(id: trial.id) { data.load(analysisURL: store.analysisURL(for: trial)) }
        .onChange(of: analysis.isRunning) { oldValue, newValue in
            if oldValue && !newValue { data.load(analysisURL: store.analysisURL(for: store.selectedTrial ?? trial)) }
        }
        .sheet(isPresented: $editingMetadata) { TrialEditForm(trial: trial) }
        .sheet(isPresented: $preparingVideo, onDismiss: { data.load(analysisURL: store.analysisURL(for: store.selectedTrial ?? trial)) }) { VideoPreparationView(trial: trial) }
        .onChange(of: trial.analysisRelativePath) { _, _ in data.load(analysisURL: store.analysisURL(for: trial)) }
        .confirmationDialog(
            deletionTarget == "analysis" ? "Delete derived analysis?" : "Delete this throw?",
            isPresented: Binding(get: { deletionTarget != nil }, set: { if !$0 { deletionTarget = nil } }),
            titleVisibility: .visible
        ) {
            if deletionTarget == "analysis" {
                Button("Delete Analysis", role: .destructive) {
                    do { try store.deleteAnalysis(for: trial) }
                    catch { store.errorMessage = error.localizedDescription }
                    deletionTarget = nil
                }
            } else {
                Button("Delete Throw and Managed Files", role: .destructive) {
                    do { try store.deleteTrial(trial) }
                    catch { store.errorMessage = error.localizedDescription }
                    deletionTarget = nil
                }
            }
            Button("Cancel", role: .cancel) { deletionTarget = nil }
        } message: {
            Text(deletionTarget == "analysis"
                 ? "Pose, kinematics, plots, and comparisons are removed. The source video remains."
                 : "The throw record, its managed video copy, analysis, and reference assignments are moved to Trash when possible.")
        }
    }

    private var athleteName: String {
        store.project?.athletes.first { $0.id == trial.athleteID }?.displayName ?? "Unknown athlete"
    }
}

private struct UnanalyzedVideoPreview: View {
    let url: URL
    @State private var player: AVPlayer
    init(url: URL) {
        self.url = url
        _player = State(initialValue: AVPlayer(url: url))
    }
    var body: some View {
        NativeVideoPlayer(player: player, showsControls: true)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .onDisappear { player.pause() }
    }
}

struct VideoPoseEditor: View {
    private var undoManager: UndoManager? { data.correctionUndoManager }
    let videoURL: URL
    @ObservedObject var data: TrialDataController
    let confidenceThreshold: Double
    let reanalyze: () -> Void
    @State private var player: AVPlayer
    private var currentFrame: Int {
        get { data.inspectionFrame }
        nonmutating set { data.inspectionFrame = newValue }
    }
    @State private var selectedLandmark = "right_wrist"
    @State private var timeObserver: Any?
    @State private var interpolationNotice: String?
    @State private var showCoordinates = false
    @State private var showBagSeed = false
    @State private var showBagCoordinates = false
    @State private var showFlightReview = false

    init(videoURL: URL, data: TrialDataController, confidenceThreshold: Double, reanalyze: @escaping () -> Void) {
        self.videoURL = videoURL
        self.data = data
        self.confidenceThreshold = confidenceThreshold
        self.reanalyze = reanalyze
        _player = State(initialValue: AVPlayer(url: videoURL))
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(data.bagTrack == nil ? "Next: track the bag" : data.bagTrack?.isAutomaticallyVerified == true ? "Bag flight found automatically" : "Review the bag through flight").font(.headline)
                    Text(data.bagTrack == nil
                         ? "The bag's flight could not be found automatically. Pause near release, select the bag, then track it through the throw."
                         : data.bagTrack?.isAutomaticallyVerified == true
                         ? "Release and first contact were found from the bag's flight and checked against projectile physics. Play the video; correct only if the cyan path leaves the bag."
                         : "Cyan is automatic tracking. Inspect every frame, confirm the path, and mark release/contact before interpreting metrics.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Button(data.bagTrack == nil ? "Select & track bag…" : "Select bag again…") { player.pause(); showBagSeed = true }
                    .buttonStyle(.borderedProminent)
                if data.bagTrack != nil {
                    Button("Confirm path through frame \(currentFrame)") {
                        player.pause(); data.markBagReviewed(through: currentFrame); reanalyze()
                    }.disabled(currentFrame <= (data.bagSeed?.frameIndex ?? 0))
                }
            }.padding(12)
            GeometryReader { geometry in
                ZStack {
                    Color.black
                    NativeVideoPlayer(player: player, showsControls: false)
                    // Redraw overlays on every display refresh from the player's actual
                    // time while playing, so the skeleton never trails the picture.
                    TimelineView(.animation(minimumInterval: nil, paused: player.timeControlStatus != .playing)) { _ in
                        let frame = displayedFrame
                        ZStack {
                            if data.pose != nil {
                                PoseOverlay(
                                    data: data, frame: frame, selectedLandmark: $selectedLandmark,
                                    confidenceThreshold: confidenceThreshold, availableSize: geometry.size
                                ) { landmark, x, y in
                                    player.pause()
                                    data.setCorrection(frame: currentFrame, landmark: landmark, x: x, y: y, undoManager: undoManager)
                                }
                            }
                            if data.bagTrack != nil {
                                BagOverlay(data: data, frame: frame, availableSize: geometry.size)
                            }
                        }
                    }
                    VStack {
                        HStack {
                            angleBadge("2D projected elbow", field: "elbow_angle_deg")
                            angleBadge("Trunk inclination", field: "trunk_inclination_deg")
                            Spacer()
                            Text("Frame \(currentFrame)").monospacedDigit().padding(7).background(.black.opacity(0.65), in: Capsule()).foregroundStyle(.white)
                        }.padding()
                        Spacer()
                    }
                }
            }
            .aspectRatio(data.pose.map { Double($0.width) / Double($0.height) } ?? 16 / 9, contentMode: .fit)
            Divider()
            VStack(spacing: 10) {
                HStack {
                    Button { step(-1) } label: { Label("Previous frame", systemImage: "backward.frame.fill") }.labelStyle(.iconOnly)
                    Button { player.timeControlStatus == .playing ? player.pause() : player.play() } label: { Label("Play or pause", systemImage: player.timeControlStatus == .playing ? "pause.fill" : "play.fill") }.labelStyle(.iconOnly)
                    Button { step(1) } label: { Label("Next frame", systemImage: "forward.frame.fill") }.labelStyle(.iconOnly)
                    Slider(value: frameBinding, in: 0...Double(max(0, (data.pose?.frameCount ?? 1) - 1)), step: 1)
                    Text(timeLabel).font(.caption.monospacedDigit()).frame(width: 110)
                }
                HStack {
                    Picker("Selected landmark", selection: $selectedLandmark) {
                        ForEach(primaryLandmarks, id: \.self) { Text($0.replacingOccurrences(of: "_", with: " ").capitalized).tag($0) }
                    }.frame(maxWidth: 250)
                    Spacer(minLength: 0)
                    Text(data.correction(frame: currentFrame, landmark: selectedLandmark)?.kind.capitalized ?? "Automatic")
                        .font(.caption).foregroundStyle(.secondary)
                }
                HStack {
                    Menu("Correction actions") {
                        Button("Enter pixel coordinates…") { player.pause(); showCoordinates = true }
                        Button("Reset to automatic") {
                            player.pause()
                            data.resetCorrection(frame: currentFrame, landmark: selectedLandmark, undoManager: undoManager)
                        }.disabled(data.correction(frame: currentFrame, landmark: selectedLandmark) == nil)
                        Button("Interpolate between anchors") {
                            player.pause()
                            let count = data.interpolate(landmark: selectedLandmark, through: currentFrame, undoManager: undoManager)
                            interpolationNotice = count > 0 ? "Added \(count) reversible interpolated corrections. Reanalyze to update kinematics." : "Add manual corrections on both sides of this frame first."
                        }
                        Button("Remove interpolation") {
                            let count = data.clearInterpolated(landmark: selectedLandmark, undoManager: undoManager)
                            interpolationNotice = "Removed \(count) interpolated corrections."
                        }
                    }.fixedSize()
                    Button("Undo") { data.correctionUndoManager.undo() }.disabled(!data.correctionUndoManager.canUndo)
                    Button("Redo") { data.correctionUndoManager.redo() }.disabled(!data.correctionUndoManager.canRedo)
                    Menu("Mark event") {
                        ForEach(eventNames, id: \.0) { name, label in
                            Button("\(label) at frame \(currentFrame)") {
                                player.pause()
                                data.setManualEvent(name: name, frame: currentFrame)
                                interpolationNotice = "\(label) marked at frame \(currentFrame). Reanalyze to update Results."
                            }
                        }
                    }.fixedSize()
                    Button("Flight & scale…") { player.pause(); showFlightReview = true }
                    Menu("Bag tracking") {
                        Button(data.bagSeed == nil ? "Seed tracker rectangle…" : "Replace tracker seed…") {
                            player.pause()
                            showBagSeed = true
                        }
                        Button("Correct centroid at frame \(currentFrame)…") {
                            player.pause()
                            showBagCoordinates = true
                        }.disabled(data.bagTrack == nil)
                        Button("Reset centroid to automatic") {
                            player.pause()
                            data.resetBagCorrection(frame: currentFrame)
                            interpolationNotice = "Removed the bag correction at frame \(currentFrame). Reanalyze to update launch metrics."
                        }.disabled(data.bagCorrection(frame: currentFrame) == nil)
                        Button("Interpolate between reviewed bag points") {
                            player.pause()
                            let count = data.interpolateBag(through: currentFrame)
                            interpolationNotice = count > 0 ? "Added \(count) reviewed bag interpolation points. Reanalyze to update launch metrics." : "Add reviewed bag centroids on both sides of this frame first."
                        }.disabled(data.bagTrack == nil)
                        Divider()
                        Button("Mark reviewed through frame \(currentFrame)") {
                            player.pause()
                            data.markBagReviewed(through: currentFrame)
                            interpolationNotice = "Bag identity marked reviewed through frame \(currentFrame). Reanalyze to determine whether this covers the complete launch-fit interval."
                        }.disabled(data.bagTrack == nil)
                        Button("Clear bag review") {
                            player.pause()
                            data.clearBagReview()
                            interpolationNotice = "Cleared bag-track review approval. Launch metrics will remain suppressed after reanalysis."
                        }.disabled(data.bagCorrections.reviewedThroughFrame == nil)
                    }.fixedSize()
                    Spacer(minLength: 0)
                }
                if let interpolationNotice { Text(interpolationNotice).font(.caption).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading) }
                Text("Pause, then drag a joint. Bag tracking begins from one reviewed rectangle; cyan is automatic, yellow is manual, and purple is reviewed interpolation. Raw pose and bag tracks remain unchanged; corrections are stored separately. Reanalyze after edits.")
                    .font(.caption).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading)
            }.padding(14)
        }
        .focusedSceneObject(data)
        .sheet(isPresented: $showCoordinates) {
            LandmarkCoordinateEditor(data: data, frame: currentFrame, landmark: selectedLandmark)
        }
        .sheet(isPresented: $showBagSeed) {
            BagSelectionView(data: data, videoURL: videoURL, frame: currentFrame, onTrack: reanalyze)
        }
        .sheet(isPresented: $showFlightReview) { FlightReviewEditor(data: data, frame: currentFrame) }
        .sheet(isPresented: $showBagCoordinates) {
            BagCoordinateEditor(data: data, frame: currentFrame)
        }
        .onAppear { frameBinding.wrappedValue = Double(currentFrame); installTimeObserver() }
        .onDisappear { removeTimeObserver(); player.pause() }
    }

    private var primaryLandmarks: [String] { ["left_shoulder", "right_shoulder", "left_elbow", "right_elbow", "left_wrist", "right_wrist", "left_hip", "right_hip"] }
    private var timeLabel: String {
        let fps = data.pose?.fps ?? 1
        return "\((Double(currentFrame) / fps).formatted(.number.precision(.fractionLength(2)))) s"
    }
    private var frameBinding: Binding<Double> {
        Binding(get: { Double(currentFrame) }, set: { value in
            player.pause()
            currentFrame = Int(value)
            player.seek(to: CMTime(seconds: Double(currentFrame) / max(1, data.pose?.fps ?? 30), preferredTimescale: 60000), toleranceBefore: .zero, toleranceAfter: .zero)
        })
    }

    private func angleBadge(_ label: String, field: String) -> some View {
        let value = data.value(field: field, frame: currentFrame)
        return Text(value.map { "\(label): \($0.formatted(.number.precision(.fractionLength(1))))°" } ?? "\(label): unavailable")
            .font(.caption.monospacedDigit()).padding(7).background(.black.opacity(0.65), in: Capsule()).foregroundStyle(.white)
    }
    /// The frame actually on screen: read from the player while playing, else the inspected frame.
    private var displayedFrame: Int {
        guard player.timeControlStatus == .playing, let pose = data.pose else { return currentFrame }
        return min(max(0, Int((player.currentTime().seconds * pose.fps).rounded())), max(0, pose.frameCount - 1))
    }
    private func step(_ amount: Int) { frameBinding.wrappedValue = Double(min(max(0, currentFrame + amount), max(0, (data.pose?.frameCount ?? 1) - 1))) }
    private func installTimeObserver() {
        guard timeObserver == nil else { return }
        let fps = data.pose?.fps ?? 30
        let maximumFrame = max(0, (data.pose?.frameCount ?? 1) - 1)
        timeObserver = player.addPeriodicTimeObserver(forInterval: CMTime(seconds: 1 / max(1, fps), preferredTimescale: 60000), queue: .main) { time in
            currentFrame = min(max(0, Int((time.seconds * fps).rounded())), maximumFrame)
        }
    }
    private func removeTimeObserver() { if let timeObserver { player.removeTimeObserver(timeObserver); self.timeObserver = nil } }
}

private struct LandmarkCoordinateEditor: View {
    @ObservedObject var data: TrialDataController
    let frame: Int
    let landmark: String
    @Environment(\.dismiss) private var dismiss
    @State private var x = ""
    @State private var y = ""
    private var point: (Double, Double)? {
        guard let px = Double(x), let py = Double(y), px.isFinite, py.isFinite,
              let pose = data.pose, (0...Double(pose.width)).contains(px),
              (0...Double(pose.height)).contains(py) else { return nil }
        return (px, py)
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Correct \(landmark.replacingOccurrences(of: "_", with: " "))").font(.title2)
            Text("Frame \(frame) · Original video pixels, measured from the top-left corner.").foregroundStyle(.secondary)
            TextField("X pixel", text: $x)
            TextField("Y pixel", text: $y)
            Text("Allowed: x 0–\(data.pose?.width ?? 0), y 0–\(data.pose?.height ?? 0). This creates a separate, undoable manual correction.").font(.caption).foregroundStyle(.secondary)
            HStack {
                Spacer()
                Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
                Button("Apply correction") {
                    guard let point else { return }
                    data.setCorrection(frame: frame, landmark: landmark, x: point.0, y: point.1, undoManager: data.correctionUndoManager)
                    dismiss()
                }.keyboardShortcut(.defaultAction).disabled(point == nil)
            }
        }.padding(24).frame(width: 420)
        .onAppear {
            let original = data.effectivePoint(frame: frame, landmark: landmark)
            x = original?.x.map { String($0) } ?? ""
            y = original?.y.map { String($0) } ?? ""
        }
    }
}

private struct BagCoordinateEditor: View {
    @ObservedObject var data: TrialDataController
    let frame: Int
    @Environment(\.dismiss) private var dismiss
    @State private var x = ""
    @State private var y = ""

    private var point: (Double, Double)? {
        guard let px = Double(x), let py = Double(y), px.isFinite, py.isFinite,
              let pose = data.pose, (0...Double(pose.width)).contains(px), (0...Double(pose.height)).contains(py)
        else { return nil }
        return (px, py)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Correct Bag Centroid").font(.title2.weight(.semibold))
            Text("Frame \(frame) · analysis video pixels, measured from the top-left corner.").foregroundStyle(.secondary)
            TextField("X pixel", text: $x)
            TextField("Y pixel", text: $y)
            Text("This adds a separate reviewed point; it never overwrites the immutable automatic track. Add anchors on both sides of a short gap to interpolate it explicitly.")
                .font(.caption).foregroundStyle(.secondary)
            HStack {
                Spacer()
                Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
                Button("Apply Correction") {
                    guard let point else { return }
                    data.setBagCorrection(frame: frame, x: point.0, y: point.1)
                    dismiss()
                }.buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction).disabled(point == nil)
            }
        }.padding(24).frame(width: 440)
        .onAppear {
            let current = data.bagPoint(frame: frame) ?? data.automaticBagPoint(frame: frame)
            x = current.map { String($0.x) } ?? ""
            y = current.map { String($0.y) } ?? ""
        }
    }
}

private struct BagOverlay: View {
    @ObservedObject var data: TrialDataController
    let frame: Int
    let availableSize: CGSize

    var body: some View {
        if let pose = data.pose {
            let rect = videoRect(width: Double(pose.width), height: Double(pose.height))
            Canvas { context, _ in
                var trail = Path(); var previous: Int?
                for sample in data.bagTrack?.samples ?? [] where sample.frameIndex <= frame {
                    let corrected = data.bagCorrection(frame: sample.frameIndex)
                    let point = corrected.map { BagTrackDocument.Centroid(x:$0.x,y:$0.y,confidence:nil) }
                        ?? sample.effectiveCentroid
                    guard let point else { previous = nil; continue }
                    let p = CGPoint(x:rect.minX+rect.width*point.x/Double(pose.width), y:rect.minY+rect.height*point.y/Double(pose.height))
                    if previous == sample.frameIndex-1 { trail.addLine(to:p) } else { trail.move(to:p) }
                    previous = sample.frameIndex
                }
                context.stroke(trail, with:.color(.cyan.opacity(0.75)), lineWidth:2)
            }.allowsHitTesting(false)
            if let point = data.bagPoint(frame: frame) {
            let location = CGPoint(x: rect.minX + rect.width * point.x / Double(pose.width),
                                   y: rect.minY + rect.height * point.y / Double(pose.height))
            ZStack {
                Circle().stroke(.black.opacity(0.8), lineWidth: 5).frame(width: 22, height: 22)
                Circle().stroke(color, lineWidth: 3).frame(width: 22, height: 22)
                Path { path in
                    path.move(to: CGPoint(x: -14, y: 0)); path.addLine(to: CGPoint(x: 14, y: 0))
                    path.move(to: CGPoint(x: 0, y: -14)); path.addLine(to: CGPoint(x: 0, y: 14))
                }.stroke(color, lineWidth: 2).frame(width: 28, height: 28)
            }
            .position(location)
            .help("Bag centroid · \(data.bagProvenance(frame: frame).replacingOccurrences(of: "_", with: " "))")
            .accessibilityLabel("Bag centroid, \(data.bagProvenance(frame: frame))")
            }
        }
    }

    private var color: Color {
        switch data.bagProvenance(frame: frame) {
        case "manual": .yellow
        case "interpolated", "reviewed_interpolation": .purple
        default: .cyan
        }
    }

    private func videoRect(width: Double, height: Double) -> CGRect {
        let scale = min(availableSize.width / width, availableSize.height / height)
        let size = CGSize(width: width * scale, height: height * scale)
        return CGRect(x: (availableSize.width - size.width) / 2, y: (availableSize.height - size.height) / 2, width: size.width, height: size.height)
    }
}

private struct PoseOverlay: View {
    @ObservedObject var data: TrialDataController
    let frame: Int
    @Binding var selectedLandmark: String
    let confidenceThreshold: Double
    let availableSize: CGSize
    let correction: (String, Double, Double) -> Void
    private let landmarks = ["left_shoulder", "right_shoulder", "left_elbow", "right_elbow", "left_wrist", "right_wrist", "left_hip", "right_hip"]
    private let edges = [("left_shoulder", "right_shoulder"), ("left_hip", "right_hip"), ("left_shoulder", "left_hip"), ("right_shoulder", "right_hip"), ("left_shoulder", "left_elbow"), ("left_elbow", "left_wrist"), ("right_shoulder", "right_elbow"), ("right_elbow", "right_wrist")]

    var body: some View {
        if let pose = data.pose {
            let rect = videoRect(width: Double(pose.width), height: Double(pose.height))
            ZStack {
                Canvas { context, _ in
                    for edge in edges {
                        guard let a = screenPoint(edge.0, rect: rect, pose: pose), let b = screenPoint(edge.1, rect: rect, pose: pose) else { continue }
                        var path = Path(); path.move(to: a); path.addLine(to: b)
                        context.stroke(path, with: .color(.white.opacity(0.78)), lineWidth: 2)
                    }
                }
                ForEach(landmarks, id: \.self) { landmark in
                    if let point = screenPoint(landmark, rect: rect, pose: pose), let estimate = data.effectivePoint(frame: frame, landmark: landmark) {
                        Circle()
                            .fill(pointColor(estimate, landmark: landmark))
                            .overlay(Circle().stroke(data.correction(frame: frame, landmark: landmark) == nil ? .white : .yellow, lineWidth: data.correction(frame: frame, landmark: landmark) == nil ? 1.5 : 3))
                            .frame(width: selectedLandmark == landmark ? 17 : 13, height: selectedLandmark == landmark ? 17 : 13)
                            .frame(width: 29, height: 29)
                            .contentShape(Circle())
                            .gesture(DragGesture(minimumDistance: 0).onChanged { _ in selectedLandmark = landmark }.onEnded { value in
                                let x = min(max(0, (estimate.x ?? 0) + Double(value.translation.width / rect.width) * Double(pose.width)), Double(pose.width))
                                let y = min(max(0, (estimate.y ?? 0) + Double(value.translation.height / rect.height) * Double(pose.height)), Double(pose.height))
                                correction(landmark, x, y)
                            })
                            .position(point)
                            .help(data.correction(frame: frame, landmark: landmark) == nil ? "\(landmark.replacingOccurrences(of: "_", with: " ")) · raw confidence \(estimate.confidence.formatted(.number.precision(.fractionLength(2))))" : "\(landmark.replacingOccurrences(of: "_", with: " ")) · manually corrected; this is not a model confidence estimate")
                            .accessibilityLabel(landmark.replacingOccurrences(of: "_", with: " "))
                    }
                }
            }.coordinateSpace(name: "poseOverlay")
            .contentShape(Rectangle())
            .onTapGesture { location in
                guard rect.contains(location), screenPoint(selectedLandmark, rect: rect, pose: pose) == nil else { return }
                correction(selectedLandmark, Double((location.x - rect.minX) / rect.width) * Double(pose.width), Double((location.y - rect.minY) / rect.height) * Double(pose.height))
            }
        }
    }

    private func videoRect(width: Double, height: Double) -> CGRect {
        let scale = min(availableSize.width / width, availableSize.height / height)
        let size = CGSize(width: width * scale, height: height * scale)
        return CGRect(x: (availableSize.width - size.width) / 2, y: (availableSize.height - size.height) / 2, width: size.width, height: size.height)
    }
    private func screenPoint(_ landmark: String, rect: CGRect, pose: PoseDocument) -> CGPoint? {
        guard let point = data.effectivePoint(frame: frame, landmark: landmark), let x = point.x, let y = point.y else { return nil }
        return CGPoint(x: rect.minX + rect.width * x / Double(pose.width), y: rect.minY + rect.height * y / Double(pose.height))
    }
    private func pointColor(_ point: PosePoint, landmark: String) -> Color {
        if data.correction(frame: frame, landmark: landmark) != nil { return .blue }
        return point.confidence >= confidenceThreshold ? .green : .red
    }
}

struct MeasurementsView: View {
    @ObservedObject var data: TrialDataController
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text("Projected 2D Kinematic Summary").font(.title2.weight(.semibold))
                Text("Angles are image-plane measurements. Relative paths are shoulder-centered and divided by robust arm length; movement time is resampled to 101 points by default.").foregroundStyle(.secondary)
                if let summaries = data.results?.summaries {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 230))], spacing: 12) {
                        ForEach(summaries.keys.sorted(), id: \.self) { key in
                            VStack(alignment: .leading, spacing: 5) {
                                Text(measurementName(key)).font(.caption).foregroundStyle(.secondary)
                                Text(format(summaries[key] ?? nil, key: key)).font(.title3.weight(.semibold)).monospacedDigit()
                            }.padding(14).frame(maxWidth: .infinity, alignment: .leading)
                                .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 10))
                        }
                    }
                    if let analysisURL = dataImage("angle_trajectories.png") {
                        Image(nsImage: analysisURL).resizable().scaledToFit().accessibilityLabel("Projected angle trajectory plot")
                    }
                } else { ContentUnavailableView("No measurements", systemImage: "chart.xyaxis.line", description: Text("Analyze the trial first.")) }
            }.padding(24)
        }
    }
    private func measurementName(_ key: String) -> String { key.replacingOccurrences(of: "_", with: " ").replacingOccurrences(of: " deg", with: "").capitalized }
    private func format(_ value: Double?, key: String) -> String {
        guard let value else { return "Unavailable" }
        if key.contains("seconds") { return "\(value.formatted(.number.precision(.fractionLength(3)))) s" }
        if key.contains("cycle") { return value.formatted(.percent.precision(.fractionLength(1))) }
        if key.contains("arm_lengths_s2") { return "\(value.formatted(.number.precision(.fractionLength(3)))) arm lengths/s²" }
        if key.contains("arm_lengths_s") { return "\(value.formatted(.number.precision(.fractionLength(3)))) arm lengths/s" }
        if key.contains("px_s2") { return "\(value.formatted(.number.precision(.fractionLength(1)))) px/s²" }
        if key.contains("px_s") { return "\(value.formatted(.number.precision(.fractionLength(1)))) px/s" }
        if key.contains("m_s2") { return "\(value.formatted(.number.precision(.fractionLength(2)))) m/s²" }
        if key.contains("m_s") { return "\(value.formatted(.number.precision(.fractionLength(2)))) m/s" }
        if key.contains("velocity") { return "\(value.formatted(.number.precision(.fractionLength(1)))) °/s" }
        if key.contains("deg") { return "\(value.formatted(.number.precision(.fractionLength(1))))°" }
        return value.formatted(.number.precision(.fractionLength(3)))
    }
    private func dataImage(_ name: String) -> NSImage? {
        guard let path = data.analysisURL else { return nil }
        return NSImage(contentsOf: path.appendingPathComponent(name))
    }
}

struct QualityEventsView: View {
    @ObservedObject var data: TrialDataController
    private var currentEventFrame: Int { data.inspectionFrame }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text("Measurement Quality").font(.title2.weight(.semibold))
                if let quality = data.results?.quality {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 180))], spacing: 12) {
                        metric("Average confidence", quality.averagePoseConfidence?.formatted(.number.precision(.fractionLength(2))) ?? "Unavailable")
                        metric("Usable frames", "\(quality.usableFramePercentage.formatted(.number.precision(.fractionLength(1))))%")
                        metric("Missing samples", "\(quality.missingDataPercentage.formatted(.number.precision(.fractionLength(1))))%")
                        metric("Manual corrections", "\(quality.manualCorrectionCount)")
                        metric("Interpolated samples", "\(quality.interpolatedSampleCount)")
                        metric("Frame rate", "\(quality.frameRateFPS.formatted()) fps")
                        metric("Resolution", "\(quality.resolutionPixels.width) × \(quality.resolutionPixels.height)")
                        metric("View label", quality.cameraView.capitalized)
                    }
                    ForEach(quality.warnings + (data.results?.warnings ?? []), id: \.self) { warning in
                        Label(warning, systemImage: "exclamationmark.triangle.fill").foregroundStyle(.orange)
                    }
                    Text(quality.confidenceNote).font(.caption).foregroundStyle(.secondary)
                }
                if let bag = data.results?.bag {
                    Divider()
                    Text("Bag Tracking Review").font(.title2.weight(.semibold))
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 180))], spacing: 12) {
                        metric("Automatic coverage", "\(bag.automaticTrackingCoveragePercent.formatted(.number.precision(.fractionLength(1))))%")
                        metric("Effective coverage", "\(bag.effectiveTrackingCoveragePercent.formatted(.number.precision(.fractionLength(1))))%")
                        metric("Median appearance quality", bag.medianAutomaticQuality?.formatted(.number.precision(.fractionLength(2))) ?? "Unavailable")
                        metric("Reviewed points", "\(bag.manualCorrectionCount)")
                        metric("Interpolated bag points", "\(bag.interpolatedSampleCount)")
                        metric("Reviewed through", bag.review?.reviewedThroughFrame.map { "Frame \($0)" } ?? "Not reviewed")
                        metric("Tracker", "\(bag.tracker.effectiveMethod.replacingOccurrences(of: "_", with: " ")) · \(bag.tracker.status.replacingOccurrences(of: "_", with: " "))")
                    }
                    if bag.review?.coversLaunchFit != true {
                        Label("Launch values are suppressed until bag identity is reviewed through frame \(bag.review?.requiredThroughFrameForLaunch.map(String.init) ?? "unavailable").", systemImage: "hand.raised.fill")
                            .foregroundStyle(.orange)
                    }
                    if !bag.tracker.failureFrames.isEmpty {
                        Label("\(bag.tracker.failureFrames.count) tracker failures remain for review.", systemImage: "exclamationmark.triangle.fill")
                            .foregroundStyle(.orange)
                    }
                    Text(bag.qualityNote).font(.caption).foregroundStyle(.secondary)
                } else {
                    Divider()
                    Text("Bag tracking has not started. In Inspect & Correct, pause near release and use Select & track bag. Review the resulting path to unlock release measurements.")
                        .font(.callout).foregroundStyle(.secondary)
                }
                Divider()
                Text("Movement Events").font(.title2.weight(.semibold))
                Text("The frame carries over from Inspect & Correct. Use Mark event while watching the video, or adjust its frame here. Automatic and manual values remain separate. Visible release is frame-limited—at 60 fps, one frame is about 16.7 ms.").foregroundStyle(.secondary)
                Stepper("Correction frame: \(currentEventFrame)", value: $data.inspectionFrame, in: 0...max(0, (data.pose?.frameCount ?? 1) - 1))
                ForEach(eventNames.map(\.0), id: \.self) { name in
                    if let event = data.events?.events[name] {
                        HStack {
                            VStack(alignment: .leading) {
                                Text(name.replacingOccurrences(of: "_", with: " ").capitalized).font(.headline)
                                Text("Automatic: \(event.automaticFrame.map(String.init) ?? "unavailable") · Effective: \(event.effectiveFrame.map(String.init) ?? "unavailable")")
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                            if event.manualFrame != nil { StatusPill(text: "Manual", color: .blue) }
                            else if event.confirmedBy == "automatic_physics" { StatusPill(text: "Automatic ✓", color: .green) }
                            Button("Set to \(currentEventFrame)") { data.setManualEvent(name: name, frame: currentEventFrame) }
                            Button("Use Automatic") { data.setManualEvent(name: name, frame: nil) }.disabled(event.manualFrame == nil)
                        }.padding(12).background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 9))
                    }
                }
                Text("Reanalyze after event changes to update normalization, timing, and derived summaries.").font(.caption).foregroundStyle(.secondary)
            }.padding(24)
        }
    }
    private func metric(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading) { Text(value).font(.title3.weight(.semibold)); Text(title).font(.caption).foregroundStyle(.secondary) }
            .padding(12).frame(maxWidth: .infinity, alignment: .leading).background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 9))
    }
}

struct TrialMetadataView: View {
    @EnvironmentObject private var store: ProjectStore
    let trial: Trial
    var body: some View {
        Form {
            LabeledContent("Original filename", value: trial.originalFilename)
            LabeledContent("Trial ID", value: trial.id.uuidString)
            LabeledContent("Camera view", value: trial.cameraView.label)
            LabeledContent("Throwing side", value: trial.throwingSide.label)
            LabeledContent("Target direction", value: trial.targetDirection.label)
            LabeledContent("Project video copy", value: trial.sourceVideoRelativePath)
            if let sourceURL = trial.sourceURL, let url = URL(string: sourceURL) {
                LabeledContent("Source URL") { Link(sourceURL, destination: url) }
            }
            if let attribution = trial.sourceAttribution { LabeledContent("Attribution", value: attribution) }
            LabeledContent("Analysis status", value: trial.analysisStatus)
            LabeledContent("Reference", value: trial.isReference ? "Yes" : "No")
            LabeledContent("Outcome", value: trial.outcome?.scoreCategory?.label ?? "Not recorded")
            Button("Reveal Source Video in Finder") { store.revealVideo(for: trial) }
            Button("Reveal Athlete Folder in Finder") {
                if let athlete = store.project?.athletes.first(where: { $0.id == trial.athleteID }) {
                    store.revealAthlete(athlete)
                }
            }
        }.formStyle(.grouped).padding(20)
    }
}

private struct TrialEditForm: View {
    @EnvironmentObject private var store: ProjectStore
    @Environment(\.dismiss) private var dismiss
    let trial: Trial
    @State private var name: String
    @State private var view: CameraView
    @State private var side: ThrowingSide
    @State private var direction: TargetDirection

    init(trial: Trial) {
        self.trial = trial
        _name = State(initialValue: trial.name ?? "")
        _view = State(initialValue: trial.cameraView)
        _side = State(initialValue: trial.throwingSide)
        _direction = State(initialValue: trial.targetDirection)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("Edit Throw").font(.title2.weight(.semibold))
            Form {
                TextField("Display name (optional)", text: $name)
                Picker("Camera view", selection: $view) { ForEach(CameraView.allCases) { Text($0.label).tag($0) } }
                Picker("Throwing side", selection: $side) { ForEach(ThrowingSide.allCases) { Text($0.label).tag($0) } }
                Picker("Target direction", selection: $direction) { ForEach(TargetDirection.allCases) { Text($0.label).tag($0) } }
            }.formStyle(.grouped)
            Text("Changing view, side, or direction changes measurement interpretation; re-run analysis afterward.")
                .font(.caption).foregroundStyle(.secondary)
            HStack {
                Spacer()
                Button("Cancel", role: .cancel) { dismiss() }
                Button("Save") {
                    var changed = trial
                    changed.name = name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? nil : name
                    changed.cameraView = view
                    changed.throwingSide = side
                    changed.targetDirection = direction
                    if changed.cameraView != trial.cameraView || changed.throwingSide != trial.throwingSide || changed.targetDirection != trial.targetDirection {
                        changed.analysisStatus = changed.analysisRelativePath == nil ? "Not analyzed" : "Needs reanalysis"
                    }
                    do { try store.updateTrialMetadata(changed); dismiss() }
                    catch { store.errorMessage = error.localizedDescription }
                }.buttonStyle(.borderedProminent)
            }
        }.padding(24).frame(width: 540)
    }
}
