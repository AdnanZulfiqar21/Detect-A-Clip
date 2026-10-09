package ai.detectaclip.lab

/**
 * Platform-independent capture lifecycle used by [CaptureService] (P01-T05/T06, CAP-A04).
 *
 * Owns exactly one projection handle and one post-capture computation per scan and routes
 * every OS/user event through [ScanCoordinator]. No Android types appear here, so the
 * cancellation races run as plain JVM tests.
 *
 * Rules:
 *  - The projection is stopped at most once (idempotent teardown).
 *  - After our own stop() the next onStop is reported as APP_REQUESTED_ACK (the OS delivers
 *    it asynchronously). Whether that report is trusted is the coordinator's adapter
 *    contract: default not attributable → fail closed, until LIFE-03 device evidence shows
 *    a user stop racing our stop can be told apart.
 *  - Frames are accepted only while the coordinator allows them and the selector has
 *    capacity; every refused frame is released immediately by the caller.
 *  - Capture Stop and post-capture Cancel are distinct: [userCancel] after capture closed
 *    cancels the computation; the late worker result carries a stale generation.
 *  - Nothing is written to disk and nothing leaves the process.
 *
 * Status: compiled and unit-tested on the JVM (no Android SDK); device behaviour UNVERIFIED.
 */
class CaptureLifecycle(
    private val coordinator: ScanCoordinator,
    private val clock: () -> Long,
    private val compute: ComputeRunner,
    private val postToMain: (() -> Unit) -> Unit,
) {
    /** The OS projection, reduced to what the lifecycle needs. */
    interface ProjectionHandle {
        fun stop()
        fun release()
    }

    /** Runs post-capture work off the main thread. `cancel()` must interrupt it promptly. */
    interface ComputeRunner {
        fun submit(work: (isCancelled: () -> Boolean) -> ScanCoordinator.Outcome, onDone: (ScanCoordinator.Outcome?) -> Unit): Cancellable
    }

    interface Cancellable { fun cancel() }

    private var projection: ProjectionHandle? = null
    private var projectionStopped = true
    private var ownStopPending = false
    private var selector: FrameSelector? = null
    private var job: Cancellable? = null

    var projectionStopCalls = 0; private set
    var releasedFrames = 0; private set
    var acceptedFrames = 0; private set

    val captureLive: Boolean get() = projection != null && !projectionStopped

    /** Called after the native consent returned a projection for this scan. */
    fun attach(handle: ProjectionHandle): Boolean {
        if (coordinator.state != ScanCoordinator.State.AWAITING_TARGET) {
            // Late or unsolicited grant: never start capture with it.
            handle.stop(); handle.release()
            return false
        }
        projection = handle
        projectionStopped = false
        selector = FrameSelector()
        return true
    }

    /** One delivered frame. Returns true if the caller may process it (then must call [frameDone]). */
    fun onFrame(): Boolean {
        val now = clock()
        if (coordinator.state == ScanCoordinator.State.AWAITING_TARGET) coordinator.targetReady(now)
        val sel = selector
        val ok = sel != null && captureLive && coordinator.frameAllowed(now) && sel.offer(now)
        if (ok) acceptedFrames += 1 else releasedFrames += 1
        return ok
    }

    fun frameDone() { selector?.release() }

    /** OS MediaProjection.Callback.onStop / ScreenCaptureKit didStop equivalent. */
    fun onProjectionStopped() {
        projectionStopped = true
        val ack = ownStopPending
        ownStopPending = false
        val cause = if (ack) ScanCoordinator.StopCause.APP_REQUESTED_ACK else ScanCoordinator.StopCause.UNKNOWN
        coordinator.captureStopped(clock(), cause)
        if (!ack) teardownCapture()
        if (coordinator.state == ScanCoordinator.State.CANCELLED || coordinator.state == ScanCoordinator.State.FAILED) cancelCompute()
    }

    /** Notification Stop, in-app Stop/Cancel: capture Stop and post-capture Cancel. */
    fun userCancel() {
        coordinator.cancel(clock())
        cancelCompute()
        teardownCapture()
    }

    fun screenOff() {
        coordinator.lock(clock())
        cancelCompute()
        teardownCapture()
    }

    fun permissionRevoked() {
        coordinator.permissionRevoked(clock())
        cancelCompute()
        teardownCapture()
    }

    /** Periodic deadline check on the main thread. */
    fun tick() {
        coordinator.tick(clock())
        when (coordinator.state) {
            ScanCoordinator.State.POST_CAPTURE -> if (captureLive) closeAndCompute()
            ScanCoordinator.State.CANCELLED, ScanCoordinator.State.FAILED -> { cancelCompute(); teardownCapture() }
            ScanCoordinator.State.COMMITTED -> teardownCapture()
            else -> Unit
        }
    }

    val terminal: Boolean
        get() = coordinator.state == ScanCoordinator.State.COMMITTED ||
            coordinator.state == ScanCoordinator.State.CANCELLED ||
            coordinator.state == ScanCoordinator.State.FAILED

    private fun closeAndCompute() {
        ownStopPending = true
        stopProjectionOnce()
        teardownCapture()
        if (coordinator.state != ScanCoordinator.State.POST_CAPTURE) return  // fail-closed ack already cancelled it
        val gen = coordinator.generation
        job = compute.submit({ isCancelled ->
            // LAB: bounded dummy work; real recognition arrives with P04-T08.
            if (isCancelled()) ScanCoordinator.Outcome.CANCELLED else ScanCoordinator.Outcome.NO_CONFIDENT_MATCH
        }) { outcome ->
            postToMain {
                job = null
                if (outcome != null && outcome != ScanCoordinator.Outcome.CANCELLED) {
                    coordinator.workerResult(clock(), gen, outcome, null, listOf("LAB_DUMMY_COMPUTE"))
                }
            }
        }
    }

    private fun stopProjectionOnce() {
        val p = projection ?: return
        if (!projectionStopped) {
            projectionStopped = true
            projectionStopCalls += 1
            p.stop()
        }
    }

    private fun cancelCompute() {
        job?.cancel()
        job = null
    }

    /** Idempotent release of every capture resource. */
    fun teardownCapture() {
        selector?.close()
        stopProjectionOnce()
        projection?.release()
        projection = null
    }
}
