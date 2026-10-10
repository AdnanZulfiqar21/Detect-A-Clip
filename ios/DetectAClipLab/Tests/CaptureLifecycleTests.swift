// Mirrors android CaptureLifecycleTest.kt (DIAGNOSTIC mode) plus background-task expiry.
import XCTest
@testable import DetectAClipCore

private final class FakeProjection: ProjectionHandle {
    var stops = 0, releases = 0
    func stop() { stops += 1 }
    func release() { releases += 1 }
}

private final class FakeBackground: BackgroundTaskGuard {
    var began = 0, ended = 0, refuse = false
    var onExpire: (() -> Void)?
    func begin(onExpire: @escaping () -> Void) -> Bool { began += 1; self.onExpire = onExpire; return !refuse }
    func end() { ended += 1 }
    var remainingMs: Int64? { 25_000 }
}

private final class ManualCompute: ComputeRunner {
    final class Token: Cancellable { var cancelled = false; func cancel() { cancelled = true } }
    var token = Token()
    var work: ((() -> Bool) -> WorkOutcome?)?
    var done: ((WorkOutcome?) -> Void)?
    func submit(_ work: @escaping (() -> Bool) -> WorkOutcome?, onDone: @escaping (WorkOutcome?) -> Void) -> Cancellable {
        token = Token(); self.work = work; self.done = onDone; return token
    }
    func finish() { guard let w = work, let d = done else { return }; work = nil; done = nil; let t = token; d(w { t.cancelled }) }
}

final class CaptureLifecycleTests: XCTestCase {
    var now: Int64 = 0

    private func rig(attributable: Bool = true) -> (ScanCoordinator, CaptureLifecycle, ManualCompute, FakeProjection, FakeBackground) {
        now = 0
        let c = ScanCoordinator(canAttributeNormalClose: attributable)
        let comp = ManualCompute(), bg = FakeBackground(), p = FakeProjection()
        let l = CaptureLifecycle(coordinator: c, clock: { [unowned self] in self.now }, compute: comp, background: bg, postToQueue: { $0() })
        return (c, l, comp, p, bg)
    }

    private func acquire(_ c: ScanCoordinator, _ l: CaptureLifecycle, _ p: FakeProjection) {
        XCTAssertTrue(c.start(now)); l.requestBackgroundEarly(); now += 100
        XCTAssertTrue(c.permissionGranted(now)); XCTAssertTrue(l.attach(p))
        for _ in 0..<40 { now += 250; if l.onFrame() { l.frameDone() } }
        now = 100 + 12_000 + 300
        l.tick()
        l.onCaptureStopped() // asynchronous ack of our own stop
    }

    func testNormalScanCommitsAndEndsBackgroundTask() {
        let (c, l, comp, p, bg) = rig()
        acquire(c, l, p)
        now += 1_000; comp.finish()
        XCTAssertEqual(c.state, .committed)
        XCTAssertEqual(c.result?.flags, ["LAB_DUMMY_COMPUTE"])
        XCTAssertEqual(p.stops, 1)
        XCTAssertEqual(bg.began, 1); XCTAssertEqual(bg.ended, 1)
    }

    func testBackgroundExpiryDuringComputeCancels() {
        let (c, l, comp, p, bg) = rig()
        acquire(c, l, p)
        bg.onExpire?()
        comp.finish()
        XCTAssertEqual(c.state, .failed)
        XCTAssertEqual(c.commits, 0)
        XCTAssertEqual(bg.ended, 1)
    }

    func testUnattributableAckFailsClosed() {
        let (c, l, comp, p, _) = rig(attributable: false)
        acquire(c, l, p)
        comp.finish()
        XCTAssertEqual(c.state, .cancelled)
        XCTAssertEqual(c.commits, 0)
    }

    func testLockAfterCloseCancels() {
        let (c, l, comp, p, _) = rig()
        acquire(c, l, p)
        l.deviceLocked(); comp.finish()
        XCTAssertEqual(c.state, .cancelled)
    }
}
