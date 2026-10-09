package ai.detectaclip.lab

/**
 * Pre-scan local eligibility (F03 per-scan step 1, P05-T03c, CAP-07, D09, D01).
 *
 * Evaluated before Start shows the native picker. Uses only local, pre-acquired state:
 * no network request, no scan-triggered entitlement or update check. Every unknown input
 * denies. Returns the first failing reason so the UI can say why scanning is unavailable.
 *
 * Status: JVM-tested; consumer cells are BLOCKED by default per the capability matrix.
 */
class EligibilityGate(private val clock: () -> Long) {

    enum class BuildPurpose { LAB, CONSUMER }

    data class Cell(
        val cellId: String,
        val osBuild: String,
        val labStatus: String,        // PASS / NOT_STARTED / ...
        val consumerStatus: String,   // PASS / BLOCKED / ...
        val stopPathVerified: Boolean,
        val postCaptureCancelVerified: Boolean,
        val expiresAtEpochMs: Long?,
    )

    data class PackState(val packId: String?, val calibrationStatus: String?, val leaseValidUntilEpochMs: Long?, val timeTrustworthy: Boolean)

    sealed class Decision {
        object Eligible : Decision()
        data class Denied(val reason: String) : Decision()
    }

    fun check(
        purpose: BuildPurpose,
        termsAccepted: Boolean,
        cell: Cell?,
        currentOsBuild: String,
        pack: PackState,
        snapchatRequested: Boolean = false,
        cloudModeRequested: Boolean = false,
    ): Decision {
        if (cloudModeRequested) return Decision.Denied("MODE_R_OFF")
        if (snapchatRequested) return Decision.Denied("SNAPCHAT_OFF")
        if (!termsAccepted) return Decision.Denied("TERMS_NOT_ACCEPTED")
        if (cell == null) return Decision.Denied("NO_CAPABILITY_CELL")
        if (cell.osBuild != currentOsBuild) return Decision.Denied("CELL_OS_BUILD_MISMATCH")
        val now = clock()
        if (cell.expiresAtEpochMs != null && (!pack.timeTrustworthy || now >= cell.expiresAtEpochMs)) return Decision.Denied("CELL_EXPIRED_OR_TIME_UNTRUSTED")
        when (purpose) {
            BuildPurpose.LAB -> if (cell.labStatus != "PASS" && cell.labStatus != "IN_PROGRESS") return Decision.Denied("CELL_NOT_ADMITTED_FOR_LAB")
            BuildPurpose.CONSUMER -> {
                if (cell.consumerStatus != "PASS") return Decision.Denied("CONSUMER_CELL_BLOCKED")
                if (!cell.stopPathVerified || !cell.postCaptureCancelVerified) return Decision.Denied("STOP_PATH_UNVERIFIED")
            }
        }
        if (pack.packId == null) return Decision.Denied("NO_ACTIVE_PACK")
        if (purpose == BuildPurpose.CONSUMER && pack.calibrationStatus != "CALIBRATED") return Decision.Denied("PACK_NOT_RELEASE_CALIBRATED")
        val until = pack.leaseValidUntilEpochMs
        if (until != null && (!pack.timeTrustworthy || now >= until)) return Decision.Denied("PACK_LEASE_EXPIRED_OR_TIME_UNTRUSTED")
        return Decision.Eligible
    }
}
