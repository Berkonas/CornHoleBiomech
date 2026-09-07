import SwiftUI

private enum BoardPointKind: String, CaseIterable, Identifiable {
    case intended = "Intended target"
    case contact = "First contact"
    case resting = "Final resting"
    var id: String { rawValue }
    var color: Color {
        switch self { case .intended: .blue; case .contact: .red; case .resting: .green }
    }
}

struct OutcomeEditor: View {
    @EnvironmentObject private var store: ProjectStore
    @EnvironmentObject private var analysis: AnalysisService
    @Environment(\.dismiss) private var dismiss
    let trial: Trial
    @State private var outcome = TrialOutcome()
    @State private var activePoint: BoardPointKind = .contact
    @State private var isSaving = false

    var body: some View {
        HStack(alignment: .top, spacing: 26) {
            VStack(alignment: .leading, spacing: 14) {
                Text("Record Task Outcome").font(.title2.weight(.semibold))
                Text(trial.originalFilename).foregroundStyle(.secondary)
                Form {
                    TextField("Intended target", text: $outcome.intendedTarget)
                    Picker("Score", selection: $outcome.scoreCategory) {
                        ForEach(ScoreCategory.allCases) { Text($0.label).tag($0) }
                    }
                    TextField("Throw type", text: $outcome.throwType)
                    TextField("Notes", text: $outcome.notes, axis: .vertical).lineLimit(3...6)
                }.formStyle(.grouped)
                Picker("Point to place", selection: $activePoint) {
                    ForEach(BoardPointKind.allCases) { Text($0.rawValue).tag($0) }
                }.pickerStyle(.segmented)
                Text("Board coordinates are approximate manual clicks in inches: x is left-to-right (0–24); y is pitcher-to-back (0–48). The hole center is (12, 39).")
                    .font(.caption).foregroundStyle(.secondary)
            }.frame(width: 390)

            VStack(spacing: 12) {
                BoardView(outcome: $outcome, activePoint: activePoint).frame(width: 300, height: 500)
                HStack {
                    Button("Clear selected point") { setPoint(nil, kind: activePoint) }
                    Spacer()
                    Button("Cancel") { dismiss() }
                    Button("Save Outcome") { save() }.buttonStyle(.borderedProminent).disabled(isSaving)
                }
            }
        }.padding(24).frame(minWidth: 780)
        .onAppear { outcome = trial.outcome ?? TrialOutcome() }
    }

    private func setPoint(_ point: BoardPoint?, kind: BoardPointKind) {
        switch kind {
        case .intended: outcome.intendedPoint = point
        case .contact: outcome.firstContactPoint = point
        case .resting: outcome.finalRestingPoint = point
        }
    }

    private func save() {
        do { try store.saveOutcome(outcome, for: trial) }
        catch { store.errorMessage = error.localizedDescription; return }
        isSaving = true
        Task {
            do {
                try await analysis.summarizeOutcome(outcome, analysisURL: store.analysisURL(for: store.selectedTrial ?? trial))
                dismiss()
            } catch {
                store.errorMessage = "Outcome metadata was saved, but spatial-error export failed: \(error.localizedDescription)"
                isSaving = false
            }
        }
    }
}

private struct BoardView: View {
    @Binding var outcome: TrialOutcome
    let activePoint: BoardPointKind

    var body: some View {
        GeometryReader { geometry in
            let size = geometry.size
            ZStack {
                RoundedRectangle(cornerRadius: 10).fill(Color(red: 0.70, green: 0.51, blue: 0.29))
                RoundedRectangle(cornerRadius: 10).stroke(.primary.opacity(0.55), lineWidth: 2)
                Circle().fill(Color(nsColor: .windowBackgroundColor))
                    .frame(width: size.width * 0.25, height: size.width * 0.25)
                    .position(x: size.width * 0.5, y: size.height * (1 - 39.0 / 48.0))
                Text("BACK").font(.caption2.weight(.bold)).foregroundStyle(.white.opacity(0.75)).position(x: size.width / 2, y: 13)
                Text("PITCHER END").font(.caption2.weight(.bold)).foregroundStyle(.white.opacity(0.75)).position(x: size.width / 2, y: size.height - 13)
                pointMarker(outcome.intendedPoint, kind: .intended, size: size)
                pointMarker(outcome.firstContactPoint, kind: .contact, size: size)
                pointMarker(outcome.finalRestingPoint, kind: .resting, size: size)
            }
            .contentShape(Rectangle())
            .gesture(DragGesture(minimumDistance: 0).onEnded { value in
                let x = min(max(0, value.location.x / size.width), 1) * 24
                let y = (1 - min(max(0, value.location.y / size.height), 1)) * 48
                let point = BoardPoint(xInches: x, yInches: y)
                switch activePoint {
                case .intended: outcome.intendedPoint = point
                case .contact: outcome.firstContactPoint = point
                case .resting: outcome.finalRestingPoint = point
                }
            })
            .accessibilityLabel("Top-down cornhole board")
            .accessibilityHint("Click to place the selected approximate board point")
        }
    }

    @ViewBuilder private func pointMarker(_ point: BoardPoint?, kind: BoardPointKind, size: CGSize) -> some View {
        if let point {
            ZStack {
                Circle().fill(kind.color).frame(width: 17, height: 17)
                Circle().stroke(.white, lineWidth: 2).frame(width: 17, height: 17)
            }
            .position(x: size.width * point.xInches / 24, y: size.height * (1 - point.yInches / 48))
            .help("\(kind.rawValue): (\(point.xInches.formatted(.number.precision(.fractionLength(1)))), \(point.yInches.formatted(.number.precision(.fractionLength(1))))) in")
        }
    }
}
