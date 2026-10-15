package app.orbit.dial.core

/** Normalized dial input, same model as the desktop app (orbit/core/events.py). */
enum class Kind { ROTATE, CLICK, DOUBLE, TRIPLE, HOLD }

data class DialEvent(val kind: Kind, val delta: Int = 0, val source: String = "", val t: Long = Clock.now())

/** Injectable monotonic clock (ms) so the logic is unit-testable. */
object Clock {
    var now: () -> Long = { System.nanoTime() / 1_000_000 }
}
