package ai.detectaclip.lab

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.Random

/** JVM port of l0/tests/test_coordinator.py (LIFE-01/02/03, SEC-02). Not yet executed (B-09). */
class ScanCoordinatorTest {
    private var n = 0
    private fun make(attributable: Boolean = false) =
        ScanCoordinator(adapter = ScanCoordinator.AdapterContract(attributable), idSource = { "scan${++n}" })

    private fun toPostCapture(c: ScanCoordinator): Long {
        assertTrue(c.start(0)); assertTrue(c.permissionGranted(100)); assertTrue(c.targetReady(200))
        for (i in 0 until 16) assertTrue(c.frameAllowed(300L + 500 * i))
        assertTrue(c.normalCloseRequested(8300))
        return c.generation
    }

    @Test fun normalScanCommitsOnce() {
        val c = make(true); val g = toPostCapture(c)
        c.captureStopped(8350, ScanCoordinator.StopCause.APP_REQUESTED_ACK)
        assertTrue(c.workerResult(9000, g, ScanCoordinator.Outcome.VERIFIED_MATCH, "SW001"))
        assertFalse(c.workerResult(9001, g, ScanCoordinator.Outcome.VERIFIED_MATCH, "SW001"))
        assertEquals(1, c.commits)
    }

    @Test fun unattributableAckFailsClosed() {
        val c = make(false); val g = toPostCapture(c)
        c.captureStopped(8350, ScanCoordinator.StopCause.APP_REQUESTED_ACK)
        assertEquals(ScanCoordinator.State.CANCELLED, c.state)
        assertFalse(c.workerResult(9000, g, ScanCoordinator.Outcome.VERIFIED_MATCH, "SW001"))
    }

    @Test fun lockAfterCloseBeforeCommitCancels() {
        val c = make(true); val g = toPostCapture(c)
        c.lock(8500)
        assertFalse(c.workerResult(8600, g, ScanCoordinator.Outcome.VERIFIED_MATCH, "SW001"))
        assertNull(c.result!!.candidateWorkId)
    }

    @Test fun life01ThousandOrderings() {
        val rng = Random(42)
        repeat(1000) {
            val c = make(rng.nextBoolean()); val g = toPostCapture(c)
            val t = 8300L + rng.nextInt(7000)
            when (rng.nextInt(5)) {
                0 -> c.captureStopped(t, ScanCoordinator.StopCause.USER_STOP)
                1 -> c.captureStopped(t, ScanCoordinator.StopCause.UNKNOWN)
                2 -> c.lock(t)
                3 -> c.permissionRevoked(t)
                else -> c.cancel(t)
            }
            assertFalse(c.workerResult(t + 1 + rng.nextInt(3000), g, ScanCoordinator.Outcome.VERIFIED_MATCH, "SW001"))
        }
    }

    @Test fun doubleStartSingleLease() {
        val c = make(); assertTrue(c.start(0)); val g = c.generation
        for (t in 1L..50L) assertFalse(c.start(t))
        assertEquals(g, c.generation)
    }

    @Test fun resultExpiryAndRollbackFailClosed() {
        val c = make(true); val g = toPostCapture(c)
        c.workerResult(9000, g, ScanCoordinator.Outcome.VERIFIED_MATCH, "SW001")
        assertTrue(c.returnToApp(9000 + 60_000) != null)
        assertNull(c.returnToApp(9000 + 16 * 60_000))
    }

    @Test fun selectorBounds() {
        val s = FrameSelector()
        for (i in 0 until 10) s.offer(i * 600L)
        assertEquals(3, s.owned)
        assertEquals(7, s.droppedBufferFull)
        assertFalse(s.offer(1L))
    }
}
