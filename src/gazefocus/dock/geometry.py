"""Dock sizes and placement (spec §8.1, §8.4). Logical px (Qt's units) unless a name ends in `_px`. Pure.

The window is sized once for the open panel and never moves; the pill is drawn inside it and
morphs between the collapsed size and the panel (`openness` 0..1, overshooting with the spring).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

BASE = (44.0, 20.0)  # the collapsed pill at scale 1
PANEL = (300.0, 158.0)
PANEL_RADIUS = 26.0
TOP_GAP = 4.0  # under the top edge of the work area
MARGIN = 16.0  # around the panel, for the shadow
VIEWBOX = (88.0, 40.0)  # the glyph's coordinate system (the mockup's SVG)
PANEL_GLYPH_W = 77.0  # the glyph's width inside the open panel (the mockup's scale 1.75)


@dataclass(frozen=True)
class Pill:
    cx: float
    cy: float
    hw: float  # half width
    hh: float  # half height
    r: float  # corner radius

    def scaled(self, k: float) -> "Pill":
        return Pill(self.cx * k, self.cy * k, self.hw * k, self.hh * k, self.r * k)

    def sdf(self, x: float, y: float) -> float:
        """Signed distance to the rounded box: negative inside."""
        qx, qy = abs(x - self.cx) - (self.hw - self.r), abs(y - self.cy) - (self.hh - self.r)
        return math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - self.r

    def contains(self, x: float, y: float) -> bool:
        return self.sdf(x, y) <= 0

    @property
    def left(self) -> float:
        return self.cx - self.hw

    @property
    def top(self) -> float:
        return self.cy - self.hh


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def pill_size(scale: float) -> tuple[float, float]:
    return BASE[0] * scale, BASE[1] * scale


def window_size(scale: float) -> tuple[float, float]:
    w, h = pill_size(scale)
    return max(PANEL[0], w) + 2 * MARGIN, TOP_GAP + max(PANEL[1], h) + MARGIN


def placement(work: tuple[int, int, int, int], scale: float) -> tuple[int, int, int, int]:
    """(x, y, w, h) of the window: top centre of a work area given as (left, top, right, bottom)."""
    w, h = window_size(scale)
    left, top, right, _ = work
    return round((left + right) / 2 - w / 2), top, math.ceil(w), math.ceil(h)


def pill_at(openness: float, scale: float, window_w: float) -> Pill:
    pw, ph = pill_size(scale)
    w, h = lerp(pw, PANEL[0], openness), lerp(ph, PANEL[1], openness)
    r = min(lerp(ph / 2, PANEL_RADIUS, max(0.0, min(1.0, openness))), h / 2)
    return Pill(window_w / 2, TOP_GAP + h / 2, w / 2, h / 2, r)


def glyph_origin(openness: float, scale: float, pill: Pill) -> tuple[float, float, float]:
    """(x0, y0, k): where the viewBox's (0, 0) sits and how many logical px one unit is.

    Collapsed, the glyph fills the pill; open, it stays centred at the top and shrinks to the
    mockup's size, with the panel's content below it (as in the approved mockup).
    """
    t = max(0.0, min(1.0, openness))
    k = lerp(pill_size(scale)[0] / VIEWBOX[0], PANEL_GLYPH_W / VIEWBOX[0], t)
    return pill.cx - VIEWBOX[0] * k / 2, pill.top, k


def to_viewbox(x: float, y: float, origin: tuple[float, float, float]) -> tuple[float, float]:
    x0, y0, k = origin
    return (x - x0) / k, (y - y0) / k
