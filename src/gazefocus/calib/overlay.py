"""The calibration overlay (spec §9): dimmed screens, the drop and its progress ring, and the cards.

Every window is click-through, never takes focus and floats above everything; the app lifts the dock
back above it with `capture.keep_on_top` after `open`. The session decides where everything is; this
module only draws a frame, with the mockup's CSS transitions as time-based fades:
  DimWindow   one per screen: plain black with a uniform window opacity (no per-pixel repaint)
  CardWindow  one per screen: dark glass rendered from a grab of what is behind it
  DropWindow  one small per-pixel-alpha window that follows the drop
The drop and the cards are excluded from capture, so neither ends up in the other's (or the dock's) glass.
"""

from __future__ import annotations

import ctypes
import math
from ctypes import wintypes
from typing import Callable

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from gazefocus.calib.path import Rect
from gazefocus.calib.session import Card, DropState, OverlayFrame
from gazefocus.dock import glass
from gazefocus.dock.geometry import Pill
from gazefocus.dock.motion import Channel, cubic_bezier

FLAGS = (Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
         | Qt.WindowTransparentForInput)
DROP_WINDOW = 70  # logical px: the ring (44) and the stretched drop's glow fit inside
DROP_R, GLOW = 9.0, 14.0
RING_R, RING_W = 17.0, 2.0
DIM_FADE_S, RING_FADE_S, CARD_FADE_S, CARD_MOVE_S = 0.6, 0.25, 0.35, 0.5
CSS_EASE = cubic_bezier(0.25, 0.1, 0.25, 1.0)  # CSS `ease`, the transitions' default
CARD_SPRING = cubic_bezier(0.3, 1.4, 0.5, 1.0)
CARD_AT = (0.5, 0.31)  # the card's centre, as a fraction of its screen
CARD_MIN_W, CARD_PAD_Y, CARD_PAD_X, CARD_R, CARD_GAP = 220.0, 14.0, 18.0, 20.0, 3.0
CARD_MARGIN = 30.0  # around the card, for its shadow
CARD_TINT = 0.26  # glass.render's openness: a dark tint of ~.42, the mockup's rgba(40,40,48,.42)
BODY = ((0.0, "#e9fff0"), (0.14, "#e9fff0"), (0.32, "#6ee58f"), (0.55, "#30d158"), (1.0, "#1c8f3f"))


def _font(size_px: float, weight=QFont.Normal) -> QFont:
    f = QFont("Segoe UI Variable Text")
    f.setPixelSize(round(size_px))
    f.setWeight(weight)
    return f


class _Floating(QWidget):
    def __init__(self, native: bool, *, translucent: bool = True, exclude: bool = False) -> None:
        super().__init__(None, FLAGS)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        if translucent:
            self.setAttribute(Qt.WA_TranslucentBackground)
        self.native = native and QGuiApplication.platformName() == "windows"  # never on the test platform
        self._exclude = exclude

    def showEvent(self, e) -> None:
        super().showEvent(e)
        if self.native:
            from gazefocus.win.capture import exclude_from_capture, make_noactivate

            hwnd = int(self.winId())
            make_noactivate(hwnd)
            if self._exclude:
                exclude_from_capture(hwnd)

    def _physical(self) -> tuple[int, int, int, int, float]:
        dpr = self.devicePixelRatioF()
        if self.native:
            from gazefocus.win import _api

            r = wintypes.RECT()
            _api.user32.GetWindowRect(int(self.winId()), ctypes.byref(r))
            return r.left, r.top, r.right - r.left, r.bottom - r.top, dpr
        return round(self.x() * dpr), round(self.y() * dpr), round(self.width() * dpr), round(self.height() * dpr), dpr


class DimWindow(_Floating):
    """Black over a whole screen; only its window opacity changes, which the compositor applies for free."""

    def __init__(self, rect: Rect, native: bool) -> None:
        super().__init__(native, translucent=False)
        x, y, w, h = rect
        self.setGeometry(math.floor(x), math.floor(y), math.ceil(w), math.ceil(h))
        self.alpha = Channel(0.0)
        self.setWindowOpacity(0.0)

    def set_target(self, alpha: float, now: float) -> None:
        if abs(alpha - self.alpha.target) > 1e-9:
            self.alpha.to(alpha, now, DIM_FADE_S, CSS_EASE)

    def tick(self, now: float) -> None:
        a = self.alpha.get(now)
        if abs(a - self.windowOpacity()) > 1e-4:
            self.setWindowOpacity(a)

    def busy(self, now: float) -> bool:
        return self.alpha.busy(now)

    def paintEvent(self, e) -> None:
        QPainter(self).fillRect(self.rect(), Qt.black)


def draw_drop(p: QPainter, cx: float, cy: float, drop: DropState, *, progress: float, ring_alpha: float) -> None:
    """The ring (the tour's progress, from 12 o'clock) and the glowing green drop, centred at (cx, cy)."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    if ring_alpha > 0:
        p.setOpacity(ring_alpha)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 64), RING_W))
        p.drawEllipse(QPointF(cx, cy), RING_R, RING_R)
        if progress > 0:
            p.setPen(QPen(QColor(255, 255, 255), RING_W, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(QRectF(cx - RING_R, cy - RING_R, 2 * RING_R, 2 * RING_R), 90 * 16, -round(min(1.0, progress) * 360 * 16))
    if drop.opacity > 0:
        p.setOpacity(drop.opacity)
        p.translate(cx, cy)
        p.rotate(drop.angle)
        p.scale(drop.along, drop.across)
        p.setPen(Qt.NoPen)
        edge = DROP_R / (DROP_R + GLOW)
        glow = QRadialGradient(0, 0, DROP_R + GLOW)  # 0 0 14px rgba(48,209,88,.65)
        glow.setColorAt(0, QColor(48, 209, 88, 166))
        glow.setColorAt(edge, QColor(48, 209, 88, 83))
        glow.setColorAt(1, QColor(48, 209, 88, 0))
        p.setBrush(glow)
        p.drawEllipse(QPointF(0, 0), DROP_R + GLOW, DROP_R + GLOW)
        rim = QRadialGradient(0, 0, DROP_R + 3)  # 0 0 3px rgba(0,0,0,.3)
        rim.setColorAt(DROP_R / (DROP_R + 3), QColor(0, 0, 0, 38))
        rim.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(rim)
        p.drawEllipse(QPointF(0, 0), DROP_R + 3, DROP_R + 3)
        # radial-gradient(circle at 34% 30%, ...): its radius reaches the farthest corner of the 18 px box
        fx, fy = -DROP_R + 0.34 * 2 * DROP_R, -DROP_R + 0.30 * 2 * DROP_R
        body = QRadialGradient(fx, fy, math.hypot(DROP_R - fx, DROP_R - fy))
        for at, colour in BODY:
            body.setColorAt(at, QColor(colour))
        p.setBrush(body)
        p.drawEllipse(QPointF(0, 0), DROP_R, DROP_R)
        clip = QPainterPath()
        clip.addEllipse(QPointF(0, 0), DROP_R, DROP_R)
        p.setClipPath(clip)
        shade = QLinearGradient(0, DROP_R - 5, 0, DROP_R)  # inset 0 -2px 3px rgba(0,60,20,.35)
        shade.setColorAt(0, QColor(0, 60, 20, 0))
        shade.setColorAt(1, QColor(0, 60, 20, 89))
        p.setBrush(shade)
        p.drawRect(QRectF(-DROP_R, -DROP_R, 2 * DROP_R, 2 * DROP_R))
    p.restore()


class DropWindow(_Floating):
    """A small window carrying the drop and its ring; it moves with the drop every frame."""

    def __init__(self, native: bool) -> None:
        super().__init__(native, exclude=True)
        self.resize(DROP_WINDOW, DROP_WINDOW)
        self.state = DropState(0.0, 0.0, 0.0)
        self.progress = 0.0
        self.ring_alpha = Channel(0.0)
        self._ring = 0.0
        self.frac = (0.0, 0.0)  # the drop's sub-pixel offset inside the window

    def set_frame(self, drop: DropState, ring: float | None, now: float) -> None:
        shown = ring is not None
        if shown != (self.ring_alpha.target > 0.5):
            self.ring_alpha.to(1.0 if shown else 0.0, now, RING_FADE_S, CSS_EASE)
        if shown:
            self.progress = ring
        self.state, self._ring = drop, self.ring_alpha.get(now)
        fx, fy = math.floor(drop.x), math.floor(drop.y)
        self.frac = (drop.x - fx, drop.y - fy)
        half = DROP_WINDOW // 2
        if (self.x(), self.y()) != (fx - half, fy - half):
            self.move(fx - half, fy - half)
        self.update()

    def busy(self, now: float) -> bool:
        return self.ring_alpha.busy(now)

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.fillRect(self.rect(), Qt.transparent)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        half = DROP_WINDOW // 2
        draw_drop(p, half + self.frac[0], half + self.frac[1], self.state, progress=self.progress, ring_alpha=self._ring)


class CardWindow(_Floating):
    """The glass card on one screen: it fades in rising and growing (.96 -> 1), and fades out sinking."""

    def __init__(self, screen: Rect, *, native: bool, grabber_factory: Callable[[int, int], object],
                 refraction: bool) -> None:
        super().__init__(native, exclude=True)
        self.screen_rect, self.refraction = screen, refraction
        self.card: Card | None = None
        self.opacity, self.rise = Channel(0.0), Channel(0.0)
        self._rise = 0.0
        self.img: QImage | None = None
        self._factory, self._grabber, self._grid, self._out = grabber_factory, None, None, None
        self._size = (CARD_MIN_W, 60.0)
        self.resize(round(CARD_MIN_W + 2 * CARD_MARGIN), 120)
        self.setWindowOpacity(0.0)

    def set_card(self, card: Card | None, now: float) -> None:
        if card == self.card:
            return
        if card is not None:
            self._layout(card)
            self._render(card)
            if self.card is None:
                self.opacity.to(1.0, now, CARD_FADE_S, CSS_EASE)
                self.rise.to(1.0, now, CARD_MOVE_S, CARD_SPRING)
        else:
            self.opacity.to(0.0, now, CARD_FADE_S, CSS_EASE)
            self.rise.to(0.0, now, CARD_MOVE_S, CARD_SPRING)
        self.card = card

    def tick(self, now: float) -> None:
        a = self.opacity.get(now)
        if abs(a - self.windowOpacity()) > 1e-4:
            self.setWindowOpacity(a)
        r = self.rise.get(now)
        if r != self._rise:
            self._rise = r
            self.update()

    def busy(self, now: float) -> bool:
        return self.opacity.busy(now) or self.rise.busy(now)

    def _layout(self, card: Card) -> None:
        title, sub = QFontMetricsF(_font(15, QFont.Bold)), QFontMetricsF(_font(12))
        cw = max(CARD_MIN_W, max(title.horizontalAdvance(card.title), sub.horizontalAdvance(card.subtitle)) + 2 * CARD_PAD_X)
        ch = 2 * CARD_PAD_Y + title.height() + CARD_GAP + sub.height()
        self._size = (cw, ch)
        sx, sy, sw, sh = self.screen_rect
        cx, cy = sx + CARD_AT[0] * sw, sy + CARD_AT[1] * sh
        w, h = math.ceil(cw + 2 * CARD_MARGIN), math.ceil(ch + 2 * CARD_MARGIN)
        self.setGeometry(round(cx - w / 2), round(cy - h / 2), w, h)

    def _render(self, card: Card) -> None:
        px, py, w, h, dpr = self._physical()
        if self._grabber is None or (self._grabber.w, self._grabber.h) != (w, h):
            if self._grabber is not None:
                self._grabber.close()
            self._grabber = self._factory(w, h)
            self._grid, self._out = glass.Grid(w, h), np.zeros((h, w, 4), np.uint8)
        backdrop = glass.prepare(self._grabber.grab(px, py), dpr, self.refraction)
        cw, ch = self._size
        pill = Pill(self.width() / 2, self.height() / 2, cw / 2, ch / 2, CARD_R).scaled(dpr)
        glass.render(backdrop, pill, dpr=dpr, dark=True, openness=CARD_TINT, refraction=self.refraction,
                     step=1, grid=self._grid, out=self._out)
        img = QImage(self._out.data, w, h, 4 * w, QImage.Format_ARGB32_Premultiplied).copy()
        img.setDevicePixelRatio(dpr)
        p = QPainter(img)
        p.setRenderHint(QPainter.TextAntialiasing)
        top = self.height() / 2 - ch / 2 + CARD_PAD_Y
        tf, sf = _font(15, QFont.Bold), _font(12)
        th = QFontMetricsF(tf).height()
        p.setPen(QColor(255, 255, 255))
        p.setFont(tf)
        p.drawText(QRectF(0, top, self.width(), th), Qt.AlignHCenter | Qt.AlignTop, card.title)
        p.setPen(QColor(255, 255, 255, 204))
        p.setFont(sf)
        p.drawText(QRectF(0, top + th + CARD_GAP, self.width(), QFontMetricsF(sf).height()),
                   Qt.AlignHCenter | Qt.AlignTop, card.subtitle)
        p.end()
        self.img = img
        self.update()

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.fillRect(self.rect(), Qt.transparent)
        if self.img is None:
            return
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        cx, cy = self.width() / 2, self.height() / 2
        s = 0.96 + 0.04 * self._rise
        p.translate(cx, cy + (1 - self._rise) * 0.06 * self._size[1])  # translate(-50%, -44%) -> (-50%, -50%)
        p.scale(s, s)
        p.translate(-cx, -cy)
        p.drawImage(0, 0, self.img)

    def close(self) -> bool:
        if self._grabber is not None:
            self._grabber.close()
            self._grabber = None
        return super().close()


class Overlay:
    """All of the calibration's windows. `open`, then `show(frame, now)` on every vsync, then `hide`."""

    def __init__(self, screens: dict[str, Rect], *, native: bool = True,
                 grabber_factory: Callable[[int, int], object] | None = None, refraction: bool = True) -> None:
        if grabber_factory is None:
            from gazefocus.win.capture import Grabber

            grabber_factory = Grabber
        self.screens, self.native = dict(screens), native
        self._factory, self._refraction = grabber_factory, refraction
        self.dims: dict[str, DimWindow] = {}
        self.cards: dict[str, CardWindow] = {}
        self.drop: DropWindow | None = None

    @property
    def is_open(self) -> bool:
        return self.drop is not None

    def _windows(self) -> list[QWidget]:
        return [*self.dims.values(), *self.cards.values(), *([self.drop] if self.drop is not None else [])]

    def open(self) -> None:
        if self.is_open:
            return
        self.dims = {n: DimWindow(r, self.native) for n, r in self.screens.items()}
        self.cards = {n: CardWindow(r, native=self.native, grabber_factory=self._factory, refraction=self._refraction)
                      for n, r in self.screens.items()}
        self.drop = DropWindow(self.native)
        for w in self._windows():  # shown in z-order: the dims, the cards above them, the drop on top
            w.show()

    def show(self, frame: OverlayFrame, now: float) -> None:
        if not self.is_open:
            return
        for name, w in self.dims.items():
            w.set_target(frame.dims.get(name, 0.0), now)
            w.tick(now)
        for name, w in self.cards.items():
            w.set_card(frame.card if frame.card is not None and frame.card.screen == name else None, now)
            w.tick(now)
        self.drop.set_frame(frame.drop, frame.ring, now)

    def busy(self, now: float) -> bool:
        """A fade is still running (the app keeps ticking until the last one settles)."""
        return any(w.busy(now) for w in self._windows())

    def hide(self) -> None:
        for w in self._windows():
            w.close()
        self.dims, self.cards, self.drop = {}, {}, None
