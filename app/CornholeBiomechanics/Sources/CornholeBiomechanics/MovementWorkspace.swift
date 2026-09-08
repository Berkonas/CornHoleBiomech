import AVKit
import Charts
import SwiftUI

let athleteInk = Color(red: 0.15, green: 0.51, blue: 0.56)
let referenceInk = Color.secondary
let eventNames: [(String, String)] = [("motion_start", "Start"), ("peak_backswing", "Backswing"), ("forward_swing", "Forward swing"), ("release", "Release"), ("peak_follow_through", "Follow-through"), ("motion_end", "End")]
let angleFields = ["elbow_angle_deg", "arm_to_trunk_deg", "trunk_inclination_deg", "upper_arm_orientation_deg", "forearm_orientation_deg"]

struct MovementWorkspace: View {
    let normalized: NormalizedDocument
    let comparison: ComparisonDocument?
    let videoURL: URL?
    let events: EventDocument?
    let fps: Double
    @Binding var fraction: Double
    @State private var field = "elbow_angle_deg"
    @State private var showDifference = false
    @State private var showNormalization = false

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack {
                Text("The movement").font(.title2.weight(.semibold))
                Spacer()
                Button { showNormalization.toggle() } label: { Label("How bodies are aligned", systemImage: "info.circle") }
                    .popover(isPresented: $showNormalization) { NormalizationGuide().frame(width: 420).padding(24) }
            }
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: 20) {
                    video.frame(minWidth: 330)
                    skeleton.frame(width: 270)
                }
                VStack(spacing: 16) { video; skeleton.frame(height: 245) }
            }
            MovementTimeline(fraction: $fraction, timing: normalized.eventTiming)
            HStack {
                Picker("Angle", selection: $field) { ForEach(angleFields, id: \.self) { Text(metricLabel($0)).tag($0) } }.frame(maxWidth: 360)
                Spacer()
                if comparison != nil { Toggle("Difference curve", isOn: $showDifference).toggleStyle(.checkbox) }
            }
            AngleComparisonPlot(tau: normalized.tau, trial: normalized.values[field]?.scalars ?? [], reference: comparison?.curves?.referenceMean[field]?.scalars, sd: comparison?.curves?.referenceSD[field]?.scalars, field: field, fraction: $fraction, difference: showDifference)
                .frame(height: 240)
            Text("Solid teal: athlete · dashed gray: reference · shaded band: reference ±1 SD when available. Gaps represent missing measurements.")
                .font(.caption).foregroundStyle(.secondary)
            HStack {
                Text("Shoulder-relative wrist path").font(.headline)
                Spacer()
                Text("Arm lengths · equal horizontal and vertical scale").font(.caption).foregroundStyle(.secondary)
            }
            WristPathPlot(trial: normalized.values["wrist_path_arm_lengths"]?.vectors ?? [], reference: comparison?.curves?.referenceMean["wrist_path_arm_lengths"]?.vectors, fraction: fraction, timing: normalized.eventTiming)
                .frame(height: 270)
        }
    }
    @ViewBuilder private var video: some View {
        if let videoURL {
            CycleVideo(url: videoURL, events: events, fps: fps, fraction: $fraction).id(videoURL)
        } else {
            ContentUnavailableView("Video unavailable", systemImage: "video.slash", description: Text("Normalized movement measurements remain available below.")).frame(height: 235)
        }
    }
    private var skeleton: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Aligned movement").font(.headline)
            NormalizedSkeleton(trial: normalized.values, reference: comparison?.curves?.referenceMean, fraction: fraction, count: normalized.tau.count).frame(height: 205)
            Text("Common shoulder origin. Orange connectors show positional differences, not injury risk.").font(.caption).foregroundStyle(.secondary)
        }
    }
}

struct CycleVideo: View {
    let url: URL; let events: EventDocument?; let fps: Double
    @Binding var fraction: Double
    var interactive = true
    @State private var player: AVPlayer
    @State private var observer: Any?
    @State private var playing = false
    @State private var fromPlayback = false
    init(url: URL, events: EventDocument?, fps: Double, fraction: Binding<Double>, interactive: Bool = true) {
        self.url = url; self.events = events; self.fps = fps; self.interactive = interactive; _fraction = fraction; _player = State(initialValue: AVPlayer(url: url))
    }
    var body: some View {
        VStack(spacing: 8) {
            NativeVideoPlayer(player: player, showsControls: false).frame(height: 235).clipShape(RoundedRectangle(cornerRadius: 6))
            HStack {
                if interactive { Button {
                    if playing { player.pause() } else { if fraction >= 0.995 { fraction = 0; seek() }; player.play() }
                    playing.toggle()
                } label: { Label(playing ? "Pause" : "Play movement", systemImage: playing ? "pause.fill" : "play.fill") } }
                Spacer()
                Text("Frame \(Int((time * fps).rounded())) · \(number(time, digits: 2)) s").font(.caption.monospacedDigit())
            }
        }
        .onAppear {
            seek()
            observer = player.addPeriodicTimeObserver(forInterval: CMTime(seconds: 1 / 30.0, preferredTimescale: 600), queue: .main) { t in
                guard player.timeControlStatus == .playing, t.seconds.isFinite else { return }
                let next = min(1, max(0, (t.seconds - start) / max(1 / fps, end - start)))
                if abs(fraction - next) > 0.000001 {
                    fromPlayback = true
                    fraction = next
                }
                if t.seconds >= end { player.pause(); playing = false }
            }
        }
        .onChange(of: fraction) { _, _ in
            if fromPlayback { fromPlayback = false } else { player.pause(); playing = false; seek() }
        }
        .onDisappear { player.pause(); if let observer { player.removeTimeObserver(observer); self.observer = nil } }
    }
    private var start: Double { Double(events?.events["motion_start"]?.effectiveFrame ?? 0) / max(1, fps) }
    private var end: Double { Double(events?.events["motion_end"]?.effectiveFrame ?? Int(fps)) / max(1, fps) }
    private var time: Double { start + fraction * (end - start) }
    private func seek() { player.seek(to: CMTime(seconds: time, preferredTimescale: 60000), toleranceBefore: .zero, toleranceAfter: .zero) }
}

struct MovementTimeline: View {
    @Binding var fraction: Double
    let timing: [String: Double?]
    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack { Text("Movement cycle").font(.subheadline.weight(.medium)); Spacer(); Text("\(number(fraction * 100, digits: 0))%").monospacedDigit() }
            Slider(value: $fraction, in: 0...1).accessibilityLabel("Movement cycle; seeks video and all plots")
            HStack(spacing: 6) {
                ForEach(eventNames, id: \.0) { name, label in
                    Button {
                        if let value = timing[name] ?? nil { fraction = min(1, max(0, value)) }
                    } label: {
                        VStack(spacing: 3) {
                            Text(label).font(.caption.weight(name == "release" ? .semibold : .regular))
                            Text((timing[name] ?? nil).map { "\(number($0 * 100, digits: 0))%" } ?? "—").font(.caption2.monospacedDigit()).foregroundStyle(.secondary)
                        }.frame(maxWidth: .infinity)
                    }.buttonStyle(.bordered).disabled(timing[name] ?? nil == nil)
                }
            }
            Text("Release is an automatic wrist-speed candidate until reviewed and corrected in Inspect & Correct.").font(.caption).foregroundStyle(.secondary)
        }
    }
}

struct PlotSample: Identifiable {
    var series: String; var index: Int; var x: Double; var y: Double; var segment: Int = 0
    var id: String { "\(series)-\(index)" }
}

struct AngleComparisonPlot: View {
    let tau: [Double]; let trial: [Double?]; let reference: [Double?]?; let sd: [Double?]?
    let field: String
    @Binding var fraction: Double
    var difference = false
    var body: some View {
        if samples.isEmpty {
            ContentUnavailableView("No usable angle samples", systemImage: "chart.xyaxis.line", description: Text("Review tracking and correct missing landmarks."))
        } else {
            Chart {
                ForEach(samples) { p in
                    LineMark(x: .value("Cycle (%)", p.x), y: .value("Degrees", p.y), series: .value("Segment", "\(p.series)-\(p.segment)"))
                        .foregroundStyle(p.series == "Reference" ? referenceInk : athleteInk)
                        .lineStyle(StrokeStyle(lineWidth: p.series == "Reference" ? 1.5 : 2.5, dash: p.series == "Reference" ? [5,4] : []))
                }
                if !difference, let reference, let sd {
                    ForEach(Array(tau.enumerated()), id: \.offset) { i, t in
                        if let mean = reference[safe: i] ?? nil, let spread = sd[safe: i] ?? nil, spread > 0 {
                            AreaMark(x: .value("Cycle", t * 100), yStart: .value("Lower", mean - spread), yEnd: .value("Upper", mean + spread)).foregroundStyle(.secondary.opacity(0.12))
                        }
                    }
                }
                if let peak = peakDifference {
                    RuleMark(x: .value("Largest difference", peak)).foregroundStyle(.orange.opacity(0.5)).lineStyle(StrokeStyle(dash: [2,3]))
                }
                RuleMark(x: .value("Video cursor", fraction * 100)).foregroundStyle(.primary.opacity(0.7)).lineStyle(StrokeStyle(lineWidth: 1))
            }
            .chartXScale(domain: 0...100).chartXAxisLabel("Movement cycle (%)")
            .chartYScale(domain: .automatic(includesZero: difference))
            .chartYAxisLabel(difference ? "Athlete − reference (degrees)" : "Projected angle (degrees)")
            .chartOverlay { proxy in
                GeometryReader { geo in
                    Rectangle().fill(.clear).contentShape(Rectangle()).gesture(DragGesture(minimumDistance: 0).onChanged { value in
                        guard let frame = proxy.plotFrame else { return }
                        let x = value.location.x - geo[frame].origin.x
                        if let percent: Double = proxy.value(atX: x) { fraction = min(1, max(0, percent / 100)) }
                    })
                }
            }.accessibilityLabel("\(metricLabel(field)); synchronized video cursor at \(Int(fraction*100)) percent")
        }
    }
    private var samples: [PlotSample] {
        var values: [PlotSample] = []; var segment = 0
        for (i,t) in tau.enumerated() {
            guard let a = trial[safe: i] ?? nil else { segment += 1; continue }
            if difference {
                if let b = reference?[safe: i] ?? nil { values.append(PlotSample(series: "Difference", index: i, x: t*100, y: delta(a,b), segment: segment)) } else { segment += 1 }
            } else { values.append(PlotSample(series: "Athlete", index: i, x: t*100, y: a, segment: segment)) }
        }
        if !difference, let reference {
            segment = 0
            for (i,t) in tau.enumerated() {
                if let b = reference[safe: i] ?? nil { values.append(PlotSample(series: "Reference", index: i, x: t*100, y: b, segment: segment)) } else { segment += 1 }
            }
        }
        return values
    }
    private func delta(_ a: Double, _ b: Double) -> Double {
        if field.contains("orientation") || field == "trunk_inclination_deg" { return (a-b+540).truncatingRemainder(dividingBy: 360)-180 }
        return a-b
    }
    private var peakDifference: Double? {
        guard let reference else { return nil }
        return tau.indices.compactMap { i -> (Double,Double)? in
            guard let a = trial[safe:i] ?? nil, let b = reference[safe:i] ?? nil else { return nil }
            return (tau[i]*100,abs(delta(a,b)))
        }.max(by: { $0.1 < $1.1 })?.0
    }
}

struct NormalizedSkeleton: View {
    let trial: [String: FlexibleNumericArray]; let reference: [String: FlexibleNumericArray]?
    let fraction: Double; let count: Int
    var body: some View {
        Canvas { context, size in
            let scale = min(size.width / 2.6, size.height / 2.4)
            let origin = CGPoint(x: size.width / 2, y: size.height * 0.35)
            func point(_ p: [Double?]?) -> CGPoint? {
                guard let p, p.count >= 2, let x = p[0], let y = p[1] else { return nil }
                return CGPoint(x: origin.x+x*scale,y:origin.y-y*scale)
            }
            func locations(_ values: [String: FlexibleNumericArray]) -> [String: CGPoint] {
                var result = ["shoulder":origin]
                for name in ["elbow", "wrist", "left_shoulder", "right_shoulder", "left_hip", "right_hip"] {
                    if let p = point(values["\(name)_path_arm_lengths"]?.vectors?[safe: index]) { result[name] = p }
                }
                return result
            }
            func draw(_ p: [String: CGPoint], color: Color, ghost: Bool) {
                for (a,b) in [("shoulder","elbow"),("elbow","wrist"),("left_shoulder","right_shoulder"),("left_shoulder","left_hip"),("right_shoulder","right_hip"),("left_hip","right_hip")] {
                    if let a = p[a], let b = p[b] { var path = Path(); path.move(to:a);path.addLine(to:b);context.stroke(path,with:.color(color),style:StrokeStyle(lineWidth:ghost ? 3 : 4, lineCap:.round, dash:ghost ? [5,4]:[])) }
                }
                for (name,p) in p { context.fill(Path(ellipseIn:CGRect(x:p.x-4,y:p.y-4,width:8,height:8)),with:.color(color)); if !ghost && ["elbow","wrist"].contains(name) { context.draw(Text(name.capitalized).font(.caption2).foregroundColor(.secondary),at:CGPoint(x:p.x+8,y:p.y-10),anchor:.leading) } }
            }
            let a=locations(trial)
            if let reference {
                let b=locations(reference);draw(b,color:.secondary.opacity(0.6),ghost:true)
                for name in ["elbow","wrist"] { if let p=a[name], let q=b[name] { var path=Path();path.move(to:p);path.addLine(to:q);context.stroke(path,with:.color(.orange.opacity(0.7)),style:StrokeStyle(lineWidth:2,dash:[2,3])) } }
            }
            draw(a,color:athleteInk,ghost:false)
        }.accessibilityLabel("Shoulder-aligned athlete and reference skeletons at \(Int(fraction*100)) percent")
    }
    private var index: Int { min(max(0,count-1),max(0,Int((fraction*Double(max(0,count-1))).rounded()))) }
}

struct WristPathPlot: View {
    let trial: [[Double?]]; let reference: [[Double?]]?
    let fraction: Double; let timing: [String: Double?]
    var traces: [[[Double?]]] = []
    var body: some View {
        Canvas { context, size in
            let pad: CGFloat = 35
            let paths=[trial]+(reference.map { [$0] } ?? [])+traces
            let points=paths.flatMap { $0 }.compactMap { p -> CGPoint? in guard p.count>=2,let x=p[0],let y=p[1] else{return nil};return CGPoint(x:x,y:y) }
            let loX=min(-0.1,points.map(\.x).min() ?? -1), hiX=max(0.1,points.map(\.x).max() ?? 1)
            let loY=min(-0.1,points.map(\.y).min() ?? -1), hiY=max(0.1,points.map(\.y).max() ?? 1)
            let scale=min((size.width-2*pad)/max(0.2,hiX-loX),(size.height-2*pad)/max(0.2,hiY-loY))
            let origin=CGPoint(x:size.width/2-(hiX+loX)/2*scale,y:size.height/2+(hiY+loY)/2*scale)
            func map(_ p:[Double?]) -> CGPoint? { guard p.count>=2,let x=p[0],let y=p[1] else{return nil};return CGPoint(x:origin.x+x*scale,y:origin.y-y*scale) }
            for tick in stride(from: -2.0, through: 2.0, by: 0.5) {
                let x=origin.x+tick*scale,y=origin.y-tick*scale
                if x>pad && x<size.width-pad {var p=Path();p.move(to:CGPoint(x:x,y:pad));p.addLine(to:CGPoint(x:x,y:size.height-pad));context.stroke(p,with:.color(.secondary.opacity(0.12)),lineWidth:1);context.draw(Text(number(tick)).font(.caption2).foregroundColor(.secondary),at:CGPoint(x:x,y:size.height-12))}
                if y>pad && y<size.height-pad {var p=Path();p.move(to:CGPoint(x:pad,y:y));p.addLine(to:CGPoint(x:size.width-pad,y:y));context.stroke(p,with:.color(.secondary.opacity(0.12)),lineWidth:1);context.draw(Text(number(tick)).font(.caption2).foregroundColor(.secondary),at:CGPoint(x:14,y:y))}
            }
            func draw(_ values:[[Double?]],color:Color,width:CGFloat,dash:[CGFloat]=[]) {
                var path=Path();var started=false
                for value in values {if let p=map(value){if started {path.addLine(to:p)}else{path.move(to:p);started=true}}else{started=false}}
                context.stroke(path,with:.color(color),style:StrokeStyle(lineWidth:width,lineCap:.round,dash:dash))
            }
            for t in traces {draw(t,color:athleteInk.opacity(0.15),width:1)}
            if let reference {draw(reference,color:.secondary,width:2,dash:[5,4])}
            draw(trial,color:athleteInk,width:2.5)
            for name in ["motion_start","peak_backswing","release","peak_follow_through"] {
                if let tau=timing[name] ?? nil, let v=trial[safe:min(max(0,trial.count-1),max(0,Int(tau*Double(max(0,trial.count-1)))))],let p=map(v) {
                    context.fill(Path(ellipseIn:CGRect(x:p.x-3,y:p.y-3,width:6,height:6)),with:.color(.primary))
                    context.draw(Text(eventNames.first { $0.0==name }?.1 ?? name).font(.caption2).foregroundColor(.secondary),at:CGPoint(x:p.x+5,y:p.y-12),anchor:.leading)
                }
            }
            let i=min(max(0,trial.count-1),Int(fraction*Double(max(0,trial.count-1))))
            if let v=trial[safe:i],let p=map(v){context.fill(Path(ellipseIn:CGRect(x:p.x-5,y:p.y-5,width:10,height:10)),with:.color(athleteInk));context.stroke(Path(ellipseIn:CGRect(x:p.x-8,y:p.y-8,width:16,height:16)),with:.color(.primary),lineWidth:1)}
            context.draw(Text("Toward target → (arm lengths)").font(.caption2).foregroundColor(.secondary),at:CGPoint(x:size.width-8,y:size.height-12),anchor:.trailing)
        }.accessibilityLabel("Normalized wrist trajectory; current sample and movement events marked")
    }
}

struct NormalizationGuide: View {
    var body: some View {
        VStack(alignment:.leading,spacing:16) {
            Text("Different bodies. Comparable motion.").font(.title2.weight(.semibold))
            Text("A 5′4″ athlete and a 6′8″ athlete can follow the same relative movement while tracing very different paths in raw pixels.")
            ForEach(Array([("1","Align shoulders","Move each throwing shoulder to the origin."),("2","Scale by arm length","Divide paths by median upper-arm length + median forearm length."),("3","Face the target","Reflect horizontal direction so positive x always points toward the target."),("4","Align movement time","Map each throw from start (0%) to end (100%).")].enumerated()),id:\.offset) { _, item in
                HStack(alignment:.top,spacing:12) {Text(item.0).font(.title3.monospacedDigit()).foregroundStyle(athleteInk);VStack(alignment:.leading,spacing:3){Text(item.1).font(.headline);Text(item.2).font(.callout).foregroundStyle(.secondary)}}
            }
            Text("We compare angles and body-normalized trajectories rather than raw pixels. Perspective and anatomical proportions still matter.").font(.callout)
        }
    }
}
