import SwiftUI

struct OverviewView: View {
    @EnvironmentObject private var store: ProjectStore
    @Binding var showsSettings: Bool
    @State private var newSession = false
    var body: some View {
        SectionContainer(title: store.project?.name ?? "Your study", subtitle: "Connect how an athlete throws with where the bag lands.") {
            HStack(spacing: 14) {
                Button("Add an athlete") { store.selectedSection = .athletes }
                Button("Start session…") { newSession = true }.buttonStyle(.borderedProminent).disabled(store.project?.athletes.isEmpty != false)
                Button("Import a throw…") { NotificationCenter.default.post(name: .importTrialVideo, object: nil) }.disabled(store.project?.athletes.isEmpty != false)
                Spacer()
            }
            if !(store.project?.sessions ?? []).isEmpty {
                Picker("Recording session", selection: $store.selectedSessionID) {
                    Text("No session selected").tag(UUID?.none)
                    ForEach(store.project?.sessions ?? []) { Text("\($0.name) · \($0.date.formatted(date: .abbreviated, time: .omitted))").tag(Optional($0.id)) }
                }.frame(maxWidth: 550)
                if let session = store.project?.sessions?.first(where: { $0.id == store.selectedSessionID }) {
                    Text("\(session.cameraSetup) · \(session.cameraView.label) · \(store.project?.trials.filter { $0.sessionID == session.id }.count ?? 0) throws").foregroundStyle(.secondary)
                }
            }
            Divider()
            Text("From recording to insight").font(.title2.weight(.semibold))
            ForEach(Array([("1","Import & analyze","Choose a local recording. Sports2D tracks the body; the lab measures the throw."),("2","Verify & add outcome","Review the wrist and elbow, correct the release candidate, and record 0, 1 or 3 points."),("3","Understand & compare","See movement differences, bag locations and the reliability of each analysis."),("4","Learn across throws","Keep collecting comparable trials to examine repeatability and movement–outcome relationships.")].enumerated()),id:\.offset) { _, item in
                HStack(alignment:.top,spacing:18) { Text(item.0).font(.title2.monospacedDigit()).foregroundStyle(athleteInk).frame(width:24); VStack(alignment:.leading,spacing:5) { Text(item.1).font(.headline);Text(item.2).foregroundStyle(.secondary) } }.padding(.vertical,6)
            }
            Divider()
            Text("Three separate questions").font(.title2.weight(.semibold))
            Text("Reference Similarity measures resemblance to a selected pattern. Athlete Consistency measures repeatability. Performance relationships examine whether movement features vary with outcomes. A successful throw can look different from the reference.")
            DisclosureGroup("The research question & Stage 1 scope") {
                Text("Can single-camera markerless video quantify upper-body cornhole kinematics repeatably, normalize measurements across different bodies, and identify movement features associated with task performance?")
                Text("Stage 1 measures projected 2D movement. Real participant data and validation are required before claims about measurement accuracy or training benefits.").foregroundStyle(.secondary)
            }
            CameraGuideCard()
            HStack { Button("Advanced Analysis…") { showsSettings = true }; Button("Show project in Finder") { store.revealProject() } }
        }.sheet(isPresented:$newSession) { SessionForm() }
    }
}
struct CameraGuideCard: View {
    var body: some View {
        DisclosureGroup("Record a useful side-view video") {
            VStack(alignment:.leading,spacing:8) {
                Text("Fix the phone on a tripod. Film perpendicular to the throwing plane, without panning or changing zoom.")
                Text("Keep both shoulders, both hips and the whole throwing arm visible. Use clear lighting and 60 fps or higher when available.")
                Text("Keep the same setup across the session. Different camera views cannot be treated as equivalent measurements.")
            }.foregroundStyle(.secondary)
        }
    }
}
