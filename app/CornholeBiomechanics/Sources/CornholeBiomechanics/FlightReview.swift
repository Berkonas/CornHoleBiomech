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
    var first_contact: Dispersion; var final_rest: Dispersion
    var observed_scores: [String: Int]; var unknown_scores: Int
    var summary: AthletePerformance?
    var sports: SportsStats?
    var zones: ZoneReport?
}

/// One explicit review document accompanies the existing immutable tracks/events.
/// Shown as the "Bag flight" tab of the Fix Tracking sheet; `frame` is the frame chosen in the other tabs.
struct FlightReviewEditor: View {
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
    @State private var saved = false
    private var isSide: Bool { data.results?.quality.cameraView == "side" }
    private var valid: Bool {
        let eventOK = contact.isEmpty || Int(contact).map { $0 >= 0 && $0 < (data.pose?.frameCount ?? 0) } == true
        let scaleOK = !useScale || (isSide && fixedCamera && !source.trimmingCharacters(in: .whitespaces).isEmpty &&
            Double(knownLength).map { $0.isFinite && $0 > 0 } == true && Double(pixelLength).map { $0.isFinite && $0 > 1 } == true)
        return eventOK && scaleOK
    }
    private var releaseStatus: String {
        guard let release = data.events?.events["release"] else { return "Release: needs confirmation" }
        if let manual = release.manualFrame { return "Release: frame \(manual) (manual)" }
        if release.confirmedBy == "automatic_physics", let frame = release.effectiveFrame { return "Release: frame \(frame) (automatic, physics-checked)" }
        return "Release: needs confirmation"
    }
    var body: some View {
        ScrollView {
        VStack(alignment: .leading, spacing: 16) {
            Text("Release → flight → first contact").font(.title2.bold())
            Text("Review one throw from visible hand separation to the first board or ground contact. A bag disappearing is not evidence of landing.").foregroundStyle(.secondary)
            HStack {
                Button("Confirm release at frame \(frame)") { data.setManualEvent(name: "release", frame: frame) }
                Text(releaseStatus).font(.caption)
            }
            HStack {
                TextField("First-contact frame (blank if unseen)", text: $contact)
                Button("Use frame \(frame)") { contact = String(frame) }
                Button("Clear") { contact = "" }
            }
            Text("Contact may occur after body follow-through ends. Pick the contact frame in the Bag tab, then return here; review the bag identity through that frame there too.").font(.caption).foregroundStyle(.secondary)
            Toggle("I verified a fixed, level side camera, approximately perpendicular to the flight plane", isOn: $fixedCamera)
            Text("Leave unchecked if the camera pans, tilts or zooms. A side-view label alone does not validate geometry. When the automatic flight was accepted, its camera motion is already removed and its board scale is kept even if this is unchecked.").font(.caption).foregroundStyle(.secondary)
            DisclosureGroup("Optional release-plane scale") {
                VStack(alignment: .leading, spacing: 10) {
                    Toggle("Use an independently measured in-plane length", isOn: $useScale)
                    TextField("Known length (meters)", text: $knownLength)
                    TextField("Length between endpoints in this video (pixels)", text: $pixelLength)
                    TextField("Object, endpoint coordinates and measurement method", text: $source)
                    Text("Scale = pixel length / known meters. Measure a rigid object in the release plane at this frame; record its two endpoints above. Without it, a located board gives the scale (its throw plane, with the field of view calibrated from the bag's gravity); a length entered here replaces that for release speed and height. Apparent arm length is not a valid substitute.").font(.caption).foregroundStyle(.secondary)
                }.padding(.vertical, 8)
            }
            TextField("Observation notes / uncertainty", text: $note, axis: .vertical)
            if let error { Text(error).foregroundStyle(.orange) }
            HStack {
                if saved {
                    Label("Saved. Re-analyze with corrections to update the report.", systemImage: "checkmark.circle.fill")
                        .font(.caption).foregroundStyle(.green)
                } else {
                    Text("Re-analyze after saving to update all derived results.").font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Button("Revert") { load(); saved = false; error = nil }
                Button("Save review") { save() }.disabled(!valid)
            }
        }.padding(24).frame(maxWidth: 760, alignment: .leading)
        }
        .onAppear { load() }
        .onChange(of: contact) { saved = false }
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
            error = nil; saved = true
        } catch { self.error = error.localizedDescription }
    }
}
