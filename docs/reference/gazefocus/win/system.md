# gazefocus/win/system.py
Verified against: GazeFocus@d3b5af3 · 2026-09-29

- `SingleInstance`: the named mutex `Local\GazeFocus`, with its own name per test home.
- `Hotkey`:
  - `RegisterHotKey(window, id, mods | MOD_NOREPEAT, vk)`; `WM_HOTKEY` carrying that id calls `on_press`.
  - `parse_hotkey("Ctrl+Alt+G")` requires a modifier plus one key (A–Z, 0–9, F1–F24).
  - If another app already owns the combination, `.registered` is False and the app logs it; the tray still works.
- `fullscreen_busy()`: `SHQueryUserNotificationState` ∈ {BUSY (2), D3D fullscreen (3), presentation (4)}, which is a spec §4.1 freeze. The normal state on this machine is 5 ("accepts notifications").
- `on_battery()`: `GetSystemPowerStatus().ACLineStatus == 0`.
- `SystemEvents` registers on the MessageWindow:
  - `WTSRegisterSessionNotification`: lock (7) and unlock (8)
  - `RegisterSuspendResumeNotification` + `WM_POWERBROADCAST`: suspend (4), resume (7 or 0x12); it always answers TRUE
  - `WM_DISPLAYCHANGE`, a broadcast that reaches our hidden top-level window
