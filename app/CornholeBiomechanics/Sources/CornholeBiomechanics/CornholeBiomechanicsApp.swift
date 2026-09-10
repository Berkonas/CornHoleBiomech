import SwiftUI
import AppKit

extension Notification.Name {
    static let createStudyProject = Notification.Name("createStudyProject")
    static let openStudyProject = Notification.Name("openStudyProject")
    static let importLegacyProject = Notification.Name("importLegacyProject")
    static let addAthlete = Notification.Name("addAthlete")
    static let importTrialVideo = Notification.Name("importTrialVideo")
    static let importReferenceVideo = Notification.Name("importReferenceVideo")
    static let analyzeSelectedTrial = Notification.Name("analyzeSelectedTrial")
    static let addTrialOutcome = Notification.Name("addTrialOutcome")
    static let exportSelectedTrial = Notification.Name("exportSelectedTrial")
}

@main
struct CornholeBiomechanicsApp: App {
    @FocusedObject private var trackingEditor: TrialDataController?
    @AppStorage("appearance") private var appearance = "system"
    @StateObject private var store = ProjectStore()
    @StateObject private var analysis = AnalysisService()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(store)
                .environmentObject(analysis)
                .frame(minWidth: 980, minHeight: 680)
        }
        .defaultSize(width: 1240, height: 820)
        .commands {
            CommandGroup(replacing: .newItem) {
                Button("New Athlete Library…") { post(.createStudyProject) }
                    .keyboardShortcut("n", modifiers: .command)
                Button("Choose Athlete Library…") { post(.openStudyProject) }
                    .keyboardShortcut("o", modifiers: .command)
                Button("Import Legacy .cornholeproject…") { post(.importLegacyProject) }
                Divider()
                Button("Add Athlete…") { post(.addAthlete) }
            }
            CommandGroup(replacing: .undoRedo) {
                Button("Undo") { undoTrackingOrText(redo: false) }.keyboardShortcut("z", modifiers: .command)
                Button("Redo") { undoTrackingOrText(redo: true) }.keyboardShortcut("z", modifiers: [.command, .shift])
            }
            CommandMenu("Appearance") {
                Picker("Appearance", selection: $appearance) {
                    Text("Follow System").tag("system")
                    Text("Light").tag("light")
                    Text("Dark").tag("dark")
                }
            }
            CommandMenu("Throw") {
                Button("Import Throw Video…") { post(.importTrialVideo) }
                    .keyboardShortcut("i", modifiers: [.command, .shift])
                Button("Import Reference Video…") { post(.importReferenceVideo) }
                Button("Analyze Selected Trial") { post(.analyzeSelectedTrial) }
                    .keyboardShortcut("r", modifiers: [.command, .shift])
                Button("Add or Edit Outcome…") { post(.addTrialOutcome) }
                    .keyboardShortcut("u", modifiers: [.command, .shift])
                Divider()
                Button("Export Analysis…") { post(.exportSelectedTrial) }
                    .keyboardShortcut("e", modifiers: [.command, .shift])
            }
        }
    }

    private func undoTrackingOrText(redo: Bool) {
        if let text = NSApp.keyWindow?.firstResponder as? NSTextView, text.isEditable {
            if redo { text.undoManager?.redo() } else { text.undoManager?.undo() }
        } else if let trackingEditor {
            if redo { trackingEditor.correctionUndoManager.redo() } else { trackingEditor.correctionUndoManager.undo() }
        } else {
            NSApp.sendAction(NSSelectorFromString(redo ? "redo:" : "undo:"), to: nil, from: nil)
        }
    }

    private func post(_ name: Notification.Name) {
        NotificationCenter.default.post(name: name, object: nil)
    }
}
