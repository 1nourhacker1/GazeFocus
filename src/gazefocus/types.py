"""Core value types shared by vision, logic and app layers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Literal


class Zone(Enum):
    LAPTOP = "LAPTOP"
    EXTERNAL = "EXTERNAL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class HeadSample:
    """One processed camera frame. Angles in degrees; iris offsets in -1..1."""

    t: float
    face: bool
    yaw: float = 0.0
    pitch: float = 0.0
    iris_h: float = 0.0
    iris_v: float = 0.0
    box: tuple[float, float, float, float] | None = None  # face bounds in 0..1 camera coords: the dock's preview only
    nose: tuple[float, float] | None = None


def recordable(sample: HeadSample) -> dict:
    """What recordings and saved calibration samples keep: head angles and timings, never face positions."""
    d = asdict(sample)
    d.pop("box", None)
    d.pop("nose", None)
    return d


Action = Literal["none", "switch", "blocked"]


@dataclass(frozen=True)
class Decision:
    t: float
    zone: Zone
    margin: float | None
    action: Action
    reason: str
    target: Zone | None = None
