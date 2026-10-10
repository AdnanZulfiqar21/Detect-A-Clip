// Full exact pipeline parity with Python (golden_pipeline.txt), as android PipelineGoldenTest.kt:
// FrameSelector + FrameView (padded RGBA strides) + RecognitionSession must reproduce every
// frame summary and decision.
import XCTest
@testable import DetectAClipCore

final class PipelineGoldenTests: XCTestCase {
    func testSessionReproducesPythonPipeline() throws {
        let lines = try Golden.lines("golden_pipeline.txt").filter { !$0.hasPrefix("#") }
        let size = lines[0].split(separator: " "); let w = Int(size[1])!, h = Int(size[2])!
        let pack = try PackIndex.parse(Golden.hex(lines[1].dropFirst(8)))
        let t = lines[2].split(separator: " ").map(String.init)
        let th = Golden.thresholds(t)
        let topK = Int(t[13])!
        var i = 3, queries = 0
        var mismatches: [String] = []
        while i < lines.count {
            let q = lines[i].split(separator: " ").map(String.init); i += 1
            let n = Int(q[2])!
            let selector = FrameSelector()
            let session = RecognitionSession(pack: pack, thresholds: th, topK: topK, mirrorInvariant: true)
            var offered = 0
            for _ in 0..<n {
                let f = lines[i].split(separator: " ").map(String.init); i += 1
                let ts = Int64(f[1])!
                offered += 1
                if selector.offer(ts) {
                    defer { selector.release() }
                    let rgb = Compose.frame(seed: UInt32(f[2])!, variant: f[3], bright: Int(f[4])!, w: w, h: h)
                    let luma = try Compose.luma(Compose.paddedRGBA(rgb, w, h, pad: 12), w, h)
                    _ = session.process(tMs: Int(ts), luma: luma, width: w, height: h)
                }
            }
            selector.close()
            let s = lines[i]; i += 1
            let expectedR = lines[i]; i += 1
            let d = session.finish { false }!
            let segs = d.segments.isEmpty ? "-" : d.segments.map {
                "\($0.workId)@\($0.editionId ?? "-")@\($0.queryStartMs)@\($0.queryEndMs)@\($0.referenceOffsetMs.map(String.init) ?? "-")@\($0.supportingFrames)"
            }.joined(separator: "|")
            let gotR = "R \(d.state.rawValue) \(d.workId ?? "-") \(d.editionId ?? "-") \(d.episodeId ?? "-") \(d.flags.isEmpty ? "-" : d.flags.joined(separator: ",")) \(segs)"
            let gotS = "S \(offered) \(session.selected) \(session.qualified) \(session.unusable)"
            if gotS != s { mismatches.append("\(q[1]) summary: \(gotS) vs \(s)") }
            if gotR != expectedR { mismatches.append("\(q[1]): \(gotR) vs \(expectedR)") }
            queries += 1
        }
        XCTAssertEqual(queries, 12)
        XCTAssertEqual(mismatches, [])
    }

    func testStrideVariantsGiveIdenticalLuma() throws {
        let w = 64, h = 36
        let rgb = DacDhash.contentFrame(seed: 7, w: w, h: h)
        let compact = DacDhash.luma(rgb, width: w, height: h)
        for pad in [0, 4, 13, 64] {
            XCTAssertEqual(try Compose.luma(Compose.paddedRGBA(rgb, w, h, pad: pad), w, h), compact)
        }
        let viaRGB = try rgb.withUnsafeBytes { try FrameView(base: $0, width: w, height: h, rowStride: w * 3, pixelStride: 3).toLuma() }
        XCTAssertEqual(viaRGB, compact)
        // BGRA (CVPixelBuffer kCVPixelFormatType_32BGRA) gives the same luma with order: .bgr
        var bgra = [UInt8](repeating: 0, count: w * h * 4)
        for k in 0..<(w * h) { bgra[4 * k] = rgb[3 * k + 2]; bgra[4 * k + 1] = rgb[3 * k + 1]; bgra[4 * k + 2] = rgb[3 * k]; bgra[4 * k + 3] = 255 }
        let viaBGRA = try bgra.withUnsafeBytes { try FrameView(base: $0, width: w, height: h, rowStride: w * 4, pixelStride: 4, order: .bgr).toLuma() }
        XCTAssertEqual(viaBGRA, compact)
    }

    func testLumaIsAnOwnedCopy() throws {
        let w = 64, h = 36
        var plane = Compose.paddedRGBA(DacDhash.contentFrame(seed: 3, w: w, h: h), w, h, pad: 8)
        let luma = try Compose.luma(plane, w, h)
        let copy = luma
        for k in 0..<plane.bytes.count { plane.bytes[k] = 0 }      // OS reuses the buffer after release
        XCTAssertEqual(luma, copy)
    }

    func testInconsistentStridesAreRefused() {
        let buf = [UInt8](repeating: 0, count: 64 * 4 * 36)
        buf.withUnsafeBytes { b in
            XCTAssertThrowsError(try FrameView(base: b, width: 64, height: 36, rowStride: 64 * 4 - 1, pixelStride: 4))
            XCTAssertThrowsError(try FrameView(base: b, width: 64, height: 36, rowStride: 64 * 4 + 8, pixelStride: 4))
            XCTAssertThrowsError(try FrameView(base: b, width: 64, height: 36, rowStride: 64 * 2, pixelStride: 2))
            XCTAssertThrowsError(try FrameView(base: b, width: 8, height: 8, rowStride: 32, pixelStride: 4))
        }
    }

    func testLateFrameAfterFinishIsRefusedAndCancellationReturnsNil() throws {
        let pack = try Golden.pipelinePack()
        var th = Recognition.Thresholds(); th.radius = 9
        let s = RecognitionSession(pack: pack, thresholds: th)
        let luma = DacDhash.luma(DacDhash.contentFrame(seed: 1, w: 64, h: 36), width: 64, height: 36)
        XCTAssertEqual(s.process(tMs: 0, luma: luma, width: 64, height: 36), "OK")
        _ = s.finish { false }
        XCTAssertEqual(s.process(tMs: 500, luma: luma, width: 64, height: 36), "CLOSED")
        XCTAssertEqual(s.selected, 1)
        let s2 = RecognitionSession(pack: pack, thresholds: th)
        var calls = 0
        XCTAssertNil(s2.finish { calls += 1; return calls > 1 })
    }
}
