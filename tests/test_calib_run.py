import random

from PySide6.QtCore import QObject, Signal

from gazefocus.calib.run import CalibrationRun
from gazefocus.types import HeadSample

LG = (-1920.0, -302.0, 1920.0, 1080.0)
LAP = (0.0, 0.0, 1706.0, 1066.0)
DOCK = (853.0, 30.0)


class FakeClock:
    def __init__(self):
        self.t = 50.0

    def __call__(self):
        return self.t


class ManualTicker(QObject):
    tick = Signal()

    def __init__(self):
        super().__init__()
        self.running, self.closed = False, False

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def handled(self):
        pass

    def close(self):
        self.closed = True


class FakeOverlay:
    def __init__(self):
        self.opened, self.hidden, self.frames = 0, 0, []

    def open(self):
        self.opened += 1

    def show(self, frame, now):
        self.frames.append(frame)

    def busy(self, now):
        return False

    def hide(self):
        self.hidden += 1


def make(qapp):
    clock, ticker, overlay = FakeClock(), ManualTicker(), FakeOverlay()
    got = {"cues": [], "done": [], "opened": 0}
    run = CalibrationRun({"LG": LG, "LAPTOP": LAP}, DOCK, on_done=got["done"].append, cue=got["cues"].append,
                         on_open=lambda: got.__setitem__("opened", got["opened"] + 1),
                         overlay=overlay, ticker=ticker, clock=clock)
    return run, clock, ticker, overlay, got


def drive(run, clock, ticker, seconds, rng=random.Random(4)):
    """60 Hz frames with a face sample every 4th frame (15 fps), yaw by the screen being toured."""
    for i in range(int(seconds * 60)):
        if not ticker.running:
            return
        clock.t += 1 / 60
        if i % 4 == 0:
            yaw = 0.0 if run.session.phase.startswith("lap") else 30.0
            run.on_sample(HeadSample(clock.t, True, yaw + rng.gauss(0, 2), rng.gauss(0, 2), 0.0))
        ticker.tick.emit()


def test_starting_opens_the_overlay_lifts_the_dock_and_starts_the_clock(qapp):
    run, clock, ticker, overlay, got = make(qapp)
    run.start()
    assert overlay.opened == 1 and got["opened"] == 1 and ticker.running and run.active


def test_a_run_beeps_for_each_screen_then_reports_its_result(qapp):
    run, clock, ticker, overlay, got = make(qapp)
    run.start()
    drive(run, clock, ticker, 20.0)
    assert got["cues"] == ["LG", "LAPTOP", "DONE"]
    assert len(got["done"]) == 1 and got["done"][0].can_save
    assert overlay.hidden == 1 and not ticker.running and ticker.closed and not run.active
    assert overlay.frames[0].phase == "start"


def test_cancel_hides_everything_and_reports_nothing(qapp):
    run, clock, ticker, overlay, got = make(qapp)
    run.start()
    drive(run, clock, ticker, 4.0)
    run.cancel()
    assert overlay.hidden == 1 and not ticker.running and not run.active
    ticker.tick.emit()  # a tick already queued
    run.on_sample(HeadSample(clock.t, True, 1.0, 0.0, 0.0))
    assert got["done"] == [] and "DONE" not in got["cues"]
    run.cancel()  # twice is harmless
    assert overlay.hidden == 1


def test_a_frame_that_fails_ends_the_run_with_a_failed_result(qapp):
    run, clock, ticker, overlay, got = make(qapp)

    def broken(frame, now):
        raise RuntimeError("GDI said no")

    overlay.show = broken
    run.start()
    clock.t += 1 / 60
    ticker.tick.emit()
    assert overlay.hidden == 1 and not ticker.running and not run.active  # nothing stays dimmed
    assert len(got["done"]) == 1 and not got["done"][0].can_save and got["done"][0].title == "Calibration failed"
