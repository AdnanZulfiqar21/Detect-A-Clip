// ScreenCaptureKit adapter skeleton for the iOS research path (P02-T02/T03).
//
// Status: UNVERIFIED and NOT COMPILED. Symbol names follow Apple's documentation metadata
// (S05–S09, V09–V10), which lists iOS 27; the exact iOS signatures must be pinned from
// installed headers (CAP-I03) before this file is trusted. It is excluded from builds unless
// ScreenCaptureKit is importable on iOS, so the platform-independent core still compiles.
//
// It deliberately does NOT: enumerate shareable content (S10/S11 list no iOS support),
// write frames to disk, use audio, or keep the stream alive to extend background time.

#if canImport(ScreenCaptureKit) && os(iOS)
import ScreenCaptureKit
import CoreMedia

@available(iOS 27.0, *)
final class ScreenCaptureAdapter: NSObject, SCStreamOutput, SCStreamDelegate, ProjectionHandle {
    private let lifecycle: CaptureLifecycle
    private let queue: DispatchQueue
    private var stream: SCStream?

    init(lifecycle: CaptureLifecycle, queue: DispatchQueue) {
        self.lifecycle = lifecycle
        self.queue = queue
    }

    /// Called with the filter the system picker returned (SCContentSharingPickerObserver).
    func start(filter: SCContentFilter) throws {
        let config = SCStreamConfiguration()
        config.width = 640
        config.height = 360
        config.queueDepth = 3                 // ≤3 OS buffers; app-owned frames bounded separately
        let s = SCStream(filter: filter, configuration: config, delegate: self)
        try s.addStreamOutput(self, type: .screen, sampleHandlerQueue: queue)
        stream = s
        guard lifecycle.attach(self) else { return }
        s.startCapture { [weak self] error in
            if error != nil { self?.queue.async { self?.lifecycle.onCaptureStopped() } }
        }
    }

    // SCStreamOutput
    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .screen else { return }
        guard lifecycle.onFrame() else { return }   // refused: the buffer is simply not retained
        defer { lifecycle.frameDone() }
        // Bounded in-memory work only; nothing persisted.
        _ = CMSampleBufferGetImageBuffer(sampleBuffer)
    }

    // SCStreamDelegate
    func stream(_ stream: SCStream, didStopWithError error: Error) {
        queue.async { [weak self] in self?.lifecycle.onCaptureStopped() }
    }

    // ProjectionHandle
    func stop() { stream?.stopCapture { _ in } }
    func release() { stream = nil }
}
#endif
