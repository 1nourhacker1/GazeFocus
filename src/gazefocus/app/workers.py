"""Background threads: the tracking camera loop and the in-app calibration.

Both run on plain Python threads and report through a QObject bridge that lives on the Qt main
thread, so every callback runs on the main thread (Qt queues cross-thread signal emissions).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Protocol

import numpy as np
from PySide6.QtCore import QObject, Signal

from gazefocus.logic.classifier import ZoneModel
from gazefocus.runtime import calibrate
from gazefocus.types import HeadSample


class CameraLike(Protocol):
    backend: str | None

    def read(self) -> "np.ndarray | None": ...

    def release(self) -> None: ...


class TrackerLike(Protocol):
    def process(self, bgr: np.ndarray, t: float) -> HeadSample: ...

    def close(self) -> None: ...


class _Bridge(QObject):
    sample = Signal(object)
    failed = Signal(str)
    crashed = Signal(str)
    done = Signal(object)


class CameraWorker:
    def __init__(
        self,
        open_camera: Callable[[], "CameraLike | None"],
        make_tracker: Callable[[], TrackerLike],
        *,
        on_sample: Callable[[HeadSample], None],
        on_failed: Callable[[str], None],
        on_crashed: Callable[[str], None],
        fps: float = 15.0,
        max_missed_frames: int = 30,
    ) -> None:
        self.open_camera, self.make_tracker = open_camera, make_tracker
        self.fps, self.max_missed_frames = fps, max_missed_frames
        self._bridge = _Bridge()
        self._bridge.sample.connect(on_sample)
        self._bridge.failed.connect(on_failed)
        self._bridge.crashed.connect(on_crashed)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="gazefocus-camera", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 3.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None

    def _run(self) -> None:
        cam = self.open_camera()
        if cam is None:
            self._bridge.failed.emit("could not open the camera")
            return
        tracker = None
        try:
            tracker = self.make_tracker()
            missed, next_t = 0, time.perf_counter()
            while not self._stop.is_set():
                frame = cam.read()
                if frame is None:
                    missed += 1
                    if missed >= self.max_missed_frames:
                        self._bridge.failed.emit("the camera stopped delivering frames")
                        return
                    continue
                missed = 0
                self._bridge.sample.emit(tracker.process(frame, time.perf_counter()))
                next_t = max(next_t + 1.0 / max(self.fps, 0.1), time.perf_counter() - 0.5)
                self._stop.wait(max(0.0, next_t - time.perf_counter()))
        except Exception as e:  # reported to the main thread, which restarts us (spec §12.1)
            self._bridge.crashed.emit(f"{type(e).__name__}: {e}")
        finally:
            cam.release()
            if tracker is not None:
                tracker.close()


@dataclass(frozen=True)
class CalibrationOutcome:
    model: ZoneModel | None
    counts: dict = field(default_factory=dict)
    samples: dict = field(default_factory=dict)
    backend: str | None = None
    error: str | None = None


class CalibrationJob:
    """Runs the two-phase calibration on its own thread (the tracking camera must be stopped).

    Keep a reference to the job until on_done fires: if it is garbage-collected, its signal
    bridge goes with it and the queued result is dropped.
    """

    def __init__(
        self,
        open_camera: Callable[[], "CameraLike | None"],
        make_tracker: Callable[[], TrackerLike],
        *,
        cue: Callable[[str], None],
        on_done: Callable[[CalibrationOutcome], None],
        say: Callable[[str], None] = lambda text: None,
        seconds: float = 6.0,
        fps: float = 15.0,
        lead_in_s: float = 2.0,
    ) -> None:
        self.open_camera, self.make_tracker, self.cue, self.say = open_camera, make_tracker, cue, say
        self.seconds, self.fps, self.lead_in_s = seconds, fps, lead_in_s
        self._bridge = _Bridge()
        self._bridge.done.connect(on_done)
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if not self.running:
            self._thread = threading.Thread(target=self._run, name="gazefocus-calibration", daemon=True)
            self._thread.start()

    def _run(self) -> None:
        cam = self.open_camera()
        if cam is None:
            self._bridge.done.emit(CalibrationOutcome(None, error="could not open the camera"))
            return
        backend, tracker, samples = cam.backend, None, {}
        try:
            tracker = self.make_tracker()
            model, counts = calibrate(
                cam.read, tracker.process, seconds=self.seconds, fps=self.fps,
                say=self.say, cue=self.cue, samples_out=samples, lead_in_s=self.lead_in_s,
            )
            self._bridge.done.emit(CalibrationOutcome(model, counts, samples, backend))
        except Exception as e:
            self._bridge.done.emit(CalibrationOutcome(None, samples=samples, backend=backend, error=str(e)))
        finally:
            cam.release()
            if tracker is not None:
                tracker.close()
