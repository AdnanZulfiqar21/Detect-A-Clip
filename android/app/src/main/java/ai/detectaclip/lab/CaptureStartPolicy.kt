package ai.detectaclip.lab

/**
 * Capture-boundary rules shared by [MainActivity] and [CaptureService]. Pure Kotlin so the
 * fail-closed paths run as JVM tests (CaptureStartPolicyTest).
 *
 * - The mediaProjection foreground service is started only with a granted consent result
 *   (RESULT_OK and a non-null consent Intent) from a picker that a user action opened.
 *   A denied or empty result records PERMISSION_DENIED and never starts the service: on
 *   Android 14+ promoting a mediaProjection-type service without consent throws, and a
 *   service started with startForegroundService must promote itself, so the only safe
 *   denial path is not to start it at all.
 * - Inside the service a stop request is handled before anything else, and a start
 *   without a usable consent result is refused before the service is promoted.
 *
 * Status: JVM-tested; the OS behaviour it guards against is a device check (B-01).
 */
object CaptureStartPolicy {

    enum class ServiceStart { STOP_REQUEST, DENY_NO_CONSENT, PROCEED }

    /** Called from onActivityResult. Returns true iff the caller may start the service. */
    fun onPickerResult(coordinator: ScanCoordinator, now: Long, resultOk: Boolean, hasConsentData: Boolean): Boolean {
        if (resultOk && hasConsentData) return true
        coordinator.permissionDenied(now)
        return false
    }

    /** First decision in CaptureService.onStartCommand, before startForeground. */
    fun onServiceStart(isStopAction: Boolean, resultOk: Boolean, hasConsentData: Boolean): ServiceStart = when {
        isStopAction -> ServiceStart.STOP_REQUEST
        !resultOk || !hasConsentData -> ServiceStart.DENY_NO_CONSENT
        else -> ServiceStart.PROCEED
    }
}
