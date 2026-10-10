// Swift port of android PackIndex.kt: the index payload format contract of docs/PACK_FORMAT.md
// and l0/dac_l0/index/format.py (writer idx-flat-4, reader idx-flat-3 and idx-flat-4), plus
// Hamming flat retrieval and display-name resolution. Every verdict must match Python on
// golden_format_cases.txt (FormatContractTests). DACDHASH payloads only.
// Status: compiled and tested by the swift-core CI job (macOS, Swift 6.3.3; first pass at 3f77273) (docs/TEST_EVIDENCE.md).
import Foundation

public enum PackError: Error, Equatable { case invalid(String) }

/// ASCII-only validators equivalent to the contract's anchored regexes (no trailing newline,
/// no non-ASCII letters or digits).
enum Ascii {
    static func alnum(_ c: UInt8) -> Bool { (c >= 48 && c <= 57) || (c >= 65 && c <= 90) || (c >= 97 && c <= 122) }
    static func lower(_ c: UInt8) -> Bool { c >= 97 && c <= 122 }
    static func all(_ s: String, _ ok: (UInt8) -> Bool) -> Bool { s.utf8.allSatisfy(ok) }
    /// ^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$
    static func isId(_ s: String) -> Bool {
        let b = Array(s.utf8)
        return (1...64).contains(b.count) && alnum(b[0]) && b.dropFirst().allSatisfy { alnum($0) || $0 == 95 || $0 == 46 || $0 == 45 }
    }
    /// ^[A-Za-z0-9_.-]{1,64}$
    static func isEpisode(_ s: String) -> Bool {
        let b = Array(s.utf8)
        return (1...64).contains(b.count) && b.allSatisfy { alnum($0) || $0 == 95 || $0 == 46 || $0 == 45 }
    }
    /// ^[A-Za-z0-9_]{1,64}$
    static func isEdition(_ s: String) -> Bool {
        let b = Array(s.utf8)
        return (1...64).contains(b.count) && b.allSatisfy { alnum($0) || $0 == 95 }
    }
    /// ^[a-z]{2,3}(-[A-Za-z0-9]{2,8}){0,3}$
    static func isLocale(_ s: String) -> Bool {
        let parts: [[UInt8]] = s.utf8.split(separator: 45, omittingEmptySubsequences: false).map { Array($0) }
        guard (1...4).contains(parts.count), (2...3).contains(parts[0].count), parts[0].allSatisfy(lower) else { return false }
        return parts.dropFirst().allSatisfy { (2...8).contains($0.count) && $0.allSatisfy(alnum) }
    }
}

public struct PackIndex {
    public struct SharedSceneMember: Equatable { public let workIndex: Int, editionIndex: Int; public let startMs: Int64, endMs: Int64 }
    public struct SharedScene: Equatable { public let groupId: String; public let members: [SharedSceneMember] }

    public static let formatV3 = "idx-flat-3"
    public static let formatV4 = "idx-flat-4"
    public static let exactPreprocessing = "dac-crop-v1+dac-qual-v1+dac-dhash-v1"

    public let formatVersion: String
    public let samplingIntervalS: Double
    public let hashes: [UInt64]
    let locs: [(Int, Int, Int)]
    public let works: [Recognition.WorkEntry]
    public let names: [[String: String]]
    public let aliases: [[String]]
    public let sharedScenes: [SharedScene]

    public var vectorCount: Int { hashes.count }

    static let workKeysV3: Set<String> = ["work_index", "work_id", "synthetic_title", "editions", "durations_s", "series_id", "episode_id", "names"]
    static let metaKeysV3: Set<String> = ["index_format_version", "generator_version", "preprocessing_version", "family", "works"]

    /// Python len() counts code points; so does unicodeScalars. Control characters (< 32) refused.
    static func text(_ v: JSONValue?, _ what: String, max: Int = 200) throws -> String {
        guard let s = v?.string else { throw PackError.invalid("bad \(what)") }
        let n = s.unicodeScalars.count
        guard n >= 1, n <= max, !s.utf16.contains(where: { $0 < 32 }) else { throw PackError.invalid("bad \(what)") }
        return s
    }

    static func int(_ v: JSONValue?, _ what: String) throws -> Int64 {
        guard let x = v?.int else { throw PackError.invalid("bad \(what)") }   // doubles and booleans refused
        return x
    }

    static func ceilMs(_ seconds: Double) -> Int64 { Int64((seconds * 1000.0).rounded(.up)) }

    /// Same order as Python resolve_display_name: exact locale, same language, English, first, fallback.
    public static func resolveDisplayName(_ names: [String: String], preferences: [String], fallback: String) -> String {
        for p in preferences { if let v = names[p] { return v } }
        let sortedKeys = names.keys.sorted()
        for p in preferences {
            let lang = p.split(separator: "-", omittingEmptySubsequences: false).first.map(String.init) ?? p
            for k in sortedKeys where (k.split(separator: "-", omittingEmptySubsequences: false).first.map(String.init) ?? k) == lang { return names[k]! }
        }
        if let en = names["en"] { return en }
        return sortedKeys.first.map { names[$0]! } ?? fallback
    }

    public func displayName(workIndex: Int, preferences: [String]) -> String {
        PackIndex.resolveDisplayName(names[workIndex], preferences: preferences, fallback: works[workIndex].workId)
    }

    /// Same as Python result_display_name: an episode result shows that episode's name; a
    /// series-level result or an unknown ID shows the ID itself; no candidate -> nil.
    public func resultDisplayName(workId: String?, episodeId: String?, preferences: [String]) -> String? {
        guard let id = workId else { return nil }
        let idx = works.firstIndex { w -> Bool in
            if let ep = episodeId { return w.seriesId == id && w.episodeId == ep }
            return w.workId == id && w.seriesId == nil
        }
        return idx.map { displayName(workIndex: $0, preferences: preferences) } ?? id
    }

    public static func parse(_ d: [UInt8], maxPayloadBytes: Int = 250_000_000) throws -> PackIndex {
        func fail(_ m: String) -> PackError { .invalid(m) }
        guard d.count <= maxPayloadBytes else { throw fail("payload exceeds installed index budget") }
        guard d.count >= 32 else { throw fail("payload too short") }
        var o = 0
        func u16() -> Int { defer { o += 2 }; return Int(d[o]) | Int(d[o + 1]) << 8 }
        func u32() -> UInt32 { defer { o += 4 }; return (0..<4).reduce(UInt32(0)) { $0 | UInt32(d[o + $1]) << (8 * UInt32($1)) } }
        func u64() -> UInt64 { defer { o += 8 }; return (0..<8).reduce(UInt64(0)) { $0 | UInt64(d[o + $1]) << (8 * UInt64($1)) } }
        guard Array(d[0..<8]) == Array("DACL0IDX".utf8) else { throw fail("bad magic") }
        o = 8
        guard u16() == 1 else { throw fail("bad version") }
        let dBytes = u16()
        let n = Int(u32()), nWorks = Int(u32())
        let interval = Double(bitPattern: u64())
        guard dBytes == 8 else { throw fail("only 8-byte hash descriptors are supported by this engine") }
        guard n <= 20_000_000, nWorks <= 1_000_000 else { throw fail("count out of bounds") }
        guard interval >= 0.1, interval <= 60.0 else { throw fail("sampling interval out of bounds") }
        let metaLen = Int(u32())
        guard metaLen <= 64 * 1024 * 1024, d.count - o >= metaLen else { throw fail("bad metadata length") }
        guard let metaText = String(data: Data(d[o..<(o + metaLen)]), encoding: .utf8) else { throw fail("metadata not UTF-8") }
        o += metaLen
        let metaValue: JSONValue
        do { metaValue = try MiniJson.parse(metaText) } catch { throw fail("metadata not valid JSON") }
        guard let meta = metaValue.object else { throw fail("metadata not an object") }

        let fmt = meta["index_format_version"]?.string
        guard fmt == formatV3 || fmt == formatV4 else { throw fail("incompatible index format version") }
        let v4 = fmt == formatV4
        guard meta.keySet == (v4 ? metaKeysV3.union(["shared_scenes"]) : metaKeysV3) else { throw fail("metadata keys mismatch") }
        for k in ["generator_version", "preprocessing_version", "family"] { _ = try text(meta[k], k) }
        guard meta["family"]?.string == "DACDHASH" else { throw fail("this engine only accepts DACDHASH packs") }
        guard meta["preprocessing_version"]?.string == exactPreprocessing else { throw fail("preprocessing version does not match the descriptor family") }

        guard let worksRaw = meta["works"]?.array, worksRaw.count == nWorks else { throw fail("work table mismatch") }
        let workKeys = v4 ? workKeysV3.union(["aliases"]) : workKeysV3
        var works: [Recognition.WorkEntry] = [], names: [[String: String]] = [], aliases: [[String]] = [], durations: [[Double]] = []
        var seenIds = Set<String>(), seenEpisodes = Set<String>()
        for (i, w) in worksRaw.enumerated() {
            guard let m = w.object, m.keySet == workKeys else { throw fail("bad work entry") }
            guard try int(m["work_index"], "work_index") == Int64(i) else { throw fail("work_index out of order") }
            guard let wid = m["work_id"]?.string, Ascii.isId(wid) else { throw fail("bad work_id") }
            guard seenIds.insert(wid).inserted else { throw fail("duplicate work_id") }
            _ = try text(m["synthetic_title"], "synthetic_title")
            guard let eds = m["editions"]?.array, (1...16).contains(eds.count) else { throw fail("bad editions") }
            let edIds = try eds.map { e -> String in
                guard let s = e.string, Ascii.isEdition(s) else { throw fail("bad or duplicate edition id") }
                return s
            }
            guard Set(edIds).count == edIds.count else { throw fail("bad or duplicate edition id") }
            guard let durs = m["durations_s"]?.array, durs.count == edIds.count else { throw fail("durations/editions mismatch") }
            let dd = try durs.map { x -> Double in
                guard let v = x.number else { throw fail("bad duration") }
                guard v.isFinite, v > 0, v <= 1e6 else { throw fail("bad duration") }
                return v
            }
            let sidV = m["series_id"]!, eidV = m["episode_id"]!
            var sid: String? = nil, eid: String? = nil
            if !sidV.isNull {
                guard let s = sidV.string, Ascii.isId(s) else { throw fail("bad series_id") }
                sid = s
            }
            if !eidV.isNull {
                guard let s = sid else { throw fail("episode_id without series_id") }
                guard let e = eidV.string, Ascii.isEpisode(e) else { throw fail("bad episode_id") }
                guard seenEpisodes.insert(s + "\u{0}" + e).inserted else { throw fail("duplicate episode") }
                eid = e
            }
            guard let nm = m["names"]?.object, nm.count <= 16 else { throw fail("bad names table") }
            var nameMap: [String: String] = [:]
            for k in nm.keys {
                guard Ascii.isLocale(k) else { throw fail("bad locale tag") }
                nameMap[k] = try text(nm[k], "display name")
            }
            var al: [String] = []
            if v4 {
                guard let a = m["aliases"]?.array, a.count <= 32 else { throw fail("bad aliases") }
                al = try a.map { try text($0, "alias") }
                guard Set(al).count == al.count else { throw fail("duplicate alias") }
            }
            works.append(.init(index: i, workId: wid, seriesId: sid, episodeId: eid, editions: edIds))
            names.append(nameMap); aliases.append(al); durations.append(dd)
        }

        var scenes: [SharedScene] = []
        if v4 {
            guard let raw = meta["shared_scenes"]?.array, raw.count <= 10_000 else { throw fail("bad shared_scenes") }
            var gids = Set<String>()
            for g in raw {
                guard let gm = g.object, gm.keySet == ["group_id", "members"] else { throw fail("bad shared scene") }
                guard let gid = gm["group_id"]?.string else { throw fail("bad shared scene group_id") }
                guard Ascii.isId(gid), gids.insert(gid).inserted else { throw fail("bad or duplicate shared scene group_id") }
                guard let mem = gm["members"]?.array else { throw fail("bad shared scene") }
                guard (2...64).contains(mem.count) else { throw fail("shared scene needs 2..64 members") }
                let members = try mem.map { x -> SharedSceneMember in
                    guard let mm = x.object, mm.keySet == ["work_index", "edition_index", "start_ms", "end_ms"] else { throw fail("bad shared scene member") }
                    let wi = try int(mm["work_index"], "member work"), ei = try int(mm["edition_index"], "member edition")
                    let s = try int(mm["start_ms"], "member start"), e = try int(mm["end_ms"], "member end")
                    guard wi >= 0, wi < Int64(works.count), ei >= 0, ei < Int64(works[Int(wi)].editions.count) else { throw fail("shared scene references a missing work/edition") }
                    let durMs = ceilMs(durations[Int(wi)][Int(ei)])
                    guard s >= 0, s < e, e <= durMs else { throw fail("shared scene interval out of range") }
                    return SharedSceneMember(workIndex: Int(wi), editionIndex: Int(ei), startMs: s, endMs: e)
                }
                scenes.append(SharedScene(groupId: gid, members: members))
            }
        }

        guard d.count - o == n * 24 else { throw fail("body length mismatch") }
        var hashes: [UInt64] = [], locs: [(Int, Int, Int)] = []
        hashes.reserveCapacity(n); locs.reserveCapacity(n)
        var seen = Set<UInt64>()
        for _ in 0..<n {
            let h = u64()
            let work = Int(u32()), ed = u16(), t = Int64(u32()), segment = u16(), reserved = u32()
            guard work < works.count else { throw fail("locator references unknown work") }
            guard ed < works[work].editions.count else { throw fail("locator references unknown edition") }
            guard t <= ceilMs(durations[work][ed]) else { throw fail("locator time beyond the edition duration") }
            guard segment == 0, reserved == 0 else { throw fail("locator segment/reserved fields must be zero") }
            guard seen.insert(UInt64(work) << 40 | UInt64(ed) << 32 | UInt64(t)).inserted else { throw fail("duplicate locator") }
            hashes.append(h); locs.append((work, ed, Int(t)))
        }
        return PackIndex(formatVersion: fmt!, samplingIntervalS: interval, hashes: hashes, locs: locs, works: works,
                         names: names, aliases: aliases, sharedScenes: scenes)
    }

    public func search(_ q: UInt64, topK: Int, maxDistance: Double) -> [Recognition.Candidate] {
        let dist = hashes.map { ($0 ^ q).nonzeroBitCount }
        let order = (0..<hashes.count).sorted { dist[$0] != dist[$1] ? dist[$0] < dist[$1] : $0 < $1 }
        return order.prefix(topK).filter { Double(dist[$0]) <= maxDistance }.map {
            .init(locator: .init(work: locs[$0].0, edition: locs[$0].1, tMs: locs[$0].2), distance: Double(dist[$0]))
        }
    }
}

extension DacDhash {
    /// Must match exact.py content_frame.
    public static func contentFrame(seed: UInt32, w: Int, h: Int, bx: Int = 16, by: Int = 9) -> [UInt8] {
        var rng = XorShift32(seed)
        var cols: [[[Int]]] = []
        for _ in 0..<by { var row: [[Int]] = []; for _ in 0..<bx { row.append([Int(rng.next() & 255), Int(rng.next() & 255), Int(rng.next() & 255)]) }; cols.append(row) }
        var out = [UInt8](repeating: 0, count: w * h * 3)
        let bw = max(1, w / bx), bh = max(1, h / by)
        for y in 0..<h {
            let cy = min(by - 1, y / bh)
            for x in 0..<w {
                let cx = min(bx - 1, x / bw)
                for ch in 0..<3 {
                    let noise: Int = Int(rng.next() >> 28) - 8
                    out[(y * w + x) * 3 + ch] = clampByte(cols[cy][cx][ch] + noise)
                }
            }
        }
        return out
    }
}
