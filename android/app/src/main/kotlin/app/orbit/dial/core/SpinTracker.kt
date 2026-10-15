package app.orbit.dial.core

import kotlin.math.abs
import kotlin.math.min
import kotlin.math.pow

/**
 * Turn-speed sensing tuned to the CMF dial (port of orbit/core/motion.py).
 * The buds report at most ~1 per 0.32 s, so a report at that floor is full speed
 * immediately; `catchUp` marks the 2nd report of a flick so the 1st gets its boost.
 */
class SpinTracker {
    companion object {
        const val FAST_GAP = 400L
        const val SLOW_GAP = 700L
        const val STREAK_FULL = 3
    }

    private var t = 0L
    private var dir = 0
    var streak = 0
        private set
    var intensity = 0f
        private set
    var catchUp = false
        private set

    fun update(delta: Int, now: Long = Clock.now()): Float {
        val gap = now - t
        t = now
        val d = if (delta > 0) 1 else -1
        val reversed = d != dir
        dir = d
        var speed = ((SLOW_GAP - gap).toFloat() / (SLOW_GAP - FAST_GAP)).coerceIn(0f, 1f)
        if (abs(delta) >= 2) speed = 1f
        if (reversed) speed = 0f
        catchUp = speed > 0 && streak == 0 && !reversed
        streak = if (speed > 0) streak + 1 else 0
        intensity = speed
        return speed
    }

    fun gain(maxGain: Float): Float = 1f + (maxGain - 1f) * intensity.pow(1.2f)
    val momentum: Float get() = intensity * min(1f, streak.toFloat() / STREAK_FULL)
}
