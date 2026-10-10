package ai.detectaclip.lab

/**
 * Bounded frame selection (F05 intake/buffers). OS delivery rate is not assumed
 * controllable: surplus frames are rejected and the caller must close the Image at once.
 * At most [maxOwned] decoded frames (queued + in-flight), ≥ [minSpacingMs] between
 * selected frames (≤2 fps at 500 ms), monotonic timestamps only.
 *
 * Status: compiled and JVM-tested via PipelineGoldenTest and the lifecycle tests; device timing unverified (B-01).
 */
class FrameSelector(private val minSpacingMs: Long = 500, private val maxOwned: Int = 3) {
    var delivered = 0; private set
    var selected = 0; private set
    var droppedSpacing = 0; private set
    var droppedBufferFull = 0; private set
    var rejectedNonMonotonic = 0; private set
    var peakOwned = 0; private set
    var owned = 0; private set
    var closed = false; private set

    private var lastDelivered: Long? = null
    private var lastSelected: Long? = null

    init { require(minSpacingMs > 0 && maxOwned > 0) }

    fun offer(timestampMs: Long): Boolean {
        if (closed) return false
        delivered += 1
        val ld = lastDelivered
        if (ld != null && timestampMs <= ld) { rejectedNonMonotonic += 1; return false }
        lastDelivered = timestampMs
        val ls = lastSelected
        if (ls != null && timestampMs - ls < minSpacingMs) { droppedSpacing += 1; return false }
        if (owned >= maxOwned) { droppedBufferFull += 1; return false }
        owned += 1
        peakOwned = maxOf(peakOwned, owned)
        lastSelected = timestampMs
        selected += 1
        return true
    }

    fun release() {
        check(owned > 0) { "release without ownership" }
        owned -= 1
    }

    fun close() { closed = true }
}
