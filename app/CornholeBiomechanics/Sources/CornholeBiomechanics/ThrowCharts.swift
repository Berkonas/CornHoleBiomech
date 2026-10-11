import Charts
import SwiftUI

// Throw report plots (spec §3.5). Every time axis is "Time from release (ms)"; clicking a time
// chart seeks the replay to that moment.

let timeAxisTitle = "Time from release (ms)"

/// Event frames of one throw, turned into milliseconds from release.
struct EventTimeline {
    let fps: Double
    let frames: [String: Int]

    init(fps: Double, frames: [String: Int]) {
        self.fps = fps > 0 ? fps : 30
        self.frames = frames
    }

    var release: Int? { frames["release"] }
    func ms(_ frame: Int) -> Double { 1000 * Double(frame - (release ?? 0)) / fps }
    func frame(ms: Double) -> Int { (release ?? 0) + Int((ms / 1000 * fps).rounded()) }

    /// The same time axis for every throw: 1 s before release … 250 ms after, reaching further back only when
    /// the backswing top came earlier than 850 ms before release (so throws compare at a glance).
    var window: ClosedRange<Double> {
        let start = frames["peak_backswing"].map { ms($0) - 150 } ?? -1000
        return min(start, -1000)...250
    }

    /// Markers drawn on the body charts.
    static let bodyEvents: [(key: String, label: String)] = [
        ("peak_backswing", "Top of backswing"), ("peak_wrist_speed", "Peak wrist speed"), ("release", "Release")]
}

/// One sample of a time series.
struct TimePoint: Identifiable, Equatable {
    var id: String { "\(series)-\(ms)" }
    let series: String
    let ms: Double
    let value: Double
}

/// Elbow angle and trunk inclination from kinematics.csv, with time taken from its `time_seconds` column.
struct JointAngleSeries {
    static let columns = [("elbow_angle_deg", "Elbow angle"), ("trunk_inclination_deg", "Trunk inclination")]
    let points: [TimePoint]

    init(rows: [[String: String]], releaseFrame: Int?) {
        guard let releaseFrame,
              let releaseRow = rows.first(where: { $0["frame"].flatMap(Int.init) == releaseFrame }) ?? rows[safe: releaseFrame],
              let releaseTime = releaseRow["time_seconds"].flatMap(Double.init) else { points = []; return }
        var points: [TimePoint] = []
        for (column, series) in Self.columns {
            for row in rows {
                guard let t = row["time_seconds"].flatMap(Double.init),
                      let v = row[column].flatMap(Double.init), v.isFinite else { continue }
                points.append(TimePoint(series: series, ms: 1000 * (t - releaseTime), value: v))
            }
        }
        self.points = points
    }
}

// MARK: - Shared chart pieces

/// Click anywhere on a time chart to seek the replay to that moment.
private struct SeekOnClick: ViewModifier {
    let timeline: EventTimeline
    let seek: (Int) -> Void
    func body(content: Content) -> some View {
        content.chartOverlay { proxy in
            GeometryReader { geometry in
                Rectangle().fill(.clear).contentShape(Rectangle()).onTapGesture { location in
                    guard let plot = proxy.plotFrame else { return }
                    if let ms: Double = proxy.value(atX: location.x - geometry[plot].origin.x) {
                        seek(timeline.frame(ms: ms))
                    }
                }
            }
        }
    }
}

extension View {
    fileprivate func seekOnClick(_ timeline: EventTimeline, _ seek: @escaping (Int) -> Void) -> some View {
        modifier(SeekOnClick(timeline: timeline, seek: seek))
    }
}

/// Dashed vertical event markers with labels, plus the replay's current moment.
@ChartContentBuilder
private func eventRules(_ timeline: EventTimeline, keys: [(key: String, label: String)], now: Int) -> some ChartContent {
    ForEach(keys, id: \.key) { item in
        if let frame = timeline.frames[item.key] {
            RuleMark(x: .value("Event", timeline.ms(frame)))
                .foregroundStyle(eventColor(item.key).opacity(0.8))
                .lineStyle(StrokeStyle(lineWidth: 1.5, dash: item.key == "release" ? [] : [4, 3]))
                // Release labels to the right of its line, the others to the left, so neighbours never overlap.
                .annotation(position: .top, alignment: item.key == "release" ? .leading : .trailing) {
                    Text(item.label).font(.caption2).foregroundStyle(.secondary)
                }
        }
    }
    RuleMark(x: .value("Now", timeline.ms(now)))
        .foregroundStyle(Color.primary.opacity(0.35)).lineStyle(StrokeStyle(lineWidth: 1))
}

struct ChartLegendItem: View {
    let color: Color
    let label: String
    var dashed = false
    var dot = false
    var body: some View {
        HStack(spacing: Space.xs) {
            if dot {
                Circle().fill(color).frame(width: 7, height: 7)
            } else {
                Path { p in p.move(to: CGPoint(x: 0, y: 1.5)); p.addLine(to: CGPoint(x: 18, y: 1.5)) }
                    .stroke(color, style: StrokeStyle(lineWidth: 2.5, dash: dashed ? [4, 3] : []))
                    .frame(width: 18, height: 3)
            }
            Text(label)
        }
        .font(.caption).foregroundStyle(.secondary)
    }
}

// MARK: - Joint angles

/// Elbow angle and trunk inclination through the throw (degrees), with event markers.
struct JointAngleChart: View {
    let series: JointAngleSeries
    let timeline: EventTimeline
    let currentFrame: Int
    let seek: (Int) -> Void

    static let elbowInk = athleteInk

    /// One angle scale for every throw: −20…190° (elbow straight = 180°, trunk upright = 0°), widened in 10°
    /// steps only when a throw goes beyond it, so curves from different throws compare directly.
    static func domain(_ values: [Double]) -> ClosedRange<Double> {
        let finite = values.filter(\.isFinite)
        let lo = min(-20, ((finite.min() ?? 0) / 10).rounded(.down) * 10)
        let hi = max(190, ((finite.max() ?? 180) / 10).rounded(.up) * 10)
        return lo...hi
    }
    static let trunkInk = Color.indigo

    var body: some View {
        let window = timeline.window
        let points = series.points.filter { window.contains($0.ms) }
        VStack(alignment: .leading, spacing: Space.s) {
            Chart {
                ForEach(points) { point in
                    LineMark(x: .value(timeAxisTitle, point.ms), y: .value("Angle (°)", point.value),
                             series: .value("Series", point.series))
                        .foregroundStyle(by: .value("Series", point.series))
                        .lineStyle(StrokeStyle(lineWidth: 2, dash: point.series == "Trunk inclination" ? [5, 3] : []))
                        .interpolationMethod(.monotone)
                }
                eventRules(timeline, keys: EventTimeline.bodyEvents, now: currentFrame)
            }
            .chartForegroundStyleScale(["Elbow angle": Self.elbowInk, "Trunk inclination": Self.trunkInk])
            .chartLegend(.hidden)
            .chartXScale(domain: window)
            .chartXAxisLabel(timeAxisTitle, alignment: .center)
            .chartYAxisLabel("Angle (°)", position: .leading)
            .chartYAxis { AxisMarks(position: .leading) }
            .chartYScale(domain: Self.domain(points.map(\.value)))
            .seekOnClick(timeline, seek)
            .frame(height: 220)
            .padding(.top, Space.l)   // room for the event labels above the plot
            .accessibilityLabel("Elbow angle and trunk inclination in degrees against time from release")
            HStack(spacing: Space.l) {
                ChartLegendItem(color: Self.elbowInk, label: "Elbow angle (180° = straight)")
                ChartLegendItem(color: Self.trunkInk, label: "Trunk inclination (0° = upright)", dashed: true)
            }
        }
    }
}

// MARK: - Wrist speed

/// Wrist speed through the throw, time relative to release, with the peak and release marked.
/// Clicking the chart seeks the replay to that moment.
struct WristSpeedChart: View {
    let speed: [Double?]
    let fps: Double
    let events: [String: Int?]
    let currentFrame: Int
    let seek: (Int) -> Void

    private var timeline: EventTimeline { EventTimeline(fps: fps, frames: events.compactMapValues { $0 }) }

    /// One speed scale for every throw: 0 to at least 12 arm lengths/s, rounded up to the next 2 when a throw is faster.
    static func domain(_ values: [Double]) -> ClosedRange<Double> {
        let top = values.filter(\.isFinite).max() ?? 0
        return 0...max(12, (top * 1.05 / 2).rounded(.up) * 2)
    }

    private var samples: [TimePoint] {
        let window = timeline.window
        return speed.enumerated().compactMap { frame, value in
            guard let value, value.isFinite else { return nil }
            let ms = timeline.ms(frame)
            return window.contains(ms) ? TimePoint(series: "Wrist speed", ms: ms, value: value) : nil
        }
    }

    var body: some View {
        let samples = samples
        let peak = timeline.frames["peak_wrist_speed"].flatMap { frame in speed[safe: frame] ?? nil }.map { (timeline.ms(timeline.frames["peak_wrist_speed"]!), $0) }
        VStack(alignment: .leading, spacing: Space.s) {
            Chart {
                ForEach(samples) { sample in
                    LineMark(x: .value(timeAxisTitle, sample.ms), y: .value("Wrist speed (arm lengths/s)", sample.value))
                        .foregroundStyle(athleteInk).interpolationMethod(.monotone)
                }
                if let peak {
                    PointMark(x: .value(timeAxisTitle, peak.0), y: .value("Wrist speed (arm lengths/s)", peak.1))
                        .foregroundStyle(eventColor("peak_wrist_speed")).symbolSize(60)
                }
                eventRules(timeline, keys: EventTimeline.bodyEvents, now: currentFrame)
            }
            .chartXScale(domain: timeline.window)
            .chartYScale(domain: Self.domain(samples.map(\.value)))
            .chartXAxisLabel(timeAxisTitle, alignment: .center)
            .chartYAxisLabel("Wrist speed (arm lengths/s)", position: .leading)
            .chartYAxis { AxisMarks(position: .leading) }
            .seekOnClick(timeline, seek)
            .frame(height: 220)
            .padding(.top, Space.l)   // room for the event labels above the plot
            .accessibilityLabel("Wrist speed in arm lengths per second against time from release")
            Text("Arm lengths per second, so throws filmed at different distances compare.")
                .font(.caption).foregroundStyle(.secondary)
        }
    }
}

// MARK: - Bag flight

/// Scale used to show the flight in metres: the analysis's own calibration first, then the board's
/// throw-plane scale, then the scale from the bag's fall (gravity).
struct FlightScale: Equatable {
    let pixelsPerMeter: Double
    let source: String

    static func load(results url: URL) -> FlightScale? {
        guard let data = try? Data(contentsOf: url),
              let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
        func valid(_ value: Any?) -> Double? {
            guard let v = value as? Double, v.isFinite, v > 0 else { return nil }
            return v
        }
        let bag = root["bag"] as? [String: Any]
        let launch = bag?["launch"] as? [String: Any]
        let units = launch?["physical_units"] as? [String: Any]
        if let calibration = units?["calibration"] as? [String: Any], calibration["valid"] as? Bool != false,
           let ppm = valid(calibration["pixels_per_meter"]) {
            return FlightScale(pixelsPerMeter: ppm, source: sourceLabel(calibration["source"] as? String ?? calibration["plane"] as? String))
        }
        if let scale = root["scale"] as? [String: Any], scale["status"] as? String == "measured", let ppm = valid(scale["pixels_per_meter"]) {
            return FlightScale(pixelsPerMeter: ppm, source: "board")
        }
        if let flight = root["flight"] as? [String: Any], let gravity = flight["gravity_scale"] as? [String: Any],
           let ppm = valid(gravity["pixels_per_meter"]) {
            return FlightScale(pixelsPerMeter: ppm, source: "bag's fall")
        }
        return nil
    }

    private static func sourceLabel(_ raw: String?) -> String {
        switch raw {
        case "reviewed_flight_gravity_fit", "bag_flight_plane_gravity": "bag's fall"
        case "regulation_board_pnp", "board_throw_plane": "board"
        case .some(let text) where !text.isEmpty: "measured length"
        default: "calibration"
        }
    }
}

/// The measured flight and its drag-free fit, side view, x forward and y up from the release point.
struct FlightChartData: Equatable {
    struct Point: Identifiable, Equatable { let id: Int; let x: Double; let y: Double }
    let measured: [Point]
    let model: [Point]
    /// Board side profile (front foot → front top → back top → back foot) and hole centre; metres only.
    let board: [Point]
    let hole: Point?
    let metres: Bool
    /// y is height above the floor (true) or rise above release (false).
    let heightAboveFloor: Bool
    /// Where the bag first touched down, its slide on the board, and where it ended (tracked on the board).
    var landing: Point? = nil
    var slide: [Point] = []
    var end: Point? = nil
    /// "fell_in_hole", "rest", … (board phase), or nil when the end was not tracked.
    var endKind: String? = nil

    var unit: String { metres ? "m" : "px" }

    private var everything: [Point] { measured + model + board + slide + [landing, end].compactMap { $0 } }
    /// In metres the axes are the same for every throw (release to just past the back of the board, floor to
    /// 2.5 m), widened only when a throw goes beyond; in pixels they fit this throw.
    var xDomain: ClosedRange<Double> {
        let fitted = Self.domain(everything.map(\.x) + [0])
        guard metres else { return fitted }
        let back = board.map(\.x).max() ?? 7.5
        return min(fitted.lowerBound, 0)...max(fitted.upperBound, ((back + 0.3) * 2).rounded(.up) / 2)
    }
    var yDomain: ClosedRange<Double> {
        let fitted = Self.domain(everything.map(\.y) + [0])
        guard metres else { return fitted }
        return min(fitted.lowerBound, 0)...max(fitted.upperBound, 2.5)
    }
    var endLabel: String { endKind == "fell_in_hole" ? "Into the hole" : endKind == "rest" ? "Stopped" : "Last seen" }
    private static func domain(_ values: [Double]) -> ClosedRange<Double> {
        let finite = values.filter(\.isFinite)
        guard let lo = finite.min(), let hi = finite.max(), hi > lo else { return 0...1 }
        let pad = 0.05 * (hi - lo)
        return (lo < 0 ? lo - pad : 0)...(hi + pad)
    }
    var xTitle: String { "Forward from release (\(unit))" }
    var yTitle: String { heightAboveFloor ? "Height above floor (m)" : "Rise above release (\(unit))" }

    static func make(replay: ReplayDocument, scale: FlightScale?, releaseHeight: Double?, boardDistance: Double?,
                     board geometry: BoardGeometry = .regulation) -> FlightChartData? {
        // Release → first contact only, anchored at the release event, from one series throughout.
        guard let release = replay.events["release"] else { return nil }
        let contact = replay.events["first_contact"]?.frame
        func inFlight(_ p: ReplayDocument.Point) -> Bool { p.frame >= release.frame && contact.map { p.frame <= $0 } ?? true }
        let series = replay.filtered.isEmpty ? replay.measured : replay.filtered
        let path = series.filter(inFlight)
        guard let start = path.first, let last = path.last, path.count >= 2 else { return nil }
        let first = start.frame == release.frame ? start
            : release.position.map { ReplayDocument.Point(frame: release.frame, x: $0.x, y: $0.y) } ?? start
        let sign: Double = last.x >= first.x ? 1 : -1
        let ppm = scale?.pixelsPerMeter
        let lift = ppm != nil ? (releaseHeight ?? 0) : 0
        func convert(_ p: ReplayDocument.Point) -> Point {
            let dx = sign * (p.x - first.x), dy = first.y - p.y
            guard let ppm else { return Point(id: p.frame, x: dx, y: dy) }
            return Point(id: p.frame, x: dx / ppm, y: dy / ppm + lift)
        }
        var board: [Point] = []
        var hole: Point?
        if ppm != nil, releaseHeight != nil, let d = boardDistance, d > 0 {
            let run = geometry.length * cos(geometry.angle)
            board = [Point(id: 0, x: d, y: 0), Point(id: 1, x: d, y: geometry.frontHeight),
                     Point(id: 2, x: d + run, y: geometry.backHeight), Point(id: 3, x: d + run, y: 0)]
            hole = Point(id: 0, x: d + geometry.holeAlong * cos(geometry.angle),
                         y: geometry.frontHeight + geometry.holeAlong * sin(geometry.angle))
        }
        // Touchdown, slide and end, in the same coordinates as the flight (release-frame pixels → chart).
        func eventPoint(_ key: String) -> Point? {
            guard let event = replay.events[key], let position = event.position else { return nil }
            return convert(ReplayDocument.Point(frame: event.frame, x: position.x, y: position.y))
        }
        let endKey = replay.events["into_hole"] != nil ? "into_hole" : replay.events["final_rest"]?.position != nil ? "final_rest" : nil
        var result = FlightChartData(measured: path.map(convert), model: replay.model.filter(inFlight).map(convert),
                                     board: board, hole: hole, metres: ppm != nil, heightAboveFloor: ppm != nil && releaseHeight != nil)
        result.landing = eventPoint("first_contact")
        result.slide = replay.after_contact.map(convert)
        if let endKey {
            result.end = eventPoint(endKey)
            result.endKind = endKey == "into_hole" ? "fell_in_hole" : "rest"
        } else if let last = replay.after_contact.last {
            result.end = convert(last)
        }
        return result
    }
}

/// Side view of the bag's flight: measured points, the dashed drag-free fit, and the board.
struct FlightChart: View {
    let data: FlightChartData
    var scaleSource: String?
    var distanceNote: String?

    var body: some View {
        VStack(alignment: .leading, spacing: Space.s) {
            Chart {
                ForEach(data.measured) { p in
                    PointMark(x: .value(data.xTitle, p.x), y: .value(data.yTitle, p.y))
                        .foregroundStyle(measuredInk.opacity(0.55)).symbolSize(9)
                }
                // The fit is drawn over the points so the dashed reference stays visible.
                ForEach(data.model) { p in
                    LineMark(x: .value(data.xTitle, p.x), y: .value(data.yTitle, p.y), series: .value("Series", "Drag-free fit"))
                        .foregroundStyle(Color.primary.opacity(0.75))
                        .lineStyle(StrokeStyle(lineWidth: 1.5, dash: [5, 4]))
                }
                ForEach(data.board) { p in
                    LineMark(x: .value(data.xTitle, p.x), y: .value(data.yTitle, p.y), series: .value("Series", "Board"))
                        .foregroundStyle(Color.primary.opacity(0.7)).lineStyle(StrokeStyle(lineWidth: 2))
                }
                if let hole = data.hole {
                    PointMark(x: .value(data.xTitle, hole.x), y: .value(data.yTitle, hole.y))
                        .symbol(.circle).symbolSize(50).foregroundStyle(Color.primary)
                        .annotation(position: .top) { Text("Hole").font(.caption2).foregroundStyle(.secondary) }
                }
                if data.heightAboveFloor {
                    RuleMark(y: .value(data.yTitle, 0)).foregroundStyle(Color.secondary.opacity(0.5))
                }
                ForEach(data.slide) { p in
                    LineMark(x: .value(data.xTitle, p.x), y: .value(data.yTitle, p.y), series: .value("Series", "Slide"))
                        .foregroundStyle(slideInk).lineStyle(StrokeStyle(lineWidth: 3, lineCap: .round))
                }
                if let landing = data.landing {
                    PointMark(x: .value(data.xTitle, landing.x), y: .value(data.yTitle, landing.y))
                        .symbol(.circle).symbolSize(90).foregroundStyle(eventColor("first_contact"))
                        .annotation(position: .bottom, spacing: 4) { Text("Landed").font(.caption2.weight(.semibold)) }
                }
                if let end = data.end {
                    PointMark(x: .value(data.xTitle, end.x), y: .value(data.yTitle, end.y))
                        .symbol(data.endKind == "fell_in_hole" ? BasicChartSymbolShape.circle : BasicChartSymbolShape.square).symbolSize(110)
                        .foregroundStyle(eventColor(data.endKind == "fell_in_hole" ? "into_hole" : "final_rest"))
                        .annotation(position: .top, spacing: 4) { Text(data.endLabel).font(.caption2.weight(.semibold)) }
                }
            }
            .chartXAxisLabel(data.xTitle, alignment: .center)
            .chartYAxisLabel(data.yTitle, position: .leading)
            .chartYAxis { AxisMarks(position: .leading) }
            .chartXScale(domain: data.xDomain)
            .chartYScale(domain: data.yDomain)
            .frame(height: 220)
            .accessibilityLabel("Bag flight side view, \(data.measured.count) measured points")
            HStack(spacing: Space.l) {
                ChartLegendItem(color: measuredInk, label: "Measured bag, release → first contact", dot: true)
                if data.landing != nil || data.end != nil { ChartLegendItem(color: slideInk, label: "Landing → slide → end") }
                if !data.model.isEmpty { ChartLegendItem(color: .primary.opacity(0.75), label: "Drag-free fit", dashed: true) }
                if !data.board.isEmpty { ChartLegendItem(color: .primary.opacity(0.7), label: "Board") }
            }
            Text(caption).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }
    }

    private var caption: String {
        var parts: [String] = []
        if data.metres {
            parts.append("Metres from the \(scaleSource ?? "calibrated") scale.")
        } else {
            parts.append("Video pixels: this throw has no metric scale yet.")
        }
        if let distanceNote, !data.board.isEmpty { parts.append(distanceNote) }
        return parts.joined(separator: " ")
    }
}

// MARK: - Timing strip

/// Backswing → peak wrist speed → release → first contact on one time axis (ms).
struct TimingStrip: View {
    let timeline: EventTimeline
    let currentFrame: Int
    let seek: (Int) -> Void

    static let events: [(key: String, label: String)] = [
        ("peak_backswing", "Top of backswing"), ("peak_wrist_speed", "Peak wrist speed"),
        ("release", "Release"), ("apex", "Apex"), ("first_contact", "First contact")]

    private struct Marker: Identifiable { let id: String; let label: String; let ms: Double; let row: Int }

    private var markers: [Marker] {
        Self.events.enumerated().compactMap { index, event in
            timeline.frames[event.key].map { Marker(id: event.key, label: event.label, ms: timeline.ms($0), row: index % 2) }
        }
    }

    /// The same time axis for every throw (−1 s … +1 s around release), widened only when an event lies beyond it,
    /// with room for the outer labels.
    static func domain(_ values: [Double]) -> ClosedRange<Double> {
        guard let lo = values.min(), let hi = values.max() else { return -1000...1000 }
        return min(-1000, lo - 120)...max(1000, hi + 120)
    }

    var body: some View {
        let markers = markers
        VStack(alignment: .leading, spacing: Space.s) {
            if markers.count < 2 {
                Text("Not enough events were found to show the timing.").font(.callout).foregroundStyle(.secondary)
            } else {
                Chart {
                    if let lo = markers.map(\.ms).min(), let hi = markers.map(\.ms).max() {
                        RuleMark(xStart: .value(timeAxisTitle, lo), xEnd: .value(timeAxisTitle, hi), y: .value("Row", 0))
                            .foregroundStyle(Color.secondary.opacity(0.4)).lineStyle(StrokeStyle(lineWidth: 3, lineCap: .round))
                    }
                    ForEach(markers) { marker in
                        PointMark(x: .value(timeAxisTitle, marker.ms), y: .value("Row", 0))
                            .foregroundStyle(eventColor(marker.id)).symbolSize(90)
                            .annotation(position: marker.row == 0 ? .top : .bottom, spacing: 6) {
                                VStack(spacing: 1) {
                                    Text(marker.label).font(.caption.weight(.medium))
                                    Text(marker.id == "release" ? "0 ms" : "\(marker.ms > 0 ? "+" : "−")\(number(abs(marker.ms), digits: 0)) ms")
                                        .font(.caption2.monospacedDigit()).foregroundStyle(.secondary)
                                }
                                .fixedSize()
                            }
                    }
                    RuleMark(x: .value("Now", timeline.ms(currentFrame)))
                        .foregroundStyle(Color.primary.opacity(0.35)).lineStyle(StrokeStyle(lineWidth: 1))
                }
                .chartYAxis(.hidden)
                .chartYScale(domain: -1...1)
                .chartXScale(domain: Self.domain(markers.map(\.ms)))
                .chartXAxis { AxisMarks(preset: .aligned, values: .automatic(desiredCount: 5)) }
                .chartXAxisLabel(timeAxisTitle, alignment: .center)
                .seekOnClick(timeline, seek)
                .frame(height: 150)
                .accessibilityLabel("Event timing: " + markers.map { "\($0.label) \(number($0.ms, digits: 0)) milliseconds" }.joined(separator: ", "))
            }
        }
    }
}

// MARK: - Plot grid

/// Four plot cards: 2-up at 900 pt and wider, stacked below.
struct ThrowPlots<A: View, B: View, C: View, D: View>: View {
    let angles: A, speed: B, flight: C, timing: D

    init(@ViewBuilder angles: () -> A, @ViewBuilder speed: () -> B, @ViewBuilder flight: () -> C, @ViewBuilder timing: () -> D) {
        self.angles = angles(); self.speed = speed(); self.flight = flight(); self.timing = timing()
    }

    var body: some View {
        ViewThatFits(in: .horizontal) {
            Grid(horizontalSpacing: Space.xl, verticalSpacing: Space.xl) {
                GridRow(alignment: .top) { card("Joint angles", "angle", angles); card("Wrist speed", "speedometer", speed) }
                GridRow(alignment: .top) { card("Bag flight", "point.topleft.down.to.point.bottomright.curvepath", flight); card("Timing", "timeline.selection", timing) }
            }
            .frame(minWidth: 900)
            VStack(alignment: .leading, spacing: Space.xl) {
                card("Joint angles", "angle", angles)
                card("Wrist speed", "speedometer", speed)
                card("Bag flight", "point.topleft.down.to.point.bottomright.curvepath", flight)
                card("Timing", "timeline.selection", timing)
            }
        }
    }

    private func card(_ title: String, _ symbol: String, _ content: some View) -> some View {
        Card(title, symbol: symbol) { content }.frame(maxHeight: .infinity, alignment: .top)
    }
}
