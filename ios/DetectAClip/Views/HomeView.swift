import DetectAClipCore
import SwiftUI

struct HomeView: View {
    @ObservedObject var scans: ScanController
    @ObservedObject var terms: TermsStore

    private var consentPresented: Binding<Bool> {
        Binding(
            get: {
                if case .awaitingConsent = scans.phase { return true }
                return false
            },
            set: { presented in
                if !presented { scans.consentDeclined() }
            }
        )
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    SyntheticBanner()
                    switch scans.phase {
                    case .idle, .awaitingConsent:
                        IdlePanel(scans: scans)
                    case let .acquiring(_, _, sampled):
                        AcquiringPanel(preview: scans.preview, sampled: sampled, stop: scans.stopCapture)
                    case .computing:
                        ComputingPanel(cancel: scans.cancelComputation)
                    case let .finished(outcome):
                        ResultPanel(outcome: outcome, scans: scans)
                    }
                }
                .padding()
            }
            .navigationTitle("Detect A Clip")
            .toolbar {
                NavigationLink {
                    LegalView(terms: terms, manifest: scans.catalogue.manifest)
                } label: {
                    Label("About and legal", systemImage: "info.circle")
                }
            }
            .sheet(isPresented: consentPresented) {
                ConsentSheet(source: scans.source,
                             confirm: scans.consentConfirmed,
                             decline: scans.consentDeclined)
            }
            .onAppear { scans.refresh() }
        }
    }
}

private struct IdlePanel: View {
    @ObservedObject var scans: ScanController

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Label("Not scanning", systemImage: "pause.circle")
                .font(.headline)
            Picker("Source", selection: $scans.source) {
                Text("Synthetic test clip").tag(CaptureSource.syntheticInApp)
                Text("Another app's screen").tag(CaptureSource.otherAppScreen)
            }
            .pickerStyle(.segmented)

            if scans.source == .syntheticInApp {
                Picker("Test clip", selection: $scans.clipChoice) {
                    ForEach(Array(scans.catalogue.works.enumerated()), id: \.offset) { index, work in
                        Text("\(work.title) (in catalogue)").tag(DemoClipChoice.catalogued(index))
                    }
                    Text("Synthetic work not in catalogue").tag(DemoClipChoice.uncatalogued)
                    Text("Blank picture").tag(DemoClipChoice.blank)
                }
                Text("The app plays a self-generated synthetic clip on its own screen and tries to recognise it. Nothing outside the app is captured.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            } else {
                Text("Capturing another app's screen is disabled in this build until the iPhone capture gate (G00) is passed. Starting will end with “capture not supported”.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }

            Button {
                scans.startTapped()
            } label: {
                Label("Start scan", systemImage: "viewfinder").frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
        }
    }
}

private struct ConsentSheet: View {
    let source: CaptureSource
    let confirm: @MainActor () -> Void
    let decline: @MainActor () -> Void

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 14) {
                Text("This scan only").font(.title2.bold())
                Text("• The app samples at most 2 pictures per second for up to 8 seconds.")
                Text("• Each picture is turned into a small fingerprint on this iPhone and thrown away. Nothing is sent anywhere.")
                Text("• **Stop** ends sampling at any time. **Cancel** stops matching after sampling. Either way, no result is produced.")
                Text("• Leaving the app or locking the phone cancels the scan.")
                if source == .otherAppScreen {
                    Text("Screen capture of other apps is disabled in this build, so this scan will end as not supported.")
                        .foregroundStyle(.orange)
                }
                Spacer()
                Button {
                    confirm()
                } label: {
                    Text("Start this scan").frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                Button("Not now", role: .cancel, action: decline)
                    .frame(maxWidth: .infinity)
            }
            .font(.callout)
            .padding()
            .navigationBarTitleDisplayMode(.inline)
        }
        .presentationDetents([.medium, .large])
        .interactiveDismissDisabled(false)
    }
}

private struct AcquiringPanel: View {
    let preview: CGImage?
    let sampled: Int
    let stop: @MainActor () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Label("Sampling synthetic clip…", systemImage: "record.circle")
                .font(.headline)
                .foregroundStyle(.red)
            ZStack(alignment: .topLeading) {
                if let preview {
                    Image(decorative: preview, scale: 1)
                        .resizable()
                        .interpolation(.none)
                        .aspectRatio(4 / 3, contentMode: .fit)
                } else {
                    Rectangle().fill(.gray.opacity(0.2)).aspectRatio(4 / 3, contentMode: .fit)
                }
                Text("SYNTHETIC")
                    .font(.caption2.bold())
                    .padding(4)
                    .background(.black.opacity(0.6))
                    .foregroundStyle(.white)
                    .padding(6)
            }
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .accessibilityLabel("Synthetic test clip playing")
            Text("\(sampled) frame(s) sampled")
                .font(.footnote)
                .foregroundStyle(.secondary)
            Button(role: .destructive, action: stop) {
                Label("Stop", systemImage: "stop.fill").frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .accessibilityHint("Stops sampling. No result will be produced.")
        }
    }
}

private struct ComputingPanel: View {
    let cancel: @MainActor () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Label("Sampling closed — matching on this iPhone…", systemImage: "cpu")
                .font(.headline)
            ProgressView()
            Button(role: .cancel, action: cancel) {
                Text("Cancel matching").frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
            .controlSize(.large)
        }
    }
}

private struct ResultPanel: View {
    let outcome: ScanOutcome
    @ObservedObject var scans: ScanController

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Label(headline, systemImage: symbol)
                .font(.title3.bold())
                .foregroundStyle(tint)
            if let work = outcome.decision?.work {
                HStack {
                    Text(work.title).font(.title2)
                    Text("SYNTHETIC")
                        .font(.caption2.bold())
                        .padding(4)
                        .background(Color.orange.opacity(0.2), in: RoundedRectangle(cornerRadius: 4))
                }
            }
            Text(explanation)
                .font(.callout)
            if let decision = outcome.decision {
                Text("Evidence: \(decision.matchedFrames) of \(decision.usableFrames) usable frames matched (\(decision.sampledFrames) sampled). Lab thresholds are \(DecisionPolicy.calibrationStatus); no confidence score is shown.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            Text("Kept in memory only, until the next scan, Discard, or 15 minutes.")
                .font(.footnote)
                .foregroundStyle(.secondary)
            HStack {
                Button("Discard", role: .destructive, action: scans.discard)
                    .buttonStyle(.bordered)
                Spacer()
                Button {
                    scans.startTapped()
                } label: {
                    Label("Scan again", systemImage: "arrow.clockwise")
                }
                .buttonStyle(.borderedProminent)
            }
        }
    }

    private var headline: String {
        switch outcome.state {
        case .verifiedMatch: return "Match found"
        case .possibleMatch: return "Possible match — uncertain"
        case .noConfidentMatch: return "No confident match"
        case .outsideCatalogue: return "Outside catalogue"
        case .insufficientSignal: return "Not enough picture to match"
        case .unsupportedCapture: return "Capture not supported"
        case .permissionDenied: return "Permission not given"
        case .cancelled: return cancelledHeadline
        case .error: return "Something went wrong"
        }
    }

    private var cancelledHeadline: String {
        switch outcome.reason {
        case .userStoppedCapture: return "Stopped"
        case .userCancelledComputation: return "Matching cancelled"
        case .deviceLocked: return "Cancelled — phone locked"
        case .appLeftForeground: return "Cancelled — app left"
        case .postCaptureTimeout, .totalTimeout: return "Timed out"
        default: return "Cancelled"
        }
    }

    private var explanation: String {
        switch outcome.state {
        case .verifiedMatch:
            return "The sampled frames match this synthetic work in order."
        case .possibleMatch:
            return "Some frames resemble this synthetic work, but the evidence is weak or out of order. Treat it as a guess."
        case .noConfidentMatch:
            return "Nothing in the on-device catalogue matched well enough. This does not mean the clip is absent from the catalogue."
        case .outsideCatalogue:
            return "This state is reserved and is never produced by this build."
        case .insufficientSignal:
            return "The picture was too flat or too short to recognise. Try again while something is moving on screen."
        case .unsupportedCapture:
            return "Recognising clips playing in another app needs screen capture, which is disabled in this lab build until it has been tested on a real iPhone. Try the synthetic test clip instead."
        case .permissionDenied:
            return "Screen recording was not allowed, so nothing was captured."
        case .cancelled:
            return "The scan was cancelled before a result was committed. Nothing was kept."
        case .error:
            return "The scan could not complete. Nothing was kept."
        }
    }

    private var symbol: String {
        switch outcome.state {
        case .verifiedMatch: return "checkmark.seal.fill"
        case .possibleMatch: return "questionmark.circle"
        case .cancelled: return "xmark.circle"
        case .unsupportedCapture, .permissionDenied, .error: return "exclamationmark.triangle"
        default: return "magnifyingglass"
        }
    }

    private var tint: Color {
        switch outcome.state {
        case .verifiedMatch: return .green
        case .possibleMatch: return .orange
        case .unsupportedCapture, .permissionDenied, .error: return .red
        default: return .primary
        }
    }
}
