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
        require(width >= 16 && height >= 9) { "frame too small" }
        require(pixelStride >= 3) { "pixelStride must cover R, G and B" }
        require(rowStride >= width * pixelStride) { "rowStride smaller than a row" }
        val needed = (height - 1).toLong() * rowStride + width.toLong() * pixelStride
        require(needed <= buffer.limit()) { "buffer too small for the declared strides" }
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

    /** Returns the quality flag (OK, BLANK, FLAT, STATIC) or CLOSED for a late frame. */
    @Synchronized
    fun process(tMs: Long, luma: IntArray, width: Int, height: Int): String {
        if (closed) return "CLOSED"
        require(luma.size == width * height) { "luma size mismatch" }
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
    fun displayName(d: Recognition.Decision, preferences: List<String>): String? {
        val id = d.workId ?: return null
        val idx = pack.works.indexOfFirst { w ->
            if (d.episodeId != null) w.seriesId == id && w.episodeId == d.episodeId else w.workId == id && w.seriesId == null
        }
        return if (idx >= 0) pack.displayName(idx, preferences) else id
    }
}
