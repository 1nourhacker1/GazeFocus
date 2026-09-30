import threading
import time

import numpy as np

from gazefocus.app.workers import CameraWorker
from gazefocus.types import HeadSample

FRAME = np.zeros((2, 2, 3), np.uint8)


class FakeCamera:
    backend = "FAKE"

    def __init__(self, frames=None):
        self.frames = frames  # None = endless frames; otherwise an iterator
        self.released = False

    def read(self):
        time.sleep(0.005)
        if self.frames is None:
            return FRAME
        return next(self.frames, None)

    def release(self):
        self.released = True


class FakeTracker:
    def __init__(self, fail_after=None, yaw_of=lambda n: 0.0):
        self.n, self.fail_after, self.closed, self.yaw_of = 0, fail_after, False, yaw_of

    def process(self, frame, t):
        self.n += 1
        if self.fail_after is not None and self.n > self.fail_after:
            raise RuntimeError("mediapipe exploded")
        return HeadSample(t, True, yaw=self.yaw_of(self.n))

    def close(self):
        self.closed = True


def wait_until(qapp, predicate, timeout=3.0):
    end = time.perf_counter() + timeout
    while time.perf_counter() < end:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_samples_arrive_on_the_main_thread_at_the_requested_rate(qapp):
    cam, tracker, got = FakeCamera(), FakeTracker(), []
    main = threading.get_ident()
    w = CameraWorker(lambda: cam, lambda: tracker, on_sample=lambda s: got.append(threading.get_ident()),
                     on_failed=print, on_crashed=print, fps=20.0)
    w.start()
    time.sleep(0.5)
    w.stop()
    assert wait_until(qapp, lambda: len(got) >= 5)
    assert set(got) == {main}
    assert len(got) <= 15  # paced to about 20 fps, not the camera's rate
    assert cam.released and tracker.closed and not w.running


def test_camera_that_will_not_open_reports_failure(qapp):
    failed = []
    w = CameraWorker(lambda: None, FakeTracker, on_sample=print, on_failed=failed.append, on_crashed=print)
    w.start()
    assert wait_until(qapp, lambda: failed == ["could not open the camera"])


def test_camera_that_stops_delivering_reports_failure(qapp):
    cam, failed = FakeCamera(frames=iter([FRAME, FRAME])), []
    w = CameraWorker(lambda: cam, FakeTracker, on_sample=lambda s: None, on_failed=failed.append,
                     on_crashed=print, max_missed_frames=5)
    w.start()
    assert wait_until(qapp, lambda: failed == ["the camera stopped delivering frames"])
    assert wait_until(qapp, lambda: cam.released)  # released in `finally`, just after the report


def test_tracker_crash_is_reported_and_resources_released(qapp):
    cam, tracker, crashed = FakeCamera(), FakeTracker(fail_after=3), []
    w = CameraWorker(lambda: cam, lambda: tracker, on_sample=lambda s: None, on_failed=print,
                     on_crashed=crashed.append)
    w.start()
    assert wait_until(qapp, lambda: crashed == ["RuntimeError: mediapipe exploded"])
    assert wait_until(qapp, lambda: cam.released and tracker.closed)  # in `finally`, just after the report


def test_resuming_during_a_slow_open_does_not_revive_the_stopped_run(qapp):
    """Pause while the camera is still opening, then resume: the stopped run must give the camera back."""
    gate, opens, cams, samples = threading.Event(), [], [], []

    def open_camera():  # the first open is slow, like MSMF plus the DSHOW fallback taking seconds
        opens.append(1)
        if len(opens) == 1:
            gate.wait(5.0)
        cams.append(FakeCamera())
        return cams[-1]

    w = CameraWorker(open_camera, FakeTracker, on_sample=samples.append, on_failed=print, on_crashed=print)
    w.start()
    assert wait_until(qapp, lambda: opens)
    w.stop(timeout=0.05)  # times out: the open is still in progress
    w.start()  # resume while that run still exists
    gate.set()
    assert wait_until(qapp, lambda: cams and cams[0].released)
    qapp.processEvents()
    assert samples == [] and not w.running
    assert wait_until(qapp, lambda: not w.alive)
    assert w.start()  # once the old run has ended, a new one starts
    assert wait_until(qapp, lambda: samples)
    w.stop()
    assert not w.alive and len(cams) == 2 and all(c.released for c in cams)


def test_a_run_stopped_while_opening_reports_no_failure(qapp):
    gate, failed = threading.Event(), []

    def busy_open():
        gate.wait(5.0)
        return None  # the open failed, but nobody wants the camera any more

    w = CameraWorker(busy_open, FakeTracker, on_sample=print, on_failed=failed.append, on_crashed=print)
    w.start()
    w.stop(timeout=0.05)
    gate.set()
    assert not wait_until(qapp, lambda: failed, timeout=0.5)


def test_the_worker_remembers_the_camera_backend(qapp):
    w = CameraWorker(FakeCamera, FakeTracker, on_sample=lambda s: None, on_failed=print, on_crashed=print)
    assert w.backend is None
    w.start()
    assert wait_until(qapp, lambda: w.backend == "FAKE")  # saved with a calibration made from its samples
    w.stop()


def test_no_preview_frames_unless_asked(qapp):
    previews = []
    w = CameraWorker(FakeCamera, FakeTracker, on_sample=lambda s: None, on_failed=print, on_crashed=print,
                     on_preview=lambda f, s: previews.append(f), fps=60.0)
    w.start()
    time.sleep(0.3)
    w.stop()
    qapp.processEvents()
    assert previews == []


def test_preview_frames_are_small_and_paced(qapp):
    previews = []
    w = CameraWorker(FakeCamera, FakeTracker, on_sample=lambda s: None, on_failed=print, on_crashed=print,
                     on_preview=lambda f, s: previews.append((f, s)), fps=60.0)
    w.preview_fps = 10.0
    w.start()
    assert wait_until(qapp, lambda: len(previews) >= 3)
    time.sleep(0.5)
    w.stop()
    qapp.processEvents()
    frame, sample = previews[0]
    assert frame.shape == (120, 160, 3) and sample.face
    ts = [s.t for _, s in previews]
    assert min(b - a for a, b in zip(ts, ts[1:])) >= 0.099  # about 10 per second, not 60
