import numpy as np

from gazefocus.vision import camera as camera_mod
from gazefocus.vision.camera import CameraSource


class FakeCap:
    """Stands in for cv2.VideoCapture. `good_apis` lists backends that open and read."""

    good_apis: set = set()

    def __init__(self, index, api):
        self.api, self.opened, self.props = api, api in FakeCap.good_apis, {}

    def isOpened(self):
        return self.opened

    def set(self, prop, value):
        self.props[prop] = value
        return True

    def read(self):
        return (True, np.zeros((480, 640, 3), np.uint8)) if self.opened else (False, None)

    def grab(self):
        return self.opened

    def release(self):
        self.opened = False


def use_fake(monkeypatch, good):
    FakeCap.good_apis = good
    monkeypatch.setattr(camera_mod.cv2, "VideoCapture", FakeCap)


def test_msmf_preferred(monkeypatch):
    use_fake(monkeypatch, {camera_mod.cv2.CAP_MSMF, camera_mod.cv2.CAP_DSHOW})
    cam = CameraSource()
    assert cam.open() and cam.backend == "MSMF" and cam.is_open


def test_falls_back_to_dshow(monkeypatch):
    use_fake(monkeypatch, {camera_mod.cv2.CAP_DSHOW})
    cam = CameraSource()
    assert cam.open() and cam.backend == "DSHOW"
    assert cam.read().shape == (480, 640, 3)
    assert cam.grab() is True


def test_open_fails_cleanly(monkeypatch):
    use_fake(monkeypatch, set())
    cam = CameraSource()
    assert cam.open() is False
    assert cam.is_open is False and cam.backend is None
    assert cam.read() is None and cam.grab() is False


def test_release_resets(monkeypatch):
    use_fake(monkeypatch, {camera_mod.cv2.CAP_MSMF})
    cam = CameraSource()
    cam.open()
    cam.release()
    assert cam.is_open is False and cam.backend is None
