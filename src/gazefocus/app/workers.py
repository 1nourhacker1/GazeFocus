"""The tracking camera loop, on a background thread (it also feeds the calibration: Plan 4).

It runs on a plain Python thread and reports through a QObject bridge that lives on the Qt main
thread, so every callback runs on the main thread (Qt queues cross-thread signal emissions).
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Protocol

import cv2
import numpy as np
from PySide6.QtCore import QObject, Signal

from gazefocus.types import HeadSample


class CameraLike(Protocol):
    backend: str | None

    def read(self) -> "np.ndarray | None": ...

    def release(self) -> None: ...


class TrackerLike(Protocol):
    def process(self, bgr: np.ndarray, t: float) -> HeadSample: ...

    def close(self) -> None: ...


PREVIEW_SIZE = (160, 120)  # the dock's camera preview (spec §8.4): small, and only while the panel is open


class _Bridge(QObject):
    sample = Signal(object)
    preview = Signal(object, object)  # (BGR frame, HeadSample)
    failed = Signal(str)
    crashed = Signal(str)


class CameraWorker:
    def __init__(
        self,
        open_camera: Callable[[], "CameraLike | None"],
        make_tracker: Callable[[], TrackerLike],
        *,
        on_sample: Callable[[HeadSample], None],
        on_failed: Callable[[str], None],
        on_crashed: Callable[[str], None],
        on_preview: Callable[[np.ndarray, HeadSample], None] | None = None,
        fps: float = 15.0,
        max_missed_frames: int = 30,
    ) -> None:
        self.open_camera, self.make_tracker = open_camera, make_tracker
        self.fps, self.max_missed_frames = fps, max_missed_frames
        self.preview_fps = 0.0  # > 0 while the dock's panel shows the camera
        self.backend: str | None = None  # the last opened camera's backend, saved with a calibration
        self._bridge = _Bridge()
        self._bridge.sample.connect(on_sample)
        if on_preview is not None:
            self._bridge.preview.connect(on_preview)
        self._bridge.failed.connect(on_failed)
        self._bridge.crashed.connect(on_crashed)
        self._stop = threading.Event()  # the current run's; every run gets its own
        self._thread: threading.Thread | None = None

    @property
    def alive(self) -> bool:
        """The thread exists: running, or stopped but not yet done with the camera."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def running(self) -> bool:
        return self.alive and not self._stop.is_set()

    def start(self) -> bool:
        """Start a run; False if one is running or a stopped one still holds the camera (retry later)."""
        if self.alive:
            return False
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(self._stop,), name="gazefocus-camera", daemon=True)
        self._thread.start()
        return True

    def stop(self, timeout: float = 0.5) -> None:
        """Ask the run to end; it releases the camera as soon as it sees the request.

        Usually that is within one frame. An open still in progress can take seconds: the join
        gives up after `timeout` so the Qt thread never freezes, and `alive` stays True until then.
        """
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)

    def _run(self, stop: threading.Event) -> None:
        cam = self.open_camera()
        if stop.is_set():  # stopped while the camera was opening
            if cam is not None:
                cam.release()
            return
        if cam is None:
            self._bridge.failed.emit("could not open the camera")
            return
        self.backend = getattr(cam, "backend", None)
        tracker = None
        try:
            tracker = self.make_tracker()
            missed, next_t, last_preview = 0, time.perf_counter(), float("-inf")
            while not stop.is_set():
                frame = cam.read()
                if frame is None:
                    missed += 1
                    if missed >= self.max_missed_frames:
                        self._bridge.failed.emit("the camera stopped delivering frames")
                        return
                    continue
                missed = 0
                sample = tracker.process(frame, time.perf_counter())
                self._bridge.sample.emit(sample)
                rate = self.preview_fps
                if rate > 0 and sample.t - last_preview >= 1.0 / rate:
                    last_preview = sample.t
                    small = cv2.resize(frame, PREVIEW_SIZE, interpolation=cv2.INTER_AREA)
                    self._bridge.preview.emit(small, sample)
                next_t = max(next_t + 1.0 / max(self.fps, 0.1), time.perf_counter() - 0.5)
                stop.wait(max(0.0, next_t - time.perf_counter()))
        except Exception as e:  # reported to the main thread, which restarts us (spec §12.1)
            self._bridge.crashed.emit(f"{type(e).__name__}: {e}")
        finally:
            cam.release()
            if tracker is not None:
                tracker.close()
