// Recognition-mode CaptureLifecycle with injected synthetic frames (no screen capture), as
// android RecognitionLifecycleTest.kt: selection, strided FrameView, RecognitionSession, compute
// runner and serial-queue commit with generation, deadline and entitlement re-checks.
import XCTest
@testable import DetectAClipCore

private final class Proj: ProjectionHandle {
    var stops = 0, releases = 0
    var onStop: (() -> Void)?
    func stop() { stops += 1; onStop?() }
    func release() { releases += 1 }
}

private final class NoBackground: BackgroundTaskGuard {
    func begin(onExpire: @escaping () -> Void) -> Bool { true }
    func end() {}
    var remainingMs: Int64? { nil }
}

private final class ManualCompute: ComputeRunner {
    final class Token: Cancellable { var cancelled = false; func cancel() { cancelled = true } }
    var token = Token()
    var submitted = 0
    private var work: ((() -> Bool) -> WorkOutcome?)?
    private var done: ((WorkOutcome?) -> Void)?
    func submit(_ work: @escaping (() -> Bool) -> WorkOutcome?, onDone: @escaping (WorkOutcome?) -> Void) -> Cancellable {
        submitted += 1; token = Token(); self.work = work; self.done = onDone; return token
    }
    /// Runs the work; `midWork` fires at the session's second cancellation check.
    func finish(midWork: (() -> Void)? = nil) {
        guard let w = work, let d = done else { return }
        work = nil; done = nil
        let t = token
        var calls = 0
        d(w { calls += 1; if calls == 2 { midWork?() }; return t.cancelled })
    }
}

final class RecognitionLifecycleTests: XCTestCase {
    var now: Int64 = 0
    var entitled = true
    var mainQueue: [() -> Void] = []

    private func rig(deferMain: Bool = false, synthetic: Bool = true) throws -> (ScanCoordinator, CaptureLifecycle, ManualCompute, Proj) {
        now = 0; entitled = true; mainQueue = []
        let pack = try Golden.pipelinePack()
        let c = ScanCoordinator(canAttributeNormalClose: true, idSource: { "s" })
        let comp = ManualCompute(), p = Proj()
        var th = Recognition.Thresholds(); th.radius = 9
        let l = CaptureLifecycle(coordinator: c, clock: { [unowned self] in self.now }, compute: comp, background: NoBackground(),
                                 postToQueue: { [unowned self] f in if deferMain { self.mainQueue.append(f) } else { f() } },
                                 recognizer: { RecognitionSession(pack: pack, thresholds: th, topK: 12, mirrorInvariant: true) },
                                 entitlementCheck: { [unowned self] in self.entitled }, syntheticPack: synthetic)
        p.onStop = { [unowned l] in l.onCaptureStopped() }
        return (c, l, comp, p)
    }

    private func plane(_ seed: UInt32) -> (bytes: [UInt8], rowStride: Int) {
        Compose.paddedRGBA(DacDhash.contentFrame(seed: seed, w: 64, h: 36), 64, 36, pad: 12)
    }

    private func process(_ l: CaptureLifecycle, _ ts: Int64, _ seed: UInt32) throws -> String {
        let pl = plane(seed)
        return try pl.bytes.withUnsafeBytes { b in
            try l.processFrame(timestampMs: ts, view: FrameView(base: b, width: 64, height: 36, rowStride: pl.rowStride, pixelStride: 4))
        }
    }

    /// Delivers frames every 100 ms for 8 s; seedAt maps scan time to content.
    private func acquire(_ c: ScanCoordinator, _ l: CaptureLifecycle, _ p: Proj, _ seedAt: (Int64) -> UInt32) throws {
        XCTAssertTrue(c.start(now)); now += 100
        XCTAssertTrue(c.permissionGranted(now))
        XCTAssertTrue(l.attach(p))
        let t0 = now
        for k in 0..<80 {
            now = t0 + Int64(k) * 100
            if let ts = l.acceptFrame() {
                defer { l.frameDone() }
                let seed = seedAt(ts - t0)
                let flag = try process(l, ts - t0, seed)
                XCTAssertEqual(flag, "OK")
            }
        }
        now = t0 + 12_100; l.tick()
    }

    private static func sw001(_ t: Int64) -> UInt32 { UInt32(20_000 + (6_000 + t) / 500) }
    private static func sw101(_ t: Int64) -> UInt32 { UInt32(50_000 + (6_000 + t) / 500) }

    func testRecognitionCommitsWorkFromInjectedFrames() throws {
        let (c, l, comp, p) = try rig()
        try acquire(c, l, p, Self.sw001)
        XCTAssertEqual(l.mode, "RECOGNITION")
        XCTAssertEqual(l.processedFrames, 16)
        XCTAssertEqual(comp.submitted, 1)
        now += 500; comp.finish()
        XCTAssertEqual(c.state, .committed)
        let r = c.result!
        XCTAssertEqual(r.outcome, .verifiedMatch)
        XCTAssertEqual(r.candidateWorkId, "SW001")
        XCTAssertEqual(r.candidateEditionId, "E0_THEATRICAL")
        XCTAssertTrue(r.flags.contains("SYNTHETIC_L0"))
    }

    func testSeriesEpisodeIsCarriedToTheResult() throws {
        let (c, l, comp, p) = try rig()
        try acquire(c, l, p, Self.sw101)
        now += 500; comp.finish()
        XCTAssertEqual(c.result?.outcome, .verifiedMatch)
        XCTAssertEqual(c.result?.candidateWorkId, "S-P")
        XCTAssertEqual(c.result?.candidateEpisodeId, "E02")
    }

    func testAbsentContentGivesNoConfidentMatch() throws {
        let (c, l, comp, p) = try rig()
        try acquire(c, l, p) { UInt32(777_000 + $0 / 500) }
        now += 500; comp.finish()
        XCTAssertEqual(c.result?.outcome, .noConfidentMatch)
        XCTAssertNil(c.result?.candidateWorkId)
    }

    func testCancelDuringVerificationNeverCommits() throws {
        let (c, l, comp, p) = try rig()
        try acquire(c, l, p, Self.sw001)
        comp.finish(midWork: { l.userCancel() })
        XCTAssertTrue(comp.token.cancelled)
        XCTAssertEqual(c.state, .cancelled)
        XCTAssertEqual(c.commits, 0)
    }

    func testLateWorkerCallbackAfterLockIsStale() throws {
        let (c, l, comp, p) = try rig(deferMain: true)
        try acquire(c, l, p, Self.sw001)
        comp.finish()
        now += 200; l.deviceLocked()
        mainQueue.forEach { $0() }
        XCTAssertEqual(c.state, .cancelled)
        XCTAssertEqual(c.staleWorkerResults, 1)
        XCTAssertEqual(c.commits, 0)
    }

    func testCommitAfterPostCaptureDeadlineFails() throws {
        let (c, l, comp, p) = try rig(deferMain: true)
        try acquire(c, l, p, Self.sw001)
        comp.finish()
        now += 8_001
        mainQueue.forEach { $0() }
        XCTAssertEqual(c.state, .failed)
        XCTAssertEqual(c.closedReason, "POST_CAPTURE_DEADLINE_EXPIRED")
    }

    func testEntitlementIsRecheckedAtCommit() throws {
        let (c, l, comp, p) = try rig(deferMain: true)
        try acquire(c, l, p, Self.sw001)
        comp.finish()
        entitled = false
        mainQueue.forEach { $0() }
        XCTAssertEqual(c.state, .failed)
        XCTAssertEqual(c.result?.outcome, .error)
        XCTAssertNil(c.result?.candidateWorkId)
    }

    func testLateFramesAfterCloseAreRefused() throws {
        let (c, l, _, p) = try rig()
        try acquire(c, l, p, Self.sw001)
        let before = l.processedFrames
        now += 600
        XCTAssertNil(l.acceptFrame())
        XCTAssertEqual(try process(l, now, 1), "CLOSED")
        XCTAssertEqual(l.processedFrames, before)
        XCTAssertEqual(p.stops, 1)
        XCTAssertEqual(p.releases, 1)
    }

    func testLicensedPackResultIsNotFlaggedSynthetic() throws {
        let (c, l, comp, p) = try rig(synthetic: false)
        try acquire(c, l, p, Self.sw001)
        comp.finish()
        XCTAssertFalse(c.result!.flags.contains("SYNTHETIC_L0"))
    }
}
