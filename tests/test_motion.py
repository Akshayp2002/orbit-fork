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


def test_flick_is_fast_from_second_report():
    """Real log: a quick flick arrives as 2-3 reports ~0.32-0.4 s apart."""
    s = SpinTracker()
    s.update(1, 100.0)                 # first of a flick looks slow (after a pause)
    assert s.gain(8) == 1.0
    s.update(1, 100.35)
    assert s.gain(8) == 8.0 and s.catch_up
    s.update(1, 100.70)
    assert s.gain(8) == 8.0 and not s.catch_up
    assert s.momentum > 0.6


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
    slow = _scrolled(SmoothScrollTool("s", {}), [1] * 4, 0.75)
    fast = _scrolled(SmoothScrollTool("s", {}), [1] * 4, 0.33)
    assert 3.5 < slow < 4.5            # careful clicks ~ 1 notch each
    assert fast > slow * 5             # intent: a spin flies


def test_two_report_flick_goes_far():
    flick = _scrolled(SmoothScrollTool("s", {}), [1, 1], 0.34)
    two_clicks = _scrolled(SmoothScrollTool("s", {}), [1, 1], 0.8)
    assert flick > two_clicks * 5


def test_reverse_brakes_momentum():
    tool, e = SmoothScrollTool("s", {}), _E()
    tool.enter(e)
    for _ in range(4):
        tool.rotate(e, 1)
        time.sleep(0.33)
    mark = len(e.out.log)
    tool.rotate(e, -1)                 # turn back mid-glide
    time.sleep(1.0)
    tool.leave(e)
    after = [n for k, n in e.out.log[mark:] if k == "scroll"]
    assert all(n < 0 for n in after)   # no forward glide survives the reversal
    assert -1.3 < sum(after) < -0.7    # and the correction is one precise click


def test_wheel_ducks_and_restores():
    e, out, ui, rot = make()
    e.handle(ev(Kind.HOLD))
    assert rot.duck[-1] == 0.5 and rot.passthrough is False
    e.handle(ev(Kind.CLICK))           # back to volume
    assert rot.duck[-1] is None and rot.passthrough is True
    e.handle(ev(Kind.HOLD))
    e.handle(ev(Kind.HOLD))            # cancel also restores
    assert rot.duck[-1] is None
