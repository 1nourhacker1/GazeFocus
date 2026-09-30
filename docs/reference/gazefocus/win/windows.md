# gazefocus/win/windows.py
Verified against: GazeFocus@8db716d · 2026-09-30

Spec §4.2: a window is a focus target only when it's
- visible, not minimized, not cloaked (which includes other virtual desktops), not hung
- not GazeFocus itself, not a shell window (Progman, WorkerW, Shell_TrayWnd, Shell_SecondaryTrayWnd)
- top-level, not a tool window (unless it's `WS_EX_APPWINDOW`), and on a monitor

`is_switch_target` returns `(ok, reason)`; `gazefocus diag windows --all` prints the reasons.

- `window_facts` never messages the window: `InternalGetWindowText` and `IsHungAppWindow`, so a hung app can't block us.
- `choose_target(device, mru, facts, zorder)` picks the first valid window on `device`, from the MRU list first and then the Z-order fallback (`top_level_windows`, topmost first). It returns `None` for an empty monitor.
- Monitors are identified by **device name** (`\\.\DISPLAYn`) at runtime. The calibration's stable monitor ids map onto device names each time the layout is refreshed.
- On the live desktop during planning there were 319 top-level windows, and 2 targets (a Windows Terminal on each screen).
- `is_fullscreen(facts, rect, monitor, device, zoomed)`: a window covering the whole monitor that isn't maximized, the shell or ours. Maximized windows don't count: with an auto-hiding taskbar they cover the monitor too.
- `fullscreen_app_on(device, rect)`: the same check for the **topmost real window on that monitor**, focused or not (GazeFocus moves focus to the LG whenever the user looks there, so a laptop video is usually not the foreground). Hidden, minimized, cloaked, tool, shell and GazeFocus windows are skipped. The Z-order, facts, rect and zoom lookups are injectable for tests.
