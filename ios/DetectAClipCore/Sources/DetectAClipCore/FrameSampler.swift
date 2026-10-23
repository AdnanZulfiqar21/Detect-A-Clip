import Foundation

/// Selects which delivered frames are processed. OS delivery rate and processing rate are
/// different things (CQ-05): whatever the source delivers, at most one frame per 500 ms is
/// admitted (≤ 2 fps) and at most `capacity` frames per scan.
public struct FrameSampler: Sendable {
    public static let minimumSpacing: TimeInterval = 0.5

    public let capacity: Int
    public private(set) var admittedCount = 0
    private var lastAdmitted: TimeInterval?

    public init(capacity: Int) {
        precondition(capacity > 0)
        self.capacity = capacity
    }

    public var isFull: Bool { admittedCount >= capacity }

    public mutating func admit(at time: TimeInterval) -> Bool {
        guard !isFull else { return false }
        if let last = lastAdmitted, time - last < Self.minimumSpacing {
            return false
        }
        lastAdmitted = time
        admittedCount += 1
        return true
    }
}
