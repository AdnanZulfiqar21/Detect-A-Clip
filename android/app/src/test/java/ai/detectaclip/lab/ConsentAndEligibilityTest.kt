package ai.detectaclip.lab

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ConsentAndEligibilityTest {
    private class Mem : ReceiptStorage {
        val m = HashMap<String, String>()
        override fun read(key: String) = m[key]
        override fun write(key: String, value: String) { m[key] = value }
        override fun delete(key: String) { m.remove(key) }
    }

    private val en = TermsDocument("1.0", "en-GB", "Terms text v1", "en-GB-1", "disc-1")
    private val now = 1_800_000_000_000L

    @Test fun firstUseRequiresExplicitAcceptance() {
        val c = ConsentRecords(Mem()) { now }
        assertEquals(ConsentRecords.TermsStatus.NOT_ACCEPTED, c.termsStatus(en))
        assertFalse(c.scanningAllowed(en))
        c.accept(en)
        assertTrue(c.scanningAllowed(en))
    }

    @Test fun reopenWithUnchangedTermsDoesNotPromptAgain() {
        val st = Mem()
        ConsentRecords(st) { now }.accept(en)
        repeat(10) { assertEquals(ConsentRecords.TermsStatus.ACCEPTED_CURRENT, ConsentRecords(st) { now + it }.termsStatus(en)) }
    }

    @Test fun translationOnlyChangeNeedsNewNotice() {
        val st = Mem()
        val c = ConsentRecords(st) { now }
        c.accept(en)
        val retranslated = en.copy(renderedText = "Terms text v1 (corrected translation)")
        assertEquals(ConsentRecords.TermsStatus.CHANGED_NEEDS_NEW_NOTICE, c.termsStatus(retranslated))
        assertFalse(c.scanningAllowed(retranslated))
        assertEquals(ConsentRecords.TermsStatus.CHANGED_NEEDS_NEW_NOTICE, c.termsStatus(en.copy(locale = "ur-PK")))
        assertEquals(ConsentRecords.TermsStatus.CHANGED_NEEDS_NEW_NOTICE, c.termsStatus(en.copy(disclosureVersion = "disc-2")))
    }

    @Test fun declineBlocksScanningUntilExplicitAcceptance() {
        val c = ConsentRecords(Mem()) { now }
        c.accept(en)
        c.decline(en)
        assertEquals(ConsentRecords.TermsStatus.DECLINED, c.termsStatus(en))
        assertFalse(c.scanningAllowed(en))
        c.accept(en)
        assertTrue(c.scanningAllowed(en))
    }

    @Test fun purposesAreSeparateAndDefaultDeny() {
        val c = ConsentRecords(Mem()) { now }
        c.accept(en)
        assertFalse(c.purposeAllowed("notifications"))
        c.setPurpose("notifications", false)
        assertTrue(c.scanningAllowed(en))   // refusing an optional purpose does not block scanning
        assertFalse(c.purposeAllowed("audio"))
    }

    @Test fun receiptRoundTripsAndRejectsCorruption() {
        val r = ConsentRecords(Mem()) { now }.accept(en)
        assertEquals(r, TermsReceipt.decode(r.encode()))
        assertEquals(null, TermsReceipt.decode("garbage"))
    }

    private val labCell = EligibilityGate.Cell("A15-LAB", "AP4A.1", "IN_PROGRESS", "BLOCKED", false, false, now + 86_400_000)
    private val devPack = EligibilityGate.PackState("L0-SYNTH-001", "CALIBRATED_L0_SYNTHETIC", null, true)

    @Test fun labBuildEligibleWithAdmittedCellAndPack() {
        val g = EligibilityGate { now }
        assertEquals(EligibilityGate.Decision.Eligible, g.check(EligibilityGate.BuildPurpose.LAB, true, labCell, "AP4A.1", devPack))
    }

    @Test fun consumerPurposeDeniedByDefault() {
        val g = EligibilityGate { now }
        val d = g.check(EligibilityGate.BuildPurpose.CONSUMER, true, labCell, "AP4A.1", devPack)
        assertEquals(EligibilityGate.Decision.Denied("CONSUMER_CELL_BLOCKED"), d)
        val passedButNoStop = labCell.copy(consumerStatus = "PASS")
        assertEquals(EligibilityGate.Decision.Denied("STOP_PATH_UNVERIFIED"), g.check(EligibilityGate.BuildPurpose.CONSUMER, true, passedButNoStop, "AP4A.1", devPack))
        val full = passedButNoStop.copy(stopPathVerified = true, postCaptureCancelVerified = true)
        assertEquals(EligibilityGate.Decision.Denied("PACK_NOT_RELEASE_CALIBRATED"), g.check(EligibilityGate.BuildPurpose.CONSUMER, true, full, "AP4A.1", devPack))
    }

    @Test fun everyUnknownOrStaleInputDenies() {
        val g = EligibilityGate { now }
        val lab = EligibilityGate.BuildPurpose.LAB
        assertEquals(EligibilityGate.Decision.Denied("TERMS_NOT_ACCEPTED"), g.check(lab, false, labCell, "AP4A.1", devPack))
        assertEquals(EligibilityGate.Decision.Denied("NO_CAPABILITY_CELL"), g.check(lab, true, null, "AP4A.1", devPack))
        assertEquals(EligibilityGate.Decision.Denied("CELL_OS_BUILD_MISMATCH"), g.check(lab, true, labCell, "AP4A.2", devPack))
        assertEquals(EligibilityGate.Decision.Denied("CELL_EXPIRED_OR_TIME_UNTRUSTED"), g.check(lab, true, labCell, "AP4A.1", devPack.copy(timeTrustworthy = false)))
        assertEquals(EligibilityGate.Decision.Denied("NO_ACTIVE_PACK"), g.check(lab, true, labCell, "AP4A.1", devPack.copy(packId = null)))
        assertEquals(EligibilityGate.Decision.Denied("PACK_LEASE_EXPIRED_OR_TIME_UNTRUSTED"), g.check(lab, true, labCell, "AP4A.1", devPack.copy(leaseValidUntilEpochMs = now - 1)))
        assertEquals(EligibilityGate.Decision.Denied("SNAPCHAT_OFF"), g.check(lab, true, labCell, "AP4A.1", devPack, snapchatRequested = true))
        assertEquals(EligibilityGate.Decision.Denied("MODE_R_OFF"), g.check(lab, true, labCell, "AP4A.1", devPack, cloudModeRequested = true))
        val expired = labCell.copy(expiresAtEpochMs = now - 1)
        assertEquals(EligibilityGate.Decision.Denied("CELL_EXPIRED_OR_TIME_UNTRUSTED"), g.check(lab, true, expired, "AP4A.1", devPack))
    }
}
