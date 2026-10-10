// Port of android CaptureLifecycle.kt. Platform-independent; the ScreenCaptureKit adapter
// (ScreenCaptureAdapter.swift) calls it on one serial queue.
// Status: compiled and tested only where CI runs `swift test`; device behaviour unverified (B-02).
//
// Modes (same as Kotlin):
//  - DIAGNOSTIC (no recognizer): frames are counted only; the post-capture result is
//    NO_CONFIDENT_MATCH flagged LAB_DUMMY_COMPUTE.
//  - RECOGNITION (recognizer factory given): selected frames are copied to app-owned luma
//    (processFrame) and fed to the scan's RecognitionSession; verification and decision run on
//    the compute runner after capture closes; the commit re-checks generation, deadline and
//    local entitlement on the serial queue.
//
// iOS specifics carried as protocol hooks:
//  - BackgroundTaskGuard: request the finite background task *early* (at Start), end it on
//    commit/cancel/expiry; expiry cancels the scan (V16). No audio keepalive.
//  - The system capture indicator's behaviour is UNVERIFIED (CAP-I02); in-app Stop is
//    always available on return.

public protocol ProjectionHandle: AnyObject {
    func stop()
    func release()
}

public protocol BackgroundTaskGuard: AnyObject {
    /// Returns false if the OS refused the assertion.
    func begin(onExpire: @escaping () -> Void) -> Bool
    func end()
    /// Diagnostic only (backgroundTimeRemaining); never a promised grant.
    var remainingMs: Int64? { get }
}

public protocol Cancellable: AnyObject { func cancel() }

/// What post-capture work hands to the commit step.
public struct WorkOutcome: Equatable {
    public let outcome: ScanCoordinator.Outcome
    public var workId: String? = nil
    public var editionId: String? = nil
    public var episodeId: String? = nil
    public var flags: [String] = []
    public init(outcome: ScanCoordinator.Outcome, workId: String? = nil, editionId: String? = nil, episodeId: String? = nil, flags: [String] = []) {
        self.outcome = outcome; self.workId = workId; self.editionId = editionId; self.episodeId = episodeId; self.flags = flags
    }
}

public protocol ComputeRunner: AnyObject {
    /// Runs `work` off the serial queue; `cancel()` must make `isCancelled` true promptly.
    func submit(_ work: @escaping (_ isCancelled: () -> Bool) -> WorkOutcome?,
                onDone: @escaping (WorkOutcome?) -> Void) -> Cancellable
}

extension ScanCoordinator.Outcome {
    init(_ s: Recognition.State) {
        switch s {
        case .VERIFIED_MATCH: self = .verifiedMatch
        case .POSSIBLE_MATCH: self = .possibleMatch
        case .NO_CONFIDENT_MATCH: self = .noConfidentMatch
        case .INSUFFICIENT_SIGNAL: self = .insufficientSignal
        case .UNSUPPORTED_CAPTURE: self = .unsupportedCapture
        case .PERMISSION_DENIED: self = .permissionDenied
        case .CANCELLED: self = .cancelled
        case .ERROR: self = .error
        }
    }
}

public final class CaptureLifecycle {
    private let coordinator: ScanCoordinator
    private let clock: () -> Int64
    private let compute: ComputeRunner
    private let background: BackgroundTaskGuard
    private let postToQueue: (@escaping () -> Void) -> Void
    private let recognizer: (() -> RecognitionSession)?
    private let entitlementCheck: () -> Bool
    private let syntheticPack: Bool

    private var projection: ProjectionHandle?
    private var projectionStopped = true
    private var ownStopPending = false
    private var selector: FrameSelector?
    private var job: Cancellable?
    private var session: RecognitionSession?
    private var backgroundHeld = false

    public private(set) var projectionStopCalls = 0
    public private(set) var acceptedFrames = 0
    public private(set) var releasedFrames = 0
    public private(set) var processedFrames = 0

    public init(coordinator: ScanCoordinator, clock: @escaping () -> Int64, compute: ComputeRunner,
                background: BackgroundTaskGuard, postToQueue: @escaping (@escaping () -> Void) -> Void,
                recognizer: (() -> RecognitionSession)? = nil, entitlementCheck: @escaping () -> Bool = { true },
                syntheticPack: Bool = true) {
        self.coordinator = coordinator
        self.clock = clock
        self.compute = compute
        self.background = background
        self.postToQueue = postToQueue
        self.recognizer = recognizer
        self.entitlementCheck = entitlementCheck
        self.syntheticPack = syntheticPack
    }

    public var mode: String { recognizer == nil ? "DIAGNOSTIC" : "RECOGNITION" }
    public var captureLive: Bool { projection != nil && !projectionStopped }
    public var terminal: Bool { [.committed, .cancelled, .failed].contains(coordinator.state) }

    /// Call right after the user tapped Start (before the picker) so the background
    /// assertion is requested early. A refusal is recorded, not hidden.
    @discardableResult public func requestBackgroundEarly() -> Bool {
        backgroundHeld = background.begin { [weak self] in
            guard let self else { return }
            self.coordinator.backgroundTaskExpired(self.clock())
            self.endScanWork(); self.teardownCapture(); self.endBackground()
        }
        return backgroundHeld
    }

    @discardableResult public func attach(_ handle: ProjectionHandle) -> Bool {
        guard coordinator.state == .awaitingTarget else { handle.stop(); handle.release(); return false }
        projection = handle
        projectionStopped = false
        selector = FrameSelector()
        session = recognizer?()
        return true
    }

    /// One delivered frame. Returns its timestamp if the caller may process it (then the caller
    /// must call frameDone()); nil means release the OS buffer immediately.
    public func acceptFrame() -> Int64? {
        let now = clock()
        if coordinator.state == .awaitingTarget { coordinator.targetReady(now) }
        var ok = false
        if let sel = selector, captureLive, coordinator.frameAllowed(now) { ok = sel.offer(now) }
        if ok { acceptedFrames += 1 } else { releasedFrames += 1 }
        return ok ? now : nil
    }

    public func onFrame() -> Bool { acceptFrame() != nil }

    /// Recognition mode: copy the accepted frame into app-owned luma and run the per-frame stage.
    /// Returns the quality flag, "DIAGNOSTIC" in diagnostic mode, or "CLOSED" if the scan ended.
    public func processFrame(timestampMs: Int64, view: FrameView) -> String {
        guard let s = session else { return recognizer == nil ? "DIAGNOSTIC" : "CLOSED" }
        guard captureLive else { return "CLOSED" }
        let luma = view.toLuma()                    // owned copy; the source buffer is not retained
        processedFrames += 1
        return s.process(tMs: Int(timestampMs), luma: luma, width: view.width, height: view.height)
    }

    public func frameDone() { selector?.release() }

    /// SCStreamDelegate stream(_:didStopWithError:) or equivalent.
    public func onCaptureStopped() {
        projectionStopped = true
        let ack = ownStopPending
        ownStopPending = false
        coordinator.captureStopped(clock(), cause: ack ? .appRequestedAck : .unknown)
        if !ack { teardownCapture() }
        if coordinator.state == .cancelled || coordinator.state == .failed { endScanWork(); endBackground() }
    }

    public func userCancel() { coordinator.cancel(clock()); endScanWork(); teardownCapture(); endBackground() }
    public func deviceLocked() { coordinator.lock(clock()); endScanWork(); teardownCapture(); endBackground() }

    public func tick() {
        coordinator.tick(clock())
        switch coordinator.state {
        case .postCapture where captureLive: closeAndCompute()
        case .cancelled, .failed: endScanWork(); teardownCapture(); endBackground()
        case .committed: teardownCapture(); session = nil; endBackground()
        default: break
        }
    }

    private func closeAndCompute() {
        ownStopPending = true
        stopProjectionOnce()
        teardownCapture()
        guard coordinator.state == .postCapture else { return }
        let gen = coordinator.generation
        let work: (() -> Bool) -> WorkOutcome?
        if let s = session {
            let synthetic = syntheticPack
            work = { isCancelled in
                guard let d = s.finish(isCancelled: isCancelled) else { return nil }
                return WorkOutcome(outcome: ScanCoordinator.Outcome(d.state), workId: d.workId, editionId: d.editionId,
                                   episodeId: d.episodeId, flags: synthetic ? d.flags + ["SYNTHETIC_L0"] : d.flags)
            }
        } else {
            // DIAGNOSTIC: bounded dummy work, explicitly labelled.
            work = { isCancelled in isCancelled() ? nil : WorkOutcome(outcome: .noConfidentMatch, flags: ["LAB_DUMMY_COMPUTE"]) }
        }
        job = compute.submit(work) { [weak self] out in
            self?.postToQueue {
                guard let self else { return }
                self.job = nil
                self.session = nil
                if let o = out {
                    // Local entitlement is re-checked at commit time, on the serial queue.
                    self.coordinator.workerResult(self.clock(), generation: gen, outcome: o.outcome, workId: o.workId, flags: o.flags,
                                                  entitlementOk: self.entitlementCheck(), editionId: o.editionId, episodeId: o.episodeId)
                }
                if self.terminal { self.endBackground() }
            }
        }
    }

    private func stopProjectionOnce() {
        guard let p = projection, !projectionStopped else { return }
        projectionStopped = true
        projectionStopCalls += 1
        p.stop()
    }

    private func endScanWork() { job?.cancel(); job = nil; session = nil }

    private func endBackground() {
        if backgroundHeld { background.end(); backgroundHeld = false }
    }

    public func teardownCapture() {
        selector?.close()
        stopProjectionOnce()
        projection?.release()
        projection = nil
    }
}
