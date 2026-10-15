"""Replays of real dial traces through the volume rotation source (no audio device needed)."""
import sys
import time

import pytest

if sys.platform != "win32":
    pytest.skip("windows backend", allow_module_level=True)

import comtypes

from orbit.platform.windows import input_volume as iv

DIAL = comtypes.GUID("{00000000-0000-0000-0000-000000000000}")   # Windows/driver context


def src(level):
    s = iv.VolumeRotationSource("x")
    got = []
    s._emit = lambda ev: got.append(ev.delta)
    s._baseline["d"] = level
    s._passthrough = False
    return s, got


def dial(s, pct):
    s._on_change("d", pct / 100, DIAL)


def our_set(s, pct):
    s._set_level(pct / 100, "test")          # records the stale-filter window (no devices bound)
    s._on_change("d", pct / 100, iv.OUR_CONTEXT)


def test_15_step_buds_from_off_grid_home_count_single_clicks():
    s, got = src(0.5625)                      # recentered on the old 1/16 grid
    for v in (66.7, 73.3, 80.0):
        dial(s, v)
    assert got == [1, 1, 1]                   # was [+2, +1, +1]


def test_reverse_click_from_off_grid_level_is_not_lost():
    s, got = src(0.5625)
    dial(s, 53.3)                             # -0.47 of a 1/16 step: used to round to 0
    assert got == [-1]


def test_stale_echo_after_recenter_is_ignored_and_reapplied():
    s, got = src(0.80)
    our_set(s, 56.25)
    dial(s, 80.0)                             # buds re-send their old level
    assert got == [] and s._reapply == pytest.approx(0.5625)


def test_click_before_buds_take_recenter_counts_once():
    """Real trace 15:23:44: buds at 80, we recenter to 56.2, buds report 86.7 -> was +5."""
    s, got = src(0.80)
    our_set(s, 56.25)
    dial(s, 56.3)                             # an echo near our level would confirm it...
    s2, got2 = src(0.80)
    our_set(s2, 56.25)
    dial(s2, 86.7)                            # ...but here the buds were still at 80
    assert got2 == [1]


def test_glitch_capped():
    s, got = src(0.20)
    dial(s, 90.0)
    assert got == [iv.MAX_CLICKS]


def test_keyboard_nudge_ignored():
    s, got = src(0.50)
    dial(s, 52.0)
    assert got == []


def test_step_is_learned_from_clean_clicks():
    s, got = src(0.40)
    for v in (46.67, 53.33, 60.0, 66.67):
        dial(s, v)
    assert abs(s._step - 1 / 15) < 0.002
    assert s._snap_home(0.55) == pytest.approx(round(0.55 * 15) / 15, abs=0.003)
