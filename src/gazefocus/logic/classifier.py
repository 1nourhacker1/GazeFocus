"""Calibration fit (two-class LDA) and per-frame screen classification (spec §6)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from gazefocus.config import ClassifierCfg
from gazefocus.types import HeadSample, Zone

FEATURES = ("yaw", "pitch", "iris_h", "iris_v")
MIN_SAMPLES = 5


def features(s: HeadSample) -> np.ndarray:
    return np.array([s.yaw, s.pitch, s.iris_h, s.iris_v], dtype=float)


@dataclass(frozen=True)
class ZoneModel:
    """z(f) = w.f + b, scaled so the LG mean maps to -1 and the laptop mean to +1."""

    w: tuple[float, ...]
    b: float
    separation: float
    mean_lg: tuple[float, ...]
    mean_laptop: tuple[float, ...]

    def z(self, f) -> float:
        return float(np.dot(self.w, f) + self.b)

    def to_dict(self) -> dict:
        return {
            "w": list(self.w),
            "b": self.b,
            "separation": self.separation,
            "mean_lg": list(self.mean_lg),
            "mean_laptop": list(self.mean_laptop),
        }

    @staticmethod
    def from_dict(d: dict) -> "ZoneModel":
        return ZoneModel(
            w=tuple(float(v) for v in d["w"]),
            b=float(d["b"]),
            separation=float(d["separation"]),
            mean_lg=tuple(float(v) for v in d["mean_lg"]),
            mean_laptop=tuple(float(v) for v in d["mean_laptop"]),
        )


def fit_zone_model(lg: Sequence[HeadSample], laptop: Sequence[HeadSample], ridge: float = 1e-3) -> ZoneModel:
    a = np.array([features(s) for s in lg if s.face]).reshape(-1, len(FEATURES))
    b = np.array([features(s) for s in laptop if s.face]).reshape(-1, len(FEATURES))
    if len(a) < MIN_SAMPLES or len(b) < MIN_SAMPLES:
        raise ValueError(
            f"need at least {MIN_SAMPLES} face samples per screen (got LG={len(a)}, laptop={len(b)})"
        )
    both = np.vstack([a, b])
    mu, sd = both.mean(axis=0), both.std(axis=0)
    sd[sd < 1e-9] = 1.0  # a constant feature carries no information; keep it harmless
    sa, sb = (a - mu) / sd, (b - mu) / sd
    ma, mb = sa.mean(axis=0), sb.mean(axis=0)
    within = (np.cov(sa, rowvar=False) * (len(sa) - 1) + np.cov(sb, rowvar=False) * (len(sb) - 1)) / (
        len(sa) + len(sb) - 2
    )
    within = within + ridge * np.eye(len(FEATURES))
    d = mb - ma
    w_std = np.linalg.solve(within, d)
    spread = float(d @ w_std)  # = separation**2 = projected distance between the means
    if not np.isfinite(spread) or spread < 1e-9:
        raise ValueError("the two screens are indistinguishable in this calibration")
    pa, pb = float(w_std @ ma), float(w_std @ mb)
    scale, offset = 2.0 / (pb - pa), -(pa + pb) / (pb - pa)
    w = scale * w_std / sd
    b0 = offset - float(w @ mu)
    return ZoneModel(
        w=tuple(float(v) for v in w),
        b=b0,
        separation=float(np.sqrt(spread)),
        mean_lg=tuple(float(v) for v in a.mean(axis=0)),
        mean_laptop=tuple(float(v) for v in b.mean(axis=0)),
    )


def quality(separation: float) -> str:
    if separation >= 4.0:
        return "excellent"
    if separation >= 2.0:
        return "good"
    return "too close"


class ZoneClassifier:
    def __init__(self, model: ZoneModel, cfg: ClassifierCfg = ClassifierCfg()) -> None:
        self.model, self.cfg = model, cfg
        self.reset()

    def reset(self) -> None:
        self._m: float | None = None
        self._last_face_t: float | None = None
        self._lost = False
        self._latched_lg = False

    def _zone(self, m: float) -> Zone:
        if m <= -self.cfg.dead_band:
            return Zone.LG
        if m >= self.cfg.dead_band:
            return Zone.LAPTOP
        return Zone.UNKNOWN

    def update(self, s: HeadSample) -> tuple[Zone, float | None]:
        if s.face:
            z = self.model.z(features(s))
            if self._m is None or self._lost:
                self._m = z
            else:
                self._m += self.cfg.ema_alpha * (z - self._m)
            self._lost, self._latched_lg, self._last_face_t = False, False, s.t
            return self._zone(self._m), self._m
        if not self._lost:
            self._lost = True
            recent = self._last_face_t is not None and s.t - self._last_face_t <= self.cfg.face_lost_memory_s
            self._latched_lg = bool(recent and self._m is not None and self._m <= self.cfg.face_lost_lg_margin)
        if self._latched_lg:
            return Zone.LG, self._m
        return Zone.UNKNOWN, None
