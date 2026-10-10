package ai.detectaclip.lab

import org.junit.Assert.assertEquals
import org.junit.Test
import java.io.File

/** The shared GoldenRunner (also executed on ART by EngineOnArtTest) agrees with the JVM goldens. */
class GoldenRunnerJvmTest {
    private fun lines(name: String): List<String> = listOf("src/test/resources/$name", "android/app/src/test/resources/$name",
        "app/src/test/resources/$name").map(::File).first { it.exists() }.readLines()

    private fun check(r: GoldenRunner.Report) {
        assertEquals("${r.name} case count", GoldenRunner.expectedCounts.getValue(r.name), r.cases)
        assertEquals(r.toString(), emptyList<String>(), r.mismatches)
    }

    @Test fun everyGoldenPassesThroughTheSharedRunner() {
        check(GoldenRunner.recognition(lines("golden_recognition.txt")))
        check(GoldenRunner.dacDhash(lines("golden_dac_dhash_v1.txt")))
        check(GoldenRunner.exact(lines("golden_exact.txt")))
        check(GoldenRunner.e2e(lines("golden_e2e.txt")))
        check(GoldenRunner.format(lines("golden_format_cases.txt")))
        check(GoldenRunner.manifest(lines("golden_manifest_cases.txt")))
        check(GoldenRunner.pipeline(lines("golden_pipeline.txt")))
    }
}
