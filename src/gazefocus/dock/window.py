"""The dock window (spec §8): a Liquid Glass pill under the laptop camera, with the hover panel,
and the calibration's intro and result panels (spec §9), which stay open until a button is pressed.

It never takes focus, lets clicks through where it is transparent, and draws only when something
changes (spec §8.3: no idle animation). The frame pipeline (M0-C2):
  backdrop grab (idle timer; only a change of it triggers work)
  -> glass (cached per shape and theme; half resolution while the panel resizes)
  -> glyph + panel (QPainter) -> repaint.
Animation frames are paced by the display (VBlankTicker); slow ones (the lid's melt, fading steam)
are capped at 60 fps.
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from typing import Callable

import numpy as np
from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QImage, QPainter, QPainterPath
from PySide6.QtWidgets import QWidget

from gazefocus.config import DockCfg
from gazefocus.dock import geometry, glass
from gazefocus.dock.glyph import draw_glyph
from gazefocus.dock.modal import draw_intro, draw_result, modal_button_at
from gazefocus.dock.motion import EXPAND, Channel, ease_in_out, ease_out
from gazefocus.dock.panel import PanelContent, button_at, draw_panel, preview_image
from gazefocus.dock.scene import GlyphScene
from gazefocus.dock.ticker import VBlankTicker
from gazefocus.dock.view import IDLE, PAUSED, DockView
from gazefocus.types import HeadSample, Zone

HOVER_MS, LEAVE_MS = 350, 250  # spec §8.4
GRAB_MS = 200  # while idle, check what is behind the dock 5 times a second
SLOW_FPS = 60.0
OPEN_S, CLOSE_S = 0.52, 0.38
WM_MOUSEACTIVATE, MA_NOACTIVATE = 0x0021, 3


class DockWindow(QWidget):
    def __init__(
        self,
        cfg: DockCfg,
        *,
        on_toggle_pause: Callable[[], None],
        on_recalibrate: Callable[[], None],
        on_panel: Callable[[bool], None] = lambda is_open: None,
        freeze_s: float = 1.5,
        native: bool = True,
        grabber_factory: Callable[[int, int], object] | None = None,
        ticker=None,
        clock: Callable[[], float] = time.perf_counter,
        seed: int | None = None,
    ) -> None:
        flags = Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
        super().__init__(None, flags)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)  # hover follows the pill's shape, not the window's shadow
        self.cfg, self.clock = cfg, clock
        self.native = native and QGuiApplication.platformName() == "windows"  # never on the test platform
        self.on_toggle_pause, self.on_recalibrate, self.on_panel = on_toggle_pause, on_recalibrate, on_panel
        self.scene = GlyphScene(freeze_s=freeze_s, seed=seed)
        self.openness = Channel(0.0)
        self.modal: str | None = None  # "intro" or "result" while a calibration panel is up
        self.result = None  # the CalibrationResult the result panel shows
        self._actions: dict[str, Callable[[], None]] = {}
        self._kind = "status"  # the panel the pill opens to (and whose content it draws)
        self._panel_from = self._panel_to = geometry.PANELS["status"]
        self._morph = Channel(1.0)
        self._reported = False  # what on_panel last said about the hover panel
        self.view = DockView(IDLE, Zone.LAPTOP)
        self.scene.update(self.view, clock())
        self.preview: QImage | None = None
        self.preview_sample: HeadSample | None = None
        self.dark = False
        self.frames = 0  # rendered frames: for tests and stats
        if grabber_factory is None:
            from gazefocus.win.capture import Grabber

            grabber_factory = Grabber
        self._grabber_factory, self._grabber = grabber_factory, None
        self._backdrop, self._backdrop_key = None, None
        self._glass_key, self._glass_img, self.img = None, None, None
        self._grid, self._out = None, None
        self._last_frame_t = float("-inf")
        self.ticker = ticker if ticker is not None else VBlankTicker()
        self.ticker.tick.connect(self._on_tick)
        self._hover = QTimer(self, singleShot=True, interval=HOVER_MS, timeout=self._open)
        self._leave = QTimer(self, singleShot=True, interval=LEAVE_MS, timeout=self._close)
        self._idle = QTimer(self, interval=GRAB_MS, timeout=self._refresh_backdrop)
        self._wake = QTimer(self, singleShot=True, timeout=self._kick)

    # ---- the app's interface -----------------------------------------------------------------------
    def place(self, work: tuple[int, int, int, int]) -> None:
        """Top centre of a monitor's work area (left, top, right, bottom), in Qt's logical coordinates."""
        x, y, w, h = geometry.placement(work, self.cfg.scale)
        self.setGeometry(x, y, w, h)
        self._backdrop_key = self._glass_key = None
        if self.isVisible():
            QTimer.singleShot(60, self._refresh_backdrop)

    def set_view(self, view: DockView) -> None:
        now = self.clock()
        old, self.view = self.view, view
        self.scene.update(view, now)
        glyph_changed = view.glyph_key() != old.glyph_key()
        text_changed = (view.title, view.detail) != (old.title, old.detail)
        if glyph_changed or (text_changed and self.panel_open):
            self._frame(now)
            self._kick()

    def set_preview(self, frame: np.ndarray, sample: HeadSample) -> None:
        """A camera frame for the open panel; ignored (and never kept) while the panel is closed."""
        if not self.panel_open:
            return
        self.preview, self.preview_sample = preview_image(frame), sample
        self._frame(self.clock())

    def set_freeze(self, seconds: float) -> None:
        """A new typing freeze (a live config change): the lid's melt must end when the freeze does."""
        self.scene.freeze_s = seconds
        self._kick()

    @property
    def panel_open(self) -> bool:
        """The hover panel (with its camera preview) is open or opening."""
        return self.modal is None and self.openness.target > 0.5

    def show_intro(self, on_start: Callable[[], None], on_cancel: Callable[[], None]) -> None:
        self._show_modal("intro", {"start": on_start, "cancel": on_cancel})

    def show_result(self, result, on_save: Callable[[], None], on_redo: Callable[[], None]) -> None:
        self.result = result
        self._show_modal("result", {"save": on_save, "redo": on_redo})

    def close_modal(self) -> None:
        if self.modal is None:
            return
        self.modal, self._actions = None, {}
        self.openness.to(0.0, self.clock(), CLOSE_S, ease_out)
        self._kick()

    def panel_size(self, now: float) -> geometry.PanelSize:
        return geometry.mix(self._panel_from, self._panel_to, self._morph.get(now))

    def _show_modal(self, kind: str, actions: dict[str, Callable[[], None]]) -> None:
        now = self.clock()
        self.modal, self._actions = kind, actions
        self._hover.stop()
        self._leave.stop()
        self.preview = self.preview_sample = None
        self._report(False)
        self._set_panel(kind, now)
        if self.openness.target < 0.5:
            self.openness.to(1.0, now, OPEN_S, EXPAND)
        self._kick()

    def _set_panel(self, kind: str, now: float) -> None:
        self._kind, target = kind, geometry.PANELS[kind]
        if target == self._panel_to:
            return
        if self.openness.get(now) < 0.01:  # closed: nothing to morph
            self._panel_from = self._panel_to = target
            self._morph.set(1.0)
            return
        self._panel_from, self._panel_to = self.panel_size(now), target
        self._morph.set(0.0)
        self._morph.to(1.0, now, OPEN_S, ease_in_out)

    def _report(self, is_open: bool) -> None:
        if is_open != self._reported:
            self._reported = is_open
            self.on_panel(is_open)

    def set_hidden(self, hidden: bool) -> None:
        """Out of the way (screen locked, a fullscreen app on this monitor), without closing."""
        if hidden and self.isVisible():
            self.ticker.stop()
            self._idle.stop()
            self._wake.stop()
            self.hide()
        elif not hidden and not self.isVisible():
            self.show()

    def close(self) -> bool:
        self.ticker.stop()
        self._idle.stop()
        self.ticker.close()
        if self._grabber is not None:
            self._grabber.close()
            self._grabber = None
        return super().close()

    # ---- window plumbing -----------------------------------------------------------------------------
    def showEvent(self, e) -> None:
        super().showEvent(e)
        if self.native:
            from gazefocus.win.capture import exclude_from_capture, make_noactivate

            hwnd = int(self.winId())
            make_noactivate(hwnd)
            exclude_from_capture(hwnd)
        self._idle.start()
        QTimer.singleShot(60, self._refresh_backdrop)  # once the capture exclusion has applied

    def nativeEvent(self, event_type, message):
        if self.native:
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_MOUSEACTIVATE:
                return True, MA_NOACTIVATE  # a click never activates the dock
        return False, 0

    def _physical(self) -> tuple[int, int, int, int, float]:
        dpr = self.devicePixelRatioF()
        if self.native:
            from gazefocus.win import _api

            r = wintypes.RECT()
            _api.user32.GetWindowRect(int(self.winId()), ctypes.byref(r))
            return r.left, r.top, r.right - r.left, r.bottom - r.top, dpr
        return round(self.x() * dpr), round(self.y() * dpr), round(self.width() * dpr), round(self.height() * dpr), dpr

    # ---- backdrop --------------------------------------------------------------------------------------
    def _refresh_backdrop(self) -> None:
        if not self.isVisible():
            return
        px, py, w, h, dpr = self._physical()
        if self._grabber is None or (self._grabber.w, self._grabber.h) != (w, h):
            if self._grabber is not None:
                self._grabber.close()
            self._grabber = self._grabber_factory(w, h)
            self._grid, self._out = glass.Grid(w, h), np.zeros((h, w, 4), np.uint8)
            self._backdrop_key = None
        shot = self._grabber.grab(px, py)
        key = shot[::4, ::4].astype(np.int16)
        if self._backdrop_key is not None and np.abs(key - self._backdrop_key).mean() < 0.6:
            return  # nothing behind the dock changed: no frame
        self._backdrop_key, self._dpr = key, dpr
        self._backdrop = glass.prepare(shot, dpr, self.cfg.refraction)
        closed = geometry.pill_at(0.0, self.cfg.scale, w / dpr).scaled(dpr)
        self.dark = glass.pick_dark(glass.luminance(self._backdrop, closed), self.dark)
        self._glass_key = None
        self._frame(self.clock())

    # ---- frames ------------------------------------------------------------------------------------------
    def _content(self) -> PanelContent:
        s, paused = self.preview_sample, self.view.mode == PAUSED
        caption = "camera off" if paused else ("face ✓" if s is not None and s.face else "no face")
        return PanelContent(
            title=self.view.title,
            detail=self.view.detail,
            pause_label="Resume" if paused else "Pause",
            preview=None if paused else self.preview,
            face_box=None if s is None else s.box,
            nose=None if s is None else s.nose,
            yaw=0.0 if s is None else s.yaw,
            pitch=0.0 if s is None else s.pitch,
            caption=caption,
        )

    def _frame(self, now: float) -> None:
        if self._backdrop is None:
            return
        _, _, w, h, dpr = self._physical()
        if self._out is None or self._out.shape[:2] != (h, w):
            return  # resized since the last grab: the next grab catches up
        t = self.openness.get(now)
        panel = self.panel_size(now)
        step = 2 if self.openness.busy(now) or self._morph.busy(now) else 1
        key = (round(t, 4), self.dark, step, round(panel.w, 2), round(panel.h, 2))
        if key != self._glass_key:
            pill_px = geometry.pill_at(t, self.cfg.scale, w / dpr, panel).scaled(dpr)
            glass.render(self._backdrop, pill_px, dpr=dpr, dark=self.dark, openness=t,
                         refraction=self.cfg.refraction, step=step, grid=self._grid, out=self._out)
            img = QImage(self._out.data, w, h, 4 * w, QImage.Format_ARGB32_Premultiplied).copy()
            img.setDevicePixelRatio(dpr)
            self._glass_key, self._glass_img = key, img
        img = self._glass_img.copy()
        pill = geometry.pill_at(t, self.cfg.scale, w / dpr, panel)
        p = QPainter(img)
        draw_glyph(p, self.scene.frame(now), geometry.glyph_origin(t, self.cfg.scale, pill, panel),
                   dark=self.dark, dpr=dpr)
        if t > 0.45:
            clip = QPainterPath()
            clip.addRoundedRect(QRectF(pill.left, pill.top, 2 * pill.hw, 2 * pill.hh), pill.r, pill.r)
            p.setClipPath(clip)  # the content is revealed as the pill grows
            left, opacity = pill.cx - panel.w / 2, min(1.0, (t - 0.45) / 0.4)
            if self._kind == "intro":
                draw_intro(p, left, pill.top, opacity=opacity, dark=self.dark)
            elif self._kind == "result" and self.result is not None:
                draw_result(p, left, pill.top, self.result, opacity=opacity, dark=self.dark)
            else:
                draw_panel(p, left, pill.top, self._content(), opacity=opacity, dark=self.dark)
        p.end()
        self.img, self.frames, self._last_frame_t = img, self.frames + 1, now
        self.repaint()  # now, inside this tick, rather than at the next event-loop pass

    def paintEvent(self, e) -> None:
        if self.img is None:
            return
        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.drawImage(0, 0, self.img)

    # ---- the clock -----------------------------------------------------------------------------------------
    def _moving(self, now: float) -> tuple[bool, bool]:
        fast = self.scene.fast(now) or self.openness.busy(now) or self._morph.busy(now)
        return fast, fast or self.scene.busy(now)

    def _kick(self) -> None:
        now = self.clock()
        _, busy = self._moving(now)
        if busy:
            self._idle.stop()  # a grab costs ~5 ms of this thread: none while something moves
            self._wake.stop()
            self.ticker.start()
        else:
            self._arm_wake(now)

    def _arm_wake(self, now: float) -> None:
        at = self.scene.wake_at(now)
        if at is not None:
            self._wake.start(max(0, int((at - now) * 1000)) + 1)

    def _on_tick(self) -> None:
        self.ticker.handled()
        now = self.clock()
        fast, busy = self._moving(now)
        if busy and not fast and now - self._last_frame_t < 1.0 / SLOW_FPS:
            return
        self._frame(now)
        if not busy:
            self.ticker.stop()
            self._frame(now)  # the settled frame, at full resolution
            if self.isVisible():
                self._idle.start()
            self._arm_wake(now)

    # ---- hover and clicks ---------------------------------------------------------------------------------
    def _open(self) -> None:
        if self.modal is not None:
            return
        now = self.clock()
        self._set_panel("status", now)
        self.openness.to(1.0, now, OPEN_S, EXPAND)
        self._report(True)
        self._kick()

    def _close(self) -> None:
        if self.modal is not None:
            return  # a calibration panel waits for its buttons
        self.openness.to(0.0, self.clock(), CLOSE_S, ease_out)
        self.preview = self.preview_sample = None  # frames are never kept once the panel is closed
        self._report(False)
        self._kick()

    def _pointer(self, x: float, y: float) -> None:
        """Hover and leave follow the pill itself: the shadow around it doesn't count."""
        if self.modal is not None:
            return
        inside = geometry.pill_at(self.openness.get(self.clock()), self.cfg.scale, self.width()).contains(x, y)
        if self.panel_open:
            if inside:
                self._leave.stop()
            elif not self._leave.isActive():
                self._leave.start()
        elif not inside:
            self._hover.stop()
        elif not self._hover.isActive():
            self._hover.start()

    def enterEvent(self, e) -> None:
        self._pointer(e.position().x(), e.position().y())

    def mouseMoveEvent(self, e) -> None:
        self._pointer(e.position().x(), e.position().y())

    def leaveEvent(self, e) -> None:
        self._hover.stop()
        if self.panel_open:  # never a calibration panel
            self._leave.start()

    def mousePressEvent(self, e) -> None:
        if e.button() != Qt.LeftButton:
            return
        x, y, now = e.position().x(), e.position().y(), self.clock()
        t = self.openness.get(now)
        panel = self.panel_size(now)
        pill = geometry.pill_at(t, self.cfg.scale, self.width(), panel)
        if not pill.contains(x, y):
            return  # the shadow is ours to draw, not to act on
        if self.modal is not None:  # only the calibration panel's buttons act
            action = self._actions.get(modal_button_at(self.modal, x, y, pill.cx - panel.w / 2, pill.top, self.result))
            if action is not None:
                action()
            return
        if self.panel_open:
            button = button_at(x, y, pill.cx - geometry.PANEL[0] / 2, pill.top)
            if button == "pause":
                self.on_toggle_pause()
            elif button == "recalibrate":
                self.on_recalibrate()
            return
        u, v = geometry.to_viewbox(x, y, geometry.glyph_origin(t, self.cfg.scale, pill))
        self.scene.ripple(u, v, now)  # clicking the pill toggles pause, with a ripple (spec §8.4)
        self.on_toggle_pause()
        self._kick()
