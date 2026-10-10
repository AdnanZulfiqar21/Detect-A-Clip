// Detect A Clip LAB (iOS) — SwiftUI shell over DetectAClipCore. No capture at launch.
import SwiftUI

@main
struct DetectAClipLabApp: App {
    @StateObject private var model = LabViewModel()
    @Environment(\.scenePhase) private var phase

    var body: some Scene {
        WindowGroup {
            ContentView(model: model)
                .onChange(of: phase) { _, newPhase in
                    if newPhase == .active { model.onReturn() }   // result-on-return; expired results drop
                }
        }
    }
}

struct ContentView: View {
    @ObservedObject var model: LabViewModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("Detect A Clip — LAB build (synthetic only)\nCapture enabled in this build: \(String(LabViewModel.captureEnabled))")
                    .font(.headline)
                Button("Start scan (LAB)") { model.start() }
                    .disabled(!model.startEnabled)
                    .accessibilityIdentifier("start")
                Button("Stop / Cancel") { model.stopCancel() }
                    .accessibilityLabel("Stop capture and cancel matching")
                    .accessibilityIdentifier("stop")
                Button("Discard result") { model.discard() }
                    .accessibilityIdentifier("discard")
                Button("Terms and privacy (draft)") { model.openTerms() }
                    .accessibilityIdentifier("terms")
                if let m = model.message {
                    Text(m).accessibilityIdentifier("message")
                }
                Text(model.lines.joined(separator: "\n"))
                    .font(.body.monospaced())
                    .accessibilityIdentifier("status")
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(24)
        }
        .sheet(isPresented: $model.showTerms) {
            TermsView(model: model).interactiveDismissDisabled(model.termsRequired)
        }
        .alert("Before you scan", isPresented: $model.showDisclosure) {
            Button("Continue") { model.continueAfterDisclosure() }
            Button("Not now", role: .cancel) {}
        } message: {
            Text(LabViewModel.disclosureText)
        }
    }
}

struct TermsView: View {
    @ObservedObject var model: LabViewModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("Terms and privacy (DRAFT, lab only)").font(.title2)
                if model.termsChanged {
                    Text("The terms changed (this includes translation changes). Please review them again.")
                }
                Text(LabViewModel.termsText)
                HStack {
                    Button("Accept") { model.acceptTerms() }.accessibilityIdentifier("accept")
                    Spacer()
                    Button(model.termsRequired ? "Decline" : "Close") { model.closeTerms() }.accessibilityIdentifier("decline")
                }
            }
            .padding(24)
        }
    }
}
