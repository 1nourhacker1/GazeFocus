"""When is a focus switch allowed? (spec §4.1). Pure: the caller supplies time and world state."""

from __future__ import annotations

from dataclasses import dataclass

from gazefocus.config import DeciderCfg
from gazefocus.types import Decision, Zone

_KNOWN = (Zone.EXTERNAL, Zone.LAPTOP)


def reason_category(reason: str) -> str:
    """'typing 0.3s' -> 'typing': blocked reasons without their numbers (log/summary dedupe)."""
    return reason.rstrip("0123456789.s ")


@dataclass(frozen=True)
class Context:
    t: float
    focus_zone: Zone
    last_key_t: float | None = None
    mouse_buttons_down: bool = False
    last_manual_focus_t: float | None = None
    fullscreen: bool = False
    paused: bool = False
    ready: bool = True


class GazeDecider:
    def __init__(self, cfg: DeciderCfg = DeciderCfg()) -> None:
        self.cfg = cfg
        self._cand: Zone | None = None
        self._since = 0.0
        self._last_switch_t: float | None = None
        self._pending = False
        self._pending_target: Zone | None = None
        self._failed_zone: Zone | None = None

    def step(self, zone: Zone, margin: float | None, ctx: Context) -> Decision:
        t = ctx.t

        def decide(action, reason, target=None):
            return Decision(t=t, zone=zone, margin=margin, action=action, reason=reason, target=target)

        if self._failed_zone is not None and zone != self._failed_zone:
            self._failed_zone = None
        if zone in _KNOWN and zone != ctx.focus_zone:
            if self._cand != zone:
                self._cand, self._since = zone, t
        else:
            self._cand = None

        if self._pending:
            return decide("none", "switch pending")
        if self._cand is None:
            return decide("none", "on target" if zone == ctx.focus_zone else "no gaze target")
        held_ms = (t - self._since) * 1000.0
        if held_ms < self.cfg.dwell_ms:
            return decide("none", f"dwell {held_ms:.0f}/{self.cfg.dwell_ms}")
        if self._failed_zone == zone:
            return decide("blocked", "switch failed; look away to retry", zone)
        reason = self._freeze_reason(ctx)
        if reason is not None:
            return decide("blocked", reason, zone)
        self._pending, self._pending_target = True, zone
        return decide("switch", "dwell met", zone)

    def _freeze_reason(self, ctx: Context) -> str | None:
        t, c = ctx.t, self.cfg
        if not ctx.ready:
            return "not ready"
        if ctx.paused:
            return "paused"
        if ctx.fullscreen:
            return "fullscreen app"
        if ctx.mouse_buttons_down:
            return "mouse button held"
        if ctx.last_key_t is not None and (t - ctx.last_key_t) * 1000.0 < c.typing_freeze_ms:
            return f"typing {t - ctx.last_key_t:.1f}s"
        if ctx.last_manual_focus_t is not None and (t - ctx.last_manual_focus_t) * 1000.0 < c.manual_cooldown_ms:
            return "manual focus cooldown"
        if self._last_switch_t is not None and (t - self._last_switch_t) * 1000.0 < c.post_switch_cooldown_ms:
            return "post-switch cooldown"
        return None

    def notify_switched(self, t: float) -> None:
        self._pending, self._pending_target, self._last_switch_t, self._cand = False, None, t, None

    def notify_switch_failed(self, t: float) -> None:
        # latch the zone we tried to switch to: the gaze may have moved while the switch was pending
        self._pending, self._failed_zone, self._cand = False, self._pending_target or self._cand, None
        self._pending_target = None
