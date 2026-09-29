"""Thin OpenCV webcam wrapper: MSMF first, DirectShow fallback. Frames stay in memory."""

from __future__ import annotations

import cv2
import numpy as np

_BACKENDS = (("MSMF", cv2.CAP_MSMF), ("DSHOW", cv2.CAP_DSHOW))


class CameraSource:
    def __init__(self, index: int = 0, width: int = 640, height: int = 480) -> None:
        self.index, self.width, self.height = index, width, height
        self._cap = None
        self.backend: str | None = None

    @property
    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def open(self) -> bool:
        self.release()
        for name, api in _BACKENDS:
            cap = cv2.VideoCapture(self.index, api)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                ok, _ = cap.read()
                if ok:
                    self._cap, self.backend = cap, name
                    return True
            cap.release()
        return False

    def read(self) -> np.ndarray | None:
        if self._cap is None:
            return None
        ok, frame = self._cap.read()
        return frame if ok else None

    def grab(self) -> bool:
        return bool(self._cap is not None and self._cap.grab())

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
        self._cap, self.backend = None, None
