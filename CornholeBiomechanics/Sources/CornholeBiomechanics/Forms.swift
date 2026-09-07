import AppKit
import SwiftUI

struct ImportTrialForm: View {
    @EnvironmentObject private var store: ProjectStore
    @Environment(\.dismiss) private var dismiss
    let videoURL: URL
    @State private var athleteID: UUID?
    @State private var cameraView: CameraView = .side
    @State private var throwingSide: ThrowingSide = .right
    @State private var targetDirection: TargetDirection = .leftToRight
    @State private var sourceURL = ""
    @State private var sourceAttribution = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("Import Trial Video").font(.title2.weight(.semibold))
            Label(videoURL.lastPathComponent, systemImage: "film").foregroundStyle(.secondary)
            Form {
                Picker("Athlete", selection: $athleteID) {
                    Text("Choose…").tag(UUID?.none)
                    ForEach(store.project?.athletes ?? []) { Text($0.displayName).tag(Optional($0.id)) }
                }
                Picker("Camera view", selection: $cameraView) {
                    ForEach(CameraView.allCases) { Text($0.label).tag($0) }
                }
                Picker("Throwing side", selection: $throwingSide) {
                    ForEach(ThrowingSide.allCases) { Text($0.label).tag($0) }
                }
                Picker("Direction toward target", selection: $targetDirection) {
                    ForEach(TargetDirection.allCases) { Text($0.label).tag($0) }
                }
                TextField("Source URL (optional)", text: $sourceURL)
                TextField("Source attribution / permission note", text: $sourceAttribution, axis: .vertical)
            }.formStyle(.grouped)
            GroupBox("Source and rights") {
                Text("The app stores a source URL and attribution but does not download from YouTube. Only analyze recordings you created or have permission to use. Public video is useful for software testing, not a replacement for project participant data.")
                    .font(.callout).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading)
            }
            if cameraView != .side {
                Label("This view is exploratory. Side view is the primary Stage 1 configuration, and incompatible views cannot be compared.", systemImage: "exclamationmark.triangle")
                    .font(.callout).foregroundStyle(.orange)
            }
            HStack {
                Spacer()
                Button("Cancel", role: .cancel) { dismiss() }
                Button("Import Copy") {
                    do {
                        _ = try store.importVideo(ImportDraft(
                            videoURL: videoURL, athleteID: athleteID, cameraView: cameraView,
                            throwingSide: throwingSide, targetDirection: targetDirection,
                            sourceURL: sourceURL, sourceAttribution: sourceAttribution
                        ))
                        store.selectedSection = .trials
                        dismiss()
                    } catch { store.errorMessage = error.localizedDescription }
                }.buttonStyle(.borderedProminent).disabled(athleteID == nil)
            }
        }.padding(24).frame(width: 600)
        .onAppear {
            athleteID = store.selectedAthleteID ?? store.project?.athletes.first?.id
            if let athlete = store.project?.athletes.first(where: { $0.id == athleteID }) {
                throwingSide = athlete.dominantHand
            }
        }
    }
}

struct AnalysisSettingsView: View {
    @EnvironmentObject private var store: ProjectStore
    @Environment(\.dismiss) private var dismiss
    @State private var settings = AnalysisSettings()

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Advanced Analysis").font(.title2.weight(.semibold))
            Text("These values are saved in every analysis manifest. Reanalyze a corrected trial to update derived kinematics.")
                .foregroundStyle(.secondary)
            Form {
                LabeledContent("Pose confidence threshold") {
                    HStack { Slider(value: $settings.confidenceThreshold, in: 0...1, step: 0.05); Text(settings.confidenceThreshold, format: .number.precision(.fractionLength(2))).monospacedDigit().frame(width: 42) }
                }
                Stepper("Maximum interpolated gap: \(settings.maxInterpolationGapFrames) frames", value: $settings.maxInterpolationGapFrames, in: 0...12)
                Toggle("Zero-phase Butterworth low-pass filter", isOn: $settings.filterEnabled)
                Stepper("Filter order: \(settings.filterOrder)", value: $settings.filterOrder, in: 1...8)
                LabeledContent("Cutoff frequency") {
                    HStack { Slider(value: $settings.filterCutoffHz, in: 1...15, step: 0.5); Text("\(settings.filterCutoffHz.formatted()) Hz").frame(width: 60) }
                }
                Stepper("Time-normalized samples: \(settings.normalizationSamples)", value: $settings.normalizationSamples, in: 51...201, step: 10)
                Stepper("Minimum paired trials: \(settings.minimumRelationshipTrials)", value: $settings.minimumRelationshipTrials, in: 5...30)
            }.formStyle(.grouped)
            Text("The 6 Hz default is a documented starting point, not a universal optimum. Cutoff validity depends on frame rate, movement content, and markerless noise; the engine rejects values above Nyquist.")
                .font(.caption).foregroundStyle(.secondary)
            HStack {
                Spacer(); Button("Cancel") { dismiss() }
                Button("Save") {
                    do { try store.updateSettings(settings); dismiss() }
                    catch { store.errorMessage = error.localizedDescription }
                }.buttonStyle(.borderedProminent)
            }
        }.padding(24).frame(width: 620)
        .onAppear { settings = store.project?.analysisSettings ?? AnalysisSettings() }
    }
}
