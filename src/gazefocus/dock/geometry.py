"""Dock sizes and placement (spec §8.1, §8.4, §9). Logical px (Qt's units) unless a name ends in `_px`. Pure.

The window is sized once for the largest panel and never moves; the pill is drawn inside it and
morphs between the collapsed size and a panel (`openness` 0..1, overshooting with the spring).
There are three panels: the hover panel ("status") and the calibration's intro and result.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

BASE = (44.0, 20.0)  # the collapsed pill at scale 1
TOP_GAP = 4.0  # under the top edge of the work area
MARGIN = 16.0  # around the panel, for the shadow
VIEWBOX = (88.0, 40.0)  # the glyph's coordinate system (the mockup's SVG)


@dataclass(frozen=True)
class PanelSize:
    w: float
    h: float
    r: float  # corner radius
    glyph_w: float  # the glyph's width at the top of the open panel
    content_top: float  # where the content starts, below the glyph


PANELS = {
    "status": PanelSize(300.0, 158.0, 26.0, 77.0, 41.0),  # the glyph at the mockup's scale 1.75
    "intro": PanelSize(300.0, 150.0, 24.0, 36.0, 24.0),  # mockup 03: a small glyph, the content from 24 px
    "result": PanelSize(372.0, 200.0, 26.0, 36.0, 24.0),
}
PANEL = (PANELS["status"].w, PANELS["status"].h)
PANEL_RADIUS = PANELS["status"].r
PANEL_GLYPH_W = PANELS["status"].glyph_w


def mix(a: PanelSize, b: PanelSize, t: float) -> PanelSize:
    """A panel part-way between two others (the pill morphing from the hover panel to the intro)."""
    if t >= 1:
        return b
    return PanelSize(*(lerp(x, y, t) for x, y in zip(vars(a).values(), vars(b).values())))


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
    pw, ph = max(p.w for p in PANELS.values()), max(p.h for p in PANELS.values())
    return max(pw, w) + 2 * MARGIN, TOP_GAP + max(ph, h) + MARGIN


def placement(work: tuple[int, int, int, int], scale: float) -> tuple[int, int, int, int]:
    """(x, y, w, h) of the window: top centre of a work area given as (left, top, right, bottom)."""
    w, h = window_size(scale)
    left, top, right, _ = work
    return round((left + right) / 2 - w / 2), top, math.ceil(w), math.ceil(h)


def pill_at(openness: float, scale: float, window_w: float, panel: PanelSize = PANELS["status"]) -> Pill:
    pw, ph = pill_size(scale)
    w, h = lerp(pw, panel.w, openness), lerp(ph, panel.h, openness)
    r = min(lerp(ph / 2, panel.r, max(0.0, min(1.0, openness))), h / 2)
    return Pill(window_w / 2, TOP_GAP + h / 2, w / 2, h / 2, r)


def glyph_origin(openness: float, scale: float, pill: Pill,
                 panel: PanelSize = PANELS["status"]) -> tuple[float, float, float]:
    """(x0, y0, k): where the viewBox's (0, 0) sits and how many logical px one unit is.

    Collapsed, the glyph fills the pill; open, it stays centred at the top and shrinks to the
    mockup's size, with the panel's content below it (as in the approved mockup).
    """
    t = max(0.0, min(1.0, openness))
    k = lerp(pill_size(scale)[0] / VIEWBOX[0], panel.glyph_w / VIEWBOX[0], t)
    return pill.cx - VIEWBOX[0] * k / 2, pill.top, k


def to_viewbox(x: float, y: float, origin: tuple[float, float, float]) -> tuple[float, float]:
    x0, y0, k = origin
    return (x - x0) / k, (y - y0) / k
