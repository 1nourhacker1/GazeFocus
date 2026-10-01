"""The dock glyph's state machine: the approved mockup's animations (spec §8.2, §8.3), time-based and pure.

Coordinates are the mockup's SVG viewBox (88 x 40). `update(view, now)` turns a change of what the dock
should show into animations; `frame(now)` samples them. `busy(now)` says whether anything still moves:
there is no idle animation, so when nothing changes nothing is drawn.

The typing lid holds for `hold_s` after each key (normal typing never moves it), then melts linearly
and is gone exactly when the freeze ends: it shows the freeze countdown.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from gazefocus.dock.motion import (
    CALM,
    FROZEN,
    Channel,
    Drop,
    Ripple,
    Steam,
    Stream,
    Wave,
    ease_in,
    ease_in_out,
    ease_out,
    spring,
)
from gazefocus.dock.view import ALERT, PAUSED, TRACKING, DockView
from gazefocus.types import Zone

TILES = {Zone.EXTERNAL: (18.0, 10.0, 22.0, 14.0), Zone.LAPTOP: (48.0, 14.0, 22.0, 14.0)}  # x, y, w, h
BIG, SMALL = 1.18, 0.9
INSET = 1.7  # the water sits this far inside a tile's outline
SWITCH_S = 0.58
PHASE_RATE = 0.17 * 60  # the slosh wave's phase, rad/s (0.17 per mockup frame)
GREEN = {False: (40, 167, 69), True: (48, 209, 88)}  # keyed by dark
AMBER = {False: (214, 120, 0), True: (255, 159, 10)}


@dataclass(frozen=True)
class TileFrame:
    fill: float
    level: float  # y of the water surface
    amp: float  # slosh amplitude, already faded for shallow water
    phase: float
    scale: float
    lid: float  # opacity of the lid line (0 = open)


@dataclass(frozen=True)
class GlyphFrame:
    tiles: dict  # Zone -> TileFrame
    amber: float  # 0 = green water, 1 = amber (frozen while typing)
    outline: float  # the tile outlines' opacity
    pause: float  # the pause bars' opacity
    alert: float  # the "!" opacity
    drops: list  # (x, y, r): the flow stream
    parts: list  # (x, y, r): falling drops
    steam: list  # (x, y, r, opacity)
    ripples: list  # (x, y, r, opacity)


def level(zone: Zone, fill: float) -> float:
    x, y, w, h = TILES[zone]
    top, bot = y + INSET, y + h - INSET
    return bot - fill * (bot - top + 0.6)


def water_zone(view: DockView) -> Zone | None:
    return view.focus if view.mode == TRACKING and view.face and view.focus in TILES else None


def target_scales(view: DockView) -> dict:
    if view.mode == TRACKING and view.focus in TILES:
        return {z: BIG if z == view.focus else SMALL for z in TILES}
    return {z: 1.0 for z in TILES}


class GlyphScene:
    def __init__(self, *, freeze_s: float = 1.5, hold_s: float = 0.3, seed: int | None = None) -> None:
        self.freeze_s, self.hold_s = freeze_s, hold_s
        self.rng = random.Random(seed)
        self.fill = {z: Channel(0.0) for z in TILES}
        self.scale = {z: Channel(1.0) for z in TILES}
        self.amp = {z: Wave() for z in TILES}
        self.dim, self.alert, self.close = Channel(0.0), Channel(0.0), Channel(0.0)
        self.view: DockView | None = None
        self.stream: Stream | None = None
        self.steam: list[Steam] = []
        self.parts: list[Drop] = []
        self.ripples: list[Ripple] = []

    # ---- inputs ----------------------------------------------------------------------------------
    def update(self, view: DockView, now: float) -> None:
        old, self.view = self.view, view
        if old is None:
            self._snap(view, now)
            return
        if view.glyph_key() == old.glyph_key():
            return
        self._lid_input(old, view, now)
        self._scales(old, view, now)
        if (view.mode == PAUSED) != (old.mode == PAUSED):
            if view.mode == PAUSED:
                self.dim.to(1.0, now, 0.38, ease_out)
            else:
                self.dim.to(0.0, now, 0.30, ease_out)
        if (view.mode == ALERT) != (old.mode == ALERT):
            self.alert.to(1.0 if view.mode == ALERT else 0.0, now, 0.25, ease_out)
        was, water = water_zone(old), water_zone(view)
        if was != water:
            if was is not None and water is not None:
                self._flow(was, water, now)
            elif water is not None:
                self._condense(water, now)
            elif view.mode == TRACKING and not view.face:
                self._evaporate(was, now)
            else:
                self._drain(was, now)
        if view.blocked and not old.blocked and view.focus in TILES:
            self.amp[view.focus].kick(0.9, now, FROZEN if self.lid(now) > 0.5 else CALM)

    def ripple(self, x: float, y: float, now: float) -> None:
        """A click on the dock (viewBox coordinates)."""
        self.ripples.append(Ripple(x, y, now))

    # ---- transitions (the mockup's doSwitch, condense, evaporate, drain, setPaused) ----------------
    def _snap(self, view: DockView, now: float) -> None:
        water = water_zone(view)
        for z in TILES:
            self.fill[z].set(1.0 if z == water else 0.0)
        for z, s in target_scales(view).items():
            self.scale[z].set(s)
        self.dim.set(1.0 if view.mode == PAUSED else 0.0)
        self.alert.set(1.0 if view.mode == ALERT else 0.0)
        self.close.set(1.0 if self._melt(view, now) > 0 else 0.0)

    def _scales(self, old: DockView, view: DockView, now: float) -> None:
        before, after = target_scales(old), target_scales(view)
        if before == after:
            return
        if view.mode == TRACKING and old.mode != TRACKING:  # resume: spring back
            for z, s in after.items():
                self.scale[z].to(s, now, 0.64, spring, delay=0.12)
        elif view.mode == TRACKING:  # the focus moved: the source shrinks, the target springs up late
            for z, s in after.items():
                if s == SMALL:
                    self.scale[z].to(s, now, SWITCH_S * 0.55, ease_in_out)
                else:
                    self.scale[z].to(s, now, SWITCH_S * 0.75, spring, delay=SWITCH_S * 0.42)
        else:  # paused, alert, idle: both tiles back to 1.0
            for z, s in after.items():
                self.scale[z].to(s, now, 0.42, ease_in_out)

    def _flow(self, src: Zone, dst: Zone, now: float) -> None:
        (ax, ay, aw, _), (bx, by, bw, bh) = TILES[src], TILES[dst]
        p0 = (ax + aw / 2, level(src, self.fill[src].get(now)) + 1.5)
        p2 = (bx + bw / 2, by + bh * 0.62)
        self.stream = Stream(p0, ((p0[0] + p2[0]) / 2, min(ay, by) - 6), p2, now, SWITCH_S)
        self.fill[src].to(0.0, now, SWITCH_S * 0.5, ease_in)
        self.amp[src].kick(1.0, now)
        self.fill[dst].to(1.0, now, SWITCH_S * 0.55, ease_out, delay=SWITCH_S * 0.5)
        self.amp[dst].kick(1.8, now + SWITCH_S * 0.5)  # the slosh (spec §8.3)

    def _condense(self, zone: Zone, now: float) -> None:
        x, y, w, h = TILES[zone]
        for i, fr in enumerate((0.28, 0.5, 0.72)):
            self.parts.append(Drop(x + w * fr, y - 4 - i, 0.0, 0.2, 1.25, y + h * 0.6, now + i * 0.07))
        self.fill[zone].to(1.0, now, 0.5, ease_out, delay=0.16)
        self.amp[zone].kick(1.1, now + 0.16)

    def _evaporate(self, zone: Zone, now: float) -> None:
        x, y, w, h = TILES[zone]
        surface = level(zone, self.fill[zone].get(now)) - 0.5
        r = self.rng
        for i in range(5):
            self.steam.append(Steam(x + 4 + r.random() * (w - 8), surface, 0.7 + r.random() * 0.5,
                                    -0.13 - r.random() * 0.07, r.random() * 6, now + i * 0.09))
        self.fill[zone].to(0.0, now, 0.56, ease_in_out)

    def _drain(self, zone: Zone, now: float) -> None:
        self.fill[zone].to(0.0, now, 0.44, ease_in)
        self.amp[zone].kick(0.6, now)

    # ---- the typing lid ---------------------------------------------------------------------------
    @property
    def _hold(self) -> float:
        """The hold never outlasts the freeze (typing_freeze_ms is tunable down to 0)."""
        return max(0.0, min(self.hold_s, self.freeze_s))

    def _melt(self, view: DockView | None, now: float) -> float:
        """1 while typing and during the hold, then linearly down to 0 when the freeze ends."""
        if view is None or view.mode != TRACKING or view.last_key_t is None or self.freeze_s <= 0:
            return 0.0
        age, hold = now - view.last_key_t, self._hold
        if age < hold:
            return 1.0
        span = self.freeze_s - hold
        return 0.0 if span <= 0 else max(0.0, min(1.0, 1 - (age - hold) / span))

    def _lid_input(self, old: DockView, view: DockView, now: float) -> None:
        if view.mode != TRACKING or view.last_key_t is None or view.last_key_t == old.last_key_t:
            return
        if self._melt(old, now) <= 0:  # the last burst had thawed: a new one closes the lid
            self.close.set(0.0)
            self.close.to(1.0, now, 0.18, ease_out)
        elif self.close.target < 1.0:
            self.close.to(1.0, now, 0.18, ease_out)

    def lid(self, now: float) -> float:
        return min(self.close.get(now), self._melt(self.view, now))

    # ---- sampling ---------------------------------------------------------------------------------
    def frame(self, now: float) -> GlyphFrame:
        lid = self.lid(now)
        focus = self.view.focus if self.view is not None else None
        tiles = {}
        for z in TILES:
            f = self.fill[z].get(now)
            tiles[z] = TileFrame(
                fill=f,
                level=level(z, f),
                amp=self.amp[z].get(now) * min(1.0, f * 3),
                phase=PHASE_RATE * now + (0.0 if z is Zone.EXTERNAL else 1.9),
                scale=self.scale[z].get(now),
                lid=0.95 * lid if z == focus else 0.0,
            )
        self._prune(now)
        dim = self.dim.get(now)
        return GlyphFrame(
            tiles=tiles,
            amber=max(0.0, min(1.0, 1.2 * lid - 0.2)),
            outline=0.78 - 0.5 * dim,
            pause=dim,
            alert=self.alert.get(now),
            drops=self.stream.drops(now) if self.stream is not None else [],
            parts=[p for d in self.parts if (p := d.at(now)) is not None],
            steam=[s for st in self.steam if (s := st.at(now)) is not None],
            ripples=[r for rp in self.ripples if (r := rp.at(now)) is not None],
        )

    def _prune(self, now: float) -> None:
        self.parts = [d for d in self.parts if d.t0 > now or d.at(now) is not None]
        self.steam = [s for s in self.steam if s.t0 > now or s.at(now) is not None]
        self.ripples = [r for r in self.ripples if r.at(now) is not None]
        if self.stream is not None and not self.stream.active(now):
            self.stream = None

    def fast(self, now: float) -> bool:
        """Something moves quickly (worth the display's full refresh rate)."""
        self._prune(now)
        channels = (*self.fill.values(), *self.scale.values(), self.dim, self.alert, self.close)
        return (self.stream is not None or bool(self.parts) or bool(self.ripples)
                or any(c.busy(now) for c in channels))

    def melting(self, now: float) -> bool:
        v = self.view
        if v is None or v.mode != TRACKING or v.last_key_t is None or self.close.get(now) <= 0:
            return False
        return v.last_key_t + self._hold <= now < v.last_key_t + self.freeze_s

    def busy(self, now: float) -> bool:
        """Anything still moving: the window keeps drawing frames until this turns False."""
        return (self.fast(now) or bool(self.steam) or any(w.busy(now) for w in self.amp.values())
                or self.melting(now))

    def wake_at(self, now: float) -> float | None:
        """When an idle scene will start moving on its own (the lid starts melting after the hold)."""
        v = self.view
        if v is None or v.mode != TRACKING or v.last_key_t is None or self.close.target <= 0:
            return None
        start = v.last_key_t + self._hold
        return start if now < start < v.last_key_t + self.freeze_s else None
