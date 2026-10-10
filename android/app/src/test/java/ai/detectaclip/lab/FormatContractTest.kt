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

    @Test fun acceptedV4CaseExposesNamesAliasesAndSharedScenes() {
        val line = file("golden_format_cases.txt").readLines().first { it.startsWith("CASE valid_v4_aliases_series_shared_scene ") }
        val p = PackIndex.parse(hex(line.split(" ")[3]))
        assertEquals("idx-flat-4", p.formatVersion)
        assertEquals(listOf("Synthetic Work Zero"), p.aliases[0])
        assertEquals("intro-S-X", p.sharedScenes.single().groupId)
        assertEquals(listOf("E2_BROADCAST"), p.works[2].editions)
        assertEquals("Masnooi Kaam 000", p.displayName(0, listOf("ur-Latn")))
        assertEquals("Masnooi Kaam 000", p.displayName(0, listOf("ur-PK")))
        assertEquals("Synthetic Work 000", p.displayName(0, listOf("ko")))
        assertEquals("SW100", PackIndex.resolveDisplayName(emptyMap(), listOf("en"), "SW100"))
    }

    @Test fun v3PayloadMigratesWithEmptyAliasesAndScenes() {
        val line = file("golden_format_cases.txt").readLines().first { it.startsWith("CASE valid_v3_migration_no_aliases ") }
        val p = PackIndex.parse(hex(line.split(" ")[3]))
        assertEquals("idx-flat-3", p.formatVersion)
        assertTrue(p.aliases.all { it.isEmpty() } && p.sharedScenes.isEmpty())
    }
}
