// Port of l0/dac_l0/coordinator.py (roadmap F03). Status: compiled/tested only where CI runs `swift test`.
// Pure and clock-injected; call from one serial queue.
import Foundation

public final class ScanCoordinator {
    public struct Budgets {
        public var permissionMs: Int64 = 60_000
        public var switchMs: Int64 = 30_000
        public var samplingMs: Int64 = 12_000
        public var totalMs: Int64 = 45_000
        public var postCaptureMs: Int64 = 8_000
        public var resultValidityMs: Int64 = 15 * 60_000
        public init() {}
    }

    public enum State { case idle, awaitingPermission, awaitingTarget, acquiring, postCapture, committed, cancelled, failed }
    public enum StopCause { case appRequestedAck, userStop, systemStop, unknown }
    /// OUTSIDE_CATALOGUE and REMOTE_UNAVAILABLE are reserved and deliberately absent (L0/L1, Mode L).
    public enum Outcome { case verifiedMatch, possibleMatch, noConfidentMatch, insufficientSignal, unsupportedCapture, permissionDenied, cancelled, error }

    /// Minimal committed result. No image, frame, descriptor or embedding field exists.
    public struct Result {
        public let scanId: String
        public let generation: Int64
        public let outcome: Outcome
        public let candidateWorkId: String?
        public let flags: [String]
        public let createdAtMs: Int64
        public let expiresAtMs: Int64
        public var candidateEditionId: String? = nil
        public var candidateEpisodeId: String? = nil
        public let synthetic = true

        public func valid(at now: Int64, clockTrustworthy: Bool) -> Bool {
            clockTrustworthy && now >= createdAtMs && now < expiresAtMs
        }
    }

    public private(set) var state: State = .idle
    public private(set) var generation: Int64 = 0
    public private(set) var leaseActive = false
    public private(set) var scanId: String?
    public private(set) var result: Result?
    public private(set) var commits = 0

    private let budgets: Budgets
    private let canAttributeNormalClose: Bool
    private let idSource: () -> String
    private var normalCloseRequested = false
    private var abortObserved = false
    private var permissionDeadline: Int64 = 0
    private var switchDeadline: Int64 = 0
    private var samplingDeadline: Int64 = 0
    private var totalDeadline: Int64 = 0
    private var postCaptureDeadline: Int64 = 0

    public init(budgets: Budgets = Budgets(), canAttributeNormalClose: Bool = false,
                idSource: @escaping () -> String = { UUID().uuidString }) {
        self.budgets = budgets
        self.canAttributeNormalClose = canAttributeNormalClose
        self.idSource = idSource
    }

    private var isTerminal: Bool { state == .committed || state == .cancelled || state == .failed }
    private var isActive: Bool { !isTerminal && state != .idle }

    private func abort(_ now: Int64, _ reason: String, _ outcome: Outcome) {
        if state == .committed { leaseActive = false; return }
        if isTerminal || state == .idle { return }
        abortObserved = true
        generation += 1
        leaseActive = false
        state = outcome == .cancelled ? .cancelled : .failed
        closedReason = reason
        result = Result(scanId: scanId ?? "none", generation: generation, outcome: outcome, candidateWorkId: nil,
                        flags: [reason], createdAtMs: now, expiresAtMs: now + budgets.resultValidityMs)
    }

    @discardableResult public func start(_ now: Int64) -> Bool {
        if isActive { return false }
        generation += 1
        leaseActive = true
        normalCloseRequested = false
        abortObserved = false
        result = nil
        scanId = idSource()
        state = .awaitingPermission
        permissionDeadline = now + budgets.permissionMs
        return true
    }

    @discardableResult public func permissionGranted(_ now: Int64) -> Bool {
        guard state == .awaitingPermission, leaseActive else { return false }
        if now > permissionDeadline { abort(now, "PERMISSION_TIMEOUT_LATE_CALLBACK", .error); return false }
        state = .awaitingTarget
        switchDeadline = now + budgets.switchMs
        totalDeadline = now + budgets.totalMs
        return true
    }

    @discardableResult public func targetReady(_ now: Int64) -> Bool {
        guard state == .awaitingTarget else { return false }
        if now > switchDeadline || now > totalDeadline { abort(now, "TARGET_WAIT_TIMEOUT", .insufficientSignal); return false }
        state = .acquiring
        samplingDeadline = min(now + budgets.samplingMs, totalDeadline)
        return true
    }

    public func frameAllowed(_ now: Int64) -> Bool {
        state == .acquiring && leaseActive && !abortObserved && now <= samplingDeadline && now <= totalDeadline
    }

    /// `remainingBackgroundMs` is diagnostic (backgroundTimeRemaining), never a promised grant.
    @discardableResult public func normalCloseRequested(_ now: Int64, remainingBackgroundMs: Int64? = nil) -> Bool {
        guard state == .acquiring else { return false }
        normalCloseRequested = true
        state = .postCapture
        var budget = budgets.postCaptureMs
        if let r = remainingBackgroundMs { budget = min(budget, max(0, r)) }
        postCaptureDeadline = now + budget
        return true
    }

    public func captureStopped(_ now: Int64, cause: StopCause) {
        if isTerminal || state == .idle { return }
        switch cause {
        case .userStop: abort(now, "USER_STOP_OBSERVED", .cancelled)
        case .systemStop: abort(now, "SYSTEM_STOP_OBSERVED", .cancelled)
        case .unknown: abort(now, "STOP_CAUSE_UNKNOWN", .cancelled)
        case .appRequestedAck:
            if !(normalCloseRequested && canAttributeNormalClose) {
                abort(now, normalCloseRequested ? "STOP_CAUSE_UNATTRIBUTABLE" : "UNEXPECTED_STOP_ACK", .cancelled)
            }
        }
    }

    public func lock(_ now: Int64) { abort(now, "DEVICE_LOCKED", .cancelled) }
    public func cancel(_ now: Int64) { abort(now, "IN_APP_CANCEL", .cancelled) }
    public func permissionRevoked(_ now: Int64) { abort(now, "PERMISSION_REVOKED", .permissionDenied) }
    /// Expiration handler of the finite background task (V16): cancel, never extend.
    public func backgroundTaskExpired(_ now: Int64) { abort(now, "BACKGROUND_TASK_EXPIRED", .error) }

    public func tick(_ now: Int64) {
        switch state {
        case .awaitingPermission where now > permissionDeadline:
            abort(now, "PERMISSION_TIMEOUT", .error)
        case .awaitingTarget where now > switchDeadline || now > totalDeadline:
            abort(now, "TARGET_WAIT_TIMEOUT", .insufficientSignal)
        case .acquiring where now > samplingDeadline || now > totalDeadline:
            normalCloseRequested(now)
        case .postCapture where now > postCaptureDeadline:
            abort(now, "POST_CAPTURE_DEADLINE_EXPIRED", .error)
        default:
            break
        }
    }

    public private(set) var staleWorkerResults = 0
    public private(set) var closedReason = "NOT_CLOSED"

    @discardableResult
    public func workerResult(_ now: Int64, generation g: Int64, outcome: Outcome, workId: String?, flags: [String] = [],
                             entitlementOk: Bool = true, editionId: String? = nil, episodeId: String? = nil) -> Bool {
        guard g == generation, state == .postCapture, !abortObserved, leaseActive else { staleWorkerResults += 1; return false }
        if now > postCaptureDeadline { abort(now, "POST_CAPTURE_DEADLINE_EXPIRED", .error); return false }
        if !entitlementOk { abort(now, "ENTITLEMENT_FAILED", .error); return false }
        let isMatch = outcome == .verifiedMatch || outcome == .possibleMatch
        precondition(isMatch == (workId != nil), "match states need a candidate; others must not name one")
        precondition(isMatch || (editionId == nil && episodeId == nil), "non-match states must not name an edition or episode")
        result = Result(scanId: scanId!, generation: generation, outcome: outcome, candidateWorkId: workId,
                        flags: flags, createdAtMs: now, expiresAtMs: now + budgets.resultValidityMs,
                        candidateEditionId: editionId, candidateEpisodeId: episodeId)
        state = .committed
        leaseActive = false
        commits += 1
        return true
    }

    public func returnToApp(_ now: Int64, entitlementOk: Bool = true, clockTrustworthy: Bool = true) -> Result? {
        guard let r = result else { return nil }
        if !r.valid(at: now, clockTrustworthy: clockTrustworthy) || !entitlementOk { result = nil; return nil }
        return r
    }
}
