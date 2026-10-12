import Charts
import AVFoundation
import SwiftUI

// Two-camera takes (python `takes.py`, `front_view.py`, `two_view.py`): the side camera measures the
// release and the distance, the front camera (behind the board, facing the athlete) measures left/right,
// where the bag ended and the frontal-plane body. This file reads two_view.json and draws the
// "Both cameras" card, the whole throw seen from above and the front-camera replay overlay.

// MARK: - Model

/// two_view.json, read loosely: every field is optional so older or partial files still open.
struct TwoViewDocument: Decodable, Equatable {
    struct Metric: Decodable, Equatable {
        var value: Double?; var unit: String?; var label: String?; var status: String?; var reason: String?
    }
    struct Heading: Decodable, Equatable {
        var status: String?; var deg: Double?; var release_offset_m: Double?; var contact_offset_m: Double?
        var sideways_at_hole_in: Double?; var from_aim_in: Double?; var from_release_position_in: Double?; var reason: String?
    }
    struct Result: Decodable, Equatable {
        var category: String?; var points: Int?; var source: String?; var side_suggestion: String?
        var views_agree: Bool?; var status: String?
    }
    struct Miss: Decodable, Equatable {
        var status: String?; var short_long_in: Double?; var left_right_in: Double?; var distance_in: Double?; var reason: String?
    }
    struct Explanation: Decodable, Equatable { var sentence: String?; var kind: String? }
    struct Camera: Decodable, Equatable { var hfov_deg: Double?; var status: String?; var source: String?; var reason: String? }
    struct Sync: Decodable, Equatable {
        var status: String?; var offset_s: Double?; var correlation: Double?; var margin: Double?; var uncertainty_s: Double?; var reason: String?
    }
    struct SyncCheck: Decodable, Equatable { var status: String?; var front_frames_difference: Int?; var agrees: Bool? }
    struct Frames: Decodable, Equatable {
        var front_fps: Double?; var side_fps: Double?; var release_side: Int?; var release_front: Int?
        var contact_side: Int?; var contact_front: Int?; var front_frame_count: Int?
    }
    struct Alignment: Decodable, Equatable { var status: String?; var median_correlation: Double?; var max_drift_px: Double? }
    struct PathPoint: Decodable, Equatable { var frame: Int; var px: [Double] }
    struct LandingPoint: Decodable, Equatable { var x_in: Double?; var y_in: Double?; var on: String?; var status: String? }
    struct Landing: Decodable, Equatable {
        var outcome: String?; var contact: LandingPoint?; var rest: LandingPoint?
        enum CodingKeys: String, CodingKey { case outcome = "where", contact, rest }
    }
    struct FrontPoint: Decodable, Equatable { var frame: Int?; var px: [Double]? }
    struct FrontLanding: Decodable, Equatable {
        var status: String?; var outcome: String?; var path: [FrontPathPoint]?; var contact: FrontPoint?; var rest: FrontPoint?
        var ambiguous: Bool?; var notes: [String]?; var reason: String?
        enum CodingKeys: String, CodingKey { case status, outcome = "where", path, contact, rest, ambiguous, notes, reason }
    }
    /// `phase`: "air" before the front camera's own first contact, "deck" from it (engine ≥ two_view_v7).
    struct FrontPathPoint: Decodable, Equatable { var frame: Int; var px: [Double]; var deck_in: [Double]?; var phase: String? }
    /// two_view.json → flight_3d (python `flight3d.reconstruct_flight`, METHODS_AND_MATH §5.4). World frame: x along the
    /// throw from the release point, y sideways from the board's centre line (+ thrower's right), z height above the
    /// floor (m); t from release (s, side camera clock). Numbers are present only when `status` is measured or estimated.
    struct Flight3D: Decodable, Equatable {
        struct Release: Decodable, Equatable { var lateral_m: Double?; var height_m: Double?; var to_board_front_m: Double? }
        struct Velocity: Decodable, Equatable { var along: Double?; var lateral: Double?; var vertical: Double?; var speed: Double? }
        struct Landing: Decodable, Equatable {
            var t_s: Double?; var at: String?; var predicted_x_in: Double?; var predicted_along_m: Double?
            var predicted_height_m: Double?; var measured_x_in: Double?; var difference_in: Double?
        }
        struct Fit: Decodable, Equatable {
            var inlier_frames: Int?; var frames_searched: Int?; var rms_px: Double?; var timing_offset_s: Double?
            var front_hfov_deg: Double?; var coverage_by_third: [Double]?; var side_scale_status: String?
        }
        struct ReleaseCheck: Decodable, Equatable { var front_pose_hand_lateral_m: Double?; var difference_m: Double? }
        struct HeadingCheck: Decodable, Equatable { var two_view_heading_deg: Double?; var difference_deg: Double? }
        /// One 60 Hz sample of the fitted 3D path (the model through the measured side arc and front line).
        struct Sample: Decodable, Equatable { var t_s: Double; var x_m: Double; var y_m: Double; var z_m: Double }

        var method_version: String?
        var status: String?
        var reason: String?
        var release: Release?
        var velocity_m_s: Velocity?
        /// atan2(lateral velocity, along velocity): + = launched towards the thrower's right.
        var lateral_launch_angle_deg: Double?
        var landing: Landing?
        var fit: Fit?
        var release_check: ReleaseCheck?
        var heading_check: HeadingCheck?
        var path_m: [Sample]?
        /// The 3D path projected into every front frame from release to first contact.
        var front_path: [PathPoint]?
        var notes: [String]?

        var isAvailable: Bool { status == "measured" || status == "estimated" }
    }

    var status: String
    var reason: String?
    var take: Int?
    var throw_in_take: Int?
    var sync: Sync?
    var sync_check: SyncCheck?
    var camera: Camera?
    var alignment: Alignment?
    var frames: Frames?
    var heading: Heading?
    var result: Result?
    var miss: Miss?
    var explanation: Explanation?
    var landing: Landing?
    var front_landing: FrontLanding?
    var frontal: [String: Metric]?
    var front_path: [PathPoint]?
    var deck_corners_by_frame_px: [[[Double]]]?
    var front_size: [Double]?
    var side_to_front_frames: [Int?]?
    var notes: [String]?
    /// The result to record automatically (front camera confident, views agree); nil otherwise.
    var auto_outcome: TrialOutcome?
    /// "flight_3d" when `front_path` is the projected 3D flight, "front_track" for the older front tracker.
    var front_path_source: String?
    /// The 3D flight (§5.4) and the per-throw miss attribution. Decoded separately in `load` so that a block written
    /// by a newer engine that does not match these types never hides the rest of the front camera's analysis.
    var flight_3d: Flight3D? = nil
    var attribution: ThrowAttribution? = nil
    var front_kinematics: FrontKinematics? = nil

    /// two_view.json → front_kinematics (front_view.front_kinematics): front view 2D series around release.
    struct FrontKinematics: Decodable, Equatable {
        var status: String?
        var reason: String?
        var t_s: [Double]?
        var wrist_across_sw: [Double?]?
        var trunk_lean_deg: [Double?]?
        var forward_swing_start_s: Double?
    }

    enum CodingKeys: String, CodingKey {
        case status, reason, take, throw_in_take, sync, sync_check, camera, alignment, frames, heading, result, miss
        case explanation, landing, front_landing, frontal, front_path, deck_corners_by_frame_px, front_size
        case side_to_front_frames, notes, auto_outcome, front_path_source
    }

    static func load(_ analysisURL: URL?) -> TwoViewDocument? {
        guard let analysisURL, let data = try? Data(contentsOf: analysisURL.appendingPathComponent("two_view.json")) else { return nil }
        guard var document = try? JSONDecoder().decode(TwoViewDocument.self, from: data) else { return nil }
        struct FlightBox: Decodable { var flight_3d: Flight3D? }
        struct AttributionBox: Decodable { var attribution: ThrowAttribution? }
        struct FrontBodyBox: Decodable { var front_kinematics: FrontKinematics? }
        document.front_kinematics = (try? JSONDecoder().decode(FrontBodyBox.self, from: data))?.front_kinematics
        document.flight_3d = (try? JSONDecoder().decode(FlightBox.self, from: data))?.flight_3d
        document.attribution = (try? JSONDecoder().decode(AttributionBox.self, from: data))?.attribution
        return document
    }

    /// The 3D flight when it was fitted and accepted (measured or estimated); nil otherwise.
    var flight: Flight3D? { flight_3d?.isAvailable == true ? flight_3d : nil }

    /// Sideways launch direction (° , + = right) and where it came from: the 3D flight when accepted, else the
    /// two-view heading (release hand → first contact). Nil when neither was measured.
    var launchDirection: (deg: Double, releaseRightM: Double?, source: String, status: String?)? {
        if let flight, let deg = flight.lateral_launch_angle_deg {
            return (deg, flight.release?.lateral_m, "3D flight", flight.status)
        }
        if let heading, heading.status == "measured" || heading.status == "estimated", let deg = heading.deg {
            return (deg, heading.release_offset_m, "release hand → first contact", heading.status)
        }
        return nil
    }

    var isMeasured: Bool { status == "measured" }

    /// The front camera's result as a score, when it decided one.
    var suggestedScore: ScoreCategory? { result?.points.flatMap(ScoreCategory.init(rawValue:)) }

    /// Front-clip frame for a side-clip frame (same instant), when the views were synchronised.
    func frontFrame(forSide frame: Int) -> Int? {
        guard let map = side_to_front_frames, !map.isEmpty else { return nil }
        return map[min(max(0, frame), map.count - 1)]
    }

    var frontFPS: Double { frames?.front_fps ?? 30 }
    var frontWidth: Double { front_size?.first ?? 1280 }
    var frontHeight: Double { front_size?.dropFirst().first ?? 720 }

    /// Deck corners (front-left, front-right, back-right, back-left as the thrower sees them) in a front frame.
    func corners(frontFrame: Int) -> [CGPoint]? {
        guard let all = deck_corners_by_frame_px, !all.isEmpty else { return nil }
        let quad = all[min(max(0, frontFrame), all.count - 1)]
        guard quad.count == 4 else { return nil }
        return quad.map { CGPoint(x: $0.first ?? 0, y: $0.dropFirst().first ?? 0) }
    }

    /// Ordered frontal-plane measures shown on the card.
    static let frontalKeys: [(key: String, label: String, help: String)] = [
        ("arm_across_body_sw", "Hand across body",
         "Where the throwing hand is at release, sideways from the throwing shoulder, in shoulder widths. 0 is a straight pendulum swing; + means the hand crossed towards the body's midline, − that it swung out."),
        ("trunk_side_lean_deg", "Trunk side lean",
         "Hip centre → shoulder centre against vertical in the front camera, at release. + leans towards the throwing arm."),
        ("release_point_offset_m", "Release point sideways",
         "How far the hand released the bag from the board's centre line (+ to the thrower's right)."),
        ("stance_offset_m", "Stance offset",
         "Feet midpoint from the board's centre line one second before release (+ to the thrower's right)."),
        ("hand_path_range_sw", "Hand path sideways range",
         "How far the throwing hand moved sideways during the forward swing, in shoulder widths (front view 2D). A planar pendulum swing gives ≈ 0. Mostly describes how this athlete throws (reproducible, ICC 0.89)."),
        ("trunk_lean_change_deg", "Trunk lean change",
         "Change in trunk side lean from set-up to release (front view 2D), + towards the throwing arm."),
    ]
}

/// "8 in left", "3 in right", "on line".
func sidewaysText(_ inches: Double?, precision: Double = 1) -> String? {
    guard let inches else { return nil }
    if abs(inches) < precision { return "on line" }
    return "\(number(abs(inches), digits: 0)) in \(inches > 0 ? "right" : "left")"
}

/// "12 in short", "4 in long", "at the hole".
func distanceText(_ inches: Double?) -> String? {
    guard let inches else { return nil }
    if abs(inches) < 1 { return "on distance" }
    return "\(number(abs(inches), digits: 0)) in \(inches > 0 ? "long" : "short")"
}

// MARK: - Two-camera details

/// The front camera's supporting measures, shown under the throw's Details: the frontal-plane body at release
/// (plausibility checks, never per-throw causes; council §7), how the two cameras were synchronised and the board
/// tracked, and how well the 3D flight fitted.
struct TwoViewDetailsCard: View {
    let document: TwoViewDocument

    var body: some View {
        Card("Front camera", symbol: "video.badge.checkmark",
             subtitle: "Body seen from the front, camera sync and the 3D flight fit.") {
            if document.isMeasured {
                frontalGrid
                if let series = document.front_kinematics, series.status == "measured" {
                    FrontBodyChart(series: series)
                }
                Text("Frontal angles are 2D image angles at release: plausibility checks, not causes of this throw's result.")
                    .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                Text(Self.trustText(document))
                    .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                flightFacts
            } else {
                Label(document.reason ?? "The front camera could not be used for this throw.", systemImage: "video.slash")
                    .foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var frontalGrid: some View {
        let frontal = document.frontal ?? [:]
        return VStack(alignment: .leading, spacing: Space.s) {
            Text("Body from the front, at release").font(.headline)
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 200), spacing: Space.s, alignment: .top)], spacing: Space.s) {
                ForEach(TwoViewDocument.frontalKeys, id: \.key) { item in
                    FrontalTile(label: item.label, help: item.help, metric: frontal[item.key])
                }
            }
        }
    }

    /// The 3D flight's fit: status, launch direction, release position and the agreement checks.
    @ViewBuilder private var flightFacts: some View {
        VStack(alignment: .leading, spacing: Space.xs) {
            Text("3D flight").font(.headline)
            if let flight = document.flight {
                Grid(alignment: .leading, horizontalSpacing: Space.xl, verticalSpacing: Space.xs) {
                    GridRow { Text("Status"); Text(flight.status == "measured" ? "Measured" : "Estimated (side scale or front field of view estimated)") }
                    if let deg = flight.lateral_launch_angle_deg {
                        GridRow { Text("Launch direction"); Text(launchText(deg)) }
                    }
                    if let x0 = flight.release?.lateral_m {
                        GridRow { Text("Release point"); Text(releaseText(x0)) }
                    }
                    if let fit = flight.fit, let inliers = fit.inlier_frames, let searched = fit.frames_searched {
                        GridRow {
                            Text("Bag found on the path")
                            Text("\(inliers) of \(searched) front frames" + (fit.rms_px.map { " · \(number($0, digits: 1)) px RMS" } ?? ""))
                        }
                    }
                    if let landing = flight.landing, let difference = landing.difference_in {
                        GridRow { Text("Landing vs front camera"); Text("\(number(abs(difference), digits: 1)) in apart across the deck") }
                    }
                    if let check = flight.heading_check, let difference = check.difference_deg {
                        GridRow { Text("vs two-view heading"); Text("\(number(abs(difference), digits: 1))° apart") }
                    }
                }
                .font(.callout).monospacedDigit()
            } else {
                Text(document.flight_3d?.reason ?? "The 3D flight was not computed for this throw.")
                    .font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private func launchText(_ deg: Double) -> String {
        let half = (abs(deg) * 2).rounded() / 2
        return half == 0 ? "straight down the centre line" : "\(number(half, digits: 1))° \(deg > 0 ? "right" : "left")"
    }

    private func releaseText(_ metres: Double) -> String {
        let cm = abs(metres) * 100
        return cm < 0.5 ? "on the board's centre line" : "\(number(cm, digits: 0)) cm \(metres > 0 ? "right" : "left") of the board's centre line"
    }

    /// "Cameras synchronised by sound (match 0.66, ±18 ms) · first contact seen 0 front frames apart · …"
    static func trustText(_ document: TwoViewDocument) -> String {
        var parts: [String] = []
        if let sync = document.sync, sync.status == "measured", let r = sync.correlation {
            parts.append("Cameras synchronised by sound (match \(number(r, digits: 2)), ±\(number(1000 * (sync.uncertainty_s ?? 0.0175), digits: 0)) ms)")
        }
        if let check = document.sync_check, check.status == "measured", let gap = check.front_frames_difference {
            parts.append("first contact seen \(abs(gap)) front frame\(abs(gap) == 1 ? "" : "s") apart")
        }
        if let camera = document.camera, let hfov = camera.hfov_deg {
            parts.append("front field of view \(number(hfov, digits: 0))° (\(camera.source ?? camera.status ?? ""))")
        }
        if let drift = document.alignment?.max_drift_px {
            parts.append("board tracked through \(number(drift, digits: 0)) px of camera drift")
        }
        return parts.isEmpty ? "Camera sync details were not saved." : parts.joined(separator: " · ") + "."
    }
}

/// One frontal-plane measure: value, unit, status glyph, and what it means.
struct FrontalTile: View {
    let label: String
    let help: String
    let metric: TwoViewDocument.Metric?

    var body: some View {
        VStack(alignment: .leading, spacing: Space.xs) {
            HStack(spacing: Space.xs) {
                Text(label).font(.subheadline.weight(.semibold)).lineLimit(1)
                Spacer(minLength: 0)
                ReliabilityGlyph(status: statusForGlyph)
            }
            HStack(alignment: .firstTextBaseline, spacing: 3) {
                Text(valueText).font(.title3.monospacedDigit())
                if metric?.value != nil, let unit = unitText { Text(unit).font(.caption).foregroundStyle(.secondary) }
            }
            if metric?.value == nil, let reason = metric?.reason {
                Text(reason).font(.caption2).foregroundStyle(.secondary).lineLimit(2)
            }
        }
        .padding(Space.s)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).strokeBorder(.separator.opacity(0.6)))
        .help(help)
        .accessibilityElement(children: .combine)
    }

    private var statusForGlyph: String {
        switch metric?.status {
        case "measured": "reliable"
        case "estimated": "caution"
        default: ""
        }
    }

    private var valueText: String {
        guard let value = metric?.value else { return "—" }
        switch metric?.unit {
        case "m": return (value >= 0 ? "+" : "−") + number(abs(value) * 100, digits: 0)
        case "°": return (value >= 0 ? "+" : "−") + number(abs(value), digits: 0) + "°"
        default: return (value >= 0 ? "+" : "−") + number(abs(value), digits: 2)
        }
    }

    private var unitText: String? {
        switch metric?.unit {
        case "m": "cm"
        case "°": nil
        case "shoulder widths": "shoulder widths"
        default: metric?.unit
        }
    }
}

// MARK: - The throw from above

/// Release point → first contact → slide → end, seen from above and drawn to scale: nothing is stretched, so the
/// 24 × 48 in board keeps its shape and its long side runs along the throw. Top strip: the release and the board at
/// their measured distance, the throw running left to right. Below: the same board enlarged (front edge, the low end,
/// at the left; the thrower's left at the top) with first contact, the slide, where the bag ended and the miss from
/// the hole. The bag follows the replay's current frame in both.
struct ThrowFromAbove: View {
    let document: TwoViewDocument
    let phase: BoardPhase?
    let currentFrame: Int
    /// Release → front of the board (m, side camera). Without it only the enlarged board is drawn.
    var releaseToBoardM: Double?
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        Canvas { context, size in
            guard let geometry = Geometry(document: document, phase: phase, size: size, releaseToBoardM: releaseToBoardM) else {
                context.draw(Text("Not enough measured to draw the throw.").font(.callout).foregroundStyle(.secondary),
                             at: CGPoint(x: size.width / 2, y: size.height / 2))
                return
            }
            let dark = colorScheme == .dark
            geometry.drawOverview(context, dark: dark)
            geometry.drawBoard(context, dark: dark)
            geometry.drawBag(context, frame: currentFrame)
        }
        .accessibilityElement()
        .accessibilityLabel("The throw seen from above, to scale, with the board enlarged")
        .accessibilityValue(accessibilityText)
    }

    private var accessibilityText: String {
        var parts: [String] = []
        if let sentence = document.explanation?.sentence { parts.append(sentence) }
        if let metres = releaseToBoardM { parts.append("Released \(number(metres, digits: 2)) m from the front of the board.") }
        if let contact = document.landing?.contact, let x = contact.x_in, let y = contact.y_in {
            parts.append("First contact \(number(y, digits: 0)) in up the board, \(sidewaysText(x - 12) ?? "on line").")
        }
        if let miss = Geometry.missText(document.miss, separator: " and ") { parts.append("Ended \(miss) of the hole.") }
        return parts.joined(separator: " ")
    }

    /// Layout and drawing. Inches throughout: `v` up the deck from the front edge, `right` to the thrower's right of
    /// the board's centreline (front camera), horizontal inches from the release along the throw.
    struct Geometry {
        /// A point on or near the board: `v` inches up the deck from the front edge (below 0 or above 48 = on the
        /// floor beyond that end) and `right` inches to the thrower's right of the centreline.
        struct DeckPoint: Equatable { var v: Double; var right: Double }

        /// The top strip: the whole throw to scale.
        struct Overview {
            /// Release → front edge, horizontal inches.
            let releaseToFront: Double
            /// Points per inch (the same along and across).
            let scale: CGFloat
            /// Screen point of the release, on the board's centreline.
            let origin: CGPoint
            let height: CGFloat
            func point(_ along: Double, _ right: Double) -> CGPoint {
                CGPoint(x: origin.x + CGFloat(along) * scale, y: origin.y + CGFloat(right) * scale)
            }
        }

        /// Inches of floor shown around the enlarged board; a bag that ended further away is shown by an arrow.
        static let apron = 6.0
        /// Regulation deck: 48 in long, front edge 3 in and back edge 12 in high (10.8°): along-deck → horizontal.
        static let slopeCos = cos(BoardGeometry.regulation.angle)
        /// The board's length seen from above (horizontal inches).
        static var footprint: Double { 48 * slopeCos }
        static let pad: CGFloat = 10
        static let labelRow: CGFloat = 14

        let size: CGSize
        let contact: DeckPoint?
        let rest: DeckPoint?
        let inHole: Bool
        let offBoard: Bool
        /// Release point sideways from the board's centreline (in, + = thrower's right).
        let releaseRight: Double?
        let headingDeg: Double?
        let miss: String?
        let releaseFrame: Int?
        let contactFrame: Int?
        let endFrame: Int?
        /// Side-camera inches up the deck by frame during the slide, to move the bag at its measured pace.
        let slideProgress: [Int: Double]
        let overview: Overview?
        /// The enlarged board on screen and its scale (points per inch).
        let deck: CGRect
        let ppi: CGFloat

        init?(document: TwoViewDocument, phase: BoardPhase?, size: CGSize, releaseToBoardM: Double?) {
            guard let landing = document.landing, size.width > 60, size.height > 80 else { return nil }
            var contact: DeckPoint?
            if let c = landing.contact, let x = c.x_in, let y = c.y_in { contact = DeckPoint(v: y, right: x - 12) }
            let inHole = landing.outcome == "hole"
            var rest: DeckPoint?
            if inHole {
                rest = DeckPoint(v: 39, right: 0)
            } else if let r = landing.rest, let x = r.x_in, let y = r.y_in {
                rest = DeckPoint(v: y, right: x - 12)
            }
            if contact == nil && rest == nil { return nil }
            let releaseRight = document.heading?.release_offset_m.map { $0 / 0.0254 }
            self.size = size
            self.contact = contact
            self.rest = rest
            self.inHole = inHole
            offBoard = landing.outcome == "off"
            self.releaseRight = releaseRight
            headingDeg = document.heading?.deg
            miss = Self.missText(document.miss)
            releaseFrame = document.frames?.release_side
            contactFrame = document.frames?.contact_side ?? phase?.touchdown?.frame
            endFrame = phase?.end?.frame
            var progress: [Int: Double] = [:]
            for point in phase?.path ?? [] {
                if let v = point.v_in { progress[point.frame] = v }
            }
            slideProgress = progress

            let width = size.width, height = size.height, pad = Self.pad, row = Self.labelRow
            // Top strip: release → board at the measured distance, one scale for both directions.
            var overview: Overview?
            if let metres = releaseToBoardM, metres.isFinite, metres > 0 {
                let front = metres / 0.0254
                let stripHeight = min(92, height * 0.3)
                var along: [Double] = [0, front + Self.footprint]
                var across: [Double] = [12, -12]
                if let releaseRight { across.append(releaseRight) }
                for point in [contact, rest].compactMap({ $0 }) {
                    along.append(front + Self.ground(point.v))
                    across.append(point.right)
                }
                let low = (along.min() ?? 0) - 14, high = (along.max() ?? 0) + 10
                let reach = (across.map { abs($0) }.max() ?? 12) + 4
                let scale = min((width - 2 * pad) / CGFloat(high - low), max(1, stripHeight - 2 * row) / CGFloat(2 * reach))
                let originX = pad + ((width - 2 * pad) - CGFloat(high - low) * scale) / 2 - CGFloat(low) * scale
                overview = Overview(releaseToFront: front, scale: scale,
                                    origin: CGPoint(x: originX, y: row + (stripHeight - 2 * row) / 2), height: stripHeight)
            }
            self.overview = overview
            // Below: the board enlarged, true 2 : 1 shape, with a little floor around it.
            let top = overview.map { $0.height + 8 } ?? 0
            let available = max(20, height - top - 2 * row)
            let ppi = max(0.5, min((width - 2 * pad) / CGFloat(48 + 2 * Self.apron), available / CGFloat(24 + 2 * Self.apron)))
            self.ppi = ppi
            deck = CGRect(x: (width - 48 * ppi) / 2, y: top + row + (available - 24 * ppi) / 2, width: 48 * ppi, height: 24 * ppi)
        }

        /// Horizontal inches from the board's front edge for a point `v` inches up the deck (floor beyond either end).
        static func ground(_ v: Double) -> Double {
            if v < 0 { return v }
            if v > 48 { return footprint + (v - 48) }
            return v * slopeCos
        }

        /// The point as shown on the enlarged board, and whether it lies beyond the view (it is then moved in along
        /// the line from the hole and drawn as an arrow).
        static func shown(_ p: DeckPoint) -> (point: DeckPoint, outside: Bool) {
            let lowV = -apron, highV = 48 + apron, lowR = -12 - apron, highR = 12 + apron
            if p.v >= lowV && p.v <= highV && p.right >= lowR && p.right <= highR { return (p, false) }
            let dv = p.v - 39, dr = p.right
            var t = 1.0
            if dv > 0 { t = min(t, (highV - 39) / dv) }
            if dv < 0 { t = min(t, (lowV - 39) / dv) }
            if dr > 0 { t = min(t, highR / dr) }
            if dr < 0 { t = min(t, lowR / dr) }
            return (DeckPoint(v: 39 + dv * t, right: dr * t), true)
        }

        /// "5 in long · 6 in left", from the front camera's signed miss.
        static func missText(_ miss: TwoViewDocument.Miss?, separator: String = " · ") -> String? {
            guard let miss, miss.status == "measured" else { return nil }
            let parts = [distanceText(miss.short_long_in), sidewaysText(miss.left_right_in)].compactMap { $0 }
            return parts.isEmpty ? nil : parts.joined(separator: separator)
        }

        /// Screen point on the enlarged board.
        func boardPoint(_ p: DeckPoint) -> CGPoint {
            CGPoint(x: deck.minX + CGFloat(p.v) * ppi, y: deck.midY + CGFloat(p.right) * ppi)
        }

        /// Screen point in the top strip.
        func overviewPoint(_ p: DeckPoint, _ overview: Overview) -> CGPoint {
            overview.point(overview.releaseToFront + Self.ground(p.v), p.right)
        }

        private func caption(_ text: String) -> Text { Text(text).font(.caption2).foregroundStyle(.secondary) }

        private func dot(_ context: GraphicsContext, _ p: CGPoint, radius: CGFloat, ink: Color, lineWidth: CGFloat) {
            let circle = Path(ellipseIn: CGRect(x: p.x - radius, y: p.y - radius, width: 2 * radius, height: 2 * radius))
            context.fill(circle, with: .color(.white))
            context.stroke(circle, with: .color(ink), lineWidth: lineWidth)
        }

        // MARK: Top strip

        func drawOverview(_ context: GraphicsContext, dark: Bool) {
            guard let overview else { return }
            let front = overview.releaseToFront
            // Centre line from the release to past the board.
            var centre = Path()
            centre.move(to: overview.point(0, 0)); centre.addLine(to: overview.point(front + Self.footprint + 6, 0))
            context.stroke(centre, with: .color(.primary.opacity(0.2)), style: StrokeStyle(lineWidth: 1, dash: [4, 4]))
            // The board's footprint, its front (low) edge drawn heavier, and the hole.
            let a = overview.point(front, -12), b = overview.point(front + Self.footprint, 12)
            let board = CGRect(x: a.x, y: a.y, width: b.x - a.x, height: b.y - a.y)
            context.fill(Path(board), with: .color(Color.red.opacity(dark ? 0.30 : 0.16)))
            context.stroke(Path(board), with: .color(.primary.opacity(0.5)), lineWidth: 1)
            var edge = Path(); edge.move(to: CGPoint(x: board.minX, y: board.minY)); edge.addLine(to: CGPoint(x: board.minX, y: board.maxY))
            context.stroke(edge, with: .color(.primary.opacity(0.8)), lineWidth: 2)
            let hole = overview.point(front + 39 * Self.slopeCos, 0), hr = max(1.5, 3 * overview.scale)
            context.fill(Path(ellipseIn: CGRect(x: hole.x - hr, y: hole.y - hr, width: 2 * hr, height: 2 * hr)), with: .color(.primary.opacity(0.85)))
            // Zoom box around the board, linked to the enlarged board below.
            let z0 = overview.point(front - 3, -15), z1 = overview.point(front + Self.footprint + 3, 15)
            let zoom = CGRect(x: z0.x, y: z0.y, width: z1.x - z0.x, height: z1.y - z0.y)
            context.stroke(Path(zoom), with: .color(.secondary.opacity(0.8)), style: StrokeStyle(lineWidth: 0.8, dash: [2, 2]))
            var links = Path()
            links.move(to: CGPoint(x: zoom.minX, y: zoom.maxY)); links.addLine(to: CGPoint(x: deck.minX, y: deck.minY))
            links.move(to: CGPoint(x: zoom.maxX, y: zoom.maxY)); links.addLine(to: CGPoint(x: deck.maxX, y: deck.minY))
            context.stroke(links, with: .color(.secondary.opacity(0.35)), lineWidth: 0.8)
            // Flight (release → first contact), slide, end.
            let contactPoint = contact.map { overviewPoint($0, overview) }
            let restPoint = rest.map { overviewPoint($0, overview) }
            if let releaseRight {
                let release = overview.point(0, releaseRight)
                if let contactPoint {
                    var flight = Path(); flight.move(to: release); flight.addLine(to: contactPoint)
                    context.stroke(flight, with: .color(measuredInk), style: StrokeStyle(lineWidth: 2.2, lineCap: .round))
                }
                context.fill(Path(ellipseIn: CGRect(x: release.x - 4, y: release.y - 4, width: 8, height: 8)), with: .color(.primary.opacity(0.7)))
                context.draw(caption("Release"), at: CGPoint(x: release.x, y: release.y + 7), anchor: .top)
            }
            if let contactPoint, let restPoint {
                var slide = Path(); slide.move(to: contactPoint); slide.addLine(to: restPoint)
                context.stroke(slide, with: .color(slideInk), style: StrokeStyle(lineWidth: 2.2, lineCap: .round))
            }
            if let contactPoint { dot(context, contactPoint, radius: 3.5, ink: .accentColor, lineWidth: 1.8) }
            if let restPoint, !inHole {
                context.fill(Path(roundedRect: CGRect(x: restPoint.x - 3, y: restPoint.y - 3, width: 6, height: 6), cornerRadius: 1),
                             with: .color(Color.accentColor))
            }
            // Distance and aim, written rather than drawn: a few inches over ~6 m is a fraction of a degree.
            var text = "\(number(front * 0.0254, digits: 2)) m to the board"
            if let deg = headingDeg {
                text += " · aimed " + (abs(deg) < 0.3 ? "straight" : "\(number(abs(deg), digits: 1))° \(deg > 0 ? "right" : "left")")
            }
            context.draw(caption(text), at: CGPoint(x: overview.point(front / 2, 0).x, y: Self.labelRow - 2), anchor: .bottom)
        }

        // MARK: Enlarged board

        func drawBoard(_ context: GraphicsContext, dark: Bool) {
            let board = Path(roundedRect: deck, cornerRadius: 3)
            context.fill(board, with: .color(Color.red.opacity(dark ? 0.30 : 0.16)))
            context.stroke(board, with: .color(.primary.opacity(0.5)), lineWidth: 1.2)
            var edge = Path(); edge.move(to: CGPoint(x: deck.minX, y: deck.minY)); edge.addLine(to: CGPoint(x: deck.minX, y: deck.maxY))
            context.stroke(edge, with: .color(.primary.opacity(0.8)), style: StrokeStyle(lineWidth: 3, lineCap: .round))
            var centre = Path(); centre.move(to: CGPoint(x: deck.minX, y: deck.midY)); centre.addLine(to: CGPoint(x: deck.maxX, y: deck.midY))
            context.stroke(centre, with: .color(.primary.opacity(0.18)), style: StrokeStyle(lineWidth: 1, dash: [4, 4]))
            let hole = boardPoint(DeckPoint(v: 39, right: 0)), hr = 3 * ppi
            context.fill(Path(ellipseIn: CGRect(x: hole.x - hr, y: hole.y - hr, width: 2 * hr, height: 2 * hr)), with: .color(.primary.opacity(0.85)))
            context.draw(caption("Front edge · 3 in high"), at: CGPoint(x: deck.minX, y: deck.maxY + 4), anchor: .topLeading)
            context.draw(caption("Back · 12 in high"), at: CGPoint(x: deck.maxX, y: deck.maxY + 4), anchor: .topTrailing)
            context.draw(caption("Thrower's left"), at: CGPoint(x: deck.minX, y: deck.minY - 4), anchor: .bottomLeading)
            // 6 in scale bar.
            let sx = deck.maxX - 6 * ppi, sy = deck.minY - 8
            var tick = Path()
            tick.move(to: CGPoint(x: sx, y: sy)); tick.addLine(to: CGPoint(x: sx + 6 * ppi, y: sy))
            tick.move(to: CGPoint(x: sx, y: sy - 3)); tick.addLine(to: CGPoint(x: sx, y: sy + 3))
            tick.move(to: CGPoint(x: sx + 6 * ppi, y: sy - 3)); tick.addLine(to: CGPoint(x: sx + 6 * ppi, y: sy + 3))
            context.stroke(tick, with: .color(.secondary), lineWidth: 1.2)
            context.draw(caption("6 in"), at: CGPoint(x: sx - 4, y: sy), anchor: .trailing)

            let shownContact = contact.map { Self.shown($0) }
            let shownRest = rest.map { Self.shown($0) }
            // The slide, first contact → end.
            if let shownContact, let shownRest {
                var slide = Path(); slide.move(to: boardPoint(shownContact.point)); slide.addLine(to: boardPoint(shownRest.point))
                context.stroke(slide, with: .color(.primary.opacity(0.25)), style: StrokeStyle(lineWidth: 4.5, lineCap: .round))
                context.stroke(slide, with: .color(slideInk), style: StrokeStyle(lineWidth: 2.6, lineCap: .round))
            }
            // Where it ended: in the hole, the bag at its true 6 in size, or an arrow when it ended beyond the view;
            // the dashed line is the miss from the hole.
            if inHole {
                for radius in [hr + 5, hr + 1] {
                    context.stroke(Path(ellipseIn: CGRect(x: hole.x - radius, y: hole.y - radius, width: 2 * radius, height: 2 * radius)),
                                   with: .color(eventColor("into_hole")), lineWidth: 2.2)
                }
                context.draw(Text("In the hole").font(.caption.weight(.semibold)).foregroundStyle(eventColor("into_hole")),
                             at: CGPoint(x: hole.x, y: hole.y - hr - 8), anchor: .bottom)
            } else if let shownRest {
                let end = boardPoint(shownRest.point)
                var vector = Path(); vector.move(to: hole); vector.addLine(to: end)
                context.stroke(vector, with: .color(.primary.opacity(0.7)), style: StrokeStyle(lineWidth: 1.2, dash: [3, 3]))
                let dx = end.x - hole.x, dy = end.y - hole.y
                let length = max(hypot(dx, dy), 0.001)
                let ux = dx / length, uy = dy / length
                if shownRest.outside {
                    let base = CGPoint(x: end.x - 11 * ux, y: end.y - 11 * uy)
                    var arrow = Path()
                    arrow.move(to: end)
                    arrow.addLine(to: CGPoint(x: base.x - 5 * uy, y: base.y + 5 * ux))
                    arrow.addLine(to: CGPoint(x: base.x + 5 * uy, y: base.y - 5 * ux))
                    arrow.closeSubpath()
                    context.fill(arrow, with: .color(Color.accentColor))
                } else {
                    let side = 6 * ppi
                    let bag = Path(roundedRect: CGRect(x: end.x - side / 2, y: end.y - side / 2, width: side, height: side), cornerRadius: side * 0.18)
                    context.fill(bag, with: .color(Color.accentColor.opacity(0.9)))
                    context.stroke(bag, with: .color(.white.opacity(0.9)), lineWidth: 1.2)
                }
                let text: String? = offBoard ? "Off the board" + (miss.map { ": \($0)" } ?? "") : miss
                if let text {
                    drawLabel(context, text, end: end, direction: CGPoint(x: ux, y: uy), outside: shownRest.outside)
                }
            }
            // First contact, labelled on the side away from the slide.
            if let shownContact {
                let p = boardPoint(shownContact.point)
                dot(context, p, radius: 5, ink: .accentColor, lineWidth: 2.2)
                let slidesRight = shownRest.map { boardPoint($0.point).x >= p.x } ?? true
                context.draw(Text("Landed").font(.caption2.weight(.semibold)),
                             at: CGPoint(x: p.x + (slidesRight ? -9 : 9), y: p.y), anchor: slidesRight ? .trailing : .leading)
            }
        }

        /// The miss label: beyond the bag, away from the hole (above or below it when the miss runs along the
        /// board); beside the arrow, inside the view, when the bag ended beyond it. Kept inside the canvas.
        private func drawLabel(_ context: GraphicsContext, _ text: String, end: CGPoint, direction u: CGPoint, outside: Bool) {
            let resolved = context.resolve(Text(text).font(.caption.weight(.semibold)).foregroundStyle(.primary))
            let measured = resolved.measure(in: CGSize(width: 400, height: 40))
            let w = measured.width + 10, h = measured.height + 4
            let gap = 3 * ppi + 6
            var centre: CGPoint
            if outside {
                centre = CGPoint(x: end.x - u.x * (14 + w / 2), y: end.y - u.y * 14 + (u.y >= 0 ? -h : h))
            } else if abs(u.y) < 0.6 {
                let below = end.y >= deck.midY
                centre = CGPoint(x: end.x, y: below ? end.y + gap + h / 2 : end.y - gap - h / 2)
            } else {
                centre = CGPoint(x: end.x + u.x * (gap + w / 2), y: end.y + u.y * (gap + h / 2))
            }
            centre.x = min(max(centre.x, w / 2 + 2), size.width - w / 2 - 2)
            centre.y = min(max(centre.y, h / 2 + 2), size.height - h / 2 - 2)
            let box = CGRect(x: centre.x - w / 2, y: centre.y - h / 2, width: w, height: h)
            context.fill(Path(roundedRect: box, cornerRadius: 4), with: .color(Color(nsColor: .textBackgroundColor).opacity(0.88)))
            context.stroke(Path(roundedRect: box, cornerRadius: 4), with: .color(.primary.opacity(0.15)), lineWidth: 0.8)
            context.draw(resolved, at: CGPoint(x: box.midX, y: box.midY))
        }

        // MARK: The bag now

        /// A ring on the bag at `frame`: along release → first contact in the top strip, then along the slide in both.
        func drawBag(_ context: GraphicsContext, frame: Int) {
            guard let contact else { return }
            func ring(_ p: CGPoint) {
                context.stroke(Path(ellipseIn: CGRect(x: p.x - 7, y: p.y - 7, width: 14, height: 14)), with: .color(.primary), lineWidth: 2)
            }
            func between(_ a: CGPoint, _ b: CGPoint, _ t: Double) -> CGPoint {
                CGPoint(x: a.x + (b.x - a.x) * CGFloat(t), y: a.y + (b.y - a.y) * CGFloat(t))
            }
            if let r0 = releaseFrame, let c0 = contactFrame, c0 > r0, frame >= r0, frame <= c0 {
                if let overview, let releaseRight {
                    let t = Double(frame - r0) / Double(c0 - r0)
                    ring(between(overview.point(0, releaseRight), overviewPoint(contact, overview), t))
                }
            } else if let c0 = contactFrame, let e0 = endFrame, e0 > c0, frame > c0, let rest {
                var t = min(1, Double(frame - c0) / Double(e0 - c0))
                // On the board, follow the measured slide (it slows down) rather than an even pace.
                if !offBoard, let v = slideProgress[min(frame, e0)], abs(rest.v - contact.v) > 1 {
                    t = min(max((v - contact.v) / (rest.v - contact.v), 0), 1)
                }
                if let overview { ring(between(overviewPoint(contact, overview), overviewPoint(rest, overview), t)) }
                ring(between(boardPoint(Self.shown(contact).point), boardPoint(Self.shown(rest).point), t))
            }
        }
    }
}

// MARK: - Front-camera replay overlay

/// Drawn over the front video: the deck outline (tracked through camera drift), the bag's path towards the
/// board up to this frame, first contact and where it ended, and which side is the thrower's left.
///
/// When the 3D flight was accepted (§5.4) its projection into the front frames is the path: solid between frames
/// where the front camera saw the bag on it (`seenFrames`, flight3d.json → detections), dashed where the path is the
/// model only (the bag hidden, out of the picture or not found). Without the 3D flight the older front tracker's
/// path is drawn (solid: it is a tracked path) and the reason the 3D flight is missing is stated.
struct FrontReplayOverlay: View {
    let document: TwoViewDocument
    let frontFrame: Int
    let size: CGSize
    /// Front frames where the bag was found on the 3D path; nil when not known (the whole path is then dashed).
    var seenFrames: Set<Int>? = nil
    /// Front-camera pose for the skeleton (front view 2D); joints below 0.3 confidence are not drawn.
    var pose: PoseDocument? = nil
    var showsSkeleton = true

    /// The path drawn and whether it is the projected 3D flight.
    private var flightPath: (points: [TwoViewDocument.PathPoint], isModel: Bool) {
        if let flight = document.flight, let path = flight.front_path, !path.isEmpty { return (path, true) }
        return (document.front_path ?? [], document.front_path_source == "flight_3d")
    }

    var body: some View {
        Canvas { context, _ in
            let rect = videoRect
            func screen(_ x: Double, _ y: Double) -> CGPoint {
                CGPoint(x: rect.minX + rect.width * x / document.frontWidth, y: rect.minY + rect.height * y / document.frontHeight)
            }
            if showsSkeleton, let pose, frontFrame >= 0, frontFrame < pose.frames.count {
                let joints = pose.frames[frontFrame].landmarks
                func point(_ name: String) -> CGPoint? {
                    guard let p = joints[name], p.confidence >= 0.3, let x = p.x, let y = p.y else { return nil }
                    return screen(x, y)
                }
                let bones = [("left_shoulder", "right_shoulder"), ("left_hip", "right_hip"), ("left_shoulder", "left_hip"),
                             ("right_shoulder", "right_hip"), ("left_shoulder", "left_elbow"), ("left_elbow", "left_wrist"),
                             ("right_shoulder", "right_elbow"), ("right_elbow", "right_wrist"), ("left_hip", "left_knee"),
                             ("left_knee", "left_ankle"), ("right_hip", "right_knee"), ("right_knee", "right_ankle")]
                var skeleton = Path()
                for (a, b) in bones {
                    if let pa = point(a), let pb = point(b) { skeleton.move(to: pa); skeleton.addLine(to: pb) }
                }
                context.stroke(skeleton, with: .color(.black.opacity(0.4)), style: StrokeStyle(lineWidth: 3.5, lineCap: .round))
                context.stroke(skeleton, with: .color(.cyan.opacity(0.9)), style: StrokeStyle(lineWidth: 1.8, lineCap: .round))
            }
            if let quad = document.corners(frontFrame: frontFrame) {
                var deck = Path(); deck.addLines(quad.map { screen($0.x, $0.y) }); deck.closeSubpath()
                context.stroke(deck, with: .color(.green.opacity(0.85)), lineWidth: 1.5)
            }
            let source = flightPath
            let path = source.points.filter { $0.frame <= frontFrame && $0.px.count == 2 }
            if path.count > 1 {
                if source.isModel {
                    // Seen segments (both ends on a frame where the bag was found) solid, model-only segments dashed.
                    var seen = Path(), model = Path()
                    for (a, b) in zip(path, path.dropFirst()) {
                        let isSeen = seenFrames.map { $0.contains(a.frame) && $0.contains(b.frame) } ?? false
                        if isSeen {
                            seen.move(to: screen(a.px[0], a.px[1])); seen.addLine(to: screen(b.px[0], b.px[1]))
                        } else {
                            model.move(to: screen(a.px[0], a.px[1])); model.addLine(to: screen(b.px[0], b.px[1]))
                        }
                    }
                    context.stroke(model, with: .color(.black.opacity(0.45)), style: StrokeStyle(lineWidth: 4, lineCap: .round, dash: [5, 5]))
                    context.stroke(model, with: .color(.white.opacity(0.9)), style: StrokeStyle(lineWidth: 2, lineCap: .round, dash: [5, 5]))
                    context.stroke(seen, with: .color(.black.opacity(0.45)), style: StrokeStyle(lineWidth: 5, lineCap: .round, lineJoin: .round))
                    context.stroke(seen, with: .color(measuredInk), style: StrokeStyle(lineWidth: 2.5, lineCap: .round, lineJoin: .round))
                } else {
                    var line = Path()
                    line.addLines(path.map { screen($0.px[0], $0.px[1]) })
                    context.stroke(line, with: .color(.black.opacity(0.45)), style: StrokeStyle(lineWidth: 5, lineCap: .round, lineJoin: .round))
                    context.stroke(line, with: .color(measuredInk), style: StrokeStyle(lineWidth: 2.5, lineCap: .round, lineJoin: .round))
                }
            }
            // The bag now, on the path, while it is in the air.
            if let now = source.points.first(where: { $0.frame == frontFrame && $0.px.count == 2 }) {
                let p = screen(now.px[0], now.px[1])
                let seenNow = !source.isModel || (seenFrames?.contains(now.frame) ?? false)
                context.stroke(Path(ellipseIn: CGRect(x: p.x - 8, y: p.y - 8, width: 16, height: 16)), with: .color(.white),
                               style: StrokeStyle(lineWidth: 2, dash: seenNow ? [] : [3, 3]))
            }
            drawLegend(context, rect: rect, isModel: source.isModel, hasPath: !source.points.isEmpty)
            let shown = (document.front_landing?.path ?? []).filter { $0.frame <= frontFrame && $0.px.count == 2 }
            let split = Self.splitAtContact(shown, contactFrame: document.front_landing?.contact?.frame)
            // The deck track's first points are the bag still in the air (tracked from before contact): drawn as flight.
            if split.air.count > 1 {
                var line = Path()
                line.addLines(split.air.map { screen($0.px[0], $0.px[1]) })
                context.stroke(line, with: .color(measuredInk), style: StrokeStyle(lineWidth: 2.5, lineCap: .round))
            }
            if split.deck.count > 1 {
                var line = Path()
                line.addLines(split.deck.map { screen($0.px[0], $0.px[1]) })
                context.stroke(line, with: .color(slideInk), style: StrokeStyle(lineWidth: 2.5, lineCap: .round))
            }
            if let contact = document.front_landing?.contact, let f = contact.frame, f <= frontFrame, let px = contact.px, px.count == 2 {
                marker(context, screen(px[0], px[1]), "First contact", eventColor("first_contact"))
            }
            if let rest = document.front_landing?.rest, let px = rest.px, px.count == 2,
               frontFrame >= (document.frames?.front_frame_count ?? 0) - Int(document.frontFPS * 0.6) {
                marker(context, screen(px[0], px[1]), document.landing?.outcome == "hole" ? "Into the hole" : "Ended",
                       eventColor(document.landing?.outcome == "hole" ? "into_hole" : "final_rest"))
            }
            let side = { (text: String) in Text(text).font(.caption2.weight(.semibold)).foregroundStyle(.white) }
            context.draw(side("← Thrower's right"), at: CGPoint(x: rect.minX + 8, y: rect.maxY - 8), anchor: .bottomLeading)
            context.draw(side("Thrower's left →"), at: CGPoint(x: rect.maxX - 8, y: rect.maxY - 8), anchor: .bottomTrailing)
        }
        .allowsHitTesting(false)
    }

    /// The deck track split at the front camera's first contact: `air` up to and including the contact point (so the
    /// two lines join), `deck` from it. Uses each point's `phase` when the engine wrote it, else the contact frame; with
    /// neither, everything is `deck` (the older drawing).
    static func splitAtContact(_ path: [TwoViewDocument.FrontPathPoint], contactFrame: Int?)
        -> (air: [TwoViewDocument.FrontPathPoint], deck: [TwoViewDocument.FrontPathPoint]) {
        func inAir(_ p: TwoViewDocument.FrontPathPoint) -> Bool? {
            if let phase = p.phase { return phase == "air" }
            return contactFrame.map { p.frame < $0 }
        }
        guard path.contains(where: { inAir($0) != nil }) else { return ([], path) }
        let air = path.filter { inAir($0) == true }
        let deck = path.filter { inAir($0) != true }
        return (deck.first.map { air + [$0] } ?? air, deck)
    }

    /// What the path is, top left: the 3D flight (solid seen / dashed model), the older tracker, or why there is none.
    private func drawLegend(_ context: GraphicsContext, rect: CGRect, isModel: Bool, hasPath: Bool) {
        var lines: [String] = []
        if isModel {
            lines.append(seenFrames == nil ? "Bag path: 3D flight (dashed: model; frames where the bag was seen not saved)"
                         : "Bag path: 3D flight · solid = bag seen here · dashed = model only")
        } else if hasPath {
            lines.append("Bag path: front tracker")
            if let flight = document.flight_3d, !flight.isAvailable { lines.append("No 3D flight: \(shortReason(flight.reason))") }
        } else if let flight = document.flight_3d, !flight.isAvailable {
            lines.append("No bag path: \(shortReason(flight.reason))")
        }
        guard !lines.isEmpty else { return }
        let text = context.resolve(Text(lines.joined(separator: "\n")).font(.system(size: 10, weight: .medium)).foregroundColor(.white))
        let measured = text.measure(in: CGSize(width: max(80, rect.width * 0.6), height: 60))
        let box = CGRect(x: rect.minX + 8, y: rect.minY + 8, width: measured.width + 12, height: measured.height + 6)
        context.fill(Path(roundedRect: box, cornerRadius: 5), with: .color(.black.opacity(0.55)))
        context.draw(text, in: box.insetBy(dx: 6, dy: 3))
    }

    private func marker(_ context: GraphicsContext, _ p: CGPoint, _ label: String, _ color: Color) {
        context.fill(Path(ellipseIn: CGRect(x: p.x - 6, y: p.y - 6, width: 12, height: 12)), with: .color(color))
        context.stroke(Path(ellipseIn: CGRect(x: p.x - 6, y: p.y - 6, width: 12, height: 12)), with: .color(.white), lineWidth: 1.5)
        let text = context.resolve(Text(label).font(.system(size: 11, weight: .semibold)).foregroundColor(.white))
        let measured = text.measure(in: CGSize(width: 200, height: 30))
        let box = CGRect(x: p.x + 9, y: p.y - measured.height - 8, width: measured.width + 10, height: measured.height + 4)
        context.fill(Path(roundedRect: box, cornerRadius: 4), with: .color(color.opacity(0.9)))
        context.draw(text, at: CGPoint(x: box.midX, y: box.midY))
    }

    private var videoRect: CGRect {
        let scale = min(size.width / document.frontWidth, size.height / document.frontHeight)
        let fitted = CGSize(width: document.frontWidth * scale, height: document.frontHeight * scale)
        return CGRect(x: (size.width - fitted.width) / 2, y: (size.height - fitted.height) / 2, width: fitted.width, height: fitted.height)
    }
}

/// The first sentence of an engine reason, for a one-line note ("not measured." when there is none).
func shortReason(_ reason: String?) -> String {
    guard let reason, !reason.isEmpty else { return "not measured." }
    if let end = reason.firstIndex(of: ".") { return String(reason[...end]) }
    return reason
}

/// The front clip and its analysis, handed to the replay.
struct FrontReplaySource: Equatable {
    var url: URL
    var document: TwoViewDocument
    /// Front frames where the bag was found on the 3D path (flight3d.json → detections); nil when not saved.
    var seenFrames: Set<Int>? = nil
    /// The front camera's Sports2D pose (front_pose_raw.json), drawn as a skeleton over the front video.
    var pose: PoseDocument? = nil

    static func == (a: FrontReplaySource, b: FrontReplaySource) -> Bool {
        a.url == b.url && a.document == b.document && a.seenFrames == b.seenFrames && (a.pose == nil) == (b.pose == nil)
    }
}

/// flight3d.json read for what two_view.json leaves out: the front frames where the bag was found on the 3D path.
enum Flight3DFile {
    static func seenFrames(_ analysisURL: URL?) -> Set<Int>? {
        struct Detection: Decodable { var frame: Int }
        struct File: Decodable { var status: String?; var detections: [Detection]? }
        guard let analysisURL, let data = try? Data(contentsOf: analysisURL.appendingPathComponent("flight3d.json")),
              let file = try? JSONDecoder().decode(File.self, from: data),
              file.status == "measured" || file.status == "estimated", let detections = file.detections else { return nil }
        return Set(detections.map(\.frame))
    }
}

// MARK: - Athlete: left/right and distance

/// Every throw's direction and distance from the front camera: where the misses go, how steady the aim
/// is, and the frontal-plane body measures that go with it (dot strips, scored vs missed).
struct DirectionSummaryCard: View {
    let rows: [SummaryThrowRow]

    var body: some View {
        Card("Left/right and distance", symbol: "arrow.left.and.right.circle",
             subtitle: "From the front camera behind the board. Each dot is one throw; filled = scored (board or hole), open = miss.") {
            Text(sentence).font(.title3.weight(.semibold)).fixedSize(horizontal: false, vertical: true)
            Grid(alignment: .leading, horizontalSpacing: Space.l, verticalSpacing: Space.m) {
                strip("Ended left/right of the hole", unit: "in", values: rows.map { ($0.leftRight, $0.score) },
                      domain: -30...30, lowLabel: "left", highLabel: "right")
                strip("Ended short/long of the hole", unit: "in", values: rows.map { ($0.shortLong, $0.score) },
                      domain: -48...24, lowLabel: "short", highLabel: "long")
                strip("Sideways aim (heading)", unit: "°", values: rows.map { ($0.heading, $0.score) },
                      domain: -5...5, lowLabel: "left", highLabel: "right")
                strip("Hand across body at release", unit: "shoulder widths",
                      values: rows.map { ($0.frontal["arm_across_body_sw"], $0.score) },
                      domain: -1...1, lowLabel: "out", highLabel: "across")
                strip("Trunk side lean at release", unit: "°",
                      values: rows.map { ($0.frontal["trunk_side_lean_deg"], $0.score) },
                      domain: -30...30, lowLabel: "away", highLabel: "towards arm")
            }
            Text("A dot strip shows the spread; the coach-focus card above names a difference between scored throws and misses only when it passes the evidence rules (at least 5 throws in each group, a large effect, and more than the measurement noise).")
                .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }
    }

    /// "Misses mostly ended short (9 of 12) and left (8 of 12); the aim varied ± 1.2° (about ± 6 in at the hole)."
    private var sentence: String {
        let misses = rows.filter { $0.score != .throughHole && ($0.leftRight != nil || $0.shortLong != nil) }
        guard !misses.isEmpty else { return "Every measured throw went in the hole." }
        var parts: [String] = []
        let lr = misses.compactMap(\.leftRight).filter { abs($0) >= 3 }
        let left = lr.filter { $0 < 0 }.count, right = lr.filter { $0 > 0 }.count
        let sl = misses.compactMap(\.shortLong).filter { abs($0) >= 3 }
        let short = sl.filter { $0 < 0 }.count, long = sl.filter { $0 > 0 }.count
        if short + long > 0 {
            parts.append(short >= long ? "short (\(short) of \(misses.count))" : "long (\(long) of \(misses.count))")
        }
        if left + right > 0 {
            parts.append(left >= right ? "left (\(left) of \(misses.count))" : "right (\(right) of \(misses.count))")
        }
        var text = parts.isEmpty ? "Throws that did not go in ended close to the hole line"
            : "Throws that did not go in mostly ended " + parts.joined(separator: " and ")
        if let aim = MedianSD.of(rows.compactMap(\.heading)), let sd = aim.sd, aim.n >= 3 {
            let atHole = tan(sd * .pi / 180) * 7.6 / 0.0254   // ~7.6 m from release to the hole
            text += "; the aim varied ± \(number(sd, digits: 1))° (about ± \(number(atHole, digits: 0)) in at the hole)"
        }
        return text + "."
    }

    @ViewBuilder
    private func strip(_ title: String, unit: String, values: [(Double?, ScoreCategory?)], domain: ClosedRange<Double>,
                       lowLabel: String, highLabel: String) -> some View {
        let points = values.compactMap { value, score in value.map { ($0, score) } }
        GridRow {
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.callout.weight(.semibold))
                if let summary = MedianSD.of(points.map(\.0)) {
                    Text("median \(number(summary.median, digits: unit == "shoulder widths" ? 2 : 1))\(unit == "°" ? "°" : " " + unit)"
                         + (summary.sd.map { " · SD \(number($0, digits: unit == "shoulder widths" ? 2 : 1))" } ?? "")
                         + " · \(summary.n) throws")
                        .font(.caption).foregroundStyle(.secondary).monospacedDigit()
                } else {
                    Text("not measured").font(.caption).foregroundStyle(.secondary)
                }
            }
            .frame(width: 230, alignment: .leading)
            DotStrip(points: points, domain: domain, lowLabel: lowLabel, highLabel: highLabel)
                .frame(height: 34)
                .accessibilityLabel(title)
        }
    }
}

/// One measure across throws: a zero line, the domain ends labelled with their meaning, one dot per throw.
struct DotStrip: View {
    let points: [(Double, ScoreCategory?)]
    let domain: ClosedRange<Double>
    let lowLabel: String
    let highLabel: String

    var body: some View {
        Canvas { context, size in
            let span = domain.upperBound - domain.lowerBound
            func x(_ v: Double) -> CGFloat { CGFloat((min(max(v, domain.lowerBound), domain.upperBound) - domain.lowerBound) / span) * (size.width - 12) + 6 }
            let midY = size.height * 0.4
            var axis = Path(); axis.move(to: CGPoint(x: 6, y: midY)); axis.addLine(to: CGPoint(x: size.width - 6, y: midY))
            context.stroke(axis, with: .color(.primary.opacity(0.18)), lineWidth: 1)
            if domain.contains(0) {
                var zero = Path(); zero.move(to: CGPoint(x: x(0), y: midY - 9)); zero.addLine(to: CGPoint(x: x(0), y: midY + 9))
                context.stroke(zero, with: .color(.primary.opacity(0.45)), lineWidth: 1.2)
            }
            for (index, point) in points.enumerated() {
                let jitter = CGFloat((index % 3) - 1) * 3
                let p = CGPoint(x: x(point.0), y: midY + jitter)
                let rect = CGRect(x: p.x - 4, y: p.y - 4, width: 8, height: 8)
                let scored = point.1 == .onBoard || point.1 == .throughHole
                if scored {
                    context.fill(Path(ellipseIn: rect), with: .color(scoredInk.opacity(0.85)))
                } else {
                    context.stroke(Path(ellipseIn: rect), with: .color(point.1 == nil ? Color.gray : missInk), lineWidth: 1.6)
                }
            }
            let caption = { (text: String) in Text(text).font(.caption2).foregroundStyle(.secondary) }
            context.draw(caption("← \(lowLabel)"), at: CGPoint(x: 6, y: size.height), anchor: .bottomLeading)
            context.draw(caption("\(highLabel) →"), at: CGPoint(x: size.width - 6, y: size.height), anchor: .bottomTrailing)
        }
    }
}


/// The front camera's frontal-plane series around release (front view 2D): where the hand was sideways relative to the
/// throwing shoulder, and the trunk's side lean. Gaps are frames the pose model did not see clearly; they are not
/// filled. Time 0 is the side camera's release.
struct FrontBodyChart: View {
    let series: TwoViewDocument.FrontKinematics

    private struct Sample: Identifiable { let id: Int; let t: Double; let value: Double; let run: Int }

    private func samples(_ values: [Double?]?) -> [Sample] {
        guard let t = series.t_s, let values else { return [] }
        var out: [Sample] = [], run = 0, wasGap = true
        for (i, value) in values.enumerated() where i < t.count {
            guard let value else { wasGap = true; continue }
            if wasGap { run += 1; wasGap = false }
            out.append(Sample(id: i, t: t[i], value: value, run: run))
        }
        return out
    }

    var body: some View {
        VStack(alignment: .leading, spacing: Space.s) {
            Text("Body from the front over the throw").font(.headline)
            HStack(alignment: .top, spacing: Space.m) {
                chart(samples(series.wrist_across_sw), title: "Hand across the body", unit: "shoulder widths",
                      sign: "+ towards the midline")
                chart(samples(series.trunk_lean_deg), title: "Trunk side lean", unit: "°", sign: "+ towards the throwing arm")
            }
            Text("Front view 2D (frontal plane image). Time from release (s); dashed line: start of the forward swing. Gaps: frames where the joints were not seen clearly.")
                .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }
    }

    private func chart(_ points: [Sample], title: String, unit: String, sign: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("\(title) (\(unit))").font(.caption.weight(.semibold))
            Chart {
                ForEach(points) { p in
                    LineMark(x: .value("Time from release (s)", p.t), y: .value(unit, p.value), series: .value("run", p.run))
                        .foregroundStyle(measuredInk).interpolationMethod(.linear)
                }
                RuleMark(x: .value("Release", 0.0)).foregroundStyle(eventColor("release"))
                    .annotation(position: .top, alignment: .leading) { Text("Release").font(.caption2) }
                if let start = series.forward_swing_start_s {
                    RuleMark(x: .value("Forward swing", start)).foregroundStyle(.secondary)
                        .lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 3]))
                }
            }
            .chartXAxisLabel("Time from release (s)")
            .frame(minWidth: 220, minHeight: 130)
            Text(sign).font(.caption2).foregroundStyle(.secondary)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(title), \(points.count) frames, front view")
    }
}
