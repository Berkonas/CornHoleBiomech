import SwiftUI

struct SwingLabPanel: View {
    @Binding var parameters: SwingParameters
    var bagMass: Double
    var boardAngle: Double
    var time: Double // seconds relative to release
    var launch: TossParameters?
    private var model: SwingMechanics { .init(parameters: parameters) }
    private var current: SwingPose { model.pose(at: min(parameters.duration, max(0, parameters.releaseTime+time))) }

    var body: some View {
        ResearchCard(title: "Body → arm swing → release", symbol: "figure.disc.sports") {
            HStack(alignment: .top, spacing: 20) {
                SwingAvatarCanvas(parameters: parameters, time: parameters.releaseTime+time, held: time < 0)
                    .frame(width: 215, height: 225)
                VStack(alignment: .leading, spacing: 9) {
                    Text(time < 0 ? "Forward swing · bag held" : "Released · arm follows through").font(.headline)
                    Text("Upper arm: \(number(current.q1*180 / .pi))° from downward vertical\nElbow included angle: \(number(current.elbowIncluded))° (180° = straight)\nUpper-arm speed: \(number(current.w1*180 / .pi))°/s")
                        .font(.callout).monospacedDigit().lineSpacing(4)
                    if let p = launch {
                        Text("Computed release: \(number(p.speed, digits: 2)) m/s at \(number(p.elevation, digits: 1))°\nHeight: \(number(p.height, digits: 2)) m · elbow: \(number(model.release.elbowIncluded))°\nRelease → board front: \(number(p.distance, digits: 2)) m")
                            .font(.callout).monospacedDigit().lineSpacing(4)
                    } else {
                        Label("This motion cannot launch: check for a below-ground, backward, or out-of-range release. Adjust joint angles, release phase or duration.", systemImage: "exclamationmark.triangle")
                            .font(.callout).foregroundStyle(.orange)
                    }
                    Text("Prescribed motion, fixed shoulder, two rigid links. The distal link reaches the bag center and includes the grip offset. It is not a measured forearm length.")
                        .font(.caption).foregroundStyle(.secondary)
                }.frame(maxWidth: .infinity, alignment: .leading)
            }
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())], spacing: 16) {
                control("Release phase", $parameters.releaseFraction, 0.15...0.90, "fraction", 2)
                control("Swing duration", $parameters.duration, 0.20...1.2, "s", 2)
                control("Swing direction (+ right)", $parameters.yaw, -20...20, "°", 1)
            }
            Text("Release phase selects when the bag detaches between the backswing endpoint (0) and follow-through endpoint (1). Changing it changes position, speed and angle together. Duration controls how quickly the same joint path is traversed.")
                .font(.caption).foregroundStyle(.secondary)
            SwingStanceCanvas(parameters: parameters, boardAngle: boardAngle).frame(height: 115)
            DisclosureGroup("Body size, standing position & joint motion") {
                VStack(alignment: .leading, spacing: 16) {
                    Picker("Throwing hand", selection: $parameters.rightHanded) {
                        Text("Right hand").tag(true); Text("Left hand").tag(false)
                    }.pickerStyle(.segmented)
                    Text("Handedness selects the throwing shoulder. Position and direction set lane geometry; neither hand receives an assumed performance advantage. Coordinates refer to the standing body axis at the throwing foul line, not a legal foot-position assessment.")
                        .font(.caption).foregroundStyle(.secondary)
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 18) {
                        control("Standing body height", $parameters.bodyHeight, 1.2...2.3, "m", 2)
                        control("Shoulder height / body height", $parameters.shoulderFraction, 0.65...0.90, "ratio", 2)
                        control("Upper-arm length", $parameters.upperLength, 0.15...0.60, "m", 2)
                        control("Elbow → bag-center length", $parameters.distalLength, 0.15...0.65, "m", 2)
                        control("Shoulder width", $parameters.shoulderWidth, 0.2...0.65, "m", 2)
                        control("Standing position · right (+)", $parameters.stanceRight, -2...2, "m", 2)
                        control("Standing position · forward (+)", $parameters.stanceForward, -2...1, "m", 2)
                        control("Foul line → target board front", $parameters.boardFront, 3...12, "m", 2)
                        control("Upper arm · backswing", $parameters.shoulderStart, -100...0, "°", 1)
                        control("Upper arm · follow-through", $parameters.shoulderEnd, 20...120, "°", 1)
                        control("Elbow flexion · backswing", $parameters.elbowStart, 0...100, "°", 1)
                        control("Elbow flexion · follow-through", $parameters.elbowEnd, 0...100, "°", 1)
                        control("Upper-link mass", $parameters.upperMass, 0.2...5, "kg", 2)
                        control("Distal-link mass", $parameters.distalMass, 0.2...4, "kg", 2)
                    }
                    Text("Shoulder height ratio, width and segment masses are editable assumptions, not inferred anatomy. The trunk stays upright; there is no step, shoulder translation, wrist snap, muscle model or joint-limit enforcement. Elbow flexion is 180° minus the included elbow angle.")
                        .font(.caption).foregroundStyle(.secondary)
                }.padding(.top, 12)
            }
            DisclosureGroup("Forces, joint torques & swing equations") {
                let t = min(parameters.releaseTime, max(0, parameters.releaseTime+time))
                let force = model.torques(at: t, bagMass: bagMass)
                VStack(alignment: .leading, spacing: 10) {
                    Text(time >= 0 ? "Values at release immediately before detachment:" : "Values at the inspected instant:").font(.headline)
                    Text("Bag weight mg = \(number(bagMass*9.81, digits: 2)) N\nRequired resultant grip force = \(number(force.gripForce, digits: 2)) N\nNet shoulder torque = \(number(force.shoulder, digits: 2)) N·m\nNet elbow torque = \(number(force.elbow, digits: 2)) N·m")
                        .monospacedDigit().lineSpacing(4)
                    Text("u = t/T; S(u) = 10u³ − 15u⁴ + 6u⁵\nqᵢ = qᵢ,start + Δqᵢ S(u)\nq̇ᵢ = Δqᵢ S′(u)/T; q̈ᵢ = Δqᵢ S″(u)/T²\nr_bag = r_shoulder + Σ lᵢ(sin qᵢ · d − cos qᵢ · ẑ)\nv_bag = Σ lᵢq̇ᵢ(cos qᵢ · d + sin qᵢ · ẑ)\nF_grip = m_bag(a_bag − g_vector)\nM(q)q̈ + C(q,q̇)q̇ + G(q) = (τ_shoulder − τ_elbow, τ_elbow)")
                        .font(.system(.callout, design: .monospaced)).textSelection(.enabled)
                    Text("q₁ and q₂ are absolute link angles from downward vertical; q₂ = q₁ + elbow flexion. d is the horizontal swing direction. Quintic interpolation starts and ends at rest. Torques use the two-uniform-rod mass matrix in Arm Mechanics, including the point bag, and are inverse-dynamics requirements of this chosen motion—not estimated human strength, muscle force, or joint loading. Air forces on the held bag are neglected.")
                        .font(.caption).foregroundStyle(.secondary)
                    Text("A heavier bag raises the force/torque demand for an identical prescribed swing. It does not slow that swing unless you lengthen its duration. Real athletes may respond differently; these example segment properties and motion curves need experimental validation.")
                        .font(.caption).foregroundStyle(.secondary)
                    Link("MIT · multibody equations", destination: URL(string: "https://underactuated.mit.edu/multibody.html")!)
                    Link("OpenStax · angular and tangential velocity", destination: URL(string: "https://openstax.org/books/university-physics-volume-1/pages/10-1-rotational-variables")!)
                }.padding(.vertical, 10)
            }
        }
    }

    private func control(_ title: String, _ value: Binding<Double>, _ range: ClosedRange<Double>, _ unit: String, _ digits: Int) -> some View {
        let bounded = Binding(get: { value.wrappedValue }, set: { candidate in
            if candidate.isFinite { value.wrappedValue = min(range.upperBound, max(range.lowerBound, candidate)) }
        })
        return VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.caption.weight(.medium))
            HStack {
                TextField(title, value: bounded, format: .number.precision(.fractionLength(digits)))
                    .textFieldStyle(.roundedBorder).frame(width: 72).monospacedDigit()
                Text(unit).font(.caption).foregroundStyle(.secondary)
                Slider(value: bounded, in: range).accessibilityLabel(title)
            }
        }
    }
}

struct SwingAvatarCanvas: View {
    var parameters: SwingParameters
    var time: Double
    var held: Bool
    var body: some View {
        Canvas { context, size in
            let p = parameters, model = SwingMechanics(parameters: p)
            let pose = model.pose(at: min(p.duration, max(0, time)))
            let release = model.release
            let scale = min((size.height-32)/max(p.bodyHeight, pose.wrist.z+0.1), (size.width-24)/2.2)
            let origin = CGPoint(x: size.width*0.46, y: size.height-20)
            func point(_ v: TossVector) -> CGPoint {
                let forward = (v-p.bodyBase).dot(p.direction)
                return .init(x: origin.x+forward*scale, y: origin.y-v.z*scale)
            }
            func line(_ a: TossVector, _ b: TossVector, color: Color, width: Double = 4) {
                var path = Path(); path.move(to: point(a)); path.addLine(to: point(b))
                context.stroke(path, with: .color(color), style: .init(lineWidth: width, lineCap: .round))
            }
            let hip = p.bodyBase + TossVector(z: p.bodyHeight*0.51)
            let neck = p.bodyBase + TossVector(z: p.shoulderHeight)
            line(hip, neck, color: .secondary)
            line(neck, p.bodyBase+TossVector(z: p.bodyHeight*0.88), color: .secondary, width: 3)
            line(hip, p.bodyBase+p.direction*(-0.20), color: .secondary)
            line(hip, p.bodyBase+p.direction*0.20, color: .secondary)
            let head = point(p.bodyBase + TossVector(z: p.bodyHeight*0.94))
            let radius = p.bodyHeight*0.06*scale
            context.stroke(Path(ellipseIn: CGRect(x: head.x-radius, y: head.y-radius, width: 2*radius, height: 2*radius)), with: .color(.secondary), lineWidth: 3)
            // Ghost shows the actual computed release pose, never a hand-drawn launch angle.
            line(release.shoulder, release.elbow, color: .blue.opacity(0.18), width: 3)
            line(release.elbow, release.wrist, color: .blue.opacity(0.18), width: 3)
            line(pose.shoulder, pose.elbow, color: .blue, width: 5)
            line(pose.elbow, pose.wrist, color: .cyan, width: 5)
            for joint in [pose.shoulder,pose.elbow,pose.wrist] {
                let point = point(joint)
                context.fill(Path(ellipseIn: CGRect(x: point.x-3, y: point.y-3, width: 6, height: 6)), with: .color(.primary))
            }
            let hand = point(pose.wrist)
            if held { context.fill(Path(roundedRect: CGRect(x: hand.x-5,y: hand.y-5,width: 10,height: 10),cornerRadius: 2), with: .color(.orange)) }
            context.draw(Text("\(p.rightHanded ? "RIGHT" : "LEFT") ARM · swing plane").font(.caption2).foregroundStyle(.secondary), at: .init(x: size.width/2,y: 6))
            context.draw(Text("toward board →").font(.caption2).foregroundStyle(.secondary), at: .init(x: size.width/2,y: size.height-5))
        }.accessibilityLabel("Animated \(parameters.rightHanded ? "right" : "left") throwing arm. Blue upper arm, cyan distal link. Faint pose marks release. \(held ? "Bag held." : "Bag released.")")
    }
}

struct SwingStanceCanvas: View {
    var parameters: SwingParameters
    var boardAngle: Double
    var body: some View {
        Canvas { context, size in
            let p = parameters, release = SwingMechanics(parameters: p).release
            let board = TossBoard(distance: p.boardFront, angleDegrees: boardAngle)
            let lowX = min(-1, p.stanceForward-0.5), highX = p.boardFront+board.length+0.5
            let halfY = max(0.8, abs(p.stanceRight)+0.5)
            let scale = min((size.width-60)/(highX-lowX), (size.height-42)/(2*halfY))
            func point(_ v: TossVector) -> CGPoint { .init(x: 30+(v.x-lowX)*scale, y: size.height/2+v.y*scale) }
            var foul = Path(); foul.move(to: point(.init(y: -halfY))); foul.addLine(to: point(.init(y: halfY)))
            context.stroke(foul, with: .color(.secondary.opacity(0.5)), style: .init(lineWidth:1,dash:[3,3]))
            var center = Path(); center.move(to: point(.init(x: lowX))); center.addLine(to: point(.init(x: highX)))
            context.stroke(center, with: .color(.secondary.opacity(0.15)), lineWidth:1)
            let corner = point(.init(x: p.boardFront, y: -board.width/2))
            let rect = CGRect(x:corner.x,y:corner.y,width:board.length*cos(board.angle)*scale,height:board.width*scale)
            context.fill(Path(rect), with:.color(.yellow.opacity(0.25)))
            context.stroke(Path(rect), with:.color(.brown),lineWidth:1.5)
            let hole = point(board.hole), r = board.holeRadius*scale
            context.fill(Path(ellipseIn:.init(x:hole.x-r,y:hole.y-r,width:2*r,height:2*r)),with:.color(.green))
            let l = p.bodyBase-p.rightDirection*(p.shoulderWidth/2), right = p.bodyBase+p.rightDirection*(p.shoulderWidth/2)
            var shoulders = Path(); shoulders.move(to:point(l)); shoulders.addLine(to:point(right))
            context.stroke(shoulders,with:.color(.primary),style:.init(lineWidth:4,lineCap:.round))
            let throwing = point(p.shoulder), atRelease = point(release.wrist)
            context.fill(Path(ellipseIn:.init(x:throwing.x-4,y:throwing.y-4,width:8,height:8)),with:.color(.blue))
            var aim = Path(); aim.move(to:atRelease); aim.addLine(to:point(release.wrist+p.direction*0.9))
            context.stroke(aim,with:.color(.blue),lineWidth:2)
            context.draw(Text("TOP VIEW · forward → · right ↓").font(.caption2).foregroundStyle(.secondary),at:.init(x:30,y:5),anchor:.topLeading)
            context.draw(Text("Foul line").font(.caption2).foregroundStyle(.secondary),at:.init(x:point(.zero).x,y:size.height-7))
            context.draw(Text("\(p.rightHanded ? "R" : "L") shoulder").font(.caption2).foregroundStyle(.blue),at:.init(x:throwing.x,y:throwing.y+15))
        }.accessibilityLabel("Top view of standing position relative to the foul line and receiving board. Blue marks the throwing shoulder and release direction. Right is downward in this map.")
    }
}
