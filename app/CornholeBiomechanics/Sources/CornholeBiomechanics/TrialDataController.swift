import Foundation

@MainActor
final class TrialDataController: ObservableObject {
    @Published private(set) var pose: PoseDocument?
    @Published private(set) var results: AnalysisResults?
    @Published private(set) var normalized: NormalizedDocument?
    @Published private(set) var comparison: ComparisonDocument?
    @Published private(set) var relationships: RelationshipDocument?
    @Published private(set) var corrections = CorrectionDocument()
    @Published private(set) var events: EventDocument?
    @Published private(set) var kinematicRows: [[String: String]] = []
    let correctionUndoManager = UndoManager()
    @Published var inspectionFrame = 0
    @Published var loadError: String?

    private(set) var analysisURL: URL?

    func load(analysisURL: URL?) {
        loadError = nil
        if self.analysisURL != analysisURL { inspectionFrame = 0; correctionUndoManager.removeAllActions() }
        self.analysisURL = analysisURL
        pose = decode(PoseDocument.self, at: analysisURL?.appendingPathComponent("pose_raw.json"))
        results = decode(AnalysisResults.self, at: analysisURL?.appendingPathComponent("results.json"))
        normalized = decode(NormalizedDocument.self, at: analysisURL?.appendingPathComponent("normalized.json"))
        corrections = decode(CorrectionDocument.self, at: analysisURL?.appendingPathComponent("corrections.json")) ?? CorrectionDocument()
        events = decode(EventDocument.self, at: analysisURL?.appendingPathComponent("events.json"))
        kinematicRows = loadCSV(at: analysisURL?.appendingPathComponent("kinematics.csv"))
    }

    func loadComparison(at url: URL?) {
        comparison = decode(ComparisonDocument.self, at: url?.appendingPathComponent("comparison.json"))
    }

    func loadRelationships(at url: URL?) {
        relationships = decode(RelationshipDocument.self, at: url)
    }

    func effectivePoint(frame: Int, landmark: String) -> PosePoint? {
        if let corrected = corrections.corrections.last(where: { $0.frameIndex == frame && $0.landmark == landmark }) {
            return PosePoint(x: corrected.x, y: corrected.y, confidence: 1)
        }
        return pose?.frames[safe: frame]?.landmarks[landmark]
    }

    func correction(frame: Int, landmark: String) -> PointCorrection? {
        corrections.corrections.last { $0.frameIndex == frame && $0.landmark == landmark }
    }

    func setCorrection(frame: Int, landmark: String, x: Double, y: Double, kind: String = "manual") {
        corrections.corrections.removeAll { $0.frameIndex == frame && $0.landmark == landmark }
        corrections.corrections.append(PointCorrection(frameIndex: frame, landmark: landmark, x: x, y: y, kind: kind))
        saveCorrections()
    }

    func setCorrection(frame: Int, landmark: String, x: Double, y: Double, undoManager: UndoManager?) {
        let previous = correction(frame: frame, landmark: landmark)
        replaceCorrection(PointCorrection(frameIndex: frame, landmark: landmark, x: x, y: y), frame: frame, landmark: landmark)
        undoManager?.registerUndo(withTarget: self) { target in
            target.restoreCorrection(previous, frame: frame, landmark: landmark, undoManager: undoManager)
        }
        undoManager?.setActionName("Move \(landmark.replacingOccurrences(of: "_", with: " ").capitalized)")
    }

    func resetCorrection(frame: Int, landmark: String, undoManager: UndoManager?) {
        let previous = correction(frame: frame, landmark: landmark)
        guard previous != nil else { return }
        replaceCorrection(nil, frame: frame, landmark: landmark)
        undoManager?.registerUndo(withTarget: self) { target in
            target.restoreCorrection(previous, frame: frame, landmark: landmark, undoManager: undoManager)
        }
        undoManager?.setActionName("Reset Landmark")
    }

    private func restoreCorrection(_ correction: PointCorrection?, frame: Int, landmark: String, undoManager: UndoManager?) {
        let current = self.correction(frame: frame, landmark: landmark)
        replaceCorrection(correction, frame: frame, landmark: landmark)
        undoManager?.registerUndo(withTarget: self) { target in
            target.restoreCorrection(current, frame: frame, landmark: landmark, undoManager: undoManager)
        }
    }

    func replaceCorrection(_ correction: PointCorrection?, frame: Int, landmark: String) {
        corrections.corrections.removeAll { $0.frameIndex == frame && $0.landmark == landmark }
        if let correction { corrections.corrections.append(correction) }
        saveCorrections()
    }

    func interpolate(landmark: String, through frame: Int, undoManager: UndoManager?) -> Int {
        let previous = corrections.corrections
        let anchors = corrections.corrections
            .filter { $0.landmark == landmark && $0.kind == "manual" }
            .sorted { $0.frameIndex < $1.frameIndex }
        guard let left = anchors.last(where: { $0.frameIndex < frame }),
              let right = anchors.first(where: { $0.frameIndex > frame }),
              right.frameIndex > left.frameIndex + 1 else { return 0 }
        corrections.corrections.removeAll {
            $0.landmark == landmark && $0.kind == "interpolated" &&
            $0.frameIndex > left.frameIndex && $0.frameIndex < right.frameIndex
        }
        for index in (left.frameIndex + 1)..<right.frameIndex {
            let fraction = Double(index - left.frameIndex) / Double(right.frameIndex - left.frameIndex)
            corrections.corrections.append(PointCorrection(
                frameIndex: index,
                landmark: landmark,
                x: left.x + fraction * (right.x - left.x),
                y: left.y + fraction * (right.y - left.y),
                kind: "interpolated"
            ))
        }
        saveCorrections()
        undoManager?.registerUndo(withTarget: self) { target in
            target.restoreCorrectionSet(previous, undoManager: undoManager)
        }
        undoManager?.setActionName("Interpolate Landmark")
        return right.frameIndex - left.frameIndex - 1
    }

    func clearInterpolated(landmark: String, undoManager: UndoManager?) -> Int {
        let previous = corrections.corrections
        let count = previous.filter { $0.landmark == landmark && $0.kind == "interpolated" }.count
        guard count > 0 else { return 0 }
        corrections.corrections.removeAll { $0.landmark == landmark && $0.kind == "interpolated" }
        saveCorrections()
        undoManager?.registerUndo(withTarget: self) { target in
            target.restoreCorrectionSet(previous, undoManager: undoManager)
        }
        undoManager?.setActionName("Remove Interpolation")
        return count
    }

    private func restoreCorrectionSet(_ values: [PointCorrection], undoManager: UndoManager?) {
        let current = corrections.corrections
        corrections.corrections = values
        saveCorrections()
        undoManager?.registerUndo(withTarget: self) { target in
            target.restoreCorrectionSet(current, undoManager: undoManager)
        }
    }

    func setManualEvent(name: String, frame: Int?) {
        guard var document = events else { return }
        document.manualOverrides[name] = frame
        if var entry = document.events[name] {
            entry.manualFrame = frame
            entry.effectiveFrame = frame ?? entry.automaticFrame
            document.events[name] = entry
        }
        markDirty()
        events = document
        if let url = analysisURL?.appendingPathComponent("events.json") {
            do { try JSONEncoder.projectEncoder.encode(document).write(to: url, options: .atomic) }
            catch { loadError = "Event edits could not be saved: \(error.localizedDescription)" }
        }
    }

    func value(field: String, frame: Int) -> Double? {
        guard let string = kinematicRows[safe: frame]?[field] else { return nil }
        return Double(string)
    }

    private func markDirty() {
        guard let url = analysisURL?.appendingPathComponent("needs_reanalysis.json") else { return }
        try? Data("{\"reason\":\"corrections_changed\"}".utf8).write(to: url, options: .atomic)
    }

    private func saveCorrections() {
        markDirty()
        guard let url = analysisURL?.appendingPathComponent("corrections.json") else { return }
        do { try JSONEncoder.projectEncoder.encode(corrections).write(to: url, options: .atomic) }
        catch { loadError = "Could not save correction: \(error.localizedDescription)" }
    }

    private func decode<T: Decodable>(_ type: T.Type, at url: URL?) -> T? {
        guard let url, FileManager.default.fileExists(atPath: url.path) else { return nil }
        do { return try JSONDecoder.projectDecoder.decode(type, from: Data(contentsOf: url)) }
        catch { loadError = "Could not read \(url.lastPathComponent): \(error.localizedDescription)"; return nil }
    }

    private func loadCSV(at url: URL?) -> [[String: String]] {
        guard let url, let content = try? String(contentsOf: url, encoding: .utf8) else { return [] }
        let lines = content.split(whereSeparator: \.isNewline).map(String.init)
        guard let first = lines.first else { return [] }
        let headers = first.split(separator: ",", omittingEmptySubsequences: false).map(String.init)
        return lines.dropFirst().map { line in
            let values = line.split(separator: ",", omittingEmptySubsequences: false).map(String.init)
            return Dictionary(uniqueKeysWithValues: zip(headers, values))
        }
    }
}

extension Collection {
    subscript(safe index: Index) -> Element? { indices.contains(index) ? self[index] : nil }
}
