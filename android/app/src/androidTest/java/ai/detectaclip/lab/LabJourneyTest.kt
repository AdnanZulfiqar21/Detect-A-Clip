package ai.detectaclip.lab

import android.content.Context
import android.content.Intent
import android.content.res.Resources
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.UiObject2
import androidx.test.uiautomator.Until
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Instrumented LAB journey on an emulator or device (capture disabled build). Runs in the app's
 * own process, so it checks the screen and the real ScanCoordinator together. The system picker
 * texts are those of Android 17 (en); other OS versions may word them differently.
 * This is emulator evidence unless it is run on a named physical device (B-01).
 */
@RunWith(AndroidJUnit4::class)
class LabJourneyTest {
    private val instr = InstrumentationRegistry.getInstrumentation()
    private val device = UiDevice.getInstance(instr)
    private val ctx: Context = instr.targetContext
    private val pkg = ctx.packageName
    private val c get() = LabState.coordinator
    private val timeout = 20_000L

    /** Emulator robustness only: dismiss a leftover system share prompt or an ANR dialog. */
    private fun clearSystemDialogs() {
        repeat(3) {
            device.findObject(By.text("Wait"))?.click()
            device.findObject(By.pkg("com.android.systemui").text("Cancel"))?.click()
            device.waitForIdle(1_000)
        }
    }

    @Before fun setUp() {
        clearSystemDialogs()
        ctx.getSharedPreferences("consent", Context.MODE_PRIVATE).edit().clear().commit()
        device.setOrientationNatural()
        device.executeShellCommand("settings put system font_scale 1.0")
        launch()
    }

    @After fun tearDown() {
        clearSystemDialogs()
        device.setOrientationNatural()
        device.executeShellCommand("settings put system font_scale 1.0")
        device.pressBack(); device.pressBack()
    }

    private fun launch() {
        ctx.startActivity(Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
        assertTrue(device.wait(Until.hasObject(By.pkg(pkg).depth(0)), timeout))
    }

    private fun obj(text: String, inPkg: String = pkg): UiObject2 =
        device.wait(Until.findObject(By.pkg(inPkg).text(text)), timeout) ?: error("'$text' not found in $inPkg")

    private fun status(): String = device.wait(Until.findObject(By.pkg(pkg).textContains("State:")), timeout)!!.text

    private fun acceptTerms() { obj("Accept").click(); assertTrue(obj("Start scan (LAB)").isEnabled) }

    private fun openSystemPicker() {
        obj("Start scan (LAB)").click()
        obj("Continue").click()
        assertNotNull("system share prompt", device.wait(Until.findObject(By.pkg("com.android.systemui").textContains("Share your screen")), 30_000))
    }

    private fun shell(cmd: String) = device.executeShellCommand(cmd)

    private fun noAppServiceAndNoProjection() {
        Thread.sleep(500)
        assertFalse("CaptureService still running", shell("dumpsys activity services $pkg").contains("CaptureService"))
        assertTrue(shell("dumpsys media_projection").contains("null"))
    }

    @Test fun termsComeFirstAndDeclineKeepsScanningOff() {
        assertNotNull(obj("Decline"))
        assertNull(device.findObject(By.pkg("com.android.systemui").textContains("Share your screen")))
        assertTrue(shell("dumpsys media_projection").contains("null"))     // nothing captures at launch
        obj("Decline").click()
        assertFalse(obj("Start scan (LAB)").isEnabled)
        assertTrue(status().contains("Terms not accepted"))
        obj("Terms and privacy (draft)").click()                         // legal text stays readable
        obj("Accept").click()
        assertTrue(obj("Start scan (LAB)").isEnabled)
    }

    /** Edge-to-edge regression (found on this emulator): no control may sit under the status bar. */
    @Test fun controlsAreBelowTheStatusBarAndUnclipped() {
        acceptTerms()
        val id = Resources.getSystem().getIdentifier("status_bar_height", "dimen", "android")
        val statusBar = if (id > 0) Resources.getSystem().getDimensionPixelSize(id) else 0
        for (t in listOf("Start scan (LAB)", "Stop / Cancel", "Discard result", "Terms and privacy (draft)")) {
            val b = obj(t)
            assertTrue("$t top ${b.visibleBounds.top} < status bar $statusBar", b.visibleBounds.top >= statusBar)
            assertTrue("$t is clipped", b.visibleBounds.height() > 40)
        }
        val banner = device.findObject(By.pkg(pkg).textContains("LAB build"))
        assertTrue(banner.visibleBounds.top >= statusBar)
    }

    @Test fun notNowOpensNoSystemPrompt() {
        acceptTerms()
        val generation = c.generation
        obj("Start scan (LAB)").click()
        obj("Not now").click()
        assertFalse(device.wait(Until.hasObject(By.pkg("com.android.systemui").textContains("Share your screen")), 2_000))
        assertEquals("no scan may start", generation, c.generation)
    }

    @Test fun pickerCancelFailsClosedWithoutService() {
        acceptTerms()
        openSystemPicker()
        obj("Cancel", "com.android.systemui").click()
        assertTrue(device.wait(Until.hasObject(By.pkg(pkg).textContains("PERMISSION_DENIED")), timeout))
        assertEquals(ScanCoordinator.State.FAILED, c.state)
        assertEquals(ScanCoordinator.Outcome.PERMISSION_DENIED, c.result!!.outcome)
        assertTrue(status().contains("Screen sharing was not allowed or was revoked. Nothing was kept."))
        noAppServiceAndNoProjection()
    }

    @Test fun rotationWhilePickerIsOpenStillFailsClosed() {
        acceptTerms()
        openSystemPicker()
        device.setOrientationLeft()
        // In landscape the Android 17 prompt pushes its buttons off-screen; Back is the user's way out.
        assertNotNull(device.wait(Until.findObject(By.pkg("com.android.systemui").textContains("Share your screen")), timeout))
        device.pressBack()
        device.setOrientationNatural()
        assertTrue(device.wait(Until.hasObject(By.pkg(pkg).textContains("PERMISSION_DENIED")), timeout))
        assertEquals(ScanCoordinator.Outcome.PERMISSION_DENIED, c.result!!.outcome)
        noAppServiceAndNoProjection()
    }

    @Test fun grantWithCaptureDisabledNeverStartsAProjection() {
        assertFalse("this test expects the capture-disabled LAB build", BuildConfig.CAPTURE_ENABLED)
        acceptTerms()
        openSystemPicker()
        obj("Next", "com.android.systemui").click()
        assertNotNull(device.wait(Until.findObject(By.pkg("com.android.systemui").textContains("Choose app")), timeout))
        obj("Clock", "com.android.systemui").click()                     // a harmless app
        val deadline = System.currentTimeMillis() + timeout
        while (c.state != ScanCoordinator.State.CANCELLED && System.currentTimeMillis() < deadline) Thread.sleep(200)
        assertEquals(ScanCoordinator.State.CANCELLED, c.state)
        assertEquals(listOf("IN_APP_CANCEL"), c.result!!.flags)
        assertTrue(shell("dumpsys media_projection").contains("null"))
        launch()
        assertTrue(status().contains("Cancelled. No result was kept."))
    }

    /** P05-T07a: with the largest common font scale every control is still reachable. */
    @Test fun largeFontScaleKeepsEveryControlReachable() {
        device.executeShellCommand("settings put system font_scale 2.0")
        launch()
        acceptTerms()
        for (t in listOf("Start scan (LAB)", "Stop / Cancel", "Discard result", "Terms and privacy (draft)")) {
            val found = device.findObject(By.pkg(pkg).text(t))
                ?: device.findObject(By.scrollable(true))?.let { it.scrollUntil(androidx.test.uiautomator.Direction.DOWN, Until.findObject(By.text(t))) }
            assertNotNull("$t unreachable at font scale 2.0", found)
        }
    }
}
