"""The calibration's panels in the dock (spec §9, mockup 03): the intro, and the result with its scatter.

They are modal: they stay open until one of their buttons is pressed. Layout is the mockup's, relative
to the panel's top-left in logical px: content from 16 px in and 24 px down, under a small glyph.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen

from gazefocus.dock.panel import BTN, TEXT, _font

if TYPE_CHECKING:
    from gazefocus.calib.session import CalibrationResult

INTRO_TITLE = "Calibrate GazeFocus"
INTRO_TEXT = ("Sit the way you normally do. Follow the drop with your eyes and turn your head naturally. "
              "It takes about 15 seconds.")
INTRO_BUTTONS = {"start": QRectF(16, 108, 58, 24), "cancel": QRectF(80, 108, 72, 24)}
LABELS = {"start": "Start", "cancel": "Not now", "save": "Save", "redo": "Redo"}
PRIMARY = {"start", "save"}
BLUE = QColor(10, 132, 255)  # #0a84ff
SCATTER = QRectF(16, 24, 160, 110)
COL_X, COL_W = 188.0, 168.0  # the result's text column
EXTERNAL_BLUE, LAPTOP_PURPLE = QColor(10, 132, 255), QColor(191, 90, 242)  # #0a84ff, #bf5af2
METER_GREEN = QColor(40, 167, 69)  # #28a745
PLOT_PAD = 8.0  # the plot area inside the scatter's rounded rect (the mockup's 8..152 x 8..102)
PARA = {False: QColor(60, 60, 67, 204), True: QColor(235, 235, 245, 179)}  # rgba(60,60,67,.8)
HINT = {False: QColor(60, 60, 67, 191), True: QColor(235, 235, 245, 166)}  # rgba(60,60,67,.75)
PLOT_BG = {False: QColor(0, 0, 0, 13), True: QColor(255, 255, 255, 15)}


def result_buttons(can_save: bool) -> dict[str, QRectF]:
    if can_save:
        return {"save": QRectF(COL_X, 162, 54, 24), "redo": QRectF(COL_X + 60, 162, 58, 24)}
    return {"redo": QRectF(COL_X, 162, 58, 24)}


def modal_button_at(kind: str, x: float, y: float, left: float, top: float,
                    result: "CalibrationResult | None" = None) -> str | None:
    buttons = INTRO_BUTTONS if kind == "intro" else result_buttons(result is not None and result.can_save)
    for name, r in buttons.items():
        if r.translated(left, top).contains(QPointF(x, y)):
            return name
    return None


NAME_MAX = 12  # a long monitor name is cut, so the stats and labels fit


def stats_text(result: "CalibrationResult") -> str:
    """The mono stats: each screen's mean yaw / pitch, under its own name, in aligned columns."""
    m = result.model
    ext, lap = result.names["EXTERNAL"][:NAME_MAX], result.names["LAPTOP"][:NAME_MAX]
    w = max(len(ext), len(lap))
    return (f"yaw / pitch\n{ext:<{w}} {fmt_deg(m.mean_external[0])} / {fmt_deg(m.mean_external[1])}\n"
            f"{lap:<{w}} {fmt_deg(m.mean_laptop[0])} / {fmt_deg(m.mean_laptop[1])}")


def fmt_deg(v: float) -> str:
    """The mockup's `fm`: +29°, −4°, 0°."""
    sign = "+" if v > 0 else "−" if v < 0 else ""
    return f"{sign}{abs(round(v))}°"


def plot_map(result: "CalibrationResult") -> Callable[[float, float], tuple[float, float]]:
    """(yaw, pitch) -> a point in the scatter (relative to its top-left). Yaw runs so that the external monitor is on
    the left, whatever the sign of its yaw; pitch up is up. Both axes fit the samples, with a margin."""
    ext, lap = result.samples.get("EXTERNAL", []), result.samples.get("LAPTOP", [])
    sign = 1.0
    if ext and lap and sum(s.yaw for s in ext) / len(ext) > sum(s.yaw for s in lap) / len(lap):
        sign = -1.0
    xs = [sign * s.yaw for s in ext + lap] or [-10.0, 10.0]
    ys = [s.pitch for s in ext + lap] or [-10.0, 10.0]

    def span(vals: list[float]) -> tuple[float, float]:
        lo, hi = min(vals), max(vals)
        mid, half = (lo + hi) / 2, max(5.0, (hi - lo) / 2)
        return mid - half * 1.15, mid + half * 1.15

    (x0, x1), (y0, y1) = span(xs), span(ys)
    w, h = SCATTER.width() - 2 * PLOT_PAD, SCATTER.height() - 2 * PLOT_PAD

    def to_xy(yaw: float, pitch: float) -> tuple[float, float]:
        return PLOT_PAD + (sign * yaw - x0) / (x1 - x0) * w, PLOT_PAD + (y1 - pitch) / (y1 - y0) * h

    to_xy.sign = sign  # type: ignore[attr-defined]
    return to_xy


def _button(p: QPainter, r: QRectF, name: str, dark: bool) -> None:
    path = QPainterPath()
    path.addRoundedRect(r, r.height() / 2, r.height() / 2)
    primary = name in PRIMARY
    p.fillPath(path, BLUE if primary else BTN[dark])
    p.setPen(QPen(BLUE if primary else QColor(127, 127, 127, 77), 0.5))
    p.drawPath(path)
    p.setPen(QColor(255, 255, 255) if primary else TEXT[dark])
    p.setFont(_font(11.5, QFont.Medium))
    p.drawText(r, Qt.AlignCenter, LABELS[name])


def _begin(p: QPainter, left: float, top: float, opacity: float) -> bool:
    if opacity <= 0.01:
        return False
    p.save()
    p.setOpacity(opacity)
    p.translate(left, top + (1 - opacity) * -8)  # it slides into place as it fades in, like the hover panel
    p.setRenderHint(QPainter.Antialiasing)
    return True


def draw_intro(p: QPainter, left: float, top: float, *, opacity: float, dark: bool) -> None:
    if not _begin(p, left, top, opacity):
        return
    p.setPen(TEXT[dark])
    p.setFont(_font(14, QFont.Bold))
    p.drawText(QRectF(16, 24, 268, 18), Qt.AlignLeft | Qt.AlignVCenter, INTRO_TITLE)
    p.setPen(PARA[dark])
    p.setFont(_font(12))
    p.drawText(QRectF(16, 46, 268, 58), Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, INTRO_TEXT)
    for name, r in INTRO_BUTTONS.items():
        _button(p, r, name, dark)
    p.restore()


def _draw_scatter(p: QPainter, result: "CalibrationResult", dark: bool) -> None:
    p.save()
    p.translate(SCATTER.topLeft())
    box = QRectF(0, 0, SCATTER.width(), SCATTER.height())
    clip = QPainterPath()
    clip.addRoundedRect(box, 12, 12)
    p.setClipPath(clip)
    p.fillRect(box, PLOT_BG[dark])
    to_xy = plot_map(result)
    p.setPen(QPen(QColor(127, 127, 127, 60), 0.6))  # the axes, where zero is in view
    zx, zy = to_xy(0.0, 0.0)
    if 0 < zx < box.width():
        p.drawLine(QPointF(zx, PLOT_PAD), QPointF(zx, box.height() - PLOT_PAD))
    if 0 < zy < box.height():
        p.drawLine(QPointF(PLOT_PAD, zy), QPointF(box.width() - PLOT_PAD, zy))
    m = result.model
    if m is not None:  # the model's own boundary (margin 0) at the screens' mean iris position
        w0, w1, w2 = m.w
        c = -(m.b + w2 * (m.mean_external[2] + m.mean_laptop[2]) / 2)
        n2 = w0 * w0 + w1 * w1
        if n2 > 1e-12:
            px, py = c * w0 / n2, c * w1 / n2  # the line's point nearest the origin, in (yaw, pitch)
            d = math.sqrt(n2)
            a, b = to_xy(px - 1000 * w1 / d, py + 1000 * w0 / d), to_xy(px + 1000 * w1 / d, py - 1000 * w0 / d)
            pen = QPen(QColor(0, 0, 0, 115) if not dark else QColor(255, 255, 255, 115), 0.8)
            pen.setDashPattern([3 / 0.8, 2 / 0.8])
            p.setPen(pen)
            p.drawLine(QPointF(*a), QPointF(*b))
    p.setPen(Qt.NoPen)
    for key, colour in (("EXTERNAL", EXTERNAL_BLUE), ("LAPTOP", LAPTOP_PURPLE)):
        c = QColor(colour)
        c.setAlphaF(0.75)
        p.setBrush(c)
        for s in result.samples.get(key, []):
            p.drawEllipse(QPointF(*to_xy(s.yaw, s.pitch)), 1.6, 1.6)
    if m is not None:
        p.setPen(QColor(28, 28, 32, 204) if not dark else QColor(245, 245, 247, 204))
        f = _font(8, QFont.DemiBold)
        p.setFont(f)
        fm = QFontMetricsF(f)
        lx, ly = to_xy(m.mean_external[0], m.mean_external[1])
        rx, ry = to_xy(m.mean_laptop[0], m.mean_laptop[1])
        left, right = result.names["EXTERNAL"][:NAME_MAX], result.names["LAPTOP"][:NAME_MAX]
        lx = max(4.0, lx - 18 - fm.horizontalAdvance(left))
        rx = min(box.width() - 4 - fm.horizontalAdvance(right), rx + 18)
        p.drawText(QPointF(lx, ly + 3), left)
        p.drawText(QPointF(rx, ry + 3), right)
    p.restore()


def draw_result(p: QPainter, left: float, top: float, result: "CalibrationResult", *, opacity: float,
                dark: bool) -> None:
    if not _begin(p, left, top, opacity):
        return
    _draw_scatter(p, result, dark)
    x, m = COL_X, result.model
    p.setPen(TEXT[dark])
    p.setFont(_font(14, QFont.Bold))
    p.drawText(QRectF(x, 24, COL_W, 18), Qt.AlignLeft | Qt.AlignVCenter, result.title)
    if result.can_save:
        p.setPen(HINT[dark])
        p.setFont(_font(10.5, family="Cascadia Mono"))
        p.drawText(QRectF(x, 46, COL_W, 50), Qt.AlignLeft | Qt.AlignTop, stats_text(result))
    else:
        p.setPen(HINT[dark])
        p.setFont(_font(11))
        p.drawText(QRectF(x, 46, COL_W, 50), Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, result.message)
    if m is not None:
        p.setPen(TEXT[dark])
        p.setFont(_font(11.5))
        label = "Separation "
        p.drawText(QRectF(x, 99, COL_W, 16), Qt.AlignLeft | Qt.AlignVCenter, label)
        p.setFont(_font(11.5, QFont.Bold))
        lw = QFontMetricsF(_font(11.5)).horizontalAdvance(label)
        p.drawText(QRectF(x + lw, 99, COL_W - lw, 16), Qt.AlignLeft | Qt.AlignVCenter,
                   f"{m.separation:.1f}σ · {result.quality}")
        track = QPainterPath()
        track.addRoundedRect(QRectF(x, 119, COL_W, 6), 3, 3)
        p.fillPath(track, QColor(0, 0, 0, 20) if not dark else QColor(255, 255, 255, 26))
        fill = QPainterPath()
        fill.addRoundedRect(QRectF(x, 119, COL_W * min(1.0, m.separation / 8) * min(1.0, opacity), 6), 3, 3)
        p.fillPath(fill, METER_GREEN)
    if result.can_save:
        p.setPen(HINT[dark])
        p.setFont(_font(11))
        p.drawText(QRectF(x, 128, COL_W, 32), Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, result.message)
    for name, r in result_buttons(result.can_save).items():
        _button(p, r, name, dark)
    p.restore()
