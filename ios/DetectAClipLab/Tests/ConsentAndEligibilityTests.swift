// NOT RUN (no Mac). Mirrors android ConsentAndEligibilityTest.kt.
import XCTest
@testable import DetectAClipCore

private final class Mem: ReceiptStorage {
    var m: [String: String] = [:]
    func read(_ key: String) -> String? { m[key] }
    func write(_ key: String, _ value: String) { m[key] = value }
    func delete(_ key: String) { m[key] = nil }
}

final class ConsentAndEligibilityTests: XCTestCase {
    let en = TermsDocument(termsVersion: "1.0", locale: "en-GB", renderedText: "Terms text v1", governingLanguageVersion: "en-GB-1", disclosureVersion: "disc-1")
    let now: Int64 = 1_800_000_000_000

    func testTranslationOnlyChangeNeedsNewNotice() {
        let c = ConsentRecords(storage: Mem(), clock: { 1 })
        c.accept(en)
        let t = TermsDocument(termsVersion: "1.0", locale: "en-GB", renderedText: "Terms text v1 (fixed translation)", governingLanguageVersion: "en-GB-1", disclosureVersion: "disc-1")
        XCTAssertEqual(c.termsStatus(t), .changedNeedsNewNotice)
        XCTAssertFalse(c.scanningAllowed(t))
    }

    func testDeclineBlocksScanning() {
        let c = ConsentRecords(storage: Mem(), clock: { 1 })
        c.decline(en)
        XCTAssertEqual(c.termsStatus(en), .declined)
        XCTAssertFalse(c.scanningAllowed(en))
    }

    func testConsumerDeniedByDefaultAndLabAllowed() {
        let g = EligibilityGate(clock: { self.now })
        let cell = EligibilityGate.Cell(cellId: "I-LAB", osBuild: "27A1", labStatus: "IN_PROGRESS", consumerStatus: "BLOCKED",
                                        stopPathVerified: false, postCaptureCancelVerified: false, expiresAtEpochMs: nil)
        let pack = EligibilityGate.PackState(packId: "L0", calibrationStatus: "CALIBRATED_L0_SYNTHETIC", leaseValidUntilEpochMs: nil, timeTrustworthy: true)
        XCTAssertEqual(g.check(.lab, termsAccepted: true, cell: cell, currentOsBuild: "27A1", pack: pack), .eligible)
        XCTAssertEqual(g.check(.consumer, termsAccepted: true, cell: cell, currentOsBuild: "27A1", pack: pack), .denied("CONSUMER_CELL_BLOCKED"))
        XCTAssertEqual(g.check(.lab, termsAccepted: true, cell: cell, currentOsBuild: "27A1", pack: pack, cloudModeRequested: true), .denied("MODE_R_OFF"))
    }
}
