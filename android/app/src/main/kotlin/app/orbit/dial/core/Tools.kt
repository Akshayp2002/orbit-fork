package app.orbit.dial.core

import kotlin.math.pow
import kotlin.math.roundToInt

/** A wheel entry. Sticky tools take over the dial; one-shot items run once. */
abstract class Tool(val id: String, val label: String, val icon: String) {
    open val sticky = true
    open val rotationPassthrough = false
    open fun enter(a: Actions) {}
    open fun leave(a: Actions) {}
    /** Every ~50 ms; a returned Hud is shown. */
    open fun tick(a: Actions, now: Long): Hud? = null
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

/** Each click is one full swipe, like a thumb flick: next / previous reel, short,
 *  story; about a page in lists. The service queues them so they never overlap. */
class ScrollTool : Tool("scroll", "Scroll", "scroll") {
    override fun rotate(a: Actions, delta: Int): Hud {
        val dir = if (delta > 0) 1 else -1
        repeat(kotlin.math.abs(delta)) { a.swipe(dir) }
        return Hud(icon, label, if (dir > 0) "next" else "previous", null, dir)
    }
}

/** Presentations and paged viewers: each click is one sideways swipe, next / previous
 *  page (Google Slides, PowerPoint, PDF and photo viewers). Never sped up. */
class SlidesTool : Tool("slides", "Slides", "presentation") {
    override fun rotate(a: Actions, delta: Int): Hud {
        val dir = if (delta > 0) 1 else -1
        repeat(kotlin.math.abs(delta)) { a.swipe(dir, sideways = true) }
        return Hud(icon, label, if (dir > 0) "next slide" else "previous slide", null, dir)
    }
}

/** Remote shutter: with the Camera tool picked, each press of the dial takes a photo
 *  (opens the camera first if it isn't in front). Turning does nothing. */
class CameraTool : Tool("camera", "Camera", "camera") {
    override fun rotate(a: Actions, delta: Int) = Hud(icon, label, "press the dial to take a photo")
    override fun gesture(a: Actions, kind: Kind): Boolean =
        if (kind == Kind.CLICK) { a.shutter(); true } else false
    override fun hud(a: Actions, direction: Int) = Hud(icon, label, "press = shutter", direction = direction)
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

/** App switcher: the first click shows a strip of recent apps with the previous one
 *  highlighted; each click moves the highlight; letting go of the dial for
 *  [commitAfterMs] (or a press) opens it. */
class AppsTool(private val commitAfterMs: Long = 900) : Tool("apps", "Apps", "app") {
    private var list: List<App> = emptyList()
    private var pos = 0
    var browsing = false
        private set
    private var last = 0L
    private var justOpened: Hud? = null
    override fun rotate(a: Actions, delta: Int): Hud {
        if (!browsing) {
            list = a.recentApps().take(8)
            if (list.isEmpty()) return Hud(icon, label, "no recent apps yet")
            pos = -1                                  // first click forward = the previous app
            browsing = true
        }
        pos = ((pos + delta) % list.size + list.size) % list.size
        last = Clock.now()
        a.haptic()
        return Hud(icon, list[pos].label, direction = if (delta > 0) 1 else -1,
                   strip = AppStrip(list, pos, commitAfterMs))
    }
    private fun commit(a: Actions): Hud? {
        if (!browsing) return null
        browsing = false
        val app = list[pos]
        a.openApp(app.pkg)
        return Hud(icon, app.label, strip = AppStrip(list, pos, 0, opened = true)).also { justOpened = it }
    }
    override fun gesture(a: Actions, kind: Kind): Boolean =
        if (kind == Kind.CLICK && browsing) { commit(a); true } else false
    /** Right after a press opened the app, the engine asks for the HUD: show the strip's exit. */
    override fun hud(a: Actions, direction: Int): Hud =
        justOpened?.also { justOpened = null } ?: super.hud(a, direction)
    override fun tick(a: Actions, now: Long): Hud? =
        if (browsing && now - last > commitAfterMs) commit(a)?.also { justOpened = null } else null
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
    SlidesTool(),
    AppsTool(),
    ZoomTool(),
    TorchTool(),
    CameraTool(),
    ActionItem("screenshot", "Screenshot", "camera") { it.global("screenshot") },
    ActionItem("claude", "Claude", "claude") { it.launch("com.anthropic.claude") },
)
