package ai.detectaclip.lab

import java.nio.ByteBuffer

/**
 * A view of one captured plane (ImageReader RGBA_8888 or any interleaved RGB/RGBA layout).
 * [toLuma] copies what the engine needs into an app-owned IntArray *before* returning, so the
 * caller can close the OS image immediately afterwards; nothing keeps a reference to [buffer].
 * Absolute reads only: the buffer's position/limit are not changed.
 */
class FrameView(
    private val buffer: ByteBuffer,
    val width: Int,
    val height: Int,
    val rowStride: Int,
    val pixelStride: Int,
) {
    init {
        // Bounds first, then 64-bit arithmetic: no overflow, no negative stride, no read past limit().
        require(width in MIN_WIDTH..MAX_DIM && height in MIN_HEIGHT..MAX_DIM) { "frame size out of range" }
        require(pixelStride in 3..MAX_PIXEL_STRIDE) { "pixelStride must cover R, G and B" }
        require(rowStride in 1..MAX_ROW_STRIDE) { "rowStride out of range" }
        require(rowStride.toLong() >= width.toLong() * pixelStride) { "rowStride smaller than a row" }
        val needed = (height - 1).toLong() * rowStride + width.toLong() * pixelStride
        require(needed <= buffer.limit()) { "buffer too small for the declared strides" }
    }

    companion object {
        /** Smallest frame whose >= 40 % crop still covers the 16x9 quality grid (and the golden size). */
        const val MIN_WIDTH = 64
        const val MIN_HEIGHT = 36
        const val MAX_DIM = 4096
        const val MAX_PIXEL_STRIDE = 16
        const val MAX_ROW_STRIDE = 1 shl 20
    }

    fun toLuma(): IntArray {
        val y = IntArray(width * height)
        for (r in 0 until height) {
            var p = r * rowStride
            val o = r * width
            for (c in 0 until width) {
                val rr = buffer.get(p).toInt() and 0xFF
                val gg = buffer.get(p + 1).toInt() and 0xFF
                val bb = buffer.get(p + 2).toInt() and 0xFF
                y[o + c] = (77 * rr + 150 * gg + 29 * bb + 128) shr 8
                p += pixelStride
            }
        }
        return y
    }
}

/**
 * One scan's local recognition work: DAC-CROP-v1 -> DAC-QUAL-v1 -> DAC-DHASH-v1 (+ mirrored)
 * -> flat retrieval -> merge -> temporal verification -> decision. Mirrors the Python exact
 * path in l0/dac_l0/pipeline.py and is checked against golden_pipeline.txt.
 *
 * Frame *selection* (>= 500 ms, <= 3 owned) is the caller's FrameSelector. [process] runs for
 * selected frames only; [finish] runs once after capture closed. Memory only: per-frame
 * candidates live in this object and are dropped with it; no frame or descriptor is persisted.
 */
class RecognitionSession(
    private val pack: PackIndex,
    private val th: Recognition.Thresholds,
    private val topK: Int = 12,
    private val mirrorInvariant: Boolean = true,
) {
    var selected = 0; private set
    var qualified = 0; private set
    var unusable = 0; private set
    private var prevMeans: LongArray? = null
    private val perFrame = ArrayList<Pair<Int, List<Recognition.Candidate>>>()
    private var closed = false

    /** Returns the quality flag (OK, BLANK, FLAT, STATIC), CLOSED for a late frame, or INVALID
     *  for a frame outside FrameView's bounds (refused without being counted). */
    @Synchronized
    fun process(tMs: Long, luma: IntArray, width: Int, height: Int): String {
        if (closed) return "CLOSED"
        if (width !in FrameView.MIN_WIDTH..FrameView.MAX_DIM || height !in FrameView.MIN_HEIGHT..FrameView.MAX_DIM ||
            luma.size != width * height) return "INVALID"
        val rect = DacDhash.cropRect(luma, width, height)
        val (flag, means) = DacDhash.quality(luma, width, rect, prevMeans)
        selected += 1
        if (flag == "BLANK") { unusable += 1; return flag }
        if (flag != "OK") return flag
        qualified += 1
        prevMeans = means
        var cands = pack.search(DacDhash.dhashRegion(luma, width, rect), topK, th.radius)
        if (mirrorInvariant) {
            val flipped = pack.search(DacDhash.dhashRegion(luma, width, rect, mirrored = true), topK, th.radius)
            val best = LinkedHashMap<Recognition.Locator, Recognition.Candidate>()
            for (c in cands + flipped) {
                val prev = best[c.locator]
                if (prev == null || c.distance < prev.distance) best[c.locator] = c
            }
            cands = best.values.sortedBy { it.distance }.take(topK)   // stable, like Python sorted()
        }
        perFrame += tMs.toInt() to cands
        return flag
    }

    /** Verification + decision. Returns null if cancelled (checked between steps). */
    fun finish(isCancelled: () -> Boolean): Recognition.Decision? {
        val snapshot: List<Pair<Int, List<Recognition.Candidate>>>
        val summary: Recognition.FrameSummary
        synchronized(this) {
            closed = true
            snapshot = ArrayList(perFrame)
            summary = Recognition.FrameSummary(selected, qualified, unusable)
        }
        if (isCancelled()) return null
        val hyps = Recognition.verify(snapshot, (pack.samplingIntervalS * 1000).toInt())
        if (isCancelled()) return null
        return Recognition.decide(hyps, summary, pack.works, th)
    }

    /** Display name for a decision: the episode's or work's localized name, else its ID. */
    fun displayName(d: Recognition.Decision, preferences: List<String>): String? =
        pack.resultDisplayName(d.workId, d.episodeId, preferences)
}
