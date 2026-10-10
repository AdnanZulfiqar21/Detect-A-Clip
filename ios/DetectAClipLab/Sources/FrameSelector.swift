// Port of android FrameSelector.kt / l0 sampler.py (F05 intake). Status: compiled and tested by the swift-core CI job (macOS, Swift 6.3.3; first pass at 3f77273).
// OS delivery rate is not assumed controllable: refused frames must be released at once.

public final class FrameSelector {
    public let minSpacingMs: Int64
    public let maxOwned: Int
    public private(set) var delivered = 0
    public private(set) var selected = 0
    public private(set) var droppedSpacing = 0
    public private(set) var droppedBufferFull = 0
    public private(set) var rejectedNonMonotonic = 0
    public private(set) var owned = 0
    public private(set) var peakOwned = 0
    public private(set) var closed = false
    private var lastDelivered: Int64?
    private var lastSelected: Int64?

    public init(minSpacingMs: Int64 = 500, maxOwned: Int = 3) {
        precondition(minSpacingMs > 0 && maxOwned > 0)
        self.minSpacingMs = minSpacingMs
        self.maxOwned = maxOwned
    }

    /// Returns true if the caller may take ownership of this frame.
    public func offer(_ timestampMs: Int64) -> Bool {
        if closed { return false }
        delivered += 1
        if let ld = lastDelivered, timestampMs <= ld { rejectedNonMonotonic += 1; return false }
        lastDelivered = timestampMs
        if let ls = lastSelected, timestampMs - ls < minSpacingMs { droppedSpacing += 1; return false }
        if owned >= maxOwned { droppedBufferFull += 1; return false }
        owned += 1
        peakOwned = max(peakOwned, owned)
        lastSelected = timestampMs
        selected += 1
        return true
    }

    public func release() {
        precondition(owned > 0, "release without ownership")
        owned -= 1
    }

    public func close() { closed = true }
}
