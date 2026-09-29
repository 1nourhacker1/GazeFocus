"""Pure geometry: head rotation angles and iris offsets from MediaPipe outputs."""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np

# corner, corner, upper lid, lower lid, iris centre (MediaPipe 478-point mesh)
RIGHT_EYE = (33, 133, 159, 145, 468)
LEFT_EYE = (362, 263, 386, 374, 473)
_MIN_SPAN = 1e-4


def yaw_pitch_roll(matrix) -> tuple[float, float, float]:
    """Degrees, for R = Ry(yaw) @ Rx(pitch) @ Rz(roll). Scale and translation ignored."""
    m = np.asarray(matrix, dtype=float)
    if m.shape not in ((3, 3), (4, 4)):
        raise ValueError(f"expected 3x3 or 4x4 matrix, got {m.shape}")
    r = m[:3, :3]
    det = float(np.linalg.det(r))
    if abs(det) < 1e-12:
        raise ValueError("degenerate rotation matrix")
    r = r / np.cbrt(abs(det))
    pitch = math.asin(max(-1.0, min(1.0, -r[1, 2])))
    yaw = math.atan2(r[0, 2], r[2, 2])
    roll = math.atan2(r[1, 0], r[1, 1])
    return math.degrees(yaw), math.degrees(pitch), math.degrees(roll)


def _clamp(v: float) -> float:
    return max(-1.0, min(1.0, v))


def _eye(lm: Sequence[tuple[float, float]], idx: tuple[int, int, int, int, int]) -> tuple[float, float]:
    a, b, up, lo, iris = (lm[i] for i in idx)
    left, right = (a, b) if a[0] <= b[0] else (b, a)
    span_x = right[0] - left[0]
    span_y = lo[1] - up[1]
    h = 2.0 * (iris[0] - left[0]) / span_x - 1.0 if span_x > _MIN_SPAN else 0.0
    v = 2.0 * (iris[1] - up[1]) / span_y - 1.0 if span_y > _MIN_SPAN else 0.0
    return _clamp(h), _clamp(v)


def iris_offsets(landmarks: Sequence[tuple[float, float]]) -> tuple[float, float]:
    """(iris_h, iris_v) averaged over both eyes, each in [-1, 1]."""
    if len(landmarks) < 478:
        return 0.0, 0.0
    rh, rv = _eye(landmarks, RIGHT_EYE)
    lh, lv = _eye(landmarks, LEFT_EYE)
    return (rh + lh) / 2.0, (rv + lv) / 2.0
