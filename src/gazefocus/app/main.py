"""`gazefocus run`: the background app. Everything lives on the Qt main thread except the camera.

Wiring: MessageWindow (Raw Input, hotkey, lock/sleep/display events) + WinEvent foreground hook
+ CameraWorker thread -> Controller -> real focus switch; Tray for status and control.
The camera runs only while switching is possible or while calibrating; pause, lock and sleep release it.
Recalibrate (spec §9): the dock's intro -> a follow-the-drop run on the tracking camera -> the dock's
result panel -> Save or Redo. Esc, Not now, pause, lock, sleep and a layout change cancel it.
"""

from __future__ import annotations

import hashlib
import logging
import os
import signal
import sys
import threading
import time
from typing import Callable

from gazefocus.app.controller import Controller, Desktop
from gazefocus.app.decision_log import DecisionLogger, setup_logging
from gazefocus.app.state import MAX_TRACKER_FAILURES, AppState, Status
from gazefocus.app.tray import Tray
from gazefocus.app.workers import CameraWorker
from gazefocus.calibration import commit_calibration
from gazefocus.config import Config, ConfigWatcher, DockCfg, load_config, write_default_config
from gazefocus.dock.view import view_for
from gazefocus.logic.classifier import ZoneClassifier
from gazefocus.logic.decider import GazeDecider
from gazefocus.paths import app_dir
from gazefocus.storage import calibration_path, load_if_matches
from gazefocus.types import HeadSample, Zone
from gazefocus.win import _api, focus, rawinput, system, windows
from gazefocus.win.foreground import ForegroundHook, MruTracker
from gazefocus.win.monitors import (
    MonitorInfo,
    enumerate_monitors,
    ensure_dpi_awareness,
    layout_fingerprint,
    zone_monitors,
)
from gazefocus.win.msgwindow import MessageWindow
from gazefocus.win.rawinput import VK_ESCAPE, InputTracker, InputWatcher
from gazefocus.win.system import Hotkey, SingleInstance, SystemEvents

CAMERA_RETRY_S = 5.0
CRASH_RESTART_S = 2.0
HEALTHY_RESET_S = 60.0
DISPLAY_SETTLE_MS = 1500
FACE_LOST_S = 0.5  # the dock shows "no face" only after this long without one (no flicker)
PREVIEW_FPS = 10.0  # the open panel's camera preview (spec §8.4)
EXIT_ALREADY_RUNNING, EXIT_NO_MODEL = 4, 5


def instance_name() -> str:
    """One GazeFocus per user session; tests (GAZEFOCUS_HOME set) get their own mutex."""
    home = os.environ.get("GAZEFOCUS_HOME")
    return "Local\\GazeFocus" + (f"-{hashlib.sha1(home.encode()).hexdigest()[:8]}" if home else "")


def qt_work_area(monitor: MonitorInfo) -> tuple[int, int, int, int] | None:
    """A monitor's work area in Qt's logical coordinates.

    Qt names screens by their friendly names ("LG FHD"), not their device names, but keeps each
    screen's top-left at its native position (only sizes are scaled), so screens match by origin.
    """
    from PySide6.QtGui import QGuiApplication

    for screen in QGuiApplication.screens():
        g = screen.geometry()
        if (g.left(), g.top()) == tuple(monitor.rect[:2]):
            a = screen.availableGeometry()
            return a.left(), a.top(), a.right() + 1, a.bottom() + 1
    return None


def qt_screen_rect(monitor: MonitorInfo) -> tuple[float, float, float, float] | None:
    """A whole monitor as (x, y, w, h) in Qt's logical coordinates, matched by origin like `qt_work_area`."""
    from PySide6.QtGui import QGuiApplication

    for screen in QGuiApplication.screens():
        g = screen.geometry()
        if (g.left(), g.top()) == tuple(monitor.rect[:2]):
            return float(g.left()), float(g.top()), float(g.width()), float(g.height())
    return None


def make_run(screens, dock, **kw):
    from gazefocus.calib.run import CalibrationRun

    return CalibrationRun(screens, dock, **kw)


def make_dock(cfg: DockCfg, **callbacks):
    from gazefocus.dock.window import DockWindow

    return DockWindow(cfg, **callbacks)


def real_desktop(work_area: Callable[[str], "tuple[int, int, int, int] | None"]) -> Desktop:
    return Desktop(
        foreground=lambda: _api.user32.GetForegroundWindow() or 0,
        device_of_window=windows.device_of_window,
        buttons_down=rawinput.buttons_down,
        fullscreen=system.fullscreen_busy,
        choose_target=lambda device, mru: windows.choose_target(device, mru, windows.window_facts, windows.top_level_windows),
        bring_to_front=focus.bring_to_front,
        title_of=lambda hwnd: windows.window_facts(hwnd).title,
        cursor_pos=focus.cursor_pos,
        device_of_point=windows.device_of_point,
        warp_cursor=focus.warp_cursor,
        window_center=focus.window_center,
        work_area=work_area,
    )


class GazeFocusApp:
    def __init__(
        self,
        cfg: Config,
        *,
        open_camera: Callable[[], object],
        make_tracker: Callable[[], object],
        beep: Callable[[str], None],
        qapp,
        log: logging.Logger,
        dlog: logging.Logger,
        desktop_factory: Callable[[Callable[[str], object]], Desktop] = real_desktop,
        monitors: Callable[[], list[MonitorInfo]] = enumerate_monitors,
        dock_factory: Callable[..., object] | None = make_dock,
        screen_work: Callable[[MonitorInfo], "tuple[int, int, int, int] | None"] = qt_work_area,
        fullscreen_on: Callable[[str, tuple[int, int, int, int]], bool] = windows.fullscreen_app_on,
        screen_rect: Callable[[MonitorInfo], "tuple[float, float, float, float] | None"] = qt_screen_rect,
        run_factory: Callable[..., object] = make_run,
        first_run: bool = True,
    ) -> None:
        self.cfg, self.qapp, self.log, self.beep = cfg, qapp, log, beep
        self.open_camera, self.make_tracker = open_camera, make_tracker
        self.dlog = DecisionLogger(dlog)
        self._monitors_fn, self._desktop_factory = monitors, desktop_factory
        self.state = AppState()
        self.monitors: list[MonitorInfo] = []
        self._work_areas: dict[str, tuple[int, int, int, int]] = {}
        self.controller: Controller | None = None
        self._screen_rect, self._run_factory = screen_rect, run_factory
        self._intro = False  # the dock shows the calibration's intro
        self._run = None  # the follow-the-drop run (calib.run.CalibrationRun)
        self._result = None  # the finished run's CalibrationResult, while the dock shows it
        self._cal_layout: str | None = None  # the layout fingerprint the calibration started on
        self._preview = None  # a ZoneClassifier on the new model: the result panel's water follows it
        self._preview_zone = Zone.UNKNOWN
        self._retry_at: float | None = None
        self._restart_at: float | None = None
        self._running_since: float | None = None
        self._notified: set[str] = set()
        self._dock_factory, self._screen_work, self._fullscreen_on = dock_factory, screen_work, fullscreen_on
        self.dock = None
        self._dock_monitor: MonitorInfo | None = None
        self._last_sample: HeadSample | None = None
        self._face_t: float | None = None  # when a face was last seen (None: not since the camera started)

        self.window = MessageWindow("GazeFocus")
        self.input = InputTracker(on_key=self._on_key)
        self.input_watcher = InputWatcher(self.window, self.input)
        self.mru = MruTracker()
        self.fg_hook = ForegroundHook(self._on_foreground)
        self.system_events = SystemEvents(
            self.window,
            on_lock=lambda: self._set("locked", True),
            on_unlock=lambda: self._set("locked", False),
            on_suspend=lambda: self._set("suspended", True),
            on_resume=lambda: self._set("suspended", False),
            on_display_change=self._on_display_change,
        )
        self.hotkey = self._register_hotkey(cfg.hotkey.pause)
        self.tray = Tray(
            on_toggle_pause=self.toggle_pause,
            on_recalibrate=self.recalibrate,
            on_open_config=lambda: os.startfile(str(app_dir() / "config.toml")),
            on_open_logs=lambda: os.startfile(str(app_dir() / "logs")),
            on_quit=self.quit,
            restore_focus=self._restore_focus,
            hotkey_text=cfg.hotkey.pause,
        )
        self.worker = CameraWorker(
            open_camera, make_tracker,
            on_sample=self._on_sample, on_failed=self._on_camera_failed, on_crashed=self._on_crashed,
            on_preview=self._on_preview, fps=cfg.camera.fps,
        )
        self._make_dock()
        self.config_watcher = ConfigWatcher(app_dir() / "config.toml", self._on_config)
        self.refresh_layout()
        self.apply()
        if first_run and self.state.calibration == "missing":
            self.recalibrate()  # the intro opens once at the first start (spec §9)

    # ---- layout, calibration, controller -------------------------------------------------
    def refresh_layout(self) -> None:
        self.monitors = self._monitors_fn()
        self._work_areas = {m.device: m.work for m in self.monitors}
        self._place_dock()
        self.controller = None
        if len(self.monitors) != 2:
            self.state.calibration = "unsupported"
            self.log.warning("GazeFocus needs exactly 2 monitors; found %d", len(self.monitors))
            return
        path = calibration_path()
        cal, warning = load_if_matches(path, layout_fingerprint(self.monitors))
        if cal is None:
            self.state.calibration = "layout_changed" if path.exists() and "layout" in (warning or "") else "missing"
            self.log.warning(warning or "not calibrated yet: use the tray's Recalibrate")
            return
        devices = {m.id: m.device for m in self.monitors}
        zone_devices = {Zone.LAPTOP: devices.get(cal.zone_monitors.get("LAPTOP")), Zone.LG: devices.get(cal.zone_monitors.get("LG"))}
        if None in zone_devices.values():
            self.state.calibration = "unsupported"
            self.log.warning("the calibration does not name both monitors; recalibrate with the LG connected")
            return
        self.state.calibration = "ok"
        self.controller = Controller(
            classifier=ZoneClassifier(cal.model, self.cfg.classifier),
            decider=GazeDecider(self.cfg.decider),
            input_tracker=self.input,
            mru=self.mru,
            desktop=self._desktop_factory(self._work_areas.get),
            zone_devices=zone_devices,
            cursor_idle_warp_ms=self.cfg.decider.cursor_idle_warp_ms,
            log=self.dlog,
        )
        self.log.info("calibration loaded (%.1f sigma); LAPTOP=%s LG=%s", cal.model.separation,
                      zone_devices[Zone.LAPTOP], zone_devices[Zone.LG])

    # ---- the camera ------------------------------------------------------------------------
    def apply(self) -> None:
        wanted = self.state.camera_wanted and self._retry_at is None and self._restart_at is None
        if wanted and not self.worker.running:
            if self.worker.start():  # refused while a stopped run still holds the camera; tick retries
                self._running_since = time.perf_counter()
                self._face_t = None  # a fresh start: don't show "no face" before the first frame
        elif not wanted and self.worker.running:
            self.worker.stop()
            self._running_since = None
        self._update_tray()
        self._dock_visibility()
        self._update_dock()

    def _on_sample(self, sample: HeadSample) -> None:
        self._last_sample = sample
        if sample.face or self._face_t is None:  # a face, or the first frame since the camera started
            self._face_t = sample.t  # (so "nobody in view since the start" also becomes "no face" after 0.5 s)
        if self._run is not None:
            self._run.on_sample(sample)
        elif self._preview is not None:
            zone, _ = self._preview.update(sample)
            if zone is not Zone.UNKNOWN:
                self._preview_zone = zone
        if self.state.switching and self.controller is not None:
            self.controller.on_sample(sample)
        self._update_dock()

    def _on_camera_failed(self, why: str) -> None:
        from gazefocus.win.camera_usage import camera_busy_message

        self.state.camera_ok = False
        self._retry_at = time.perf_counter() + CAMERA_RETRY_S
        message = camera_busy_message() if "open" in why else why
        self.log.warning("camera: %s; retrying every %.0f s", message, CAMERA_RETRY_S)
        self._notify_once("camera", "Camera unavailable", message)
        self.apply()

    def _on_crashed(self, why: str) -> None:
        self.state.tracker_failures += 1
        self.log.error("tracker crashed (%d/%d): %s", self.state.tracker_failures, MAX_TRACKER_FAILURES, why)
        if self.state.tracker_failures < MAX_TRACKER_FAILURES:
            self._restart_at = time.perf_counter() + CRASH_RESTART_S
        else:
            self.tray.notify("GazeFocus stopped tracking", f"The tracker failed {MAX_TRACKER_FAILURES} times: {why}")
        self.apply()

    # ---- user and system events ---------------------------------------------------------------
    def _set(self, flag: str, value: bool) -> None:
        setattr(self.state, flag, value)
        self.log.info("%s -> %s", flag, value)
        if value:
            self.cancel_calibration(flag)  # pause, lock and sleep release the camera, even mid-calibration
        self.apply()

    def toggle_pause(self) -> None:
        self._set("paused", not self.state.paused)

    def _on_pill(self) -> None:
        """A click on the collapsed dock: calibrate when it shows "!" for a missing calibration, else pause."""
        if self.state.status in (Status.NOT_CALIBRATED, Status.LAYOUT_CHANGED):
            self.recalibrate()
        else:
            self.toggle_pause()

    def _on_key(self, vkey: int) -> None:
        if vkey == VK_ESCAPE:
            self.cancel_calibration("Esc")  # only listening: the focused app gets its Esc too

    def _on_foreground(self, hwnd: int) -> None:
        facts = windows.window_facts(hwnd)
        self.mru.on_foreground(time.perf_counter(), hwnd, facts.device, is_target=windows.is_switch_target(facts)[0])
        self._dock_visibility()  # a fullscreen app may just have come to the front
        self._update_dock()

    # ---- the dock ------------------------------------------------------------------------------------
    def _make_dock(self) -> None:
        if self.dock is not None:
            self.dock.close()
            self.dock = None
        if self.cfg.dock.enabled and self._dock_factory is not None:
            self.dock = self._dock_factory(
                self.cfg.dock, on_toggle_pause=self.toggle_pause, on_recalibrate=self.recalibrate,
                on_panel=self._on_panel, on_pill=self._on_pill, freeze_s=self.cfg.decider.typing_freeze_ms / 1000.0,
            )
            self.worker.preview_fps = 0.0  # a new dock starts with its panel closed

    def _place_dock(self) -> None:
        want = self.cfg.dock.monitor  # the same choice as the LAPTOP zone (zone_monitors)
        self._dock_monitor = next(
            (m for m in self.monitors if (m.primary if want == "primary" else m.device == want)), None)
        if self.dock is not None and self._dock_monitor is not None:
            work = self._screen_work(self._dock_monitor)
            if work is not None:
                self.dock.place(work)

    def _dock_visibility(self) -> None:
        """Out of the way while locked, asleep, or under a fullscreen app on its monitor (1 Hz + on focus change)."""
        if self.dock is None:
            return
        m = self._dock_monitor
        self.dock.set_hidden(self.state.locked or self.state.suspended or m is None
                             or self._fullscreen_on(m.device, m.rect))

    def _update_dock(self) -> None:
        """What the dock shows: cheap, called for every camera sample (the dock ignores repeats)."""
        if self.dock is None:
            return
        now = time.perf_counter()
        face = self._face_t is None or now - self._face_t < FACE_LOST_S
        if self._preview is not None:  # the result panel: the water follows the new model, nothing switches
            view = view_for(Status.RUNNING, focus=self._preview_zone, face=face, last_key_t=None, decision=None,
                            sample=self._last_sample, now=now, freeze_s=0.0)
            self.dock.set_view(view)
            return
        view = view_for(
            self.state.status,
            focus=self.controller.focus_zone() if self.controller is not None else Zone.UNKNOWN,
            face=face,
            last_key_t=self.input.last_key_t,
            decision=self.controller.last_decision if self.controller is not None else None,
            sample=self._last_sample,
            now=now,
            freeze_s=self.cfg.decider.typing_freeze_ms / 1000.0,
        )
        self.dock.set_view(view)

    def _on_panel(self, is_open: bool) -> None:
        self.worker.preview_fps = PREVIEW_FPS if is_open else 0.0  # the camera preview only while open

    def _on_preview(self, frame, sample: HeadSample) -> None:
        if self.dock is not None:
            self.dock.set_preview(frame, sample)

    def _on_display_change(self) -> None:
        from PySide6.QtCore import QTimer

        QTimer.singleShot(DISPLAY_SETTLE_MS, self._relayout)  # Windows reports changes in bursts

    def _relayout(self) -> None:
        before = self.state.calibration
        if self._run is not None and layout_fingerprint(self._monitors_fn()) != self._cal_layout:
            self.cancel_calibration("the monitors changed", notify=True)  # the overlay no longer fits them
        self.refresh_layout()
        if self.state.calibration != before:
            self.tray.notify("GazeFocus", f"Monitor layout: {self.state.status.value}")
        self.apply()

    def _restore_focus(self) -> None:
        hwnd = self.mru.last_app_window
        if hwnd:
            focus.bring_to_front(hwnd)

    # ---- calibration (spec §9) ------------------------------------------------------------------
    def recalibrate(self) -> None:
        """The tray, the panel's Recalibrate, a click on the dock's "!" and the first start: the intro first."""
        if self._intro or self._run is not None or self._result is not None:
            return
        if self._screens(self._monitors_fn()) is None:
            return
        if self.dock is None:
            self._start_run()  # no dock to ask in: start at once
            return
        self._intro = True
        self.dock.show_intro(self._start_run, lambda: self.cancel_calibration("Not now"))
        self.log.info("calibration: intro")

    def _screens(self, monitors: list[MonitorInfo]) -> dict | None:
        """{"LG": rect, "LAPTOP": rect} in Qt's logical coordinates, or None (and the user is told why)."""
        if len(monitors) != 2:
            self.tray.notify("Can't calibrate yet", f"GazeFocus needs 2 monitors and sees {len(monitors)}: "
                             "connect the LG, then Recalibrate.")
            self.log.warning("recalibrate refused: %d monitor(s)", len(monitors))
            return None
        by_id = {m.id: m for m in monitors}
        zones = zone_monitors(monitors, self.cfg.dock.monitor)
        rects = {z: self._screen_rect(by_id[i]) if i in by_id else None for z, i in zones.items()}
        if None in rects.values():
            self.tray.notify("Can't calibrate yet", "GazeFocus could not find both screens.")
            self.log.warning("recalibrate refused: screens %s", rects)
            return None
        return rects

    def _start_run(self) -> None:
        self._intro = False
        if self.dock is not None:
            self.dock.close_modal()
        monitors = self._monitors_fn()
        screens = self._screens(monitors)
        if screens is None:
            return
        self._cal_layout = layout_fingerprint(monitors)
        self.state.calibrating = True
        if self.dock is not None:
            dock_point = self.dock.pill_centre()
        else:
            x, y, w, _ = screens["LAPTOP"]
            dock_point = (x + w / 2, y + 30.0)
        self._run = self._run_factory(
            screens, dock_point, on_done=self._run_done, cue=self._cue, on_open=self._lift_dock,
            refraction=self.cfg.dock.refraction,
        )
        self.worker.fps = float(self.cfg.camera.fps)  # every sample counts: no idle or battery rate
        self.apply()  # the tracking camera stays on (or starts): the run samples it
        self._run.start()
        self.log.info("calibration started")

    def _lift_dock(self) -> None:
        if self.dock is not None:
            self.dock.raise_to_top()  # the overlay was shown after the dock

    def _cue(self, name: str) -> None:
        """The beeps (1 = LG, 2 = laptop, 3 = done), off the Qt thread: winsound.Beep blocks."""
        threading.Thread(target=self.beep, args=(name,), name="gazefocus-beep", daemon=True).start()

    def _run_done(self, result) -> None:
        self._run = None
        sep = f"{result.model.separation:.1f} sigma" if result.model is not None else "no model"
        self.log.info("calibration run: %s (%s; samples %s)", result.title, sep, result.counts)
        self._result = result
        if self.dock is None:
            if result.can_save:
                self._save()
            else:
                self.tray.notify(result.title, result.message)
                self.cancel_calibration(result.title)
            return
        if result.can_save:
            self._preview = ZoneClassifier(result.model, self.cfg.classifier)
            self._preview_zone = Zone.UNKNOWN
        self.dock.show_result(result, self._save, self._redo)
        self._update_dock()

    def _save(self) -> None:
        result = self._result
        if result is None or not result.can_save:
            return  # the dock offers no Save for it; nothing to do
        self._end_calibration()
        monitors = self._monitors_fn()
        if layout_fingerprint(monitors) != self._cal_layout:
            self.tray.notify("Calibration not saved", "The monitors changed during calibration. "
                             "The previous calibration was kept.")
            self.log.warning("calibration not saved: the monitor layout changed during it")
        else:
            cam = self.cfg.camera
            commit = commit_calibration(
                result.model, result.counts, result.samples, monitors=monitors, dock_monitor=self.cfg.dock.monitor,
                camera={"index": cam.index, "width": cam.width, "height": cam.height, "backend": self.worker.backend},
            )
            self.tray.notify("Calibration saved" if commit.saved else "Calibration not saved", commit.message)
            self.log.info(commit.message)
        self.refresh_layout()
        self.apply()

    def _redo(self) -> None:
        self._result, self._preview = None, None
        self._start_run()  # straight to the LG: no intro

    def _end_calibration(self) -> None:
        if self._run is not None:
            self._run.cancel()
        self._run = self._result = self._preview = None
        self._intro = False
        if self.dock is not None:
            self.dock.close_modal()
        self.state.calibrating = False

    def cancel_calibration(self, why: str, notify: bool = False) -> None:
        """Esc, Not now, pause, lock, sleep, a layout change: the previous calibration stays."""
        if not (self._intro or self._run is not None or self._result is not None):
            return
        self._end_calibration()
        self.log.info("calibration cancelled: %s", why)
        if notify:
            self.tray.notify("Calibration cancelled", f"{why[0].upper()}{why[1:]}. The previous calibration was kept.")
        self.apply()

    def _on_config(self, cfg: Config, warnings: list[str]) -> None:
        for w in warnings:
            self.log.warning("config: %s", w)
        hotkey_changed = cfg.hotkey.pause != self.cfg.hotkey.pause
        dock_changed = cfg.dock != self.cfg.dock
        freeze_changed = cfg.decider.typing_freeze_ms != self.cfg.decider.typing_freeze_ms
        self.cfg = cfg
        if dock_changed:
            self._make_dock()  # placed by refresh_layout below
        elif freeze_changed and self.dock is not None:
            self.dock.set_freeze(cfg.decider.typing_freeze_ms / 1000.0)
        self.worker.fps = cfg.camera.fps
        if hotkey_changed:
            if self.hotkey is not None:
                self.hotkey.close()
            self.hotkey = self._register_hotkey(cfg.hotkey.pause)
        self.refresh_layout()
        self.log.info("config reloaded")
        self.apply()

    def _register_hotkey(self, text: str) -> Hotkey | None:
        try:
            hk = Hotkey(self.window, text, self.toggle_pause)
        except ValueError as e:
            self.log.warning("hotkey: %s", e)
            return None
        if not hk.registered:
            self.log.warning("hotkey %s is taken by another app; use the tray to pause", text)
        return hk

    # ---- housekeeping (1 Hz) ----------------------------------------------------------------
    def tick(self) -> None:
        now = time.perf_counter()
        self.config_watcher.poll()
        fps = float(self.cfg.camera.fps)
        if not self.state.calibrating:  # a calibration samples at the full rate
            if self.input.idle_s(now) >= self.cfg.camera.idle_after_s:
                fps = float(self.cfg.camera.idle_fps)
            if system.on_battery():
                fps = min(fps, float(self.cfg.camera.battery_fps))
        self.worker.fps = fps
        if self._retry_at is not None and now >= self._retry_at:
            self._retry_at, self.state.camera_ok = None, True  # try again; a failure re-arms the timer
        if self._restart_at is not None and now >= self._restart_at:
            self._restart_at = None
        if self.state.tracker_failures and self._running_since and now - self._running_since >= HEALTHY_RESET_S:
            self.state.tracker_failures = 0
        self.apply()

    def _notify_once(self, key: str, title: str, text: str) -> None:
        if key not in self._notified:
            self._notified.add(key)
            self.tray.notify(title, text)

    def _update_tray(self) -> None:
        focus_zone = self.controller.focus_zone() if self.controller is not None else None
        self.tray.update(self.state.status, focus_zone)

    def quit(self) -> None:
        self.qapp.quit()

    def close(self) -> None:
        self._end_calibration()
        self.worker.stop(timeout=3.0)
        for part in (self.dock, self.fg_hook, self.input_watcher, self.system_events, self.hotkey, self.tray,
                     self.window):
            if part is not None:
                part.close()


def run_app(seconds: float | None = None) -> int:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from gazefocus.cues import beep
    from gazefocus.paths import model_path
    from gazefocus.vision.camera import CameraSource
    from gazefocus.vision.tracker import HeadTracker

    ensure_dpi_awareness()
    instance = SingleInstance(instance_name())
    if not instance.acquired:
        print("GazeFocus is already running (look for its tray icon).", file=sys.stderr)
        return EXIT_ALREADY_RUNNING
    if not model_path().is_file():
        print("face model missing; run: uv run python scripts/fetch_model.py", file=sys.stderr)
        instance.close()
        return EXIT_NO_MODEL
    cfg_path = app_dir() / "config.toml"
    write_default_config(cfg_path)
    cfg, warnings = load_config(cfg_path)
    log, dlog = setup_logging(app_dir() / "logs")
    for w in warnings:
        log.warning("config: %s", w)

    def open_camera():
        c = cfg.camera
        cam = CameraSource(c.index, c.width, c.height)
        return cam if cam.open() else None

    qapp = QApplication.instance() or QApplication(sys.argv)
    qapp.setQuitOnLastWindowClosed(False)
    app = GazeFocusApp(cfg, open_camera=open_camera, make_tracker=lambda: HeadTracker(model_path()),
                       beep=beep, qapp=qapp, log=log, dlog=dlog)
    housekeeping = QTimer()
    housekeeping.timeout.connect(app.tick)
    housekeeping.start(1000)
    signal.signal(signal.SIGINT, lambda *_: qapp.quit())
    wake = QTimer()  # lets Python notice Ctrl+C while Qt's loop runs
    wake.timeout.connect(lambda: None)
    wake.start(200)
    if seconds is not None:
        QTimer.singleShot(int(seconds * 1000), qapp.quit)
    log.info("GazeFocus started: %s", app.state.status.value)
    try:
        return qapp.exec()
    finally:
        housekeeping.stop()
        app.close()
        instance.close()
        log.info("GazeFocus stopped")
