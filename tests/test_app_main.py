import logging
import time
from dataclasses import replace

import numpy as np
import pytest

from gazefocus.app.controller import Desktop
from gazefocus.app.main import GazeFocusApp, instance_name
from gazefocus.app.state import Status
from gazefocus.calibration import commit_calibration
from gazefocus.config import Config, HotkeyCfg
from gazefocus.logic.classifier import ZoneModel
from gazefocus.storage import calibration_path
from gazefocus.types import HeadSample
from gazefocus.win.focus import SwitchResult
from gazefocus.win.monitors import MonitorInfo

LAP = MonitorInfo(r"\\.\FAKE1", "id-lap", (0, 0, 2560, 1600), (0, 0, 2560, 1552), True)
LG = MonitorInfo(r"\\.\FAKE5", "id-lg", (-1920, -302, 0, 778), (-1920, -302, 0, 738), False)
MODEL = ZoneModel(w=(-1 / 15, 0.0, 0.0), b=1.0, separation=9.0, mean_lg=(30, 10, 0), mean_laptop=(0, 10, 0), sd=(3.0, 5.0, 0.1))
FRAME = np.zeros((2, 2, 3), np.uint8)
TEST_HOTKEY = "Ctrl+Alt+Shift+F24"  # tests never register the real Ctrl+Alt+G


class NoInput:
    """Stands in for InputWatcher: tests set `app.input` themselves and never hear the real keyboard or mouse."""

    def __init__(self, window, tracker) -> None:
        pass

    def close(self) -> None:
        pass


@pytest.fixture(autouse=True)
def _no_real_input(monkeypatch):
    monkeypatch.setattr("gazefocus.app.main.InputWatcher", NoInput)


def test_the_rig_never_hears_the_real_keyboard(rig):
    """The real InputWatcher registers system-wide Raw Input: typing during a test run would freeze switching."""
    from gazefocus.win.rawinput import InputWatcher

    assert not isinstance(rig[0].input_watcher, InputWatcher)


class FakeCamera:
    backend = "FAKE"

    def __init__(self):
        self.released = False

    def read(self):
        time.sleep(0.005)
        return FRAME

    def release(self):
        self.released = True


class FakeTracker:
    yaw = 0.0

    def process(self, frame, t):
        return HeadSample(t, True, yaw=FakeTracker.yaw, pitch=10.0)

    def close(self):
        pass


class FakeDesktop:
    def __init__(self):
        self.fg, self.brought = 1, []
        self.devices = {1: LAP.device, 11: LG.device}

    def __call__(self, work_area):
        return Desktop(
            foreground=lambda: self.fg,
            device_of_window=self.devices.get,
            buttons_down=lambda: False,
            fullscreen=lambda: False,
            choose_target=lambda device, mru: next((h for h, d in self.devices.items() if d == device), None),
            bring_to_front=self.bring,
            title_of=lambda h: f"window {h}",
            cursor_pos=lambda: (100, 100),
            device_of_point=lambda x, y: LAP.device,
            warp_cursor=lambda p: True,
            window_center=lambda h: (0, 0),
            work_area=work_area,
        )

    def bring(self, hwnd):
        self.brought.append(hwnd)
        self.fg = hwnd
        return SwitchResult(True, "direct", 5.0)


def wait_until(qapp, predicate, timeout=5.0):
    end = time.perf_counter() + timeout
    while time.perf_counter() < end:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def rig(qapp):
    FakeTracker.yaw = 0.0
    cams, beeps, desktop = [], [], FakeDesktop()
    state = {"camera_ok": True}

    def open_camera():
        if not state["camera_ok"]:
            return None
        cams.append(FakeCamera())
        return cams[-1]

    log = logging.getLogger("test.app")
    app = GazeFocusApp(
        Config(hotkey=HotkeyCfg(pause=TEST_HOTKEY)), open_camera=open_camera, make_tracker=FakeTracker, beep=beeps.append, qapp=qapp,
        log=log, dlog=logging.getLogger("test.app.decisions"), desktop_factory=desktop,
        monitors=lambda: [LAP, LG], calibration_seconds=1.8, calibration_lead_in_s=0.0,
    )
    yield app, desktop, cams, beeps, state
    app.close()


def calibrate_fake():
    commit_calibration(MODEL, {"LG": 60, "LAPTOP": 60}, None, monitors=[LAP, LG], dock_monitor="primary", camera={})


def test_uncalibrated_app_keeps_the_camera_off(rig):
    app, _, cams, _, _ = rig
    assert app.state.status is Status.NOT_CALIBRATED and not app.worker.running and cams == []


def test_calibrated_app_tracks_and_switches(rig, qapp):
    app, desktop, cams, _, _ = rig
    calibrate_fake()
    app.refresh_layout()
    app.apply()
    assert app.state.status is Status.RUNNING and app.worker.running
    FakeTracker.yaw = 30.0  # look at the LG
    assert wait_until(qapp, lambda: desktop.brought == [11])
    assert "focus on LG" in app.tray.icon.toolTip() or app.tray.icon.toolTip().startswith("GazeFocus: running")


def test_pause_releases_the_camera_and_resume_reopens_it(rig, qapp):
    app, _, cams, _, _ = rig
    calibrate_fake()
    app.refresh_layout()
    app.apply()
    app.toggle_pause()
    assert app.state.status is Status.PAUSED and not app.worker.running and cams[-1].released
    app.toggle_pause()
    assert app.worker.running and len(cams) == 2


def test_lock_and_sleep_release_the_camera(rig):
    app, _, cams, _, _ = rig
    calibrate_fake()
    app.refresh_layout()
    app.apply()
    app._set("locked", True)
    assert app.state.status is Status.LOCKED and not app.worker.running
    app._set("locked", False)
    app._set("suspended", True)
    assert not app.worker.running
    app._set("suspended", False)
    assert app.worker.running


def test_busy_camera_waits_and_retries(rig, qapp):
    app, _, cams, _, state = rig
    calibrate_fake()
    state["camera_ok"] = False
    app.refresh_layout()
    app.apply()
    assert wait_until(qapp, lambda: app.state.status is Status.CAMERA_WAIT)
    state["camera_ok"] = True
    app._retry_at = time.perf_counter() - 1  # pretend 5 s passed
    app.tick()
    assert app.worker.running and app.state.status is Status.RUNNING


def test_a_changed_layout_stops_switching(rig):
    app, _, _, _, _ = rig
    calibrate_fake()
    app._monitors_fn = lambda: [LAP]  # the LG was unplugged
    app.refresh_layout()
    app.apply()
    assert app.state.status is Status.UNSUPPORTED and not app.worker.running
    moved = MonitorInfo(LG.device, LG.id, (2560, 0, 4480, 1080), (2560, 0, 4480, 1040), False)
    app._monitors_fn = lambda: [LAP, moved]  # plugged back in somewhere else
    app.refresh_layout()
    assert app.state.status is Status.LAYOUT_CHANGED


def test_recalibrate_from_the_tray_saves_and_resumes(rig, qapp):
    app, _, _, beeps, _ = rig

    def cue(name):
        beeps.append(name)
        FakeTracker.yaw = 30.0 if name == "LG" else 0.0

    app.beep = cue
    app.cfg = replace(app.cfg, camera=replace(app.cfg.camera, fps=60))  # (1.8 s - 1.0 s settle) x 60 = 48 samples
    app.recalibrate()
    assert app.state.status is Status.CALIBRATING and not app.worker.running
    assert wait_until(qapp, lambda: not app.state.calibrating, timeout=15.0)
    assert beeps == ["LG", "LAPTOP", "DONE"]
    assert app.state.status is Status.RUNNING and app.worker.running


@pytest.mark.parametrize("flag", ["paused", "locked", "suspended"])
def test_pause_lock_or_sleep_during_recalibrate_cancels_it(rig, qapp, flag):
    app, _, cams, beeps, _ = rig
    calibrate_fake()
    before = calibration_path().read_text()
    app.calibration_seconds = 10.0
    app.recalibrate()
    assert wait_until(qapp, lambda: cams)  # the calibration has the camera
    app._set(flag, True)
    assert wait_until(qapp, lambda: cams[-1].released, timeout=1.0)
    assert wait_until(qapp, lambda: not app.state.calibrating, timeout=1.0)
    assert not app.worker.running and "DONE" not in beeps
    assert calibration_path().read_text() == before  # the good calibration is kept


def test_recalibrate_is_refused_without_two_monitors(rig):
    app, _, cams, beeps, _ = rig
    calibrate_fake()
    before = calibration_path().read_text()
    app._monitors_fn = lambda: [LAP]  # the LG was unplugged
    app.refresh_layout()
    app.apply()
    app.recalibrate()
    assert not app.state.calibrating and app._job is None and cams == [] and beeps == []
    assert calibration_path().read_text() == before


def test_a_layout_change_during_recalibrate_keeps_the_old_calibration(rig, qapp):
    app, _, _, beeps, _ = rig
    calibrate_fake()
    before = calibration_path().read_text()

    def cue(name):
        beeps.append(name)
        FakeTracker.yaw = 30.0 if name == "LG" else 0.0
        if name == "DONE":
            app._monitors_fn = lambda: [LAP]  # the LG is unplugged just before the end

    app.beep = cue
    app.cfg = replace(app.cfg, camera=replace(app.cfg.camera, fps=60))
    app.recalibrate()
    assert wait_until(qapp, lambda: not app.state.calibrating, timeout=15.0)
    assert beeps == ["LG", "LAPTOP", "DONE"]
    assert calibration_path().read_text() == before


def test_the_rig_never_holds_the_real_pause_hotkey(rig):
    """A real `gazefocus run` started while the tests run would lose Ctrl+Alt+G for its whole session."""
    app = rig[0]
    assert app.cfg.hotkey.pause == TEST_HOTKEY


def test_instance_name_is_isolated_under_tests(_isolated_home):
    assert instance_name().startswith("Local\\GazeFocus-")
