import CoreGraphics
import DetectAClipCore
import SwiftUI

/// Which synthetic clip the in-app source plays. Lets a tester reach each result path.
enum DemoClipChoice: Hashable {
    case catalogued(Int)
    case uncatalogued
    case blank
}

/// Bridges the thread-safe `ScanCoordinator` to SwiftUI. All recognition work happens off the
/// main thread; this object only mirrors the coordinator's phase for display.
@MainActor
final class ScanController: ObservableObject {
    /// Delivery rate of the synthetic source. The sampler still processes at most 2 fps.
    private static let deliveryInterval: UInt64 = 100_000_000

    @Published private(set) var phase: ScanPhase = .idle
    @Published private(set) var preview: CGImage?
    @Published var source: CaptureSource = .syntheticInApp
    @Published var clipChoice: DemoClipChoice = .catalogued(0)

    let catalogue = SyntheticCatalogue.makeDefault()
    private let coordinator = ScanCoordinator()
    private var worker: Task<Void, Never>?

    func refresh() {
        coordinator.tick()
        phase = coordinator.phase
        if !phase.isActive {
            preview = nil
        }
    }

    // MARK: User actions

    func startTapped() {
        coordinator.requestStart(source: source)
        refresh()
    }

    func consentDeclined() {
        coordinator.declineConsent()
        refresh()
    }

    func consentConfirmed() {
        guard case let .awaitingConsent(source) = coordinator.phase,
              let ticket = coordinator.confirmConsent() else { return refresh() }
        switch source {
        case .otherAppScreen:
            // P02-T02: picker/stream preparation authorizes no frames before the iOS G00 gate.
            coordinator.fail(ticket, state: .unsupportedCapture, reason: .captureDisabledInBuild)
        case .syntheticInApp:
            runSyntheticScan(ticket, clip: makeClip())
        }
        refresh()
    }

    /// In-app Stop while sampling.
    func stopCapture() {
        coordinator.cancel(reason: .userStoppedCapture)
        worker?.cancel()
        refresh()
    }

    /// Cancel of unfinished matching after sampling has closed.
    func cancelComputation() {
        coordinator.cancel(reason: .userCancelledComputation)
        worker?.cancel()
        refresh()
    }

    func discard() {
        coordinator.discard()
        refresh()
    }

    // MARK: Lifecycle

    func scenePhaseChanged(_ scenePhase: ScenePhase) {
        switch scenePhase {
        case .background:
            // The in-app source cannot keep playing in the background; never continue silently.
            if coordinator.cancel(reason: .appLeftForeground) { worker?.cancel() }
        case .active:
            break
        default:
            break
        }
        refresh()
    }

    func deviceWillLock() {
        if coordinator.cancel(reason: .deviceLocked) { worker?.cancel() }
        refresh()
    }

    // MARK: Scan

    private func makeClip() -> SyntheticClip {
        switch clipChoice {
        case let .catalogued(index):
            let work = catalogue.works[min(max(index, 0), catalogue.works.count - 1)]
            return .catalogued(work, startOffset: Double.random(in: 0...22))
        case .uncatalogued:
            return .uncatalogued(seed: UInt64.random(in: 2001...2999),
                                 startOffset: Double.random(in: 0...22))
        case .blank:
            return .blank
        }
    }

    private func runSyntheticScan(_ ticket: ScanTicket, clip: SyntheticClip) {
        let coordinator = self.coordinator
        let matcher = Matcher(catalogue: catalogue)
        let deliveryInterval = Self.deliveryInterval
        worker?.cancel()
        worker = Task.detached(priority: .userInitiated) { [weak self] in
            var rng = SplitMix64(seed: UInt64.random(in: UInt64.min...UInt64.max))
            let started = ProcessInfo.processInfo.systemUptime

            // Bounded acquisition with incremental local work: each admitted frame is hashed
            // immediately and the frame is dropped.
            while !Task.isCancelled {
                coordinator.tick()
                guard case let .acquiring(current, _, _) = coordinator.phase, current == ticket else { break }
                let frame = clip.frame(at: ProcessInfo.processInfo.systemUptime - started, rng: &rng)
                if let time = coordinator.admitFrame(ticket) {
                    _ = coordinator.record(ticket, sample: QuerySample(time: time, frame: frame,
                                                                       policy: matcher.policy))
                }
                let image = FrameImage.make(frame)
                await MainActor.run {
                    self?.preview = image
                    self?.refresh()
                }
                try? await Task.sleep(nanoseconds: deliveryInterval)
            }

            // Post-capture: local decision, then atomic commit (rejected if cancelled first).
            if !Task.isCancelled, let samples = coordinator.samplesForDecision(ticket) {
                let decision = matcher.decide(samples)
                coordinator.commit(ticket, decision: decision)
            }
            await MainActor.run { self?.refresh() }
        }
    }
}

enum FrameImage {
    static func make(_ frame: GrayFrame) -> CGImage? {
        guard let provider = CGDataProvider(data: Data(frame.pixels) as CFData) else { return nil }
        return CGImage(width: frame.width, height: frame.height,
                       bitsPerComponent: 8, bitsPerPixel: 8, bytesPerRow: frame.width,
                       space: CGColorSpaceCreateDeviceGray(),
                       bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.none.rawValue),
                       provider: provider, decode: nil, shouldInterpolate: false,
                       intent: .defaultIntent)
    }
}
