// CVPixelBuffer → app-owned luma for the iOS capture path (ScreenCaptureKit delivers 32BGRA
// CVPixelBuffers). The buffer is locked read-only only for the duration of the copy, the
// bounds-checked FrameView is built from the real bytesPerRow (row padding included), and the
// lock is released before returning, so the OS buffer can be recycled immediately.
// Status: compiled and tested by the swift-core CI job (macOS CoreVideo); device frames B-02.
#if canImport(CoreVideo)
import CoreVideo

public enum PixelBufferFrame {
    public enum Failure: Error, Equatable { case unsupportedFormat(OSType), lockFailed(Int32), noBaseAddress }

    /// Locks a 32BGRA (or 32RGBA) pixel buffer read-only, builds the bounds-checked FrameView over
    /// the locked bytes (no pixel is read by the constructor), runs `body`, and unlocks before
    /// returning. Throws for any other format, a lock failure, or geometry FrameView refuses.
    public static func withView<T>(_ pb: CVPixelBuffer, _ body: (FrameView) throws -> T) throws -> T {
        let format = CVPixelBufferGetPixelFormatType(pb)
        let order: FrameView.Order
        switch format {
        case kCVPixelFormatType_32BGRA: order = .bgr
        case kCVPixelFormatType_32RGBA: order = .rgb
        default: throw Failure.unsupportedFormat(format)
        }
        let status = CVPixelBufferLockBaseAddress(pb, .readOnly)
        guard status == kCVReturnSuccess else { throw Failure.lockFailed(status) }
        defer { CVPixelBufferUnlockBaseAddress(pb, .readOnly) }
        guard let base = CVPixelBufferGetBaseAddress(pb) else { throw Failure.noBaseAddress }
        let w = CVPixelBufferGetWidth(pb), h = CVPixelBufferGetHeight(pb), rowBytes = CVPixelBufferGetBytesPerRow(pb)
        let size = CVPixelBufferGetDataSize(pb)
        let view = try FrameView(base: UnsafeRawBufferPointer(start: base, count: size), width: w, height: h,
                                 rowStride: rowBytes, pixelStride: 4, order: order)
        return try body(view)
    }

    /// Copies luma out of the pixel buffer (app-owned result; the buffer is unlocked on return).
    public static func luma(_ pb: CVPixelBuffer) throws -> (luma: [Int], width: Int, height: Int) {
        try withView(pb) { view in (view.toLuma(), view.width, view.height) }
    }
}
#endif
