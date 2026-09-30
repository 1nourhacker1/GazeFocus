"""The dock's frame clock: one tick per display refresh while something moves, none otherwise.

Qt's animation timer runs at 60 Hz, which looked choppy on this 240 Hz laptop (M0-C2). A helper
thread waits on DwmFlush and signals the Qt thread. It never queues a second tick before the first
is handled, so a slow frame can't pile up a backlog.
"""

from __future__ import annotations

import threading
import time
from typing import Callable

from PySide6.QtCore import QObject, Signal

from gazefocus.win.capture import dwm_flush


class VBlankTicker(QObject):
    tick = Signal()

    def __init__(self, wait: Callable[[], None] = dwm_flush) -> None:
        super().__init__()
        self._wait = wait
        self._active, self._pending, self._quit = threading.Event(), threading.Event(), False
        self._thread = threading.Thread(target=self._run, name="gazefocus-vblank", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._quit:
            if not self._active.wait(0.5):
                continue
            t0 = time.perf_counter()
            self._wait()
            if time.perf_counter() - t0 < 0.001:
                time.sleep(0.002)  # the compositor had nothing to do: don't spin
            if self._active.is_set() and not self._quit and not self._pending.is_set():
                self._pending.set()
                self.tick.emit()

    @property
    def running(self) -> bool:
        return self._active.is_set()

    def start(self) -> None:
        self._active.set()

    def stop(self) -> None:
        self._active.clear()

    def handled(self) -> None:
        """Call at the start of each tick's handler: the next tick may then be queued."""
        self._pending.clear()

    def close(self) -> None:
        self._quit = True
        self._active.set()
        self._thread.join(1.0)
