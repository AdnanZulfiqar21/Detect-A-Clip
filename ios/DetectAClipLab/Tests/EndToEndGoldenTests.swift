// Runs in the swift-core CI job. Same golden file as android EndToEndGoldenTest.kt.
import XCTest
@testable import DetectAClipCore

final class EndToEndGoldenTests: XCTestCase {
    func testSwiftEngineReproducesPythonDecisions() throws {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("../../../android/app/src/test/resources/golden_e2e.txt").standardized
        let lines = try String(contentsOf: url, encoding: .utf8).split(separator: "\n").map(String.init).filter { !$0.hasPrefix("#") }
        let hex = Array(lines[0].dropFirst(8))
        var bytes: [UInt8] = []
        var k = 0
        while k < hex.count { bytes.append(UInt8(String(hex[k..<k + 2]), radix: 16)!); k += 2 }
        let pack = try PackIndex.parse(bytes)
        let t = lines[1].split(separator: " ").map(String.init)
        var th = Recognition.Thresholds()
        th.minQualifiedFrames = Int(t[1])!; th.verifiedMinSupport = Int(t[2])!; th.verifiedMinSupportFraction = Double(t[3])!
        th.verifiedMinSpanMs = Int(t[4])!; th.verifiedMaxMeanDistFrac = Double(t[5])!; th.verifiedMinMargin = Int(t[6])!
        th.possibleMinSupport = Int(t[7])!; th.possibleMinSpanMs = Int(t[8])!; th.possibleMaxMeanDistFrac = Double(t[9])!
        th.possibleOnCompetition = t[10] == "1"; th.episodeMargin = Int(t[11])!; th.radius = Double(t[12])!
        let topK = Int(t[13])!
        var i = 2, queries = 0
        while i < lines.count {
            let q = lines[i].split(separator: " ").map(String.init); i += 1
            let n = Int(q[2])!
            var pf: [(Int, [Recognition.Candidate])] = []
            for _ in 0..<n {
                let f = lines[i].split(separator: " ").map(String.init); i += 1
                var frame = DacDhash.contentFrame(seed: UInt32(f[2])!, w: 64, h: 36)
                let b = Int(f[3])!
                if b != 0 { frame = frame.map { DacDhash.clampByte(Int($0) + b) } }
                pf.append((Int(f[1])!, pack.search(DacDhash.hash(frame, width: 64, height: 36), topK: topK, maxDistance: th.radius)))
            }
            let expected = lines[i]; i += 1
            let hyps = Recognition.verify(pf, samplingIntervalMs: Int(pack.samplingIntervalS * 1000))
            let r = Recognition.decide(hyps, frames: .init(selected: n, qualified: n, unusable: 0), works: pack.works, th: th)
            XCTAssertEqual(DecisionLine.format(r), expected, q[1])
            queries += 1
        }
        XCTAssertEqual(queries, 6)
    }
}
