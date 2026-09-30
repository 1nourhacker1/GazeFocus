import time

import numpy as np

from gazefocus.dock.ticker import VBlankTicker
from gazefocus.win.capture import Grabber, dwm_flush, exclude_from_capture


def test_grabber_returns_a_bgr_copy_of_the_requested_size():
    g = Grabber(8, 6)
    try:
        a, b = g.grab(0, 0), g.grab(0, 0)
        assert a.shape == (6, 8, 3) and a.dtype == np.uint8
        assert not np.shares_memory(a, b)  # the DIB is reused; callers get their own pixels
    finally:
        g.close()
    g.close()  # twice is harmless


def test_exclude_from_capture_refuses_a_missing_window():
    assert exclude_from_capture(0) is False


def test_dwm_flush_returns_within_a_frame_or_two():
    t0 = time.perf_counter()
    dwm_flush()
    assert time.perf_counter() - t0 < 0.1


def wait_for(qapp, predicate, timeout=2.0):
    end = time.perf_counter() + timeout
    while time.perf_counter() < end:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.002)
    return False


def test_ticks_arrive_on_the_qt_thread_while_running(qapp):
    ticker, ticks = VBlankTicker(wait=lambda: time.sleep(0.004)), []

    def on_tick():
        ticker.handled()
        ticks.append(time.perf_counter())

    ticker.tick.connect(on_tick)
    try:
        ticker.start()
        assert wait_for(qapp, lambda: len(ticks) >= 10)
        ticker.stop()
        qapp.processEvents()
        time.sleep(0.05)
        n = len(ticks)
        qapp.processEvents()
        assert len(ticks) <= n + 1  # at most the one already queued
    finally:
        ticker.close()


def test_an_unhandled_tick_blocks_the_next(qapp):
    ticker, ticks = VBlankTicker(wait=lambda: time.sleep(0.002)), []
    ticker.tick.connect(lambda: ticks.append(1))  # never calls handled()
    try:
        ticker.start()
        wait_for(qapp, lambda: False, timeout=0.2)
        assert len(ticks) == 1  # no backlog behind a slow frame
    finally:
        ticker.close()
