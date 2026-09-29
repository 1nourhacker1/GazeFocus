# gazefocus/app/tray.py
Verified against: GazeFocus@3cdfdbb · 2026-09-29

- **Icon** (drawn in code, 32 px): two tiles laid out like the desk, the LG on the left and higher. They have a dark rim and a white line so they read on any taskbar.
  - The focused tile is green while running. Both tiles are blue while calibrating.
  - Grey bars show paused, locked or asleep.
  - A red "!" means camera unavailable, not calibrated, layout changed, unsupported layout, or tracker failed.
- **Tooltip and first menu line:** `GazeFocus: running (focus on LG)` or `GazeFocus: paused`, and so on.
- **Menu:** Pause/Resume (with the hotkey), Recalibrate, Open config, Open logs folder, Quit.
- **Focus hand-back:** opening the menu makes the taskbar the foreground window. 150 ms after the menu closes, `restore_focus()` brings back the last app window, **unless** the action opened a window of its own (config, logs, quit).
