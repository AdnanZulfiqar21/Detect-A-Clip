// Swift port of l0/dac_l0/verify.py + decision.py (same rules as android Recognition.kt).
// Status: compiled and tested by the swift-core CI job (macOS, Swift 6.3.3; first pass at 3f77273); RecognitionGoldenTests (400 cases).
// Ordering: insertion order + stable sorts, exactly as the Python reference.

public enum Recognition {
    public struct Locator: Hashable { public let work: Int, edition: Int, tMs: Int }
    public struct Candidate { public let locator: Locator; public let distance: Double }

    public final class Hypothesis {
        public let work: Int
        public var edition: Int?
        public let offsetMs: Int, support: Int
        public let meanDistance: Double
        public let queryStartMs: Int, queryEndMs: Int
        public var ambiguousEditions: [Int] = []
        init(_ w: Int, _ e: Int?, _ o: Int, _ s: Int, _ m: Double, _ a: Int, _ b: Int) {
            work = w; edition = e; offsetMs = o; support = s; meanDistance = m; queryStartMs = a; queryEndMs = b
        }
        public var spanMs: Int { queryEndMs - queryStartMs }
    }

    public struct WorkEntry { public let index: Int; public let workId: String; public let seriesId: String?; public let episodeId: String?; public let editions: [String] }

    public struct Thresholds {
        public var minQualifiedFrames = 4, verifiedMinSupport = 6
        public var verifiedMinSupportFraction = 0.5
        public var verifiedMinSpanMs = 2500
        public var verifiedMaxMeanDistFrac = 0.8
        public var verifiedMinMargin = 3, possibleMinSupport = 3, possibleMinSpanMs = 1000
        public var possibleMaxMeanDistFrac = 0.9
        public var possibleOnCompetition = false
        public var episodeMargin = 3
        public var radius = 9.0
        public init() {}
    }

    public struct FrameSummary { public let selected: Int, qualified: Int, unusable: Int }

    public enum State: String { case VERIFIED_MATCH, POSSIBLE_MATCH, NO_CONFIDENT_MATCH, INSUFFICIENT_SIGNAL, UNSUPPORTED_CAPTURE, PERMISSION_DENIED, CANCELLED, ERROR }

    public struct Segment { public let workId: String; public let editionId: String?; public let queryStartMs: Int, queryEndMs: Int; public let referenceOffsetMs: Int?; public let supportingFrames: Int }

    public struct Decision {
        public let state: State
        public let workId, editionId, episodeId: String?
        public let flags: [String]
        public let segments: [Segment]
    }

    // Stable sort helper (Swift's sort is not guaranteed stable on all toolchains).
    static func stableSorted<T>(_ xs: [T], by less: (T, T) -> Bool) -> [T] {
        xs.enumerated().sorted { a, b in less(a.element, b.element) || (!less(b.element, a.element) && a.offset < b.offset) }.map { $0.element }
    }

    static func hypLess(_ a: Hypothesis, _ b: Hypothesis) -> Bool {
        if a.support != b.support { return a.support > b.support }
        return a.meanDistance < b.meanDistance
    }

    private struct P3 { let qt: Int, off: Int; let d: Double }

    private static func clusterOffsets(_ pairs: [P3], _ tol: Int) -> (Int, [P3]) {
        var bestC = 0
        var best: [P3] = []
        for c in Set(pairs.map { $0.off }).sorted() {
            var order: [Int] = []
            var members: [Int: P3] = [:]
            for p in pairs where abs(p.off - c) <= tol {
                if let prev = members[p.qt] { if p.d < prev.d { members[p.qt] = p } } else { members[p.qt] = p; order.append(p.qt) }
            }
            if members.count > best.count { bestC = c; best = order.map { members[$0]! } }
        }
        return (bestC, best)
    }

    public static func verify(_ perFrame: [(Int, [Candidate])], samplingIntervalMs: Int, minSupport: Int = 2, editionMargin: Int = 3) -> [Hypothesis] {
        let tol = samplingIntervalMs / 2 + 250
        var keys: [[Int]] = []
        var byWe: [[Int]: [P3]] = [:]
        for (qt, cands) in perFrame {
            for c in cands {
                let k = [c.locator.work, c.locator.edition]
                if byWe[k] == nil { byWe[k] = []; keys.append(k) }
                byWe[k]!.append(P3(qt: qt, off: c.locator.tMs - qt, d: c.distance))
            }
        }
        var raw: [Hypothesis] = []
        for k in keys {
            let (centre, m) = clusterOffsets(byWe[k]!, tol)
            if m.count < minSupport { continue }
            var sum = 0.0
            for x in m { sum += x.d }
            raw.append(Hypothesis(k[0], k[1], centre, m.count, sum / Double(m.count), m.map { $0.qt }.min()!, m.map { $0.qt }.max()!))
        }
        var workOrder: [Int] = []
        var byWork: [Int: [Hypothesis]] = [:]
        for h in raw { if byWork[h.work] == nil { byWork[h.work] = []; workOrder.append(h.work) }; byWork[h.work]!.append(h) }
        var merged: [Hypothesis] = []
        for w in workOrder {
            let hs = stableSorted(byWork[w]!, by: hypLess)
            let top = hs[0]
            let tied = hs.filter { $0.support > top.support - editionMargin && $0.edition != top.edition }
            if !tied.isEmpty {
                top.ambiguousEditions = Array(Set([top.edition!] + tied.map { $0.edition! })).sorted()
                top.edition = nil
            }
            merged.append(top)
        }
        return stableSorted(merged, by: hypLess)
    }

    public static func segmentMontage(_ hyps: [Hypothesis], minSupport: Int = 3) -> [Hypothesis] {
        var segs: [Hypothesis] = []
        for h in hyps where h.support >= minSupport {
            var overlap = false
            for s in segs {
                let lo = max(h.queryStartMs, s.queryStartMs), hi = min(h.queryEndMs, s.queryEndMs)
                if Double(hi - lo) > 0.5 * Double(max(1, min(h.queryEndMs - h.queryStartMs, s.queryEndMs - s.queryStartMs))) { overlap = true; break }
            }
            if !overlap { segs.append(h) }
        }
        return stableSorted(segs) { $0.queryStartMs < $1.queryStartMs }
    }

    public static func decide(_ hyps: [Hypothesis], frames: FrameSummary, works: [WorkEntry], th: Thresholds, entitlementOk: Bool = true) -> Decision {
        func plain(_ s: State, _ f: [String]) -> Decision { Decision(state: s, workId: nil, editionId: nil, episodeId: nil, flags: f, segments: []) }
        if !entitlementOk { return plain(.ERROR, ["ENTITLEMENT_RECHECK_FAILED"]) }
        if frames.selected > 0 && frames.unusable == frames.selected { return plain(.UNSUPPORTED_CAPTURE, ["ALL_FRAMES_BLANK"]) }
        if frames.qualified < th.minQualifiedFrames { return plain(.INSUFFICIENT_SIGNAL, ["QUALIFIED_FRAMES=\(frames.qualified)"]) }
        if hyps.isEmpty { return plain(.NO_CONFIDENT_MATCH, []) }

        func key(_ h: Hypothesis) -> String { let w = works[h.work]; return w.seriesId.map { "SERIES:\($0)" } ?? "WORK:\(w.workId)" }
        func strong(_ h: Hypothesis, _ ms: Int, _ span: Int, _ frac: Double) -> Bool { h.support >= ms && h.spanMs >= span && h.meanDistance <= frac * th.radius }

        var gOrder: [String] = []
        var groups: [String: [Hypothesis]] = [:]
        for h in hyps { let k = key(h); if groups[k] == nil { groups[k] = []; gOrder.append(k) }; groups[k]!.append(h) }
        let sortedGroups = gOrder.map { stableSorted(groups[$0]!, by: hypLess) }
        let ranked = stableSorted(sortedGroups) { hypLess($0[0], $1[0]) }
        let topList = ranked[0], top = topList[0]
        let competitor = ranked.count > 1 ? ranked[1][0] : nil
        let margin = top.support - (competitor?.support ?? 0)

        var flags: [String] = []
        let segments = segmentMontage(hyps, minSupport: th.possibleMinSupport)
        let montage = Set(segments.map(key)).count > 1
        let competing = competitor != nil && margin < th.verifiedMinMargin && !montage
        let tw = works[top.work]
        var epAmb = false
        if tw.seriesId != nil { epAmb = topList.dropFirst().contains { $0.work != top.work && $0.support > top.support - th.episodeMargin } }
        if !top.ambiguousEditions.isEmpty { flags.append("EDITION_AMBIGUOUS") }
        if epAmb { flags.append("EPISODE_AMBIGUOUS") }
        if montage { flags.append("MULTI_TITLE_SEGMENTS") }
        if competing { flags.append("COMPETING_WORKS") }

        func names(_ h: Hypothesis, _ amb: Bool) -> (String, String?, String?) {
            let w = works[h.work]
            let ed = h.edition.map { w.editions[$0] }
            if let s = w.seriesId { return amb ? (s, nil, nil) : (s, ed, w.episodeId) }
            return (w.workId, ed, nil)
        }
        func seg(_ h: Hypothesis, _ amb: Bool) -> Segment {
            let (w, ed, _) = names(h, amb)
            let unique = ed != nil && !amb
            return Segment(workId: w, editionId: ed, queryStartMs: h.queryStartMs, queryEndMs: h.queryEndMs, referenceOffsetMs: unique ? h.offsetMs : nil, supportingFrames: h.support)
        }
        func match(_ s: State, _ h: Hypothesis, _ segs: [Segment], _ extra: [String], _ amb: Bool) -> Decision {
            let (w, ed, ep) = names(h, amb)
            return Decision(state: s, workId: w, editionId: ed, episodeId: ep, flags: flags + extra, segments: segs)
        }
        func possible(_ h: Hypothesis) -> Bool { strong(h, th.possibleMinSupport, th.possibleMinSpanMs, th.possibleMaxMeanDistFrac) }

        if montage {
            let ss = segments.filter(possible)
            guard var lead = ss.first else { return plain(.NO_CONFIDENT_MATCH, flags) }
            for s in ss where s.support > lead.support || (s.support == lead.support && s.meanDistance < lead.meanDistance) { lead = s }
            return match(.POSSIBLE_MATCH, lead, ss.map { seg($0, true) }, [], true)
        }
        let frac = Double(top.support) / Double(max(1, frames.selected))
        let verified = !competing && strong(top, th.verifiedMinSupport, th.verifiedMinSpanMs, th.verifiedMaxMeanDistFrac)
            && frac >= th.verifiedMinSupportFraction && margin >= th.verifiedMinMargin
        if verified { return match(.VERIFIED_MATCH, top, [seg(top, epAmb)], [], epAmb) }
        if competing && !th.possibleOnCompetition { return plain(.NO_CONFIDENT_MATCH, flags) }
        if possible(top) { return match(.POSSIBLE_MATCH, top, [seg(top, epAmb)], ["WEAK_SUPPORT"], epAmb) }
        return plain(.NO_CONFIDENT_MATCH, flags)
    }
}
