import logging

import pytest

from gazefocus.app.controller import Controller, Desktop
from gazefocus.app.decision_log import DecisionLogger
from gazefocus.config import ClassifierCfg, DeciderCfg
from gazefocus.logic.classifier import ZoneClassifier, ZoneModel
from gazefocus.logic.decider import GazeDecider
from gazefocus.types import HeadSample, Zone
from gazefocus.win.focus import SwitchResult
from gazefocus.win.foreground import MruTracker
from gazefocus.win.rawinput import InputTracker, RawEvent

LG_DEV, LAP_DEV = r"\\.\DISPLAY5", r"\\.\DISPLAY1"
TOY = ZoneModel(w=(1 / 15, 0.0, 0.0), b=1.0, separation=5.0, mean_lg=(-30, 10, 0), mean_laptop=(0, 10, 0), sd=(10.0, 5.0, 0.1))
AREAS = {LG_DEV: (-1920, -302, 0, 778), LAP_DEV: (0, 0, 2560, 1600)}


class FakeDesktop:
    def __init__(self):
        self.windows = {1: LAP_DEV, 2: LAP_DEV, 11: LG_DEV, 12: LG_DEV}
        self.fg = 1
        self.buttons = False
        self.full = False
        self.fail_with = None
        self.brought = []
        self.cursor = (500, 500)
        self.warped = []
        self.lg_windows = [11, 12]

    def desktop(self):
        return Desktop(
            foreground=lambda: self.fg,
            device_of_window=lambda h: self.windows.get(h),
            buttons_down=lambda: self.buttons,
            fullscreen=lambda: self.full,
            choose_target=self.choose,
            bring_to_front=self.bring,
            title_of=lambda h: f"window {h}",
            cursor_pos=lambda: self.cursor,
            device_of_point=lambda x, y: LG_DEV if x < 0 else LAP_DEV,
            warp_cursor=lambda p: self.warped.append(p) or True,
            window_center=lambda h: (-960, 238) if self.windows.get(h) == LG_DEV else (1280, 800),
            work_area=AREAS.get,
        )

    def choose(self, device, mru):
        pool = [h for h in mru if self.windows.get(h) == device] or [
            h for h, d in self.windows.items() if d == device and (d != LG_DEV or h in self.lg_windows)
        ]
        return pool[0] if pool else None

    def bring(self, hwnd):
        self.brought.append(hwnd)
        if self.fail_with:
            return SwitchResult(False, "failed", 510.0, self.fail_with)
        self.fg = hwnd
        return SwitchResult(True, "direct", 8.0)


class Lines(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


class Rig:
    def __init__(self, zone_devices=None, **decider_kw):
        self.now = 100.0
        self.fake = FakeDesktop()
        self.input = InputTracker()
        self.mru = MruTracker()
        logger = logging.getLogger("test.controller")
        logger.handlers.clear()
        logger.propagate = False
        logger.setLevel(logging.INFO)
        self.lines = Lines()
        logger.addHandler(self.lines)
        self.ctrl = Controller(
            classifier=ZoneClassifier(TOY, ClassifierCfg()),
            decider=GazeDecider(DeciderCfg(**decider_kw)),
            input_tracker=self.input,
            mru=self.mru,
            desktop=self.fake.desktop(),
            zone_devices=zone_devices or {Zone.LAPTOP: LAP_DEV, Zone.LG: LG_DEV},
            cursor_idle_warp_ms=2000,
            log=DecisionLogger(logger),
            clock=lambda: self.now,
        )

    def look(self, seconds, yaw, every_frame=None):
        out = []
        for _ in range(round(seconds * 15)):
            self.now += 1 / 15
            if every_frame:
                every_frame(self)
            out.append(self.ctrl.on_sample(HeadSample(self.now, True, yaw=yaw, pitch=10.0)))
        return out


LG_YAW, LAP_YAW = -30.0, 0.0


def test_looking_at_the_lg_focuses_its_most_recent_window():
    r = Rig()
    r.mru.on_foreground(50.0, 12, LG_DEV)
    r.mru.on_foreground(51.0, 11, LG_DEV)  # 11 is the most recent LG window
    r.look(1.0, LAP_YAW)
    out = r.look(1.5, LG_YAW)
    assert r.fake.brought == [11] and r.fake.fg == 11
    assert out[-1].reason == "on target"
    assert any(l.startswith("zone=LG") and "SWITCH LG" in l for l in r.lines.lines)
    assert any("focused 'window 11' on LG via direct" in l for l in r.lines.lines)


def test_looking_back_returns_to_the_laptop():
    r = Rig()
    r.look(1.5, LG_YAW)
    r.look(1.5, LAP_YAW)
    assert r.fake.brought == [11, 1] and r.fake.fg == 1


def test_typing_freezes_until_the_thaw():
    r = Rig()

    def typing(rig):
        rig.input.on_event(rig.now, RawEvent("key", injected=False, key_down=True))

    r.look(1.0, LG_YAW, every_frame=typing)  # glancing at the LG while typing
    assert r.fake.brought == []
    last_key = r.input.last_key_t
    r.look(2.0, LG_YAW)
    assert r.fake.brought == [11]
    assert any("BLOCKED(typing" in l for l in r.lines.lines)
    assert last_key is not None


def test_a_held_mouse_button_is_read_live_every_frame():  # Review Focus #1
    r = Rig()
    r.fake.buttons = True
    r.look(1.0, LG_YAW)
    assert r.fake.brought == []
    r.fake.buttons = False  # released: no stale "held" state anywhere
    r.look(0.2, LG_YAW)
    assert r.fake.brought == [11]


def test_manual_focus_change_cools_down():
    r = Rig()
    r.look(0.4, LG_YAW)
    r.mru.on_foreground(r.now, 2, LAP_DEV)  # the user clicked a laptop window
    r.fake.fg = 2
    r.look(0.5, LG_YAW)
    assert r.fake.brought == []
    assert any("BLOCKED(manual focus cooldown)" in l for l in r.lines.lines)


def test_fullscreen_blocks():
    r = Rig()
    r.fake.full = True
    r.look(1.5, LG_YAW)
    assert r.fake.brought == [] and any("fullscreen app" in l for l in r.lines.lines)


def test_a_refused_switch_is_tried_once_and_logged_once():  # Review Focus #6 (elevated window)
    r = Rig()
    r.fake.fail_with = "refused (elevated window or focus lock)"
    r.look(3.0, LG_YAW)
    assert r.fake.brought == [11]
    assert sum("FAIL" in l for l in r.lines.lines) == 1
    assert any("switch failed; look away to retry" in l for l in r.lines.lines)


def test_an_empty_lg_is_noted_and_not_retried():
    r = Rig()
    r.fake.lg_windows = []
    r.look(2.0, LG_YAW)
    assert r.fake.brought == []
    assert sum("no window to focus on LG" in l for l in r.lines.lines) == 1


def test_an_unplugged_lg_is_never_attempted():  # Review Focus #4 (transient, before re-layout)
    r = Rig(zone_devices={Zone.LAPTOP: LAP_DEV, Zone.LG: None})
    r.look(2.0, LG_YAW)
    assert r.fake.brought == [] and sum("LG is not connected" in l for l in r.lines.lines) == 1


def test_cursor_warps_to_where_it_was_on_that_monitor_only_if_the_mouse_is_idle():
    r = Rig()
    r.fake.cursor = (-400, 300)  # the cursor visits the LG, then goes back to the laptop
    r.look(0.1, LAP_YAW)
    r.fake.cursor = (900, 700)
    r.look(0.5, LAP_YAW)
    r.look(1.5, LG_YAW)
    assert r.fake.warped == [(-400, 300)]


def test_no_warp_while_the_mouse_is_in_use():
    r = Rig()

    def moving(rig):
        rig.input.on_event(rig.now, RawEvent("mouse", injected=False, moved=True))

    r.look(1.5, LG_YAW, every_frame=moving)
    assert r.fake.brought == [11] and r.fake.warped == []


def test_warp_falls_back_to_the_window_centre_clamped_to_the_work_area():
    r = Rig()
    r.look(1.5, LG_YAW)  # the cursor has never been on the LG
    assert r.fake.warped == [(-960, 238)]


def test_focus_zone_follows_the_live_foreground():
    r = Rig()
    r.fake.fg = 12
    assert r.ctrl.focus_zone() is Zone.LG
    r.fake.fg = 999  # a window on no known monitor
    assert r.ctrl.focus_zone() is Zone.UNKNOWN
