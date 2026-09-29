# gazefocus/win/windows.py
Verified against: GazeFocus@1b7f201 · 2026-09-29

Spec §4.2: a window is a focus target only when it's
- visible, not minimized, not cloaked (which includes other virtual desktops), not hung
- not GazeFocus itself, not a shell window (Progman, WorkerW, Shell_TrayWnd, Shell_SecondaryTrayWnd)
- top-level, not a tool window (unless it's `WS_EX_APPWINDOW`), and on a monitor

`is_switch_target` returns `(ok, reason)`; `gazefocus diag windows --all` prints the reasons.

- `window_facts` never messages the window: `InternalGetWindowText` and `IsHungAppWindow`, so a hung app can't block us.
- `choose_target(device, mru, facts, zorder)` picks the first valid window on `device`, from the MRU list first and then the Z-order fallback (`top_level_windows`, topmost first). It returns `None` for an empty monitor.
- Monitors are identified by **device name** (`\\.\DISPLAYn`) at runtime. The calibration's stable monitor ids map onto device names each time the layout is refreshed.
- On the live desktop during planning there were 319 top-level windows, and 2 targets (a Windows Terminal on each screen).
