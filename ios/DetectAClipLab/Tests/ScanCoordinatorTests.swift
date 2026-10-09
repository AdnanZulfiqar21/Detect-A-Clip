// NOT RUN (no Mac). Mirrors l0/tests/test_coordinator.py.
import XCTest
@testable import DetectAClipCore

final class ScanCoordinatorTests: XCTestCase {
    private func toPostCapture(_ c: ScanCoordinator) -> Int64 {
        XCTAssertTrue(c.start(0))
        XCTAssertTrue(c.permissionGranted(100))
        XCTAssertTrue(c.targetReady(200))
        XCTAssertTrue(c.normalCloseRequested(8300))
        return c.generation
    }

    func testNormalScanCommitsOnceWhenAttributable() {
        let c = ScanCoordinator(canAttributeNormalClose: true)
        let g = toPostCapture(c)
        c.captureStopped(8350, cause: .appRequestedAck)
        XCTAssertTrue(c.workerResult(9000, generation: g, outcome: .verifiedMatch, workId: "SW001"))
        XCTAssertFalse(c.workerResult(9001, generation: g, outcome: .verifiedMatch, workId: "SW001"))
        XCTAssertEqual(c.commits, 1)
    }

    func testUnattributableAckFailsClosed() {
        let c = ScanCoordinator(canAttributeNormalClose: false)
        let g = toPostCapture(c)
        c.captureStopped(8350, cause: .appRequestedAck)
        XCTAssertEqual(c.state, .cancelled)
        XCTAssertFalse(c.workerResult(9000, generation: g, outcome: .verifiedMatch, workId: "SW001"))
    }

    func testBackgroundExpiryBeforeCommitCancels() {
        let c = ScanCoordinator(canAttributeNormalClose: true)
        let g = toPostCapture(c)
        c.backgroundTaskExpired(9000)
        XCTAssertFalse(c.workerResult(9100, generation: g, outcome: .verifiedMatch, workId: "SW001"))
    }

    func testLife01Orderings() {
        var rng = SystemRandomNumberGenerator()
        for _ in 0..<1000 {
            let c = ScanCoordinator(canAttributeNormalClose: Bool.random(using: &rng))
            let g = toPostCapture(c)
            let t = 8300 + Int64.random(in: 0..<7000, using: &rng)
            switch Int.random(in: 0..<4, using: &rng) {
            case 0: c.captureStopped(t, cause: .userStop)
            case 1: c.lock(t)
            case 2: c.permissionRevoked(t)
            default: c.cancel(t)
            }
            XCTAssertFalse(c.workerResult(t + 1, generation: g, outcome: .verifiedMatch, workId: "SW001"))
        }
    }

    func testResultExpiresAfter15Minutes() {
        let c = ScanCoordinator(canAttributeNormalClose: true)
        let g = toPostCapture(c)
        XCTAssertTrue(c.workerResult(9000, generation: g, outcome: .noConfidentMatch, workId: nil))
        XCTAssertNotNil(c.returnToApp(9000 + 60_000))
        XCTAssertNil(c.returnToApp(9000 + 16 * 60_000))
    }
}
