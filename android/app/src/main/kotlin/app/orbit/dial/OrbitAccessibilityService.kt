package app.orbit.dial

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.ComponentName
import android.content.Intent
import android.graphics.Path
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.media.AudioManager
import android.media.session.MediaController
import android.media.session.MediaSessionManager
import android.media.session.PlaybackState
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.VibrationEffect
import android.os.Vibrator
import android.provider.Settings
import android.view.KeyEvent
import android.view.accessibility.AccessibilityEvent
import app.orbit.dial.core.Actions
import app.orbit.dial.core.App
import app.orbit.dial.core.Clock
import app.orbit.dial.core.Engine
import app.orbit.dial.core.defaultTools
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlin.math.abs
import kotlin.math.min
import kotlin.math.sqrt

/**
 * Centre of the Android app: started (and restarted after reboot) by the system
 * once the user enables it. Owns the Engine and the overlay, and performs every
 * action: scroll gestures, magnification, global actions, app launches.
 */
class OrbitAccessibilityService : AccessibilityService(), Actions {
    private val main = Handler(Looper.getMainLooper())
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private lateinit var overlay: OverlayController
    lateinit var engine: Engine
        private set
    private val recent = ArrayDeque<String>()       // most recent first

    private val ticker = object : Runnable {
        override fun run() { engine.tick(); main.postDelayed(this, 50) }
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        Orbit.a11y = this
        overlay = OverlayController(this)
        engine = Engine(this, overlay, Orbit.rotation, defaultTools())
        scope.launch { Orbit.events.collect { ev -> engine.handle(ev) } }
        main.post(ticker)
        if (BuildConfig.DEBUG) registerDebugInjector()
        OrbitMediaService.start(this)
        Orbit.log("accessibility service connected")
    }

    /** Debug builds only: inject dial events without bringing any Orbit UI forward.
     *  adb shell am broadcast -a app.orbit.dial.DEBUG_EMIT --es e rotate:2 */
    private var debugRx: android.content.BroadcastReceiver? = null
    private fun registerDebugInjector() {
        debugRx = object : android.content.BroadcastReceiver() {
            override fun onReceive(c: android.content.Context, i: Intent) {
                val spec = i.getStringExtra("e") ?: return
                val parts = spec.split(":")
                runCatching {
                    Orbit.emit(app.orbit.dial.core.DialEvent(app.orbit.dial.core.Kind.valueOf(parts[0].uppercase()),
                        parts.getOrNull(1)?.toIntOrNull() ?: 0, "debug"))
                }
            }
        }
        androidx.core.content.ContextCompat.registerReceiver(this, debugRx, android.content.IntentFilter("app.orbit.dial.DEBUG_EMIT"),
            androidx.core.content.ContextCompat.RECEIVER_EXPORTED)
    }

    override fun onDestroy() {
        debugRx?.let { runCatching { unregisterReceiver(it) } }
        main.removeCallbacks(ticker)
        scope.cancel()
        if (::overlay.isInitialized) overlay.destroy()
        if (Orbit.a11y === this) Orbit.a11y = null
        super.onDestroy()
    }

    override fun onInterrupt() {}

    override fun onAccessibilityEvent(e: AccessibilityEvent) {
        if (e.eventType != AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) return
        val pkg = e.packageName?.toString() ?: return
        if (pkg == packageName || pkg == "com.android.systemui" || packageManager.getLaunchIntentForPackage(pkg) == null) return
        recent.remove(pkg); recent.addFirst(pkg)
        while (recent.size > 12) recent.removeLast()
    }

    /** Phone volume keys: let them through, but mark them so the volume change isn't read as the dial. */
    override fun onKeyEvent(event: KeyEvent): Boolean {
        if (event.keyCode == KeyEvent.KEYCODE_VOLUME_UP || event.keyCode == KeyEvent.KEYCODE_VOLUME_DOWN) {
            Orbit.lastPhoneVolumeKey = Clock.now()
        }
        return false
    }

    // ================================================================ Actions
    // ---- scroll: one continuous virtual finger; each click pushes it further, it lifts when idle
    private var stroke: GestureDescription.StrokeDescription? = null
    private var fingerY = 0f
    private val pending = ArrayDeque<Float>()
    private var dispatching = false
    private val lift = Runnable { endStroke() }

    override fun scrollBy(px: Float) {
        pending.addLast(px)
        main.removeCallbacks(lift)
        main.postDelayed(lift, 420)
        if (!dispatching) nextSegment()
    }

    private fun nextSegment() {
        val px = pending.removeFirstOrNull() ?: run { dispatching = false; return }
        dispatching = true
        val dm = resources.displayMetrics
        val x = dm.widthPixels / 2f
        val top = dm.heightPixels * 0.2f
        val bottom = dm.heightPixels * 0.8f
        var from = if (stroke == null) (if (px > 0) bottom else top).also { fingerY = it } else fingerY
        var to = (from - px).coerceIn(top, bottom)              // scroll down = finger moves up
        if (abs(to - from) < 2f) {                               // ran out of room: lift, start over
            endStroke(); from = if (px > 0) bottom else top; fingerY = from
            to = (from - px).coerceIn(top, bottom)
        }
        val path = Path().apply { moveTo(x, from); lineTo(x, to) }
        val dur = (abs(to - from) / 2.2f).toLong().coerceIn(40, 300)   // slow enough not to fling
        val s = stroke?.continueStroke(path, 0, dur, true) ?: GestureDescription.StrokeDescription(path, 0, dur, true)
        stroke = s; fingerY = to
        val ok = dispatchGesture(GestureDescription.Builder().addStroke(s).build(), object : GestureResultCallback() {
            override fun onCompleted(g: GestureDescription?) { nextSegment() }
            override fun onCancelled(g: GestureDescription?) { stroke = null; nextSegment() }
        }, main)
        if (!ok) { stroke = null; dispatching = false }
    }

    private fun endStroke() {
        val s = stroke ?: return
        stroke = null
        if (dispatching) return                                  // the queue will lift on its own
        val p = Path().apply { moveTo(resources.displayMetrics.widthPixels / 2f, fingerY); lineTo(resources.displayMetrics.widthPixels / 2f, fingerY + 1) }
        dispatchGesture(GestureDescription.Builder().addStroke(s.continueStroke(p, 0, 120, false)).build(), null, main)
    }

    // ---- zoom
    override fun zoom(scale: Float): Float {
        val mc = magnificationController
        val dm = resources.displayMetrics
        if (scale <= 1.001f) mc.reset(true) else {
            mc.setScale(scale, true)
            mc.setCenter(dm.widthPixels / 2f, dm.heightPixels / 2f, true)
        }
        return scale
    }
    override fun zoomScale(): Float = magnificationController.scale

    // ---- brightness (perceptual: slider position = sqrt of the 0..255 value)
    override fun brightness(): Float? {
        if (!Settings.System.canWrite(this)) return null
        val v = Settings.System.getInt(contentResolver, Settings.System.SCREEN_BRIGHTNESS, 128)
        return sqrt(v / 255f)
    }
    override fun setBrightness(v: Float) {
        if (!Settings.System.canWrite(this)) return
        Settings.System.putInt(contentResolver, Settings.System.SCREEN_BRIGHTNESS_MODE, Settings.System.SCREEN_BRIGHTNESS_MODE_MANUAL)
        Settings.System.putInt(contentResolver, Settings.System.SCREEN_BRIGHTNESS, (v * v * 255).toInt().coerceIn(1, 255))
    }

    // ---- torch
    private val cams by lazy { getSystemService(CameraManager::class.java) }
    private val flashId by lazy {
        runCatching {
            cams.cameraIdList.firstOrNull { cams.getCameraCharacteristics(it).get(CameraCharacteristics.FLASH_INFO_AVAILABLE) == true }
        }.getOrNull()
    }
    override fun torchAvailable() = flashId != null
    override fun torch(on: Boolean, level: Float) {
        val id = flashId ?: return
        runCatching {
            if (on && Build.VERSION.SDK_INT >= 33) {
                val max = cams.getCameraCharacteristics(id).get(CameraCharacteristics.FLASH_INFO_STRENGTH_MAXIMUM_LEVEL) ?: 1
                if (max > 1) { cams.turnOnTorchWithStrengthLevel(id, (level * max).toInt().coerceIn(1, max)); return }
            }
            cams.setTorchMode(id, on)
        }
    }

    // ---- apps
    override fun recentApps(): List<App> = recent.drop(1).ifEmpty { recent.toList() }.map { pkg ->
        App(pkg, runCatching { packageManager.getApplicationLabel(packageManager.getApplicationInfo(pkg, 0)).toString() }.getOrDefault(pkg))
    }
    override fun openApp(pkg: String) {
        packageManager.getLaunchIntentForPackage(pkg)?.let { startActivity(it.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
    }
    override fun launch(pkg: String) {
        val i = packageManager.getLaunchIntentForPackage(pkg)
            ?: Intent(Intent.ACTION_VIEW, Uri.parse("https://play.google.com/store/apps/details?id=$pkg"))
        runCatching { startActivity(i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
    }

    override fun global(action: String) {
        val id = when (action) {
            "back" -> GLOBAL_ACTION_BACK
            "home" -> GLOBAL_ACTION_HOME
            "recents" -> GLOBAL_ACTION_RECENTS
            "notifications" -> GLOBAL_ACTION_NOTIFICATIONS
            "quick_settings" -> GLOBAL_ACTION_QUICK_SETTINGS
            "screenshot" -> if (Build.VERSION.SDK_INT >= 28) GLOBAL_ACTION_TAKE_SCREENSHOT else return
            "lock" -> if (Build.VERSION.SDK_INT >= 28) GLOBAL_ACTION_LOCK_SCREEN else return
            else -> return
        }
        // let the wheel's close animation clear the screen before a screenshot
        main.postDelayed({ performGlobalAction(id) }, if (action == "screenshot") 450 else 0)
    }

    // ---- media: to the real player (we own the media buttons, so we can't just dispatch keys)
    override fun media(command: String) {
        val c = realPlayer() ?: run { Orbit.log("media:$command - no player (enable notification access)"); return }
        val tc = c.transportControls
        when (command) {
            "play_pause" -> if (c.playbackState?.state == PlaybackState.STATE_PLAYING) tc.pause() else tc.play()
            "next" -> tc.skipToNext()
            "previous" -> tc.skipToPrevious()
        }
        Orbit.log("media:$command -> ${c.packageName}")
        main.postDelayed({ Orbit.media?.reassert() }, 700)    // the player takes the buttons when it starts
    }

    private fun realPlayer(): MediaController? = runCatching {
        val msm = getSystemService(MediaSessionManager::class.java)
        val list = msm.getActiveSessions(ComponentName(this, OrbitNotificationListener::class.java))
            .filter { it.packageName != packageName }
        list.firstOrNull { it.playbackState?.state == PlaybackState.STATE_PLAYING } ?: list.firstOrNull()
    }.getOrNull()

    override fun volume(): Float? = Orbit.rotation.level() ?: getSystemService(AudioManager::class.java).let {
        it.getStreamVolume(AudioManager.STREAM_MUSIC).toFloat() / it.getStreamMaxVolume(AudioManager.STREAM_MUSIC)
    }

    private val vibrator by lazy { getSystemService(Vibrator::class.java) }
    override fun haptic() {
        runCatching {
            if (Build.VERSION.SDK_INT >= 29) vibrator.vibrate(VibrationEffect.createPredefined(VibrationEffect.EFFECT_TICK))
            else vibrator.vibrate(VibrationEffect.createOneShot(8, 60))
        }
    }

}
