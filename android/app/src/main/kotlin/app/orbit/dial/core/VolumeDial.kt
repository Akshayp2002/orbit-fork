package app.orbit.dial.core

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/**
 * Turns an output-volume level stream into dial clicks. Kotlin port of
 * orbit/core/volume_dial.py — same rules, learned on the real buds:
 *
 *  - the buds keep their own N-step grid (16 on Windows; Android's stream index
 *    has its own); every report is one step. The grid is detected: the smallest N
 *    all recent reports sit on. Any change of at least CLICK_MIN of a step is a click.
 *  - every set of ours may be echoed back as a not-ours report of the same level:
 *    never a click
 *  - a click in flight while we set arrives measured from the buds' old level; while
 *    a set is fresh, a report is measured from whichever of (ours, theirs) makes it
 *    a whole step. Landing back on their old level is a click from ours.
 *  - recenter targets sit on the grid; at most MAX_CLICKS per report
 *
 * Levels are fractions 0..1 (Android: streamIndex / streamMax). The platform calls
 * [onLevel] for every change and [tick] every ~50 ms; [tick] performs any pending set.
 */
class VolumeDial(
    private val backend: Backend,
    private val emit: (DialEvent) -> Unit,
    private val source: String = "volume-dial",
    /** Android: levels are stream index / max, a grid of its own (15, 25...) that the
     *  buds' 16 steps don't line up with, so one click can move 0-2 indices. Pass the
     *  stream max: the grid is fixed to it and every report counts as one click
     *  (the buds send exactly one step per report, calibration Oct 2026). */
    private val streamSteps: Int? = null,
) {
    interface Backend {
        fun getLevel(): Float?
        fun setLevel(level: Float)
    }

    companion object {
        const val DEFAULT_GRID = 16
        const val GRID_FIT = 0.15f
        const val GRID_SAMPLES = 8
        const val CLICK_MIN = 0.35f
        const val MAX_CLICKS = 2
        const val RECENTER_IDLE_MS = 900L
        const val EDGE_STEPS = 2
        const val STALE_MS = 800L
    }

    var grid = streamSteps ?: DEFAULT_GRID
        private set
    val step: Float get() = 1f / grid
    private val seen = ArrayDeque<Float>()     // recent dial-reported levels
    private var level: Float? = null
    private var passthrough = true
    private var home: Float? = null
    private var lastMove = 0L
    private var lastDial = 0L
    private var needRecenter = false
    private var saved: Float? = null
    private var apply: Float? = null
    // our most recent set: time, buds' level before it, our level (null once the buds moved on)
    private var setAt = 0L
    private var setBefore: Float? = null
    private var setTarget: Float? = null

    @Synchronized fun rebase() {
        level = backend.getLevel(); setBefore = null; setTarget = null; seen.clear()
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
            if (ours) { level = newLevel; return }
            val prev = level ?: run { level = newLevel; return }
            val target = setTarget
            val fresh = target != null && now - setAt < STALE_MS
            if (fresh && abs(newLevel - target!!) < (if (streamSteps != null) 1.1f else CLICK_MIN) * step) { level = newLevel; return }   // echo
            var d = newLevel - prev
            if (fresh) {
                val before = setBefore
                if (before != null && abs(abs(newLevel - before) / step - 1) < abs(abs(d) / step - 1) - 0.25f) {
                    d = newLevel - before          // click was in flight: measured from their old level
                    setBefore = null               // the OS re-applies ours next: still an echo
                } else {
                    setBefore = null; setTarget = null
                }
            }
            level = newLevel
            if (abs(d) < CLICK_MIN * step) return                      // keyboard nudge
            if (streamSteps == null) learnGrid(newLevel)
            // floor(+0.3): one click from an off-grid level stays 1
            val clicks = if (streamSteps != null) 1 else min(MAX_CLICKS, max(1, (abs(d) / step + 0.3f).toInt()))
            lastMove = now; lastDial = now
            if (!passthrough) {
                needRecenter = true
            }
            out = DialEvent(Kind.ROTATE, if (d > 0) clicks else -clicks, source, now)
        }
        out?.let(emit)
    }

    /** Call every ~50 ms. Performs duck/restore and the idle recenter. */
    fun tick(now: Long = Clock.now()) {
        var target: Float? = null
        synchronized(this) {
            when {
                apply != null -> { target = apply; apply = null }
                needRecenter && now - lastMove >= RECENTER_IDLE_MS -> {
                    needRecenter = false
                    if (!passthrough) target = home
                }
            }
            val t = target ?: return
            val before = level
            if (before != null && abs(before - t) < 1e-3f) return
            setAt = now; setBefore = before; setTarget = t
        }
        backend.setLevel(target!!)
    }

    private fun grid(): Int = max(grid, 2 * EDGE_STEPS + 3)

    /** Smallest grid every recent dial report sits on. */
    private fun learnGrid(l: Float) {
        seen.addLast(l)
        if (seen.size > GRID_SAMPLES) seen.removeFirst()
        if (seen.size < 3) return
        fun fit(n: Int) = seen.sumOf { abs(it * n - (it * n).roundToInt()).toDouble() } / seen.size
        if (fit(grid) <= GRID_FIT) return
        (8..32).firstOrNull { fit(it) <= GRID_FIT }?.let { grid = it }
    }

    internal fun snapHome(l: Float): Float {
        val n = grid()
        val k = min(max((l * n).roundToInt(), EDGE_STEPS + 1), n - EDGE_STEPS - 1)
        return k.toFloat() / n
    }
}
