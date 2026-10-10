// Swift port of android RecognitionSession.kt (FrameView + RecognitionSession), checked against
// golden_pipeline.txt by PipelineGoldenTests. Memory only: luma copies and per-frame
// candidates live in the session and are dropped with it.
// Status: compiled and tested only where CI runs `swift test` (see docs/TEST_EVIDENCE.md).
import Foundation

/// A view of one captured plane (CVPixelBuffer BGRA/RGBA rows, or any interleaved layout).
/// `toLuma()` copies what the engine needs into an app-owned array before returning, so the
/// caller can unlock/release the OS buffer immediately; nothing keeps the pointer.
public struct FrameView {
    public enum Order { case rgb, bgr }
    public let width: Int, height: Int, rowStride: Int, pixelStride: Int
    public let order: Order
    private let base: UnsafeRawBufferPointer

    /// `base` must stay valid only for the duration of `toLuma()`.
    public init(base: UnsafeRawBufferPointer, width: Int, height: Int, rowStride: Int, pixelStride: Int, order: Order = .rgb) throws {
        guard width >= 16, height >= 9 else { throw PackError.invalid("frame too small") }
        guard pixelStride >= 3 else { throw PackError.invalid("pixelStride must cover R, G and B") }
        guard rowStride >= width * pixelStride else { throw PackError.invalid("rowStride smaller than a row") }
        guard (height - 1) * rowStride + width * pixelStride <= base.count else { throw PackError.invalid("buffer too small for the declared strides") }
        self.base = base; self.width = width; self.height = height; self.rowStride = rowStride; self.pixelStride = pixelStride; self.order = order
    }

    public func toLuma() -> [Int] {
        var y = [Int](repeating: 0, count: width * height)
        let (ri, bi) = order == .rgb ? (0, 2) : (2, 0)
        for r in 0..<height {
            var p = r * rowStride
            let o = r * width
            for c in 0..<width {
                let rr = Int(base[p + ri]), gg = Int(base[p + 1]), bb = Int(base[p + bi])
                y[o + c] = (77 * rr + 150 * gg + 29 * bb + 128) >> 8
                p += pixelStride
            }
        }
        return y
    }
}

/// One scan's local recognition work: DAC-CROP-v1 -> DAC-QUAL-v1 -> DAC-DHASH-v1 (+ mirrored)
/// -> flat retrieval -> merge -> temporal verification -> decision.
public final class RecognitionSession {
    private let pack: PackIndex
    private let th: Recognition.Thresholds
    private let topK: Int
    private let mirrorInvariant: Bool
    private let lock = NSLock()
    public private(set) var selected = 0
    public private(set) var qualified = 0
    public private(set) var unusable = 0
    private var prevMeans: [Int64]?
    private var perFrame: [(Int, [Recognition.Candidate])] = []
    private var closed = false

    public init(pack: PackIndex, thresholds: Recognition.Thresholds, topK: Int = 12, mirrorInvariant: Bool = true) {
        self.pack = pack; self.th = thresholds; self.topK = topK; self.mirrorInvariant = mirrorInvariant
    }

    /// Returns the quality flag (OK, BLANK, FLAT, STATIC) or CLOSED for a late frame.
    public func process(tMs: Int, luma: [Int], width: Int, height: Int) -> String {
        lock.lock(); defer { lock.unlock() }
        if closed { return "CLOSED" }
        precondition(luma.count == width * height, "luma size mismatch")
        let rect = DacDhash.cropRect(luma, w: width, h: height)
        let (flag, means) = DacDhash.quality(luma, w: width, rect: rect, prev: prevMeans)
        selected += 1
        if flag == "BLANK" { unusable += 1; return flag }
        if flag != "OK" { return flag }
        qualified += 1
        prevMeans = means
        var cands = pack.search(DacDhash.dhashRegion(luma, w: width, rect: rect), topK: topK, maxDistance: th.radius)
        if mirrorInvariant {
            let flipped = pack.search(DacDhash.dhashRegion(luma, w: width, rect: rect, mirrored: true), topK: topK, maxDistance: th.radius)
            var order: [Recognition.Locator] = []
            var best: [Recognition.Locator: Recognition.Candidate] = [:]
            for c in cands + flipped {
                if let prev = best[c.locator] { if c.distance < prev.distance { best[c.locator] = c } }
                else { best[c.locator] = c; order.append(c.locator) }
            }
            cands = Array(Recognition.stableSorted(order.map { best[$0]! }) { $0.distance < $1.distance }.prefix(topK))
        }
        perFrame.append((tMs, cands))
        return flag
    }

    /// Verification + decision. Returns nil if cancelled (checked between steps).
    public func finish(isCancelled: () -> Bool) -> Recognition.Decision? {
        lock.lock()
        closed = true
        let snapshot = perFrame
        let summary = Recognition.FrameSummary(selected: selected, qualified: qualified, unusable: unusable)
        lock.unlock()
        if isCancelled() { return nil }
        let hyps = Recognition.verify(snapshot, samplingIntervalMs: Int(pack.samplingIntervalS * 1000))
        if isCancelled() { return nil }
        return Recognition.decide(hyps, frames: summary, works: pack.works, th: th)
    }

    /// Display name for a decision: the episode's or work's localized name, else its ID.
    public func displayName(_ d: Recognition.Decision, preferences: [String]) -> String? {
        pack.resultDisplayName(workId: d.workId, episodeId: d.episodeId, preferences: preferences)
    }
}
