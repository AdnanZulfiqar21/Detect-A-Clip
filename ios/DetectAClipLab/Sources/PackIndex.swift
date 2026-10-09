// Swift port of android PackIndex.kt (bounded idx-flat-3 parser + Hamming flat retrieval) and
// DacDhash.contentFrame. Status: IMPLEMENTED_NOT_VERIFIED (EndToEndGoldenTests on a Mac, B-02).
import Foundation

public enum PackError: Error { case invalid(String) }

public struct PackIndex {
    public let samplingIntervalS: Double
    public let hashes: [UInt64]
    let locs: [(Int, Int, Int)]
    public let works: [Recognition.WorkEntry]

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
        guard dBytes == 8 else { throw fail("only 8-byte hashes") }
        guard n <= 20_000_000, nWorks <= 1_000_000, interval >= 0.1, interval <= 60 else { throw fail("count out of bounds") }
        let metaLen = Int(u32())
        guard metaLen <= 64 * 1024 * 1024, o + metaLen <= d.count else { throw fail("bad metadata length") }
        let metaData = Data(d[o..<(o + metaLen)]); o += metaLen
        guard let meta = try JSONSerialization.jsonObject(with: metaData) as? [String: Any],
              meta["index_format_version"] as? String == "idx-flat-3", meta["family"] as? String == "HASH64",
              let wr = meta["works"] as? [[String: Any]], wr.count == nWorks else { throw fail("bad metadata") }
        var works: [Recognition.WorkEntry] = []
        for w in wr {
            guard Set(w.keys) == ["work_index", "work_id", "synthetic_title", "editions", "durations_s", "series_id", "episode_id", "names"],
                  let idx = w["work_index"] as? Int, let id = w["work_id"] as? String, let eds = w["editions"] as? [String] else { throw fail("bad work") }
            works.append(.init(index: idx, workId: id, seriesId: w["series_id"] as? String, episodeId: w["episode_id"] as? String, editions: eds))
        }
        guard d.count - o == n * 24 else { throw fail("body length mismatch") }
        var hashes: [UInt64] = [], locs: [(Int, Int, Int)] = []
        hashes.reserveCapacity(n); locs.reserveCapacity(n)
        for _ in 0..<n {
            let h = u64()
            let work = Int(u32()), ed = u16(), t = Int(u32())
            o += 6 // segment u16 + reserved u32
            guard work < nWorks, ed < works[work].editions.count else { throw fail("bad locator") }
            hashes.append(h); locs.append((work, ed, t))
        }
        return PackIndex(samplingIntervalS: interval, hashes: hashes, locs: locs, works: works)
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
                for ch in 0..<3 { out[(y * w + x) * 3 + ch] = UInt8(min(255, max(0, cols[cy][cx][ch] + Int(rng.next() >> 28) - 8))) }
            }
        }
        return out
    }
}
