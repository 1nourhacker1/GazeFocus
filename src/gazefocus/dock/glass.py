"""The Liquid Glass material (spec §8.1, M0-C2), rendered on the CPU from the pixels behind the dock. Pure.

The values are the approved mockup's CSS:
- backdrop blur(20px) saturate(1.7)
- tint: white .36 (.74 open) on light backdrops; rgba(58,58,64,.32) (.70 open) on dark ones
- the top specular line, the hairline rim, the bottom inner glow, the ::before sheen and the ::after rim lights
- box-shadows 0 5px 16px rgba(0,0,0,.22) and 0 1px 2px rgba(0,0,0,.2)
The lens rim (M0-C2) bends what is under the edge and keeps it clear of tint.

Every highlight is a smooth falloff, never a hard mask, and never thinner than the sampling step,
so nothing aliases along the curve (the user's M0-C2 feedback).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

from gazefocus.dock.geometry import Pill

LUMA = np.array([0.0722, 0.7152, 0.2126], np.float32)  # BGR weights
DARK_BELOW, LIGHT_ABOVE = 0.45, 0.55  # the theme switch's hysteresis (spec §8.1)
DARK_TINT = np.array([64, 58, 58], np.float32)  # rgb(58,58,64) as BGR
INVISIBLE = 8 / 255  # below this the shadow can't be seen: made fully transparent


@dataclass(frozen=True)
class Backdrop:
    heavy: np.ndarray  # H x W x 3 float32: blur(20px) saturate(1.7)
    light: np.ndarray | None  # lightly blurred: what the lens rim bends


class Grid:
    """Pixel-centre coordinates of the window, reused for every frame."""

    def __init__(self, w: int, h: int) -> None:
        self.w, self.h = w, h
        self.yy, self.xx = np.mgrid[0:h, 0:w].astype(np.float32)


def saturate(bgr: np.ndarray, k: float) -> np.ndarray:
    lum = bgr @ LUMA
    return lum[..., None] + (bgr - lum[..., None]) * k


def prepare(shot: np.ndarray, dpr: float, refraction: bool) -> Backdrop:
    """Everything that depends only on what is behind the dock: computed once per change of it."""
    h, w = shot.shape[:2]
    bgr = shot[..., :3].astype(np.float32)
    small = cv2.resize(bgr, (max(1, w // 4), max(1, h // 4)), interpolation=cv2.INTER_AREA)
    heavy = cv2.resize(cv2.GaussianBlur(small, (0, 0), 20 * dpr / 4), (w, h), interpolation=cv2.INTER_LINEAR)
    light = saturate(cv2.GaussianBlur(bgr, (0, 0), 1.5 * dpr), 1.3) if refraction else None
    return Backdrop(saturate(heavy, 1.7), light)


def luminance(bd: Backdrop, pill: Pill) -> float:
    """Mean brightness (0..1) behind the pill's bounding box."""
    h, w = bd.heavy.shape[:2]
    x0, x1 = max(0, int(pill.cx - pill.hw)), min(w, int(pill.cx + pill.hw))
    y0, y1 = max(0, int(pill.cy - pill.hh)), min(h, int(pill.cy + pill.hh))
    crop = bd.heavy[y0:y1, x0:x1].reshape(-1, 3)
    return float(crop.mean(0) @ LUMA) / 255 if len(crop) else 0.5


def pick_dark(lum: float, was_dark: bool) -> bool:
    return lum < LIGHT_ABOVE if was_dark else lum < DARK_BELOW


def render(
    bd: Backdrop,
    pill: Pill,
    *,
    dpr: float,
    dark: bool,
    openness: float,
    refraction: bool,
    step: int,
    grid: Grid,
    out: np.ndarray,
) -> None:
    """Write the premultiplied BGRA glass for `pill` (physical px) into `out`; everything else is cleared.

    step=2 renders at half resolution (while the panel resizes) and scales up.
    """
    d, cx, cy, hw, hh, r = dpr, pill.cx, pill.cy, pill.hw, pill.hh, pill.r
    pad, sig1, off1 = 3 * 8 * d, 8 * d, 5 * d  # room for the soft shadow
    x0, x1 = max(0, int(cx - hw - pad)), min(grid.w, int(cx + hw + pad) + 1)
    y0, y1 = max(0, int(cy - hh - 2 * d)), min(grid.h, int(cy + hh + off1 + pad) + 1)
    out.fill(0)
    if x1 <= x0 or y1 <= y0:
        return
    xx, yy = grid.xx[y0:y1:step, x0:x1:step], grid.yy[y0:y1:step, x0:x1:step]

    def width(w: float) -> float:  # a highlight never gets thinner than the sampling
        return max(w * d, 0.8 * step)

    dx, dy = xx - cx, yy - cy
    qx, qy = np.abs(dx) - (hw - r), np.abs(dy) - (hh - r)
    mx, my = np.maximum(qx, 0), np.maximum(qy, 0)
    outer = np.hypot(mx, my)
    sdf = outer + np.minimum(np.maximum(qx, qy), 0) - r
    corner = (qx > 0) & (qy > 0)
    safe = np.maximum(outer, 1e-6)
    nx = np.where(corner, mx / safe, (qx > qy).astype(np.float32)) * np.sign(dx)  # the outward normal
    ny = np.where(corner, my / safe, (qx <= qy).astype(np.float32)) * np.sign(dy)
    cov = np.clip(0.5 - sdf / (1.25 * step), 0, 1)  # a 1.25 px antialiasing ramp
    sp = np.maximum(-sdf, 0)  # depth inside the pill

    color = bd.heavy[y0:y1:step, x0:x1:step].copy()
    lens = None
    if refraction and bd.light is not None:  # a clear lens around the frosted centre
        band, amount = 18 * d, 20 * d
        lens = (np.clip(1 - sp / band, 0, 1) ** 2).astype(np.float32)
        bent = cv2.remap(bd.light, xx + nx * amount * lens, yy + ny * amount * lens, cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_REFLECT)
        k = (lens * 0.92)[..., None]
        color = color * (1 - k) + bent * k

    te = max(0.0, min(1.0, openness))
    ta = (0.32 + 0.38 * te) if dark else (0.36 + 0.38 * te)
    ta = ta * (1 - 0.8 * lens) if lens is not None else np.float32(ta)  # the lens stays clear of tint

    # Every white overlay composes as 1 - prod(1 - a_i): one pass over the colour instead of six.
    keep = 1 - 0.85 * np.exp(-sp / width(0.7)) * np.clip(-ny, 0, 1)  # top specular line
    keep *= 1 - 0.30 * np.exp(-sp / width(0.5))  # hairline rim
    keep *= 1 - 0.27 * np.exp(-sp / width(2.5)) * np.clip(ny, 0, 1) ** 1.5  # bottom inner glow
    ex, ey, rx, ry = cx - hw + 0.56 * hw, cy - hh - 0.4 * hh, 2.6 * hw, 2.0 * hh
    keep *= 1 - 0.30 * np.clip(1 - np.hypot((xx - ex) / rx, (yy - ey) / ry) / 0.55, 0, 1)  # top-left sheen
    e = np.exp(-sp / width(1.2))
    diag = (nx + ny) / math.sqrt(2)
    keep *= 1 - 0.60 * e * np.clip(-diag, 0, 1)  # top-left rim light
    keep *= 1 - 0.30 * e * np.clip(diag, 0, 1)  # bottom-right rim light
    if dark:
        ta3 = ta[..., None] if np.ndim(ta) else ta
        color = color * (1 - ta3) + DARK_TINT * ta3
    else:
        keep = keep * (1 - ta)  # the light tint is white too
    color = 255 - (255 - color) * keep[..., None]

    def box_shadow(off: float, sigma: float, strength: float) -> np.ndarray:
        qx2, qy2 = np.abs(dx) - (hw - r), np.abs(dy - off) - (hh - r)
        d2 = np.hypot(np.maximum(qx2, 0), np.maximum(qy2, 0)) + np.minimum(np.maximum(qx2, qy2), 0) - r
        return strength / (1 + np.exp(1.702 * d2 / sigma))  # a logistic: close to the Gaussian CDF

    shadow = 1 - (1 - box_shadow(off1, sig1, 0.22)) * (1 - box_shadow(1 * d, max(1 * d, step), 0.20))
    alpha = cov + shadow * (1 - cov)
    seen = (alpha >= INVISIBLE).astype(np.float32)  # Windows lets clicks through alpha 0 only: no invisible ring
    rgba = np.empty(cov.shape + (4,), np.uint8)
    rgba[..., :3] = np.clip(color * (cov * seen)[..., None], 0, 255)
    rgba[..., 3] = np.clip(alpha * seen * 255, 0, 255)
    out[y0:y1, x0:x1] = rgba if step == 1 else cv2.resize(rgba, (x1 - x0, y1 - y0), interpolation=cv2.INTER_LINEAR)
