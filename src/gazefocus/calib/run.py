"""One follow-the-drop run on screen (spec §9): the session, its overlay windows and the beeps,
paced by the display's refresh. The app owns the camera and feeds `on_sample`; the run reports
`on_done(result)` once, unless it is cancelled first.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from gazefocus.calib.path import Point, Rect
from gazefocus.calib.session import CUES, CalibrationResult, CalibrationSession

log = logging.getLogger(__name__)


class CalibrationRun:
    def __init__(
        self,
        screens: dict[str, Rect],
        dock: Point,
        *,
        on_done: Callable[[CalibrationResult], None],
        cue: Callable[[str], None] = lambda name: None,
        on_open: Callable[[], None] = lambda: None,
        overlay=None,
        ticker=None,
        clock: Callable[[], float] = time.perf_counter,
        native: bool = True,
        refraction: bool = True,
    ) -> None:
        self.session = CalibrationSession(screens["LG"], screens["LAPTOP"], dock)
        if overlay is None:
            from gazefocus.calib.overlay import Overlay

            overlay = Overlay(screens, native=native, refraction=refraction)
        if ticker is None:
            from gazefocus.dock.ticker import VBlankTicker

            ticker = VBlankTicker()
        self.overlay, self.ticker, self.clock = overlay, ticker, clock
        self.on_done, self.cue, self.on_open = on_done, cue, on_open
        self.ticker.tick.connect(self._tick)
        self.active = False
        self._phase: str | None = None

    def start(self) -> None:
        self.session.start(self.clock())
        self._phase = self.session.phase
        self.active = True
        self.overlay.open()
        self.on_open()  # the app lifts the dock back above the overlay
        self.ticker.start()

    def on_sample(self, sample) -> None:
        if self.active:
            self.session.on_sample(sample)

    def cancel(self) -> None:
        if self.active:
            self.session.cancel()
            self._stop()

    def _stop(self) -> None:
        self.active = False
        self.ticker.stop()
        self.ticker.close()
        try:
            self.overlay.hide()
        except Exception:
            log.exception("calibration overlay: hide failed")

    def _tick(self) -> None:
        self.ticker.handled()
        if not self.active:
            return  # a tick queued before cancel
        try:
            now = self.clock()
            frame = self.session.frame(now)
            self.overlay.show(frame, now)
            if frame.phase != self._phase:
                self._phase = frame.phase
                if frame.phase in CUES:
                    self.cue(CUES[frame.phase])
            result = self.session.result() if frame.phase == "done" else None
        except Exception as e:  # never leave both screens dimmed: end the run and say why
            log.exception("calibration frame failed")
            result = CalibrationResult(None, title="Calibration failed", message=f"{type(e).__name__}: {e}")
        if result is not None:
            self._stop()
            self.on_done(result)
