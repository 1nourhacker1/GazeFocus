"""Calibration fit and per-frame screen classification (spec §6, revised by the 2026-09-29 desk session).

The discriminant uses a *diagonal* pooled covariance, so every weight follows its own
feature's mean difference. The first real calibration showed full-covariance LDA exploiting
the pitch<->eyelid correlation and pointing "LG" whenever the user looked down.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from gazefocus.config import ClassifierCfg
from gazefocus.types import HeadSample, Zone

FEATURES = ("yaw", "pitch", "iris_h")
MIN_SAMPLES = 5
# Variance floors (per feature): 1 degree for the angles, 0.05 for the iris offset.
VAR_FLOOR = np.array([1.0, 1.0, 0.05**2])
TRIM_MADS = 3.0  # calibration frames farther than this from the screen's median yaw are turn frames
_OOD_FEATURES = (1, 2)  # pitch and iris_h; yaw beyond either screen still points at that side
# Minimum spread for the outlier gate only: normal reading moves pitch a few degrees and the eyes a little,
# even when calibration was steady (desk session: pitch sd hit the 1 deg variance floor).
OOD_SD_FLOOR = np.array([0.0, 4.0, 0.15])


def features(s: HeadSample) -> np.ndarray:
    return np.array([s.yaw, s.pitch, s.iris_h], dtype=float)


@dataclass(frozen=True)
class ZoneModel:
    """z(f) = w.f + b, scaled so the LG mean maps to -1 and the laptop mean to +1."""

    w: tuple[float, ...]
    b: float
    separation: float
    mean_lg: tuple[float, ...]
    mean_laptop: tuple[float, ...]
    sd: tuple[float, ...]  # pooled within-screen standard deviation per feature

    def z(self, f) -> float:
        return float(np.dot(self.w, f) + self.b)

    def is_outlier(self, f, sigma: float) -> bool:
        """True when pitch or iris_h is more than `sigma` sd from BOTH screens (e.g. looking at a phone)."""
        f, sd = np.asarray(f, dtype=float), np.maximum(np.asarray(self.sd), OOD_SD_FLOOR)
        idx = list(_OOD_FEATURES)
        far = [np.max(np.abs(f[idx] - np.asarray(mean)[idx]) / sd[idx]) for mean in (self.mean_lg, self.mean_laptop)]
        return min(far) > sigma

    def to_dict(self) -> dict:
        return {
            "w": list(self.w),
            "b": self.b,
            "separation": self.separation,
            "mean_lg": list(self.mean_lg),
            "mean_laptop": list(self.mean_laptop),
            "sd": list(self.sd),
        }

    @staticmethod
    def from_dict(d: dict) -> "ZoneModel":
        return ZoneModel(
            w=tuple(float(v) for v in d["w"]),
            b=float(d["b"]),
            separation=float(d["separation"]),
            mean_lg=tuple(float(v) for v in d["mean_lg"]),
            mean_laptop=tuple(float(v) for v in d["mean_laptop"]),
            sd=tuple(float(v) for v in d["sd"]),
        )


def _face_matrix(samples: Sequence[HeadSample]) -> np.ndarray:
    return np.array([features(s) for s in samples if s.face]).reshape(-1, len(FEATURES))


def _trim_turn_frames(x: np.ndarray) -> np.ndarray:
    if len(x) == 0:
        return x
    yaw = x[:, 0]
    med = np.median(yaw)
    mad = np.median(np.abs(yaw - med)) * 1.4826
    if mad < 1e-9:
        return x
    return x[np.abs(yaw - med) <= TRIM_MADS * mad]


def fit_zone_model(lg: Sequence[HeadSample], laptop: Sequence[HeadSample]) -> ZoneModel:
    a, b = _trim_turn_frames(_face_matrix(lg)), _trim_turn_frames(_face_matrix(laptop))
    if len(a) < MIN_SAMPLES or len(b) < MIN_SAMPLES:
        raise ValueError(
            f"need at least {MIN_SAMPLES} face samples per screen (got LG={len(a)}, laptop={len(b)})"
        )
    ma, mb = a.mean(axis=0), b.mean(axis=0)
    var = (a.var(axis=0, ddof=1) * (len(a) - 1) + b.var(axis=0, ddof=1) * (len(b) - 1)) / (len(a) + len(b) - 2)
    var = np.maximum(var, VAR_FLOOR)
    d = mb - ma
    w_raw = d / var
    spread = float(d @ w_raw)  # = separation**2 (diagonal Mahalanobis distance between the means)
    if not np.isfinite(spread) or spread < 1e-9:
        raise ValueError("the two screens are indistinguishable in this calibration")
    pa, pb = float(w_raw @ ma), float(w_raw @ mb)
    scale = 2.0 / (pb - pa)
    return ZoneModel(
        w=tuple(float(v) for v in scale * w_raw),
        b=-(pa + pb) / (pb - pa),
        separation=float(np.sqrt(spread)),
        mean_lg=tuple(float(v) for v in ma),
        mean_laptop=tuple(float(v) for v in mb),
        sd=tuple(float(v) for v in np.sqrt(var)),
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
        self._restart = False  # set on face loss: the EMA restarts from the next face frame

    def _zone(self, m: float) -> Zone:
        if m <= -self.cfg.dead_band:
            return Zone.LG
        if m >= self.cfg.dead_band:
            return Zone.LAPTOP
        return Zone.UNKNOWN

    def update(self, s: HeadSample) -> tuple[Zone, float | None]:
        if s.face:
            f = features(s)
            self._lost, self._latched_lg, self._last_face_t = False, False, s.t
            if self.model.is_outlier(f, self.cfg.ood_sigma):
                return Zone.UNKNOWN, None  # looking at neither screen; keep it out of the EMA
            z = self.model.z(f)
            self._m = z if self._m is None or self._restart else self._m + self.cfg.ema_alpha * (z - self._m)
            self._restart = False
            return self._zone(self._m), self._m
        if not self._lost:
            self._lost = True
            self._restart = True
            recent = self._last_face_t is not None and s.t - self._last_face_t <= self.cfg.face_lost_memory_s
            self._latched_lg = bool(recent and self._m is not None and self._m <= self.cfg.face_lost_lg_margin)
        if self._latched_lg:
            return Zone.LG, self._m
        return Zone.UNKNOWN, None
