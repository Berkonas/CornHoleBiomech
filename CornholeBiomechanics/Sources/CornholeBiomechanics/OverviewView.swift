import SwiftUI

struct OverviewView: View {
    @EnvironmentObject private var store: ProjectStore
    @Binding var showsSettings: Bool

    var body: some View {
        SectionContainer(
            title: "Study Rationale",
            subtitle: "Movement and outcome belong in the same evidence trail."
        ) {
            ResearchCard(title: "Primary research question", symbol: "questionmark.circle") {
                Text("Can a single-camera, markerless 2D video-analysis system quantify upper-body cornhole throwing kinematics in a repeatable and interpretable way, normalize those measurements across athletes with different body sizes and proportions, and identify which movement features or deviations from a coach-selected reference pattern are associated with task performance?")
            }
            ResearchCard(title: "Secondary research question", symbol: "person.crop.circle.badge.questionmark") {
                Text("For an individual athlete, are better cornhole outcomes associated more strongly with similarity to a reference technique, with consistency of their own technique, or with specific kinematic features such as elbow motion, arm trajectory, trunk orientation, and timing?")
            }
            ResearchCard(title: "Why this matters", symbol: "heart.text.square") {
                Text("Cornhole scores tell a coach what happened, but not why it happened. Laboratory motion capture can provide detailed biomechanics, but it is expensive, time-consuming, and impractical for routine training. If ordinary phone video can provide sufficiently repeatable upper-body kinematics, a coach could obtain individualized, evidence-based feedback during normal practice. The system must account for body-size differences, camera limitations, measurement uncertainty, and the possibility that more than one successful throwing strategy exists.")
            }
            HStack(alignment: .top, spacing: 16) {
                CameraGuideCard()
                ResearchCard(title: "Scientific boundaries", symbol: "checkmark.shield") {
                    Label("Projected 2D measurements—not true 3D joint orientation", systemImage: "view.2d")
                    Label("Reference similarity—not performance quality", systemImage: "arrow.left.and.right")
                    Label("Within-athlete association—not causation", systemImage: "chart.xyaxis.line")
                    Label("Real participant data remains required", systemImage: "person.badge.clock")
                }
            }
            HStack {
                Button("Advanced Analysis Settings…") { showsSettings = true }
                Button("Show Project in Finder") { store.revealProject() }
            }
        }
    }
}

struct CameraGuideCard: View {
    var body: some View {
        ResearchCard(title: "Camera Setup / Recording Guide", symbol: "camera") {
            Text("Primary Stage 1 view: side / sagittal-like").font(.subheadline.weight(.semibold))
            VStack(alignment: .leading, spacing: 6) {
                Label("Fix the phone on a tripod or stable support.", systemImage: "checkmark")
                Label("Keep the optical axis perpendicular to the motion plane.", systemImage: "checkmark")
                Label("Keep the upper body and throwing arm fully visible.", systemImage: "checkmark")
                Label("Use consistent framing, lighting, and camera position.", systemImage: "checkmark")
                Label("Record at 60 fps or higher when available.", systemImage: "checkmark")
                Label("Avoid digital zoom, motion blur, and handheld movement.", systemImage: "checkmark")
            }.font(.callout)
            Text("Different view labels are not compared as though they measure the same quantity.")
                .font(.caption).foregroundStyle(.secondary)
        }
    }
}
