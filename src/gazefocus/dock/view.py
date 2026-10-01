"""What the dock should show (spec §8.2), derived from the app's state. Pure."""

from __future__ import annotations

from dataclasses import dataclass

from gazefocus.app.state import Status
from gazefocus.logic.decider import reason_category
from gazefocus.types import Decision, HeadSample, Zone

TRACKING, PAUSED, ALERT, IDLE = "tracking", "paused", "alert", "idle"
PAUSED_TITLES = {Status.PAUSED: "Paused", Status.LOCKED: "Screen locked", Status.SUSPENDED: "Asleep"}
ALERT_TITLES = {
    Status.CAMERA_WAIT: "Camera unavailable",
    Status.NOT_CALIBRATED: "Not calibrated",
    Status.LAYOUT_CHANGED: "Monitor layout changed",
    Status.UNSUPPORTED: "Unsupported monitor layout",
    Status.TRACKER_FAILED: "Tracker failed",
}
NAMES = {Zone.EXTERNAL: "EXTERNAL", Zone.LAPTOP: "Laptop"}


@dataclass(frozen=True)
class DockView:
    mode: str  # TRACKING, PAUSED, ALERT or IDLE
    focus: Zone  # the tile that gets the water
    face: bool = True
    last_key_t: float | None = None  # perf_counter of the last keystroke: drives the typing lid
    blocked: bool = False  # a switch is being held back while typing: the water wobbles
    title: str = ""  # the open panel's heading
    detail: str = ""  # the open panel's numbers

    def glyph_key(self) -> tuple:
        """The fields the glyph animates on; title and detail only matter while the panel is open."""
        return self.mode, self.focus, self.face, self.last_key_t, self.blocked


def view_for(
    status: Status,
    *,
    focus: Zone,
    face: bool,
    last_key_t: float | None,
    decision: Decision | None,
    sample: HeadSample | None,
    now: float,
    freeze_s: float,
) -> DockView:
    if status is Status.RUNNING:
        typing = last_key_t is not None and now - last_key_t < freeze_s
        blocked = decision is not None and decision.action == "blocked" and reason_category(decision.reason) == "typing"
        name = NAMES.get(focus, "?")
        title = f"No face, holding {name}" if not face else "Frozen while typing" if typing else f"Focus: {name}"
        return DockView(TRACKING, focus, face, last_key_t, blocked, title, _detail(sample, decision, last_key_t, now))
    if status in PAUSED_TITLES:
        return DockView(PAUSED, focus, face, None, False, PAUSED_TITLES[status], "camera off")
    if status is Status.CALIBRATING:
        return DockView(IDLE, focus, face, None, False, "Calibrating…", "follow the drop  ·  Esc cancels")
    return DockView(ALERT, focus, face, None, False, ALERT_TITLES.get(status, status.value), "details in the tray")


def _detail(sample: HeadSample | None, decision: Decision | None, last_key_t: float | None, now: float) -> str:
    head = f"yaw {sample.yaw:+.1f}°   pitch {sample.pitch:+.1f}°" if sample is not None and sample.face else "no face"
    margin = None if decision is None else decision.margin
    m = "margin n/a" if margin is None else f"margin {margin:+.2f}"
    k = "no key yet" if last_key_t is None else f"key {now - last_key_t:.1f} s ago"
    return f"{head}\n{m}   {k}"
