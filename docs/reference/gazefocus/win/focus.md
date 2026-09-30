# gazefocus/win/focus.py
Verified against: GazeFocus@0b9e2a5 · 2026-09-29

`bring_to_front(hwnd)` implements spec §7.3 from a process that doesn't have focus:
1. A dead or missing handle gives `none / "window is gone"` immediately. If the window is already in front, the result is `already`.
2. `nudge_input()`: one zero-motion `SendInput`, which makes our process the last one to receive input. Raw Input sees it as injected (`hDevice == NULL`) and ignores it.
3. `SetForegroundWindow` plus up to 50 ms of `GetForegroundWindow` polling gives `direct`.
4. Fallback thread: create a message queue, `AttachThreadInput(me, foreground thread)`, then `BringWindowToTop` and `SetForegroundWindow`, then detach. It's **abandoned after 500 ms**, because attaching can deadlock on a hung thread. Success gives `attach`.
5. Otherwise `failed`: "refused (elevated window or focus lock)" or "fallback timed out (hung window?)". The caller logs one FAIL and **doesn't retry**. M0-B (2026-09-30): elevated windows actually succeed via `direct`, so in practice a refusal means a focus lock.

Cursor helpers: `cursor_pos`, `warp_cursor` (`SetCursorPos`, physical pixels under per-monitor DPI v2), `window_center` and `clamp_point(p, work_rect)`.
M0-B results: `docs/spikes/m0b-focus-switch.md`.
