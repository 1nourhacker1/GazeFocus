"""Time-based animation primitives for the dock (spec §8.3). Pure: every value is a function of `now`.

The approved mockup animated per frame at 60 Hz (requestAnimationFrame). Here each effect is a
closed-form function of time, so it looks the same at 60 or 240 Hz and is testable without a clock.
Per-frame factors convert as f**60 per second: 0.955 -> e^(-2.76 t), 0.962 -> e^(-2.33 t), 0.9 -> e^(-6.32 t).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

Ease = Callable[[float], float]
FPS = 60.0  # the mockup's frame rate, for converting its per-frame constants


def lin(x: float) -> float:
    return x


def ease_in(x: float) -> float:
    return x ** 3


def ease_out(x: float) -> float:
    return 1 - (1 - x) ** 3


def ease_in_out(x: float) -> float:
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def spring(x: float) -> float:
    """1 - e^(-5.5x)·cos(9x): overshoots, then settles (the tile spring)."""
    return 1.0 if x >= 1 else 1 - math.exp(-5.5 * x) * math.cos(9 * x)


def cubic_bezier(x1: float, y1: float, x2: float, y2: float) -> Ease:
    """CSS cubic-bezier(x1, y1, x2, y2) as an easing function."""

    def ease(x: float) -> float:
        if x <= 0:
            return 0.0
        if x >= 1:
            return 1.0
        u = x
        for _ in range(8):  # Newton's method on Bx(u) = x
            bx = 3 * (1 - u) ** 2 * u * x1 + 3 * (1 - u) * u * u * x2 + u ** 3
            dbx = 3 * (1 - u) ** 2 * x1 + 6 * (1 - u) * u * (x2 - x1) + 3 * u * u * (1 - x2)
            if abs(dbx) < 1e-6:
                break
            u = min(1.0, max(0.0, u - (bx - x) / dbx))
        return 3 * (1 - u) ** 2 * u * y1 + 3 * (1 - u) * u * u * y2 + u ** 3

    return ease


EXPAND = cubic_bezier(0.3, 1.45, 0.5, 1.0)  # the panel spring (spec §8.4)


class Channel:
    """A scalar that tweens toward a target. `to()` always starts from wherever the value is now."""

    def __init__(self, value: float = 0.0) -> None:
        self._a = self._b = float(value)
        self._t0, self._dur, self._ease = 0.0, 0.0, lin

    def get(self, now: float) -> float:
        if self._dur <= 0 or now >= self._t0 + self._dur:
            return self._b
        if now <= self._t0:
            return self._a
        return self._a + (self._b - self._a) * self._ease((now - self._t0) / self._dur)

    def to(self, target: float, now: float, seconds: float, ease: Ease = ease_in_out, delay: float = 0.0) -> None:
        self._a, self._b = self.get(now), float(target)
        self._t0, self._dur, self._ease = now + delay, max(seconds, 1e-6), ease

    def set(self, value: float) -> None:
        self._a = self._b = float(value)
        self._dur = 0.0

    @property
    def target(self) -> float:
        return self._b

    def busy(self, now: float) -> bool:
        return self._dur > 0 and now < self._t0 + self._dur


CALM = -math.log(0.955) * FPS  # 2.76 /s: the slosh's decay
FROZEN = -math.log(0.9) * FPS  # 6.32 /s: faster under a closed lid


class Wave:
    """The water's slosh amplitude. Kicks (possibly scheduled for later) decay exponentially."""

    def __init__(self) -> None:
        self._kicks: list[tuple[float, float, float]] = []  # (amplitude, start, rate)

    def kick(self, amplitude: float, at: float, rate: float = CALM) -> None:
        self._kicks.append((amplitude, at, rate))

    def get(self, now: float) -> float:
        live = [a * math.exp(-r * (now - t)) for a, t, r in self._kicks if t <= now]
        return max(live, default=0.0)

    def busy(self, now: float, eps: float = 0.02) -> bool:
        self._kicks = [k for k in self._kicks if k[1] > now or k[0] * math.exp(-k[2] * (now - k[1])) > eps]
        return bool(self._kicks)


def bezier(p0, p1, p2, q: float) -> tuple[float, float]:
    u = 1 - q
    return (u * u * p0[0] + 2 * u * q * p1[0] + q * q * p2[0], u * u * p0[1] + 2 * u * q * p1[1] + q * q * p2[1])


@dataclass(frozen=True)
class Stream:
    """The "Flow" switch: 6 merging droplets along an arc from one tile to the other (580 ms)."""

    p0: tuple[float, float]
    p1: tuple[float, float]
    p2: tuple[float, float]
    t0: float
    seconds: float = 0.58

    def drops(self, now: float) -> list[tuple[float, float, float]]:
        p = (now - self.t0) / self.seconds
        if p <= 0 or p >= 1:
            return []
        out = []
        for i in range(6):
            q = p * 1.4 - i * 0.08
            if 0 < q < 1:
                q = ease_in_out(q)
                x, y = bezier(self.p0, self.p1, self.p2, q)
                out.append((x, y, (2.7 - i * 0.18) * math.sin(math.pi * q) ** 0.55))
        return out

    def active(self, now: float) -> bool:
        return now < self.t0 + self.seconds


@dataclass(frozen=True)
class Steam:
    """Evaporation: rises, drifts, grows and fades (mockup: vy/frame, o *= 0.962, r *= 1.012)."""

    x: float
    y: float
    r: float
    vy: float  # units per mockup frame (negative = up)
    seed: float
    t0: float

    def at(self, now: float) -> tuple[float, float, float, float] | None:
        dt = now - self.t0
        if dt < 0:
            return None
        o = 0.85 * math.exp(-2.33 * dt)
        if o < 0.03:
            return None
        drift = 0.04 * FPS * 0.18 * (math.cos(self.seed) - math.cos(dt / 0.18 + self.seed))
        return self.x + drift, self.y + self.vy * FPS * dt, self.r * math.exp(0.716 * dt), o


@dataclass(frozen=True)
class Drop:
    """A falling drop (condense): gravity 0.05 per frame², gone once it falls past `until`."""

    x: float
    y: float
    vx: float  # units per mockup frame
    vy: float
    r: float
    until: float
    t0: float

    def at(self, now: float) -> tuple[float, float, float] | None:
        dt = now - self.t0
        if dt < 0:
            return None
        g, vy = 0.05 * FPS * FPS, self.vy * FPS
        y = self.y + vy * dt + 0.5 * g * dt * dt
        if vy + g * dt > 0 and y > self.until:
            return None
        return self.x + self.vx * FPS * dt, y, self.r


@dataclass(frozen=True)
class Ripple:
    """The click ripple: a ring that grows 0.9 units per frame and fades by 0.9 per frame."""

    x: float
    y: float
    t0: float
    speed: float = 0.9  # units per mockup frame
    opacity: float = 0.7

    def at(self, now: float) -> tuple[float, float, float, float] | None:
        dt = now - self.t0
        o = self.opacity * math.exp(-6.32 * dt)
        if dt < 0 or o < 0.03:
            return None
        return self.x, self.y, 1.0 + self.speed * FPS * dt, o
