import SwiftUI

/// One of an athlete's measured releases, in metres, metres per second and degrees.
struct MeasuredRelease: Identifiable, Equatable {
    var id: UUID
    var label: String
    var speed: Double
    var angle: Double
    var height: Double
    var score: ScoreCategory?
    /// Measured release-to-board-front distance, when the analysis had a metric scale.
    var distance: Double? = nil
}

extension MeasuredRelease {
    /// What the file reads need from one trial, captured on the main actor.
    struct Source: Sendable {
        var id: UUID
        var label: String
        var score: ScoreCategory?
        var results: URL
    }

    /// The athlete's analysed trials, oldest first (main actor: reads the store only, no file I/O).
    @MainActor static func sources(athleteID: UUID?, store: ProjectStore) -> [Source] {
        guard let athleteID, let trials = store.project?.trials else { return [] }
        return trials.filter { $0.athleteID == athleteID }.sorted { $0.createdAt < $1.createdAt }.compactMap { trial in
            store.analysisURL(for: trial).map {
                Source(id: trial.id, label: trial.displayName, score: trial.outcome?.scoreCategory,
                       results: $0.appendingPathComponent("results.json"))
            }
        }
    }

    /// Reads results.json for each source off the main actor; keeps current (not out-of-date) throws whose
    /// release speed, angle and height are all measured and usable. Cancellation stops between files.
    static func read(_ sources: [Source]) async -> [MeasuredRelease] {
        await Task.detached(priority: .userInitiated) {
            var releases: [MeasuredRelease] = []
            for source in sources {
                if Task.isCancelled { return [] }
                if let release = read(source) { releases.append(release) }
            }
            return releases
        }.value
    }

    /// Selected athlete's measured releases: sources gathered on the main actor, files parsed in the background.
    @MainActor static func load(athleteID: UUID?, store: ProjectStore) async -> [MeasuredRelease] {
        await read(sources(athleteID: athleteID, store: store))
    }

    static func read(_ source: Source) -> MeasuredRelease? {
        // An out-of-date analysis (needs_reanalysis.json beside results.json) is not plotted.
        let marker = source.results.deletingLastPathComponent().appendingPathComponent("needs_reanalysis.json")
        guard !FileManager.default.fileExists(atPath: marker.path),
              let metrics = CoachMetricsDocument.load(source.results) else { return nil }
        func value(_ key: String) -> Double? {
            metrics.coach_metrics[key]?.usableValue
        }
        guard let speed = value("bag_release_speed_m_s"), let angle = value("bag_release_angle_deg"),
              let height = value("bag_release_height_m") else { return nil }
        return MeasuredRelease(id: source.id, label: source.label, speed: speed, angle: angle, height: height,
                               score: source.score, distance: releaseToBoard(source.results))
    }

    /// `summaries.release_to_board_front_m` from results.json, when present.
    static func releaseToBoard(_ results: URL) -> Double? {
        guard let data = try? Data(contentsOf: results),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let summaries = object["summaries"] as? [String: Any],
              let value = summaries["release_to_board_front_m"] as? Double, value.isFinite, value > 0 else { return nil }
        return value
    }
}

// MARK: - Zone styling (UI side of `LandingZone`)

extension LandingZone {
    var label: String { ZoneStyle.label(styleKey) }
    var color: Color { ZoneStyle.color(styleKey) }
    var symbol: String { ZoneStyle.symbol(styleKey) }
}

// MARK: - Grid

/// First-contact zone over release angle 10–70° × speed 3–11 m/s, in 0.5° × 0.05 m/s cells, at one
/// release height and distance. For a fixed angle the first contact moves monotonically forward with
/// speed, so each column is a run of zones separated by the speeds whose drag-free path passes exactly
/// through the zone edges (floor 0.30 m short, floor at the board, top of the front edge, hole window,
/// back of the deck): v² = g X² / (2 cos²θ (h + X tanθ − Y)). Six closed-form evaluations per column.
struct SuccessMapGrid: Equatable {
    static let angleRange = 10.0...70.0, speedRange = 3.0...11.0
    static let angleStep = 0.5, speedStep = 0.05
    static var columns: Int { Int(((angleRange.upperBound - angleRange.lowerBound) / angleStep).rounded()) }
    static var rows: Int { Int(((speedRange.upperBound - speedRange.lowerBound) / speedStep).rounded()) }

    struct Run: Equatable { var zone: LandingZone; var firstRow: Int; var lastRow: Int }

    var height: Double
    var distance: Double
    /// Per column (angle), the zone runs from the lowest speed row upward.
    var runs: [[Run]]
    var slideAllowance = 0.45

    static func angle(column: Int) -> Double { angleRange.lowerBound + (Double(column) + 0.5) * angleStep }
    static func speed(row: Int) -> Double { speedRange.lowerBound + (Double(row) + 0.5) * speedStep }

    /// Speed whose path passes through (x, y), or ∞ when no speed reaches it at this angle.
    static func speedThrough(x: Double, y: Double, angleDegrees: Double, height: Double) -> Double {
        let theta = angleDegrees * .pi / 180
        let denominator = 2 * cos(theta) * cos(theta) * (height + x * tan(theta) - y)
        return denominator > 0 ? sqrt(LaunchModel.gravity * x * x / denominator) : .infinity
    }

    /// Zone for one release, from the column's boundary speeds (same rules as `LaunchModel.zone`).
    static func zone(speed v: Double, boundaries b: [Double]) -> LandingZone {
        if v < b[0] { return .off }          // short by more than the slide-up allowance
        if v < b[1] { return .board }        // short, but close enough to slide on
        if v < b[2] { return .off }          // strikes the front face
        if v < b[3] { return .board }        // deck, before the hole window
        if v <= b[4] { return .hole }        // hole window
        if v <= b[5] { return .board }       // deck, past the hole
        return .off                          // long
    }

    static func boundaries(angleDegrees a: Double, height h: Double, distance d: Double, board: BoardGeometry,
                           slideAllowance: Double = 0.45, slideUp: Double = 0.30) -> [Double] {
        func deck(_ along: Double) -> Double {
            speedThrough(x: d + along * cos(board.angle), y: board.frontHeight + along * sin(board.angle), angleDegrees: a, height: h)
        }
        return [speedThrough(x: max(d - slideUp, 0), y: 0, angleDegrees: a, height: h),
                speedThrough(x: d, y: 0, angleDegrees: a, height: h),
                speedThrough(x: d, y: board.frontHeight, angleDegrees: a, height: h),
                deck(max(board.holeAlong - slideAllowance, 0)),
                deck(board.holeAlong + board.holeRadius),
                deck(board.length)]
    }

    static func compute(height: Double, distance: Double, board: BoardGeometry = .regulation,
                        slideAllowance: Double = 0.45) -> SuccessMapGrid {
        let runs = (0..<columns).map { column -> [Run] in
            let b = boundaries(angleDegrees: angle(column: column), height: height, distance: distance, board: board,
                               slideAllowance: slideAllowance)
            var runs: [Run] = []
            for row in 0..<rows {
                let zone = zone(speed: speed(row: row), boundaries: b)
                if let last = runs.last, last.zone == zone { runs[runs.count - 1].lastRow = row }
                else { runs.append(Run(zone: zone, firstRow: row, lastRow: row)) }
            }
            return runs
        }
        return SuccessMapGrid(height: height, distance: distance, runs: runs, slideAllowance: slideAllowance)
    }

    func zone(column: Int, row: Int) -> LandingZone? {
        runs[safe: column]?.first { $0.firstRow <= row && row <= $0.lastRow }?.zone
    }
}

// MARK: - View

/// Heat map of predicted first contact over release angle × speed at the current height and distance,
/// with the current release as a crosshair and the athlete's measured throws as marks.
struct SuccessMap: View {
    @Binding var params: LaunchParameters
    let throwsList: [MeasuredRelease]
    var interactive: Bool
    /// Called when a click or drag on the map ends.
    var onPick: (() -> Void)?
    /// A throw drawn larger with a ring (the throw this report is about).
    var highlight: UUID?
    /// The release with the best modelled chance of the hole window for this athlete (a target marker).
    var bestAim: (speed: Double, angle: Double)?
    /// Clicking a measured throw's mark (non-interactive maps only) calls this with its id.
    var onSelectThrow: ((UUID) -> Void)?

    @State private var grid: SuccessMapGrid
    @State private var hover: (angle: Double, speed: Double)?

    init(params: Binding<LaunchParameters>, throws measured: [MeasuredRelease], interactive: Bool = true, onPick: (() -> Void)? = nil,
         highlight: UUID? = nil, bestAim: (speed: Double, angle: Double)? = nil, onSelectThrow: ((UUID) -> Void)? = nil) {
        _params = params
        throwsList = measured
        self.interactive = interactive
        self.onPick = onPick
        self.highlight = highlight
        self.bestAim = bestAim
        self.onSelectThrow = onSelectThrow
        _grid = State(initialValue: SuccessMapGrid.compute(height: params.wrappedValue.releaseHeight,
                                                           distance: params.wrappedValue.distanceToBoard,
                                                           board: params.wrappedValue.board,
                                                           slideAllowance: params.wrappedValue.slideAllowance))
    }

    private struct Key: Equatable { var height: Double; var distance: Double; var board: BoardGeometry; var slide: Double }

    private static let insets = EdgeInsets(top: 8, leading: 58, bottom: 44, trailing: 10)

    var body: some View {
        VStack(alignment: .leading, spacing: Space.m) {
            Canvas { context, size in draw(&context, size) }
                .frame(minHeight: 280, idealHeight: 320)
                .contentShape(Rectangle())
                .gesture(interactive ? pickGesture : nil)
                .onTapGesture { location in
                    guard !interactive, let onSelectThrow, let id = nearestThrow(to: location) else { return }
                    onSelectThrow(id)
                }
                .onContinuousHover { phase in
                    guard interactive else { return }
                    if case .active(let location) = phase { hover = value(at: location) } else { hover = nil }
                }
                .accessibilityElement()
                .accessibilityLabel("Success map: predicted first contact for release angles 10 to 70 degrees and speeds 3 to 11 metres per second")
                .accessibilityValue("Current release \(number(params.angleDegrees, digits: 1)) degrees, \(number(params.speed, digits: 2)) metres per second: \(LaunchModel(params).zone().label). \(throwsList.count) measured throws shown.")
                .overlay { GeometryReader { proxy in Color.clear.onAppear { canvasSize = proxy.size }.onChange(of: proxy.size) { canvasSize = $1 } } }
            legend
        }
        .task(id: Key(height: params.releaseHeight, distance: params.distanceToBoard, board: params.board, slide: params.slideAllowance)) {
            let (h, d, b, slide) = (params.releaseHeight, params.distanceToBoard, params.board, params.slideAllowance)
            guard grid.height != h || grid.distance != d || grid.slideAllowance != slide else { return }
            let next = await Task.detached(priority: .userInitiated) {
                SuccessMapGrid.compute(height: h, distance: d, board: b, slideAllowance: slide)
            }.value
            if !Task.isCancelled { grid = next }
        }
    }

    @State private var canvasSize: CGSize = .zero
    @Environment(\.colorScheme) private var colorScheme

    /// Fill opacity per zone: the hole window clearly visible, the board a tint, off barely there.
    static func opacity(_ zone: LandingZone, dark: Bool) -> Double {
        switch zone {
        case .hole: dark ? 0.70 : 0.62
        case .board: dark ? 0.40 : 0.30
        case .off: 0.12
        }
    }

    // MARK: Geometry

    private func plotRect(_ size: CGSize) -> CGRect {
        let i = Self.insets
        return CGRect(x: i.leading, y: i.top, width: max(size.width - i.leading - i.trailing, 1), height: max(size.height - i.top - i.bottom, 1))
    }

    private func point(angle: Double, speed: Double, in plot: CGRect) -> CGPoint {
        let a = SuccessMapGrid.angleRange, s = SuccessMapGrid.speedRange
        return CGPoint(x: plot.minX + CGFloat((angle - a.lowerBound) / (a.upperBound - a.lowerBound)) * plot.width,
                       y: plot.maxY - CGFloat((speed - s.lowerBound) / (s.upperBound - s.lowerBound)) * plot.height)
    }

    private func value(at location: CGPoint) -> (angle: Double, speed: Double)? {
        let plot = plotRect(canvasSize)
        guard plot.width > 1 else { return nil }
        let a = SuccessMapGrid.angleRange, s = SuccessMapGrid.speedRange
        let angle = a.lowerBound + Double((location.x - plot.minX) / plot.width) * (a.upperBound - a.lowerBound)
        let speed = s.lowerBound + Double((plot.maxY - location.y) / plot.height) * (s.upperBound - s.lowerBound)
        return ((min(max(angle, a.lowerBound), a.upperBound) * 2).rounded() / 2,
                (min(max(speed, s.lowerBound), s.upperBound) * 20).rounded() / 20)
    }

    /// The measured throw whose mark is within 10 pt of a click, nearest first.
    private func nearestThrow(to location: CGPoint) -> UUID? {
        let plot = plotRect(canvasSize)
        let hits = throwsList.map { release -> (UUID, CGFloat) in
            let p = point(angle: release.angle, speed: release.speed, in: plot)
            return (release.id, hypot(p.x - location.x, p.y - location.y))
        }.filter { $0.1 <= 10 }
        return hits.min { $0.1 < $1.1 }?.0
    }

    private var pickGesture: some Gesture {
        DragGesture(minimumDistance: 0)
            .onChanged { drag in
                guard let v = value(at: drag.location) else { return }
                params.angleDegrees = v.angle
                params.speed = v.speed
            }
            .onEnded { _ in onPick?() }
    }

    // MARK: Drawing

    private func draw(_ ctx: inout GraphicsContext, _ size: CGSize) {
        let plot = plotRect(size)
        let columns = SuccessMapGrid.columns, rows = SuccessMapGrid.rows
        let cellW = plot.width / CGFloat(columns), cellH = plot.height / CGFloat(rows)
        // One layer per zone: opaque cells composited once at the zone's opacity, so neighbouring cells never
        // double up into seams. The hole window is strong; board and off stay calm so the target stands out.
        for zone in LandingZone.allCases {
            var cells = ctx
            cells.opacity = Self.opacity(zone, dark: colorScheme == .dark)
            cells.drawLayer { layer in
                for (column, runs) in grid.runs.enumerated() {
                    for run in runs where run.zone == zone {
                        let rect = CGRect(x: plot.minX + CGFloat(column) * cellW, y: plot.maxY - CGFloat(run.lastRow + 1) * cellH,
                                          width: cellW + 0.5, height: CGFloat(run.lastRow - run.firstRow + 1) * cellH + 0.5)
                        layer.fill(Path(rect), with: .color(zone.color))
                    }
                }
            }
        }
        // Axes: ticks every 10° and 1 m/s, light gridlines over the map.
        var gridLines = Path(), ticks = Path()
        for angle in stride(from: 10.0, through: 70.0, by: 10) {
            let x = point(angle: angle, speed: 3, in: plot).x
            gridLines.move(to: CGPoint(x: x, y: plot.minY)); gridLines.addLine(to: CGPoint(x: x, y: plot.maxY))
            ticks.move(to: CGPoint(x: x, y: plot.maxY)); ticks.addLine(to: CGPoint(x: x, y: plot.maxY + 4))
            ctx.draw(Text("\(Int(angle))°").font(.caption2).monospacedDigit().foregroundStyle(.secondary),
                     at: CGPoint(x: x, y: plot.maxY + 7), anchor: .top)
        }
        for speed in stride(from: 3.0, through: 11.0, by: 1) {
            let y = point(angle: 10, speed: speed, in: plot).y
            gridLines.move(to: CGPoint(x: plot.minX, y: y)); gridLines.addLine(to: CGPoint(x: plot.maxX, y: y))
            ticks.move(to: CGPoint(x: plot.minX - 4, y: y)); ticks.addLine(to: CGPoint(x: plot.minX, y: y))
            ctx.draw(Text("\(Int(speed))").font(.caption2).monospacedDigit().foregroundStyle(.secondary),
                     at: CGPoint(x: plot.minX - 7, y: y), anchor: .trailing)
        }
        ctx.stroke(gridLines, with: .color(.primary.opacity(0.10)), lineWidth: 0.75)
        ctx.stroke(ticks, with: .color(.secondary), lineWidth: 1)
        ctx.stroke(Path(plot), with: .color(.primary.opacity(0.25)), lineWidth: 1)
        ctx.draw(Text("Release angle (°)").font(.caption).foregroundStyle(.secondary),
                 at: CGPoint(x: plot.midX, y: size.height - 2), anchor: .bottom)
        var rotated = ctx
        rotated.translateBy(x: 12, y: plot.midY)
        rotated.rotate(by: .degrees(-90))
        rotated.draw(Text("Release speed (m/s)").font(.caption).foregroundStyle(.secondary), at: .zero, anchor: .center)

        // Measured throws.
        var clipped = ctx
        clipped.clip(to: Path(plot.insetBy(dx: -6, dy: -6)))
        for release in throwsList where release.id != highlight {
            let p = point(angle: release.angle, speed: release.speed, in: plot)
            guard plot.insetBy(dx: -5, dy: -5).contains(p) else { continue }
            drawMark(&clipped, at: p, score: release.score)
        }
        if let highlight, let release = throwsList.first(where: { $0.id == highlight }) {
            let p = point(angle: release.angle, speed: release.speed, in: plot)
            if plot.insetBy(dx: -5, dy: -5).contains(p) {
                let ring = Path(ellipseIn: CGRect(x: p.x - 11, y: p.y - 11, width: 22, height: 22))
                clipped.stroke(ring, with: .color(Color(nsColor: .controlBackgroundColor)), lineWidth: 5)
                clipped.stroke(ring, with: .color(.accentColor), lineWidth: 2.5)
                drawMark(&clipped, at: p, score: release.score)
                clipped.draw(Text("This throw").font(.caption2.weight(.semibold)).foregroundStyle(Color.accentColor),
                             at: CGPoint(x: p.x, y: p.y - 14), anchor: .bottom)
            }
        }
        // Best aim for this athlete: a target (concentric rings), labelled.
        if let bestAim {
            let p = point(angle: bestAim.angle, speed: bestAim.speed, in: plot)
            if plot.contains(p) {
                for (radius, width) in [(9.0, 2.0), (4.0, 2.0)] as [(CGFloat, CGFloat)] {
                    let ring = Path(ellipseIn: CGRect(x: p.x - radius, y: p.y - radius, width: 2 * radius, height: 2 * radius))
                    clipped.stroke(ring, with: .color(Color(nsColor: .controlBackgroundColor)), lineWidth: width + 2)
                    clipped.stroke(ring, with: .color(.primary), lineWidth: width)
                }
                clipped.draw(Text("Best aim").font(.caption2.weight(.semibold)), at: CGPoint(x: p.x + 12, y: p.y), anchor: .leading)
            }
        }

        // Current release: crosshair and a ring.
        let current = point(angle: params.angleDegrees, speed: params.speed, in: plot)
        if plot.contains(current) {
            var cross = Path()
            cross.move(to: CGPoint(x: current.x, y: plot.minY)); cross.addLine(to: CGPoint(x: current.x, y: plot.maxY))
            cross.move(to: CGPoint(x: plot.minX, y: current.y)); cross.addLine(to: CGPoint(x: plot.maxX, y: current.y))
            ctx.stroke(cross, with: .color(.primary.opacity(0.55)), style: StrokeStyle(lineWidth: 1, dash: [3, 3]))
            let ring = Path(ellipseIn: CGRect(x: current.x - 7, y: current.y - 7, width: 14, height: 14))
            ctx.fill(ring, with: .color(Color(nsColor: .controlBackgroundColor)))
            ctx.stroke(ring, with: .color(.primary), lineWidth: 2.5)
            ctx.fill(Path(ellipseIn: CGRect(x: current.x - 2, y: current.y - 2, width: 4, height: 4)), with: .color(.primary))
        }
    }

    /// ● hole · ◆ board · ✕ miss · ○ no result — dark marks with a light halo so they read on every zone colour.
    private func drawMark(_ ctx: inout GraphicsContext, at p: CGPoint, score: ScoreCategory?) {
        let r: CGFloat = 4.5
        let ink = Color.primary, halo = Color(nsColor: .controlBackgroundColor)
        switch score {
        case .throughHole:
            let dot = Path(ellipseIn: CGRect(x: p.x - r, y: p.y - r, width: 2 * r, height: 2 * r))
            ctx.stroke(dot, with: .color(halo), lineWidth: 3); ctx.fill(dot, with: .color(ink))
        case .onBoard:
            var diamond = Path()
            diamond.move(to: CGPoint(x: p.x, y: p.y - r - 1)); diamond.addLine(to: CGPoint(x: p.x + r + 1, y: p.y))
            diamond.addLine(to: CGPoint(x: p.x, y: p.y + r + 1)); diamond.addLine(to: CGPoint(x: p.x - r - 1, y: p.y)); diamond.closeSubpath()
            ctx.stroke(diamond, with: .color(halo), lineWidth: 3); ctx.fill(diamond, with: .color(ink))
        case .offBoard:
            var cross = Path()
            cross.move(to: CGPoint(x: p.x - r, y: p.y - r)); cross.addLine(to: CGPoint(x: p.x + r, y: p.y + r))
            cross.move(to: CGPoint(x: p.x + r, y: p.y - r)); cross.addLine(to: CGPoint(x: p.x - r, y: p.y + r))
            ctx.stroke(cross, with: .color(halo), style: StrokeStyle(lineWidth: 5, lineCap: .round))
            ctx.stroke(cross, with: .color(ink), style: StrokeStyle(lineWidth: 2, lineCap: .round))
        case nil:
            let dot = Path(ellipseIn: CGRect(x: p.x - r, y: p.y - r, width: 2 * r, height: 2 * r))
            ctx.stroke(dot, with: .color(halo), lineWidth: 4); ctx.stroke(dot, with: .color(ink), lineWidth: 1.6)
        }
    }

    private var legend: some View {
        VStack(alignment: .leading, spacing: Space.xs) {
            HStack(spacing: Space.l) {
                ForEach(LandingZone.allCases, id: \.self) { zone in
                    Label {
                        Text(zone.label)
                    } icon: {
                        Image(systemName: zone.symbol).foregroundStyle(zone.color)
                    }
                }
                Spacer(minLength: Space.s)
                if let hover {
                    let zone = zone(angle: hover.angle, speed: hover.speed)
                    Text("\(number(hover.angle, digits: 1))°, \(number(hover.speed, digits: 2)) m/s → \(zone?.label ?? "—")")
                        .monospacedDigit().foregroundStyle(.secondary)
                }
            }
            .font(.caption.weight(.medium))
            if !throwsList.isEmpty {
                Text("● hole · ◆ board · ✕ miss · ○ no result — each measured throw at its own speed and angle; the colours use the current height and distance.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    private func zone(angle: Double, speed: Double) -> LandingZone? {
        let column = Int((angle - SuccessMapGrid.angleRange.lowerBound) / SuccessMapGrid.angleStep)
        let row = Int((speed - SuccessMapGrid.speedRange.lowerBound) / SuccessMapGrid.speedStep)
        return grid.zone(column: min(column, SuccessMapGrid.columns - 1), row: min(row, SuccessMapGrid.rows - 1))
    }
}
