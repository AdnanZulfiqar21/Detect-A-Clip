package ai.detectaclip.lab

/**
 * DAC-DHASH-v1 (see l0/dac_l0/index/exact.py): integer-only 64-bit difference hash that is
 * bit-identical across Python, Kotlin and Swift. CANDIDATE device descriptor; not yet used by
 * any pack (adoption needs new calibration and a new sealed evaluation).
 *
 * Input is interleaved RGB bytes (the RGBA_8888 ImageReader path drops alpha before calling).
 */
object DacDhash {
    const val SPEC = "DAC-DHASH-v1"

    fun hash(rgb: ByteArray, width: Int, height: Int, stride: Int = 3): Long {
        require(width >= 9 && height >= 8) { "frame too small" }
        require(rgb.size >= width * height * stride) { "buffer too small" }
        val means = Array(8) { LongArray(9) }
        for (j in 0 until 8) {
            val y0 = (j * height) / 8
            val y1 = ((j + 1) * height) / 8
            for (i in 0 until 9) {
                val x0 = (i * width) / 9
                val x1 = ((i + 1) * width) / 9
                var sum = 0L
                for (y in y0 until y1) {
                    var p = (y * width + x0) * stride
                    for (x in x0 until x1) {
                        val r = rgb[p].toInt() and 0xFF
                        val g = rgb[p + 1].toInt() and 0xFF
                        val b = rgb[p + 2].toInt() and 0xFF
                        sum += (77 * r + 150 * g + 29 * b + 128) shr 8
                        p += stride
                    }
                }
                val count = (y1 - y0).toLong() * (x1 - x0)
                means[j][i] = sum / count
            }
        }
        var v = 0L
        for (j in 0 until 8) for (i in 0 until 8) {
            v = (v shl 1) or (if (means[j][i + 1] > means[j][i]) 1L else 0L)
        }
        return v
    }

    // ------------------------------------------------ exact device path (ED-17)

    /** Integer BT.601 luma of an interleaved RGB(A) buffer. */
    fun luma(rgb: ByteArray, width: Int, height: Int, stride: Int = 3): IntArray {
        val y = IntArray(width * height)
        for (k in 0 until width * height) {
            val p = k * stride
            y[k] = (77 * (rgb[p].toInt() and 0xFF) + 150 * (rgb[p + 1].toInt() and 0xFF) + 29 * (rgb[p + 2].toInt() and 0xFF) + 128) shr 8
        }
        return y
    }

    private fun trim(flags: BooleanArray): IntArray {
        var lo = 0; var hi = flags.size
        while (lo < hi && flags[lo]) lo++
        while (hi > lo && flags[hi - 1]) hi--
        return intArrayOf(lo, hi)
    }

    /** DAC-CROP-v1: returns [top, bottom, left, right) half-open; see exact.py crop_rect. */
    fun cropRect(y: IntArray, w: Int, h: Int): IntArray {
        var top = 0; var bot = h; var left = 0; var right = w
        repeat(2) {
            if (bot <= top || right <= left) return@repeat
            val rows = BooleanArray(bot - top) { r ->
                var mx = Int.MIN_VALUE; var mn = Int.MAX_VALUE
                for (x in left until right) { val v = y[(top + r) * w + x]; if (v > mx) mx = v; if (v < mn) mn = v }
                mx < 16 || mx - mn <= 8
            }
            val tr = trim(rows); val t0 = top
            top = t0 + tr[0]; bot = t0 + tr[1]
            if (bot <= top) return@repeat
            val cols = BooleanArray(right - left) { c ->
                var mx = Int.MIN_VALUE; var mn = Int.MAX_VALUE
                for (yy in top until bot) { val v = y[yy * w + left + c]; if (v > mx) mx = v; if (v < mn) mn = v }
                mx < 16 || mx - mn <= 8
            }
            val tc = trim(cols); val l0 = left
            left = l0 + tc[0]; right = l0 + tc[1]
        }
        if (10 * (bot - top) < 4 * h || 10 * (right - left) < 4 * w) return intArrayOf(0, h, 0, w)
        return intArrayOf(top, bot, left, right)
    }

    /** Integer area means on a gx×gy grid of the region (row-major gy×gx). */
    fun cellMeans(y: IntArray, w: Int, rect: IntArray, gx: Int, gy: Int, mirrored: Boolean = false): LongArray {
        val rh = rect[1] - rect[0]; val rw = rect[3] - rect[2]
        require(rw >= gx && rh >= gy) { "frame too small" }
        val out = LongArray(gx * gy)
        for (j in 0 until gy) {
            val y0 = (j * rh) / gy; val y1 = ((j + 1) * rh) / gy
            for (i in 0 until gx) {
                val x0 = (i * rw) / gx; val x1 = ((i + 1) * rw) / gx
                var sum = 0L
                for (yy in y0 until y1) for (xx in x0 until x1) {
                    val sx = if (mirrored) rw - 1 - xx else xx
                    sum += y[(rect[0] + yy) * w + rect[2] + sx]
                }
                out[j * gx + i] = sum / ((y1 - y0).toLong() * (x1 - x0))
            }
        }
        return out
    }

    fun dhashRegion(y: IntArray, w: Int, rect: IntArray, mirrored: Boolean = false): Long {
        val m = cellMeans(y, w, rect, 9, 8, mirrored)
        var v = 0L
        for (j in 0 until 8) for (i in 0 until 8) v = (v shl 1) or (if (m[j * 9 + i + 1] > m[j * 9 + i]) 1L else 0L)
        return v
    }

    /** DAC-QUAL-v1 on 16×9 cell means: BLANK / FLAT / STATIC / OK. */
    fun quality(y: IntArray, w: Int, rect: IntArray, prev: LongArray?): Pair<String, LongArray> {
        val m = cellMeans(y, w, rect, 16, 9)
        val mx = m.max(); val mn = m.min()
        if (mx < 12) return "BLANK" to m
        if (mx - mn < 6) return "FLAT" to m
        if (prev != null && m.indices.all { kotlin.math.abs(m[it] - prev[it]) <= 1 }) return "STATIC" to m
        return "OK" to m
    }

    fun exactDescribe(rgb: ByteArray, w: Int, h: Int, stride: Int = 3, mirrored: Boolean = false): Long {
        val y = luma(rgb, w, h, stride)
        return dhashRegion(y, w, cropRect(y, w, h), mirrored)
    }

    fun hamming(a: Long, b: Long): Int = java.lang.Long.bitCount(a xor b)

    /** Shared deterministic test-frame source (must match exact.py XorShift32/test_frame). */
    class XorShift32(seed: Int) {
        private var s: Int = if (seed == 0) 0x9E3779B9.toInt() else seed
        fun next(): Long {
            var x = s
            x = x xor (x shl 13)
            x = x xor (x ushr 17)
            x = x xor (x shl 5)
            s = x
            return x.toLong() and 0xFFFFFFFFL
        }
    }

    fun testFrame(seed: Int, w: Int, h: Int): ByteArray {
        val rng = XorShift32(seed)
        val rx = (rng.next() % w).toInt()
        val ry = (rng.next() % h).toInt()
        val rw = 1 + (rng.next() % (w / 2)).toInt()
        val rh = 1 + (rng.next() % (h / 2)).toInt()
        val col = intArrayOf((rng.next() and 255).toInt(), (rng.next() and 255).toInt(), (rng.next() and 255).toInt())
        val out = ByteArray(w * h * 3)
        for (y in 0 until h) for (x in 0 until w) {
            val inside = x >= rx && x < rx + rw && y >= ry && y < ry + rh
            for (ch in 0 until 3) {
                val base = if (inside) col[ch] else (((x * 255) / maxOf(1, w - 1) + (y * 255) / maxOf(1, h - 1) * (ch + 1)) and 255)
                val noise = (rng.next() ushr 28).toInt() - 8
                out[(y * w + x) * 3 + ch] = (base + noise).coerceIn(0, 255).toByte()
            }
        }
        return out
    }

    /** Must match exact.py content_frame (block colours row-major, then noise y→x→channel). */
    fun contentFrame(seed: Int, w: Int, h: Int, bx: Int = 16, by: Int = 9): ByteArray {
        val rng = XorShift32(seed)
        val cols = Array(by) { Array(bx) { IntArray(3) { (rng.next() and 255).toInt() } } }
        val out = ByteArray(w * h * 3)
        val bw = maxOf(1, w / bx)
        val bh = maxOf(1, h / by)
        for (y in 0 until h) {
            val cy = minOf(by - 1, y / bh)
            for (x in 0 until w) {
                val cx = minOf(bx - 1, x / bw)
                for (ch in 0 until 3) {
                    val v = cols[cy][cx][ch] + (rng.next() ushr 28).toInt() - 8
                    out[(y * w + x) * 3 + ch] = v.coerceIn(0, 255).toByte()
                }
            }
        }
        return out
    }
}
