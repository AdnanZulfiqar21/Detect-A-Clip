package ai.detectaclip.lab

import android.app.Activity
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.ServiceInfo
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.SystemClock
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.Future

/**
 * mediaProjection foreground service for the LAB build: a thin Android adapter around
 * [CaptureLifecycle], which holds all lifecycle decisions and is JVM-tested.
 *
 * - Frames: every Image is closed immediately unless the lifecycle accepts it; accepted
 *   images are closed right after the in-memory dummy work. No file output, no network.
 * - BuildConfig.CAPTURE_ENABLED=false (DATA-L00 Part A build): getMediaProjection() is never
 *   called; the scan ends CANCELLED.
 * - Screen off → lock event; MediaProjection.Callback.onStop → lifecycle (cause attribution
 *   is the coordinator's adapter contract, default fail closed).
 * - After capture closes the notification switches to "Matching… Cancel" while bounded
 *   post-capture work runs. Whether the OS keeps a mediaProjection-type FGS alive after the
 *   projection stopped is a CAP-A04 device question; this code does not assume it.
 *
 * Status: compiled with AGP and lint-clean; no device test (B-01).
 */
class CaptureService : Service() {

    private val main = Handler(Looper.getMainLooper())
    private var display: VirtualDisplay? = null
    private var reader: ImageReader? = null
    private val worker: ExecutorService = Executors.newSingleThreadExecutor()
    private var screenOffRegistered = false

    private val lifecycle: CaptureLifecycle by lazy {
        // DIAGNOSTIC mode only (CAP-A04): no recognizer factory is passed, so frames are counted,
        // never decoded. The recognition path (CaptureLifecycle RECOGNITION + RecognitionSession)
        // is JVM-tested with injected frames; wiring it to real capture stays closed until the
        // capture and consumer gates have their evidence (B-01, CTRL-G00).
        CaptureLifecycle(LabState.coordinator, { now() }, ExecutorCompute(worker, DUMMY_COMPUTE_MS), postToMain = { block -> main.post(block) })
    }

    private val tick = object : Runnable {
        override fun run() {
            val wasLive = lifecycle.captureLive
            lifecycle.tick()
            if (wasLive && !lifecycle.captureLive && !lifecycle.terminal) updateNotification(postCapture = true)
            if (lifecycle.terminal) { releaseSurfaces(); stopSelf(); return }
            main.postDelayed(this, TICK_MS)
        }
    }

    private val screenOff = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (intent?.action == Intent.ACTION_SCREEN_OFF) { lifecycle.screenOff(); releaseSurfaces() }
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            lifecycle.userCancel()
            releaseSurfaces()
            stopSelf()
            return START_NOT_STICKY
        }
        startForeground(NOTIFICATION_ID, buildNotification(postCapture = false), ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION)
        registerReceiver(screenOff, IntentFilter(Intent.ACTION_SCREEN_OFF))
        screenOffRegistered = true

        val c = LabState.coordinator
        val resultCode = intent?.getIntExtra(EXTRA_RESULT_CODE, Activity.RESULT_CANCELED) ?: Activity.RESULT_CANCELED
        val data: Intent? = intent?.getParcelableExtra(EXTRA_DATA, Intent::class.java)
        if (resultCode != Activity.RESULT_OK || data == null) {
            c.permissionDenied(now()); stopSelf(); return START_NOT_STICKY
        }
        if (!c.permissionGranted(now())) { stopSelf(); return START_NOT_STICKY }
        if (!BuildConfig.CAPTURE_ENABLED) {
            c.cancel(now()); stopSelf(); return START_NOT_STICKY
        }

        val mpm = getSystemService(MediaProjectionManager::class.java)
        val mp = mpm.getMediaProjection(resultCode, data)
        if (mp == null) { c.permissionDenied(now()); stopSelf(); return START_NOT_STICKY }
        mp.registerCallback(object : MediaProjection.Callback() {
            override fun onStop() { lifecycle.onProjectionStopped(); releaseSurfaces() }
            override fun onCapturedContentResize(width: Int, height: Int) { /* recorded by P01-T06 instrumentation */ }
            override fun onCapturedContentVisibilityChanged(isVisible: Boolean) { /* recorded; never a privacy boundary */ }
        }, main)
        val attached = lifecycle.attach(object : CaptureLifecycle.ProjectionHandle {
            override fun stop() = mp.stop()
            override fun release() = releaseSurfaces()
        })
        if (!attached) { stopSelf(); return START_NOT_STICKY }

        val r = ImageReader.newInstance(W, H, PixelFormat.RGBA_8888, 3)
        reader = r
        r.setOnImageAvailableListener({ rd ->
            val img = rd.acquireLatestImage() ?: return@setOnImageAvailableListener
            if (!lifecycle.onFrame()) { img.close(); return@setOnImageAvailableListener }
            try {
                img.planes[0].buffer.get(0) // dummy bounded in-memory work (P01-T05b)
            } finally {
                img.close()
                lifecycle.frameDone()
            }
        }, main)
        display = mp.createVirtualDisplay("dac-lab", W, H, resources.displayMetrics.densityDpi,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR, r.surface, null, main)
        main.postDelayed(tick, TICK_MS)
        return START_NOT_STICKY
    }

    private fun releaseSurfaces() {
        reader?.setOnImageAvailableListener(null, null)
        display?.release(); display = null
        reader?.close(); reader = null
    }

    override fun onDestroy() {
        main.removeCallbacks(tick)
        lifecycle.teardownCapture()
        releaseSurfaces()
        if (screenOffRegistered) { unregisterReceiver(screenOff); screenOffRegistered = false }
        worker.shutdownNow()
        super.onDestroy()
    }

    private fun updateNotification(postCapture: Boolean) {
        getSystemService(NotificationManager::class.java).notify(NOTIFICATION_ID, buildNotification(postCapture))
    }

    private fun buildNotification(postCapture: Boolean): Notification {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(CHANNEL, getString(R.string.channel_name), NotificationManager.IMPORTANCE_LOW))
        val stop = PendingIntent.getService(this, 0, Intent(this, CaptureService::class.java).setAction(ACTION_STOP), PendingIntent.FLAG_IMMUTABLE)
        val title = getString(if (postCapture) R.string.notif_matching_title else R.string.notif_capturing_title)
        val text = getString(if (postCapture) R.string.notif_matching_text else R.string.notif_capturing_text)
        return Notification.Builder(this, CHANNEL)
            .setContentTitle(title)
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_media_pause)
            .setOngoing(true)
            .addAction(Notification.Action.Builder(null, getString(if (postCapture) R.string.action_cancel else R.string.action_stop), stop).build())
            .build()
    }

    /** Post-capture work on a worker thread; cancel() interrupts it. [dummyMs] > 0 adds the
     *  CAP-A04 measurement delay before the work and is used in DIAGNOSTIC mode only. */
    private class ExecutorCompute(private val ex: ExecutorService, private val dummyMs: Long) : CaptureLifecycle.ComputeRunner {
        override fun submit(
            work: (isCancelled: () -> Boolean) -> CaptureLifecycle.WorkOutcome?,
            onDone: (CaptureLifecycle.WorkOutcome?) -> Unit,
        ): CaptureLifecycle.Cancellable {
            var future: Future<*>? = null
            future = ex.submit {
                val end = SystemClock.elapsedRealtime() + dummyMs
                val cancelled = { Thread.currentThread().isInterrupted || future?.isCancelled == true }
                while (SystemClock.elapsedRealtime() < end && !cancelled()) { Thread.onSpinWait() }
                onDone(if (cancelled()) null else work(cancelled))
            }
            return object : CaptureLifecycle.Cancellable { override fun cancel() { future?.cancel(true) } }
        }
    }

    companion object {
        const val EXTRA_RESULT_CODE = "resultCode"
        const val EXTRA_DATA = "data"
        const val ACTION_STOP = "ai.detectaclip.lab.STOP"
        private const val CHANNEL = "scan"
        private const val NOTIFICATION_ID = 1
        private const val TICK_MS = 250L
        private const val DUMMY_COMPUTE_MS = 6_000L   // CAP-A04 dummy computation
        private const val W = 640
        private const val H = 360
        fun now(): Long = SystemClock.elapsedRealtime()
        fun start(ctx: Context, resultCode: Int, data: Intent?) {
            ctx.startForegroundService(Intent(ctx, CaptureService::class.java).putExtra(EXTRA_RESULT_CODE, resultCode).putExtra(EXTRA_DATA, data))
        }
    }
}

/** Process-wide holder; memory only. Process death loses everything by design (D08). */
object LabState {
    val coordinator = ScanCoordinator()
}
