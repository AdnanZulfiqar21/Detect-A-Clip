// iOS LAB app state: a thin SwiftUI wrapper around DetectAClipCore.LabFlow (the tested journey).
// Capture stays disabled (Info.plist DACCaptureEnabled = false) and no capability cell is
// admitted: the hosted Xcode 26.6 / iOS 26.5 SDK has no ScreenCaptureKit framework, so Start is
// denied before any OS prompt (P05-T03c). Nothing is persisted except the Terms receipt.
import Foundation
import UIKit
import DetectAClipCore

/// Terms receipt and purpose choices only, in the app's own UserDefaults domain.
final class DefaultsStorage: ReceiptStorage {
    private let d = UserDefaults.standard
    static let keys = ["terms.receipt", "terms.declined"]
    func read(_ key: String) -> String? { d.string(forKey: "dac." + key) }
    func write(_ key: String, _ value: String) { d.set(value, forKey: "dac." + key) }
    func delete(_ key: String) { d.removeObject(forKey: "dac." + key) }
}

/// Finite background task (V16): requested early, ended on completion or expiry; expiry
/// cancels the scan. No audio keepalive. Used by the capture lifecycle once a path exists.
final class UIKitBackgroundTask: BackgroundTaskGuard {
    private var id: UIBackgroundTaskIdentifier = .invalid
    func begin(onExpire: @escaping () -> Void) -> Bool {
        id = UIApplication.shared.beginBackgroundTask(withName: "dac.scan") { [weak self] in
            onExpire()
            self?.end()
        }
        return id != .invalid
    }
    func end() {
        if id != .invalid { UIApplication.shared.endBackgroundTask(id); id = .invalid }
    }
    /// Diagnostic only; never a promised grant.
    var remainingMs: Int64? {
        let t = UIApplication.shared.backgroundTimeRemaining
        return t.isFinite ? Int64(t * 1000) : nil
    }
}

@MainActor
final class LabViewModel: ObservableObject {
    @Published private(set) var lines: [String] = []
    @Published private(set) var startEnabled = false
    @Published private(set) var message: String?
    @Published var showTerms = false
    @Published private(set) var termsRequired = false
    @Published var showDisclosure = false

    static let captureEnabled: Bool = (Bundle.main.object(forInfoDictionaryKey: "DACCaptureEnabled") as? Bool) ?? false
    static let termsText = """
        DRAFT, not legally reviewed, lab use only. Each scan needs your tap and the system's permission. \
        Frames are processed in memory on this phone and never saved or sent. Results expire after 15 minutes \
        and are lost if the app is closed. Matches come from a synthetic test catalogue only.
        """
    static let disclosureText = """
        iOS will ask you to share your screen. Only frames from this scan are used, in memory on this phone, \
        and nothing leaves the device. To stop capture use the system control or Stop / Cancel here; \
        after capture ends, Stop / Cancel also discards the matching.
        """

    let flow: LabFlow
    private let coordinator: ScanCoordinator
    private var timer: Timer?

    init() {
        if ProcessInfo.processInfo.arguments.contains("-DACResetForUITest") {
            let d = UserDefaults.standard
            DefaultsStorage.keys.forEach { d.removeObject(forKey: "dac." + $0) }
        }
        let wall: () -> Int64 = { Int64(Date().timeIntervalSince1970 * 1000) }
        let monotonic: () -> Int64 = { Int64(ProcessInfo.processInfo.systemUptime * 1000) }
        let c = ScanCoordinator()
        coordinator = c
        flow = LabFlow(
            coordinator: c,
            consent: ConsentRecords(storage: DefaultsStorage(), clock: wall),
            gate: EligibilityGate(clock: wall),
            terms: TermsDocument(termsVersion: "0.1-draft", locale: "en-GB", renderedText: LabViewModel.termsText,
                                 governingLanguageVersion: "en-GB-draft", disclosureVersion: "lab-disclosure-1"),
            clock: monotonic,
            osBuild: ProcessInfo.processInfo.operatingSystemVersionString,
            captureEnabled: LabViewModel.captureEnabled,
            capability: { nil },     // no admitted iOS capture cell (ScreenCaptureKit absent from this SDK; B-02)
            pack: { EligibilityGate.PackState(packId: "L0-SYNTH-DUMMY", calibrationStatus: "UNCALIBRATED",
                                              leaseValidUntilEpochMs: nil, timeTrustworthy: true) })
        termsRequired = flow.termsPromptRequired
        showTerms = termsRequired
        refresh()
    }

    var termsChanged: Bool { flow.termsChanged }

    func refresh() {
        startEnabled = flow.scanningAllowed
        lines = flow.statusLines()
    }

    /// Opened from the button: readable any time; Close does not record a decline (as on Android).
    func openTerms() { termsRequired = false; showTerms = true }

    func acceptTerms() { flow.acceptTerms(); showTerms = false; refresh() }

    func closeTerms() { flow.closeTerms(required: termsRequired); showTerms = false; refresh() }

    func start() {
        message = nil
        switch flow.requestStart() {
        case .denied(let reason): message = "Scanning unavailable: \(reason)"
        case .showDisclosure: showDisclosure = true
        }
        refresh()
    }

    func continueAfterDisclosure() {
        guard flow.confirmDisclosure() == .presentPicker else { refresh(); return }
        presentPicker()
        startTicking()
        refresh()
    }

    /// The native picker would be presented here. This build has no admitted capture path, so
    /// the eligibility gate already refused Start; reaching this point means a configuration
    /// error, and the scan is cancelled rather than reported as a user denial.
    private func presentPicker() {
        flow.cancel()
        message = "No capture path in this build"
    }

    func stopCancel() { flow.cancel(); refresh() }

    func discard() { flow.discard(); refresh() }

    func onReturn() { flow.onReturn(); refresh() }

    private func startTicking() {
        timer?.invalidate()
        timer = Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { [weak self] t in
            Task { @MainActor in
                guard let self else { t.invalidate(); return }
                self.flow.tick()
                self.refresh()
                switch self.flow.state {
                case .idle, .committed, .cancelled, .failed: t.invalidate()
                default: break
                }
            }
        }
    }
}
