"""Draws the dock glyph from a GlyphFrame: two tiles, water, lid, pause bars, "!" and the effects.

The water, the flow's droplets and the falling drops form one "goo" layer: a signed-distance field
merged with a smooth minimum, so drops melt into the water like the mockup's blur-and-threshold SVG
filter (spec §8.1). Everything else is antialiased QPainter strokes and fills in viewBox units.
"""

from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen

from gazefocus.dock.scene import AMBER, GREEN, INSET, TILES, GlyphFrame

GOO_K = 1.2  # the smooth minimum's radius (viewBox units); the mockup's goo filter blurs by 1.05
OUTLINE_R, OUTLINE_W, CLIP_R, LID_W = 3.6, 1.3, 2.2, 1.25
GLYPH = {False: (28, 28, 32, 0.82), True: (255, 255, 255, 0.88)}  # var(--glyph), keyed by dark
GOO_BOX = (0.0, -8.0, 88.0, 40.0)  # u0, v0, u1, v1: the tiles plus room above for the flow's arc
FAR = 1e6


def water_rgb(frame: GlyphFrame, dark: bool) -> tuple[int, int, int]:
    g, a, t = GREEN[dark], AMBER[dark], frame.amber
    return tuple(round(g[i] + (a[i] - g[i]) * t) for i in range(3))


def smin(a: np.ndarray, b: np.ndarray, k: float) -> np.ndarray:
    """Polynomial smooth minimum: the union of two shapes with a rounded, gooey join."""
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b * (1 - h) + a * h - k * h * (1 - h)


def _rounded_box(u, v, cx, cy, hw, hh, r):
    qx, qy = np.abs(u - cx) - (hw - r), np.abs(v - cy) - (hh - r)
    return np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r


def goo_field(frame: GlyphFrame, px_per_unit: float) -> np.ndarray | None:
    """Signed distance (viewBox units) to the water and drops over GOO_BOX, or None if there are none."""
    u0, v0, u1, v1 = GOO_BOX
    w, h = max(1, math.ceil((u1 - u0) * px_per_unit)), max(1, math.ceil((v1 - v0) * px_per_unit))
    vv, uu = np.mgrid[0:h, 0:w].astype(np.float32)
    u, v = u0 + (uu + 0.5) / px_per_unit, v0 + (vv + 0.5) / px_per_unit
    d, any_shape = np.full((h, w), FAR, np.float32), False
    for zone, tf in frame.tiles.items():
        if tf.fill <= 0.001:
            continue
        x, y, tw, th = TILES[zone]
        cx, cy, s = x + tw / 2, y + th / 2, tf.scale
        tu, tv = cx + (u - cx) / s, cy + (v - cy) / s  # into the tile's own (unscaled) coordinates
        clip = _rounded_box(tu, tv, cx, cy, tw / 2 - INSET, th / 2 - INSET, CLIP_R)
        wx0, wx1 = x + INSET - 0.5, x + tw - INSET + 0.5
        surface = tf.level + tf.amp * np.sin((tu - wx0) / (wx1 - wx0) * math.pi * 2.4 + tf.phase)
        d = smin(d, np.maximum(clip, surface - tv) * s, GOO_K)
        any_shape = True
    for x, y, r in (*frame.drops, *frame.parts):
        if r > 0.05:
            d = smin(d, np.hypot(u - x, v - y) - r, GOO_K)
            any_shape = True
    return d if any_shape else None


def goo_image(frame: GlyphFrame, px_per_unit: float, rgb: tuple[int, int, int]) -> QImage | None:
    d = goo_field(frame, px_per_unit)
    if d is None:
        return None
    cov = np.clip(0.5 - d * px_per_unit, 0, 1)
    h, w = cov.shape
    buf = np.empty((h, w, 4), np.uint8)
    buf[..., 0], buf[..., 1], buf[..., 2] = cov * rgb[2], cov * rgb[1], cov * rgb[0]  # premultiplied BGRA
    buf[..., 3] = cov * 255
    return QImage(buf.data, w, h, 4 * w, QImage.Format_ARGB32_Premultiplied).copy()


def _qcolor(rgba: tuple, alpha: float = 1.0) -> QColor:
    r, g, b, a = rgba if len(rgba) == 4 else (*rgba, 1.0)
    return QColor(r, g, b, max(0, min(255, round(255 * a * alpha))))


def _tile_transform(p: QPainter, zone, scale: float) -> None:
    x, y, w, h = TILES[zone]
    cx, cy = x + w / 2, y + h / 2
    p.translate(cx, cy)
    p.scale(scale, scale)
    p.translate(-cx, -cy)


def draw_glyph(p: QPainter, frame: GlyphFrame, origin: tuple[float, float, float], *, dark: bool, dpr: float) -> None:
    """Paint the glyph with the viewBox's (0, 0) at origin[0:2] and one unit = origin[2] logical px."""
    x0, y0, k = origin
    stroke, rgb = GLYPH[dark], water_rgb(frame, dark)
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.translate(x0, y0)
    p.scale(k, k)

    for zone, tf in frame.tiles.items():  # outlines
        x, y, w, h = TILES[zone]
        p.save()
        _tile_transform(p, zone, tf.scale)
        p.setPen(QPen(_qcolor(stroke, frame.outline), OUTLINE_W))  # var(--glyph) x the outline's opacity
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(x, y, w, h), OUTLINE_R, OUTLINE_R)
        p.restore()

    img = goo_image(frame, k * dpr, rgb)  # the water and drops, at the screen's resolution
    if img is not None:
        u0, v0, u1, v1 = GOO_BOX
        p.drawImage(QRectF(u0, v0, u1 - u0, v1 - v0), img)

    p.setPen(Qt.NoPen)
    for zone, tf in frame.tiles.items():  # the water's highlight
        if tf.fill > 0.03:
            x, y, w, h = TILES[zone]
            p.save()
            _tile_transform(p, zone, tf.scale)
            p.setBrush(_qcolor((255, 255, 255), 0.6 * min(1.0, tf.fill * 2)))
            p.drawEllipse(QPointF(x + INSET + 3.4, tf.level + 1.5), 2.4, 0.8)
            p.restore()
    p.setBrush(_qcolor((255, 255, 255), 0.75))
    for x, y, r in frame.drops:
        if r > 1.6:
            p.drawEllipse(QPointF(x - r * 0.3, y - r * 0.4), r * 0.22, r * 0.22)

    for zone, tf in frame.tiles.items():  # the typing lid
        if tf.lid > 0.01:
            x, y, w, h = TILES[zone]
            p.save()
            _tile_transform(p, zone, tf.scale)
            pen = QPen(_qcolor(stroke, tf.lid), LID_W)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawLine(QPointF(x + 2.6, y + 2.5), QPointF(x + w - 2.6, y + 2.5))
            p.restore()

    p.setPen(Qt.NoPen)
    for x, y, r, o in frame.steam:
        p.setBrush(_qcolor(rgb, o))
        p.drawEllipse(QPointF(x, y), r, r)
    p.setBrush(Qt.NoBrush)
    for x, y, r, o in frame.ripples:
        p.setPen(QPen(_qcolor(stroke, o), 0.8))
        p.drawEllipse(QPointF(x, y), r, r)

    p.setPen(Qt.NoPen)
    if frame.pause > 0.01:  # the pause bars
        p.setBrush(_qcolor(stroke, frame.pause))
        p.drawRoundedRect(QRectF(40.2, 13.5, 2.8, 10), 1.1, 1.1)
        p.drawRoundedRect(QRectF(45.0, 13.5, 2.8, 10), 1.1, 1.1)
    if frame.alert > 0.01:  # "!": camera off, not calibrated, error
        p.setBrush(_qcolor(AMBER[dark], frame.alert))
        p.drawRoundedRect(QRectF(42.6, 11.8, 2.8, 8.4), 1.2, 1.2)
        p.drawEllipse(QPointF(44.0, 23.4), 1.55, 1.55)
    p.restore()
