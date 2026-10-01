"""Where the calibration drop is (spec §9). Pure geometry, ported from the approved mockup's JS.

Points are (x, y) in Qt logical px of the virtual desktop; a screen is (x, y, w, h).
"""

from __future__ import annotations

import math

from gazefocus.dock.motion import FPS, ease_in_out

Point = tuple[float, float]
Rect = tuple[float, float, float, float]

EXTERNAL_TOUR = ((0.5, 0.5), (0.1, 0.14), (0.9, 0.14), (0.9, 0.86), (0.1, 0.86), (0.5, 0.5))
# The top waypoints sit lower on the laptop, clear of the dock under the camera.
LAPTOP_TOUR = ((0.5, 0.5), (0.12, 0.24), (0.88, 0.24), (0.88, 0.86), (0.12, 0.86), (0.5, 0.5))
ARC_LIFT = 60.0  # the travel arc's control point sits this far above the higher end
MOCKUP_SCREEN_W = 500.0  # the mockup's EXTERNAL was ~500 px wide; its stretch constants assume that scale
MAX_STRETCH = 0.55


def at(rect: Rect, u: float, v: float) -> Point:
    x, y, w, h = rect
    return (x + u * w, y + v * h)


def tour_points(rect: Rect, laptop: bool = False) -> list[Point]:
    return [at(rect, u, v) for u, v in (LAPTOP_TOUR if laptop else EXTERNAL_TOUR)]


def _cr(a: float, b: float, c: float, d: float, t: float) -> float:
    t2 = t * t
    return 0.5 * (2 * b + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t2 + (-a + 3 * b - 3 * c + d) * t2 * t)


def catmull_rom(points: list[Point], t: float) -> Point:
    """The tour at fraction t: a Catmull-Rom spline whose every segment is eased in and out,
    so the drop slows into each waypoint and lingers in the corners."""
    n = len(points) - 1
    s = min(n - 1e-6, max(0.0, t) * n)
    i = int(s)
    f = ease_in_out(s - i)
    p0, p1, p2, p3 = points[max(0, i - 1)], points[i], points[i + 1], points[min(n, i + 2)]
    return (_cr(p0[0], p1[0], p2[0], p3[0], f), _cr(p0[1], p1[1], p2[1], p3[1], f))


def travel(p0: Point, p1: Point, t: float) -> Point:
    """A trip between screens: a quadratic Bézier arcing over the higher end, eased in and out."""
    c = ((p0[0] + p1[0]) / 2, min(p0[1], p1[1]) - ARC_LIFT)
    q = ease_in_out(min(1.0, max(0.0, t)))
    u = 1 - q
    return (u * u * p0[0] + 2 * u * q * c[0] + q * q * p1[0], u * u * p0[1] + 2 * u * q * c[1] + q * q * p1[1])


def mockup_velocity(dist: float, dt: float, screen_w: float) -> float:
    """Speed in the mockup's units: px per 60 Hz frame, on a screen the mockup's size."""
    if dt <= 0 or screen_w <= 0:
        return 0.0
    return dist / dt / FPS * MOCKUP_SCREEN_W / screen_w


def stretch(velocity: float) -> float:
    return min(MAX_STRETCH, velocity * 0.05)


def squash(st: float) -> tuple[float, float]:
    """The drop's (along, across) scale for a stretch: longer along the motion, thinner across."""
    return (1 + st, 1 - st * 0.55)
