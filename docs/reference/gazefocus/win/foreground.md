# gazefocus/win/foreground.py
Verified against: GazeFocus@1c804ee · 2026-09-29

- `ForegroundHook` is `SetWinEventHook(EVENT_SYSTEM_FOREGROUND, WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS)`.
  - Events are queued to our thread and delivered by Qt's loop, so no code of ours runs inside other processes.
  - GazeFocus's own windows (the tray menu) are skipped.
- `MruTracker` (pure):
  - Keeps up to 20 windows per monitor device, most recent first. A window seen on a new monitor leaves its old list.
  - A change **we** announced with `expect(hwnd, t)` that arrives within **300 ms** for the same window is *ours*. Anything else is **manual** and sets `last_manual_t`, which starts the decider's 1 s cooldown.
  - Non-targets (the taskbar, the Alt+Tab switcher) count as manual but never enter the lists.
  - `last_app_window` is the last real app window; the tray restores focus to it.
