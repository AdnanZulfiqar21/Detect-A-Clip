package ai.detectaclip.lab

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.time.OffsetDateTime

/** Kotlin PackLoader verdicts must equal the Python loader on every committed manifest case,
 *  and a rejected pack must leave the device state unchanged. */
class ManifestContractTest {
    private fun file(): File = listOf("src/test/resources/golden_manifest_cases.txt", "android/app/src/test/resources/golden_manifest_cases.txt",
        "app/src/test/resources/golden_manifest_cases.txt").map(::File).first { it.exists() }

    private fun hex(s: String) = ByteArray(s.length / 2) { s.substring(2 * it, 2 * it + 2).toInt(16).toByte() }

    @Test fun kotlinVerdictsMatchPython() {
        val lines = file().readLines()
        val pub = lines.first { it.startsWith("PUBKEY ") }.split(" ")
        val payloads = lines.filter { it.startsWith("PAYLOAD ") }.associate { val p = it.split(" "); p[1] to hex(p[2]) }
        val mismatches = ArrayList<String>()
        var n = 0
        for (line in lines.filter { it.startsWith("CASE ") }) {
            val p = line.split(" ")
            val kv = p.drop(3).associate { it.substringBefore("=") to it.substringAfter("=") }
            val st = PackLoader.DeviceRightsState().apply {
                minimumRightsEpoch = kv.getValue("epoch").toLong()
                trustedKeys[pub[1]] = hex(pub[2])
                if (kv["revoked"] == "1") revokedKeyIds += pub[1]
                if (kv["floors"] != "-") for (item in kv.getValue("floors").split(",")) {
                    minimumPackVersions[item.substringBefore(":")] = PackLoader.parseVersion(item.substringAfter(":"), "floor")
                }
            }
            val before = Triple(st.minimumRightsEpoch, HashMap(st.installedIndexBytes), HashMap(st.minimumPackVersions))
            val now = kv["now"]?.takeIf { it != "UNTRUSTED" }?.let { OffsetDateTime.parse(it) }
            val accepted = try {
                PackLoader(st).load(hex(kv.getValue("manifest")), hex(kv.getValue("sig")), payloads.getValue(kv.getValue("payload")), now, kv["release"] == "1")
                true
            } catch (e: PackLoader.Rejected) { false }
            if (accepted != (p[2] == "ACCEPT")) mismatches += "${p[1]}: expected ${p[2]}"
            if (!accepted) assertEquals("state changed on rejection in ${p[1]}", before,
                Triple(st.minimumRightsEpoch, HashMap(st.installedIndexBytes), HashMap(st.minimumPackVersions)))
            n++
        }
        assertTrue("case count $n", n >= 50)
        assertEquals(emptyList<String>(), mismatches)
    }
}
