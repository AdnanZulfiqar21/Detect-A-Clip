package ai.detectaclip.lab

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.Random

/** JVM tests for CaptureLifecycle: races between capture close, user Stop, lock and the
 *  post-capture computation. Device behaviour is not covered (B-01, B-09). */
class CaptureLifecycleTest {
    private var now = 0L

    private class FakeProjection(val onStopCallback: () -> Unit, val deliverStopSynchronously: Boolean) : CaptureLifecycle.ProjectionHandle {
        var stops = 0
        var releases = 0
        val pendingCallbacks = ArrayList<() -> Unit>()
        override fun stop() {
            stops += 1
            if (deliverStopSynchronously) onStopCallback() else pendingCallbacks += onStopCallback
        }
        override fun release() { releases += 1 }
    }

    /** Manual compute runner: work runs only when the test calls finish(). */
    private class ManualCompute : CaptureLifecycle.ComputeRunner {
        var submitted = 0
        var cancelled = false
        private var work: ((() -> Boolean) -> ScanCoordinator.Outcome)? = null
        private var done: ((ScanCoordinator.Outcome?) -> Unit)? = null
        override fun submit(work: (isCancelled: () -> Boolean) -> ScanCoordinator.Outcome, onDone: (ScanCoordinator.Outcome?) -> Unit): CaptureLifecycle.Cancellable {
            submitted += 1; cancelled = false; this.work = work; this.done = onDone
            return object : CaptureLifecycle.Cancellable { override fun cancel() { cancelled = true } }
        }
        fun finish() {
            val w = work ?: return
            val d = done ?: return
            work = null; done = null
            d(w { cancelled })
        }
        val pending get() = work != null
    }

    private data class Rig(val c: ScanCoordinator, val l: CaptureLifecycle, val compute: ManualCompute, val proj: FakeProjection)

    private fun rig(attributable: Boolean = true, syncStop: Boolean = true): Rig {
        now = 0
        val c = ScanCoordinator(adapter = ScanCoordinator.AdapterContract(attributable), idSource = { "s" })
        val compute = ManualCompute()
        lateinit var l: CaptureLifecycle
        l = CaptureLifecycle(c, { now }, compute) { it() }
        val p = FakeProjection({ l.onProjectionStopped() }, syncStop)
        return Rig(c, l, compute, p)
    }

    private fun acquire(r: Rig) {
        assertTrue(r.c.start(now)); now += 100
        assertTrue(r.c.permissionGranted(now))
        assertTrue(r.l.attach(r.proj))
        repeat(40) { now += 250; if (r.l.onFrame()) r.l.frameDone() }   // 10 s of frames
        now = 100 + 12_000 + 300          // past the sampling window
        r.l.tick()                          // closes capture and submits compute
    }

    @Test fun normalScanCommitsAfterComputeWhenAckAttributable() {
        val r = rig(attributable = true)
        acquire(r)
        assertEquals(1, r.proj.stops)
        assertEquals(1, r.compute.submitted)
        now += 2_000; r.compute.finish()
        assertEquals(ScanCoordinator.State.COMMITTED, r.c.state)
        assertEquals(1, r.c.commits)
        assertTrue(r.l.acceptedFrames in 12..24)
    }

    @Test fun unattributableAckFailsClosedAndNoComputeIsSubmitted() {
        val r = rig(attributable = false)
        acquire(r)
        assertEquals(ScanCoordinator.State.CANCELLED, r.c.state)
        assertEquals(0, r.compute.submitted)
    }

    @Test fun userCancelDuringComputeCancelsAndLateResultIsDropped() {
        val r = rig()
        acquire(r)
        now += 1_000; r.l.userCancel()
        assertTrue(r.compute.cancelled)
        r.compute.finish()
        assertEquals(ScanCoordinator.State.CANCELLED, r.c.state)
        assertEquals(0, r.c.commits)
        assertEquals(1, r.proj.stops)   // never stopped twice
    }

    @Test fun lockAfterCaptureCloseBeforeCommitCancels() {
        val r = rig()
        acquire(r)
        now += 500; r.l.screenOff()
        r.compute.finish()
        assertEquals(ScanCoordinator.State.CANCELLED, r.c.state)
        assertNull(r.c.result!!.candidateWorkId)
    }

    @Test fun computeOverrunningPostCaptureDeadlineFails() {
        val r = rig()
        acquire(r)
        now += 8_001; r.l.tick()
        assertEquals(ScanCoordinator.State.FAILED, r.c.state)
        assertTrue(r.compute.cancelled)
        r.compute.finish()
        assertEquals(0, r.c.commits)
    }

    @Test fun osStopDuringAcquisitionCancelsAndReleasesOnce() {
        val r = rig()
        assertTrue(r.c.start(0)); now = 100; r.c.permissionGranted(now); r.l.attach(r.proj)
        now = 500; r.l.onFrame()
        r.l.onProjectionStopped()             // user tapped the system chip
        assertEquals(ScanCoordinator.State.CANCELLED, r.c.state)
        r.l.teardownCapture(); r.l.teardownCapture()
        assertEquals(0, r.proj.stops)         // OS already stopped it; we never call stop() again
        assertEquals(1, r.proj.releases)
        assertFalse(r.l.onFrame())            // late frame refused
    }

    @Test fun lateGrantAfterCancelIsStoppedAndNeverCaptures() {
        val r = rig()
        r.c.start(0); r.c.cancel(10)
        assertFalse(r.l.attach(r.proj))
        assertEquals(1, r.proj.stops)
        assertEquals(1, r.proj.releases)
        assertFalse(r.l.onFrame())
    }

    @Test fun asynchronousAckIsTrustedOnlyWithAttributableAdapter() {
        val r = rig(attributable = true, syncStop = false)
        acquire(r)
        assertEquals(1, r.compute.submitted)
        r.proj.pendingCallbacks.forEach { it() }  // onStop arrives later on the main looper
        assertEquals(ScanCoordinator.State.POST_CAPTURE, r.c.state)
        now += 1_000; r.compute.finish()
        assertEquals(ScanCoordinator.State.COMMITTED, r.c.state)

        val r2 = rig(attributable = false, syncStop = false)
        acquire(r2)
        r2.proj.pendingCallbacks.forEach { it() }
        assertEquals(ScanCoordinator.State.CANCELLED, r2.c.state)
        assertTrue(r2.compute.cancelled)
        r2.compute.finish()
        assertEquals(0, r2.c.commits)
    }

    @Test fun secondStopCallbackAfterAckIsTreatedAsUnknown() {
        val r = rig(attributable = true, syncStop = false)
        acquire(r)
        r.proj.pendingCallbacks.forEach { it() }  // our ack
        r.l.onProjectionStopped()                  // a further, unexplained stop
        assertEquals(ScanCoordinator.State.CANCELLED, r.c.state)
    }

    @Test fun randomisedEventOrderingsNeverPublishAfterAbort() {
        val rnd = Random(7)
        repeat(1000) {
            val r = rig(attributable = rnd.nextBoolean())
            acquire(r)
            val events = listOf<() -> Unit>({ r.l.userCancel() }, { r.l.screenOff() }, { r.l.permissionRevoked() }, { r.l.onProjectionStopped() })
            now += rnd.nextInt(7_000)
            events[rnd.nextInt(events.size)]()
            now += rnd.nextInt(2_000)
            r.compute.finish()
            assertEquals(0, r.c.commits)
            assertTrue(r.proj.stops <= 1)
        }
    }
}
