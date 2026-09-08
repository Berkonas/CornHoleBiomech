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
                    Text("Recorded Throws").font(.headline)
                    Spacer()
                    Button(action: beginImport) { Image(systemName: "plus") }.help("Import local video")
                }
                List(store.project?.trials ?? [], selection: $store.selectedTrialID) { trial in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(trial.originalFilename).lineLimit(1)
                        HStack {
                            Text(athleteName(trial.athleteID))
                            Text("·")
                            Text(trial.cameraView.label)
                            Spacer()
                            if trial.isReference { Image(systemName: "bookmark.fill").foregroundStyle(.tint) }
                        }.font(.caption).foregroundStyle(.secondary)
                        StatusPill(text: trial.analysisStatus, color: trial.analysisRelativePath == nil ? .secondary : .green)
                    }.padding(.vertical, 3).tag(trial.id)
                }
            }.padding().frame(minWidth: 210, idealWidth: 240, maxWidth: 280)

            if let trial = store.selectedTrial {
                TrialDetailView(trial: trial)
            } else {
                ContentUnavailableView("Select or import a trial", systemImage: "video", description: Text("The primary flow is import, inspect, correct, attach outcome, then compare."))
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

    var body: some View {
        VStack(spacing: 0) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(trial.originalFilename).font(.title2.weight(.semibold)).lineLimit(1)
                    Text("\(athleteName) · \(trial.cameraView.label) view · \(trial.throwingSide.label)-hand throw")
                        .foregroundStyle(.secondary)
                }
                Spacer()
                if trial.isReference { StatusPill(text: "Reference", color: .blue) }
                if trial.outcome != nil { StatusPill(text: "Outcome recorded", color: .green) }
            }.padding([.horizontal, .top], 20)
            Picker("Trial section", selection: $selectedTab) {
                Text("Inspect & Correct").tag("Inspect")
                Text("Measurements").tag("Measurements")
                Text("Quality & Events").tag("Quality")
                Text("Metadata").tag("Metadata")
            }.pickerStyle(.segmented).labelsHidden().padding()
            HStack {
                Button("Understand this throw") { store.selectedSection = .results }.buttonStyle(.borderedProminent).disabled(trial.analysisRelativePath == nil)
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
                    if let videoURL = store.videoURL(for: trial), data.pose != nil {
                        VideoPoseEditor(videoURL: videoURL, data: data, confidenceThreshold: store.project?.analysisSettings.confidenceThreshold ?? 0.35).id(trial.id)
                    } else if analysis.activeTrialID == trial.id {
                        ContentUnavailableView("Analyzing video", systemImage: "waveform.path.ecg", description: Text(analysis.detail))
                    } else {
                        ContentUnavailableView {
                            Label("Analysis required", systemImage: "figure.walk.motion")
                        } description: {
                            Text("Run the local markerless pose engine before inspecting landmarks or derived kinematics.")
                        } actions: {
                            Button("Analyze Trial") { Task { await analysis.analyze(trial: trial, store: store) } }.buttonStyle(.borderedProminent)
                        }
                    }
                }
            }.frame(maxWidth: .infinity, maxHeight: .infinity).disabled(analysis.isRunning)
        }
        .task(id: trial.id) { data.load(analysisURL: store.analysisURL(for: trial)) }
        .onChange(of: analysis.isRunning) { oldValue, newValue in
            if oldValue && !newValue { data.load(analysisURL: store.analysisURL(for: store.selectedTrial ?? trial)) }
        }
    }

    private var athleteName: String {
        store.project?.athletes.first { $0.id == trial.athleteID }?.displayName ?? "Unknown athlete"
    }
}

struct VideoPoseEditor: View {
    private var undoManager: UndoManager? { data.correctionUndoManager }
    let videoURL: URL
    @ObservedObject var data: TrialDataController
    let confidenceThreshold: Double
    @State private var player: AVPlayer
    private var currentFrame: Int {
        get { data.inspectionFrame }
        nonmutating set { data.inspectionFrame = newValue }
    }
    @State private var selectedLandmark = "right_wrist"
    @State private var timeObserver: Any?
    @State private var interpolationNotice: String?
    @State private var showCoordinates = false

    init(videoURL: URL, data: TrialDataController, confidenceThreshold: Double) {
        self.videoURL = videoURL
        self.data = data
        self.confidenceThreshold = confidenceThreshold
        _player = State(initialValue: AVPlayer(url: videoURL))
    }

    var body: some View {
        VStack(spacing: 0) {
            GeometryReader { geometry in
                ZStack {
                    Color.black
                    NativeVideoPlayer(player: player, showsControls: false)
                    if data.pose != nil {
                        PoseOverlay(
                            data: data, frame: currentFrame, selectedLandmark: $selectedLandmark,
                            confidenceThreshold: confidenceThreshold, availableSize: geometry.size
                        ) { landmark, x, y in
                            player.pause()
                            data.setCorrection(frame: currentFrame, landmark: landmark, x: x, y: y, undoManager: undoManager)
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
                    Spacer(minLength: 0)
                }
                if let interpolationNotice { Text(interpolationNotice).font(.caption).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading) }
                Text("Pause, then drag a joint. To restore a missing joint, select its name and click its location on the video. Raw model predictions remain unchanged; corrections are stored separately. Reanalyze after edits.")
                    .font(.caption).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading)
            }.padding(14)
        }
        .focusedSceneObject(data)
        .sheet(isPresented: $showCoordinates) {
            LandmarkCoordinateEditor(data: data, frame: currentFrame, landmark: selectedLandmark)
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
    private func step(_ amount: Int) { frameBinding.wrappedValue = Double(min(max(0, currentFrame + amount), max(0, (data.pose?.frameCount ?? 1) - 1))) }
    private func installTimeObserver() {
        guard timeObserver == nil else { return }
        let fps = data.pose?.fps ?? 30
        let maximumFrame = max(0, (data.pose?.frameCount ?? 1) - 1)
        timeObserver = player.addPeriodicTimeObserver(forInterval: CMTime(value: 1, timescale: 30), queue: .main) { time in
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
            LabeledContent("Outcome", value: trial.outcome?.scoreCategory.label ?? "Not recorded")
            Button("Show Project in Finder") { store.revealProject() }
        }.formStyle(.grouped).padding(20)
    }
}
