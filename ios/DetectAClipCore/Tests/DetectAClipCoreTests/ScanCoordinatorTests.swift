import XCTest
@testable import DetectAClipCore

final class ScanCoordinatorTests: XCTestCase {
    private final class FakeClock {
        var now: TimeInterval = 1_000
    }

    private var clock = FakeClock()
    private let sample = QuerySample(time: 0, hash: 0xABCD, usable: true)
    private let decision = Decision(state: .noConfidentMatch, work: nil, matchedFrames: 0,
                                    usableFrames: 4, sampledFrames: 4)

    override func setUp() {
        clock = FakeClock()
    }

    private func makeCoordinator(capacity: Int = 3) -> ScanCoordinator {
        let clock = self.clock
        return ScanCoordinator(samplerCapacity: capacity, clock: { clock.now })
    }

    private func startScan(_ c: ScanCoordinator) -> ScanTicket {
        XCTAssertTrue(c.requestStart(source: .syntheticInApp))
        return c.confirmConsent()!
    }

    /// Feeds frames 0.5 s apart until the sampler closes acquisition.
    private func fillSampler(_ c: ScanCoordinator, _ ticket: ScanTicket) {
        while case .acquiring = c.phase {
            if let t = c.admitFrame(ticket) {
                _ = c.record(ticket, sample: QuerySample(time: t, hash: 1, usable: true))
            }
            clock.now += 0.5
        }
    }

    func testNoScanWithoutConsent() {
        let c = makeCoordinator()
        XCTAssertNil(c.confirmConsent(), "consent cannot be confirmed before Start")
        c.requestStart(source: .syntheticInApp)
        c.declineConsent()
        XCTAssertEqual(c.phase, .idle)
        XCTAssertNil(c.confirmConsent())
    }

    func testHappyPathCommitsExactlyOneResult() {
        let c = makeCoordinator()
        let ticket = startScan(c)
        fillSampler(c, ticket)
        XCTAssertEqual(c.phase, .computing(ticket))
        XCTAssertEqual(c.samplesForDecision(ticket)?.count, 3)
        let outcome = c.commit(ticket, decision: decision)
        XCTAssertEqual(outcome?.state, .noConfidentMatch)
        XCTAssertEqual(outcome?.reason, .completed)
        XCTAssertNil(c.commit(ticket, decision: decision), "second commit must be rejected")
        XCTAssertEqual(c.currentOutcome(), outcome)
    }

    func testCancelBeforeCommitWins() {
        let c = makeCoordinator()
        let ticket = startScan(c)
        fillSampler(c, ticket)
        XCTAssertTrue(c.cancel(ticket, reason: .userCancelledComputation))
        XCTAssertNil(c.commit(ticket, decision: decision), "late decision must not publish")
        XCTAssertEqual(c.currentOutcome()?.state, .cancelled)
        XCTAssertEqual(c.currentOutcome()?.reason, .userCancelledComputation)
        XCTAssertNil(c.samplesForDecision(ticket))
    }

    func testCaptureStopDuringAcquisitionCancelsAndRejectsLateFrames() {
        let c = makeCoordinator()
        let ticket = startScan(c)
        XCTAssertNotNil(c.admitFrame(ticket))
        XCTAssertTrue(c.cancel(reason: .userStoppedCapture))
        clock.now += 1
        XCTAssertNil(c.admitFrame(ticket))
        XCTAssertEqual(c.record(ticket, sample: sample), .rejected)
        XCTAssertEqual(c.currentOutcome()?.reason, .userStoppedCapture)
    }

    func testStaleTicketFromPreviousScanIsRejected() {
        let c = makeCoordinator()
        let first = startScan(c)
        c.cancel(reason: .deviceLocked)
        let second = startScan(c)
        XCTAssertNotEqual(first.scanID, second.scanID)
        XCTAssertGreaterThan(second.generation, first.generation)
        XCTAssertNil(c.admitFrame(first))
        XCTAssertEqual(c.record(first, sample: sample), .rejected)
        XCTAssertFalse(c.cancel(first, reason: .userStoppedCapture), "old ticket cannot cancel new scan")
        XCTAssertNotNil(c.admitFrame(second))
    }

    func testOnlyOneActiveSession() {
        let c = makeCoordinator()
        _ = startScan(c)
        XCTAssertFalse(c.requestStart(source: .syntheticInApp))
    }

    func testNewStartClearsPreviousResult() {
        let c = makeCoordinator()
        let ticket = startScan(c)
        fillSampler(c, ticket)
        c.commit(ticket, decision: decision)
        XCTAssertTrue(c.requestStart(source: .syntheticInApp))
        XCTAssertNil(c.currentOutcome())
    }

    func testSamplingWindowClosesNormally() {
        let c = makeCoordinator(capacity: 12)
        let ticket = startScan(c)
        clock.now += ScanDeadlines().sampling
        c.tick()
        XCTAssertEqual(c.phase, .computing(ticket))
    }

    func testPostCaptureDeadlineCancelsUncommittedWork() {
        let c = makeCoordinator()
        let ticket = startScan(c)
        fillSampler(c, ticket)
        clock.now += ScanDeadlines().postCapture + 0.1
        XCTAssertNil(c.commit(ticket, decision: decision))
        let outcome = c.currentOutcome()
        XCTAssertEqual(outcome?.state, .cancelled)
        XCTAssertTrue(outcome?.reason == .postCaptureTimeout || outcome?.reason == .totalTimeout)
    }

    func testTotalBudgetCancelsEvenWhileAcquiring() {
        let c = makeCoordinator(capacity: 12)
        _ = startScan(c)
        clock.now += ScanDeadlines().total + 1
        c.tick()
        XCTAssertEqual(c.currentOutcome()?.reason, .totalTimeout)
    }

    func testResultExpiresAfterFifteenMinutes() {
        let c = makeCoordinator()
        let ticket = startScan(c)
        fillSampler(c, ticket)
        c.commit(ticket, decision: decision)
        clock.now += ScanCoordinator.resultValidity - 1
        XCTAssertNotNil(c.currentOutcome())
        clock.now += 2
        XCTAssertNil(c.currentOutcome())
        XCTAssertEqual(c.phase, .idle)
    }

    func testDiscardClearsResult() {
        let c = makeCoordinator()
        let ticket = startScan(c)
        fillSampler(c, ticket)
        c.commit(ticket, decision: decision)
        c.discard()
        XCTAssertNil(c.currentOutcome())
    }

    func testDisabledCaptureEndsAsUnsupported() {
        let c = makeCoordinator()
        c.requestStart(source: .otherAppScreen)
        let ticket = c.confirmConsent()!
        let outcome = c.fail(ticket, state: .unsupportedCapture, reason: .captureDisabledInBuild)
        XCTAssertEqual(outcome?.state, .unsupportedCapture)
        XCTAssertNil(c.fail(ticket, state: .error, reason: .internalError), "already finished")
    }

    func testConcurrentCancelAndCommitPublishAtMostOneOutcome() {
        for _ in 0..<200 {
            let c = ScanCoordinator(samplerCapacity: 1)
            c.requestStart(source: .syntheticInApp)
            let ticket = c.confirmConsent()!
            _ = c.admitFrame(ticket)
            XCTAssertEqual(c.record(ticket, sample: sample), .recordedAndClosed)
            var committed: ScanOutcome?
            var cancelled = false
            DispatchQueue.concurrentPerform(iterations: 2) { i in
                if i == 0 {
                    committed = c.commit(ticket, decision: decision)
                } else {
                    cancelled = c.cancel(ticket, reason: .userCancelledComputation)
                }
            }
            let final = c.currentOutcome()
            if let committed {
                XCTAssertFalse(cancelled, "cancel after commit must be a no-op")
                XCTAssertEqual(final, committed)
            } else {
                XCTAssertTrue(cancelled)
                XCTAssertEqual(final?.state, .cancelled)
            }
        }
    }
}
