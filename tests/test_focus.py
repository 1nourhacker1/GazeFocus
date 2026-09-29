import time

from gazefocus.win import _api
from gazefocus.win.focus import bring_to_front, clamp_point, cursor_pos, nudge_input, window_center
from gazefocus.win.msgwindow import MessageWindow


def test_clamp_point_keeps_the_cursor_on_the_monitor():
    rect = (-1920, -302, 0, 778)
    assert clamp_point((-100, 100), rect) == (-100, 100)
    assert clamp_point((50, -900), rect) == (-1, -302)
    assert clamp_point((-5000, 5000), rect) == (-1920, 777)


def test_a_dead_window_fails_fast_without_raising():  # Review Focus #3
    win = MessageWindow()
    hwnd = win.hwnd
    win.close()
    t0 = time.perf_counter()
    r = bring_to_front(hwnd)
    assert r.ok is False and r.method == "none" and "gone" in r.detail
    assert time.perf_counter() - t0 < 0.1


def test_the_current_foreground_window_is_already_in_front():
    fg = _api.user32.GetForegroundWindow()
    r = bring_to_front(fg)
    assert r.ok and r.method == "already"


def test_window_center_and_cursor_are_readable():
    win = MessageWindow()
    try:
        assert window_center(win.hwnd) == (0, 0)  # a 0x0 window at the origin
    finally:
        win.close()
    x, y = cursor_pos()
    assert isinstance(x, int) and isinstance(y, int)


def test_nudge_sends_one_input_event():
    assert nudge_input() is True  # a zero-motion move: the pointer does not move
