package ai.detectaclip.lab

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * Python-built pack (hex) → Kotlin parser → DAC-DHASH-v1 query hashing → flat retrieval →
 * verification → decision must equal the Python reference for every golden query.
 */
class EndToEndGoldenTest {
    private fun golden(): File = listOf("src/test/resources/golden_e2e.txt", "android/app/src/test/resources/golden_e2e.txt",
        "app/src/test/resources/golden_e2e.txt").map(::File).first { it.exists() }

    private fun hex(s: String) = ByteArray(s.length / 2) { s.substring(2 * it, 2 * it + 2).toInt(16).toByte() }

    private fun frame(seed: Int, bright: Int): ByteArray {
        val f = DacDhash.contentFrame(seed, 64, 36)
        if (bright == 0) return f
        return ByteArray(f.size) { ((f[it].toInt() and 0xFF) + bright).coerceIn(0, 255).toByte() }
    }

    private fun load(): Triple<PackIndex, Recognition.Thresholds, List<String>> {
        val lines = golden().readLines().filter { it.isNotBlank() && !it.startsWith("#") }
        val pack = PackIndex.parse(hex(lines[0].removePrefix("PACKHEX ")))
        val t = lines[1].split(" ")
        val th = Recognition.Thresholds(
            minQualifiedFrames = t[1].toInt(), verifiedMinSupport = t[2].toInt(), verifiedMinSupportFraction = t[3].toDouble(),
            verifiedMinSpanMs = t[4].toInt(), verifiedMaxMeanDistFrac = t[5].toDouble(), verifiedMinMargin = t[6].toInt(),
            possibleMinSupport = t[7].toInt(), possibleMinSpanMs = t[8].toInt(), possibleMaxMeanDistFrac = t[9].toDouble(),
            possibleOnCompetition = t[10] == "1", episodeMargin = t[11].toInt(), radius = t[12].toDouble(),
        )
        return Triple(pack, th, lines.drop(2) + listOf(t[13]))
    }

    @Test fun kotlinEngineReproducesPythonDecisions() {
        val (pack, th, rest0) = load()
        val topK = rest0.last().toInt()
        val rest = rest0.dropLast(1)
        assertEquals(5, pack.works.size)
        var i = 0
        var queries = 0
        while (i < rest.size) {
            val q = rest[i++].split(" ")
            val n = q[2].toInt()
            val perFrame = ArrayList<Pair<Int, List<Recognition.Candidate>>>()
            repeat(n) {
                val f = rest[i++].split(" ")
                val h = DacDhash.hash(frame(f[2].toInt(), f[3].toInt()), 64, 36)
                perFrame += f[1].toInt() to pack.search(h, topK, th.radius)
            }
            val expected = rest[i++]
            val hyps = Recognition.verify(perFrame, (pack.samplingIntervalS * 1000).toInt())
            val r = Recognition.decide(hyps, Recognition.FrameSummary(n, n, 0), pack.works, th)
            val segs = r.segments.joinToString("|") { s ->
                "${s.workId}@${s.editionId ?: "-"}@${s.queryStartMs}@${s.queryEndMs}@${s.referenceOffsetMs ?: "-"}@${s.supportingFrames}"
            }.ifEmpty { "-" }
            assertEquals(q[1], expected, "R ${r.state} ${r.workId ?: "-"} ${r.editionId ?: "-"} ${r.episodeId ?: "-"} ${r.flags.joinToString(",").ifEmpty { "-" }} $segs")
            queries++
        }
        assertEquals(6, queries)
    }

    @Test fun parserRejectsTamperedOrTruncatedPayloads() {
        val (pack, _, _) = load()
        val bytes = hex(golden().readLines().first { it.startsWith("PACKHEX ") }.removePrefix("PACKHEX "))
        assertTrue(pack.vectorCount > 0)
        assertThrows(IllegalArgumentException::class.java) { PackIndex.parse(bytes.copyOf(bytes.size - 1)) }
        val badMagic = bytes.copyOf().also { it[0] = 'X'.code.toByte() }
        assertThrows(IllegalArgumentException::class.java) { PackIndex.parse(badMagic) }
        val inflated = bytes.copyOf().also { it[12] = (it[12] + 1).toByte() } // vector count field
        assertThrows(IllegalArgumentException::class.java) { PackIndex.parse(inflated) }
        assertThrows(IllegalArgumentException::class.java) { PackIndex.parse(bytes, maxPayloadBytes = 100) }
    }

    @Test fun packForAnotherDescriptorFamilyIsRejected() {
        val bytes = hex(golden().readLines().first { it.startsWith("PACKHEX ") }.removePrefix("PACKHEX "))
        val text = String(bytes, Charsets.ISO_8859_1).replace("\"DACDHASH\"", "\"HASH6400\"") // same length
        assertThrows(IllegalArgumentException::class.java) { PackIndex.parse(text.toByteArray(Charsets.ISO_8859_1)) }
    }

    @Test fun miniJsonRejectsMalformedInput() {
        for (bad in listOf("{\"a\":1,\"a\":2}", "[1,2", "{\"a\" 1}", "\"\u0001\"", "{}x", "[".repeat(40) + "]".repeat(40))) {
            assertThrows(Exception::class.java) { MiniJson.parse(bad) }
        }
        assertEquals(mapOf("k" to listOf(1L, 2.5, null, true)), MiniJson.parse("{\"k\":[1,2.5,null,true]}"))
    }
}
