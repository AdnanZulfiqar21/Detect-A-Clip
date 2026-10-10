package ai.detectaclip.lab

import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The recognition engine on Android's ART runtime (emulator or device): every committed golden
 * file must give the same verdicts as on the JVM and in Python, and Ed25519 must be served by
 * a platform provider (PackLoader relies on it; its availability per OS version was recorded
 * as a device check). Golden files are packaged as test assets from src/test/resources.
 * Timings are logged for the record only; they are emulator numbers unless run on a named device.
 */
@RunWith(AndroidJUnit4::class)
class EngineOnArtTest {
    private val assets = InstrumentationRegistry.getInstrumentation().context.assets
    private fun lines(name: String): List<String> = assets.open(name).bufferedReader(Charsets.UTF_8).readLines()

    private fun check(r: GoldenRunner.Report) {
        Log.i("DAC-ART", r.toString())
        assertEquals("${r.name} case count", GoldenRunner.expectedCounts.getValue(r.name), r.cases)
        assertEquals(r.toString(), emptyList<String>(), r.mismatches)
    }

    @Test fun ed25519IsAvailableThroughAPlatformProvider() {
        val provider = GoldenRunner.ed25519Provider()
        Log.i("DAC-ART", "Ed25519 provider: $provider; SDK ${android.os.Build.VERSION.SDK_INT}; ${android.os.Build.FINGERPRINT}")
        assertNotNull("no Ed25519 Signature provider on this runtime", provider)
    }

    @Test fun recognitionGolden() = check(GoldenRunner.recognition(lines("golden_recognition.txt")))
    @Test fun dacDhashGolden() = check(GoldenRunner.dacDhash(lines("golden_dac_dhash_v1.txt")))
    @Test fun exactPathGolden() = check(GoldenRunner.exact(lines("golden_exact.txt")))
    @Test fun endToEndGolden() = check(GoldenRunner.e2e(lines("golden_e2e.txt")))
    @Test fun formatContract() = check(GoldenRunner.format(lines("golden_format_cases.txt")))
    @Test fun manifestContractWithPlatformEd25519() = check(GoldenRunner.manifest(lines("golden_manifest_cases.txt")))

    @Test fun fullPipelineWithTiming() {
        val timing = ArrayList<GoldenRunner.PipelineTiming>()
        val r = GoldenRunner.pipeline(lines("golden_pipeline.txt"), timing)
        val perFrame = timing.filter { it.frames > 0 }.map { it.perFrameUs }
        Log.i("DAC-ART", "pipeline per-frame us (64x36, crop+quality+hash+mirror+retrieval): median=${perFrame.sorted()[perFrame.size / 2]} max=${perFrame.max()}; " +
            "finish us max=${timing.maxOf { it.finishUs }}")
        check(r)
        assertTrue(timing.size == 12)
    }
}
