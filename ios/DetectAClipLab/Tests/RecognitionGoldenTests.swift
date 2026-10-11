// Runs in the swift-core CI job. Reads the same golden file as android RecognitionGoldenTest.kt and must
// reproduce the Python reference exactly. Path is resolved relative to this source file.
import XCTest
@testable import DetectAClipCore

final class RecognitionGoldenTests: XCTestCase {
    func testPortMatchesPythonReference() throws {
        let here = URL(fileURLWithPath: #filePath)
        let golden = here.deletingLastPathComponent().appendingPathComponent("../../../android/app/src/test/resources/golden_recognition.txt").standardized
        let text = try String(contentsOf: golden, encoding: .utf8)
        var lines = text.split(separator: "\n").map(String.init).filter { !$0.isEmpty && !$0.hasPrefix("#") }
        lines.reverse()
        func next() -> String { lines.removeLast() }
        func peek() -> String { lines.last ?? "" }
        let nWorks = Int(next().dropFirst(6))!
        var works: [Recognition.WorkEntry] = []
        for _ in 0..<nWorks {
            let p = next().split(separator: " ").map(String.init)
            works.append(.init(index: Int(p[1])!, workId: p[2], seriesId: p[3] == "-" ? nil : p[3], episodeId: p[4] == "-" ? nil : p[4], editions: p[5].split(separator: ",").map(String.init)))
        }
        var cases = 0
        while !lines.isEmpty {
            let header = next()
            let f = next().split(separator: " ").map(String.init)
            let frames = Recognition.FrameSummary(selected: Int(f[1])!, qualified: Int(f[2])!, unusable: Int(f[3])!)
            let t = next().split(separator: " ").map(String.init)
            var th = Recognition.Thresholds()
            th.minQualifiedFrames = Int(t[1])!; th.verifiedMinSupport = Int(t[2])!; th.verifiedMinSupportFraction = Double(t[3])!
            th.verifiedMinSpanMs = Int(t[4])!; th.verifiedMaxMeanDistFrac = Double(t[5])!; th.verifiedMinMargin = Int(t[6])!
            th.possibleMinSupport = Int(t[7])!; th.possibleMinSpanMs = Int(t[8])!; th.possibleMaxMeanDistFrac = Double(t[9])!
            th.possibleOnCompetition = t[10] == "1"; th.episodeMargin = Int(t[11])!; th.radius = Double(t[12])!
            var pf: [(Int, [Recognition.Candidate])] = []
            while peek().hasPrefix("PF ") {
                let p = next().split(separator: " ").map(String.init)
                var cs: [Recognition.Candidate] = []
                if p[2] != "-" {
                    for c in p[2].split(separator: ";") {
                        let q = c.split(separator: ":").map(String.init)
                        let loc = Recognition.Locator(work: Int(q[0])!, edition: Int(q[1])!, tMs: Int(q[2])!)
                        cs.append(Recognition.Candidate(locator: loc, distance: Double(q[3])!))
                    }
                }
                pf.append((Int(p[1])!, cs))
            }
            var expH: [[String]] = []
            while peek().hasPrefix("H ") { expH.append(next().split(separator: " ").map(String.init)) }
            let expR = next()
            XCTAssertEqual(next(), "END")
            let hyps = Recognition.verify(pf, samplingIntervalMs: 2000)
            XCTAssertEqual(hyps.count, expH.count, header)
            for (h, e) in zip(hyps, expH) {
                XCTAssertEqual([String(h.work), String(h.edition ?? -1), String(h.offsetMs), String(h.support)], Array(e[1...4]), header)
                XCTAssertEqual(h.meanDistance, Double(e[5])!, header)
                let amb: String = h.ambiguousEditions.isEmpty ? "-" : h.ambiguousEditions.map { String($0) }.joined(separator: ",")
                XCTAssertEqual([String(h.queryStartMs), String(h.queryEndMs), amb], Array(e[6...8]), header)
            }
            let r = Recognition.decide(hyps, frames: frames, works: works, th: th)
            let got = DecisionLine.format(r)
            XCTAssertEqual(got, expR, header)
            cases += 1
        }
        XCTAssertGreaterThanOrEqual(cases, 400)
    }
}
