"""Spin sensing, smooth scroll and wheel ducking."""
import time

from orbit.core.engine import Engine, State
from orbit.core.events import InputEvent, Kind
from orbit.core.motion import SpinTracker
from orbit.core.tools import SmoothScrollTool
from tests.test_engine import FakeOut, ev, make


def test_slow_clicks_stay_exact():
    s = SpinTracker()
    t = 100.0
    for _ in range(5):
        s.update(1, t)
        t += 0.8
    assert s.gain(8) == 1.0


def test_sustained_fast_spin_builds_gain():
    s = SpinTracker()
    gains = []
    t = 100.0
    for _ in range(6):
        s.update(1, t)
        gains.append(s.gain(8))
        t += 0.3
    assert gains[0] == 1.0 and gains[-1] == 8.0
    assert gains == sorted(gains)


def test_folded_double_report_counts_as_fast():
    s = SpinTracker()
    s.update(1, 100.0)
    s.update(2, 101.0)          # slow gap, but the firmware folded two detents
    assert s.intensity > 0


def test_reverse_resets_streak():
    s = SpinTracker()
    t = 100.0
    for _ in range(5):
        s.update(1, t)
        t += 0.3
    s.update(-1, t)
    assert s.streak <= 1 and s.gain(8) < 3


class _E:
    def __init__(self):
        self.out = FakeOut()


def _scrolled(tool, deltas, gap):
    e = _E()
    tool.enter(e)
    for d in deltas:
        tool.rotate(e, d)
        time.sleep(gap)
    time.sleep(1.2)
    tool.leave(e)
    return sum(n for k, n in e.out.log if k == "scroll")


def test_fast_spin_scrolls_much_further_than_slow():
    slow = _scrolled(SmoothScrollTool("s", {}), [1] * 4, 0.7)
    fast = _scrolled(SmoothScrollTool("s", {}), [1] * 4, 0.3)
    assert 3.5 < slow < 4.5            # careful clicks ~ 1 notch each
    assert fast > slow * 3             # intent: a spin flies


def test_reverse_brakes_momentum():
    up_then_down = _scrolled(SmoothScrollTool("s", {}), [1, 1, 1, 1, -1], 0.3)
    assert up_then_down < 30           # no runaway glide after reversing


def test_wheel_ducks_and_restores():
    e, out, ui, rot = make()
    e.handle(ev(Kind.HOLD))
    assert rot.duck[-1] == 0.5 and rot.passthrough is False
    e.handle(ev(Kind.CLICK))           # back to volume
    assert rot.duck[-1] is None and rot.passthrough is True
    e.handle(ev(Kind.HOLD))
    e.handle(ev(Kind.HOLD))            # cancel also restores
    assert rot.duck[-1] is None
