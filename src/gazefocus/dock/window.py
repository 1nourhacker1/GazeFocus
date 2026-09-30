"""The dock window (spec §8): a Liquid Glass pill under the laptop camera, with the hover panel.

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
from gazefocus.dock.motion import EXPAND, Channel, ease_out
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
        self.cfg, self.clock = cfg, clock
        self.native = native and QGuiApplication.platformName() == "windows"  # never on the test platform
        self.on_toggle_pause, self.on_recalibrate, self.on_panel = on_toggle_pause, on_recalibrate, on_panel
        self.scene = GlyphScene(freeze_s=freeze_s, seed=seed)
        self.openness = Channel(0.0)
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
        return self.openness.target > 0.5

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
        step = 2 if self.openness.busy(now) else 1
        key = (round(t, 4), self.dark, step)
        if key != self._glass_key:
            pill_px = geometry.pill_at(t, self.cfg.scale, w / dpr).scaled(dpr)
            glass.render(self._backdrop, pill_px, dpr=dpr, dark=self.dark, openness=t,
                         refraction=self.cfg.refraction, step=step, grid=self._grid, out=self._out)
            img = QImage(self._out.data, w, h, 4 * w, QImage.Format_ARGB32_Premultiplied).copy()
            img.setDevicePixelRatio(dpr)
            self._glass_key, self._glass_img = key, img
        img = self._glass_img.copy()
        pill = geometry.pill_at(t, self.cfg.scale, w / dpr)
        p = QPainter(img)
        draw_glyph(p, self.scene.frame(now), geometry.glyph_origin(t, self.cfg.scale, pill), dark=self.dark, dpr=dpr)
        if t > 0.45:
            clip = QPainterPath()
            clip.addRoundedRect(QRectF(pill.left, pill.top, 2 * pill.hw, 2 * pill.hh), pill.r, pill.r)
            p.setClipPath(clip)  # the content is revealed as the pill grows
            draw_panel(p, pill.cx - geometry.PANEL[0] / 2, pill.top, self._content(),
                       opacity=min(1.0, (t - 0.45) / 0.4), dark=self.dark)
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
        fast = self.scene.fast(now) or self.openness.busy(now)
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
        self.openness.to(1.0, self.clock(), OPEN_S, EXPAND)
        self.on_panel(True)
        self._kick()

    def _close(self) -> None:
        self.openness.to(0.0, self.clock(), CLOSE_S, ease_out)
        self.preview = self.preview_sample = None  # frames are never kept once the panel is closed
        self.on_panel(False)
        self._kick()

    def enterEvent(self, e) -> None:
        self._leave.stop()
        if not self.panel_open:
            self._hover.start()

    def leaveEvent(self, e) -> None:
        self._hover.stop()
        if self.panel_open:
            self._leave.start()

    def mousePressEvent(self, e) -> None:
        if e.button() != Qt.LeftButton:
            return
        x, y, now = e.position().x(), e.position().y(), self.clock()
        t = self.openness.get(now)
        pill = geometry.pill_at(t, self.cfg.scale, self.width())
        if not pill.contains(x, y):
            return  # the shadow is ours to draw, not to act on
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
