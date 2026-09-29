# gazefocus/win/msgwindow.py
Verified against: GazeFocus@024a9c5 · 2026-09-29

`MessageWindow` is a hidden **top-level** tool window (`WS_POPUP`, `WS_EX_TOOLWINDOW`, never shown). It is not `HWND_MESSAGE`, because message-only windows don't get broadcasts such as `WM_DISPLAYCHANGE`.
- A single module-level WNDPROC dispatches by hwnd to per-window handlers: `on(msg, handler)`, where the handler returns a result or `None` (meaning DefWindowProc).
- A handler that raises is logged and swallowed, so it can't break the message loop.
- **Pumping:** in the app, Qt's event loop dispatches these messages (verified by `test_qt_event_loop_pumps_the_window`). `pump_messages(seconds)` is a bare pump for tests and CLI diagnostics.
- Uses: Raw Input (`WM_INPUT`), the hotkey (`WM_HOTKEY`), session, power and display events.
