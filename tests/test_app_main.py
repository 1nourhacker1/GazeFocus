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
from gazefocus.types import HeadSample, Zone
from gazefocus.win.focus import SwitchResult
from gazefocus.win.monitors import MonitorInfo
from gazefocus.win.rawinput import VK_ESCAPE, RawEvent

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


class FakeDock:
    def __init__(self, cfg, **callbacks):
        self.cfg, self.cb = cfg, callbacks
        self.views, self.previews, self.hidden, self.placed, self.closed = [], [], [], [], False
        self.freezes = []

    def place(self, work):
        self.placed.append(work)

    def set_view(self, view):
        self.views.append(view)

    def set_preview(self, frame, sample):
        self.previews.append((frame, sample))

    def set_hidden(self, hidden):
        self.hidden.append(hidden)

    def set_freeze(self, seconds):
        self.freezes.append(seconds)

    modal = None
    raised = 0

    def show_intro(self, on_start, on_cancel):
        self.modal, self.actions = "intro", {"start": on_start, "cancel": on_cancel}

    def show_result(self, result, on_save, on_redo):
        self.modal, self.result, self.actions = "result", result, {"save": on_save, "redo": on_redo}

    def close_modal(self):
        self.modal, self.actions = None, {}

    def press(self, name):
        self.actions[name]()

    def pill_centre(self):
        return (1280.0, 30.0)

    def raise_to_top(self):
        self.raised += 1
        return True

    def close(self):
        self.closed = True


class FakeRun:
    """Stands in for calib.run.CalibrationRun: the test decides when (and how) it ends."""

    made = []

    def __init__(self, screens, dock, *, on_done, cue, on_open, **kw):
        self.screens, self.dock_point, self.on_done, self.cue, self.on_open = screens, dock, on_done, cue, on_open
        self.samples, self.started, self.cancelled, self.active = [], False, False, False
        FakeRun.made.append(self)

    def start(self):
        self.started = self.active = True
        self.on_open()

    def on_sample(self, sample):
        if self.active:
            self.samples.append(sample)

    def cancel(self):
        self.cancelled, self.active = True, False

    def finish(self, result):
        self.active = False
        self.cue("DONE")
        self.on_done(result)


def cal_result(lg_yaw=30.0, lap_yaw=0.0):
    """A finished run's result: 60 face samples per screen."""
    import random

    from gazefocus.calib.session import CalibrationResult
    from gazefocus.logic.classifier import fit_zone_model, quality

    rng = random.Random(7)
    lg = [HeadSample(i, True, lg_yaw + rng.gauss(0, 2), 10 + rng.gauss(0, 2), 0.0) for i in range(60)]
    lap = [HeadSample(i, True, lap_yaw + rng.gauss(0, 2), 10 + rng.gauss(0, 2), 0.0) for i in range(60)]
    m = fit_zone_model(lg, lap)
    q = quality(m.separation)
    return CalibrationResult(m, {"LG": lg, "LAPTOP": lap}, {"LG": 60, "LAPTOP": 60}, q,
                             "Calibrated ✓" if q != "too close" else "Too close", "")


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
    FakeRun.made = []
    state = {"camera_ok": True, "fullscreen": False}
    docks = []

    def open_camera():
        if not state["camera_ok"]:
            return None
        cams.append(FakeCamera())
        return cams[-1]

    log = logging.getLogger("test.app")
    app = GazeFocusApp(
        Config(hotkey=HotkeyCfg(pause=TEST_HOTKEY)), open_camera=open_camera, make_tracker=FakeTracker, beep=beeps.append, qapp=qapp,
        log=log, dlog=logging.getLogger("test.app.decisions"), desktop_factory=desktop,
        monitors=lambda: [LAP, LG],
        dock_factory=lambda cfg, **cb: docks.append(FakeDock(cfg, **cb)) or docks[-1],
        screen_work=lambda m: m.work, fullscreen_on=lambda device, rect: state["fullscreen"],
        screen_rect=rect_of, run_factory=FakeRun, first_run=False,
    )
    state["docks"] = docks
    yield app, desktop, cams, beeps, state
    app.close()


def rect_of(m):
    x0, y0, x1, y1 = m.rect
    return (x0, y0, x1 - x0, y1 - y0)


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


def running_app(rig):
    app = rig[0]
    calibrate_fake()
    app.refresh_layout()
    app.apply()
    return app


def start_run(rig, qapp):
    """Recalibrate, then press Start on the intro."""
    app, state = rig[0], rig[4]
    dock = state["docks"][-1]
    app.recalibrate()
    assert dock.modal == "intro" and not app.state.calibrating  # the intro first; tracking goes on meanwhile
    dock.press("start")
    return app, dock, FakeRun.made[-1]


def test_recalibrate_opens_the_intro_and_start_runs_on_the_tracking_camera(rig, qapp):
    app, desktop = running_app(rig), rig[1]
    app, dock, run = start_run(rig, qapp)
    assert dock.modal is None and run.started and dock.raised == 1  # the dock is lifted above the overlay
    assert app.state.status is Status.CALIBRATING and app.worker.running
    assert run.screens == {"LG": rect_of(LG), "LAPTOP": rect_of(LAP)} and run.dock_point == (1280.0, 30.0)
    FakeTracker.yaw = 30.0  # looking at the LG must not switch focus while calibrating
    assert wait_until(qapp, lambda: len(run.samples) >= 5)
    assert desktop.brought == []


def test_not_now_keeps_the_old_calibration_tracking(rig, qapp):
    app = running_app(rig)
    dock = rig[4]["docks"][-1]
    app.recalibrate()
    dock.press("cancel")
    assert dock.modal is None and FakeRun.made == [] and app.state.status is Status.RUNNING


def test_the_first_calibration_turns_the_camera_on(rig, qapp):
    app, cams = rig[0], rig[2]
    assert app.state.status is Status.NOT_CALIBRATED and cams == []
    app, dock, run = start_run(rig, qapp)
    assert app.worker.running and wait_until(qapp, lambda: run.samples)


def test_save_commits_the_result_and_tracking_resumes(rig, qapp):
    app, _, _, beeps, _ = rig
    app, dock, run = start_run(rig, qapp)
    assert wait_until(qapp, lambda: app.worker.backend == "FAKE")
    run.finish(cal_result(28.0))
    assert dock.modal == "result" and dock.result.can_save and app.state.status is Status.CALIBRATING
    assert wait_until(qapp, lambda: beeps == ["DONE"])  # played off the Qt thread
    dock.press("save")
    assert dock.modal is None and app.state.status is Status.RUNNING and app.worker.running
    from gazefocus.storage import load_if_matches
    from gazefocus.win.monitors import layout_fingerprint

    cal, _ = load_if_matches(calibration_path(), layout_fingerprint([LAP, LG]))
    assert cal.camera["backend"] == "FAKE" and abs(cal.model.mean_lg[0] - 28.0) < 1.5


def test_the_result_panel_shows_the_new_model_live_without_switching(rig, qapp):
    app, desktop = running_app(rig), rig[1]
    app, dock, run = start_run(rig, qapp)
    run.finish(cal_result())
    app._on_sample(HeadSample(time.perf_counter(), True, yaw=30.0, pitch=10.0))
    app._on_sample(HeadSample(time.perf_counter(), True, yaw=30.0, pitch=10.0))
    assert dock.views[-1].mode == "tracking" and dock.views[-1].focus is Zone.LG  # the water follows the new model
    assert desktop.brought == []


def test_redo_starts_a_new_run_without_the_intro(rig, qapp):
    app, dock, run = start_run(rig, qapp)
    run.finish(cal_result())
    dock.press("redo")
    assert len(FakeRun.made) == 2 and FakeRun.made[-1].started and dock.modal is None
    assert app.state.status is Status.CALIBRATING


def test_a_result_too_close_to_save_offers_only_redo(rig, qapp):
    app, dock, run = start_run(rig, qapp)
    run.finish(cal_result(1.0))
    assert not dock.result.can_save and "save" in dock.actions  # the dock refuses its Save; the app would too
    before = calibration_path().exists()
    dock.press("save")
    assert calibration_path().exists() == before


def test_esc_cancels_the_run_and_keeps_the_calibration(rig, qapp):
    app = running_app(rig)
    before = calibration_path().read_text()
    app, dock, run = start_run(rig, qapp)
    app.input.on_event(time.perf_counter(), RawEvent("key", False, key_down=True, vkey=VK_ESCAPE))
    assert run.cancelled and app.state.status is Status.RUNNING and dock.modal is None
    assert calibration_path().read_text() == before


def test_esc_on_the_result_panel_discards_it(rig, qapp):
    app = running_app(rig)
    before = calibration_path().read_text()
    app, dock, run = start_run(rig, qapp)
    run.finish(cal_result())
    app.input.on_event(time.perf_counter(), RawEvent("key", False, key_down=True, vkey=VK_ESCAPE))
    assert dock.modal is None and app.state.status is Status.RUNNING
    assert calibration_path().read_text() == before


def test_other_keys_do_not_cancel(rig, qapp):
    app, dock, run = start_run(rig, qapp)
    app.input.on_event(time.perf_counter(), RawEvent("key", False, key_down=True, vkey=0x41))
    assert not run.cancelled and app.state.calibrating


@pytest.mark.parametrize("flag", ["paused", "locked", "suspended"])
def test_pause_lock_or_sleep_cancels_the_intro_or_the_run(rig, qapp, flag):
    app = running_app(rig)
    before = calibration_path().read_text()
    dock = rig[4]["docks"][-1]
    app.recalibrate()
    app._set(flag, True)
    assert dock.modal is None and FakeRun.made == []
    app._set(flag, False)
    app, dock, run = start_run(rig, qapp)
    app._set(flag, True)
    assert run.cancelled and not app.state.calibrating and not app.worker.running
    assert calibration_path().read_text() == before  # the good calibration is kept


def test_recalibrate_is_refused_without_two_monitors(rig):
    app, _, cams, beeps, state = rig
    calibrate_fake()
    before = calibration_path().read_text()
    app._monitors_fn = lambda: [LAP]  # the LG was unplugged
    app.refresh_layout()
    app.apply()
    app.recalibrate()
    assert state["docks"][-1].modal is None and FakeRun.made == [] and not app.state.calibrating
    assert calibration_path().read_text() == before


def test_a_layout_change_mid_run_cancels_it(rig, qapp):
    app = running_app(rig)
    before = calibration_path().read_text()
    app, dock, run = start_run(rig, qapp)
    app._monitors_fn = lambda: [LAP]  # the LG is unplugged mid-run
    app._relayout()
    assert run.cancelled and not app.state.calibrating
    assert calibration_path().read_text() == before


def test_a_layout_change_before_save_keeps_the_old_calibration(rig, qapp):
    app = running_app(rig)
    before = calibration_path().read_text()
    app, dock, run = start_run(rig, qapp)
    run.finish(cal_result())
    moved = MonitorInfo(LG.device, LG.id, (2560, 0, 4480, 1080), (2560, 0, 4480, 1040), False)
    app._monitors_fn = lambda: [LAP, moved]  # the LG moved before Save
    dock.press("save")
    assert calibration_path().read_text() == before and not app.state.calibrating


def test_calibrating_samples_at_the_full_camera_rate(rig, qapp):
    app, dock, run = start_run(rig, qapp)
    app.input.last_key_t = app.input.last_mouse_t = time.perf_counter() - 3600  # idle for an hour
    app.tick()
    assert app.worker.fps == app.cfg.camera.fps


def test_clicking_the_dock_alert_calibrates(rig):
    app, _, _, _, state = rig
    dock = state["docks"][-1]
    assert app.state.status is Status.NOT_CALIBRATED
    dock.cb["on_pill"]()
    assert dock.modal == "intro" and not app.state.paused


def test_first_run_opens_the_intro(qapp):
    docks = []
    app = GazeFocusApp(
        Config(hotkey=HotkeyCfg(pause=TEST_HOTKEY)), open_camera=lambda: None, make_tracker=FakeTracker,
        beep=lambda n: None, qapp=qapp, log=logging.getLogger("test.app"),
        dlog=logging.getLogger("test.app.decisions"), desktop_factory=FakeDesktop(), monitors=lambda: [LAP, LG],
        dock_factory=lambda cfg, **cb: docks.append(FakeDock(cfg, **cb)) or docks[-1], screen_work=lambda m: m.work,
        fullscreen_on=lambda d, r: False, screen_rect=rect_of, run_factory=FakeRun,
    )
    try:
        assert docks[-1].modal == "intro"
    finally:
        app.close()


def test_without_a_dock_the_run_starts_at_once_and_a_good_result_is_saved(qapp):
    from gazefocus.config import DockCfg

    FakeRun.made = []
    app = GazeFocusApp(
        Config(hotkey=HotkeyCfg(pause=TEST_HOTKEY), dock=DockCfg(enabled=False)), open_camera=lambda: None,
        make_tracker=FakeTracker, beep=lambda n: None, qapp=qapp, log=logging.getLogger("test.app"),
        dlog=logging.getLogger("test.app.decisions"), desktop_factory=FakeDesktop(), monitors=lambda: [LAP, LG],
        dock_factory=None, screen_work=lambda m: m.work, fullscreen_on=lambda d, r: False,
        screen_rect=rect_of, run_factory=FakeRun, first_run=False,
    )
    try:
        app.recalibrate()
        run = FakeRun.made[-1]
        assert run.started and run.dock_point == (1280.0, 30.0)  # the laptop's top centre
        run.finish(cal_result())
        assert calibration_path().exists() and app.state.calibration == "ok" and not app.state.calibrating
    finally:
        app.close()


def test_the_rig_never_holds_the_real_pause_hotkey(rig):
    """A real `gazefocus run` started while the tests run would lose Ctrl+Alt+G for its whole session."""
    app = rig[0]
    assert app.cfg.hotkey.pause == TEST_HOTKEY


def test_instance_name_is_isolated_under_tests(_isolated_home):
    assert instance_name().startswith("Local\\GazeFocus-")


def test_the_dock_sits_on_the_laptop_screen(rig):
    app, _, _, _, state = rig
    dock = state["docks"][-1]
    assert dock.placed and dock.placed[-1] == LAP.work
    assert dock.cb["freeze_s"] == 1.5


def test_the_dock_follows_the_app_state(rig):
    app, _, _, _, state = rig
    dock = state["docks"][-1]
    assert dock.views[-1].mode == "alert" and dock.views[-1].title == "Not calibrated"
    calibrate_fake()
    app.refresh_layout()
    app.apply()
    assert dock.views[-1].mode == "tracking" and dock.views[-1].focus == Zone.LAPTOP  # the fake foreground
    app.toggle_pause()
    assert dock.views[-1].mode == "paused" and dock.views[-1].title == "Paused"


def test_clicking_the_dock_pauses(rig):
    app = running_app(rig)
    dock = rig[4]["docks"][-1]
    dock.cb["on_pill"]()
    assert app.state.paused and dock.modal is None
    dock.cb["on_toggle_pause"]()  # the panel's Resume
    assert not app.state.paused


def test_the_dock_hides_while_locked_or_under_a_fullscreen_app(rig):
    app, _, _, _, state = rig
    dock = state["docks"][-1]
    assert dock.hidden[-1] is False
    app._set("locked", True)
    assert dock.hidden[-1] is True
    app._set("locked", False)
    state["fullscreen"] = True
    app.tick()
    assert dock.hidden[-1] is True
    state["fullscreen"] = False
    app.tick()
    assert dock.hidden[-1] is False


def test_the_open_panel_turns_the_camera_preview_on(rig):
    app, _, _, _, state = rig
    dock = state["docks"][-1]
    dock.cb["on_panel"](True)
    assert app.worker.preview_fps == 10.0
    frame = np.zeros((120, 160, 3), np.uint8)
    app._on_preview(frame, HeadSample(1.0, True))
    assert dock.previews and dock.previews[-1][0] is frame
    dock.cb["on_panel"](False)
    assert app.worker.preview_fps == 0.0


def test_a_lost_face_shows_only_after_half_a_second(rig):
    app, _, _, _, state = rig
    dock = state["docks"][-1]
    calibrate_fake()
    app.refresh_layout()
    app.apply()
    now = time.perf_counter()
    app._on_sample(HeadSample(now, True))
    app._on_sample(HeadSample(now + 0.1, False))
    assert dock.views[-1].face is True  # a blink: still holding the water
    app._face_t = time.perf_counter() - 0.6
    app._on_sample(HeadSample(time.perf_counter(), False))
    assert dock.views[-1].face is False


def test_a_disabled_dock_is_never_created(qapp):
    from gazefocus.config import DockCfg

    made = []
    app = GazeFocusApp(
        Config(hotkey=HotkeyCfg(pause=TEST_HOTKEY), dock=DockCfg(enabled=False)), open_camera=lambda: None,
        make_tracker=FakeTracker, beep=lambda n: None, qapp=qapp, log=logging.getLogger("test.app"),
        dlog=logging.getLogger("test.app.decisions"), desktop_factory=FakeDesktop(), monitors=lambda: [LAP, LG],
        dock_factory=lambda cfg, **cb: made.append(cfg), screen_work=lambda m: m.work,
        fullscreen_on=lambda d, r: False,
    )
    try:
        assert made == [] and app.dock is None
    finally:
        app.close()


def test_a_dock_setting_change_rebuilds_the_dock(rig, tmp_path):
    app, _, _, _, state = rig
    first = state["docks"][-1]
    app._on_config(replace(app.cfg, dock=replace(app.cfg.dock, refraction=False)), [])
    assert first.closed and state["docks"][-1] is not first and state["docks"][-1].cfg.refraction is False
    assert state["docks"][-1].placed  # and places it again



def test_qt_work_area_matches_screens_by_origin_not_name(qapp):
    """Qt names screens by their friendly names ("LG FHD"), not device names; the offscreen screen sits at (0, 0)."""
    from gazefocus.app.main import qt_work_area

    here = MonitorInfo("any-device-name", "id", (0, 0, 800, 800), (0, 0, 800, 800), True)
    elsewhere = MonitorInfo("any-device-name", "id", (-1920, -302, 0, 778), (-1920, -302, 0, 778), False)
    assert qt_work_area(here) == (0, 0, 800, 800)
    assert qt_work_area(elsewhere) is None


def test_a_live_typing_freeze_change_reaches_the_dock(rig):
    app, _, _, _, state = rig
    dock = state["docks"][-1]
    app._on_config(replace(app.cfg, decider=replace(app.cfg.decider, typing_freeze_ms=800)), [])
    assert state["docks"][-1] is dock and dock.freezes == [0.8]  # the same dock, told the new freeze


def test_no_face_since_the_camera_started_still_shows_no_face(rig):
    """A closed privacy shutter, or nobody in view at resume: the first sample starts the no-face clock."""
    app, _, _, _, state = rig
    dock = state["docks"][-1]
    calibrate_fake()
    app.refresh_layout()
    app.apply()  # the camera starts: nothing seen yet
    app._on_sample(HeadSample(time.perf_counter() - 0.6, False))  # the first frame, 0.6 s ago: nobody
    app._on_sample(HeadSample(time.perf_counter(), False))
    assert dock.views[-1].face is False


def test_a_dock_rebuilt_with_its_panel_open_turns_the_preview_off(rig):
    app, _, _, _, state = rig
    state["docks"][-1].cb["on_panel"](True)
    assert app.worker.preview_fps == 10.0
    app._on_config(replace(app.cfg, dock=replace(app.cfg.dock, refraction=False)), [])
    assert app.worker.preview_fps == 0.0
