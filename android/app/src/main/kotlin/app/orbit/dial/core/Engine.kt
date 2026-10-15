package app.orbit.dial.core

/**
 * Gesture engine: same model as the desktop app (orbit/core/engine.py).
 *
 *  TOOL   dial drives the active tool
 *  WHEEL  wheel open: rotate moves the highlight, press selects
 *
 *  double press      -> open wheel (and close it again, no change)
 *  in wheel: rotate  -> move highlight (wraps)   press -> select
 *            triple / hold -> close, no change    5 s idle -> keep highlighted tool
 *  tool mode: press/double/triple/hold -> the tool's own action, else the global one
 */
class Engine(
    val actions: Actions,
    private val ui: Ui,
    private val rotation: RotationControl?,
    val tools: List<Tool>,
    defaultTool: String = "volume",
    private val globalGestures: Map<Kind, Gesture> = mapOf(
        Kind.CLICK to Gesture.Media("play_pause"),
        Kind.TRIPLE to Gesture.LastTool,
        Kind.HOLD to Gesture.Launch("com.anthropic.claude"),
    ),
    private val openWith: Set<Kind> = setOf(Kind.DOUBLE),
    private val dismissAfterMs: Long = 5000,
    private val duck: Float = 0.5f,
) {
    enum class State { TOOL, WHEEL }

    var state = State.TOOL
        private set
    var tool: Tool = tools.first { it.id == defaultTool }
        private set
    var index = 0
        private set
    private var prevTool: Tool? = null
    private var wheelLast = 0L

    init { sync() }

    fun handle(ev: DialEvent) {
        if (state == State.WHEEL) wheelEvent(ev) else toolEvent(ev)
    }

    fun tick(now: Long = Clock.now()) {
        tool.tick(actions, now)
        if (state == State.WHEEL && now - wheelLast > dismissAfterMs) {
            if (tools[index].sticky) commit() else cancel()
        }
    }

    fun openWheel() {
        if (state == State.WHEEL) return
        tool.leave(actions)
        state = State.WHEEL
        index = tools.indexOf(tool).coerceAtLeast(0)
        wheelLast = Clock.now()
        sync()
        ui.wheelOpen(tools, index)
    }

    fun setTool(id: String) {
        val t = tools.firstOrNull { it.id == id } ?: return
        tool.leave(actions)
        switchTo(t)
        tool.enter(actions)
        sync()
        ui.hud(tool.hud(actions, 0))
    }

    private fun lastTool() { prevTool?.let { setTool(it.id) } }

    private fun switchTo(t: Tool) { if (t !== tool) { prevTool = tool; tool = t } }

    private fun toolEvent(ev: DialEvent) {
        if (ev.kind == Kind.ROTATE) {
            tool.rotate(actions, ev.delta)?.let(ui::hud)
            return
        }
        if (ev.kind in openWith) { openWheel(); return }
        if (tool.gesture(actions, ev.kind)) { ui.hud(tool.hud(actions, 0)); return }
        when (val g = globalGestures[ev.kind]) {
            is Gesture.Media -> actions.media(g.command)
            is Gesture.Launch -> actions.launch(g.pkg)
            is Gesture.Global -> actions.global(g.action)
            Gesture.LastTool -> lastTool()
            Gesture.OpenWheel -> openWheel()
            null -> {}
        }
    }

    private fun wheelEvent(ev: DialEvent) {
        wheelLast = Clock.now()
        when (ev.kind) {
            Kind.ROTATE -> {
                val n = tools.size
                index = ((index + ev.delta) % n + n) % n
                actions.haptic()
                ui.wheelMove(index, if (ev.delta > 0) 1 else -1)
            }
            Kind.CLICK -> commit()
            else -> cancel()            // double, triple, hold: close without change
        }
    }

    private fun commit() {
        val item = tools[index]
        ui.wheelCommit(index)
        state = State.TOOL
        if (item.sticky) {
            switchTo(item)
            item.enter(actions)
            sync()
            ui.hud(item.hud(actions, 0))
        } else {
            sync()
            tool.enter(actions)
            item.fire(actions)
            ui.hud(Hud(item.icon, item.label, "done"))
        }
    }

    private fun cancel() {
        state = State.TOOL
        ui.wheelCancel()
        tool.enter(actions)
        sync()
    }

    /** Wheel: consume rotation and duck the volume. Tool mode: restore, then per-tool. */
    private fun sync() {
        val r = rotation ?: return
        if (state == State.WHEEL) {
            r.setPassthrough(false); r.setDuck(duck)
        } else {
            r.setDuck(null); r.setPassthrough(tool.rotationPassthrough)
        }
    }
}

sealed interface Gesture {
    data class Media(val command: String) : Gesture
    data class Launch(val pkg: String) : Gesture
    data class Global(val action: String) : Gesture
    data object LastTool : Gesture
    data object OpenWheel : Gesture
}

data class Hud(val icon: String, val title: String, val detail: String = "",
               val progress: Float? = null, val direction: Int = 0)

interface Ui {
    fun wheelOpen(items: List<Tool>, index: Int)
    fun wheelMove(index: Int, direction: Int)
    fun wheelCommit(index: Int)
    fun wheelCancel()
    fun hud(h: Hud)
}

interface RotationControl {
    fun setPassthrough(on: Boolean)
    fun setDuck(factor: Float?)
    fun level(): Float?
}

/** Everything a tool can do to the phone. Implemented by the accessibility service. */
interface Actions {
    fun scrollBy(px: Float)
    fun zoom(scale: Float): Float          // returns the applied scale
    fun zoomScale(): Float
    fun brightness(): Float?               // 0..1, null if not permitted
    fun setBrightness(v: Float)
    fun torchAvailable(): Boolean
    fun torch(on: Boolean, level: Float = 1f)
    fun recentApps(): List<App>
    fun openApp(pkg: String)
    fun global(action: String)             // back, home, recents, notifications, quick_settings, screenshot, lock
    fun media(command: String)             // play_pause, next, previous
    fun launch(pkg: String)
    fun volume(): Float?
    fun haptic()
}

data class App(val pkg: String, val label: String)
