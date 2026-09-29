"""Core value types shared by vision, logic and app layers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal


class Zone(Enum):
    LAPTOP = "LAPTOP"
    LG = "LG"
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


Action = Literal["none", "switch", "blocked"]


@dataclass(frozen=True)
class Decision:
    t: float
    zone: Zone
    margin: float | None
    action: Action
    reason: str
    target: Zone | None = None
