import Foundation
import SwiftUI

// What the take screen, the throw list and the "Needs your eye" inbox need from one analysed throw, read from
// two_view.json and results.json with every field optional (missing stays missing). Decoded here, separately
// from the throw report's model, and loaded off the main thread with a per-file cache.

/// A point on or near the board in board inches: x 0–24 across (12 = centre, + = thrower's right),
/// y 0–48 up the board from the front edge (hole centre at y = 39). Off-board points lie outside that box.
struct BoardXY: Equatable, Sendable {
    var x: Double
    var y: Double

    static let hole = BoardXY(x: 12, y: 39)
    var isOnDeck: Bool { (0...24).contains(x) && (0...48).contains(y) }
}

struct ThrowGlance: Equatable, Sendable {
    /// two_view.json exists (a two-camera throw that has been analysed).
    var hasTwoView = false
    var twoViewStatus: String?
    var twoViewReason: String?
    /// The front camera's result and how sure it was ("suggested" or "needs_confirmation").
    var category: ScoreCategory?
    var resultStatus: String?
    /// What the side camera alone suggested, and whether the two cameras agreed.
    var sideSuggestion: ScoreCategory?
    var viewsAgree: Bool?
    /// "board" / "hole" / "off".
    var whereEnded: String?
    var contact: BoardXY?
    var rest: BoardXY?
    /// "board" / "hole" / "floor".
    var restOn: String?
    /// Signed miss from the hole (in): + long / + thrower's right.
    var shortLong: Double?
    var leftRight: Double?
    var sentence: String?
    var cue: String?
    /// Release speed (m/s) and angle (°), withheld when the engine marked them unreliable or unavailable.
    var speed: Double?
    var angle: Double?
    /// Launch direction from above (°, + = thrower's right), measured or estimated.
    var heading: Double?
    var sideFPS: Double?
    var frontFPS: Double?
    var releaseSide: Int?
    var contactSide: Int?
    var contactFront: Int?
    var releaseFront: Int?
    var frontFrameCount: Int?
    /// Side-clip frame where the bag stopped (board phase).
    var endSide: Int?
    /// Front-clip time (s) at side-clip time 0, from the frame map (or the release frames).
    var frontOffsetSeconds: Double?
    /// Front-clip frame at which the bag had come to rest.
    var restFront: Int?
    var notes: [String] = []
    /// needs_reanalysis.json is present: the files are from a run that is out of date or was interrupted (a mix of
    /// old and new files is possible), so they are not offered for In / On / Off.
    var isStale = false

    /// The engine could not decide the result on its own: the front camera asked for confirmation, or it gave
    /// no category. Landing and rest are still measured automatically.
    var isUnsure: Bool {
        !isStale && hasTwoView && (resultStatus == "needs_confirmation" || category == nil)
    }

    /// The first sentence of the engine's explanation ("Board: 5 in long, 6 in left.").
    var shortSentence: String? {
        guard let sentence, !sentence.isEmpty else { return nil }
        if let end = sentence.range(of: ". ") { return String(sentence[..<end.lowerBound]) + "." }
        return sentence
    }

    /// Why the engine was unsure, in one line.
    var unsureReason: String {
        if !hasTwoView { return "No front-camera reading." }
        if twoViewStatus != "measured" { return twoViewReason ?? "The front camera could not be used for this throw." }
        if category == nil { return "The front camera could not tell where the bag ended." }
        if viewsAgree == false { return "The front and side cameras disagree." }
        return "The front camera was not sure."
    }

    // MARK: Loading

    static func load(analysisURL: URL) -> ThrowGlance? {
        var glance = ThrowGlance()
        glance.isStale = FileManager.default.fileExists(atPath: analysisURL.appendingPathComponent("needs_reanalysis.json").path)
        if let data = try? Data(contentsOf: analysisURL.appendingPathComponent("two_view.json")),
           let file = try? JSONDecoder().decode(GlanceTwoViewFile.self, from: data) {
            glance.apply(file)
        }
        if let data = try? Data(contentsOf: analysisURL.appendingPathComponent("results.json")),
           let file = try? JSONDecoder().decode(GlanceResultsFile.self, from: data) {
            glance.speed = file.coach_metrics?["bag_release_speed_m_s"]?.usable
            glance.angle = file.coach_metrics?["bag_release_angle_deg"]?.usable
        }
        return glance
    }

    private mutating func apply(_ file: GlanceTwoViewFile) {
        hasTwoView = true
        twoViewStatus = file.status
        twoViewReason = file.reason
        category = ScoreCategory(engineCategory: file.result?.category)
            ?? (file.result?.category == nil ? nil : file.result?.points.flatMap(ScoreCategory.init(rawValue:)))
        resultStatus = file.result?.status
        sideSuggestion = ScoreCategory(engineCategory: file.result?.side_suggestion)
        viewsAgree = file.result?.views_agree
        whereEnded = file.landing?.outcome
        if let c = file.landing?.contact, let x = c.x_in, let y = c.y_in, x.isFinite, y.isFinite { contact = BoardXY(x: x, y: y) }
        if file.landing?.outcome == "hole" {
            rest = .hole
            restOn = "hole"
        } else if let r = file.landing?.rest, let x = r.x_in, let y = r.y_in, x.isFinite, y.isFinite {
            rest = BoardXY(x: x, y: y)
            restOn = r.on
        } else {
            restOn = file.landing?.rest?.on
        }
        if file.miss?.status == "measured" {
            shortLong = file.miss?.short_long_in
            leftRight = file.miss?.left_right_in
        }
        sentence = file.explanation?.sentence ?? file.attribution?.sentence
        cue = file.explanation?.cue ?? file.attribution?.cue
        if let status = file.heading?.status, status == "measured" || status == "estimated" { heading = file.heading?.deg }
        let frames = file.frames
        sideFPS = frames?.side_fps
        frontFPS = frames?.front_fps
        releaseSide = frames?.release_side
        contactSide = frames?.contact_side
        contactFront = frames?.contact_front
        releaseFront = frames?.release_front
        frontFrameCount = frames?.front_frame_count
        endSide = file.board_phase?.end?.frame
        let sfps = frames?.side_fps ?? 0, ffps = frames?.front_fps ?? 0
        if sfps > 0, ffps > 0 {
            if let map = file.side_to_front_frames, let index = map.firstIndex(where: { $0 != nil }), let front = map[index] {
                frontOffsetSeconds = Double(front) / ffps - Double(index) / sfps
            } else if let side = frames?.release_side, let front = frames?.release_front {
                frontOffsetSeconds = Double(front) / ffps - Double(side) / sfps
            }
        }
        // The front frame at rest: the side camera's end of the slide mapped to the front clip, else one second
        // after first contact; never past the clip.
        var restFrame: Int?
        if let end = endSide, let map = file.side_to_front_frames, !map.isEmpty {
            restFrame = map[min(max(0, end), map.count - 1)]
        }
        if restFrame == nil, let contact = contactFront, ffps > 0 { restFrame = contact + Int(ffps.rounded()) }
        if let frame = restFrame, let count = frontFrameCount, count > 0 { restFrame = min(frame, count - 1) }
        restFront = restFrame
        notes = (file.notes ?? []) + (file.front_landing?.notes ?? [])
    }
}

// MARK: - Loose file models (every block optional; a block of the wrong shape is skipped, not fatal)

private extension KeyedDecodingContainer {
    func loose<T: Decodable>(_ type: T.Type, _ key: Key) -> T? {
        (try? decodeIfPresent(type, forKey: key)) ?? nil
    }
}

private struct GlanceTwoViewFile: Decodable {
    struct Result: Decodable {
        var category: String?; var points: Int?; var status: String?; var side_suggestion: String?; var views_agree: Bool?
        enum CodingKeys: String, CodingKey { case category, points, status, side_suggestion, views_agree }
        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            category = c.loose(String.self, .category); points = c.loose(Int.self, .points)
            status = c.loose(String.self, .status); side_suggestion = c.loose(String.self, .side_suggestion)
            views_agree = c.loose(Bool.self, .views_agree)
        }
    }
    struct Point: Decodable {
        var x_in: Double?; var y_in: Double?; var on: String?
        enum CodingKeys: String, CodingKey { case x_in, y_in, on }
        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            x_in = c.loose(Double.self, .x_in); y_in = c.loose(Double.self, .y_in); on = c.loose(String.self, .on)
        }
    }
    struct Landing: Decodable {
        var outcome: String?; var contact: Point?; var rest: Point?
        enum CodingKeys: String, CodingKey { case outcome = "where", contact, rest }
        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            outcome = c.loose(String.self, .outcome); contact = c.loose(Point.self, .contact); rest = c.loose(Point.self, .rest)
        }
    }
    struct Miss: Decodable {
        var status: String?; var short_long_in: Double?; var left_right_in: Double?
        enum CodingKeys: String, CodingKey { case status, short_long_in, left_right_in }
        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            status = c.loose(String.self, .status); short_long_in = c.loose(Double.self, .short_long_in)
            left_right_in = c.loose(Double.self, .left_right_in)
        }
    }
    struct Sentence: Decodable {
        var sentence: String?; var cue: String?
        enum CodingKeys: String, CodingKey { case sentence, cue }
        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            sentence = c.loose(String.self, .sentence); cue = c.loose(String.self, .cue)
        }
    }
    struct Heading: Decodable {
        var status: String?; var deg: Double?
        enum CodingKeys: String, CodingKey { case status, deg }
        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            status = c.loose(String.self, .status); deg = c.loose(Double.self, .deg)
        }
    }
    struct Frames: Decodable {
        var front_fps: Double?; var side_fps: Double?; var release_side: Int?; var release_front: Int?
        var contact_side: Int?; var contact_front: Int?; var front_frame_count: Int?
        enum CodingKeys: String, CodingKey {
            case front_fps, side_fps, release_side, release_front, contact_side, contact_front, front_frame_count
        }
        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            front_fps = c.loose(Double.self, .front_fps); side_fps = c.loose(Double.self, .side_fps)
            release_side = c.loose(Int.self, .release_side); release_front = c.loose(Int.self, .release_front)
            contact_side = c.loose(Int.self, .contact_side); contact_front = c.loose(Int.self, .contact_front)
            front_frame_count = c.loose(Int.self, .front_frame_count)
        }
    }
    struct PhaseEnd: Decodable {
        var frame: Int?
        enum CodingKeys: String, CodingKey { case frame }
        init(from decoder: Decoder) throws {
            frame = try decoder.container(keyedBy: CodingKeys.self).loose(Int.self, .frame)
        }
    }
    struct Phase: Decodable {
        var end: PhaseEnd?
        enum CodingKeys: String, CodingKey { case end }
        init(from decoder: Decoder) throws {
            end = try decoder.container(keyedBy: CodingKeys.self).loose(PhaseEnd.self, .end)
        }
    }
    struct FrontLanding: Decodable {
        var notes: [String]?
        enum CodingKeys: String, CodingKey { case notes }
        init(from decoder: Decoder) throws {
            notes = try decoder.container(keyedBy: CodingKeys.self).loose([String].self, .notes)
        }
    }

    var status: String?
    var reason: String?
    var result: Result?
    var landing: Landing?
    var miss: Miss?
    var explanation: Sentence?
    var attribution: Sentence?
    var heading: Heading?
    var frames: Frames?
    var board_phase: Phase?
    var front_landing: FrontLanding?
    var side_to_front_frames: [Int?]?
    var notes: [String]?

    enum CodingKeys: String, CodingKey {
        case status, reason, result, landing, miss, explanation, attribution, heading, frames, board_phase
        case front_landing, side_to_front_frames, notes
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        status = c.loose(String.self, .status)
        reason = c.loose(String.self, .reason)
        result = c.loose(Result.self, .result)
        landing = c.loose(Landing.self, .landing)
        miss = c.loose(Miss.self, .miss)
        explanation = c.loose(Sentence.self, .explanation)
        attribution = c.loose(Sentence.self, .attribution)
        heading = c.loose(Heading.self, .heading)
        frames = c.loose(Frames.self, .frames)
        board_phase = c.loose(Phase.self, .board_phase)
        front_landing = c.loose(FrontLanding.self, .front_landing)
        side_to_front_frames = c.loose([Int?].self, .side_to_front_frames)
        notes = c.loose([String].self, .notes)
    }
}

private struct GlanceResultsFile: Decodable {
    struct Metric: Decodable {
        var value: Double?; var status: String?
        enum CodingKeys: String, CodingKey { case value, status }
        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            value = c.loose(Double.self, .value); status = c.loose(String.self, .status)
        }
        /// The value unless the engine withheld it (same rule as the throw report's tiles).
        var usable: Double? {
            guard let value, value.isFinite, status != "unreliable", status != "unavailable" else { return nil }
            return value
        }
    }
    var coach_metrics: [String: Metric]?
    enum CodingKeys: String, CodingKey { case coach_metrics }
    init(from decoder: Decoder) throws {
        coach_metrics = try decoder.container(keyedBy: CodingKeys.self).loose([String: Metric].self, .coach_metrics)
    }
}

// MARK: - Shared store

/// Which files a glance was read from, and when they last changed.
struct GlanceStamp: Equatable, Sendable {
    var folder: String
    var twoView: Date?
    var results: Date?
    var stale: Bool

    init(folder: URL) {
        self.folder = folder.path
        let manager = FileManager.default
        stale = manager.fileExists(atPath: folder.appendingPathComponent("needs_reanalysis.json").path)
        twoView = (try? manager.attributesOfItem(atPath: folder.appendingPathComponent("two_view.json").path))?[.modificationDate] as? Date
        results = (try? manager.attributesOfItem(atPath: folder.appendingPathComponent("results.json").path))?[.modificationDate] as? Date
    }
}

/// Glances for every analysed throw in the library, refreshed when analyses or the library change. Files are read
/// off the main thread and only again when their modification date changes.
@MainActor
final class ThrowGlanceStore: ObservableObject {
    @Published private(set) var glances: [UUID: ThrowGlance] = [:]
    private var stamps: [UUID: GlanceStamp] = [:]
    private var generation = 0

    func glance(_ trialID: UUID) -> ThrowGlance? { glances[trialID] }

    /// Throws that need a person to say In / On / Off: analysed, the engine unsure, and no result entered by a
    /// person (an automatic result does not count as one).
    func needsEye(_ trials: [Trial]) -> [Trial] {
        trials.filter { trial in
            guard trial.analysisRelativePath != nil, glances[trial.id]?.isUnsure == true else { return false }
            guard let outcome = trial.outcome, outcome.scoreCategory != nil else { return true }
            return outcome.isAutomatic
        }
    }

    func refresh(store: ProjectStore) async {
        generation += 1
        let mine = generation
        let folders: [(UUID, URL)] = (store.project?.trials ?? []).compactMap { trial in
            store.analysisURL(for: trial).map { (trial.id, $0) }
        }
        let known = stamps
        let loaded: [UUID: (GlanceStamp, ThrowGlance?)] = await Task.detached(priority: .utility) {
            var changed: [UUID: (GlanceStamp, ThrowGlance?)] = [:]
            for (id, folder) in folders {
                let stamp = GlanceStamp(folder: folder)
                if known[id] == stamp { continue }
                changed[id] = (stamp, ThrowGlance.load(analysisURL: folder))
            }
            return changed
        }.value
        guard mine == generation else { return }   // a newer refresh is on its way
        let present = Set(folders.map { $0.0 })
        var next = glances.filter { present.contains($0.key) }
        stamps = stamps.filter { present.contains($0.key) }
        for (id, entry) in loaded {
            stamps[id] = entry.0
            next[id] = entry.1
        }
        if next != glances { glances = next }
    }
}

// MARK: - Shared formatting (take screen and inbox)

enum GlanceText {
    /// "8 in left", "3 in right", "on line" (whole inches).
    static func sideways(_ inches: Double?) -> String? {
        guard let inches, inches.isFinite else { return nil }
        if abs(inches) < 1 { return "on line" }
        return "\(number(abs(inches), digits: 0)) in \(inches > 0 ? "right" : "left")"
    }

    /// "12 in short", "4 in long", "on distance" (whole inches).
    static func depth(_ inches: Double?) -> String? {
        guard let inches, inches.isFinite else { return nil }
        if abs(inches) < 1 { return "on distance" }
        return "\(number(abs(inches), digits: 0)) in \(inches > 0 ? "long" : "short")"
    }

    /// Heading to 0.5°: "1.5° right", "straight".
    static func heading(_ degrees: Double?) -> String? {
        guard let degrees, degrees.isFinite else { return nil }
        let half = (abs(degrees) * 2).rounded() / 2
        if half < 0.5 { return "straight" }
        return "\(number(half, digits: half == half.rounded() ? 0 : 1))° \(degrees > 0 ? "right" : "left")"
    }

    /// "Front camera: off the board · side camera: on the board (they disagree)".
    static func readings(_ glance: ThrowGlance) -> String {
        let front = glance.category.map { $0.plainLabel.lowercased() } ?? "could not tell"
        let side = glance.sideSuggestion.map { $0.plainLabel.lowercased() } ?? "no reading"
        var text = "Front camera: \(front) · side camera: \(side)"
        if glance.category != nil, glance.sideSuggestion != nil {
            text += glance.viewsAgree == false || glance.category != glance.sideSuggestion ? " (they disagree)" : " (they agree)"
        }
        return text
    }
}

extension ThrowGlance {
    /// The cameras' first contact and rest as board points for a recorded outcome (on the deck only; a bag in the
    /// hole or on the floor has no deck rest point).
    var measuredBoardPoints: (contact: BoardPoint?, rest: BoardPoint?) {
        func point(_ p: BoardXY?) -> BoardPoint? {
            guard let p, p.isOnDeck else { return nil }
            return BoardPoint(xInches: (p.x * 100).rounded() / 100, yInches: (p.y * 100).rounded() / 100,
                              precision: "board_camera_homography")
        }
        return (point(contact), whereEnded == "hole" ? nil : point(rest))
    }
}

/// Points and counts for one take ("6/12 · 1 in · 2 on · 1 off"), from the recorded results.
struct TakeTally: Equatable {
    var points = 0
    var possible = 0
    var scored = 0
    var inHole = 0
    var onBoard = 0
    var offBoard = 0
    var unscored = 0
    var analysed = 0
    var throwsCount = 0

    init(_ trials: [Trial]) {
        throwsCount = trials.count
        possible = 3 * trials.count
        for trial in trials {
            if trial.analysisRelativePath != nil { analysed += 1 }
            switch trial.outcome?.scoreCategory {
            case .throughHole?: inHole += 1; points += 3; scored += 1
            case .onBoard?: onBoard += 1; points += 1; scored += 1
            case .offBoard?: offBoard += 1; scored += 1
            case nil: unscored += 1
            }
        }
    }

    /// "6/12".
    var pointsText: String { "\(points)/\(possible)" }

    /// "1 in · 2 on · 1 off".
    var countsText: String { "\(inHole) in · \(onBoard) on · \(offBoard) off" }
}
