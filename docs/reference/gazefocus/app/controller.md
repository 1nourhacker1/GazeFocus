# gazefocus/app/controller.py
Verified against: GazeFocus@e41d557 · 2026-09-29

`Controller.on_sample(sample)`:
1. Remembers the cursor's position on its current monitor.
2. Classifies the sample into (zone, margin).
3. Builds `Context` from the **live** world: `focus_zone` (the monitor of `GetForegroundWindow`), `last_key_t` (Raw Input), `buttons_down()` (**read live every frame**), `mru.last_manual_t` and `fullscreen()`.
4. Runs `decider.step`, then `DecisionLogger.decision`.
5. On `switch`:
   - Map the zone to a device. `None` gives the note "LG is not connected" and a failure.
   - `choose_target(device, mru.order(device))`. `None` gives the note "no window to focus on LG" and a failure.
   - `mru.expect(hwnd)`, so the resulting foreground event isn't counted as manual, then `bring_to_front`, then `log.outcome`.
   - On success: `notify_switched`, and if the mouse has been idle ≥ `cursor_idle_warp_ms`, warp the cursor to its remembered spot on that monitor (or the window centre), clamped to the work area.
   - On failure: `notify_switch_failed`, which latches the target until the gaze leaves it. There's one FAIL line and no retry loop.

`Desktop` is the whole Win32 surface as injectable callables; `app/main.py:real_desktop` builds the real one. Tests use fakes, so they never move real focus.
