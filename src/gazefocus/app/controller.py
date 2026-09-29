"""The switching brain: one HeadSample in, at most one focus switch out (spec §4).

Everything that touches Windows goes through `Desktop`, so the whole behaviour is testable
with fakes. The live foreground window is the source of truth for "where focus is".
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from gazefocus.app.decision_log import DecisionLogger
from gazefocus.logic.classifier import ZoneClassifier
from gazefocus.logic.decider import Context, GazeDecider
from gazefocus.types import Decision, HeadSample, Zone
from gazefocus.win.focus import SwitchResult, clamp_point
from gazefocus.win.foreground import MruTracker
from gazefocus.win.rawinput import InputTracker


@dataclass
class Desktop:
    foreground: Callable[[], int]
    device_of_window: Callable[[int], "str | None"]
    buttons_down: Callable[[], bool]
    fullscreen: Callable[[], bool]
    choose_target: Callable[[str, list[int]], "int | None"]  # (device, MRU order) -> hwnd
    bring_to_front: Callable[[int], SwitchResult]
    title_of: Callable[[int], str]
    cursor_pos: Callable[[], tuple[int, int]]
    device_of_point: Callable[[int, int], "str | None"]
    warp_cursor: Callable[[tuple[int, int]], bool]
    window_center: Callable[[int], "tuple[int, int] | None"]
    work_area: Callable[[str], "tuple[int, int, int, int] | None"]


class Controller:
    def __init__(
        self,
        *,
        classifier: ZoneClassifier,
        decider: GazeDecider,
        input_tracker: InputTracker,
        mru: MruTracker,
        desktop: Desktop,
        zone_devices: dict[Zone, "str | None"],
        cursor_idle_warp_ms: int,
        log: DecisionLogger,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.classifier, self.decider, self.input, self.mru = classifier, decider, input_tracker, mru
        self.desktop, self.log, self.clock = desktop, log, clock
        self.cursor_idle_warp_ms = cursor_idle_warp_ms
        self.zone_devices = dict(zone_devices)
        self._cursor_at: dict[str, tuple[int, int]] = {}
        self.last_decision: Decision | None = None

    def zone_of(self, device: str | None) -> Zone:
        for zone, dev in self.zone_devices.items():
            if dev is not None and dev == device:
                return zone
        return Zone.UNKNOWN

    def focus_zone(self) -> Zone:
        return self.zone_of(self.desktop.device_of_window(self.desktop.foreground()))

    def on_sample(self, sample: HeadSample) -> Decision:
        now = self.clock()
        self._remember_cursor()
        zone, margin = self.classifier.update(sample)
        ctx = Context(
            t=now,
            focus_zone=self.focus_zone(),
            last_key_t=self.input.last_key_t,
            mouse_buttons_down=self.desktop.buttons_down(),  # live every frame: never a stale "held"
            last_manual_focus_t=self.mru.last_manual_t,
            fullscreen=self.desktop.fullscreen(),
        )
        decision = self.decider.step(zone, margin, ctx)
        self.log.decision(decision)
        if decision.action == "switch":
            self._switch(decision.target, now)
        self.last_decision = decision
        return decision

    def _switch(self, target: Zone, now: float) -> None:
        device = self.zone_devices.get(target)
        if device is None:
            self.log.note(f"{target.value} is not connected")
            self.decider.notify_switch_failed(now)
            return
        hwnd = self.desktop.choose_target(device, self.mru.order(device))
        if hwnd is None:
            self.log.note(f"no window to focus on {target.value}")
            self.decider.notify_switch_failed(now)
            return
        self.mru.expect(hwnd, now)
        result = self.desktop.bring_to_front(hwnd)
        self.log.outcome(target.value, self.desktop.title_of(hwnd), result)
        if not result.ok:
            self.decider.notify_switch_failed(now)  # one FAIL, then "look away to retry"
            return
        self.decider.notify_switched(now)
        if self.input.idle_s(now, "mouse") * 1000.0 >= self.cursor_idle_warp_ms:
            self._warp(device, hwnd)

    def _remember_cursor(self) -> None:
        p = self.desktop.cursor_pos()
        device = self.desktop.device_of_point(*p)
        if device is not None:
            self._cursor_at[device] = p

    def _warp(self, device: str, hwnd: int) -> None:
        p = self._cursor_at.get(device) or self.desktop.window_center(hwnd)
        if p is None:
            return
        area = self.desktop.work_area(device)
        self.desktop.warp_cursor(clamp_point(p, area) if area else p)
