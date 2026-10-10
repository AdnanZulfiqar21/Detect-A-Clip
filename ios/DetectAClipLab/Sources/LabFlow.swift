// LAB journey (F03) for the iOS app, platform-independent so it runs under `swift test`:
// first use → Terms/Privacy (DRAFT; readable even if declined) → explicit acceptance → HOME.
// Per scan: local eligibility gate (P05-T03c: unsupported cell/pack denied before scanning) →
// disclosure → one coordinator start → native picker → fail-closed picker result → result on
// return. Mirrors android MainActivity. Nothing captures at launch; nothing is persisted except
// the Terms receipt and purpose choices (D08 memory-only results).
// Status: compiled and tested by the swift-core CI job; the SwiftUI shell is in ios/LabApp.

public final class LabFlow {
    public enum StartStep: Equatable { case denied(String), showDisclosure }
    public enum PickerStep: Equatable { case presentPicker, alreadyActive }

    public let terms: TermsDocument
    public let captureEnabled: Bool
    private let coordinator: ScanCoordinator
    private let consent: ConsentRecords
    private let gate: EligibilityGate
    private let clock: () -> Int64
    private let osBuild: String
    private let capability: () -> EligibilityGate.Cell?
    private let pack: () -> EligibilityGate.PackState

    /// - Parameters:
    ///   - capability: the admitted capability cell for this OS build, or nil when no capture path
    ///     is admitted (for example ScreenCaptureKit absent from the SDK, or capture disabled).
    ///   - pack: the locally active pack state (pre-acquired; no scan-triggered request).
    public init(coordinator: ScanCoordinator, consent: ConsentRecords, gate: EligibilityGate, terms: TermsDocument,
                clock: @escaping () -> Int64, osBuild: String, captureEnabled: Bool,
                capability: @escaping () -> EligibilityGate.Cell?, pack: @escaping () -> EligibilityGate.PackState) {
        self.coordinator = coordinator; self.consent = consent; self.gate = gate; self.terms = terms
        self.clock = clock; self.osBuild = osBuild; self.captureEnabled = captureEnabled
        self.capability = capability; self.pack = pack
    }

    // MARK: Terms

    public var termsStatus: ConsentRecords.TermsStatus { consent.termsStatus(terms) }
    /// Shown on launch whenever the current Terms are not accepted (including after a decline).
    public var termsPromptRequired: Bool { termsStatus != .acceptedCurrent }
    public var termsChanged: Bool { termsStatus == .changedNeedsNewNotice }
    public var scanningAllowed: Bool { consent.scanningAllowed(terms) }
    public func acceptTerms() { consent.accept(terms) }
    /// Declining from the required prompt records the decline; closing the optional view does not.
    public func closeTerms(required: Bool) { if required { consent.decline(terms) } }

    // MARK: Scan

    /// Start tapped: local eligibility only, before any OS prompt.
    public func requestStart() -> StartStep {
        let cell = captureEnabled ? capability() : nil
        switch gate.check(.lab, termsAccepted: scanningAllowed, cell: cell, currentOsBuild: osBuild, pack: pack()) {
        case .denied(let reason): return .denied(reason)
        case .eligible: return .showDisclosure
        }
    }

    /// Disclosure confirmed: begins exactly one scan; the caller then presents the native picker.
    public func confirmDisclosure() -> PickerStep {
        coordinator.start(clock()) ? .presentPicker : .alreadyActive
    }

    /// Native picker returned. A declined or empty result records PERMISSION_DENIED; a grant is
    /// accepted only while this scan still awaits it (late grants after Cancel are refused).
    /// Returns true iff the caller may attach the capture stream.
    public func pickerResult(granted: Bool) -> Bool {
        let now = clock()
        guard granted else { coordinator.permissionDenied(now); return false }
        return coordinator.permissionGranted(now)
    }

    public func cancel() { coordinator.cancel(clock()) }
    public func discard() { coordinator.discard() }
    public func tick() { coordinator.tick(clock()) }
    public var state: ScanCoordinator.State { coordinator.state }

    /// On return to the app: an expired result or untrusted clock drops it (memory only).
    public func onReturn(clockTrustworthy: Bool = true) { _ = coordinator.returnToApp(clock(), clockTrustworthy: clockTrustworthy) }

    // MARK: Presentation (plain text; the app localizes the fixed phrases)

    public static func outcomeText(_ o: ScanCoordinator.Outcome) -> String {
        switch o {
        case .verifiedMatch: return "Match"
        case .possibleMatch: return "Possible match, not confirmed"
        case .noConfidentMatch: return "NO_CONFIDENT_MATCH"
        case .insufficientSignal: return "INSUFFICIENT_SIGNAL"
        case .unsupportedCapture: return "UNSUPPORTED_CAPTURE"
        case .permissionDenied: return "PERMISSION_DENIED"
        case .cancelled: return "CANCELLED"
        case .error: return "ERROR"
        }
    }

    /// Every named candidate is labelled SYNTHETIC: L0 packs are synthetic only.
    public static func resultLine(_ r: ScanCoordinator.Result, displayName: String? = nil) -> String {
        let outcome = outcomeText(r.outcome)
        guard let id = r.candidateWorkId else { return "Result: \(outcome)" }
        return "Result: \(outcome) — \(displayName ?? id) (SYNTHETIC)"
    }

    public func statusLines() -> [String] {
        var lines: [String] = []
        if !scanningAllowed { lines.append("Terms not accepted: scanning is off. Legal pages stay available.") }
        lines.append("State: \(String(describing: coordinator.state))")
        if let r = coordinator.result {
            lines.append(LabFlow.resultLine(r))
            if !r.flags.isEmpty { lines.append(r.flags.joined(separator: ", ")) }
        } else {
            lines.append("NOT SCANNING / no result")
        }
        return lines
    }
}
