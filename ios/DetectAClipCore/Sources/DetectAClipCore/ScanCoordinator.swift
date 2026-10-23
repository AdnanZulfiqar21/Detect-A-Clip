import Foundation

public enum CaptureSource: String, Sendable, CaseIterable {
    /// In-app synthetic playback; no screen capture involved.
    case syntheticInApp
    /// Another app's screen (ReplayKit / ScreenCaptureKit research paths). Disabled in this
    /// build until the iOS G00 gate; selecting it ends in UNSUPPORTED_CAPTURE.
    case otherAppScreen
}

/// Why a scan ended. Capture Stop and post-capture Cancel are distinct user actions (CQ-02).
public enum TerminalReason: String, Sendable {
    case completed
    case userStoppedCapture
    case userCancelledComputation
    case deviceLocked
    case appLeftForeground
    case permissionRevoked
    case stopCauseUnresolved
    case postCaptureTimeout
    case totalTimeout
    case captureDisabledInBuild
    case permissionDenied
    case internalError
}

public struct ScanTicket: Sendable, Hashable {
    public let scanID: UUID
    public let generation: UInt64
}

/// F05 proposals (D05, not approved): sampling window, ≤ 8 s post-close hard cap and a 15 s
/// total budget measured from consent.
public struct ScanDeadlines: Sendable, Equatable {
    public var sampling: TimeInterval = 8
    public var postCapture: TimeInterval = 8
    public var total: TimeInterval = 15

    public init() {}
}

/// The single committed, immutable outcome of a scan. Memory only (D08 MEMORY_ONLY).
public struct ScanOutcome: Sendable, Equatable {
    public let scanID: UUID
    public let generation: UInt64
    public let state: ResultState
    public let reason: TerminalReason
    public let decision: Decision?
    public let createdAt: TimeInterval
    public let expiresAt: TimeInterval
}

public enum ScanPhase: Sendable, Equatable {
    case idle
    case awaitingConsent(CaptureSource)
    case acquiring(ScanTicket, source: CaptureSource, sampled: Int)
    case computing(ScanTicket)
    case finished(ScanOutcome)

    public var isActive: Bool {
        switch self {
        case .acquiring, .computing: return true
        default: return false
        }
    }
}

public enum SampleDisposition: Sendable, Equatable {
    case rejected
    case recorded
    /// Sampler is full: acquisition closed normally and post-capture computation may begin.
    case recordedAndClosed
}

/// One consent-aware coordinator per app (F03 coordinator event table). Every transition runs
/// under one lock so that a cancellation serialized before commit always wins, late callbacks
/// from an earlier generation are rejected, and at most one result is ever published.
public final class ScanCoordinator: @unchecked Sendable {
    public static let resultValidity: TimeInterval = 15 * 60

    private let lock = NSLock()
    private let clock: () -> TimeInterval
    private let deadlines: ScanDeadlines
    private let samplerCapacity: Int

    private var generation: UInt64 = 0
    private var state: ScanPhase = .idle
    private var sampler: FrameSampler
    private var samples: [QuerySample] = []
    private var consentedAt: TimeInterval = 0
    private var captureClosedAt: TimeInterval = 0

    public init(deadlines: ScanDeadlines = ScanDeadlines(),
                samplerCapacity: Int = 12,
                clock: @escaping () -> TimeInterval = { ProcessInfo.processInfo.systemUptime }) {
        self.deadlines = deadlines
        self.samplerCapacity = samplerCapacity
        self.sampler = FrameSampler(capacity: samplerCapacity)
        self.clock = clock
    }

    public var phase: ScanPhase {
        locked { state }
    }

    // MARK: Start and consent

    /// User pressed Start. Clears any previous result and shows the per-scan disclosure.
    /// Refused while another scan is active (single session).
    @discardableResult
    public func requestStart(source: CaptureSource) -> Bool {
        locked {
            guard !state.isActive else { return false }
            state = .awaitingConsent(source)
            return true
        }
    }

    public func declineConsent() {
        locked {
            if case .awaitingConsent = state {
                state = .idle
            }
        }
    }

    /// Consent given for exactly one scan: fresh unpredictable scan ID, new generation, empty
    /// sampler. Never resumes an earlier acquisition.
    public func confirmConsent() -> ScanTicket? {
        locked {
            guard case let .awaitingConsent(source) = state else { return nil }
            generation &+= 1
            let ticket = ScanTicket(scanID: UUID(), generation: generation)
            sampler = FrameSampler(capacity: samplerCapacity)
            samples = []
            consentedAt = clock()
            state = .acquiring(ticket, source: source, sampled: 0)
            return ticket
        }
    }

    // MARK: Acquisition

    /// Asks whether the frame delivered now should be processed. Returns the scan-relative
    /// time to stamp the sample with, or nil when the frame must be dropped unprocessed.
    public func admitFrame(_ ticket: ScanTicket) -> TimeInterval? {
        locked {
            guard isAcquiring(ticket) else { return nil }
            let elapsed = clock() - consentedAt
            return sampler.admit(at: elapsed) ? elapsed : nil
        }
    }

    public func record(_ ticket: ScanTicket, sample: QuerySample) -> SampleDisposition {
        locked {
            guard case let .acquiring(current, source, _) = state, current == ticket,
                  ticket.generation == generation else { return .rejected }
            samples.append(sample)
            if sampler.isFull {
                closeAcquisitionLocked(ticket)
                return .recordedAndClosed
            }
            state = .acquiring(ticket, source: source, sampled: samples.count)
            return .recorded
        }
    }

    /// App-requested normal close (sampling window over or source ended). Distinct from a
    /// stop whose cause is unknown, which must go through `cancel(_:reason:)`.
    @discardableResult
    public func closeAcquisition(_ ticket: ScanTicket) -> Bool {
        locked {
            guard isAcquiring(ticket) else { return false }
            closeAcquisitionLocked(ticket)
            return true
        }
    }

    // MARK: Post-capture computation and commit

    public func samplesForDecision(_ ticket: ScanTicket) -> [QuerySample]? {
        locked {
            guard case let .computing(current) = state, current == ticket,
                  ticket.generation == generation else { return nil }
            return samples
        }
    }

    /// Atomic commit: rechecks generation, phase and deadlines under the lock. Anything that
    /// invalidated the scan first wins and the decision is discarded.
    @discardableResult
    public func commit(_ ticket: ScanTicket, decision: Decision) -> ScanOutcome? {
        locked {
            guard case let .computing(current) = state, current == ticket,
                  ticket.generation == generation else { return nil }
            if let expired = expiredDeadlineLocked() {
                cancelLocked(reason: expired)
                return nil
            }
            precondition(!ResultState.unreachableInL0L1.contains(decision.state),
                         "OUTSIDE_CATALOGUE is unreachable in L0/L1")
            return finishLocked(ticket, state: decision.state, reason: .completed, decision: decision)
        }
    }

    /// Ends an acquiring scan without a recognition attempt (capture unavailable or refused).
    @discardableResult
    public func fail(_ ticket: ScanTicket, state result: ResultState,
                     reason: TerminalReason) -> ScanOutcome? {
        locked {
            guard isAcquiring(ticket) || isComputing(ticket) else { return nil }
            return finishLocked(ticket, state: result, reason: reason, decision: nil)
        }
    }

    // MARK: Cancellation, deadlines, expiry

    /// In-app Stop/Cancel, lock, revoke, leaving the foreground or an unresolved stop cause.
    /// Invalidates the generation so no uncommitted work can publish later. With a ticket,
    /// only that scan is cancelled; without one, whichever scan is active.
    @discardableResult
    public func cancel(_ ticket: ScanTicket? = nil, reason: TerminalReason) -> Bool {
        locked {
            switch state {
            case let .acquiring(current, _, _), let .computing(current):
                if let ticket, ticket != current { return false }
                cancelLocked(reason: reason)
                return true
            case .awaitingConsent:
                guard ticket == nil else { return false }
                state = .idle
                return true
            case .idle, .finished:
                return false
            }
        }
    }

    /// Periodic deadline check: ends the sampling window normally, cancels on post-capture or
    /// total budget expiry, and drops an expired result.
    public func tick() {
        locked {
            switch state {
            case let .acquiring(ticket, _, _):
                if let expired = expiredDeadlineLocked(), expired == .totalTimeout {
                    cancelLocked(reason: expired)
                } else if clock() - consentedAt >= deadlines.sampling {
                    closeAcquisitionLocked(ticket)
                }
            case .computing:
                if let expired = expiredDeadlineLocked() {
                    cancelLocked(reason: expired)
                }
            case let .finished(outcome):
                if clock() >= outcome.expiresAt {
                    state = .idle
                }
            case .idle, .awaitingConsent:
                break
            }
        }
    }

    /// The result to display, if still valid (next scan or 15 minutes, whichever first).
    public func currentOutcome() -> ScanOutcome? {
        locked {
            guard case let .finished(outcome) = state else { return nil }
            guard clock() < outcome.expiresAt else {
                state = .idle
                return nil
            }
            return outcome
        }
    }

    public func discard() {
        locked {
            if case .finished = state {
                state = .idle
            }
        }
    }

    // MARK: Private (call with lock held)

    private func locked<T>(_ body: () -> T) -> T {
        lock.lock()
        defer { lock.unlock() }
        return body()
    }

    private func isAcquiring(_ ticket: ScanTicket) -> Bool {
        guard case let .acquiring(current, _, _) = state else { return false }
        return current == ticket && ticket.generation == generation
    }

    private func isComputing(_ ticket: ScanTicket) -> Bool {
        guard case let .computing(current) = state else { return false }
        return current == ticket && ticket.generation == generation
    }

    private func closeAcquisitionLocked(_ ticket: ScanTicket) {
        captureClosedAt = clock()
        state = .computing(ticket)
    }

    private func expiredDeadlineLocked() -> TerminalReason? {
        let now = clock()
        if now - consentedAt > deadlines.total { return .totalTimeout }
        if case .computing = state, now - captureClosedAt > deadlines.postCapture {
            return .postCaptureTimeout
        }
        return nil
    }

    private func cancelLocked(reason: TerminalReason) {
        let ticket: ScanTicket
        switch state {
        case let .acquiring(current, _, _), let .computing(current):
            ticket = current
        default:
            return
        }
        generation &+= 1
        _ = finishLocked(ticket, state: .cancelled, reason: reason, decision: nil)
    }

    private func finishLocked(_ ticket: ScanTicket, state result: ResultState,
                              reason: TerminalReason, decision: Decision?) -> ScanOutcome {
        let now = clock()
        let outcome = ScanOutcome(scanID: ticket.scanID, generation: ticket.generation,
                                  state: result, reason: reason, decision: decision,
                                  createdAt: now, expiresAt: now + Self.resultValidity)
        samples = []
        state = .finished(outcome)
        return outcome
    }
}
