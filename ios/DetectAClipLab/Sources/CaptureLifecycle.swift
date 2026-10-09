// Port of android CaptureLifecycle.kt. Platform-independent; the ScreenCaptureKit adapter
// (ScreenCaptureAdapter.swift) calls it on one serial queue. Status: IMPLEMENTED_NOT_VERIFIED.
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

public protocol ComputeRunner: AnyObject {
    func submit(_ work: @escaping (_ isCancelled: () -> Bool) -> ScanCoordinator.Outcome,
                onDone: @escaping (ScanCoordinator.Outcome?) -> Void) -> Cancellable
}

public final class CaptureLifecycle {
    private let coordinator: ScanCoordinator
    private let clock: () -> Int64
    private let compute: ComputeRunner
    private let background: BackgroundTaskGuard
    private let postToQueue: (@escaping () -> Void) -> Void

    private var projection: ProjectionHandle?
    private var projectionStopped = true
    private var ownStopPending = false
    private var selector: FrameSelector?
    private var job: Cancellable?
    private var backgroundHeld = false

    public private(set) var projectionStopCalls = 0
    public private(set) var acceptedFrames = 0
    public private(set) var releasedFrames = 0

    public init(coordinator: ScanCoordinator, clock: @escaping () -> Int64, compute: ComputeRunner,
                background: BackgroundTaskGuard, postToQueue: @escaping (@escaping () -> Void) -> Void) {
        self.coordinator = coordinator
        self.clock = clock
        self.compute = compute
        self.background = background
        self.postToQueue = postToQueue
    }

    public var captureLive: Bool { projection != nil && !projectionStopped }
    public var terminal: Bool { [.committed, .cancelled, .failed].contains(coordinator.state) }

    /// Call right after the user tapped Start (before the picker) so the background
    /// assertion is requested early. A refusal is recorded, not hidden.
    @discardableResult public func requestBackgroundEarly() -> Bool {
        backgroundHeld = background.begin { [weak self] in
            guard let self else { return }
            self.coordinator.backgroundTaskExpired(self.clock())
            self.cancelCompute(); self.teardownCapture(); self.endBackground()
        }
        return backgroundHeld
    }

    @discardableResult public func attach(_ handle: ProjectionHandle) -> Bool {
        guard coordinator.state == .awaitingTarget else { handle.stop(); handle.release(); return false }
        projection = handle
        projectionStopped = false
        selector = FrameSelector()
        return true
    }

    public func onFrame() -> Bool {
        let now = clock()
        if coordinator.state == .awaitingTarget { coordinator.targetReady(now) }
        var ok = false
        if let sel = selector, captureLive, coordinator.frameAllowed(now) { ok = sel.offer(now) }
        if ok { acceptedFrames += 1 } else { releasedFrames += 1 }
        return ok
    }

    public func frameDone() { selector?.release() }

    /// SCStreamDelegate stream(_:didStopWithError:) or equivalent.
    public func onCaptureStopped() {
        projectionStopped = true
        let ack = ownStopPending
        ownStopPending = false
        coordinator.captureStopped(clock(), cause: ack ? .appRequestedAck : .unknown)
        if !ack { teardownCapture() }
        if coordinator.state == .cancelled || coordinator.state == .failed { cancelCompute(); endBackground() }
    }

    public func userCancel() { coordinator.cancel(clock()); cancelCompute(); teardownCapture(); endBackground() }
    public func deviceLocked() { coordinator.lock(clock()); cancelCompute(); teardownCapture(); endBackground() }

    public func tick() {
        coordinator.tick(clock())
        switch coordinator.state {
        case .postCapture where captureLive: closeAndCompute()
        case .cancelled, .failed: cancelCompute(); teardownCapture(); endBackground()
        case .committed: teardownCapture(); endBackground()
        default: break
        }
    }

    private func closeAndCompute() {
        ownStopPending = true
        stopProjectionOnce()
        teardownCapture()
        guard coordinator.state == .postCapture else { return }
        let gen = coordinator.generation
        job = compute.submit({ isCancelled in isCancelled() ? .cancelled : .noConfidentMatch }) { [weak self] outcome in
            self?.postToQueue {
                guard let self else { return }
                self.job = nil
                if let o = outcome, o != .cancelled {
                    self.coordinator.workerResult(self.clock(), generation: gen, outcome: o, workId: nil)
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

    private func cancelCompute() { job?.cancel(); job = nil }

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
