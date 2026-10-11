// Capture-boundary regressions, mirroring android CaptureBoundaryTest.kt: picker denial fails
// closed, nothing captures without an explicit start + grant, and malformed frame geometry is
// refused before any unchecked read.
import XCTest
@testable import DetectAClipCore

private final class Handle: ProjectionHandle {
    var stops = 0, releases = 0
    func stop() { stops += 1 }
    func release() { releases += 1 }
}

private final class NoCompute: ComputeRunner {
    final class Token: Cancellable { func cancel() {} }
    func submit(_ work: @escaping (() -> Bool) -> WorkOutcome?, onDone: @escaping (WorkOutcome?) -> Void) -> Cancellable { Token() }
}

private final class NoBackground: BackgroundTaskGuard {
    func begin(onExpire: @escaping () -> Void) -> Bool { true }
    func end() {}
    var remainingMs: Int64? { nil }
}

final class CaptureBoundaryTests: XCTestCase {
    func testDeclinedPickerRecordsPermissionDenied() {
        let c = ScanCoordinator(idSource: { "s" })
        XCTAssertTrue(c.start(0))
        c.permissionDenied(100)
        XCTAssertEqual(c.state, .failed)
        XCTAssertEqual(c.result?.outcome, .permissionDenied)
        XCTAssertNil(c.result?.candidateWorkId)
        XCTAssertFalse(c.permissionGranted(200))       // a later grant cannot revive the scan
    }

    func testDenialAfterCancelKeepsTheCancel() {
        let c = ScanCoordinator(idSource: { "s" })
        c.start(0); c.cancel(50)
        c.permissionDenied(100)
        XCTAssertEqual(c.state, .cancelled)
    }

    func testNoCaptureWithoutExplicitStartAndGrant() {
        let c = ScanCoordinator(idSource: { "s" })
        XCTAssertFalse(c.permissionGranted(0))
        XCTAssertFalse(c.frameAllowed(0))
        let l = CaptureLifecycle(coordinator: c, clock: { 0 }, compute: NoCompute(), background: NoBackground(), postToQueue: { $0() })
        let h = Handle()
        XCTAssertFalse(l.attach(h))                    // unsolicited stream is stopped and released
        XCTAssertEqual(h.stops, 1); XCTAssertEqual(h.releases, 1)
        XCTAssertNil(l.acceptFrame())
        c.start(0)
        XCTAssertFalse(l.attach(h))                    // started but not granted: still refused
        XCTAssertNil(l.acceptFrame())
    }

    func testMalformedGeometryIsRefusedBeforeAnyRead() {
        let buf = [UInt8](repeating: 0, count: 64 * 4 * 36)
        let bad: [[Int]] = [
            [63, 36, 256, 4], [64, 35, 256, 4], [4097, 36, 4097 * 4, 4], [64, 4097, 256, 4],
            [64, 36, 256, 2], [64, 36, 256, 17], [64, 36, 256, 0],
            [64, 36, 0, 4], [64, 36, -256, 4], [64, 36, Int.min, 4], [64, 36, (1 << 20) + 1, 4], [64, 36, 255, 4],
            [Int.max, 36, 256, 4], [64, Int.max, Int.max, 4], [64, 36, 264, 4],
        ]
        buf.withUnsafeBytes { (b: UnsafeRawBufferPointer) -> Void in
            for g in bad {
                var refused = false
                do { _ = try FrameView(base: b, width: g[0], height: g[1], rowStride: g[2], pixelStride: g[3]) } catch { refused = true }
                XCTAssertTrue(refused, "\(g)")
            }
            var exact = false
            do { _ = try FrameView(base: b, width: 64, height: 36, rowStride: 256, pixelStride: 4).toLuma(); exact = true } catch {}
            XCTAssertTrue(exact)
        }
    }

    func testInvalidLumaIsRefusedUncounted() throws {
        var th = Recognition.Thresholds(); th.radius = 9
        let s = RecognitionSession(pack: try Golden.pipelinePack(), thresholds: th)
        XCTAssertEqual(s.process(tMs: 0, luma: [Int](repeating: 0, count: 16 * 9), width: 16, height: 9), "INVALID")
        XCTAssertEqual(s.process(tMs: 0, luma: [Int](repeating: 0, count: 10), width: 64, height: 36), "INVALID")
        XCTAssertEqual(s.process(tMs: 0, luma: [], width: Int.max, height: 2), "INVALID")
        XCTAssertEqual(s.selected, 0)
    }
}
