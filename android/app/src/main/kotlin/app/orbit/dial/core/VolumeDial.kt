package app.orbit.dial.core

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/**
 * Turns an output-volume level stream into dial clicks. Kotlin port of
 * orbit/core/volume_dial.py — same rules, learned on the real buds:
 *
 *  - the click size isn't fixed (1/16 one session, 1/15 the next): it is learned,
 *    and any change of at least CLICK_MIN of a step is a click (never rounded to 0)
 *  - after we set the level ourselves the buds may still sit on their old level:
 *    reports are measured from that old level until they take ours, ours is re-sent
 *  - recenter targets sit on the buds' own grid; at most MAX_CLICKS per report
 *
 * Levels are fractions 0..1 (Android: streamIndex / streamMax). The platform calls
 * [onLevel] for every change and [tick] every ~50 ms; [tick] performs any pending set.
 */
class VolumeDial(
    private val backend: Backend,
    private val emit: (DialEvent) -> Unit,
    private val source: String = "volume-dial",
) {
    interface Backend {
        fun getLevel(): Float?
        fun setLevel(level: Float)
    }

    companion object {
        const val DEFAULT_STEP = 1f / 16
        const val CLICK_MIN = 0.35f
        const val MAX_CLICKS = 3
        const val RECENTER_IDLE_MS = 900L
        const val EDGE_STEPS = 2
        const val STALE_MS = 800L
    }

    var step = DEFAULT_STEP
        private set
    private var level: Float? = null
    private var fromDial = false
    private var passthrough = true
    private var home: Float? = null
    private var lastMove = 0L
    private var lastDial = 0L
    private var needRecenter = false
    private var saved: Float? = null
    private var apply: Float? = null
    private var reapply: Float? = null
    // our most recent set: time, buds' level before it, our level, re-sends left
    private var setAt = 0L
    private var setBefore: Float? = null
    private var setTarget = 0f
    private var setRetries = 0

    @Synchronized fun rebase() {
        level = backend.getLevel(); fromDial = false; setBefore = null
    }

    @Synchronized fun setPassthrough(on: Boolean) {
        if (on == passthrough) return
        passthrough = on
        val l = level
        if (!on && l != null) { home = snapHome(l); needRecenter = true }
    }

    @Synchronized fun setDuck(factor: Float?) {
        if (factor != null && factor > 0f && factor < 1f) {
            if (saved == null) saved = level ?: return
            val n = grid()
            val ducked = max((saved!! * factor * n).roundToInt(), EDGE_STEPS).toFloat() / n
            home = min(ducked, snapHome(saved!!))
            apply = home
        } else {
            val s = saved ?: return
            apply = s; home = snapHome(s); saved = null
        }
    }

    @Synchronized fun level(): Float? = saved ?: level
    @Synchronized fun lastActivity(): Long = max(lastDial, setAt)

    fun onLevel(newLevel: Float, ours: Boolean, now: Long = Clock.now()) {
        var out: DialEvent? = null
        synchronized(this) {
            if (ours) { level = newLevel; fromDial = false; return }
            val prev = level ?: run { level = newLevel; return }
            var d = newLevel - prev
            val before = setBefore
            if (before != null && now - setAt < STALE_MS) {
                if (abs(newLevel - setTarget) < CLICK_MIN * step) {
                    setBefore = null                                   // buds took our level
                } else {
                    d = newLevel - before                              // still on their old level
                    setBefore = newLevel
                    if (setRetries > 0) { reapply = setTarget; setRetries-- }
                    if (abs(d) < CLICK_MIN * step) return              // stale echo
                }
            }
            level = newLevel
            if (abs(d) < CLICK_MIN * step) { fromDial = true; return }
            // floor(+0.3): one click from an off-grid level stays 1, a folded double stays 2
            val clicks = min(MAX_CLICKS, max(1, (abs(d) / step + 0.3f).toInt()))
            if (fromDial && clicks == 1 && abs(d) > 0.03f && abs(d) < 0.15f) step = 0.5f * step + 0.5f * abs(d)
            fromDial = true
            lastMove = now; lastDial = now
            if (!passthrough) {
                val k = (newLevel * grid()).roundToInt()
                if (k <= EDGE_STEPS || k >= grid() - EDGE_STEPS) lastMove = 0L    // at an end: recenter now
                needRecenter = true
            }
            out = DialEvent(Kind.ROTATE, if (d > 0) clicks else -clicks, source, now)
        }
        out?.let(emit)
    }

    /** Call every ~50 ms. Performs duck/restore, re-sends, and the idle recenter. */
    fun tick(now: Long = Clock.now()) {
        var target: Float? = null
        var force = false
        synchronized(this) {
            when {
                apply != null -> { target = apply; apply = null }
                reapply != null -> { target = reapply; reapply = null; force = true }
                needRecenter && now - lastMove >= RECENTER_IDLE_MS -> {
                    needRecenter = false
                    if (!passthrough) target = home
                }
            }
            val t = target ?: return
            val before = level
            if (!force && before != null && abs(before - t) < 1e-3f) return
            if (!force) { setAt = now; setBefore = before; setTarget = t; setRetries = 2 }
        }
        backend.setLevel(target!!)
    }

    private fun grid(): Int = max((1f / step).roundToInt(), 2 * EDGE_STEPS + 3)

    internal fun snapHome(l: Float): Float {
        val n = grid()
        val k = min(max((l * n).roundToInt(), EDGE_STEPS + 1), n - EDGE_STEPS - 1)
        return k.toFloat() / n
    }
}
