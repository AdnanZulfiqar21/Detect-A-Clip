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
