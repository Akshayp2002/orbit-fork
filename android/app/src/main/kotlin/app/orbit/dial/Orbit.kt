package app.orbit.dial

import android.content.Context
import app.orbit.dial.core.Clock
import app.orbit.dial.core.DialEvent
import app.orbit.dial.core.RotationControl
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * In-process hub. One process, so services talk through this object:
 *  - every dial event (media service, hold trampoline, test buttons) -> [events]
 *  - the accessibility service owns the Engine and collects [events]
 *  - the media service owns the VolumeDial and plugs it in as [rotation]
 */
object Orbit {
    private val _events = MutableSharedFlow<DialEvent>(extraBufferCapacity = 64)
    val events: SharedFlow<DialEvent> = _events

    fun emit(ev: DialEvent) {
        log("in  ${ev.kind}${if (ev.delta != 0) " ${ev.delta}" else ""} <${ev.source}>")
        _events.tryEmit(ev)
    }

    @Volatile var a11y: OrbitAccessibilityService? = null
    @Volatile var media: OrbitMediaService? = null

    /** Engine-facing rotation control; remembers the request until the media service attaches. */
    val rotation = RotationProxy()

    class RotationProxy : RotationControl {
        private var passthrough = true
        private var duck: Float? = null
        override fun setPassthrough(on: Boolean) { passthrough = on; media?.dial?.setPassthrough(on) }
        override fun setDuck(factor: Float?) { duck = factor; media?.dial?.setDuck(factor) }
        override fun level(): Float? = media?.dial?.level()
        fun replayInto(svc: OrbitMediaService) { svc.dial.setPassthrough(passthrough); svc.dial.setDuck(duck) }
    }

    /** Phone volume keys pressed recently: those volume changes are not the dial. */
    @Volatile var lastPhoneVolumeKey = 0L
    fun phoneKeyRecently() = Clock.now() - lastPhoneVolumeKey < 600

    // ---- small diagnostic log for the setup screen
    val logLines = MutableStateFlow<List<String>>(emptyList())
    private val fmt = SimpleDateFormat("HH:mm:ss.SSS", Locale.US)
    fun log(line: String) {
        android.util.Log.d("Orbit", line)
        logLines.value = (logLines.value + "${fmt.format(Date())}  $line").takeLast(60)
    }

    // ---- settings
    private const val PREFS = "orbit"
    fun prefs(ctx: Context) = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
    fun requireBluetooth(ctx: Context) = prefs(ctx).getBoolean("require_bt", true)
    fun setRequireBluetooth(ctx: Context, on: Boolean) = prefs(ctx).edit().putBoolean("require_bt", on).apply()
}
