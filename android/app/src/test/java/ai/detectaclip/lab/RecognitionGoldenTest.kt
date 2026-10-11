package ai.detectaclip.lab

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The Kotlin port must reproduce the Python reference (l0/dac_l0/eval/golden.py) exactly:
 * every hypothesis field (incl. mean distance as an exact double) and every decision field.
 */
class RecognitionGoldenTest {

    private fun goldenFile(): File {
        val candidates = listOf("src/test/resources/golden_recognition.txt", "android/app/src/test/resources/golden_recognition.txt",
            "app/src/test/resources/golden_recognition.txt")
        return candidates.map { File(it) }.firstOrNull { it.exists() }
            ?: error("golden_recognition.txt not found from ${File(".").absolutePath}")
    }

    @Test fun portMatchesPythonReferenceOnAllGoldenCases() {
        val lines = goldenFile().readLines().filter { it.isNotBlank() && !it.startsWith("#") }
        var i = 0
        val nWorks = lines[i++].removePrefix("WORKS ").toInt()
        val works = (0 until nWorks).map {
            val p = lines[i++].split(" ")
            Recognition.WorkEntry(p[1].toInt(), p[2], p[3].takeIf { s -> s != "-" }, p[4].takeIf { s -> s != "-" }, p[5].split(","))
        }
        var cases = 0
        while (i < lines.size) {
            val header = lines[i++]; check(header.startsWith("CASE ")) { header }
            val f = lines[i++].split(" ")
            val frames = Recognition.FrameSummary(f[1].toInt(), f[2].toInt(), f[3].toInt())
            val t = lines[i++].split(" ")
            val th = Recognition.Thresholds(
                minQualifiedFrames = t[1].toInt(), verifiedMinSupport = t[2].toInt(), verifiedMinSupportFraction = t[3].toDouble(),
                verifiedMinSpanMs = t[4].toInt(), verifiedMaxMeanDistFrac = t[5].toDouble(), verifiedMinMargin = t[6].toInt(),
                possibleMinSupport = t[7].toInt(), possibleMinSpanMs = t[8].toInt(), possibleMaxMeanDistFrac = t[9].toDouble(),
                possibleOnCompetition = t[10] == "1", episodeMargin = t[11].toInt(), radius = t[12].toDouble(),
            )
            val perFrame = ArrayList<Pair<Int, List<Recognition.Candidate>>>()
            while (lines[i].startsWith("PF ")) {
                val p = lines[i++].split(" ")
                val cands = if (p[2] == "-") emptyList() else p[2].split(";").map { c ->
                    val q = c.split(":")
                    Recognition.Candidate(Recognition.Locator(q[0].toInt(), q[1].toInt(), q[2].toInt()), q[3].toDouble())
                }
                perFrame += p[1].toInt() to cands
            }
            val expectedH = ArrayList<String>()
            while (lines[i].startsWith("H ")) expectedH += lines[i++]
            val expectedR = lines[i++]
            check(lines[i++] == "END")

            val hyps = Recognition.verify(perFrame, 2000)
            val gotH = hyps.map { h ->
                "H ${h.work} ${h.edition ?: -1} ${h.offsetMs} ${h.support} ${h.meanDistance} ${h.queryStartMs} ${h.queryEndMs} " +
                    (h.ambiguousEditions.joinToString(",").ifEmpty { "-" })
            }
            assertEquals("hypotheses differ in $header", expectedH.map(::normaliseDoubles), gotH.map(::normaliseDoubles))

            val r = Recognition.decide(hyps, frames, works, th)
            val segs = r.segments.joinToString("|") { s ->
                "${s.workId}@${s.editionId ?: "-"}@${s.queryStartMs}@${s.queryEndMs}@${s.referenceOffsetMs ?: "-"}@${s.supportingFrames}"
            }.ifEmpty { "-" }
            val gotR = "R ${r.state} ${r.workId ?: "-"} ${r.editionId ?: "-"} ${r.episodeId ?: "-"} ${r.flags.joinToString(",").ifEmpty { "-" }} $segs"
            assertEquals("decision differs in $header", expectedR, gotR)
            cases++
        }
        assertTrue("expected at least 400 golden cases, got $cases", cases >= 400)
    }

    /** Python repr and Kotlin toString may format the same double differently (e.g. 1e-05 vs
     *  1.0E-5); compare the parsed value of field 5 exactly instead of its text. */
    private fun normaliseDoubles(line: String): String {
        val p = line.split(" ").toMutableList()
        p[5] = java.lang.Double.toString(p[5].toDouble())
        return p.joinToString(" ")
    }
}
