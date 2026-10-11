package ai.detectaclip.lab

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.ByteBuffer

/**
 * Recognition-mode CaptureLifecycle with injected synthetic frames (no screen capture):
 * FrameSelector -> FrameView (padded RGBA strides) -> RecognitionSession -> compute runner ->
 * main-thread commit with generation, deadline and entitlement re-checks. Uses the synthetic
 * pack from golden_pipeline.txt. Device behaviour is not covered (B-01).
 */
class RecognitionLifecycleTest {
    private var now = 0L

    private class Proj(val onStop: () -> Unit) : CaptureLifecycle.ProjectionHandle {
        var stops = 0; var releases = 0
        override fun stop() { stops += 1; onStop() }
        override fun release() { releases += 1 }
    }

    private class ManualCompute : CaptureLifecycle.ComputeRunner {
        var submitted = 0; var cancelled = false
        private var work: ((() -> Boolean) -> CaptureLifecycle.WorkOutcome?)? = null
        private var done: ((CaptureLifecycle.WorkOutcome?) -> Unit)? = null
        override fun submit(work: (isCancelled: () -> Boolean) -> CaptureLifecycle.WorkOutcome?, onDone: (CaptureLifecycle.WorkOutcome?) -> Unit): CaptureLifecycle.Cancellable {
            submitted += 1; cancelled = false; this.work = work; this.done = onDone
            return object : CaptureLifecycle.Cancellable { override fun cancel() { cancelled = true } }
        }
        /** Runs the work; [midWork] fires at the session's second cancellation check. */
        fun finish(midWork: (() -> Unit)? = null) {
            val w = work ?: return; val d = done ?: return
            work = null; done = null
            var calls = 0
            val out = w { calls += 1; if (calls == 2) midWork?.invoke(); cancelled }
            d(out)
        }
    }

    private class Rig(val c: ScanCoordinator, val l: CaptureLifecycle, val compute: ManualCompute, val proj: Proj, val main: ArrayList<() -> Unit>) {
        var entitled = true
    }

    private val pack: PackIndex by lazy {
        val f = listOf("src/test/resources/golden_pipeline.txt", "android/app/src/test/resources/golden_pipeline.txt",
            "app/src/test/resources/golden_pipeline.txt").map(::File).first { it.exists() }
        val hex = f.readLines().first { it.startsWith("PACKHEX ") }.removePrefix("PACKHEX ")
        PackIndex.parse(ByteArray(hex.length / 2) { hex.substring(2 * it, 2 * it + 2).toInt(16).toByte() })
    }

    /** postToMain can be queued so a test can inject events between the worker and the commit. */
    private fun rig(deferMain: Boolean = false, synthetic: Boolean = true): Rig {
        now = 0
        val c = ScanCoordinator(adapter = ScanCoordinator.AdapterContract(true), idSource = { "s" })
        val compute = ManualCompute()
        val main = ArrayList<() -> Unit>()
        lateinit var r: Rig
        lateinit var l: CaptureLifecycle
        l = CaptureLifecycle(c, { now }, compute, { if (deferMain) main += it else it() },
            recognizer = { RecognitionSession(pack, Recognition.Thresholds(radius = 9.0), 12, mirrorInvariant = true) },
            entitlementCheck = { r.entitled }, syntheticPack = synthetic)
        val p = Proj { l.onProjectionStopped() }
        r = Rig(c, l, compute, p, main)
        return r
    }

    /** Padded RGBA plane (rowStride = w*4 + 12) with garbage in the padding. */
    private fun plane(seed: Int, w: Int = 64, h: Int = 36): FrameView {
        val rgb = DacDhash.contentFrame(seed, w, h)
        val rs = w * 4 + 12
        val b = ByteBuffer.allocateDirect(rs * h)
        for (y in 0 until h) {
            for (x in 0 until w) for (k in 0 until 3) b.put(y * rs + x * 4 + k, rgb[(y * w + x) * 3 + k])
            for (k in 0 until 12) b.put(y * rs + w * 4 + k, 0x5A)
        }
        return FrameView(b, w, h, rs, 4)
    }

    /** Delivers frames every 100 ms for 8 s; seedAt maps scan time to content. */
    private fun acquire(r: Rig, seedAt: (Long) -> Int) {
        assertTrue(r.c.start(now)); now += 100
        assertTrue(r.c.permissionGranted(now))
        assertTrue(r.l.attach(r.proj))
        val t0 = now
        repeat(80) {
            now = t0 + it * 100L
            val ts = r.l.acceptFrame()
            if (ts != null) {
                try { assertEquals("OK", r.l.processFrame(ts - t0, plane(seedAt(ts - t0)))) } finally { r.l.frameDone() }
            }
        }
        now = t0 + 12_100; r.l.tick()       // sampling window over: capture closes, compute submitted
    }

    private fun sw001(t: Long) = 20_000 + ((6_000 + t) / 500).toInt()          // pipeline_golden seed_at(1, .)
    private fun sw101(t: Long) = 50_000 + ((6_000 + t) / 500).toInt()          // unique part of episode E02

    @Test fun recognitionCommitsWorkFromInjectedFrames() {
        val r = rig()
        acquire(r, ::sw001)
        assertEquals("RECOGNITION", r.l.mode)
        assertEquals(16, r.l.processedFrames)
        assertEquals(1, r.compute.submitted)
        now += 500; r.compute.finish()
        assertEquals(ScanCoordinator.State.COMMITTED, r.c.state)
        val res = r.c.result!!
        assertEquals(ScanCoordinator.Outcome.VERIFIED_MATCH, res.outcome)
        assertEquals("SW001", res.candidateWorkId)
        assertEquals("E0_THEATRICAL", res.candidateEditionId)
        assertTrue("SYNTHETIC_L0" in res.flags)
        assertTrue(res.synthetic)
    }

    @Test fun seriesEpisodeIsCarriedToTheResult() {
        val r = rig()
        acquire(r, ::sw101)
        now += 500; r.compute.finish()
        val res = r.c.result!!
        assertEquals(ScanCoordinator.Outcome.VERIFIED_MATCH, res.outcome)
        assertEquals("S-P", res.candidateWorkId)
        assertEquals("E02", res.candidateEpisodeId)
    }

    @Test fun absentContentGivesNoConfidentMatchWithoutCandidate() {
        val r = rig()
        acquire(r) { t -> 777_000 + (t / 500).toInt() }
        now += 500; r.compute.finish()
        assertEquals(ScanCoordinator.Outcome.NO_CONFIDENT_MATCH, r.c.result!!.outcome)
        assertNull(r.c.result!!.candidateWorkId)
    }

    @Test fun cancelDuringVerificationReturnsNothingAndNeverCommits() {
        val r = rig()
        acquire(r, ::sw001)
        r.compute.finish(midWork = { r.l.userCancel() })   // user taps Cancel while verify runs
        assertTrue(r.compute.cancelled)
        assertEquals(ScanCoordinator.State.CANCELLED, r.c.state)
        assertEquals(0, r.c.commits)
        assertNull(r.c.result!!.candidateWorkId)
    }

    @Test fun lateWorkerCallbackAfterLockIsStale() {
        val r = rig(deferMain = true)
        acquire(r, ::sw001)
        r.compute.finish()                  // worker done; commit is queued on main
        now += 200; r.l.screenOff()         // lock observed first
        r.main.forEach { it() }
        assertEquals(ScanCoordinator.State.CANCELLED, r.c.state)
        assertEquals(1, r.c.staleWorkerResults)
        assertEquals(0, r.c.commits)
    }

    @Test fun commitAfterPostCaptureDeadlineFails() {
        val r = rig(deferMain = true)
        acquire(r, ::sw001)
        r.compute.finish()
        now += 8_001                        // main thread was blocked past the deadline
        r.main.forEach { it() }
        assertEquals(ScanCoordinator.State.FAILED, r.c.state)
        assertEquals("POST_CAPTURE_DEADLINE_EXPIRED", r.c.closedReason)
        assertEquals(0, r.c.commits)
    }

    @Test fun entitlementIsRecheckedAtCommit() {
        val r = rig(deferMain = true)
        acquire(r, ::sw001)
        r.compute.finish()
        r.entitled = false                  // pack lease revoked between compute and commit
        r.main.forEach { it() }
        assertEquals(ScanCoordinator.State.FAILED, r.c.state)
        assertEquals(ScanCoordinator.Outcome.ERROR, r.c.result!!.outcome)
        assertNull(r.c.result!!.candidateWorkId)
    }

    @Test fun lateFramesAfterCloseAreRefusedAndNotProcessed() {
        val r = rig()
        acquire(r, ::sw001)
        val before = r.l.processedFrames
        now += 600
        assertNull(r.l.acceptFrame())
        assertEquals("CLOSED", r.l.processFrame(now, plane(1)))
        assertEquals(before, r.l.processedFrames)
        assertEquals(1, r.proj.stops)
        assertEquals(1, r.proj.releases)
    }

    @Test fun licensedPackResultIsNotFlaggedSynthetic() {
        val r = rig(synthetic = false)
        acquire(r, ::sw001)
        r.compute.finish()
        assertTrue("SYNTHETIC_L0" !in r.c.result!!.flags)
    }

    @Test fun diagnosticModeIsUnchanged() {
        now = 0
        val c = ScanCoordinator(adapter = ScanCoordinator.AdapterContract(true), idSource = { "s" })
        val compute = ManualCompute()
        lateinit var l: CaptureLifecycle
        l = CaptureLifecycle(c, { now }, compute, { it() })
        val p = Proj { l.onProjectionStopped() }
        c.start(0); now = 100; c.permissionGranted(now); l.attach(p)
        now = 600; val ts = l.acceptFrame()!!
        assertEquals("DIAGNOSTIC", l.processFrame(ts, plane(1)))
        l.frameDone()
        now = 12_700; l.tick(); compute.finish()   // sampling began at 600 ms
        assertEquals("DIAGNOSTIC", l.mode)
        assertEquals(ScanCoordinator.Outcome.NO_CONFIDENT_MATCH, c.result!!.outcome)
        assertEquals(listOf("LAB_DUMMY_COMPUTE"), c.result!!.flags)
    }
}
