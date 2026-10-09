package ai.detectaclip.lab

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/** DAC-CROP-v1, DAC-QUAL-v1 and mirrored DAC-DHASH-v1 must equal the Python reference. */
class ExactPathGoldenTest {
    private fun golden(): File = listOf("src/test/resources/golden_exact.txt", "android/app/src/test/resources/golden_exact.txt",
        "app/src/test/resources/golden_exact.txt").map(::File).first { it.exists() }

    private fun compose(w: Int, h: Int, seed: Int, iw: Int, ih: Int, ox: Int, oy: Int, bg: Int, bx: Int, by: Int): ByteArray {
        val out = ByteArray(w * h * 3) { bg.toByte() }
        if (iw > 0 && ih > 0) {
            val c = DacDhash.contentFrame(seed, iw, ih, bx, by)
            for (y in 0 until ih) for (x in 0 until iw) for (ch in 0 until 3) {
                out[((oy + y) * w + ox + x) * 3 + ch] = c[(y * iw + x) * 3 + ch]
            }
        }
        return out
    }

    @Test fun exactPathMatchesPython() {
        val lines = golden().readLines().filter { it.isNotBlank() && !it.startsWith("#") }
        val size = lines[0].split(" ")
        val w = size[1].toInt(); val h = size[2].toInt()
        var n = 0
        for (line in lines.drop(1)) {
            val p = line.split(" ")
            val seed = p[2].toInt()
            val args = p.subList(3, 10).map { it.toInt() } // iw ih ox oy bg bx by
            val seeds = listOf(seed, seed, seed + 1000)
            var prev: LongArray? = null
            val rects = ArrayList<String>(); val flags = ArrayList<String>(); val hashes = ArrayList<String>()
            for (s in seeds) {
                val f = compose(w, h, s, args[0], args[1], args[2], args[3], args[4], args[5], args[6])
                val y = DacDhash.luma(f, w, h)
                val r = DacDhash.cropRect(y, w, h)
                val (flag, means) = DacDhash.quality(y, w, r, prev)
                if (flag == "OK") prev = means
                rects += r.joinToString(","); flags += flag
                hashes += "%016x:%016x".format(DacDhash.dhashRegion(y, w, r), DacDhash.dhashRegion(y, w, r, mirrored = true))
            }
            assertEquals(p[1] + " rect", p[10], rects.joinToString("/"))
            assertEquals(p[1] + " quality", p[11], flags.joinToString("/"))
            assertEquals(p[1] + " hashes", p[12], hashes.joinToString("/"))
            n++
        }
        assertTrue(n >= 9)
    }

    @Test fun fullFrameExactDescribeEqualsPlainHashWhenNothingIsCropped() {
        val f = DacDhash.contentFrame(5, 160, 90)
        assertEquals(DacDhash.hash(f, 160, 90), DacDhash.exactDescribe(f, 160, 90))
    }
}
