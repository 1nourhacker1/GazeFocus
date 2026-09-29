"""What is the app doing, and should the camera be on? Pure; the highest-priority reason wins."""

from __future__ import annotations

from enum import Enum


class Status(Enum):
    RUNNING = "running"
    CAMERA_WAIT = "camera unavailable"
    PAUSED = "paused"
    LOCKED = "screen locked"
    SUSPENDED = "asleep"
    CALIBRATING = "calibrating"
    NOT_CALIBRATED = "not calibrated"
    LAYOUT_CHANGED = "monitor layout changed"
    UNSUPPORTED = "unsupported monitor layout"
    TRACKER_FAILED = "tracker failed"


CALIBRATION_STATES = ("ok", "missing", "layout_changed", "unsupported")
MAX_TRACKER_FAILURES = 3


class AppState:
    def __init__(self) -> None:
        self.paused = False
        self.locked = False
        self.suspended = False
        self.calibrating = False
        self.calibration = "missing"  # one of CALIBRATION_STATES
        self.camera_ok = True
        self.tracker_failures = 0

    @property
    def status(self) -> Status:
        if self.calibrating:
            return Status.CALIBRATING
        if self.locked:
            return Status.LOCKED
        if self.suspended:
            return Status.SUSPENDED
        if self.paused:
            return Status.PAUSED
        if self.calibration == "unsupported":
            return Status.UNSUPPORTED
        if self.calibration == "missing":
            return Status.NOT_CALIBRATED
        if self.calibration == "layout_changed":
            return Status.LAYOUT_CHANGED
        if self.tracker_failures >= MAX_TRACKER_FAILURES:
            return Status.TRACKER_FAILED
        if not self.camera_ok:
            return Status.CAMERA_WAIT
        return Status.RUNNING

    @property
    def camera_wanted(self) -> bool:
        """The tracking camera runs only while switching is possible (or retrying to become so)."""
        return self.status in (Status.RUNNING, Status.CAMERA_WAIT)

    @property
    def switching(self) -> bool:
        return self.status is Status.RUNNING
