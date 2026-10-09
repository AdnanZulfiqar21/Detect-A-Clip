package ai.detectaclip.lab

import android.app.Activity
import android.app.AlertDialog
import android.content.Context
import android.content.Intent
import android.media.projection.MediaProjectionConfig
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

/**
 * LAB journey (F03): first use → Terms/Privacy (DRAFT, readable even if declined) → explicit
 * acceptance → HOME/NOT SCANNING. Per scan: local eligibility gate → disclosure (capture Stop
 * and post-capture Cancel) → native picker → coordinator states → result on return.
 * No capture at app open. Results are labelled SYNTHETIC.
 *
 * Status: IMPLEMENTED_NOT_VERIFIED (not compiled, B-09; no device, B-01).
 */
class MainActivity : Activity() {
    private val main = Handler(Looper.getMainLooper())
    private lateinit var status: TextView
    private lateinit var startButton: Button
    private val coordinator get() = LabState.coordinator
    private val consent by lazy { ConsentRecords(PrefsStorage(this)) { System.currentTimeMillis() } }
    private val gate = EligibilityGate { System.currentTimeMillis() }

    private val terms by lazy {
        TermsDocument(
            termsVersion = "0.1-draft",
            locale = "en-GB",
            renderedText = LAB_TERMS_TEXT, // exactly the text shown in the dialog
            governingLanguageVersion = "en-GB-draft",
            disclosureVersion = "lab-disclosure-1",
        )
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        status = TextView(this).apply { textSize = 18f }
        startButton = Button(this).apply { text = "Start scan (LAB)"; setOnClickListener { confirmAndStart() } }
        val cancel = Button(this).apply {
            text = "Stop / Cancel"
            contentDescription = "Stop capture and cancel matching"
            setOnClickListener {
                startService(Intent(this@MainActivity, CaptureService::class.java).setAction(CaptureService.ACTION_STOP))
                coordinator.cancel(CaptureService.now()); render()
            }
        }
        val discard = Button(this).apply { text = "Discard result"; setOnClickListener { coordinator.discard(); render() } }
        val legal = Button(this).apply { text = "Terms and privacy (draft)"; setOnClickListener { showTerms(required = false) } }
        setContentView(ScrollView(this).apply {
            addView(LinearLayout(context).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(48, 96, 48, 48)
                addView(TextView(context).apply { text = "Detect A Clip — LAB build (synthetic only)\nCapture enabled in this build: ${BuildConfig.CAPTURE_ENABLED}" })
                addView(startButton); addView(cancel); addView(discard); addView(legal); addView(status)
            })
        })
        render()
        if (consent.termsStatus(terms) != ConsentRecords.TermsStatus.ACCEPTED_CURRENT) showTerms(required = true)
    }

    override fun onResume() {
        super.onResume()
        coordinator.returnToApp(CaptureService.now())
        render()
    }

    private fun showTerms(required: Boolean) {
        val st = consent.termsStatus(terms)
        val heading = when (st) {
            ConsentRecords.TermsStatus.CHANGED_NEEDS_NEW_NOTICE -> "The terms changed (this includes translation changes). Please review them again."
            else -> ""
        }
        AlertDialog.Builder(this)
            .setTitle("Terms and privacy (DRAFT, lab only)")
            .setMessage(heading + "\n\n" + LAB_TERMS_TEXT)
            .setPositiveButton("Accept") { _, _ -> consent.accept(terms); render() }
            .setNegativeButton(if (required) "Decline" else "Close") { _, _ -> if (required) consent.decline(terms); render() }
            .show()
    }

    private fun eligibility(): EligibilityGate.Decision {
        val labCell = EligibilityGate.Cell(
            cellId = "LAB-${Build.ID}", osBuild = Build.ID, labStatus = "IN_PROGRESS", consumerStatus = "BLOCKED",
            stopPathVerified = false, postCaptureCancelVerified = false, expiresAtEpochMs = null,
        )
        val pack = EligibilityGate.PackState("L0-SYNTH-DUMMY", "UNCALIBRATED", null, timeTrustworthy = true)
        return gate.check(EligibilityGate.BuildPurpose.LAB, consent.scanningAllowed(terms), labCell, Build.ID, pack)
    }

    private fun confirmAndStart() {
        val e = eligibility()
        if (e is EligibilityGate.Decision.Denied) { status.text = "Scanning unavailable: ${e.reason}"; return }
        AlertDialog.Builder(this)
            .setTitle("Before you scan")
            .setMessage(
                "Android will ask you to share your screen or one app. Only frames from this scan are used, " +
                    "in memory on this phone, and nothing leaves the device.\n\n" +
                    "To stop capture: use the system sharing indicator, the notification's Stop action, or Stop here.\n" +
                    "To cancel matching after capture ends: tap Cancel in the notification or return here and tap Stop / Cancel.\n\n" +
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
        // experiment (CAP-A03) is specified in android/CAP-A03_PLAN.md.
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
                val s = coordinator.state
                if (s != ScanCoordinator.State.IDLE && s != ScanCoordinator.State.COMMITTED &&
                    s != ScanCoordinator.State.CANCELLED && s != ScanCoordinator.State.FAILED
                ) main.postDelayed(this, 250)
            }
        }, 250)
    }

    private fun render() {
        startButton.isEnabled = consent.scanningAllowed(terms)
        val r = coordinator.result
        status.text = buildString {
            if (!consent.scanningAllowed(terms)) append("Terms not accepted: scanning is off. Legal pages stay available.\n")
            append("State: ${coordinator.state}\n")
            if (r != null) {
                append("Result: ${when (r.outcome) {
                    ScanCoordinator.Outcome.VERIFIED_MATCH -> "Match"
                    ScanCoordinator.Outcome.POSSIBLE_MATCH -> "Possible match, not confirmed"
                    else -> r.outcome.name
                }}")
                r.candidateWorkId?.let { append(" — $it (SYNTHETIC)") }
                if (r.flags.isNotEmpty()) append("\n${r.flags.joinToString()}")
            } else append("NOT SCANNING / no result")
        }
    }

    /** Terms receipt and purpose choices only; excluded from backup by data-extraction rules. */
    private class PrefsStorage(ctx: Context) : ReceiptStorage {
        private val p = ctx.getSharedPreferences("consent", Context.MODE_PRIVATE)
        override fun read(key: String): String? = p.getString(key, null)
        override fun write(key: String, value: String) { p.edit().putString(key, value).apply() }
        override fun delete(key: String) { p.edit().remove(key).apply() }
    }

    companion object {
        private const val REQ = 41
        private const val LAB_TERMS_TEXT =
            "DRAFT, not legally reviewed, lab use only. Each scan needs your tap and the system's permission. " +
                "Frames are processed in memory on this phone and never saved or sent. Results expire after 15 minutes " +
                "or at your next scan. This build recognises synthetic test clips only. Full drafts: docs/legal/."
    }
}
