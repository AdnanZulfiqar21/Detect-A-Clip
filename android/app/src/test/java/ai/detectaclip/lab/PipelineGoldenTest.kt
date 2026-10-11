package ai.detectaclip.lab

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.ByteBuffer

/**
 * Full exact pipeline parity with Python (golden_pipeline.txt), plus FrameView stride and
 * ownership checks. Frames are rebuilt from the shared xorshift source and fed through
 * FrameSelector + FrameView(rowStride, pixelStride) + RecognitionSession.
 */
class PipelineGoldenTest {
    private fun file(): File = listOf("src/test/resources/golden_pipeline.txt", "android/app/src/test/resources/golden_pipeline.txt",
        "app/src/test/resources/golden_pipeline.txt").map(::File).first { it.exists() }

    private fun hex(s: String) = ByteArray(s.length / 2) { s.substring(2 * it, 2 * it + 2).toInt(16).toByte() }

    private fun scaleNearest(src: ByteArray, w: Int, h: Int, nw: Int, nh: Int): ByteArray {
        val out = ByteArray(nw * nh * 3)
        for (y in 0 until nh) for (x in 0 until nw) {
            val sy = (y * h) / nh; val sx = (x * w) / nw
            for (c in 0 until 3) out[(y * nw + x) * 3 + c] = src[(sy * w + sx) * 3 + c]
        }
        return out
    }

    private fun place(dst: ByteArray, w: Int, src: ByteArray, sw: Int, sh: Int, ox: Int, oy: Int) {
        for (y in 0 until sh) System.arraycopy(src, y * sw * 3, dst, ((oy + y) * w + ox) * 3, sw * 3)
    }

    /** Same composition as pipeline_golden.compose (RGB, 3 bytes per pixel). */
    private fun compose(seed: Int, variant: String, bright: Int, w: Int, h: Int): ByteArray {
        if (variant == "black") return ByteArray(w * h * 3)
        val c = DacDhash.contentFrame(seed, w, h)
        var out = when (variant) {
            "full" -> c
            "mirror" -> ByteArray(c.size).also { o -> for (y in 0 until h) for (x in 0 until w) for (k in 0 until 3) o[(y * w + x) * 3 + k] = c[(y * w + (w - 1 - x)) * 3 + k] }
            "letterbox" -> ByteArray(w * h * 3).also { place(it, w, scaleNearest(c, w, h, w, 26), w, 26, 0, 5) }
            "pillarbox" -> ByteArray(w * h * 3).also { place(it, w, scaleNearest(c, w, h, 48, h), 48, h, 8, 0) }
            "pip" -> ByteArray(w * h * 3) { 235.toByte() }.also { o ->
                for (i in 0 until 5 * w * 3) o[i] = 60
                place(o, w, scaleNearest(c, w, h, 40, 22), 40, 22, 12, 9)
            }
            else -> error(variant)
        }
        if (bright != 0) out = ByteArray(out.size) { ((out[it].toInt() and 0xFF) + bright).coerceIn(0, 255).toByte() }
        return out
    }

    /** RGB -> padded RGBA plane (rowStride > width * 4), like an ImageReader plane. */
    private fun toPaddedRgba(rgb: ByteArray, w: Int, h: Int, pad: Int): Pair<ByteBuffer, Int> {
        val rowStride = w * 4 + pad
        val buf = ByteBuffer.allocateDirect(rowStride * h)
        for (y in 0 until h) for (x in 0 until w) {
            val p = y * rowStride + x * 4
            buf.put(p, rgb[(y * w + x) * 3]); buf.put(p + 1, rgb[(y * w + x) * 3 + 1]); buf.put(p + 2, rgb[(y * w + x) * 3 + 2]); buf.put(p + 3, -1)
            if (x == w - 1) for (k in 0 until pad) buf.put(y * rowStride + w * 4 + k, 0x5A)   // garbage in the padding
        }
        return buf to rowStride
    }

    @Test fun sessionReproducesPythonPipeline() {
        val lines = file().readLines().filter { it.isNotBlank() && !it.startsWith("#") }
        val size = lines[0].split(" "); val w = size[1].toInt(); val h = size[2].toInt()
        val pack = PackIndex.parse(hex(lines[1].removePrefix("PACKHEX ")))
        val t = lines[2].split(" ")
        val th = Recognition.Thresholds(t[1].toInt(), t[2].toInt(), t[3].toDouble(), t[4].toInt(), t[5].toDouble(), t[6].toInt(),
            t[7].toInt(), t[8].toInt(), t[9].toDouble(), t[10] == "1", t[11].toInt(), t[12].toDouble())
        val topK = t[13].toInt()
        var i = 3; var queries = 0
        val mismatches = ArrayList<String>()
        while (i < lines.size) {
            val q = lines[i++].split(" ")
            val n = q[2].toInt()
            val selector = FrameSelector()
            val session = RecognitionSession(pack, th, topK, mirrorInvariant = true)
            var offered = 0
            repeat(n) {
                val f = lines[i++].split(" ")
                val ts = f[1].toLong()
                offered += 1
                if (selector.offer(ts)) {
                    try {
                        val (buf, stride) = toPaddedRgba(compose(f[2].toInt(), f[3], f[4].toInt(), w, h), w, h, pad = 12)
                        val luma = FrameView(buf, w, h, stride, 4).toLuma()
                        session.process(ts, luma, w, h)
                    } finally { selector.release() }
                }
            }
            selector.close()
            val s = lines[i++].split(" ")
            val expectedR = lines[i++]
            val d = session.finish { false }!!
            val segs = d.segments.joinToString("|") { g -> "${g.workId}@${g.editionId ?: "-"}@${g.queryStartMs}@${g.queryEndMs}@${g.referenceOffsetMs ?: "-"}@${g.supportingFrames}" }.ifEmpty { "-" }
            val gotR = "R ${d.state} ${d.workId ?: "-"} ${d.editionId ?: "-"} ${d.episodeId ?: "-"} ${d.flags.joinToString(",").ifEmpty { "-" }} $segs"
            val gotS = "S $offered ${session.selected} ${session.qualified} ${session.unusable}"
            if (gotS != s.joinToString(" ")) mismatches += "${q[1]} summary: $gotS vs ${s.joinToString(" ")}"
            if (gotR != expectedR) mismatches += "${q[1]}: $gotR vs $expectedR"
            queries++
        }
        assertEquals(12, queries)
        assertEquals(emptyList<String>(), mismatches)
    }

    @Test fun strideVariantsGiveIdenticalLuma() {
        val w = 64; val h = 36
        val rgb = DacDhash.contentFrame(7, w, h)
        val compact = DacDhash.luma(rgb, w, h)
        for (pad in listOf(0, 4, 13, 64)) {
            val (buf, stride) = toPaddedRgba(rgb, w, h, pad)
            assertTrue(FrameView(buf, w, h, stride, 4).toLuma().contentEquals(compact))
        }
        val rgbBuf = ByteBuffer.wrap(rgb)
        assertTrue(FrameView(rgbBuf, w, h, w * 3, 3).toLuma().contentEquals(compact))
    }

    @Test fun lumaIsAnOwnedCopyAndBufferStateIsUntouched() {
        val w = 64; val h = 36
        val (buf, stride) = toPaddedRgba(DacDhash.contentFrame(3, w, h), w, h, 8)
        buf.position(17)
        val luma = FrameView(buf, w, h, stride, 4).toLuma()
        val copy = luma.copyOf()
        for (k in 0 until buf.capacity()) buf.put(k, 0)          // OS reuses the buffer after close()
        assertTrue(luma.contentEquals(copy))
        assertEquals(17, buf.position())
    }

    @Test fun inconsistentStridesAreRefused() {
        val buf = ByteBuffer.allocate(64 * 4 * 36)
        assertThrows(IllegalArgumentException::class.java) { FrameView(buf, 64, 36, 64 * 4 - 1, 4) }   // row too short
        assertThrows(IllegalArgumentException::class.java) { FrameView(buf, 64, 36, 64 * 4 + 8, 4) }   // buffer too small
        assertThrows(IllegalArgumentException::class.java) { FrameView(buf, 64, 36, 64 * 2, 2) }       // no B channel
        assertThrows(IllegalArgumentException::class.java) { FrameView(buf, 8, 8, 32, 4) }             // too small
    }

    @Test fun lateFrameAfterFinishIsRefused() {
        val lines = file().readLines()
        val pack = PackIndex.parse(hex(lines.first { it.startsWith("PACKHEX ") }.removePrefix("PACKHEX ")))
        val s = RecognitionSession(pack, Recognition.Thresholds(radius = 9.0))
        val luma = DacDhash.luma(DacDhash.contentFrame(1, 64, 36), 64, 36)
        assertEquals("OK", s.process(0, luma, 64, 36))
        s.finish { false }
        assertEquals("CLOSED", s.process(500, luma, 64, 36))
        assertEquals(1, s.selected)
    }

    @Test fun cancellationDuringFinishReturnsNull() {
        val lines = file().readLines()
        val pack = PackIndex.parse(hex(lines.first { it.startsWith("PACKHEX ") }.removePrefix("PACKHEX ")))
        val s = RecognitionSession(pack, Recognition.Thresholds(radius = 9.0))
        var calls = 0
        assertEquals(null, s.finish { ++calls > 1 })
    }
}
