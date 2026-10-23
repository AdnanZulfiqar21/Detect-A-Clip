import Foundation

/// Decision thresholds. These are lab budgets for the synthetic L0 pack only, marked
/// UNCALIBRATED until P04-T05; they are not D05-approved release criteria and must never be
/// relaxed after seeing outcomes.
public struct DecisionPolicy: Sendable, Equatable {
    public static let calibrationStatus = "UNCALIBRATED"

    public var maxHammingDistance = 6
    public var minSignalStdDev = 12.0
    public var minUsableFrames = 4
    public var verifiedMinVotes = 6
    public var verifiedMinVoteFraction = 0.6
    public var verifiedMinTemporalConsistency = 0.7
    public var possibleMinVotes = 3
    /// Runner-up votes must not exceed this fraction of the leader for VERIFIED_MATCH.
    public var maxRunnerUpFraction = 0.34
    /// Largest reference-frame step between consecutive matched samples that still counts as
    /// in-order playback.
    public var maxTemporalStep = 3

    public init() {}
}

/// One sampled query frame reduced to its descriptor. The frame itself is dropped as soon as
/// this is computed, so only 64-bit hashes are held for the duration of the scan.
public struct QuerySample: Sendable, Equatable {
    public let time: Double
    public let hash: UInt64
    public let usable: Bool

    public init(time: Double, hash: UInt64, usable: Bool) {
        self.time = time
        self.hash = hash
        self.usable = usable
    }

    public init(time: Double, frame: GrayFrame, policy: DecisionPolicy = DecisionPolicy()) {
        self.init(time: time, hash: PerceptualHash.dHash(frame),
                  usable: frame.standardDeviation >= policy.minSignalStdDev)
    }
}

/// Minimal evidence attached to a result: counts only, no numeric confidence (none is
/// calibrated) and no episode/time claim.
public struct Decision: Sendable, Equatable {
    public let state: ResultState
    public let work: SyntheticWork?
    public let matchedFrames: Int
    public let usableFrames: Int
    public let sampledFrames: Int
}

public struct Matcher: Sendable {
    public let catalogue: SyntheticCatalogue
    public let policy: DecisionPolicy

    public init(catalogue: SyntheticCatalogue, policy: DecisionPolicy = DecisionPolicy()) {
        self.catalogue = catalogue
        self.policy = policy
    }

    public func decide(_ samples: [QuerySample]) -> Decision {
        let usable = samples.filter(\.usable).sorted { $0.time < $1.time }
        guard usable.count >= policy.minUsableFrames else {
            return Decision(state: .insufficientSignal, work: nil, matchedFrames: 0,
                            usableFrames: usable.count, sampledFrames: samples.count)
        }

        var framesByWork: [Int: [Int]] = [:]
        for sample in usable {
            guard let hit = catalogue.nearest(to: sample.hash),
                  hit.distance <= policy.maxHammingDistance else { continue }
            framesByWork[hit.entry.workIndex, default: []].append(hit.entry.frameIndex)
        }

        let ranked = framesByWork.sorted {
            $0.value.count != $1.value.count ? $0.value.count > $1.value.count : $0.key < $1.key
        }
        guard let leader = ranked.first else {
            return Decision(state: .noConfidentMatch, work: nil, matchedFrames: 0,
                            usableFrames: usable.count, sampledFrames: samples.count)
        }

        let votes = leader.value.count
        let runnerUp = ranked.count > 1 ? ranked[1].value.count : 0
        let consistency = temporalConsistency(leader.value)
        let work = catalogue.works[leader.key]

        let state: ResultState
        if votes >= policy.verifiedMinVotes,
           Double(votes) / Double(usable.count) >= policy.verifiedMinVoteFraction,
           consistency >= policy.verifiedMinTemporalConsistency,
           Double(runnerUp) <= Double(votes) * policy.maxRunnerUpFraction {
            state = .verifiedMatch
        } else if votes >= policy.possibleMinVotes, runnerUp < votes {
            state = .possibleMatch
        } else {
            state = .noConfidentMatch
        }
        return Decision(state: state, work: state == .noConfidentMatch ? nil : work,
                        matchedFrames: votes, usableFrames: usable.count,
                        sampledFrames: samples.count)
    }

    /// Fraction of consecutive matched samples whose reference frames advance in playback order.
    private func temporalConsistency(_ frames: [Int]) -> Double {
        guard frames.count > 1 else { return 0 }
        var ordered = 0
        for i in 1..<frames.count {
            let step = frames[i] - frames[i - 1]
            if step >= 0 && step <= policy.maxTemporalStep {
                ordered += 1
            }
        }
        return Double(ordered) / Double(frames.count - 1)
    }
}
