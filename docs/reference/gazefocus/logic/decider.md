# gazefocus/logic/decider.py
Verified against: GazeFocus@a653369 · 2026-09-29

A pure state machine. The caller builds a `Context` every frame from the **live** world: the foreground window's zone, last key time, mouse buttons, last manual focus change, fullscreen, paused, ready.

`step(zone, margin, ctx) -> Decision`, in this order:
1. **Candidate:** a known zone other than `ctx.focus_zone`. Its dwell timer restarts whenever the candidate changes or disappears. It keeps running during freezes.
2. If a switch is pending, return `none / "switch pending"`.
3. If there's no candidate, return `none / "on target"` or `"no gaze target"`. If dwell < `dwell_ms`, return `none / "dwell N/500"`.
4. If the zone failed last time, return `blocked / "switch failed; look away to retry"` until the gaze leaves that zone.
5. **Freezes, in priority order:** `not ready`, `paused`, `fullscreen app`, `mouse button held`, `typing N.Ns`, `manual focus cooldown`, `post-switch cooldown`. Any of them gives `blocked`.
6. Otherwise return `switch / "dwell met"` with `target=zone`, and mark it pending.

The caller must answer every `switch` with `notify_switched(t)` or `notify_switch_failed(t)`.
