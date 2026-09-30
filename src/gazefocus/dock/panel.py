"""The open panel's content (spec §8.4): camera preview, state title, numbers, Pause and Recalibrate.

Layout is the approved mockup's (at openness 1, relative to the panel's top-left, logical px):
content from 12 px in and 41 px down; a 112 px preview on the left; the info column 11 px after it.
The preview is mirrored, like `gazefocus live`, with the face box and the head-direction ray.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen

PREVIEW = QRectF(12, 41, 112, 105)
PREVIEW_R = 12.0
INFO_X, TITLE_Y, DETAIL_Y = 135.0, 42.0, 62.0
BUTTONS = {"pause": QRectF(135, 120, 62, 24), "recalibrate": QRectF(203, 120, 85, 24)}
TEXT = {False: QColor(28, 28, 30), True: QColor(245, 245, 247)}  # var(--text), keyed by dark
SUB = {False: QColor(60, 60, 67, 184), True: QColor(235, 235, 245, 158)}  # var(--sub)
BTN = {False: QColor(0, 0, 0, 18), True: QColor(255, 255, 255, 31)}  # var(--btn)
FACE_GREEN, RAY_BLUE = QColor(48, 209, 88), QColor(10, 132, 255)


@dataclass(frozen=True)
class PanelContent:
    title: str
    detail: str
    pause_label: str  # "Pause" or "Resume"
    preview: QImage | None = None  # the camera frame (unmirrored), only while the panel is open
    face_box: tuple[float, float, float, float] | None = None  # x0, y0, x1, y1 in 0..1 camera coordinates
    nose: tuple[float, float] | None = None
    yaw: float = 0.0
    pitch: float = 0.0
    caption: str = ""  # bottom-left of the preview, e.g. "face ✓ · 15 fps"


def preview_image(bgr: np.ndarray) -> QImage:
    """A camera frame (BGR, H x W x 3) as a QImage that owns its pixels."""
    h, w = bgr.shape[:2]
    return QImage(np.ascontiguousarray(bgr).data, w, h, 3 * w, QImage.Format_BGR888).copy()


def button_at(x: float, y: float, left: float, top: float) -> str | None:
    """Which button (if any) is under a point, given the panel's top-left."""
    for name, r in BUTTONS.items():
        if r.translated(left, top).contains(QPointF(x, y)):
            return name
    return None


def _font(size_px: float, weight=QFont.Normal, family: str = "Segoe UI Variable Text") -> QFont:
    f = QFont(family)
    f.setPixelSize(max(1, round(size_px)))
    f.setWeight(weight)
    return f


def _cover(src_w: int, src_h: int, dst: QRectF) -> QRectF:
    """The source rect that fills `dst` without distortion (cropping the long side), in source px."""
    scale = max(dst.width() / src_w, dst.height() / src_h)
    w, h = dst.width() / scale, dst.height() / scale
    return QRectF((src_w - w) / 2, (src_h - h) / 2, w, h)


def draw_preview(p: QPainter, rect: QRectF, content: PanelContent) -> None:
    clip = QPainterPath()
    clip.addRoundedRect(rect, PREVIEW_R, PREVIEW_R)
    p.save()
    p.setClipPath(clip)
    bg = QLinearGradient(rect.topLeft(), rect.bottomRight())
    bg.setColorAt(0, QColor("#3a3f4a"))
    bg.setColorAt(1, QColor("#15171c"))
    p.fillRect(rect, bg)
    img = content.preview
    if img is not None and not img.isNull():
        src = _cover(img.width(), img.height(), rect)
        p.save()  # mirrored, like looking in a mirror (and like `gazefocus live`)
        p.translate(rect.left() + rect.width(), rect.top())
        p.scale(-1, 1)
        p.drawImage(QRectF(0, 0, rect.width(), rect.height()), img, src)
        p.restore()

        def to_rect(nx: float, ny: float) -> QPointF:  # 0..1 camera coordinates -> the mirrored preview
            sx = (nx * img.width() - src.left()) / src.width()
            sy = (ny * img.height() - src.top()) / src.height()
            return QPointF(rect.left() + (1 - sx) * rect.width(), rect.top() + sy * rect.height())

        if content.face_box is not None:
            x0, y0, x1, y1 = content.face_box
            a, b = to_rect(x0, y0), to_rect(x1, y1)
            box = QRectF(QPointF(min(a.x(), b.x()), a.y()), QPointF(max(a.x(), b.x()), b.y()))
            p.setPen(QPen(FACE_GREEN, 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(box, 6, 6)
        if content.nose is not None:
            n = to_rect(*content.nose)
            tip = QPointF(n.x() - math.sin(math.radians(content.yaw)) * 28,
                          n.y() + math.sin(math.radians(content.pitch)) * 28)
            pen = QPen(RAY_BLUE, 2)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawLine(n, tip)
    if content.caption:
        p.setPen(QColor(255, 255, 255, 184))
        p.setFont(_font(10, family="Cascadia Mono"))
        p.drawText(QRectF(rect.left() + 7, rect.bottom() - 17, rect.width() - 10, 14), Qt.AlignLeft, content.caption)
    p.restore()


def draw_panel(p: QPainter, left: float, top: float, content: PanelContent, *, opacity: float, dark: bool) -> None:
    if opacity <= 0.01:
        return
    p.save()
    p.setOpacity(opacity)
    p.translate(left, top + (1 - opacity) * -8)  # it slides into place as it fades in
    p.setRenderHint(QPainter.Antialiasing)
    draw_preview(p, PREVIEW, content)
    p.setPen(TEXT[dark])
    p.setFont(_font(13, QFont.DemiBold, "Segoe UI Variable Display"))
    p.drawText(QRectF(INFO_X, TITLE_Y, 288 - INFO_X, 18), Qt.AlignLeft | Qt.AlignVCenter, content.title)
    p.setPen(SUB[dark])
    p.setFont(_font(10.5, family="Cascadia Mono"))
    p.drawText(QRectF(INFO_X, DETAIL_Y, 288 - INFO_X, 54), Qt.AlignLeft | Qt.AlignTop, content.detail)
    for name, r in BUTTONS.items():
        path = QPainterPath()
        path.addRoundedRect(r, r.height() / 2, r.height() / 2)
        p.fillPath(path, BTN[dark])
        p.setPen(QPen(QColor(127, 127, 127, 77), 0.5))
        p.drawPath(path)
        p.setPen(TEXT[dark])
        p.setFont(_font(11.5, QFont.Medium))
        p.drawText(r, Qt.AlignCenter, content.pause_label if name == "pause" else "Recalibrate")
    p.restore()
