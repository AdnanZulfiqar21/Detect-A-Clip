// LabFlow (iOS LAB journey) behaviour: Terms gate, eligibility before any OS prompt, single
// start, fail-closed picker results, late grants, cancel/discard and SYNTHETIC labelling.
import XCTest
@testable import DetectAClipCore

private final class Mem: ReceiptStorage {
    var m: [String: String] = [:]
    func read(_ key: String) -> String? { m[key] }
    func write(_ key: String, _ value: String) { m[key] = value }
    func delete(_ key: String) { m[key] = nil }
}

final class LabFlowTests: XCTestCase {
    var now: Int64 = 1_800_000_000_000
    let terms = TermsDocument(termsVersion: "0.1-draft", locale: "en-GB", renderedText: "Terms v1",
                              governingLanguageVersion: "en-GB-draft", disclosureVersion: "lab-disclosure-1")
    let labCell = EligibilityGate.Cell(cellId: "I-LAB", osBuild: "27A1", labStatus: "IN_PROGRESS", consumerStatus: "BLOCKED",
                                       stopPathVerified: false, postCaptureCancelVerified: false, expiresAtEpochMs: nil)
    let pack = EligibilityGate.PackState(packId: "L0-SYNTH", calibrationStatus: "UNCALIBRATED", leaseValidUntilEpochMs: nil, timeTrustworthy: true)

    private func flow(captureEnabled: Bool = true, cell: EligibilityGate.Cell?? = nil,
                      storage: Mem = Mem()) -> (LabFlow, ScanCoordinator) {
        let c = ScanCoordinator(idSource: { "s" })
        let consent = ConsentRecords(storage: storage, clock: { [unowned self] in self.now })
        let chosen: EligibilityGate.Cell? = cell ?? labCell
        let f = LabFlow(coordinator: c, consent: consent, gate: EligibilityGate(clock: { [unowned self] in self.now }), terms: terms,
                        clock: { [unowned self] in self.now }, osBuild: "27A1", captureEnabled: captureEnabled,
                        capability: { chosen }, pack: { [unowned self] in self.pack })
        return (f, c)
    }

    func testTermsGateComesFirstAndDeclineKeepsScanningOff() {
        let (f, c) = flow()
        XCTAssertTrue(f.termsPromptRequired)
        XCTAssertEqual(f.requestStart(), .denied("TERMS_NOT_ACCEPTED"))
        f.closeTerms(required: true)
        XCTAssertEqual(f.termsStatus, .declined)
        XCTAssertTrue(f.termsPromptRequired)
        XCTAssertEqual(c.state, .idle)                               // nothing started
        f.acceptTerms()
        XCTAssertFalse(f.termsPromptRequired)
        XCTAssertEqual(f.requestStart(), .showDisclosure)
    }

    func testChangedTermsNeedANewNotice() {
        let storage = Mem()
        let (f, _) = flow(storage: storage)
        f.acceptTerms()
        let changed = TermsDocument(termsVersion: "0.1-draft", locale: "en-GB", renderedText: "Terms v1 (fixed translation)",
                                    governingLanguageVersion: "en-GB-draft", disclosureVersion: "lab-disclosure-1")
        let f2 = LabFlow(coordinator: ScanCoordinator(), consent: ConsentRecords(storage: storage, clock: { 0 }),
                         gate: EligibilityGate(clock: { 0 }), terms: changed, clock: { 0 }, osBuild: "27A1", captureEnabled: true,
                         capability: { nil }, pack: { [unowned self] in self.pack })
        XCTAssertTrue(f2.termsChanged)
        XCTAssertFalse(f2.scanningAllowed)
    }

    func testNoCapabilityCellOrCaptureDisabledDeniesBeforeAnyPrompt() {
        let (noCell, c1) = flow(cell: .some(nil))
        noCell.acceptTerms()
        XCTAssertEqual(noCell.requestStart(), .denied("NO_CAPABILITY_CELL"))
        XCTAssertEqual(c1.state, .idle)
        let (disabled, c2) = flow(captureEnabled: false)
        disabled.acceptTerms()
        XCTAssertEqual(disabled.requestStart(), .denied("NO_CAPABILITY_CELL"))
        XCTAssertEqual(c2.state, .idle)
    }

    func testDeclinedPickerFailsClosedAndLateGrantIsRefused() {
        let (f, c) = flow()
        f.acceptTerms()
        XCTAssertEqual(f.confirmDisclosure(), .presentPicker)
        XCTAssertEqual(f.confirmDisclosure(), .alreadyActive)      // one scan at a time
        XCTAssertFalse(f.pickerResult(granted: false))
        XCTAssertEqual(c.result?.outcome, .permissionDenied)
        XCTAssertFalse(f.pickerResult(granted: true))              // late grant cannot revive it
        XCTAssertEqual(f.statusLines()[1], "Result: PERMISSION_DENIED")
    }

    func testGrantAfterCancelIsRefused() {
        let (f, c) = flow()
        f.acceptTerms()
        _ = f.confirmDisclosure()
        f.cancel()
        XCTAssertFalse(f.pickerResult(granted: true))
        XCTAssertEqual(c.state, .cancelled)
    }

    func testGrantedPickerAllowsAttach() {
        let (f, c) = flow()
        f.acceptTerms()
        _ = f.confirmDisclosure()
        XCTAssertTrue(f.pickerResult(granted: true))
        XCTAssertEqual(c.state, .awaitingTarget)
    }

    func testResultsAreLabelledSyntheticAndExpireOnReturn() {
        let (f, c) = flow()
        f.acceptTerms()
        _ = f.confirmDisclosure()
        _ = f.pickerResult(granted: true)
        c.targetReady(now)
        now += 12_001; f.tick()                                    // sampling window closes
        XCTAssertEqual(c.state, .postCapture)
        XCTAssertTrue(c.workerResult(now, generation: c.generation, outcome: .verifiedMatch, workId: "SW001"))
        let line = LabFlow.resultLine(c.result!, displayName: "Synthetic Work 001")
        XCTAssertEqual(line, "Result: Match — Synthetic Work 001 (SYNTHETIC)")
        XCTAssertTrue(f.statusLines().contains("Result: Match — SW001 (SYNTHETIC)"))
        now += 15 * 60_000; f.onReturn()                           // result validity is 15 min
        XCTAssertNil(c.result)
        f.discard()
        XCTAssertEqual(f.statusLines().last, "NOT SCANNING / no result")
    }
}
