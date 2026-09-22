import SwiftUI
import Foundation

struct FlightSummary: Codable {
    struct Point: Codable { var frame: Int; var x: Double?; var y: Double? }
    var status: String
    var message: String
    var time_of_flight_seconds: Double?
    var observed_rise_pixels: Double?
    var horizontal_travel_pixels: Double?
    var coverage: Double
    var trajectory: [Point]
    var frame_interval_seconds: Double
}

struct PerformanceSummary: Decodable {
    struct Dispersion: Decodable {
        var n: Int; var missing: Int; var rms_radius_inches: Double?
        var lateral_sd_inches: Double?; var longitudinal_sd_inches: Double?; var note: String
    }
    struct Evidence: Decodable, Identifiable {
        struct Range: Decodable { var n: Int; var median: Double?; var low: Double?; var high: Double? }
        struct Feedback: Decodable {
            var zone: String; var explanation: String; var minimum_per_group: Int
            var ranges: [String: Range]; var meaning: String
        }
        var metric: String; var groups: [String: Range]; var minimum: Int; var note: String
        var feedback: Feedback?
        var id: String { metric }
    }
    var first_contact: Dispersion; var final_rest: Dispersion
    var observed_scores: [String: Int]; var unknown_scores: Int
    var personal_evidence: [Evidence]
}

/// One explicit review document accompanies the existing immutable tracks/events.
struct FlightReviewEditor: View {
    @Environment(\.dismiss) private var dismiss
    @ObservedObject var data: TrialDataController
    let frame: Int
    @State private var contact = ""
    @State private var fixedCamera = false
    @State private var useScale = false
    @State private var knownLength = ""
    @State private var pixelLength = ""
    @State private var source = ""
    @State private var note = ""
    @State private var error: String?
    private var isSide: Bool { data.results?.quality.cameraView == "side" }
    private var valid: Bool {
        let eventOK = contact.isEmpty || Int(contact).map { $0 >= 0 && $0 < (data.pose?.frameCount ?? 0) } == true
        let scaleOK = !useScale || (isSide && fixedCamera && !source.trimmingCharacters(in: .whitespaces).isEmpty &&
            Double(knownLength).map { $0.isFinite && $0 > 0 } == true && Double(pixelLength).map { $0.isFinite && $0 > 1 } == true)
        return eventOK && scaleOK
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Release → flight → first contact").font(.title2.bold())
            Text("Review one throw from visible hand separation to the first board or ground contact. A bag disappearing is not evidence of landing.").foregroundStyle(.secondary)
            HStack {
                Button("Confirm release at frame \(frame)") { data.setManualEvent(name: "release", frame: frame) }
                Text("Release: \(data.events?.events["release"]?.manualFrame.map(String.init) ?? "needs confirmation")").font(.caption)
            }
            HStack {
                TextField("First-contact frame (blank if unseen)", text: $contact)
                Button("Use frame \(frame)") { contact = String(frame) }
                Button("Clear") { contact = "" }
            }
            Text("Contact may occur after body follow-through ends. Reopen this panel at the contact frame; review the bag identity through that frame using Bag tracking.").font(.caption).foregroundStyle(.secondary)
            Toggle("I verified a fixed, level side camera, approximately perpendicular to the flight plane", isOn: $fixedCamera)
            Text("Leave unchecked if the camera pans, tilts or zooms. A side-view label alone does not validate geometry.").font(.caption).foregroundStyle(.secondary)
            DisclosureGroup("Optional release-plane scale") {
                VStack(alignment: .leading, spacing: 10) {
                    Toggle("Use an independently measured in-plane length", isOn: $useScale)
                    TextField("Known length (meters)", text: $knownLength)
                    TextField("Length between endpoints in this video (pixels)", text: $pixelLength)
                    TextField("Object, endpoint coordinates and measurement method", text: $source)
                    Text("Scale = pixel length / known meters. Measure a rigid object in the release plane at this frame; record its two endpoints above. The distant board and apparent arm length are not valid substitutes. This scale applies to release speed only, not the entire flight or board.").font(.caption).foregroundStyle(.secondary)
                }.padding(.vertical, 8)
            }
            TextField("Observation notes / uncertainty", text: $note, axis: .vertical)
            if let error { Text(error).foregroundStyle(.orange) }
            HStack {
                Text("Reanalyze after saving to update all derived results.").font(.caption).foregroundStyle(.secondary)
                Spacer(); Button("Cancel") { dismiss() }
                Button("Save review") { save() }.buttonStyle(.borderedProminent).disabled(!valid)
            }
        }.padding(24).frame(width: 680).onAppear { load() }
    }
    private func load() {
        guard let directory = data.analysisURL else { return }
        func read(_ name: String) -> [String: Any] {
            guard let bytes = try? Data(contentsOf: directory.appendingPathComponent(name)), let value = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any] else { return [:] }; return value
        }
        let review = read("flight_review.json")
        contact = (review["first_contact_frame"] as? Int).map(String.init) ?? ""
        fixedCamera = review["fixed_camera"] as? Bool ?? false
        note = review["note"] as? String ?? ""
        let scale = read("calibration.json")
        useScale = scale["valid"] as? Bool ?? false
        source = scale["source"] as? String ?? ""
        knownLength = (scale["known_length_m"] as? Double).map { String($0) } ?? ""
        pixelLength = (scale["observed_length_px"] as? Double).map { String($0) } ?? ""
    }
    private func save() {
        guard let directory = data.analysisURL else { return }
        if let c = Int(contact), let r = data.events?.events["release"]?.effectiveFrame, c <= r {
            error = "First contact must follow release."; return
        }
        do {
            let review: [String: Any] = ["schema_version": 1, "first_contact_frame": Int(contact).map { $0 as Any } ?? NSNull(),
                "fixed_camera": fixedCamera, "note": note, "reviewed_at": ISO8601DateFormatter().string(from: Date())]
            try JSONSerialization.data(withJSONObject: review, options: [.prettyPrinted, .sortedKeys]).write(to: directory.appendingPathComponent("flight_review.json"), options: .atomic)
            let scaleURL = directory.appendingPathComponent("calibration.json")
            if useScale, let meters = Double(knownLength), let pixels = Double(pixelLength) {
                let scale: [String: Any] = ["schema_version": 1, "pixels_per_meter": pixels/meters, "plane": "athlete_release_motion_plane", "valid": true,
                    "source": source, "known_length_m": meters, "observed_length_px": pixels, "frame_index": frame]
                try JSONSerialization.data(withJSONObject: scale, options: [.prettyPrinted, .sortedKeys]).write(to: scaleURL, options: .atomic)
            } else if FileManager.default.fileExists(atPath: scaleURL.path) { try FileManager.default.removeItem(at: scaleURL) }
            try Data("{\"reason\":\"flight_review_changed\"}".utf8).write(to: directory.appendingPathComponent("needs_reanalysis.json"), options: .atomic)
            dismiss()
        } catch { self.error = error.localizedDescription }
    }
}

struct FlightPathPanel: View {
    let flight: FlightSummary?
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Bag flight").font(.title2.weight(.semibold))
            if let flight {
                HStack {
                    Text("Release → first contact: \(number(flight.time_of_flight_seconds, digits: 2)) s").font(.headline)
                    Spacer()
                    Text("One frame = \(number(flight.frame_interval_seconds * 1000)) ms").font(.caption).foregroundStyle(.secondary)
                }
                Text(flight.message).font(.callout).foregroundStyle(.secondary)
                if !flight.trajectory.isEmpty {
                    Canvas { context, size in
                        let samples = flight.trajectory.filter { $0.x != nil && $0.y != nil }
                        let xs = samples.compactMap(\.x), ys = samples.compactMap(\.y)
                        let minX = xs.min() ?? 0, maxX = xs.max() ?? 1
                        let minY = ys.min() ?? 0, maxY = ys.max() ?? 1
                        let scale = min((size.width-40)/max(maxX-minX,1), (size.height-40)/max(maxY-minY,1))
                        var path = Path(); var penDown = false
                        for p in flight.trajectory {
                            guard let x = p.x, let y = p.y else { penDown = false; continue }
                            let point = CGPoint(x: 20+(x-minX)*scale, y: 20+(y-minY)*scale)
                            if penDown { path.addLine(to: point) } else { path.move(to: point); penDown = true }
                            context.fill(Path(ellipseIn: CGRect(x: point.x-2,y: point.y-2,width:4,height:4)), with: .color(.accentColor))
                        }
                        context.stroke(path, with: .color(.accentColor), lineWidth: 1.5)
                    }.frame(height: 230).background(.quaternary.opacity(0.2), in: RoundedRectangle(cornerRadius: 10))
                    Text("Reviewed centroids · equal image scale on both axes · gaps remain gaps · not a reconstructed world trajectory").font(.caption).foregroundStyle(.secondary)
                }
            } else { Text("In Throws, review the bag, confirm release, then use Flight & scale to mark first contact. Reanalyze to connect the events.").foregroundStyle(.secondary) }
        }
    }
}
