package ai.detectaclip.lab

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/** Every verdict in golden_format_cases.txt (generated and checked by the Python parser) must be
 *  reproduced by the Kotlin parser; plus display-name parity with Python resolve_display_name. */
class FormatContractTest {
    private fun file(name: String): File = listOf("src/test/resources/$name", "android/app/src/test/resources/$name",
        "app/src/test/resources/$name").map(::File).first { it.exists() }

    private fun hex(s: String) = ByteArray(s.length / 2) { s.substring(2 * it, 2 * it + 2).toInt(16).toByte() }

    @Test fun kotlinVerdictsMatchThePythonContract() {
        val mismatches = ArrayList<String>()
        var n = 0
        for (line in file("golden_format_cases.txt").readLines()) {
            if (!line.startsWith("CASE ")) continue
            val p = line.split(" ")
            val accepted = try { PackIndex.parse(hex(p[3])); true } catch (e: IllegalArgumentException) { false } catch (e: java.nio.charset.CharacterCodingException) { false }
            if (accepted != (p[2] == "ACCEPT")) mismatches += "${p[1]}: expected ${p[2]}"
            n++
        }
        assertTrue("expected the full case list, got $n", n >= 49)
        assertEquals(emptyList<String>(), mismatches)
    }

    @Test fun acceptedV5CaseExposesNamesAliasesScenesAndSeriesNames() {
        val line = file("golden_format_cases.txt").readLines().first { it.startsWith("CASE valid_v5_series_names_aliases_shared_scene ") }
        val p = PackIndex.parse(hex(line.split(" ")[3]))
        assertEquals("idx-flat-5", p.formatVersion)
        assertEquals("Synthetic Series X", p.resultDisplayName("S-X", null, listOf("en")))
        assertEquals("Masnooi Series X", p.resultDisplayName("S-X", null, listOf("ur-PK")))
        assertEquals("S-Y", p.resultDisplayName("S-Y", null, listOf("en")))
        assertEquals(listOf("Synthetic Work Zero"), p.aliases[0])
        assertEquals("intro-S-X", p.sharedScenes.single().groupId)
        assertEquals(listOf("E2_BROADCAST"), p.works[2].editions)
        assertEquals("Masnooi Kaam 000", p.displayName(0, listOf("ur-Latn")))
        assertEquals("Masnooi Kaam 000", p.displayName(0, listOf("ur-PK")))
        assertEquals("Synthetic Work 000", p.displayName(0, listOf("ko")))
        assertEquals("SW100", PackIndex.resolveDisplayName(emptyMap(), listOf("en"), "SW100"))
    }

    @Test fun resultDisplayNamesMatchPython() {
        val lines = file("golden_format_cases.txt").readLines()
        val p = PackIndex.parse(hex(lines.first { it.startsWith("CASE valid_v5_series_names_aliases_shared_scene ") }.split(" ")[3]))
        val cases = lines.filter { it.startsWith("DISPLAY ") }.map { it.split(" ") }
        assertTrue(cases.size >= 10)
        for (c in cases) {
            val prefs = if (c[3] == "-") emptyList() else c[3].split(",")
            val expected = if (c[4] == "-") null else String(hex(c[4]), Charsets.UTF_8)
            assertEquals(c.joinToString(" "), expected,
                p.resultDisplayName(c[1].takeIf { it != "-" }, c[2].takeIf { it != "-" }, prefs))
        }
    }

    @Test fun v3AndV4PayloadsMigrateWithEmptyAliasesScenesAndSeriesNames() {
        val lines = file("golden_format_cases.txt").readLines()
        val v3 = PackIndex.parse(hex(lines.first { it.startsWith("CASE valid_v3_migration_no_aliases ") }.split(" ")[3]))
        assertEquals("idx-flat-3", v3.formatVersion)
        assertTrue(v3.aliases.all { it.isEmpty() } && v3.sharedScenes.isEmpty())
        assertEquals(mapOf("S-X" to emptyMap<String, String>()), v3.seriesNames)
        assertEquals("S-X", v3.resultDisplayName("S-X", null, listOf("en")))     // no names: the ID itself
        val v4 = PackIndex.parse(hex(lines.first { it.startsWith("CASE valid_v4_migration_no_series ") }.split(" ")[3]))
        assertEquals("idx-flat-4", v4.formatVersion)
        assertEquals(listOf("Synthetic Work Zero"), v4.aliases[0])
        assertEquals(mapOf("S-X" to emptyMap<String, String>()), v4.seriesNames)
    }
}
