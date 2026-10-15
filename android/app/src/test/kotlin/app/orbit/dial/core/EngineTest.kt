package app.orbit.dial.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class EngineTest {
    private var now = 1_000L
    private val log = mutableListOf<String>()
    private var passthrough: Boolean? = null
    private val duck = mutableListOf<Float?>()

    @Before fun clock() { Clock.now = { now } }

    private val actions = object : Actions {
        var bright = 0.5f
        var scale = 1f
        override fun scrollBy(px: Float) { log += "scroll:${px.toInt()}" }
        override fun zoom(scale: Float): Float { this.scale = scale; log += "zoom:$scale"; return scale }
        override fun zoomScale() = scale
        override fun brightness() = bright
        override fun setBrightness(v: Float) { bright = v; log += "bright:$v" }
        override fun torchAvailable() = true
        override fun torch(on: Boolean, level: Float) { log += "torch:$on" }
        override fun recentApps() = listOf(App("a.one", "One"), App("b.two", "Two"))
        override fun openApp(pkg: String) { log += "open:$pkg" }
        override fun global(action: String) { log += "global:$action" }
        override fun media(command: String) { log += "media:$command" }
        override fun launch(pkg: String) { log += "launch:$pkg" }
        override fun volume() = 0.5f
        override fun haptic() {}
    }
    private val ui = object : Ui {
        override fun wheelOpen(items: List<Tool>, index: Int) { log += "ui:open:$index" }
        override fun wheelMove(index: Int, direction: Int) { log += "ui:move:$index" }
        override fun wheelCommit(index: Int) { log += "ui:commit:$index" }
        override fun wheelCancel() { log += "ui:cancel" }
        override fun hud(h: Hud) {}
    }
    private val rot = object : RotationControl {
        override fun setPassthrough(on: Boolean) { passthrough = on }
        override fun setDuck(factor: Float?) { duck += factor }
        override fun level() = 0.5f
    }

    private fun engine() = Engine(actions, ui, rot, defaultTools())
    private fun Engine.ev(k: Kind, d: Int = 0) { now += 400; handle(DialEvent(k, d, "test", now)) }

    @Test fun startsOnVolumeWithPassthrough() {
        val e = engine()
        assertEquals("volume", e.tool.id); assertEquals(true, passthrough)
    }

    @Test fun doubleOpensRotateMovesPressSelects() {
        val e = engine()
        e.ev(Kind.DOUBLE)
        assertEquals(Engine.State.WHEEL, e.state); assertEquals(false, passthrough); assertEquals(0.5f, duck.last())
        e.ev(Kind.ROTATE, 2)
        e.ev(Kind.CLICK)
        assertEquals("scroll", e.tool.id); assertEquals(null, duck.last()); assertEquals(false, passthrough)
        e.ev(Kind.ROTATE, 1)
        assertTrue(log.any { it.startsWith("scroll:") })
    }

    @Test fun doubleClosesWithoutChange() {
        val e = engine()
        e.ev(Kind.DOUBLE); e.ev(Kind.ROTATE, 3); e.ev(Kind.DOUBLE)
        assertEquals(Engine.State.TOOL, e.state); assertEquals("volume", e.tool.id)
        assertTrue(log.none { it.startsWith("media") })
    }

    @Test fun wheelWrapsBackwards() {
        val e = engine()
        e.ev(Kind.DOUBLE); e.ev(Kind.ROTATE, -1)
        assertEquals(e.tools.size - 1, e.index)
    }

    @Test fun timeoutKeepsStickyNeverFiresOneShot() {
        val e = engine()
        e.ev(Kind.DOUBLE); e.ev(Kind.ROTATE, 1)
        e.tick(now + 6000)
        assertEquals("brightness", e.tool.id)
        e.ev(Kind.DOUBLE); e.ev(Kind.ROTATE, -2)          // claude (one-shot)
        e.tick(now + 6000)
        assertTrue(log.none { it.startsWith("launch") })
    }

    @Test fun oneShotRunsAndKeepsTool() {
        val e = engine()
        e.ev(Kind.DOUBLE); e.ev(Kind.ROTATE, -1); e.ev(Kind.CLICK)
        assertTrue("launch:com.anthropic.claude" in log); assertEquals("volume", e.tool.id)
    }

    @Test fun volumeToolGestures() {
        val e = engine()
        e.ev(Kind.CLICK); e.ev(Kind.TRIPLE); e.ev(Kind.HOLD)
        assertEquals(listOf("media:play_pause", "media:next", "launch:com.anthropic.claude"),
            log.filter { it.startsWith("media") || it.startsWith("launch") })
    }

    @Test fun tripleFlipsLastTool() {
        val e = engine()
        e.setTool("zoom")
        e.ev(Kind.TRIPLE)
        assertEquals("volume", e.tool.id)
    }

    @Test fun appsToolCyclesAndCommitsOnPause() {
        val e = engine()
        e.setTool("apps")
        e.ev(Kind.ROTATE, 1)
        e.tick(now + 2000)
        assertTrue("open:b.two" in log)
    }

    @Test fun flickScrollsMuchFurtherThanSlowClicks() {
        val slow = ScrollTool(); val fast = ScrollTool()
        var s = 0f; var f = 0f
        val a = object : Actions by actions { override fun scrollBy(px: Float) { s += px } }
        val b = object : Actions by actions { override fun scrollBy(px: Float) { f += px } }
        for (i in 0 until 3) { now += 800; Clock.now = { now }; slow.rotate(a, 1) }
        for (i in 0 until 3) { now += 340; Clock.now = { now }; fast.rotate(b, 1) }
        assertTrue("fast=$f slow=$s", f > s * 3)
    }
}
