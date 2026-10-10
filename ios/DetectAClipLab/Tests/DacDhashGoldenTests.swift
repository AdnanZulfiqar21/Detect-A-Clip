// Runs in the swift-core CI job. Same golden file as android DacDhashGoldenTest.kt.
import XCTest
@testable import DetectAClipCore

final class DacDhashGoldenTests: XCTestCase {
    func testSwiftHashIsBitIdenticalToPython() throws {
        let golden = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("../../../android/app/src/test/resources/golden_dac_dhash_v1.txt").standardized
        var n = 0
        for line in try String(contentsOf: golden, encoding: .utf8).split(separator: "\n") where !line.hasPrefix("#") {
            let p = line.split(separator: " ").map(String.init)
            let seed = UInt32(p[1])!, w = Int(p[2])!, h = Int(p[3])!
            XCTAssertEqual(DacDhash.hash(DacDhash.testFrame(seed: seed, w: w, h: h), width: w, height: h), UInt64(p[4], radix: 16)!, line.description)
            n += 1
        }
        XCTAssertGreaterThanOrEqual(n, 40)
    }
}
