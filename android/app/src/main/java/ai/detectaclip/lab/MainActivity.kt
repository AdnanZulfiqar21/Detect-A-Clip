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
 * Status: compiled with AGP and lint-clean; no device test (B-01).
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
            renderedText = getString(R.string.lab_terms_text), // exactly the text shown in the dialog
            governingLanguageVersion = "en-GB-draft",
            disclosureVersion = "lab-disclosure-1",
        )
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        status = TextView(this).apply { textSize = 18f }
        startButton = Button(this).apply { text = getString(R.string.start_scan); setOnClickListener { confirmAndStart() } }
        val cancel = Button(this).apply {
            text = getString(R.string.stop_cancel)
            contentDescription = getString(R.string.stop_cancel_description)
            setOnClickListener {
                startService(Intent(this@MainActivity, CaptureService::class.java).setAction(CaptureService.ACTION_STOP))
                coordinator.cancel(CaptureService.now()); render()
            }
        }
        val discard = Button(this).apply { text = getString(R.string.discard_result); setOnClickListener { coordinator.discard(); render() } }
        val legal = Button(this).apply { text = getString(R.string.terms_button); setOnClickListener { showTerms(required = false) } }
        setContentView(ScrollView(this).apply {
            addView(LinearLayout(context).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(48, 96, 48, 48)
                addView(TextView(context).apply { text = getString(R.string.build_banner, BuildConfig.CAPTURE_ENABLED.toString()) })
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
            ConsentRecords.TermsStatus.CHANGED_NEEDS_NEW_NOTICE -> getString(R.string.terms_changed)
            else -> ""
        }
        AlertDialog.Builder(this)
            .setTitle(R.string.terms_title)
            .setMessage(heading + "\n\n" + terms.renderedText)
            .setPositiveButton(R.string.accept) { _, _ -> consent.accept(terms); render() }
            .setNegativeButton(if (required) R.string.decline else R.string.close) { _, _ -> if (required) consent.decline(terms); render() }
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
        if (e is EligibilityGate.Decision.Denied) { status.text = getString(R.string.scanning_unavailable, e.reason); return }
        AlertDialog.Builder(this)
            .setTitle(R.string.before_scan_title)
            .setMessage(R.string.before_scan_body)
            .setPositiveButton(R.string.continue_) { _, _ -> launchPicker() }
            .setNegativeButton(R.string.not_now, null)
            .show()
    }

    private fun launchPicker() {
        if (!coordinator.start(CaptureService.now())) { render(); return }
        val mpm = getSystemService(MediaProjectionManager::class.java)
        val intent = mpm.createScreenCaptureIntent(projectionConfig())
        @Suppress("DEPRECATION")
        startActivityForResult(intent, REQ)
        tickLoop() // UI refresh + permission deadline; capture deadlines run in CaptureService
    }

    /**
     * CAP-A03: API 34 user-choice picker by default. With dac.sourceMode=app_only on API 37+,
     * the display source is disabled and the app source enabled, so the picker should not
     * offer full-display sharing. Whether a user can still escape to the display is exactly
     * what CAP-A03 must test on devices; this code is not evidence of enforcement.
     */
    private fun projectionConfig(): MediaProjectionConfig {
        if (BuildConfig.SOURCE_MODE == "app_only" && Build.VERSION.SDK_INT >= 37) {
            return MediaProjectionConfig.Builder()
                .setSourceEnabled(MediaProjectionConfig.PROJECTION_SOURCE_DISPLAY, false)
                .setSourceEnabled(MediaProjectionConfig.PROJECTION_SOURCE_APP, true)
                .setInitiallySelectedSource(MediaProjectionConfig.PROJECTION_SOURCE_APP)
                .build()
        }
        return MediaProjectionConfig.createConfigForUserChoice()
    }

    @Deprecated("Activity result API kept minimal for the lab build")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != REQ) return
        // Denied or empty consent: PERMISSION_DENIED, and the mediaProjection service is never started.
        if (CaptureStartPolicy.onPickerResult(coordinator, CaptureService.now(), resultCode == RESULT_OK, data != null)) {
            CaptureService.start(this, resultCode, data) // fresh intent per session; never stored
        }
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
        val lines = ArrayList<String>()
        if (!consent.scanningAllowed(terms)) lines += getString(R.string.terms_not_accepted)
        lines += getString(R.string.state_line, coordinator.state.name)
        if (r != null) {
            // Honest, outcome-specific text (P05-T04b); identical wording on iOS (LabFlow.outcomeText).
            val outcome = getString(when (r.outcome) {
                ScanCoordinator.Outcome.VERIFIED_MATCH -> R.string.result_verified_match
                ScanCoordinator.Outcome.POSSIBLE_MATCH -> R.string.result_possible_match
                ScanCoordinator.Outcome.NO_CONFIDENT_MATCH -> R.string.result_no_confident_match
                ScanCoordinator.Outcome.INSUFFICIENT_SIGNAL -> R.string.result_insufficient_signal
                ScanCoordinator.Outcome.UNSUPPORTED_CAPTURE -> R.string.result_unsupported_capture
                ScanCoordinator.Outcome.PERMISSION_DENIED -> R.string.result_permission_denied
                ScanCoordinator.Outcome.CANCELLED -> R.string.result_cancelled
                ScanCoordinator.Outcome.ERROR -> R.string.result_error
            })
            val shown = r.candidateWorkId?.let { getString(R.string.synthetic_suffix, "$outcome — $it") } ?: outcome
            lines += getString(R.string.result_line, shown)
            if (r.flags.isNotEmpty()) lines += getString(R.string.result_details, r.flags.joinToString())
        } else lines += getString(R.string.no_result)
        status.text = lines.joinToString("\n")
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
    }
}
