package ai.detectaclip.lab

import android.app.Activity
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
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
import java.util.concurrent.Executors

/**
 * mediaProjection foreground service for the LAB build (P01-T01/T02/T05/T06).
 *
 * - Holds no frames after use: every Image is closed immediately unless the selector takes
 *   it, and taken images are closed right after the (dummy, in-memory) work.
 * - No file output, no network (manifest has no INTERNET).
 * - Capture itself is gated by BuildConfig.CAPTURE_ENABLED, which is false for the Part A
 *   build. With it false, the service starts, shows its notification, and stops without
 *   ever calling getMediaProjection().
 * - Every OS stop callback is reported to the coordinator as StopCause.UNKNOWN unless we
 *   are inside our own stop() call; even then AdapterContract decides whether that is
 *   attributable (default: not attributable → fail closed).
 *
 * Status: IMPLEMENTED_NOT_VERIFIED. Not compiled; no device test exists (B-01, B-09).
 */
class CaptureService : Service() {

    private val main = Handler(Looper.getMainLooper())
    private var projection: MediaProjection? = null
    private var display: VirtualDisplay? = null
    private var reader: ImageReader? = null
    private var selector: FrameSelector? = null
    private var insideOwnStop = false
    private var projectionStopped = true
    private val worker = Executors.newSingleThreadExecutor()
    private val tick = object : Runnable {
        override fun run() {
            val c = coordinator
            c.tick(now())
            if (c.state == ScanCoordinator.State.POST_CAPTURE && !projectionStopped) closeNormallyAndCompute()
            if (c.state == ScanCoordinator.State.CANCELLED || c.state == ScanCoordinator.State.FAILED || c.state == ScanCoordinator.State.COMMITTED) {
                teardown(); stopSelf(); return
            }
            main.postDelayed(this, TICK_MS)
        }
    }

    private val coordinator get() = LabState.coordinator

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                // Observed user Stop: cancel first (generation invalidated), then release capture.
                coordinator.cancel(now())
                teardown()
                stopSelf()
                return START_NOT_STICKY
            }
        }
        startForeground(NOTIFICATION_ID, buildNotification(), ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION)

        val resultCode = intent?.getIntExtra(EXTRA_RESULT_CODE, Activity.RESULT_CANCELED) ?: Activity.RESULT_CANCELED
        @Suppress("DEPRECATION")
        val data: Intent? = intent?.getParcelableExtra(EXTRA_DATA)
        if (resultCode != Activity.RESULT_OK || data == null) {
            coordinator.permissionDenied(now())
            stopSelf()
            return START_NOT_STICKY
        }
        if (!coordinator.permissionGranted(now())) { stopSelf(); return START_NOT_STICKY }

        if (!BuildConfig.CAPTURE_ENABLED) {
            // DATA-L00 Part A build: never obtain a projection.
            coordinator.cancel(now())
            stopSelf()
            return START_NOT_STICKY
        }

        val mpm = getSystemService(MediaProjectionManager::class.java)
        val mp = mpm.getMediaProjection(resultCode, data) ?: run { coordinator.permissionDenied(now()); stopSelf(); return START_NOT_STICKY }
        projection = mp
        projectionStopped = false
        mp.registerCallback(object : MediaProjection.Callback() {
            override fun onStop() {
                projectionStopped = true
                coordinator.captureStopped(now(), if (insideOwnStop) ScanCoordinator.StopCause.APP_REQUESTED_ACK else ScanCoordinator.StopCause.UNKNOWN)
                if (!insideOwnStop) { teardown(); stopSelf() }
            }
            override fun onCapturedContentResize(width: Int, height: Int) { /* logged by P01-T06 instrumentation */ }
            override fun onCapturedContentVisibilityChanged(isVisible: Boolean) { /* recorded, never a privacy boundary */ }
        }, main)

        val w = 640; val h = 360
        val r = ImageReader.newInstance(w, h, PixelFormat.RGBA_8888, 3)
        reader = r
        selector = FrameSelector()
        r.setOnImageAvailableListener({ rd ->
            val img = rd.acquireLatestImage() ?: return@setOnImageAvailableListener
            val sel = selector
            val t = now()
            // LAB simplification: the first delivered frame marks the target as ready.
            if (coordinator.state == ScanCoordinator.State.AWAITING_TARGET) coordinator.targetReady(t)
            if (sel == null || !coordinator.frameAllowed(t) || !sel.offer(t)) { img.close(); return@setOnImageAvailableListener }
            try {
                // Dummy bounded local work (P01-T05b). Real descriptors come with P04-T08.
                img.planes[0].buffer.get(0)
            } finally {
                img.close()
                sel.release()
            }
        }, main)
        display = mp.createVirtualDisplay("dac-lab", w, h, resources.displayMetrics.densityDpi,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR, r.surface, null, main)
        main.postDelayed(tick, TICK_MS) // deadlines + sampling close, independent of the activity
        return START_NOT_STICKY
    }

    /**
     * Sampling window ended (coordinator already moved to POST_CAPTURE via tick): release
     * capture through the real API, then run bounded post-capture work (CAP-A04 uses a 6 s
     * dummy computation). The worker result carries the generation it started with, so a
     * cancel/lock/revoke that lands first makes it stale.
     */
    private fun closeNormallyAndCompute() {
        insideOwnStop = true
        try { projection?.stop() } finally { insideOwnStop = false }
        projectionStopped = true // stop() issued; onStop() may arrive later on the main looper
        teardown()
        val gen = coordinator.generation
        worker.execute {
            val end = SystemClock.elapsedRealtime() + DUMMY_COMPUTE_MS
            var x = 0L
            while (SystemClock.elapsedRealtime() < end) { x += 1 }
            main.post {
                coordinator.workerResult(now(), gen, ScanCoordinator.Outcome.NO_CONFIDENT_MATCH, null, listOf("LAB_DUMMY_COMPUTE"))
            }
        }
    }

    /** Idempotent release of every capture resource. Stops the projection if still live. */
    private fun teardown() {
        selector?.close()
        reader?.setOnImageAvailableListener(null, null)
        display?.release(); display = null
        reader?.close(); reader = null
        val p = projection
        projection = null
        if (p != null && !projectionStopped) {
            projectionStopped = true
            p.stop() // onStop() will arrive; the coordinator is already terminal or acknowledges it
        }
    }

    override fun onDestroy() {
        main.removeCallbacks(tick)
        teardown()
        worker.shutdownNow()
        super.onDestroy()
    }

    private fun buildNotification(): Notification {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(CHANNEL, "Scan in progress", NotificationManager.IMPORTANCE_LOW))
        val stop = PendingIntent.getService(this, 0, Intent(this, CaptureService::class.java).setAction(ACTION_STOP), PendingIntent.FLAG_IMMUTABLE)
        return Notification.Builder(this, CHANNEL)
            .setContentTitle("Detect A Clip LAB is capturing your screen")
            .setContentText("Synthetic lab test. Tap Stop to end capture and cancel matching.")
            .setSmallIcon(android.R.drawable.ic_media_pause)
            .setOngoing(true)
            .addAction(Notification.Action.Builder(null, "Stop", stop).build())
            .build()
    }

    companion object {
        const val EXTRA_RESULT_CODE = "resultCode"
        const val EXTRA_DATA = "data"
        const val ACTION_STOP = "ai.detectaclip.lab.STOP"
        private const val CHANNEL = "scan"
        private const val NOTIFICATION_ID = 1
        private const val TICK_MS = 250L
        private const val DUMMY_COMPUTE_MS = 6_000L
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
