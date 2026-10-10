// PixelBufferFrame: BGRA CVPixelBuffer (with row padding) gives exactly the reference luma, the
// copy outlives the buffer, and unsupported formats are refused without reading.
import XCTest
@testable import DetectAClipCore
#if canImport(CoreVideo)
import CoreVideo

final class PixelBufferFrameTests: XCTestCase {
    private func bgraBuffer(_ rgb: [UInt8], _ w: Int, _ h: Int) throws -> CVPixelBuffer {
        var pb: CVPixelBuffer?
        // Force row padding: CoreVideo aligns bytesPerRow; extended pixels add more.
        let attrs: [CFString: Any] = [kCVPixelBufferExtendedPixelsRightKey: 13]
        XCTAssertEqual(CVPixelBufferCreate(nil, w, h, kCVPixelFormatType_32BGRA, attrs as CFDictionary, &pb), kCVReturnSuccess)
        let b = try XCTUnwrap(pb)
        CVPixelBufferLockBaseAddress(b, [])
        let base = CVPixelBufferGetBaseAddress(b)!.assumingMemoryBound(to: UInt8.self)
        let rowBytes = CVPixelBufferGetBytesPerRow(b)
        XCTAssertGreaterThan(rowBytes, w * 4)                 // the test really exercises padding
        for y in 0..<h {
            for x in 0..<w {
                let p = y * rowBytes + x * 4, q = (y * w + x) * 3
                base[p] = rgb[q + 2]; base[p + 1] = rgb[q + 1]; base[p + 2] = rgb[q]; base[p + 3] = 255
            }
            for k in (w * 4)..<rowBytes { base[y * rowBytes + k] = 0x5A }   // garbage in the padding
        }
        CVPixelBufferUnlockBaseAddress(b, [])
        return b
    }

    func testBGRAWithPaddingMatchesReferenceLuma() throws {
        let w = 64, h = 36
        let rgb = DacDhash.contentFrame(seed: 11, w: w, h: h)
        let pb = try bgraBuffer(rgb, w, h)
        let out = try PixelBufferFrame.luma(pb)
        XCTAssertEqual(out.width, w); XCTAssertEqual(out.height, h)
        XCTAssertEqual(out.luma, DacDhash.luma(rgb, width: w, height: h))
    }

    func testCopyOutlivesTheBuffer() throws {
        let w = 64, h = 36
        let pb = try bgraBuffer(DacDhash.contentFrame(seed: 5, w: w, h: h), w, h)
        let first = try PixelBufferFrame.luma(pb).luma
        CVPixelBufferLockBaseAddress(pb, [])
        memset(CVPixelBufferGetBaseAddress(pb)!, 0, CVPixelBufferGetDataSize(pb))   // OS reuses the buffer
        CVPixelBufferUnlockBaseAddress(pb, [])
        XCTAssertNotEqual(first, try PixelBufferFrame.luma(pb).luma)
        XCTAssertEqual(first.count, w * h)
    }

    func testUnsupportedFormatAndTinyFramesAreRefused() throws {
        var yuv: CVPixelBuffer?
        CVPixelBufferCreate(nil, 64, 36, kCVPixelFormatType_420YpCbCr8BiPlanarFullRange, nil, &yuv)
        XCTAssertThrowsError(try PixelBufferFrame.luma(try XCTUnwrap(yuv)))
        var tiny: CVPixelBuffer?
        CVPixelBufferCreate(nil, 16, 9, kCVPixelFormatType_32BGRA, nil, &tiny)
        XCTAssertThrowsError(try PixelBufferFrame.luma(try XCTUnwrap(tiny)))
    }
}
#endif
