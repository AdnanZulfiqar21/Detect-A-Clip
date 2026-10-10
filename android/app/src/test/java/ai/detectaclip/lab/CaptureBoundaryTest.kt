package ai.detectaclip.lab

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.ByteBuffer

/**
 * Capture-boundary regressions: consent denial fails closed and never starts the
 * mediaProjection service; nothing captures without an explicit start + grant; malformed
 * frame geometry is refused before any read.
 */
class CaptureBoundaryTest {
    private fun coordinator() = ScanCoordinator(idSource = { "s" })

    @Test fun deniedPickerRecordsPermissionDeniedAndStartsNoService() {
        val c = coordinator()
        assertTrue(c.start(0))
        assertFalse(CaptureStartPolicy.onPickerResult(c, 100, resultOk = false, hasConsentData = false))
        assertEquals(ScanCoordinator.State.FAILED, c.state)
        assertEquals(ScanCoordinator.Outcome.PERMISSION_DENIED, c.result!!.outcome)
        assertNull(c.result!!.candidateWorkId)
        assertFalse(c.permissionGranted(200))              // a later grant cannot revive the scan
    }

    @Test fun okResultWithoutConsentIntentIsADenial() {
        val c = coordinator()
        c.start(0)
        assertFalse(CaptureStartPolicy.onPickerResult(c, 100, resultOk = true, hasConsentData = false))
        assertEquals(ScanCoordinator.Outcome.PERMISSION_DENIED, c.result!!.outcome)
    }

    @Test fun grantedPickerMayStartServiceButDoesNotGrantByItself() {
        val c = coordinator()
        c.start(0)
        assertTrue(CaptureStartPolicy.onPickerResult(c, 100, resultOk = true, hasConsentData = true))
        assertEquals(ScanCoordinator.State.AWAITING_PERMISSION, c.state)   // the service grants after promotion
    }

    @Test fun denialAfterUserCancelKeepsTheCancel() {
        val c = coordinator()
        c.start(0); c.cancel(50)
        assertFalse(CaptureStartPolicy.onPickerResult(c, 100, resultOk = false, hasConsentData = false))
        assertEquals(ScanCoordinator.State.CANCELLED, c.state)
    }

    @Test fun serviceStartDecisions() {
        assertEquals(CaptureStartPolicy.ServiceStart.STOP_REQUEST, CaptureStartPolicy.onServiceStart(true, true, true))
        assertEquals(CaptureStartPolicy.ServiceStart.STOP_REQUEST, CaptureStartPolicy.onServiceStart(true, false, false))
        assertEquals(CaptureStartPolicy.ServiceStart.DENY_NO_CONSENT, CaptureStartPolicy.onServiceStart(false, false, true))
        assertEquals(CaptureStartPolicy.ServiceStart.DENY_NO_CONSENT, CaptureStartPolicy.onServiceStart(false, true, false))
        assertEquals(CaptureStartPolicy.ServiceStart.PROCEED, CaptureStartPolicy.onServiceStart(false, true, true))
    }

    @Test fun noCaptureWithoutExplicitStartAndGrant() {
        val c = coordinator()
        assertFalse(c.permissionGranted(0))                 // no scan started: a grant is ignored
        assertFalse(c.frameAllowed(0))
        val l = CaptureLifecycle(c, { 0L }, object : CaptureLifecycle.ComputeRunner {
            override fun submit(work: (isCancelled: () -> Boolean) -> CaptureLifecycle.WorkOutcome?,
                                onDone: (CaptureLifecycle.WorkOutcome?) -> Unit) = object : CaptureLifecycle.Cancellable { override fun cancel() {} }
        }, postToMain = { it() })
        var stops = 0; var releases = 0
        val handle = object : CaptureLifecycle.ProjectionHandle {
            override fun stop() { stops += 1 }
            override fun release() { releases += 1 }
        }
        assertFalse(l.attach(handle))                       // unsolicited projection is stopped and released
        assertEquals(1, stops); assertEquals(1, releases)
        assertNull(l.acceptFrame())
        c.start(0)
        assertFalse(l.attach(handle))                       // started but not yet granted: still refused
        assertNull(l.acceptFrame())
    }

    @Test fun malformedGeometryIsRefusedBeforeAnyRead() {
        val buf = ByteBuffer.allocate(64 * 4 * 36)
        val bad = listOf(
            intArrayOf(63, 36, 256, 4), intArrayOf(64, 35, 256, 4),        // below the minimum size
            intArrayOf(4097, 36, 4097 * 4, 4), intArrayOf(64, 4097, 256, 4), // above the maximum size
            intArrayOf(64, 36, 256, 2), intArrayOf(64, 36, 256, 17), intArrayOf(64, 36, 256, 0),
            intArrayOf(64, 36, 0, 4), intArrayOf(64, 36, -256, 4), intArrayOf(64, 36, Int.MIN_VALUE, 4),
            intArrayOf(64, 36, (1 shl 20) + 1, 4), intArrayOf(64, 36, 255, 4),
            intArrayOf(1 shl 29, 36, Int.MIN_VALUE, 4),                       // width * pixelStride overflows Int
            intArrayOf(64, 36, 264, 4),                                        // needs more than the buffer holds
        )
        for (b in bad) assertThrows(b.joinToString(), IllegalArgumentException::class.java) { FrameView(buf, b[0], b[1], b[2], b[3]) }
        val limited = ByteBuffer.allocate(64 * 4 * 36 + 100).also { it.limit(64 * 4 * 36 - 1) }
        assertThrows(IllegalArgumentException::class.java) { FrameView(limited, 64, 36, 256, 4) }   // limit(), not capacity
        FrameView(buf, 64, 36, 256, 4).toLuma()                                                     // exact fit is fine
    }

    @Test fun invalidLumaIsRefusedUncounted() {
        val f = listOf("src/test/resources/golden_pipeline.txt", "android/app/src/test/resources/golden_pipeline.txt",
            "app/src/test/resources/golden_pipeline.txt").map(::File).first { it.exists() }
        val hex = f.readLines().first { it.startsWith("PACKHEX ") }.removePrefix("PACKHEX ")
        val pack = PackIndex.parse(ByteArray(hex.length / 2) { hex.substring(2 * it, 2 * it + 2).toInt(16).toByte() })
        val s = RecognitionSession(pack, Recognition.Thresholds(radius = 9.0))
        assertEquals("INVALID", s.process(0, IntArray(16 * 9), 16, 9))
        assertEquals("INVALID", s.process(0, IntArray(10), 64, 36))
        assertEquals(0, s.selected)
    }
}
