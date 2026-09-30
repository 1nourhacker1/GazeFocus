# gazefocus/dock/window.py
Verified against: GazeFocus@e017b50 · 2026-09-30

`DockWindow`: the Liquid Glass pill under the laptop camera, with the hover panel (spec §8) and the calibration's intro and result panels (spec §9).
- **Never focused:**
  - Qt: `Tool | FramelessWindowHint | WindowStaysOnTopHint | WindowDoesNotAcceptFocus` and `WA_ShowWithoutActivating`
  - Win32: `make_noactivate` and `WM_MOUSEACTIVATE → MA_NOACTIVATE`
  - It's also excluded from capture.
  - All the native calls are off unless Qt's platform is "windows", so tests on the offscreen platform never touch a real window.
- **Per-pixel alpha, no region:** the edges are antialiased, and Windows passes clicks through pixels with alpha 0.
- **Frames only on change:**
  - The idle timer grabs the backdrop 5 times a second, and only a change makes a frame (it also re-picks the light or dark theme).
  - `set_view` animates only on a glyph change, or on a text change while the panel is open.
  - Ticks come from `VBlankTicker` at the display's refresh. While the panel resizes, the glass is at half resolution, followed by one full-resolution settled frame. Slow animations are capped at 60 fps.
- **Hover:**
  - Hover and leave follow **the pill's shape** (mouse tracking), not the window or its shadow (final-review fix).
  - Opening takes 350 ms over the pill, then a 520 ms spring (`EXPAND`); leaving the pill takes 250 ms, then a 380 ms ease-out.
  - Opening calls `on_panel(True)`, and the app turns the camera preview on.
  - Closing drops the last preview frame; `set_preview` is refused while the panel is closed.
- **Clicks:**
  - The collapsed pill: a ripple plus `on_toggle_pause`.
  - The open panel: only Pause/Resume and Recalibrate act.
  - The shadow never acts.
- **Calibration panels** (modal):
  - `show_intro(on_start, on_cancel)` and `show_result(result, on_save, on_redo)` open the pill to that panel (`geometry.PANELS`). If the hover panel is open, the pill morphs from its size in 0.52 s, and its camera preview stops (`on_panel(False)`).
  - Hover and leave never open or close them. Only their buttons act (`dock/modal.py`); a click anywhere else, even on the pill, does nothing.
  - `close_modal()` closes the pill; the next hover opens the hover panel again.
  - `panel_open` means the hover panel only; `on_panel` reports only its changes.
- `set_hidden`: hide without closing (locked, asleep, or under a fullscreen app). No grabs, no frames.
- `set_freeze(seconds)`: a live `typing_freeze_ms` change, so the lid's melt still ends with the freeze.
- `place(work)`: the top centre of a work area in Qt logical coordinates (see `app/main.py:qt_work_area`).
