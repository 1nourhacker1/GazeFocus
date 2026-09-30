"""One run of the "follow the drop" calibration (spec §9). Pure: time comes in, frames come out.

The app feeds it the tracking camera's samples (`on_sample`) and asks for a frame on every vsync
(`frame(now)`); the overlay draws the frame. Both clocks are `time.perf_counter`, like `HeadSample.t`.

The timeline is the approved mockup's, with one addition: a tour's clock stands still while no face
is in view (or the camera has gone quiet), so the drop waits for the user instead of collecting nothing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from gazefocus.calib.path import Point, Rect, at, catmull_rom, mockup_velocity, squash, stretch, tour_points, travel
from gazefocus.logic.classifier import ZoneModel, fit_zone_model, quality
from gazefocus.runtime import MIN_CAL_SAMPLES
from gazefocus.types import HeadSample

PHASES = (
    ("start", 0.42),  # the intro panel has closed
    ("lg_travel", 1.1),
    ("lg_card", 1.3),
    ("lg_tour", 5.2),
    ("lap_travel", 1.1),
    ("lap_card", 1.2),
    ("lap_tour", 5.2),
    ("return", 0.7),  # back to the dock
    ("outro", 0.6),  # the drop and the dims fade out
)
TOURS = {"lg_tour": "LG", "lap_tour": "LAPTOP"}
CUES = {"lg_travel": "LG", "lap_travel": "LAPTOP", "done": "DONE"}  # beeps: the user may be looking elsewhere
SETTLE_S = 0.4  # a tour's first samples are the eyes catching up with the drop
LOST_CARD_S = 0.3  # without a face this long, the card says so
STALE_S = 1.0  # no sample for this long counts as no face (a camera that stopped)
FADE_S = 0.25
FRAME_60 = 1 / 60  # stretch is measured over one of the mockup's 60 Hz frames
DIM_ON, DIM_OFF = 0.25, 0.62  # the screen to look at, the other one
TOO_CLOSE = "Too close. Turn your head a little more, or move the LG closer to the laptop."
HINT = "Look at each screen: the water should follow."
CARDS = {
    "lg_card": ("LG", "Look at this screen", "Follow the drop with your eyes"),
    "lap_card": ("LAPTOP", "Now this screen", "Follow the drop"),
}


@dataclass(frozen=True)
class Card:
    screen: str  # "LG" or "LAPTOP"
    title: str
    subtitle: str


@dataclass(frozen=True)
class DropState:
    x: float
    y: float
    opacity: float
    along: float = 1.0  # scale along the motion
    across: float = 1.0
    angle: float = 0.0  # degrees, the direction of motion (Qt: y down)


@dataclass(frozen=True)
class OverlayFrame:
    phase: str
    dims: dict[str, float]  # black overlay opacity per screen
    drop: DropState
    ring: float | None = None  # the tour's progress, 0..1, or None when hidden
    card: Card | None = None
    waiting: bool = False  # a tour stands still: no face


@dataclass(frozen=True)
class CalibrationResult:
    model: ZoneModel | None
    samples: dict[str, list[HeadSample]] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    quality: str | None = None
    title: str = ""
    message: str = ""

    @property
    def can_save(self) -> bool:
        return self.model is not None and self.quality != "too close"


class CalibrationSession:
    def __init__(self, lg: Rect, laptop: Rect, dock: Point) -> None:
        self.lg, self.laptop, self.dock = lg, laptop, dock
        self._lg_tour = tour_points(lg)
        self._lap_tour = tour_points(laptop, laptop=True)
        self._ends, t = [], 0.0
        for _, seconds in PHASES:
            t += seconds
            self._ends.append(t)
        self.start(0.0)

    def start(self, now: float) -> None:
        """Begin (or Redo) from the top: the intro has closed, the LG comes first."""
        self.t0 = self.last_now = now
        self.tau = 0.0  # timeline time: wall time minus the time tours stood waiting
        self._i = 0
        self._cancelled = False
        self._face = False
        self._last_t: float | None = None
        self._lost_since = now
        self._samples: dict[str, list[HeadSample]] = {"LG": [], "LAPTOP": []}

    @property
    def phase(self) -> str:
        if self._cancelled:
            return "cancelled"
        return PHASES[self._i][0] if self._i < len(PHASES) else "done"

    def cancel(self) -> None:
        self._cancelled = True

    def on_sample(self, s: HeadSample) -> None:
        self._last_t = s.t
        if not s.face:
            if self._face or self._lost_since is None:
                self._lost_since = s.t
            self._face = False
            return
        self._face, self._lost_since = True, None
        screen = TOURS.get(self.phase)
        if screen is not None and self.tau - self._begin(self._i) >= SETTLE_S:
            self._samples[screen].append(s)

    # --- time ---

    def _begin(self, i: int) -> float:
        return self._ends[i - 1] if i > 0 else 0.0

    def _face_now(self, now: float) -> bool:
        return self._face and self._last_t is not None and now - self._last_t <= STALE_S

    def _lost_for(self, now: float) -> float:
        if self._face_now(now):
            return 0.0
        since = self._lost_since if not self._face else self._last_t
        return now - (since if since is not None else self.t0)

    def _advance(self, now: float) -> None:
        dt, self.last_now = max(0.0, now - self.last_now), now
        waiting = not self._face_now(now)
        while dt > 0 and self.phase not in ("done", "cancelled"):
            if self.phase in TOURS and waiting:
                return
            step = min(dt, self._ends[self._i] - self.tau)
            self.tau += step
            dt -= step
            if self.tau >= self._ends[self._i] - 1e-12:
                self._i += 1

    # --- where things are ---

    def _phase_at(self, tau: float) -> tuple[str, float]:
        for (name, seconds), end in zip(PHASES, self._ends):
            if tau < end:
                return name, 1 - (end - tau) / seconds
        return "done", 1.0

    def _pos(self, tau: float) -> Point:
        name, f = self._phase_at(max(0.0, tau))
        lg_c, lap_c = at(self.lg, 0.5, 0.5), at(self.laptop, 0.5, 0.5)
        return {
            "start": lambda: self.dock,
            "lg_travel": lambda: travel(self.dock, lg_c, f),
            "lg_card": lambda: lg_c,
            "lg_tour": lambda: catmull_rom(self._lg_tour, f),
            "lap_travel": lambda: travel(lg_c, lap_c, f),
            "lap_card": lambda: lap_c,
            "lap_tour": lambda: catmull_rom(self._lap_tour, f),
            "return": lambda: travel(lap_c, self.dock, f),
        }.get(name, lambda: self.dock)()

    def _opacity(self) -> float:
        name = self.phase
        if name in ("start", "done", "cancelled"):
            return 0.0
        if name == "lg_travel":
            return min(1.0, (self.tau - self._begin(self._i)) / FADE_S)
        if name == "outro":
            return max(0.0, 1 - (self.tau - self._begin(self._i)) / FADE_S)
        return 1.0

    def _dims(self) -> dict[str, float]:
        name = self.phase
        if name.startswith("lg_"):
            return {"LG": DIM_ON, "LAPTOP": DIM_OFF}
        if name.startswith("lap_") or name == "return":
            return {"LG": DIM_OFF, "LAPTOP": DIM_ON}
        return {"LG": 0.0, "LAPTOP": 0.0}

    def frame(self, now: float) -> OverlayFrame:
        self._advance(now)
        name = self.phase
        x, y = self._pos(self.tau)
        waiting = name in TOURS and not self._face_now(now)
        along = across = 1.0
        angle = 0.0
        if not waiting and name not in ("done", "cancelled"):
            px, py = self._pos(self.tau - FRAME_60)
            dx, dy = x - px, y - py
            dist = math.hypot(dx, dy)
            if dist > 1e-6:
                screen = self.laptop if name.startswith("lap") or name in ("return", "outro") else self.lg
                along, across = squash(stretch(mockup_velocity(dist, FRAME_60, screen[2])))
                angle = math.degrees(math.atan2(dy, dx))
        drop = DropState(x, y, self._opacity(), along, across, angle)
        ring = None
        if name in TOURS:
            i = self._i
            ring = min(1.0, (self.tau - self._begin(i)) / PHASES[i][1])
        card = None
        if name in CARDS:
            card = Card(*CARDS[name])
        elif waiting and self._lost_for(now) >= LOST_CARD_S:
            card = Card(TOURS[name], "Can't see you", "Is the room too dark?")
        return OverlayFrame(name, self._dims(), drop, ring, card, waiting)

    # --- the outcome ---

    def result(self) -> CalibrationResult:
        samples = {k: list(v) for k, v in self._samples.items()}
        counts = {k: len(v) for k, v in samples.items()}
        if min(counts.values()) < MIN_CAL_SAMPLES:
            return CalibrationResult(
                None, samples, counts, None, "Too few samples",
                f"Saw your face {counts['LG']} times on the LG and {counts['LAPTOP']} on the laptop "
                f"({MIN_CAL_SAMPLES} each needed). Is the room too dark?",
            )
        try:
            model = fit_zone_model(samples["LG"], samples["LAPTOP"])
        except ValueError:
            return CalibrationResult(None, samples, counts, "too close", "Too close", TOO_CLOSE)
        q = quality(model.separation)
        if q == "too close":
            return CalibrationResult(model, samples, counts, q, "Too close", TOO_CLOSE)
        return CalibrationResult(model, samples, counts, q, "Calibrated ✓", HINT)
