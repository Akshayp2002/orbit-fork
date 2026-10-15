package app.orbit.dial.core

import kotlin.math.pow
import kotlin.math.roundToInt

/** A wheel entry. Sticky tools take over the dial; one-shot items run once. */
abstract class Tool(val id: String, val label: String, val icon: String) {
    open val sticky = true
    open val rotationPassthrough = false
    open fun enter(a: Actions) {}
    open fun leave(a: Actions) {}
    open fun tick(a: Actions, now: Long) {}
    open fun rotate(a: Actions, delta: Int): Hud? = null
    /** Return true when the tool handled the gesture itself. */
    open fun gesture(a: Actions, kind: Kind): Boolean = false
    open fun hud(a: Actions, direction: Int): Hud = Hud(icon, label, direction = direction)
    open fun fire(a: Actions) {}
}

class VolumeTool : Tool("volume", "Volume", "volume") {
    override val rotationPassthrough = true
    override fun rotate(a: Actions, delta: Int) = hud(a, if (delta > 0) 1 else -1)
    override fun hud(a: Actions, direction: Int): Hud {
        val v = a.volume()
        return Hud(icon, label, v?.let { "${(it * 100).roundToInt()}%" } ?: "", v, direction)
    }
    override fun gesture(a: Actions, kind: Kind): Boolean =
        if (kind == Kind.TRIPLE) { a.media("next"); true } else false
}

/** Each click scrolls; a fast spin goes up to maxGain times further (see SpinTracker). */
class ScrollTool(private val pxPerClick: Float = 220f, private val maxGain: Float = 6f) :
    Tool("scroll", "Scroll", "scroll") {
    val spin = SpinTracker()
    override fun rotate(a: Actions, delta: Int): Hud {
        spin.update(delta)
        val g = spin.gain(maxGain)
        var px = delta * pxPerClick * g
        if (spin.catchUp) px += (if (delta > 0) 1 else -1) * pxPerClick * (g - 1)
        a.scrollBy(px)
        val dir = if (delta > 0) 1 else -1
        return Hud(icon, label, (if (dir > 0) "down" else "up") + if (spin.intensity > 0.5f) " · fast" else "", null, dir)
    }
}

class BrightnessTool(private val step: Float = 0.06f, private val maxGain: Float = 3f) :
    Tool("brightness", "Brightness", "brightness") {
    private val spin = SpinTracker()
    override fun rotate(a: Actions, delta: Int): Hud {
        val cur = a.brightness() ?: return Hud(icon, label, "allow 'Modify system settings'")
        spin.update(delta)
        val v = (cur + delta * step * spin.gain(maxGain)).coerceIn(0f, 1f)
        a.setBrightness(v)
        return Hud(icon, label, "${(v * 100).roundToInt()}%", v, if (delta > 0) 1 else -1)
    }
    override fun hud(a: Actions, direction: Int): Hud {
        val v = a.brightness() ?: return Hud(icon, label, "allow 'Modify system settings'")
        return Hud(icon, label, "${(v * 100).roundToInt()}%", v, direction)
    }
}

class ZoomTool : Tool("zoom", "Zoom", "zoom") {
    override fun rotate(a: Actions, delta: Int): Hud {
        val s = a.zoom((a.zoomScale() * 1.2f.pow(delta)).coerceIn(1f, 8f))
        return Hud(icon, label, "${"%.1f".format(s)}×", (s - 1f) / 7f, if (delta > 0) 1 else -1)
    }
    override fun gesture(a: Actions, kind: Kind): Boolean =
        if (kind == Kind.CLICK) { a.zoom(1f); true } else false
    override fun leave(a: Actions) { a.zoom(1f) }
}

class TorchTool : Tool("torch", "Torch", "bolt") {
    private var on = false
    private var level = 1f
    override fun rotate(a: Actions, delta: Int): Hud {
        if (!a.torchAvailable()) return Hud(icon, label, "no flash")
        level = (level + delta * 0.2f).coerceIn(0.2f, 1f)
        on = true
        a.torch(true, level)
        return Hud(icon, label, "${(level * 100).roundToInt()}%", level, if (delta > 0) 1 else -1)
    }
    override fun gesture(a: Actions, kind: Kind): Boolean {
        if (kind != Kind.CLICK) return false
        on = !on
        a.torch(on, level)
        return true
    }
    override fun hud(a: Actions, direction: Int) = Hud(icon, label, if (on) "on" else "off", if (on) level else 0f, direction)
}

/** Rotate walks the recent apps (shown in the HUD); press or a pause switches. */
class AppsTool(private val commitAfterMs: Long = 1100) : Tool("apps", "Apps", "app") {
    private var list: List<App> = emptyList()
    private var pos = 0
    private var browsing = false
    private var last = 0L
    override fun rotate(a: Actions, delta: Int): Hud {
        if (!browsing) { list = a.recentApps(); pos = 0; browsing = true }
        if (list.isEmpty()) { browsing = false; return Hud(icon, label, "no recent apps yet") }
        pos = ((pos + delta) % list.size + list.size) % list.size
        last = Clock.now()
        return Hud(icon, list[pos].label, "${pos + 1}/${list.size}", (pos + 1f) / list.size, if (delta > 0) 1 else -1)
    }
    private fun commit(a: Actions) {
        if (browsing && list.isNotEmpty()) a.openApp(list[pos].pkg)
        browsing = false
    }
    override fun gesture(a: Actions, kind: Kind): Boolean =
        if (kind == Kind.CLICK && browsing) { commit(a); true } else false
    override fun tick(a: Actions, now: Long) { if (browsing && now - last > commitAfterMs) commit(a) }
    override fun leave(a: Actions) { browsing = false }
}

class ActionItem(id: String, label: String, icon: String, private val run: (Actions) -> Unit) :
    Tool(id, label, icon) {
    override val sticky = false
    override fun fire(a: Actions) = run(a)
}

fun defaultTools(): List<Tool> = listOf(
    VolumeTool(),
    BrightnessTool(),
    ScrollTool(),
    AppsTool(),
    ZoomTool(),
    TorchTool(),
    ActionItem("screenshot", "Screenshot", "camera") { it.global("screenshot") },
    ActionItem("claude", "Claude", "claude") { it.launch("com.anthropic.claude") },
)
