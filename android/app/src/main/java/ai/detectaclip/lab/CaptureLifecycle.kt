package ai.detectaclip.lab

/**
 * Platform-independent capture lifecycle used by [CaptureService] (P01-T05/T06, CAP-A04,
 * P04-T08 preparation).
 *
 * Owns exactly one projection handle, one [RecognitionSession] (recognition mode) and one
 * post-capture computation per scan, and routes every OS/user event through
 * [ScanCoordinator]. No Android types appear here, so cancellation races and the
 * recognition path run as plain JVM tests with injected synthetic frames.
 *
 * Modes:
 *  - DIAGNOSTIC (no recognizer factory): CAP-A04 measurement mode. Frames are counted only;
 *    post-capture work is the bounded dummy computation and the result is
 *    NO_CONFIDENT_MATCH flagged LAB_DUMMY_COMPUTE. Kept unchanged for CAP-A04.
 *  - RECOGNITION (recognizer factory given): selected frames are copied to app-owned luma
 *    ([processFrame]) and fed to the scan's RecognitionSession; after capture closes, the
 *    session's verification + decision run on the compute runner. The commit re-checks
 *    generation, deadline and local entitlement on the main thread.
 *
 * Rules:
 *  - The projection is stopped at most once (idempotent teardown).
 *  - After our own stop() the next onStop is reported as APP_REQUESTED_ACK (the OS delivers
 *    it asynchronously). Whether that report is trusted is the coordinator's adapter
 *    contract: default not attributable -> fail closed, until LIFE-03 device evidence shows
 *    a user stop racing our stop can be told apart.
 *  - Frames are accepted only while the coordinator allows them and the selector has
 *    capacity; every refused frame is released immediately by the caller. Late frames after
 *    close are refused by both the selector and the session.
 *  - Capture Stop and post-capture Cancel are distinct: [userCancel] after capture closed
 *    cancels the computation; a late worker result carries a stale generation.
 *  - Memory only: the session (candidates, luma copies) is dropped when the scan ends.
 *    Nothing is written to disk and nothing leaves the process.
 *
 * Status: compiled (AGP) and unit-tested on the JVM; device behaviour UNVERIFIED (B-01).
 */
class CaptureLifecycle(
    private val coordinator: ScanCoordinator,
    private val clock: () -> Long,
    private val compute: ComputeRunner,
    private val postToMain: (() -> Unit) -> Unit,
    private val recognizer: (() -> RecognitionSession)? = null,
    private val entitlementCheck: () -> Boolean = { true },
    private val syntheticPack: Boolean = true,
) {
    /** The OS projection, reduced to what the lifecycle needs. */
    interface ProjectionHandle {
        fun stop()
        fun release()
    }

    /** Runs post-capture work off the main thread. `cancel()` must interrupt it promptly. */
    interface ComputeRunner {
        fun submit(work: (isCancelled: () -> Boolean) -> WorkOutcome?, onDone: (WorkOutcome?) -> Unit): Cancellable
    }

    interface Cancellable { fun cancel() }

    /** What post-capture work hands to the commit step. */
    data class WorkOutcome(
        val outcome: ScanCoordinator.Outcome,
        val workId: String? = null,
        val editionId: String? = null,
        val episodeId: String? = null,
        val flags: List<String> = emptyList(),
    )

    val mode: String get() = if (recognizer == null) "DIAGNOSTIC" else "RECOGNITION"

    private var projection: ProjectionHandle? = null
    private var projectionStopped = true
    private var ownStopPending = false
    private var selector: FrameSelector? = null
    private var job: Cancellable? = null
    private var session: RecognitionSession? = null

    var projectionStopCalls = 0; private set
    var releasedFrames = 0; private set
    var acceptedFrames = 0; private set
    var processedFrames = 0; private set

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
        session = recognizer?.invoke()
        return true
    }

    /** One delivered frame. Returns its timestamp if the caller may process it (then the
     *  caller must call [frameDone]); null means release the OS buffer immediately. */
    fun acceptFrame(): Long? {
        val now = clock()
        if (coordinator.state == ScanCoordinator.State.AWAITING_TARGET) coordinator.targetReady(now)
        val sel = selector
        val ok = sel != null && captureLive && coordinator.frameAllowed(now) && sel.offer(now)
        if (ok) acceptedFrames += 1 else releasedFrames += 1
        return if (ok) now else null
    }

    fun onFrame(): Boolean = acceptFrame() != null

    /**
     * Recognition mode: copy the accepted frame into app-owned luma and run the per-frame
     * stage. Returns the quality flag, "DIAGNOSTIC" in diagnostic mode, or "CLOSED" if the
     * scan already ended. The caller may close the OS image as soon as this returns.
     */
    fun processFrame(timestampMs: Long, view: FrameView): String {
        val s = session ?: return if (recognizer == null) "DIAGNOSTIC" else "CLOSED"
        if (!captureLive) return "CLOSED"
        val luma = view.toLuma()                       // owned copy; the source buffer is not retained
        processedFrames += 1
        return s.process(timestampMs, luma, view.width, view.height)
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
        if (coordinator.state == ScanCoordinator.State.CANCELLED || coordinator.state == ScanCoordinator.State.FAILED) endScanWork()
    }

    /** Notification Stop, in-app Stop/Cancel: capture Stop and post-capture Cancel. */
    fun userCancel() {
        coordinator.cancel(clock())
        endScanWork()
        teardownCapture()
    }

    fun screenOff() {
        coordinator.lock(clock())
        endScanWork()
        teardownCapture()
    }

    fun permissionRevoked() {
        coordinator.permissionRevoked(clock())
        endScanWork()
        teardownCapture()
    }

    /** Periodic deadline check on the main thread. */
    fun tick() {
        coordinator.tick(clock())
        when (coordinator.state) {
            ScanCoordinator.State.POST_CAPTURE -> if (captureLive) closeAndCompute()
            ScanCoordinator.State.CANCELLED, ScanCoordinator.State.FAILED -> { endScanWork(); teardownCapture() }
            ScanCoordinator.State.COMMITTED -> { teardownCapture(); session = null }
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
        val s = session
        val work: (() -> Boolean) -> WorkOutcome? = if (s == null) {
            { isCancelled ->
                // DIAGNOSTIC (CAP-A04): bounded dummy work, explicitly labelled.
                if (isCancelled()) null else WorkOutcome(ScanCoordinator.Outcome.NO_CONFIDENT_MATCH, flags = listOf("LAB_DUMMY_COMPUTE"))
            }
        } else {
            { isCancelled ->
                s.finish(isCancelled)?.let { d ->
                    WorkOutcome(ScanCoordinator.Outcome.valueOf(d.state.name), d.workId, d.editionId, d.episodeId,
                        if (syntheticPack) d.flags + "SYNTHETIC_L0" else d.flags)
                }
            }
        }
        job = compute.submit(work) { out ->
            postToMain {
                job = null
                session = null
                if (out != null) {
                    // Local entitlement is re-checked at commit time, on the main thread.
                    coordinator.workerResult(clock(), gen, out.outcome, out.workId, out.flags, entitlementCheck(), out.editionId, out.episodeId)
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

    private fun endScanWork() {
        job?.cancel()
        job = null
        session = null
    }

    /** Idempotent release of every capture resource. */
    fun teardownCapture() {
        selector?.close()
        stopProjectionOnce()
        projection?.release()
        projection = null
    }
}
