# gazefocus/win/capture.py
Verified against: GazeFocus@03c76d8 · 2026-09-30

- **`Grabber(w, h)`**: the screen's pixels in a fixed-size rect (physical px), through one reusable DIB section and `BitBlt(SRCCOPY | CAPTUREBLT)`.
  - `grab(x, y)` returns a BGR copy.
  - It costs 4–6 ms whatever the size (M0-C2), so the dock grabs at most 5 times a second, and never while animating.
- **`exclude_from_capture(hwnd)`**: `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)`. Every capture API, GDI included, then sees straight through the dock: 12,248 red test pixels before, 0 after (M0-C2). Screenshots don't show the dock either.
- **`make_noactivate(hwnd)`**: adds `WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST`, so the dock never becomes the foreground window (spec §8.5).
- **`dwm_flush()`**: blocks until the compositor's next frame, which is the display's refresh (240 Hz on this laptop).
