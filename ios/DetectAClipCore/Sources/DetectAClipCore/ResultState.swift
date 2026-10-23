import Foundation

/// Canonical result enum (roadmap F03). REMOTE_UNAVAILABLE is reserved for Mode R, which is
/// OFF, so it is not represented at all. OUTSIDE_CATALOGUE is reserved and unreachable in
/// L0/L1: an ordinary non-match is NO_CONFIDENT_MATCH and absence is never derived from it.
public enum ResultState: String, CaseIterable, Sendable {
    case verifiedMatch = "VERIFIED_MATCH"
    case possibleMatch = "POSSIBLE_MATCH"
    case noConfidentMatch = "NO_CONFIDENT_MATCH"
    case outsideCatalogue = "OUTSIDE_CATALOGUE"
    case insufficientSignal = "INSUFFICIENT_SIGNAL"
    case unsupportedCapture = "UNSUPPORTED_CAPTURE"
    case permissionDenied = "PERMISSION_DENIED"
    case cancelled = "CANCELLED"
    case error = "ERROR"

    /// States no L0/L1 code path may emit (F-12, AI-07).
    public static let unreachableInL0L1: Set<ResultState> = [.outsideCatalogue]
}
