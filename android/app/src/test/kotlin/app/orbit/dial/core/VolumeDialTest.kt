package app.orbit.dial.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import kotlin.math.abs

/** Same replays as tests/test_volume_source.py, against the Kotlin port. */
class VolumeDialTest {
    private var now = 10_000L
    private val sets = mutableListOf<Float>()
    private val got = mutableListOf<Int>()

    @Before fun clock() { Clock.now = { now } }

    private fun make(level: Float, passthrough: Boolean = false): VolumeDial {
        val d = VolumeDial(object : VolumeDial.Backend {
            override fun getLevel() = level
            override fun setLevel(level: Float) { sets += level }
        }, { got += it.delta })
        d.rebase()
        d.setPassthrough(true)
        if (!passthrough) d.setPassthrough(false)
        d.tick(now)          // initial recenter (if any) happens here
        sets.clear()
        return d
    }

    private fun VolumeDial.dial(pct: Double) { now += 400; onLevel((pct / 100).toFloat(), false, now) }
    private fun VolumeDial.ourSet(pct: Double) {
        setDuck(null)
        // emulate a recenter to pct: force a set through tick
        val target = (pct / 100).toFloat()
        val f = VolumeDial::class.java.getDeclaredField("apply"); f.isAccessible = true; f.set(this, target)
        tick(now)
        onLevel(target, true, now)
    }

    @Test fun fifteenStepBudsFromOffGridHomeCountSingleClicks() {
        val d = make(0.5625f)
        d.dial(66.7); d.dial(73.3); d.dial(80.0)
        assertEquals(listOf(1, 1, 1), got)
    }

    @Test fun reverseClickFromOffGridLevelIsNotLost() {
        val d = make(0.5625f)
        d.dial(53.3)
        assertEquals(listOf(-1), got)
    }

    @Test fun staleEchoAfterRecenterIsIgnored() {
        val d = make(0.80f)
        d.ourSet(56.25)
        d.dial(80.0)
        assertEquals(emptyList<Int>(), got)
    }

    @Test fun clickBeforeBudsTakeRecenterCountsOnce() {
        val d = make(0.80f)
        d.ourSet(56.25)
        d.dial(86.7)
        assertEquals(listOf(1), got)
    }

    @Test fun glitchCapped() {
        val d = make(0.20f)
        d.dial(90.0)
        assertEquals(listOf(VolumeDial.MAX_CLICKS), got)
    }

    @Test fun keyboardNudgeIgnored() {
        val d = make(0.50f)
        d.dial(52.0)
        assertEquals(emptyList<Int>(), got)
    }

    @Test fun stepIsLearnedAndHomeSnapsToGrid() {
        val d = make(0.40f)
        for (v in listOf(46.67, 53.33, 60.0, 66.67)) d.dial(v)
        assertTrue(abs(d.step - 1f / 15) < 0.002f)
        assertEquals(8f / 15, d.snapHome(0.55f), 1e-4f)
    }

    @Test fun idleRecenterHappensAfterQuietTime() {
        val d = make(0.50f)
        d.dial(56.25)
        d.tick(now + 100)
        assertTrue(sets.isEmpty())
        d.tick(now + VolumeDial.RECENTER_IDLE_MS + 1)
        assertEquals(1, sets.size)
    }

    @Test fun duckAndRestore() {
        val d = make(0.60f, passthrough = true)
        d.setDuck(0.5f); d.tick(now)
        assertEquals(5f / 16, sets.last(), 1e-4f)
        d.onLevel(sets.last(), true, now)
        d.setDuck(null); d.tick(now)
        assertEquals(0.60f, sets.last(), 1e-4f)
    }
}
