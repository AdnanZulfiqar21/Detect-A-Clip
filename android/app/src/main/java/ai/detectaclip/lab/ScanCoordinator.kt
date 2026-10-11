package ai.detectaclip.lab

import java.security.SecureRandom

/**
 * Single-session, consent-aware scan coordinator (roadmap F03 coordinator event table).
 *
 * Kotlin port of the reference semantics in l0/dac_l0/coordinator.py. Pure and
 * clock-injected so the LIFE-01/02/03 and SEC-02 orderings run as JVM unit tests; the
 * Android service calls it on one thread (the main looper) so every method is serialized.
 *
 * Invariants:
 *  - One lease and one cancellation generation per scan; a new start never resumes.
 *  - Observed abort / lock / revoke / cancel / entitlement failure / deadline before commit
 *    atomically invalidates the generation; nothing uncommitted publishes later.
 *  - A stop callback whose cause the adapter cannot attribute fails closed. Our own
 *    normal-close flag never establishes callback cause (CQ-02).
 *  - At most one committed result; memory only (D08 unapproved).
 *
 * Status: compiled and JVM-tested (ScanCoordinatorTest); device orderings unverified (B-01).
 */
class ScanCoordinator(
    private val budgets: Budgets = Budgets(),
    private val adapter: AdapterContract = AdapterContract(),
    private val idSource: () -> String = { randomId() },
) {
    data class Budgets(
        val permissionMs: Long = 60_000,
        val switchMs: Long = 30_000,
        val samplingMs: Long = 12_000,
        val totalMs: Long = 45_000,
        val postCaptureMs: Long = 8_000,
        val resultValidityMs: Long = 15 * 60_000,
    )

    /** Measured adapter semantics per OS/build; false until LIFE-03 device evidence exists. */
    data class AdapterContract(val canAttributeNormalClose: Boolean = false)

    enum class State { IDLE, AWAITING_PERMISSION, AWAITING_TARGET, ACQUIRING, POST_CAPTURE, COMMITTED, CANCELLED, FAILED }
    enum class StopCause { APP_REQUESTED_ACK, USER_STOP, SYSTEM_STOP, UNKNOWN }
    enum class Outcome {
        VERIFIED_MATCH, POSSIBLE_MATCH, NO_CONFIDENT_MATCH, INSUFFICIENT_SIGNAL,
        UNSUPPORTED_CAPTURE, PERMISSION_DENIED, CANCELLED, ERROR,
        // OUTSIDE_CATALOGUE and REMOTE_UNAVAILABLE are reserved and deliberately absent (L0/L1, Mode L).
    }

    /** Minimal committed result. No image, frame, descriptor or embedding field exists. */
    data class Result(
        val scanId: String,
        val generation: Long,
        val outcome: Outcome,
        val candidateWorkId: String?,
        val synthetic: Boolean,
        val flags: List<String>,
        val createdAtMs: Long,
        val expiresAtMs: Long,
        val candidateEditionId: String? = null,
        val candidateEpisodeId: String? = null,
    ) {
        init {
            val isMatch = outcome == Outcome.VERIFIED_MATCH || outcome == Outcome.POSSIBLE_MATCH
            require(isMatch == (candidateWorkId != null)) { "match states need a candidate; others must not name one" }
            require(isMatch || (candidateEditionId == null && candidateEpisodeId == null)) { "non-match states must not name an edition or episode" }
            require(expiresAtMs > createdAtMs)
        }

        fun validAt(nowMs: Long, clockTrustworthy: Boolean): Boolean =
            clockTrustworthy && nowMs >= createdAtMs && nowMs < expiresAtMs
    }

    var state: State = State.IDLE; private set
    var generation: Long = 0; private set
    var leaseActive: Boolean = false; private set
    var scanId: String? = null; private set
    var result: Result? = null; private set
    var closedReason: String = "NOT_CLOSED"; private set
    val events = ArrayList<String>()
    var commits = 0; private set
    var staleWorkerResults = 0; private set

    private var normalCloseRequested = false
    private var abortObserved = false
    private var permissionDeadline = 0L
    private var switchDeadline = 0L
    private var samplingDeadline = 0L
    private var totalDeadline = 0L
    private var postCaptureDeadline = 0L

    private val terminal = setOf(State.COMMITTED, State.CANCELLED, State.FAILED)
    private fun active() = state !in terminal && state != State.IDLE

    private fun abort(now: Long, reason: String, outcome: Outcome) {
        if (state == State.COMMITTED) {
            events += "$now: $reason after commit; committed result stands"
            leaseActive = false
            return
        }
        if (state in terminal || state == State.IDLE) return
        abortObserved = true
        generation += 1
        leaseActive = false
        state = if (outcome == Outcome.CANCELLED) State.CANCELLED else State.FAILED
        closedReason = reason
        result = Result(scanId ?: "none", generation, outcome, null, true, listOf(reason), now, now + budgets.resultValidityMs)
        events += "$now: ABORT $reason gen=$generation"
    }

    fun start(now: Long): Boolean {
        if (active()) { events += "$now: start rejected (active)"; return false }
        generation += 1
        leaseActive = true
        normalCloseRequested = false
        abortObserved = false
        result = null
        closedReason = "NOT_CLOSED"
        scanId = idSource()
        state = State.AWAITING_PERMISSION
        permissionDeadline = now + budgets.permissionMs
        events += "$now: START $scanId gen=$generation"
        return true
    }

    fun permissionGranted(now: Long): Boolean {
        if (state != State.AWAITING_PERMISSION || !leaseActive) { events += "$now: late permission callback rejected"; return false }
        if (now > permissionDeadline) { abort(now, "PERMISSION_TIMEOUT_LATE_CALLBACK", Outcome.ERROR); return false }
        state = State.AWAITING_TARGET
        switchDeadline = now + budgets.switchMs
        totalDeadline = now + budgets.totalMs
        return true
    }

    fun permissionDenied(now: Long) {
        if (state == State.AWAITING_PERMISSION) abort(now, "PERMISSION_DENIED", Outcome.PERMISSION_DENIED)
    }

    fun targetReady(now: Long): Boolean {
        if (state != State.AWAITING_TARGET) return false
        if (now > switchDeadline || now > totalDeadline) { abort(now, "TARGET_WAIT_TIMEOUT", Outcome.INSUFFICIENT_SIGNAL); return false }
        state = State.ACQUIRING
        samplingDeadline = minOf(now + budgets.samplingMs, totalDeadline)
        return true
    }

    fun frameAllowed(now: Long): Boolean =
        state == State.ACQUIRING && leaseActive && !abortObserved && now <= samplingDeadline && now <= totalDeadline

    fun normalCloseRequested(now: Long, remainingBackgroundMs: Long? = null): Boolean {
        if (state != State.ACQUIRING) return false
        normalCloseRequested = true
        state = State.POST_CAPTURE
        closedReason = "APP_REQUESTED_NORMAL_CLOSE"
        var budget = budgets.postCaptureMs
        if (remainingBackgroundMs != null) budget = minOf(budget, maxOf(0, remainingBackgroundMs))
        postCaptureDeadline = now + budget
        return true
    }

    fun captureStopped(now: Long, cause: StopCause) {
        if (state in terminal || state == State.IDLE) return
        when (cause) {
            StopCause.USER_STOP -> abort(now, "USER_STOP_OBSERVED", Outcome.CANCELLED)
            StopCause.SYSTEM_STOP -> abort(now, "SYSTEM_STOP_OBSERVED", Outcome.CANCELLED)
            StopCause.APP_REQUESTED_ACK ->
                if (normalCloseRequested && adapter.canAttributeNormalClose) events += "$now: attributable normal-close ack"
                else abort(now, if (normalCloseRequested) "STOP_CAUSE_UNATTRIBUTABLE" else "UNEXPECTED_STOP_ACK", Outcome.CANCELLED)
            StopCause.UNKNOWN -> abort(now, "STOP_CAUSE_UNKNOWN", Outcome.CANCELLED)
        }
    }

    fun lock(now: Long) = abort(now, "DEVICE_LOCKED", Outcome.CANCELLED)
    fun permissionRevoked(now: Long) = abort(now, "PERMISSION_REVOKED", Outcome.PERMISSION_DENIED)
    fun cancel(now: Long) = abort(now, "IN_APP_CANCEL", Outcome.CANCELLED)
    fun entitlementFailed(now: Long) = abort(now, "ENTITLEMENT_FAILED", Outcome.ERROR)

    fun tick(now: Long) {
        when (state) {
            State.AWAITING_PERMISSION -> if (now > permissionDeadline) abort(now, "PERMISSION_TIMEOUT", Outcome.ERROR)
            State.AWAITING_TARGET -> if (now > switchDeadline || now > totalDeadline) abort(now, "TARGET_WAIT_TIMEOUT", Outcome.INSUFFICIENT_SIGNAL)
            State.ACQUIRING -> if (now > samplingDeadline || now > totalDeadline) normalCloseRequested(now)
            State.POST_CAPTURE -> if (now > postCaptureDeadline) abort(now, "POST_CAPTURE_DEADLINE_EXPIRED", Outcome.ERROR)
            else -> Unit
        }
    }

    /** Commit path. Returns true iff the result was committed. */
    fun workerResult(now: Long, workerGeneration: Long, outcome: Outcome, workId: String?, flags: List<String> = emptyList(),
                     entitlementOk: Boolean = true, editionId: String? = null, episodeId: String? = null): Boolean {
        if (workerGeneration != generation || state != State.POST_CAPTURE || abortObserved || !leaseActive) {
            staleWorkerResults += 1
            return false
        }
        if (now > postCaptureDeadline) { abort(now, "POST_CAPTURE_DEADLINE_EXPIRED", Outcome.ERROR); return false }
        if (!entitlementOk) { entitlementFailed(now); return false }
        result = Result(scanId!!, generation, outcome, workId, true, flags, now, now + budgets.resultValidityMs, editionId, episodeId)
        state = State.COMMITTED
        leaseActive = false
        commits += 1
        return true
    }

    fun returnToApp(now: Long, entitlementOk: Boolean = true, clockTrustworthy: Boolean = true): Result? {
        val r = result ?: return null
        if (!r.validAt(now, clockTrustworthy) || !entitlementOk) { result = null; return null }
        return r
    }

    fun discard() { result = null }

    companion object {
        private val rng = SecureRandom()
        fun randomId(): String = ByteArray(8).also { rng.nextBytes(it) }.joinToString("") { "%02x".format(it) }
    }
}
