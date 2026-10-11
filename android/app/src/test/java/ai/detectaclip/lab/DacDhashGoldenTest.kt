package ai.detectaclip.lab

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class DacDhashGoldenTest {
    private fun golden(): File = listOf("src/test/resources/golden_dac_dhash_v1.txt", "android/app/src/test/resources/golden_dac_dhash_v1.txt",
        "app/src/test/resources/golden_dac_dhash_v1.txt").map(::File).first { it.exists() }

    @Test fun kotlinHashIsBitIdenticalToPython() {
        var n = 0
        for (line in golden().readLines()) {
            if (line.isBlank() || line.startsWith("#")) continue
            val p = line.split(" ")
            val seed = p[1].toInt(); val w = p[2].toInt(); val h = p[3].toInt()
            val expected = java.lang.Long.parseUnsignedLong(p[4], 16)
            assertEquals("seed=$seed ${w}x$h", expected, DacDhash.hash(DacDhash.testFrame(seed, w, h), w, h))
            n++
        }
        assertTrue(n >= 40)
    }

    @Test fun rgbaStrideGivesSameHashAsRgb() {
        val rgb = DacDhash.testFrame(3, 64, 36)
        val rgba = ByteArray(64 * 36 * 4)
        for (k in 0 until 64 * 36) { rgba[k * 4] = rgb[k * 3]; rgba[k * 4 + 1] = rgb[k * 3 + 1]; rgba[k * 4 + 2] = rgb[k * 3 + 2]; rgba[k * 4 + 3] = -1 }
        assertEquals(DacDhash.hash(rgb, 64, 36), DacDhash.hash(rgba, 64, 36, stride = 4))
    }
}
