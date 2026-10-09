// NOT RUN (no Mac). Same golden file as android ExactPathGoldenTest.kt.
import XCTest
@testable import DetectAClipCore

final class ExactPathGoldenTests: XCTestCase {
    func testExactPathMatchesPython() throws {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("../../../android/app/src/test/resources/golden_exact.txt").standardized
        let lines = try String(contentsOf: url, encoding: .utf8).split(separator: "\n").map(String.init).filter { !$0.hasPrefix("#") }
        let size = lines[0].split(separator: " ").map { Int($0) ?? 0 }
        let w = size[1], h = size[2]
        for line in lines.dropFirst() {
            let p = line.split(separator: " ").map(String.init)
            let seed = UInt32(p[2])!
            let a = p[3...9].map { Int($0)! } // iw ih ox oy bg bx by
            var prev: [Int64]? = nil
            var rects: [String] = [], flags: [String] = [], hashes: [String] = []
            for s in [seed, seed, seed + 1000] {
                var f = [UInt8](repeating: UInt8(a[4]), count: w * h * 3)
                if a[0] > 0 && a[1] > 0 {
                    let c = DacDhash.contentFrame(seed: s, w: a[0], h: a[1], bx: a[5], by: a[6])
                    for yy in 0..<a[1] { for xx in 0..<a[0] { for ch in 0..<3 {
                        f[((a[3] + yy) * w + a[2] + xx) * 3 + ch] = c[(yy * a[0] + xx) * 3 + ch]
                    } } }
                }
                let y = DacDhash.luma(f, width: w, height: h)
                let r = DacDhash.cropRect(y, w: w, h: h)
                let (flag, means) = DacDhash.quality(y, w: w, rect: r, prev: prev)
                if flag == "OK" { prev = means }
                rects.append(r.map(String.init).joined(separator: ","))
                flags.append(flag)
                hashes.append(String(format: "%016llx:%016llx", DacDhash.dhashRegion(y, w: w, rect: r), DacDhash.dhashRegion(y, w: w, rect: r, mirrored: true)))
            }
            XCTAssertEqual(rects.joined(separator: "/"), p[10], p[1])
            XCTAssertEqual(flags.joined(separator: "/"), p[11], p[1])
            XCTAssertEqual(hashes.joined(separator: "/"), p[12], p[1])
        }
    }
}
