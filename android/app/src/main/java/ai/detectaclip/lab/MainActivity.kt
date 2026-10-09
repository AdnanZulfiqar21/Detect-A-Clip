package ai.detectaclip.lab

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.media.projection.MediaProjectionConfig
import android.media.projection.MediaProjectionManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView

/**
 * LAB journey: HOME/NOT SCANNING → Start → disclosure (capture Stop + post-capture Cancel)
 * → native picker → coordinator states → result on return. No capture at app open.
 * Results shown here are labelled SYNTHETIC.
 *
 * Status: IMPLEMENTED_NOT_VERIFIED.
 */
class MainActivity : Activity() {
    private val main = Handler(Looper.getMainLooper())
    private lateinit var status: TextView
    private val coordinator get() = LabState.coordinator

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        status = TextView(this).apply { textSize = 18f }
        val start = Button(this).apply { text = "Start scan (LAB)"; setOnClickListener { confirmAndStart() } }
        val cancel = Button(this).apply {
            text = "Stop / Cancel"
            contentDescription = "Stop capture and cancel matching"
            setOnClickListener {
                startService(Intent(this@MainActivity, CaptureService::class.java).setAction(CaptureService.ACTION_STOP))
                coordinator.cancel(CaptureService.now()); render()
            }
        }
        val discard = Button(this).apply { text = "Discard result"; setOnClickListener { coordinator.discard(); render() } }
        setContentView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 96, 48, 48)
            addView(TextView(context).apply { text = "Detect A Clip — LAB build (synthetic only)\nCapture enabled in this build: ${BuildConfig.CAPTURE_ENABLED}" })
            addView(start); addView(cancel); addView(discard); addView(status)
        })
        render()
    }

    override fun onResume() {
        super.onResume()
        coordinator.returnToApp(CaptureService.now())
        render()
    }

    private fun confirmAndStart() {
        AlertDialog.Builder(this)
            .setTitle("Before you scan")
            .setMessage(
                "Android will ask you to share your screen or one app. Only frames from this scan are used, " +
                    "on this phone, and nothing leaves the device.\n\n" +
                    "To stop capture: use the system sharing indicator, the notification's Stop action, or Stop here.\n" +
                    "To cancel matching after capture ends: return here and tap Stop / Cancel.\n\n" +
                    "This LAB build only recognises synthetic test clips."
            )
            .setPositiveButton("Continue") { _, _ -> launchPicker() }
            .setNegativeButton("Not now", null)
            .show()
    }

    private fun launchPicker() {
        if (!coordinator.start(CaptureService.now())) { render(); return }
        val mpm = getSystemService(MediaProjectionManager::class.java)
        // API 34: user chooses display or a single app. The API 37 source-restriction
        // experiment (CAP-A03, setSourceEnabled) is specified in android/CAP-A03_PLAN.md and
        // is not compiled here until installed-SDK symbols are verified (P00-T02).
        val intent = mpm.createScreenCaptureIntent(MediaProjectionConfig.createConfigForUserChoice())
        @Suppress("DEPRECATION")
        startActivityForResult(intent, REQ)
        tickLoop() // UI refresh + permission deadline; capture deadlines run in CaptureService
    }

    @Deprecated("Activity result API kept minimal for the lab build")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != REQ) return
        CaptureService.start(this, resultCode, data) // fresh intent per session; never stored
        render()
    }

    private fun tickLoop() {
        main.postDelayed(object : Runnable {
            override fun run() {
                coordinator.tick(CaptureService.now())
                render()
                if (coordinator.state != ScanCoordinator.State.IDLE &&
                    coordinator.state != ScanCoordinator.State.COMMITTED &&
                    coordinator.state != ScanCoordinator.State.CANCELLED &&
                    coordinator.state != ScanCoordinator.State.FAILED
                ) main.postDelayed(this, 250)
            }
        }, 250)
    }

    private fun render() {
        val r = coordinator.result
        status.text = buildString {
            append("State: ${coordinator.state}\n")
            if (r != null) {
                append("Result: ${r.outcome}")
                r.candidateWorkId?.let { append(" — $it (SYNTHETIC)") }
                if (r.flags.isNotEmpty()) append("\n${r.flags.joinToString()}")
            } else append("NOT SCANNING / no result")
        }
    }

    companion object { private const val REQ = 41 }
}
